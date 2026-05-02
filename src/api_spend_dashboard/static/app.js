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
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function setStatus(message, state = "") {
  const status = document.querySelector("#sync-status");
  status.textContent = message;
  status.className = state ? `is-${state}` : "";
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

  const cards = [
    {
      label: "Month spend",
      value: formatCurrency(summary.total_cost),
      subtext: `${formatNumber(summary.provider_count)} providers with data`,
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
      label: "Daily spend",
      value: formatCurrency(totalDailyCost),
      subtext: "Visible 30-day rows",
    },
  ];

  document.querySelector("#summary-cards").innerHTML = cards
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
}

function renderProviders(statuses) {
  const configured = providers.filter((provider) => statuses[provider.id]?.status === "configured").length;
  const total = providers.length;
  const hint = document.querySelector("#config-hint");
  hint.textContent = `${configured} of ${total} providers configured. Missing fields are shown on each card.`;

  document.querySelector("#provider-grid").innerHTML = providers
    .map((provider) => {
      const config = statuses[provider.id] || { status: "unknown", missing: [] };
      const statusText = config.status.replaceAll("_", " ");
      const missing = Array.isArray(config.missing) ? config.missing : [];
      const detail = missing.length ? `Missing ${missing.join(", ")}` : "No required fields missing";

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

function buildProviderTotals(dailyCosts) {
  return providers
    .map((provider) => ({
      ...provider,
      total: dailyCosts
        .filter((row) => row.provider_id === provider.id)
        .reduce((sum, row) => sum + Number(row.cost || 0), 0),
    }))
    .filter((provider) => provider.total > 0);
}

function renderCharts(summaryData) {
  const dailyCosts = summaryData.daily_costs || [];
  const trendContext = document.querySelector("#trend-chart");
  const shareContext = document.querySelector("#share-chart");

  if (trendChart) {
    trendChart.destroy();
  }
  if (shareChart) {
    shareChart.destroy();
  }

  const trendData = buildDailyDatasets(dailyCosts);
  trendChart = new Chart(trendContext, {
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

  const providerTotals = buildProviderTotals(dailyCosts);
  shareChart = new Chart(shareContext, {
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

async function loadDashboard() {
  setStatus("Loading dashboard...");

  try {
    const [summaryData, configStatus] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/config/status"),
    ]);

    renderSummaryCards(summaryData);
    renderProviders(configStatus);
    renderCharts(summaryData);
    setStatus("Dashboard loaded", "ok");
  } catch (error) {
    setStatus(`Load failed: ${error.message}`, "error");
  }
}

async function syncNow() {
  const button = document.querySelector("#sync-now");
  button.disabled = true;
  setStatus("Syncing providers...");

  try {
    const result = await fetchJson("/api/sync", { method: "POST" });
    if (result.sync?.status === "already_running") {
      setStatus("Sync is already running", "error");
      return;
    }

    await loadDashboard();
  } catch (error) {
    setStatus(`Sync failed: ${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#sync-now").addEventListener("click", syncNow);
  loadDashboard();
});
