const providers = [
  { id: "openai", name: "OpenAI API" },
  { id: "chatgpt_pro", name: "ChatGPT Pro" },
  { id: "minimax", name: "MiniMax" },
  { id: "gemini", name: "Gemini" },
  { id: "qianfan", name: "Baidu Qianfan" },
  { id: "brave", name: "Brave Search" },
  { id: "digitalocean", name: "DigitalOcean" },
];

const colors = {
  openai: "#2563eb",
  chatgpt_pro: "#16794c",
  minimax: "#c2410c",
  gemini: "#7c3aed",
  qianfan: "#0f766e",
  brave: "#b45309",
  digitalocean: "#0284c7",
};

let trendChart = null;
let shareChart = null;

function formatCurrency(value) {
  return formatCurrencyWithCode(value, "USD");
}

function formatCurrencyWithCode(value, currency = "USD") {
  const code = currency || "USD";
  const amount = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
  return `${code} ${amount}`;
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function breakdownName(row) {
  if (row.source_type === "recurring_expense") {
    return row.name || row.expense_id;
  }
  return providers.find((provider) => provider.id === row.provider_id)?.name || row.provider_id;
}

function setStatus(message, state = "") {
  const status = document.querySelector("#sync-status");
  status.textContent = message;
  status.className = state ? `is-${state}` : "";
}

function setChartState(chartId, message) {
  const state = document.querySelector(`#${chartId}-state`);
  if (state) {
    state.textContent = message;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }

  return response.json();
}

function renderSummaryCards(summaryData) {
  const summary = summaryData.summary || summaryData.month || {};
  const dailyCosts = summaryData.daily_costs || [];
  const totalDailyCost = dailyCosts.reduce((sum, row) => sum + Number(row.cost || 0), 0);
  const monthSpend = monthSpendCard(summaryData);

  const cards = [
    {
      label: "Month spend",
      value: monthSpend.value,
      subtext: monthSpend.subtext,
      tooltip: monthSpend.tooltip,
    },
    {
      label: "Tracked tokens",
      value: formatNumber(summary.total_tokens),
      subtext: "Current calendar month",
    },
    {
      label: "Requests",
      value: formatNumber(summary.total_requests),
      subtext: "Recorded usage events",
    },
    {
      label: "Actual daily spend",
      value: formatCurrency(totalDailyCost),
      subtext: "Providers with daily rows",
    },
  ];

  document.querySelector("#summary-cards").innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card${card.tooltip ? " metric-card--has-tooltip" : ""}" ${
          card.tooltip ? 'tabindex="0" aria-describedby="month-spend-tooltip"' : ""
        }>
          <p class="metric-label">${escapeHtml(card.label)}</p>
          <p class="metric-value">${escapeHtml(card.value)}</p>
          <p class="metric-subtext">${escapeHtml(card.subtext)}</p>
          ${card.tooltip || ""}
        </article>
      `,
    )
    .join("");
}

function monthSpendCard(summaryData) {
  const summary = summaryData.summary || summaryData.month || {};
  const currencyTotals = summary.cost_totals_by_currency || [];
  const convertedTotal = summary.converted_total || null;
  const availableBreakdown = (summaryData.month_cost_breakdown || []).filter((row) => row.cost_available);
  const unavailableBreakdown = (summaryData.month_cost_breakdown || []).filter((row) => !row.cost_available);
  const value = convertedTotal?.amount != null
    ? formatCurrencyWithCode(convertedTotal.amount, convertedTotal.currency)
    : currencyTotals.length
    ? currencyTotals.map((row) => formatCurrencyWithCode(row.cost, row.currency)).join(" + ")
    : formatCurrencyWithCode(summary.total_cost, "USD");
  const subtext =
    convertedTotal?.amount != null
      ? `${formatSpendSourceCount(summary)} · converted to ${convertedTotal.currency}`
      : `${formatSpendSourceCount(summary)} · missing FX rate`;

  return {
    value,
    subtext,
    tooltip: renderMonthSpendTooltip(availableBreakdown, unavailableBreakdown, convertedTotal),
  };
}

function renderMonthSpendTooltip(availableRows, unavailableRows, convertedTotal = null) {
  const rows = [...availableRows, ...unavailableRows];
  if (!rows.length) {
    return "";
  }

  const lineItems = rows
    .map((row) => {
      const amount = row.cost_available
        ? formatCurrencyWithCode(row.cost, row.currency)
        : `${row.currency || "USD"} unavailable`;
      return `
        <li>
          <span>${escapeHtml(breakdownName(row))}</span>
          <strong>${escapeHtml(amount)}</strong>
          <em>${escapeHtml(formatBreakdownDetail(row))}</em>
        </li>
      `;
    })
    .join("");

  return `
    <div id="month-spend-tooltip" class="metric-tooltip" role="tooltip">
      <p>Included in month spend</p>
      <ul>${lineItems}</ul>
      ${renderConversionSummary(convertedTotal)}
    </div>
  `;
}

function renderConversionSummary(convertedTotal) {
  if (!convertedTotal) {
    return "";
  }
  if (convertedTotal.amount == null) {
    return `<small>Missing FX rate for ${escapeHtml((convertedTotal.missing_rates || []).join(", "))}.</small>`;
  }
  const rateLines = (convertedTotal.items || [])
    .map((item) => `${item.currency} x ${item.rate}`)
    .join(" · ");
  return `<small>Converted to ${escapeHtml(convertedTotal.currency)} using ${escapeHtml(rateLines)}. ${escapeHtml(
    convertedTotal.source || "",
  )}</small>`;
}

function formatSpendSourceCount(summary) {
  const providerCount = Number(summary.provider_count || 0);
  const expenseCount = Number(summary.recurring_expense_count || 0);
  const parts = [];
  if (providerCount) {
    parts.push(`${formatNumber(providerCount)} providers`);
  }
  if (expenseCount) {
    parts.push(`${formatNumber(expenseCount)} recurring`);
  }
  return parts.length ? `${parts.join(" + ")} with data` : "No spend data";
}

function formatBreakdownDetail(row) {
  if (row.source_type === "recurring_expense") {
    return [row.category, row.due_date ? `due ${row.due_date}` : ""].filter(Boolean).join(" · ");
  }
  return formatCostBasis([row]) || "snapshot";
}

function renderCodexTokenSummary(usage) {
  const hint = document.querySelector("#codex-token-hint");
  const summary = document.querySelector("#codex-token-summary");

  if (!usage.available) {
    hint.textContent = "No rollout files found under CODEX_HOME sessions.";
    summary.innerHTML = `
      <article class="metric-card codex-token-empty">
        <p class="metric-label">Local tokens</p>
        <p class="metric-value">0</p>
        <p class="metric-subtext">No Codex CLI token records found</p>
      </article>
    `;
    renderCodexDailyUsage([]);
    return;
  }

  hint.textContent = `${formatNumber(usage.session_count)} sessions with token counts from ${formatNumber(
    usage.files_scanned,
  )} rollout files.`;

  const cards = [
    {
      label: "Total",
      value: formatNumber(usage.total_tokens),
      subtext: "All local Codex CLI sessions",
    },
    {
      label: "Input",
      value: formatNumber(usage.input_tokens),
      subtext: "Prompt and context tokens",
    },
    {
      label: "Cached input",
      value: formatNumber(usage.cached_input_tokens),
      subtext: "Prompt tokens served from cache",
    },
    {
      label: "Output",
      value: formatNumber(usage.output_tokens),
      subtext: "Assistant response tokens",
    },
    {
      label: "Reasoning output",
      value: formatNumber(usage.reasoning_output_tokens),
      subtext: "Reasoning tokens reported by Codex",
    },
  ];

  summary.innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card">
          <p class="metric-label">${card.label}</p>
          <p class="metric-value">${card.value}</p>
          <p class="metric-subtext">${card.subtext}</p>
        </article>
      `,
    )
    .join("");
  renderCodexDailyUsage(usage.daily_token_usage || []);
}

function renderCodexDailyUsage(rows) {
  const dailyUsage = document.querySelector("#codex-daily-usage");
  const recentRows = rows.slice(0, 14);

  if (!recentRows.length) {
    dailyUsage.innerHTML = `<p class="codex-daily-state">No daily Codex token rows found.</p>`;
    return;
  }

  dailyUsage.innerHTML = `
    <table class="codex-daily-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Sessions</th>
          <th>Total</th>
          <th>Input</th>
          <th>Cached</th>
          <th>Output</th>
          <th>Reasoning</th>
        </tr>
      </thead>
      <tbody>
        ${recentRows
          .map(
            (row) => `
              <tr>
                <td>${row.date || "Unknown"}</td>
                <td>${formatNumber(row.session_count)}</td>
                <td>${formatNumber(row.total_tokens)}</td>
                <td>${formatNumber(row.input_tokens)}</td>
                <td>${formatNumber(row.cached_input_tokens)}</td>
                <td>${formatNumber(row.output_tokens)}</td>
                <td>${formatNumber(row.reasoning_output_tokens)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderCodexTokenError(error) {
  const hint = document.querySelector("#codex-token-hint");
  const summary = document.querySelector("#codex-token-summary");
  hint.textContent = `Could not load local Codex tokens: ${error.message}`;
  summary.innerHTML = `
    <article class="metric-card codex-token-empty">
      <p class="metric-label">Local tokens</p>
      <p class="metric-value">--</p>
      <p class="metric-subtext">Check that CODEX_HOME is readable by this server.</p>
    </article>
  `;
  document.querySelector("#codex-daily-usage").innerHTML =
    `<p class="codex-daily-state">Daily token usage unavailable.</p>`;
}

async function loadCodexTokenSummary() {
  try {
    renderCodexTokenSummary(await fetchJson("/api/codex/tokens"));
  } catch (error) {
    renderCodexTokenError(error);
  }
}

function providerTotalsById(summaryData) {
  return (summaryData.provider_totals || []).reduce((byId, row) => {
    byId[row.provider_id] ||= [];
    byId[row.provider_id].push(row);
    return byId;
  }, {});
}

function renderProviders(statuses, summaryData) {
  const configured = providers.filter((provider) => statuses[provider.id]?.status === "configured").length;
  const total = providers.length;
  const hint = document.querySelector("#config-hint");
  hint.textContent = `${configured} of ${total} providers configured. Missing fields are shown on each card.`;
  const totalsById = providerTotalsById(summaryData);

  document.querySelector("#provider-grid").innerHTML = providers
    .map((provider) => {
      const config = statuses[provider.id] || { status: "unknown", missing: [] };
      const statusText = config.status.replaceAll("_", " ");
      const missing = Array.isArray(config.missing) ? config.missing : [];
      const totals = totalsById[provider.id] || [];
      const spendText = totals.length
        ? `Month spend ${totals.map(formatProviderTotal).join(", ")}`
        : "No spend snapshot for this month";
      const basisText = totals.length ? formatCostBasis(totals) : "";
      const detail = config.last_error
        ? config.last_error
        : missing.length
          ? `Missing ${missing.join(", ")}`
          : [spendText, basisText].filter(Boolean).join(" · ");

      return `
        <article class="provider-card">
          <h3 class="provider-name">${provider.name}</h3>
          <span class="status-pill ${config.status}">${statusText}</span>
          <p class="provider-detail">${detail}</p>
        </article>
      `;
    })
    .join("");
}

function renderRecurringExpenses(summaryData) {
  const expenses = summaryData.recurring_expenses || [];
  const container = document.querySelector("#recurring-expenses");
  const hint = document.querySelector("#recurring-hint");

  if (!expenses.length) {
    hint.textContent = "No recurring expenses configured in .env.";
    container.innerHTML = `<p class="recurring-state">No fixed monthly expenses configured.</p>`;
    return;
  }

  hint.textContent = `${formatNumber(expenses.length)} fixed monthly expense(s) configured in .env.`;
  container.innerHTML = `
    <table class="recurring-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Category</th>
          <th>Amount</th>
          <th>Due date</th>
          <th>Status</th>
          <th>Payment</th>
        </tr>
      </thead>
      <tbody>
        ${expenses
          .map(
            (expense) => `
              <tr>
                <td>${escapeHtml(expense.name)}</td>
                <td>${escapeHtml(expense.category)}</td>
                <td>${escapeHtml(formatCurrencyWithCode(expense.amount, expense.currency))}</td>
                <td>${escapeHtml(expense.due_date)}</td>
                <td><span class="expense-status ${escapeHtml(expense.status)}">${escapeHtml(
                  formatExpenseStatus(expense.status),
                )}</span></td>
                <td>${escapeHtml(formatPaymentMethod(expense.payment_method))}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function formatExpenseStatus(status) {
  return (status || "upcoming").replaceAll("_", " ");
}

function formatPaymentMethod(method) {
  return method ? method.replaceAll("_", " ") : "-";
}

function formatProviderTotal(row) {
  if (!row.cost_available) {
    return `${row.currency || "USD"} unavailable`;
  }
  return formatCurrencyWithCode(row.cost, row.currency);
}

function formatCostBasis(rows) {
  const bases = [...new Set(rows.map((row) => row.cost_basis).filter(Boolean))];
  if (bases.includes("actual_daily")) {
    return "actual daily";
  }
  if (bases.includes("month_snapshot")) {
    return "month snapshot";
  }
  if (bases.includes("recurring")) {
    return "recurring";
  }
  return "";
}

function buildDailyDatasets(dailyCosts) {
  const dates = [...new Set(dailyCosts.map((row) => row.date))].sort();

  return {
    labels: dates,
    datasets: providers.map((provider) => ({
      label: provider.name,
      data: dates.map((date) => {
        return dailyCosts
          .filter((row) => row.date === date && row.provider_id === provider.id)
          .reduce((sum, row) => sum + Number(row.cost || 0), 0);
      }),
      borderColor: colors[provider.id],
      backgroundColor: colors[provider.id],
      borderWidth: 2,
      pointRadius: 2,
      tension: 0.25,
    })),
  };
}

function buildMonthProviderTotals(summaryData) {
  const totalsByProvider = providerTotalsById(summaryData);
  return providers
    .map((provider) => ({
      ...provider,
      total: (totalsByProvider[provider.id] || [])
        .filter((row) => row.cost_available)
        .reduce((sum, row) => sum + Number(row.cost || 0), 0),
    }))
    .filter((provider) => provider.total > 0);
}

function renderCharts(summaryData) {
  const dailyCosts = summaryData.daily_costs || [];
  const trendContext = document.querySelector("#trend-chart");
  const shareContext = document.querySelector("#share-chart");
  const chartUnavailableMessage = "Charts unavailable because Chart.js did not load.";

  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }
  if (shareChart) {
    shareChart.destroy();
    shareChart = null;
  }

  if (!window.Chart) {
    setChartState("trend-chart", chartUnavailableMessage);
    setChartState("share-chart", chartUnavailableMessage);
    return;
  }

  if (dailyCosts.length) {
    setChartState("trend-chart", "");
    const trendData = buildDailyDatasets(dailyCosts);
    trendChart = new window.Chart(trendContext, {
      type: "line",
      data: trendData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 12, usePointStyle: true },
          },
          tooltip: {
            callbacks: {
              label: (context) => `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`,
            },
          },
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { callback: (value) => formatCurrency(value) },
          },
        },
      },
    });
  } else {
    setChartState("trend-chart", "No daily spend rows yet.");
  }

  if ((summaryData.summary?.cost_totals_by_currency || []).length > 1) {
    setChartState("share-chart", "Provider share unavailable across mixed currencies.");
    return;
  }

  const providerTotals = buildMonthProviderTotals(summaryData);
  if (!providerTotals.length) {
    setChartState("share-chart", "No provider spend to chart yet.");
    return;
  }

  setChartState("share-chart", "");
  shareChart = new window.Chart(shareContext, {
    type: "doughnut",
    data: {
      labels: providerTotals.map((provider) => provider.name),
      datasets: [
        {
          data: providerTotals.map((provider) => provider.total),
          backgroundColor: providerTotals.map((provider) => colors[provider.id]),
          borderColor: "#ffffff",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label: (context) => `${context.label}: ${formatCurrency(context.parsed)}`,
          },
        },
      },
    },
  });
}

function summarizeSyncResult(result) {
  if (result.sync?.status === "already_running") {
    return { message: "Sync is already running.", state: "error" };
  }

  const providerResults = result.providers || {};
  const providerErrors = Object.entries(providerResults)
    .filter(([, providerResult]) => {
      return (
        providerResult.status === "failed" ||
        providerResult.status === "unknown_error" ||
        Boolean(providerResult.error_type || providerResult.error_message || providerResult.error)
      );
    })
    .map(([providerId]) => providerId);

  if (providerErrors.length) {
    return {
      message: `Sync completed with ${providerErrors.length} provider error(s): ${providerErrors.join(", ")}`,
      state: "error",
    };
  }

  const providerCount = Object.keys(providerResults).length;
  if (!providerCount) {
    return { message: "Sync completed; no configured providers ran.", state: "ok" };
  }

  return {
    message: `Sync completed for ${providerCount} provider(s).`,
    state: "ok",
  };
}

async function loadDashboard(statusOverride = null) {
  if (!statusOverride) {
    setStatus("Loading dashboard...");
  }

  try {
    const [summaryData, configStatus] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/config/status"),
    ]);

    renderSummaryCards(summaryData);
    renderProviders(configStatus, summaryData);
    renderRecurringExpenses(summaryData);
    renderCharts(summaryData);
    if (statusOverride) {
      setStatus(statusOverride.message, statusOverride.state);
    } else {
      setStatus("Dashboard loaded", "ok");
    }
  } catch (error) {
    if (statusOverride) {
      setStatus(`${statusOverride.message}; dashboard refresh failed: ${error.message}`, "error");
    } else {
      setStatus(`Load failed: ${error.message}`, "error");
    }
  }
}

async function syncNow() {
  const button = document.querySelector("#sync-now");
  button.disabled = true;
  setStatus("Syncing providers...");

  try {
    const result = await fetchJson("/api/sync", { method: "POST" });
    const syncStatus = summarizeSyncResult(result);
    if (result.sync?.status === "already_running") {
      setStatus(syncStatus.message, syncStatus.state);
      return;
    }

    await loadDashboard(syncStatus);
    await loadCodexTokenSummary();
  } catch (error) {
    setStatus(`Sync failed: ${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#sync-now").addEventListener("click", syncNow);
  loadDashboard();
  loadCodexTokenSummary();
});
