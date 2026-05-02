# API Spend Dashboard Design

Date: 2026-05-02

## Goal

Build a browser-based local dashboard for monitoring personal API and infrastructure spend across OpenAI API, ChatGPT Pro, MiniMax Token Plan, Gemini API, Baidu Qianfan, Brave Search API, and DigitalOcean.

The dashboard runs locally, reads secrets from `.env`, syncs provider usage on an internal schedule, stores historical snapshots in SQLite, and displays current month cost, usage trends, platform status, and configuration gaps.

## Decisions

- Use a local Python FastAPI service, not a static HTML file.
- Serve a lightweight first-party frontend from FastAPI using HTML, CSS, vanilla JavaScript, and Chart.js.
- Use SQLite for local history.
- Use application-managed periodic sync, with a dashboard "sync now" action.
- Keep one account instance per provider in v1.
- Store API keys only in `.env`; never expose them to the frontend.
- Treat missing provider configuration as a visible provider status, not a startup failure.
- Use the overview-first dashboard layout selected during brainstorming.

## Architecture

The application is a local FastAPI monolith with four responsibilities:

1. Configuration loading and validation from `.env`.
2. Provider connector execution.
3. SQLite persistence and aggregation.
4. Local HTTP API and dashboard UI.

The backend exposes local endpoints such as:

- `GET /` for the dashboard page.
- `GET /api/summary` for top-level month-to-date metrics and charts.
- `GET /api/providers` for provider card status.
- `GET /api/providers/{provider_id}` for provider detail.
- `POST /api/sync` for manual sync.
- `GET /api/config/status` for missing or invalid configuration.

Provider connectors return a normalized snapshot. The frontend never calls provider APIs directly.

## Dashboard UX

The v1 dashboard is overview-first:

- Top row: month-to-date total spend, today's added spend, total tokens/requests, and number of providers with errors or missing config.
- Middle row: 30-day spend trend and provider spend share.
- Provider cards: OpenAI API, ChatGPT Pro, MiniMax, Gemini, Baidu Qianfan, Brave Search, and DigitalOcean.
- Each card shows current cost/usage, last sync time, status, and a short actionable message.
- Provider detail panels show historical snapshots, quota information, recent sync runs, and the exact missing `.env` variables when relevant.

The UI is quiet and operational rather than decorative. It should support repeated local use: quick scanning, clear errors, and immediate sync feedback.

## Provider Connectors

### OpenAI API

Use OpenAI organization usage and costs endpoints to collect API usage and spend. The Usage API exposes organization usage endpoints such as completions, embeddings, images, moderations, audio, and code interpreter sessions. The Costs endpoint is preferred for financial reconciliation.

Configuration:

- `OPENAI_ENABLED`
- `OPENAI_ADMIN_API_KEY`
- `OPENAI_ORG_ID` if required by the API key setup

Displayed:

- API spend by day and month.
- Token totals where available.
- Request counts.
- Last sync and error status.

Limitation:

- ChatGPT consumer subscription data is separate from OpenAI API billing and is not queried through the OpenAI API connector.

Sources:

- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage
- https://help.openai.com/en/articles/9039756-billing-settings-in-chatgpt-vs-platform

### ChatGPT Pro

Treat ChatGPT Pro as a manual fixed subscription item. OpenAI documents ChatGPT billing and API billing as separate systems, and ChatGPT Pro does not provide an official token-usage API for this use case.

Configuration:

- `CHATGPT_PRO_ENABLED`
- `CHATGPT_PRO_PLAN_NAME`
- `CHATGPT_PRO_PRICE`
- `CHATGPT_PRO_CURRENCY`
- `CHATGPT_PRO_BILLING_PERIOD`
- `CHATGPT_PRO_RENEWAL_DATE`
- `CHATGPT_PRO_NOTES`

Displayed:

- Subscription cost allocation for the current month.
- Renewal date and notes.
- Explicit status saying token usage is not automatically available.

### MiniMax Token Plan

Use the official Token Plan remains endpoint. MiniMax documents Token Plan usage as request quota for M2.7 over a 5-hour rolling window and daily quotas for other modalities.

Configuration:

- `MINIMAX_ENABLED`
- `MINIMAX_API_KEY`
- `MINIMAX_BASE_URL`
- `MINIMAX_PLAN_NAME`
- `MINIMAX_PLAN_PRICE`
- `MINIMAX_PLAN_CURRENCY`
- `MINIMAX_PLAN_START_DATE`
- `MINIMAX_PLAN_END_DATE`

Displayed:

- Remaining quota and reset information returned by the endpoint.
- Manually configured subscription dates and price.
- Status if the selected base URL fails.

Sources:

- https://platform.minimax.io/docs/token-plan/faq
- https://platform.minimaxi.com/docs/coding-plan/faq

### Gemini API

Use Google Cloud Billing Export to BigQuery for accurate cost data. Gemini API billing is handled through Cloud Billing, and Google documents BigQuery export as the way to export detailed billing data automatically.

Configuration:

- `GEMINI_ENABLED`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `GCP_BILLING_PROJECT_ID`
- `GCP_BILLING_DATASET`
- `GCP_BILLING_TABLE`
- `GEMINI_SERVICE_FILTER`

Displayed:

- Gemini API spend from billing export.
- BigQuery sync status and most recent available billing date.
- `missing_config` until billing export and credentials are provided.

Setup required from the user before enabling:

1. Enable Cloud Billing export to BigQuery.
2. Create or select a BigQuery dataset.
3. Create a service account with read access to the billing export dataset.
4. Download the service account JSON locally.
5. Add the JSON path and table identifiers to `.env`.

Sources:

- https://ai.google.dev/gemini-api/docs/billing/
- https://cloud.google.com/billing/docs/how-to/export-data-bigquery

### Baidu Qianfan

Use Qianfan's `DescribeServiceMetric` management API to query service usage metrics. The API requires Baidu Cloud AK/SK signature authentication and Qianfan read permissions.

Configuration:

- `QIANFAN_ENABLED`
- `BAIDU_ACCESS_KEY_ID`
- `BAIDU_SECRET_ACCESS_KEY`
- `QIANFAN_ENDPOINT`
- `QIANFAN_SERVICE_IDS`
- `QIANFAN_APP_IDS`

Displayed:

- Input tokens, output tokens, total tokens, request totals, failure metrics where available.
- Cost if the response includes cost-like fields or if a configured pricing estimate is available.
- Permission or signing errors as actionable status.

Sources:

- https://cloud.baidu.com/doc/qianfan-api/s/4mm33t0kj
- https://cloud.baidu.com/doc/qianfan-docs/s/km96ryv9w

### Brave Search API

Use a lightweight probe request to Brave Search and read rate limit headers. Brave documents rate limit headers including `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. There is no separate public usage billing endpoint identified for v1.

Configuration:

- `BRAVE_ENABLED`
- `BRAVE_API_KEY`
- `BRAVE_PROBE_QUERY`
- `BRAVE_PRICE_PER_1000_REQUESTS`
- `BRAVE_CURRENCY`

Displayed:

- Monthly quota, remaining quota, reset time.
- Estimated used requests and estimated cost from configured pricing.
- Warning that cost is an estimate based on rate limit headers and configured price.

Sources:

- https://api-dashboard.search.brave.com/documentation/guides/rate-limiting
- https://brave.com/search/api/

### DigitalOcean

Use DigitalOcean billing endpoints to retrieve balance, invoices, billing history, and billing insights.

Configuration:

- `DIGITALOCEAN_ENABLED`
- `DIGITALOCEAN_TOKEN`

Displayed:

- Current balance.
- Invoice preview or latest invoice data.
- Billing insights by day and resource where available.
- VPS-related spend trends where billing insights provide resource descriptions.

Source:

- https://docs.digitalocean.com/platform/billing/reference/api/

## Data Model

### `providers`

Stores provider metadata and runtime status, but never stores secrets.

Fields:

- `id`
- `name`
- `enabled`
- `status`
- `last_sync_at`
- `last_success_at`
- `last_error`
- `created_at`
- `updated_at`

### `sync_runs`

Stores one row per provider sync attempt.

Fields:

- `id`
- `provider_id`
- `started_at`
- `finished_at`
- `status`
- `error_type`
- `error_message`
- `snapshots_written`

### `usage_snapshots`

Stores normalized historical measurements.

Fields:

- `id`
- `provider_id`
- `period_start`
- `period_end`
- `granularity`
- `currency`
- `cost_amount`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `requests`
- `quota_limit`
- `quota_remaining`
- `quota_reset_at`
- `raw_summary_json`
- `created_at`

The unique key is provider, period, granularity, and metric shape so repeated syncs update the same daily bucket instead of duplicating data.

### `manual_items`

Stores manual recurring items such as ChatGPT Pro and manually configured MiniMax subscription metadata.

Fields:

- `id`
- `provider_id`
- `name`
- `amount`
- `currency`
- `billing_period`
- `start_date`
- `end_date`
- `renewal_date`
- `notes`

### `settings`

Stores local display and sync preferences.

Fields:

- `key`
- `value`
- `updated_at`

## Configuration

The app reads `.env` at startup. Missing provider-specific variables mark that provider as `missing_config`; they do not prevent the service from starting.

Core variables:

- `APP_HOST=127.0.0.1`
- `APP_PORT=8000`
- `DATABASE_URL=sqlite:///./data/api_spend.sqlite3`
- `SYNC_INTERVAL_HOURS=6`
- `DEFAULT_CURRENCY=USD`
- `HTTP_TIMEOUT_SECONDS=30`

Secrets remain in `.env` and are included in `.gitignore`.

## Error Handling

Each provider sync is isolated:

- One provider failure does not fail the whole sync run.
- Errors are classified as `missing_config`, `auth_error`, `permission_error`, `rate_limited`, `timeout`, `provider_error`, `parse_error`, or `unknown_error`.
- Provider cards display the latest actionable error.
- Sanitized raw summaries can be stored for debugging, but full sensitive responses and keys are never persisted.

## Scheduling

The app starts an internal scheduler when FastAPI starts.

- Default interval: every 6 hours.
- Manual sync endpoint: `POST /api/sync`.
- If a sync is already running, additional sync requests return a clear "already running" response.
- Sync runs are serialized to avoid overlapping provider calls and duplicate writes.

## Testing

Test coverage should focus on connector parsing, persistence, aggregation, and endpoint behavior:

- Connector tests with mocked provider responses and mocked errors.
- Database tests for upsert behavior and monthly/daily aggregation.
- API tests for summary, provider status, config status, and sync trigger.
- Frontend smoke test that confirms the dashboard route loads and key containers are present.

No tests should require real provider credentials.

## User Setup Requirements

The user must provide the following credentials/configuration as needed:

- OpenAI Platform admin API key for organization usage/cost queries.
- MiniMax Token Plan API key and plan metadata.
- Google Cloud Billing export to BigQuery plus service account JSON path.
- Baidu Cloud AK/SK with Qianfan read permissions.
- Brave Search API key.
- DigitalOcean personal access token with billing read access.
- ChatGPT Pro subscription metadata entered manually in `.env`.

## Out of Scope for v1

- Multiple accounts per provider.
- Cloud deployment or remote access.
- Browser-based provider OAuth login.
- Scraping provider web consoles.
- Automatic ChatGPT Pro token usage.
- Currency conversion unless a provider returns a non-default currency.
- Alerting beyond visible dashboard status.

## Open Questions Deferred to Implementation

- Exact raw response shapes for MiniMax remains endpoint across `.io` and `.com` domains.
- Whether Baidu Qianfan response includes cost fields sufficient for direct spend display or only token/request metrics.
- Exact BigQuery table naming chosen by the user's Google Cloud Billing export setup.
