# API Spend Dashboard

Local browser dashboard for tracking personal API and infrastructure usage costs.

## Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
scripts/restart-server.sh
```

Open http://127.0.0.1:8000.

The restart script stops any existing project Uvicorn process on the target port, then starts the dashboard in the foreground. Keep that terminal open while using the dashboard; press `Ctrl+C` to stop it. Runtime PID data is written under `.run/`. To use a different port:

```bash
PORT=8001 scripts/restart-server.sh
```

## Configuration

All secrets live in `.env`. The frontend never receives provider credentials.

Start from `.env.example` and enable only the providers you want to sync.

### OpenAI API

Set `OPENAI_ENABLED=true` and `OPENAI_ADMIN_API_KEY`. The key must have permission to read organization usage and costs. If your account requires an organization identifier, set `OPENAI_ORG_ID` too.

### ChatGPT Pro

Set `CHATGPT_PRO_ENABLED=true` and fill the manual plan metadata: `CHATGPT_PRO_PLAN_NAME`, `CHATGPT_PRO_PRICE`, `CHATGPT_PRO_CURRENCY`, `CHATGPT_PRO_BILLING_PERIOD`, `CHATGPT_PRO_RENEWAL_DATE`, and `CHATGPT_PRO_NOTES`.

ChatGPT Pro does not provide an official token usage API, so this dashboard tracks it as manually entered subscription metadata.

### MiniMax

Set `MINIMAX_ENABLED=true`, `MINIMAX_API_KEY`, and `MINIMAX_BASE_URL`. Fill the manual plan metadata with `MINIMAX_PLAN_NAME`, `MINIMAX_PLAN_PRICE`, `MINIMAX_PLAN_CURRENCY`, `MINIMAX_PLAN_START_DATE`, and `MINIMAX_PLAN_END_DATE`.

### Gemini

Set up Google Cloud Billing Export to BigQuery. Then set `GEMINI_ENABLED=true`, `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_BILLING_PROJECT_ID`, `GCP_BILLING_DATASET`, and `GCP_BILLING_TABLE`.

Use `GEMINI_SERVICE_FILTER` to control which exported billing rows are counted as Gemini spend.

### Baidu Qianfan

Set `QIANFAN_ENABLED=true`, `BAIDU_ACCESS_KEY_ID`, and `BAIDU_SECRET_ACCESS_KEY`. The AK/SK pair needs Qianfan read permissions. Optional filters are available through `QIANFAN_SERVICE_IDS` and `QIANFAN_APP_IDS`.

### Brave Search

Set `BRAVE_ENABLED=true` and `BRAVE_API_KEY`. Cost is estimated from quota headers and the configured request price in `BRAVE_PRICE_PER_1000_REQUESTS`; set `BRAVE_CURRENCY` to match that price.

### DigitalOcean

Set `DIGITALOCEAN_ENABLED=true` and `DIGITALOCEAN_TOKEN`.

## Data

SQLite data is stored under `data/` by default through `DATABASE_URL=sqlite:///./data/api_spend.sqlite3`. The `data/` directory is ignored by git.

## Verification

Task 9 verification used these commands/results:

- `.venv/bin/python -m pytest -q` -> `69 passed`
- `.venv/bin/python -m ruff check .` -> passed
- Uvicorn factory server was verified on port 8001 because port 8000 was already in use.
- `curl -s http://127.0.0.1:8001/ | rg "API Spend Dashboard"` -> matched `API Spend Dashboard`
- `curl -s http://127.0.0.1:8001/api/config/status | rg "openai|chatgpt_pro|minimax|gemini|qianfan|brave|digitalocean"` -> matched all provider keys
