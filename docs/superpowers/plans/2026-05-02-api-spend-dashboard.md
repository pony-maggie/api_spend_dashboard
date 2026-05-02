# API Spend Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI + SQLite browser dashboard that periodically syncs API spend and usage from OpenAI API, ChatGPT Pro manual subscription data, MiniMax Token Plan, Gemini BigQuery billing export, Baidu Qianfan, Brave Search API, and DigitalOcean.

**Architecture:** A Python FastAPI monolith reads `.env`, runs provider connectors, persists normalized snapshots in SQLite, and serves a vanilla HTML/CSS/JS dashboard with Chart.js. Each provider sync is isolated so missing config or API failure for one platform does not block the rest of the dashboard.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic Settings, HTTPX, APScheduler, SQLite stdlib, Google Cloud BigQuery client, pytest, respx, vanilla JS, Chart.js CDN.

---

## File Structure

- Create: `pyproject.toml` - package metadata, runtime dependencies, test tooling.
- Create: `.env.example` - all supported config variables with safe example values.
- Modify: `.gitignore` - keep local secrets, data, caches, and companion files out of git.
- Create: `src/api_spend_dashboard/__init__.py` - package marker.
- Create: `src/api_spend_dashboard/config.py` - typed environment configuration and provider config status.
- Create: `src/api_spend_dashboard/models.py` - dataclasses and typed dictionaries shared across app layers.
- Create: `src/api_spend_dashboard/db.py` - SQLite connection, schema migration, upsert helpers.
- Create: `src/api_spend_dashboard/providers/base.py` - provider connector protocol, errors, result types.
- Create: `src/api_spend_dashboard/providers/manual.py` - ChatGPT Pro and manual subscription connector.
- Create: `src/api_spend_dashboard/providers/openai.py` - OpenAI usage and costs connector.
- Create: `src/api_spend_dashboard/providers/minimax.py` - MiniMax Token Plan remains connector.
- Create: `src/api_spend_dashboard/providers/brave.py` - Brave Search quota header connector.
- Create: `src/api_spend_dashboard/providers/digitalocean.py` - DigitalOcean billing connector.
- Create: `src/api_spend_dashboard/providers/gemini.py` - Gemini BigQuery billing connector.
- Create: `src/api_spend_dashboard/providers/qianfan.py` - Baidu Qianfan metric connector and BCE signing.
- Create: `src/api_spend_dashboard/services/sync.py` - sync orchestration, scheduler guard, provider registry.
- Create: `src/api_spend_dashboard/services/queries.py` - dashboard summary and provider detail aggregation.
- Create: `src/api_spend_dashboard/main.py` - FastAPI app, startup scheduler, API routes, static/template serving.
- Create: `src/api_spend_dashboard/templates/index.html` - dashboard shell.
- Create: `src/api_spend_dashboard/static/app.css` - dashboard styling.
- Create: `src/api_spend_dashboard/static/app.js` - dashboard API calls and Chart.js rendering.
- Create: `tests/conftest.py` - temporary DB and settings fixtures.
- Create: `tests/test_config.py` - config parsing and missing config tests.
- Create: `tests/test_db.py` - schema, upsert, aggregation tests.
- Create: `tests/test_providers_*.py` - connector parsing tests.
- Create: `tests/test_sync.py` - isolated provider sync and locking tests.
- Create: `tests/test_api.py` - FastAPI endpoint tests.
- Create: `README.md` - local setup, provider credential guide, run instructions.

The current directory is not a git repository. Task 1 initializes git so later checkpoint commits work.

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `src/api_spend_dashboard/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git repository**

Run:

```bash
git init
```

Expected: `Initialized empty Git repository`.

- [ ] **Step 2: Write project metadata**

Create `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "api-spend-dashboard"
version = "0.1.0"
description = "Local dashboard for API usage and spend monitoring"
requires-python = ">=3.11"
dependencies = [
  "apscheduler>=3.10.4",
  "fastapi>=0.115.0",
  "google-cloud-bigquery>=3.25.0",
  "httpx>=0.27.0",
  "jinja2>=3.1.4",
  "pydantic>=2.8.0",
  "pydantic-settings>=2.4.0",
  "python-dotenv>=1.0.1",
  "uvicorn[standard]>=0.30.0"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.23.8",
  "respx>=0.21.1",
  "ruff>=0.6.0"
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 3: Write safe example environment**

Create `.env.example` with:

```dotenv
APP_HOST=127.0.0.1
APP_PORT=8000
DATABASE_URL=sqlite:///./data/api_spend.sqlite3
SYNC_INTERVAL_HOURS=6
DEFAULT_CURRENCY=USD
HTTP_TIMEOUT_SECONDS=30

OPENAI_ENABLED=false
OPENAI_ADMIN_API_KEY=
OPENAI_ORG_ID=

CHATGPT_PRO_ENABLED=true
CHATGPT_PRO_PLAN_NAME=ChatGPT Pro
CHATGPT_PRO_PRICE=0
CHATGPT_PRO_CURRENCY=USD
CHATGPT_PRO_BILLING_PERIOD=monthly
CHATGPT_PRO_RENEWAL_DATE=
CHATGPT_PRO_NOTES=

MINIMAX_ENABLED=false
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://www.minimax.io
MINIMAX_PLAN_NAME=
MINIMAX_PLAN_PRICE=0
MINIMAX_PLAN_CURRENCY=USD
MINIMAX_PLAN_START_DATE=
MINIMAX_PLAN_END_DATE=

GEMINI_ENABLED=false
GOOGLE_APPLICATION_CREDENTIALS=
GCP_BILLING_PROJECT_ID=
GCP_BILLING_DATASET=
GCP_BILLING_TABLE=
GEMINI_SERVICE_FILTER=Gemini API

QIANFAN_ENABLED=false
BAIDU_ACCESS_KEY_ID=
BAIDU_SECRET_ACCESS_KEY=
QIANFAN_ENDPOINT=https://qianfan.baidubce.com
QIANFAN_SERVICE_IDS=
QIANFAN_APP_IDS=

BRAVE_ENABLED=false
BRAVE_API_KEY=
BRAVE_PROBE_QUERY=api spend dashboard
BRAVE_PRICE_PER_1000_REQUESTS=5
BRAVE_CURRENCY=USD

DIGITALOCEAN_ENABLED=false
DIGITALOCEAN_TOKEN=
```

- [ ] **Step 4: Ensure ignore rules cover local artifacts**

Update `.gitignore` so it contains:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
data/
*.sqlite
*.sqlite3
.DS_Store
.superpowers/
```

- [ ] **Step 5: Create package marker and base test fixture**

Create `src/api_spend_dashboard/__init__.py` with:

```python
"""Local API spend dashboard."""
```

Create `tests/conftest.py` with:

```python
from pathlib import Path

import pytest


@pytest.fixture
def temp_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.sqlite3'}"
```

- [ ] **Step 6: Install dependencies**

Run:

```bash
python3 -m venv .venv
```

Run:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

Expected: package installs without dependency resolution errors.

- [ ] **Step 7: Run empty test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: pytest runs and reports no tests collected or all current tests passing.

- [ ] **Step 8: Commit scaffold**

Run:

```bash
git add pyproject.toml .env.example .gitignore src tests
git commit -m "chore: scaffold local dashboard project"
```

Expected: commit succeeds.

---

### Task 2: Configuration And Provider Status

**Files:**
- Create: `src/api_spend_dashboard/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py` with:

```python
from api_spend_dashboard.config import Settings


def test_provider_missing_config_is_reported(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        openai_enabled=True,
        openai_admin_api_key="",
        minimax_enabled=True,
        minimax_api_key="sk-minimax",
    )

    statuses = settings.provider_config_status()

    assert statuses["openai"]["status"] == "missing_config"
    assert statuses["openai"]["missing"] == ["OPENAI_ADMIN_API_KEY"]
    assert statuses["minimax"]["status"] == "configured"
    assert statuses["minimax"]["missing"] == []


def test_disabled_provider_is_not_missing_config(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=False, brave_api_key="")

    statuses = settings.provider_config_status()

    assert statuses["brave"]["status"] == "disabled"
    assert statuses["brave"]["missing"] == []
```

- [ ] **Step 2: Run config tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_config.py -q
```

Expected: FAIL because `api_spend_dashboard.config` does not exist.

- [ ] **Step 3: Implement settings**

Create `src/api_spend_dashboard/config.py` with:

```python
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/api_spend.sqlite3"
    sync_interval_hours: int = Field(default=6, ge=1)
    default_currency: str = "USD"
    http_timeout_seconds: int = Field(default=30, ge=1)

    openai_enabled: bool = False
    openai_admin_api_key: str = ""
    openai_org_id: str = ""

    chatgpt_pro_enabled: bool = True
    chatgpt_pro_plan_name: str = "ChatGPT Pro"
    chatgpt_pro_price: float = 0.0
    chatgpt_pro_currency: str = "USD"
    chatgpt_pro_billing_period: str = "monthly"
    chatgpt_pro_renewal_date: str = ""
    chatgpt_pro_notes: str = ""

    minimax_enabled: bool = False
    minimax_api_key: str = ""
    minimax_base_url: str = "https://www.minimax.io"
    minimax_plan_name: str = ""
    minimax_plan_price: float = 0.0
    minimax_plan_currency: str = "USD"
    minimax_plan_start_date: str = ""
    minimax_plan_end_date: str = ""

    gemini_enabled: bool = False
    google_application_credentials: str = ""
    gcp_billing_project_id: str = ""
    gcp_billing_dataset: str = ""
    gcp_billing_table: str = ""
    gemini_service_filter: str = "Gemini API"

    qianfan_enabled: bool = False
    baidu_access_key_id: str = ""
    baidu_secret_access_key: str = ""
    qianfan_endpoint: str = "https://qianfan.baidubce.com"
    qianfan_service_ids: str = ""
    qianfan_app_ids: str = ""

    brave_enabled: bool = False
    brave_api_key: str = ""
    brave_probe_query: str = "api spend dashboard"
    brave_price_per_1000_requests: float = 5.0
    brave_currency: str = "USD"

    digitalocean_enabled: bool = False
    digitalocean_token: str = ""

    def provider_config_status(self) -> dict[str, dict[str, Any]]:
        requirements = {
            "openai": (self.openai_enabled, {"OPENAI_ADMIN_API_KEY": self.openai_admin_api_key}),
            "chatgpt_pro": (self.chatgpt_pro_enabled, {}),
            "minimax": (self.minimax_enabled, {"MINIMAX_API_KEY": self.minimax_api_key}),
            "gemini": (
                self.gemini_enabled,
                {
                    "GOOGLE_APPLICATION_CREDENTIALS": self.google_application_credentials,
                    "GCP_BILLING_PROJECT_ID": self.gcp_billing_project_id,
                    "GCP_BILLING_DATASET": self.gcp_billing_dataset,
                    "GCP_BILLING_TABLE": self.gcp_billing_table,
                },
            ),
            "qianfan": (
                self.qianfan_enabled,
                {
                    "BAIDU_ACCESS_KEY_ID": self.baidu_access_key_id,
                    "BAIDU_SECRET_ACCESS_KEY": self.baidu_secret_access_key,
                },
            ),
            "brave": (self.brave_enabled, {"BRAVE_API_KEY": self.brave_api_key}),
            "digitalocean": (
                self.digitalocean_enabled,
                {"DIGITALOCEAN_TOKEN": self.digitalocean_token},
            ),
        }
        statuses: dict[str, dict[str, Any]] = {}
        for provider_id, (enabled, required) in requirements.items():
            if not enabled:
                statuses[provider_id] = {"status": "disabled", "missing": []}
                continue
            missing = [key for key, value in required.items() if not str(value).strip()]
            statuses[provider_id] = {
                "status": "missing_config" if missing else "configured",
                "missing": missing,
            }
        return statuses

    def csv_values(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run config tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit configuration**

Run:

```bash
git add src/api_spend_dashboard/config.py tests/test_config.py
git commit -m "feat: add typed dashboard configuration"
```

Expected: commit succeeds.

---

### Task 3: SQLite Schema And Aggregation

**Files:**
- Create: `src/api_spend_dashboard/models.py`
- Create: `src/api_spend_dashboard/db.py`
- Create: `src/api_spend_dashboard/services/queries.py`
- Create: `src/api_spend_dashboard/services/__init__.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing database tests**

Create `tests/test_db.py` with:

```python
from datetime import UTC, datetime

from api_spend_dashboard.db import Database
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.services.queries import DashboardQueries


def test_snapshot_upsert_and_month_summary(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    snapshot = UsageSnapshot(
        provider_id="openai",
        period_start=datetime(2026, 5, 1, tzinfo=UTC),
        period_end=datetime(2026, 5, 2, tzinfo=UTC),
        granularity="day",
        currency="USD",
        cost_amount=12.5,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        requests=3,
        quota_limit=None,
        quota_remaining=None,
        quota_reset_at=None,
        raw_summary={"source": "test"},
    )

    db.upsert_snapshot(snapshot)
    db.upsert_snapshot(snapshot)

    summary = DashboardQueries(db).month_summary(2026, 5)

    assert summary["total_cost"] == 12.5
    assert summary["total_tokens"] == 150
    assert summary["total_requests"] == 3
    assert summary["provider_count"] == 1


def test_sync_run_records_error(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    run_id = db.start_sync_run("openai")
    db.finish_sync_run(run_id, status="failed", error_type="auth_error", error_message="bad key")

    runs = db.recent_sync_runs("openai", limit=1)

    assert runs[0]["status"] == "failed"
    assert runs[0]["error_type"] == "auth_error"
    assert runs[0]["error_message"] == "bad key"
```

- [ ] **Step 2: Run database tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_db.py -q
```

Expected: FAIL because database modules do not exist.

- [ ] **Step 3: Implement shared models**

Create `src/api_spend_dashboard/models.py` with:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UsageSnapshot:
    provider_id: str
    period_start: datetime
    period_end: datetime
    granularity: str
    currency: str
    cost_amount: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    requests: int | None
    quota_limit: int | None
    quota_remaining: int | None
    quota_reset_at: datetime | None
    raw_summary: dict[str, Any]
```

Create `src/api_spend_dashboard/services/__init__.py` with:

```python
"""Application service layer."""
```

- [ ] **Step 4: Implement SQLite persistence**

Create `src/api_spend_dashboard/db.py` with the schema and helpers:

```python
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api_spend_dashboard.models import UsageSnapshot


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// database URLs are supported")
    return Path(database_url.removeprefix(prefix))


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


class Database:
    def __init__(self, database_url: str):
        self.path = _sqlite_path(database_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'disabled',
                    last_sync_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    snapshots_written INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS usage_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    granularity TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    cost_amount REAL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    requests INTEGER,
                    quota_limit INTEGER,
                    quota_remaining INTEGER,
                    quota_reset_at TEXT,
                    raw_summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider_id, period_start, period_end, granularity)
                );

                CREATE TABLE IF NOT EXISTS manual_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    billing_period TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    renewal_date TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def ensure_provider(self, provider_id: str, name: str, enabled: bool, status: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO providers (id, name, enabled, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    enabled = excluded.enabled,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (provider_id, name, int(enabled), status, now, now),
            )

    def upsert_snapshot(self, snapshot: UsageSnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_snapshots (
                    provider_id, period_start, period_end, granularity, currency, cost_amount,
                    input_tokens, output_tokens, total_tokens, requests, quota_limit,
                    quota_remaining, quota_reset_at, raw_summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, period_start, period_end, granularity) DO UPDATE SET
                    currency = excluded.currency,
                    cost_amount = excluded.cost_amount,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    total_tokens = excluded.total_tokens,
                    requests = excluded.requests,
                    quota_limit = excluded.quota_limit,
                    quota_remaining = excluded.quota_remaining,
                    quota_reset_at = excluded.quota_reset_at,
                    raw_summary_json = excluded.raw_summary_json
                """,
                (
                    snapshot.provider_id,
                    _to_iso(snapshot.period_start),
                    _to_iso(snapshot.period_end),
                    snapshot.granularity,
                    snapshot.currency,
                    snapshot.cost_amount,
                    snapshot.input_tokens,
                    snapshot.output_tokens,
                    snapshot.total_tokens,
                    snapshot.requests,
                    snapshot.quota_limit,
                    snapshot.quota_remaining,
                    _to_iso(snapshot.quota_reset_at),
                    json.dumps(snapshot.raw_summary, sort_keys=True),
                ),
            )

    def start_sync_run(self, provider_id: str) -> int:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sync_runs (provider_id, started_at, status) VALUES (?, ?, ?)",
                (provider_id, now, "running"),
            )
            return int(cursor.lastrowid)

    def finish_sync_run(
        self,
        run_id: int,
        *,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        snapshots_written: int = 0,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, error_type = ?, error_message = ?,
                    snapshots_written = ?
                WHERE id = ?
                """,
                (now, status, error_type, error_message, snapshots_written, run_id),
            )

    def recent_sync_runs(self, provider_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sync_runs
                WHERE provider_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (provider_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 5: Implement dashboard aggregation**

Create `src/api_spend_dashboard/services/queries.py` with:

```python
from api_spend_dashboard.db import Database


class DashboardQueries:
    def __init__(self, db: Database):
        self.db = db

    def month_summary(self, year: int, month: int) -> dict[str, float | int]:
        start = f"{year:04d}-{month:02d}-01T00:00:00+00:00"
        end_month = month + 1
        end_year = year
        if end_month == 13:
            end_month = 1
            end_year += 1
        end = f"{end_year:04d}-{end_month:02d}-01T00:00:00+00:00"
        rows = self.db.query_all(
            """
            SELECT
                COALESCE(SUM(cost_amount), 0) AS total_cost,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(requests), 0) AS total_requests,
                COUNT(DISTINCT provider_id) AS provider_count
            FROM usage_snapshots
            WHERE period_start >= ? AND period_start < ?
            """,
            (start, end),
        )
        row = rows[0]
        return {
            "total_cost": float(row["total_cost"]),
            "total_tokens": int(row["total_tokens"]),
            "total_requests": int(row["total_requests"]),
            "provider_count": int(row["provider_count"]),
        }

    def daily_costs(self, days: int = 30) -> list[dict[str, str | float]]:
        return self.db.query_all(
            """
            SELECT substr(period_start, 1, 10) AS date,
                   provider_id,
                   COALESCE(SUM(cost_amount), 0) AS cost
            FROM usage_snapshots
            WHERE granularity = 'day'
            GROUP BY substr(period_start, 1, 10), provider_id
            ORDER BY date ASC
            LIMIT ?
            """,
            (days * 8,),
        )
```

- [ ] **Step 6: Run database tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_db.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit database layer**

Run:

```bash
git add src/api_spend_dashboard/models.py src/api_spend_dashboard/db.py src/api_spend_dashboard/services tests/test_db.py
git commit -m "feat: add sqlite snapshots and aggregation"
```

Expected: commit succeeds.

---

### Task 4: Provider Base And Manual Subscription Connector

**Files:**
- Create: `src/api_spend_dashboard/providers/__init__.py`
- Create: `src/api_spend_dashboard/providers/base.py`
- Create: `src/api_spend_dashboard/providers/manual.py`
- Create: `tests/test_providers_manual.py`

- [ ] **Step 1: Write failing manual connector tests**

Create `tests/test_providers_manual.py` with:

```python
from datetime import UTC, datetime

import pytest

from api_spend_dashboard.config import Settings
from api_spend_dashboard.providers.manual import ChatGPTProConnector


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        chatgpt_pro_price=200,
        chatgpt_pro_currency="USD",
        chatgpt_pro_renewal_date="2026-05-20",
    )
    connector = ChatGPTProConnector(settings)

    result = await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.provider_id == "chatgpt_pro"
    assert len(result.snapshots) == 1
    assert result.snapshots[0].cost_amount == 200
    assert result.snapshots[0].raw_summary["automatic_token_usage"] is False
```

- [ ] **Step 2: Run manual connector tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_manual.py -q
```

Expected: FAIL because provider modules do not exist.

- [ ] **Step 3: Implement provider base types**

Create `src/api_spend_dashboard/providers/__init__.py` with:

```python
"""Provider connectors."""
```

Create `src/api_spend_dashboard/providers/base.py` with:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from api_spend_dashboard.models import UsageSnapshot


class ProviderSyncError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


@dataclass(frozen=True)
class SyncResult:
    provider_id: str
    snapshots: list[UsageSnapshot]
    status_message: str


class ProviderConnector(Protocol):
    provider_id: str
    display_name: str

    async def sync(self, now: datetime) -> SyncResult:
        ...
```

- [ ] **Step 4: Implement ChatGPT Pro connector**

Create `src/api_spend_dashboard/providers/manual.py` with:

```python
from datetime import UTC, datetime

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import SyncResult


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, end


class ChatGPTProConnector:
    provider_id = "chatgpt_pro"
    display_name = "ChatGPT Pro"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        start, end = _month_bounds(now)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=self.settings.chatgpt_pro_currency,
            cost_amount=self.settings.chatgpt_pro_price,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={
                "plan_name": self.settings.chatgpt_pro_plan_name,
                "billing_period": self.settings.chatgpt_pro_billing_period,
                "renewal_date": self.settings.chatgpt_pro_renewal_date,
                "notes": self.settings.chatgpt_pro_notes,
                "automatic_token_usage": False,
            },
        )
        return SyncResult(
            provider_id=self.provider_id,
            snapshots=[snapshot],
            status_message="Manual subscription cost recorded; token usage is not available.",
        )
```

- [ ] **Step 5: Run manual connector tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_manual.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit provider base**

Run:

```bash
git add src/api_spend_dashboard/providers tests/test_providers_manual.py
git commit -m "feat: add provider base and chatgpt subscription connector"
```

Expected: commit succeeds.

---

### Task 5: HTTP Provider Connectors

**Files:**
- Create: `src/api_spend_dashboard/providers/openai.py`
- Create: `src/api_spend_dashboard/providers/minimax.py`
- Create: `src/api_spend_dashboard/providers/brave.py`
- Create: `src/api_spend_dashboard/providers/digitalocean.py`
- Create: `tests/test_providers_http.py`

- [ ] **Step 1: Write failing HTTP connector tests**

Create `tests/test_providers_http.py` with:

```python
from datetime import UTC, datetime

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.providers.brave import BraveConnector
from api_spend_dashboard.providers.digitalocean import DigitalOceanConnector
from api_spend_dashboard.providers.minimax import MiniMaxConnector
from api_spend_dashboard.providers.openai import OpenAIConnector


@pytest.mark.asyncio
@respx.mock
async def test_minimax_remains_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
        minimax_plan_name="Plus",
        minimax_plan_price=99,
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={
                "base_resp": {"status_code": 0},
                "data": {"text": {"limit": 4500, "remaining": 3000, "reset_seconds": 7200}},
            },
        )
    )

    result = await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].quota_limit == 4500
    assert result.snapshots[0].quota_remaining == 3000
    assert result.snapshots[0].cost_amount == 99


@pytest.mark.asyncio
@respx.mock
async def test_brave_quota_header_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=True, brave_api_key="brave")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "1, 15000",
                "X-RateLimit-Remaining": "1, 14900",
                "X-RateLimit-Reset": "1, 1000",
            },
            json={"web": {"results": []}},
        )
    )

    result = await BraveConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].quota_limit == 15000
    assert result.snapshots[0].quota_remaining == 14900
    assert result.snapshots[0].requests == 100


@pytest.mark.asyncio
@respx.mock
async def test_digitalocean_balance_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, digitalocean_enabled=True, digitalocean_token="do")
    respx.get("https://api.digitalocean.com/v2/customers/my/balance").mock(
        return_value=httpx.Response(
            200,
            json={"month_to_date_balance": "6.25", "account_balance": "0.00", "month_to_date_usage": "6.25"},
        )
    )

    result = await DigitalOceanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].cost_amount == 6.25


@pytest.mark.asyncio
@respx.mock
async def test_openai_cost_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key="sk-admin")
    respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "results": [{"amount": {"value": 3.5, "currency": "usd"}}],
                    }
                ]
            },
        )
    )
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "results": [{"input_tokens": 10, "output_tokens": 5, "num_model_requests": 2}],
                    }
                ]
            },
        )
    )

    result = await OpenAIConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].cost_amount == 3.5
    assert result.snapshots[0].total_tokens == 15
    assert result.snapshots[0].requests == 2
```

- [ ] **Step 2: Run HTTP connector tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_http.py -q
```

Expected: FAIL because connector modules do not exist.

- [ ] **Step 3: Implement MiniMax connector**

Create `src/api_spend_dashboard/providers/minimax.py` with:

```python
from datetime import UTC, datetime, timedelta

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class MiniMaxConnector:
    provider_id = "minimax"
    display_name = "MiniMax Token Plan"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        url = self.settings.minimax_base_url.rstrip("/") + "/v1/token_plan/remains"
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.minimax_api_key}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "MiniMax API key was rejected")
        if response.status_code >= 400:
            raise ProviderSyncError("provider_error", f"MiniMax returned HTTP {response.status_code}")
        payload = response.json()
        data = payload.get("data", payload)
        text = data.get("text", data.get("m2_7", data))
        limit = _first_int(text, ["limit", "total", "quota", "max"])
        remaining = _first_int(text, ["remaining", "remain", "available"])
        reset_seconds = _first_int(text, ["reset_seconds", "reset_in", "reset"])
        start, end = _month_bounds(now)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=self.settings.minimax_plan_currency,
            cost_amount=self.settings.minimax_plan_price,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=limit,
            quota_remaining=remaining,
            quota_reset_at=now + timedelta(seconds=reset_seconds) if reset_seconds else None,
            raw_summary={
                "plan_name": self.settings.minimax_plan_name,
                "plan_start_date": self.settings.minimax_plan_start_date,
                "plan_end_date": self.settings.minimax_plan_end_date,
                "quota_payload": data,
            },
        )
        return SyncResult(self.provider_id, [snapshot], "MiniMax Token Plan remains synced")


def _first_int(payload: object, keys: list[str]) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None
```

- [ ] **Step 4: Implement Brave connector**

Create `src/api_spend_dashboard/providers/brave.py` with the quota probe:

```python
from datetime import datetime, timedelta

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class BraveConnector:
    provider_id = "brave"
    display_name = "Brave Search API"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self.settings.brave_api_key},
                params={"q": self.settings.brave_probe_query, "count": 1},
            )
        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "Brave API key was rejected")
        if response.status_code == 429:
            raise ProviderSyncError("rate_limited", "Brave rate limit exceeded")
        if response.status_code >= 400:
            raise ProviderSyncError("provider_error", f"Brave returned HTTP {response.status_code}")

        limits = _csv_int_header(response.headers.get("X-RateLimit-Limit", ""))
        remaining_values = _csv_int_header(response.headers.get("X-RateLimit-Remaining", ""))
        reset_values = _csv_int_header(response.headers.get("X-RateLimit-Reset", ""))
        monthly_limit = limits[-1] if limits else None
        monthly_remaining = remaining_values[-1] if remaining_values else None
        used = monthly_limit - monthly_remaining if monthly_limit is not None and monthly_remaining is not None else None
        cost = None
        if used is not None:
            cost = used * self.settings.brave_price_per_1000_requests / 1000
        start, end = _month_bounds(now)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=self.settings.brave_currency,
            cost_amount=cost,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=used,
            quota_limit=monthly_limit,
            quota_remaining=monthly_remaining,
            quota_reset_at=now + timedelta(seconds=reset_values[-1]) if reset_values else None,
            raw_summary={
                "cost_is_estimate": True,
                "rate_limit_limit": response.headers.get("X-RateLimit-Limit"),
                "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining"),
                "rate_limit_reset": response.headers.get("X-RateLimit-Reset"),
            },
        )
        return SyncResult(self.provider_id, [snapshot], "Brave quota headers synced")


def _csv_int_header(value: str) -> list[int]:
    numbers: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            numbers.append(int(part))
    return numbers
```

- [ ] **Step 5: Implement DigitalOcean connector**

Create `src/api_spend_dashboard/providers/digitalocean.py` with:

```python
from datetime import datetime

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class DigitalOceanConnector:
    provider_id = "digitalocean"
    display_name = "DigitalOcean"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.get(
                "https://api.digitalocean.com/v2/customers/my/balance",
                headers={"Authorization": f"Bearer {self.settings.digitalocean_token}"},
            )
        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "DigitalOcean token was rejected")
        if response.status_code >= 400:
            raise ProviderSyncError("provider_error", f"DigitalOcean returned HTTP {response.status_code}")
        payload = response.json()
        start, end = _month_bounds(now)
        amount = float(payload.get("month_to_date_usage") or payload.get("month_to_date_balance") or 0)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency="USD",
            cost_amount=amount,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={
                "account_balance": payload.get("account_balance"),
                "month_to_date_balance": payload.get("month_to_date_balance"),
                "month_to_date_usage": payload.get("month_to_date_usage"),
            },
        )
        return SyncResult(self.provider_id, [snapshot], "DigitalOcean balance synced")
```

- [ ] **Step 6: Implement OpenAI connector**

Create `src/api_spend_dashboard/providers/openai.py` with:

```python
from datetime import UTC, datetime, timedelta

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult


class OpenAIConnector:
    provider_id = "openai"
    display_name = "OpenAI API"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        start = datetime(now.year, now.month, 1, tzinfo=UTC)
        start_time = int(start.timestamp())
        end_time = int(now.timestamp())
        headers = {"Authorization": f"Bearer {self.settings.openai_admin_api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            costs = await client.get(
                "https://api.openai.com/v1/organization/costs",
                headers=headers,
                params={"start_time": start_time, "end_time": end_time, "bucket_width": "1d"},
            )
            usage = await client.get(
                "https://api.openai.com/v1/organization/usage/completions",
                headers=headers,
                params={"start_time": start_time, "end_time": end_time, "bucket_width": "1d"},
            )
        for response in (costs, usage):
            if response.status_code in {401, 403}:
                raise ProviderSyncError("auth_error", "OpenAI admin API key was rejected")
            if response.status_code >= 400:
                raise ProviderSyncError("provider_error", f"OpenAI returned HTTP {response.status_code}")

        usage_by_start = _usage_by_start(usage.json())
        snapshots: list[UsageSnapshot] = []
        for bucket in costs.json().get("data", []):
            bucket_start = datetime.fromtimestamp(int(bucket["start_time"]), tz=UTC)
            bucket_end = datetime.fromtimestamp(int(bucket["end_time"]), tz=UTC)
            amount = 0.0
            currency = self.settings.default_currency
            for result in bucket.get("results", []):
                value = result.get("amount", {}).get("value", 0)
                amount += float(value or 0)
                currency = str(result.get("amount", {}).get("currency", currency)).upper()
            usage_bucket = usage_by_start.get(int(bucket["start_time"]), {})
            input_tokens = usage_bucket.get("input_tokens")
            output_tokens = usage_bucket.get("output_tokens")
            total_tokens = None
            if input_tokens is not None or output_tokens is not None:
                total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
            snapshots.append(
                UsageSnapshot(
                    provider_id=self.provider_id,
                    period_start=bucket_start,
                    period_end=bucket_end,
                    granularity="day",
                    currency=currency,
                    cost_amount=amount,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    requests=usage_bucket.get("num_model_requests"),
                    quota_limit=None,
                    quota_remaining=None,
                    quota_reset_at=None,
                    raw_summary={"cost_results": bucket.get("results", []), "usage": usage_bucket},
                )
            )
        if not snapshots:
            snapshots.append(
                UsageSnapshot(
                    provider_id=self.provider_id,
                    period_start=start,
                    period_end=now + timedelta(seconds=1),
                    granularity="month",
                    currency=self.settings.default_currency,
                    cost_amount=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    requests=0,
                    quota_limit=None,
                    quota_remaining=None,
                    quota_reset_at=None,
                    raw_summary={"empty": True},
                )
            )
        return SyncResult(self.provider_id, snapshots, "OpenAI usage and costs synced")


def _usage_by_start(payload: dict) -> dict[int, dict[str, int]]:
    by_start: dict[int, dict[str, int]] = {}
    for bucket in payload.get("data", []):
        aggregate = {"input_tokens": 0, "output_tokens": 0, "num_model_requests": 0}
        for result in bucket.get("results", []):
            aggregate["input_tokens"] += int(result.get("input_tokens") or 0)
            aggregate["output_tokens"] += int(result.get("output_tokens") or 0)
            aggregate["num_model_requests"] += int(result.get("num_model_requests") or 0)
        by_start[int(bucket["start_time"])] = aggregate
    return by_start
```

- [ ] **Step 7: Run HTTP connector tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_http.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit HTTP connectors**

Run:

```bash
git add src/api_spend_dashboard/providers tests/test_providers_http.py
git commit -m "feat: add openai minimax brave and digitalocean connectors"
```

Expected: commit succeeds.

---

### Task 6: Gemini And Baidu Qianfan Connectors

**Files:**
- Create: `src/api_spend_dashboard/providers/gemini.py`
- Create: `src/api_spend_dashboard/providers/qianfan.py`
- Create: `tests/test_providers_cloud.py`

- [ ] **Step 1: Write failing cloud connector tests**

Create `tests/test_providers_cloud.py` with:

```python
from datetime import UTC, datetime

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.providers.gemini import rows_to_snapshots
from api_spend_dashboard.providers.qianfan import QianfanConnector


def test_gemini_rows_to_snapshots(temp_db_url):
    settings = Settings(database_url=temp_db_url, default_currency="USD")
    rows = [
        {
            "usage_start_time": datetime(2026, 5, 1, tzinfo=UTC),
            "usage_end_time": datetime(2026, 5, 2, tzinfo=UTC),
            "cost": 4.2,
            "currency": "USD",
            "service_description": "Gemini API",
        }
    ]

    snapshots = rows_to_snapshots(settings, rows)

    assert snapshots[0].provider_id == "gemini"
    assert snapshots[0].cost_amount == 4.2
    assert snapshots[0].currency == "USD"


@pytest.mark.asyncio
@respx.mock
async def test_qianfan_metric_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        qianfan_enabled=True,
        baidu_access_key_id="ak",
        baidu_secret_access_key="sk",
    )
    respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "startTime": "2026-05-01T00:00:00Z",
                    "endTime": "2026-05-02T00:00:00Z",
                    "serviceList": [
                        {
                            "serviceId": "svc",
                            "appList": [
                                {
                                    "appId": "app",
                                    "metric": {
                                        "inputTokensTotal": 100,
                                        "outputTokensTotal": 50,
                                        "requestTotal": 3,
                                    },
                                }
                            ],
                        }
                    ],
                }
            },
        )
    )

    result = await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].input_tokens == 100
    assert result.snapshots[0].output_tokens == 50
    assert result.snapshots[0].total_tokens == 150
    assert result.snapshots[0].requests == 3
```

- [ ] **Step 2: Run cloud connector tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_cloud.py -q
```

Expected: FAIL because cloud connector modules do not exist.

- [ ] **Step 3: Implement Gemini row parser and connector**

Create `src/api_spend_dashboard/providers/gemini.py` with:

```python
from datetime import UTC, datetime
from typing import Any

from google.cloud import bigquery

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult


class GeminiConnector:
    provider_id = "gemini"
    display_name = "Gemini API"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        table = (
            f"`{self.settings.gcp_billing_project_id}."
            f"{self.settings.gcp_billing_dataset}.{self.settings.gcp_billing_table}`"
        )
        query = f"""
            SELECT usage_start_time, usage_end_time, cost, currency, service.description AS service_description
            FROM {table}
            WHERE usage_start_time >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)
              AND service.description LIKE @service_filter
            ORDER BY usage_start_time ASC
        """
        try:
            client = bigquery.Client(project=self.settings.gcp_billing_project_id)
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        "service_filter", "STRING", f"%{self.settings.gemini_service_filter}%"
                    )
                ]
            )
            rows = list(client.query(query, job_config=job_config).result())
        except Exception as exc:
            raise ProviderSyncError("provider_error", f"Gemini BigQuery query failed: {exc}") from exc
        snapshots = rows_to_snapshots(self.settings, [dict(row.items()) for row in rows])
        return SyncResult(self.provider_id, snapshots, "Gemini billing export synced")


def rows_to_snapshots(settings: Settings, rows: list[dict[str, Any]]) -> list[UsageSnapshot]:
    snapshots: list[UsageSnapshot] = []
    for row in rows:
        start = _as_datetime(row["usage_start_time"])
        end = _as_datetime(row["usage_end_time"])
        snapshots.append(
            UsageSnapshot(
                provider_id="gemini",
                period_start=start,
                period_end=end,
                granularity="day",
                currency=str(row.get("currency") or settings.default_currency).upper(),
                cost_amount=float(row.get("cost") or 0),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                requests=None,
                quota_limit=None,
                quota_remaining=None,
                quota_reset_at=None,
                raw_summary={"service_description": row.get("service_description")},
            )
        )
    return snapshots


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
```

- [ ] **Step 4: Implement Qianfan connector with BCE signing**

Create `src/api_spend_dashboard/providers/qianfan.py` with:

```python
import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class QianfanConnector:
    provider_id = "qianfan"
    display_name = "Baidu Qianfan"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        start, end = _month_bounds(now)
        body = {
            "serviceId": self.settings.csv_values(self.settings.qianfan_service_ids),
            "appId": self.settings.csv_values(self.settings.qianfan_app_ids),
            "startTime": start.isoformat().replace("+00:00", "Z"),
            "endTime": end.isoformat().replace("+00:00", "Z"),
        }
        body = {key: value for key, value in body.items() if value not in ([], "")}
        endpoint = self.settings.qianfan_endpoint.rstrip("/")
        url = f"{endpoint}/v2/service"
        params = {"Action": "DescribeServiceMetric"}
        headers = _signed_headers(
            access_key=self.settings.baidu_access_key_id,
            secret_key=self.settings.baidu_secret_access_key,
            method="POST",
            host=endpoint.removeprefix("https://").removeprefix("http://"),
            path="/v2/service",
            params=params,
            body=json.dumps(body, separators=(",", ":")),
        )
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.post(url, params=params, headers=headers, json=body)
        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "Baidu AK/SK was rejected")
        if response.status_code >= 400:
            raise ProviderSyncError("provider_error", f"Qianfan returned HTTP {response.status_code}")
        payload = response.json()
        metric = _aggregate_metrics(payload)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=self.settings.default_currency,
            cost_amount=None,
            input_tokens=metric["input_tokens"],
            output_tokens=metric["output_tokens"],
            total_tokens=metric["input_tokens"] + metric["output_tokens"],
            requests=metric["requests"],
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={"metric": metric, "cost_available": False},
        )
        return SyncResult(self.provider_id, [snapshot], "Qianfan service metrics synced")


def _aggregate_metrics(payload: dict) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
    for service in payload.get("result", {}).get("serviceList", []):
        for app in service.get("appList", []):
            metric = app.get("metric", {})
            totals["input_tokens"] += int(metric.get("inputTokensTotal") or 0)
            totals["output_tokens"] += int(metric.get("outputTokensTotal") or 0)
            totals["requests"] += int(metric.get("requestTotal") or 0)
    return totals


def _signed_headers(
    *,
    access_key: str,
    secret_key: str,
    method: str,
    host: str,
    path: str,
    params: dict[str, str],
    body: str,
) -> dict[str, str]:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signed_headers = "host;x-bce-date"
    auth_prefix = f"bce-auth-v1/{access_key}/{timestamp}/1800"
    signing_key = hmac.new(secret_key.encode(), auth_prefix.encode(), hashlib.sha256).hexdigest()
    canonical_uri = quote(path)
    canonical_query = "&".join(f"{quote(k)}={quote(v)}" for k, v in sorted(params.items()))
    canonical_headers = f"host:{host}\nx-bce-date:{timestamp}"
    canonical_request = "\n".join(
        [method.upper(), canonical_uri, canonical_query, canonical_headers, signed_headers, hashlib.sha256(body.encode()).hexdigest()]
    )
    signature = hmac.new(signing_key.encode(), canonical_request.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"{auth_prefix}/{signed_headers}/{signature}",
        "x-bce-date": timestamp,
        "Content-Type": "application/json",
    }
```

- [ ] **Step 5: Run cloud connector tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_providers_cloud.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit cloud connectors**

Run:

```bash
git add src/api_spend_dashboard/providers/gemini.py src/api_spend_dashboard/providers/qianfan.py tests/test_providers_cloud.py
git commit -m "feat: add gemini and qianfan connectors"
```

Expected: commit succeeds.

---

### Task 7: Sync Orchestration And API Routes

**Files:**
- Create: `src/api_spend_dashboard/services/sync.py`
- Create: `src/api_spend_dashboard/main.py`
- Create: `tests/test_sync.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing sync tests**

Create `tests/test_sync.py` with:

```python
from datetime import UTC, datetime

import pytest

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.services.sync import SyncService


class GoodConnector:
    provider_id = "good"
    display_name = "Good"

    async def sync(self, now):
        return SyncResult(
            provider_id="good",
            snapshots=[
                UsageSnapshot(
                    provider_id="good",
                    period_start=datetime(2026, 5, 1, tzinfo=UTC),
                    period_end=datetime(2026, 5, 2, tzinfo=UTC),
                    granularity="day",
                    currency="USD",
                    cost_amount=1,
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    requests=None,
                    quota_limit=None,
                    quota_remaining=None,
                    quota_reset_at=None,
                    raw_summary={},
                )
            ],
            status_message="ok",
        )


class BadConnector:
    provider_id = "bad"
    display_name = "Bad"

    async def sync(self, now):
        raise ProviderSyncError("auth_error", "bad key")


@pytest.mark.asyncio
async def test_sync_isolates_provider_failures(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    settings = Settings(database_url=temp_db_url)
    service = SyncService(settings, db, connectors=[GoodConnector(), BadConnector()])

    result = await service.sync_all(datetime(2026, 5, 2, tzinfo=UTC))

    assert result["good"]["status"] == "success"
    assert result["bad"]["status"] == "failed"
    assert db.recent_sync_runs("bad", 1)[0]["error_type"] == "auth_error"
```

- [ ] **Step 2: Write failing API tests**

Create `tests/test_api.py` with:

```python
from fastapi.testclient import TestClient

from api_spend_dashboard.config import Settings
from api_spend_dashboard.main import create_app


def test_config_status_endpoint(temp_db_url):
    app = create_app(Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key=""))
    client = TestClient(app)

    response = client.get("/api/config/status")

    assert response.status_code == 200
    assert response.json()["openai"]["status"] == "missing_config"


def test_dashboard_route_loads(temp_db_url):
    app = create_app(Settings(database_url=temp_db_url))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "API Spend Dashboard" in response.text
```

- [ ] **Step 3: Run sync and API tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_sync.py tests/test_api.py -q
```

Expected: FAIL because `SyncService` and `create_app` do not exist.

- [ ] **Step 4: Implement sync service**

Create `src/api_spend_dashboard/services/sync.py` with:

```python
import asyncio
from datetime import UTC, datetime
from typing import Any

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderConnector, ProviderSyncError
from api_spend_dashboard.providers.brave import BraveConnector
from api_spend_dashboard.providers.digitalocean import DigitalOceanConnector
from api_spend_dashboard.providers.gemini import GeminiConnector
from api_spend_dashboard.providers.manual import ChatGPTProConnector
from api_spend_dashboard.providers.minimax import MiniMaxConnector
from api_spend_dashboard.providers.openai import OpenAIConnector
from api_spend_dashboard.providers.qianfan import QianfanConnector


class SyncService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        connectors: list[ProviderConnector] | None = None,
    ):
        self.settings = settings
        self.db = db
        self.connectors = connectors if connectors is not None else build_connectors(settings)
        self._lock = asyncio.Lock()

    async def sync_all(self, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        if self._lock.locked():
            return {"sync": {"status": "already_running"}}
        async with self._lock:
            sync_time = now or datetime.now(UTC)
            results: dict[str, dict[str, Any]] = {}
            for connector in self.connectors:
                run_id = self.db.start_sync_run(connector.provider_id)
                try:
                    result = await connector.sync(sync_time)
                    for snapshot in result.snapshots:
                        self.db.upsert_snapshot(snapshot)
                    self.db.finish_sync_run(
                        run_id,
                        status="success",
                        snapshots_written=len(result.snapshots),
                    )
                    results[connector.provider_id] = {
                        "status": "success",
                        "snapshots_written": len(result.snapshots),
                        "message": result.status_message,
                    }
                except ProviderSyncError as exc:
                    self.db.finish_sync_run(
                        run_id,
                        status="failed",
                        error_type=exc.error_type,
                        error_message=exc.message,
                    )
                    results[connector.provider_id] = {
                        "status": "failed",
                        "error_type": exc.error_type,
                        "message": exc.message,
                    }
                except Exception as exc:
                    self.db.finish_sync_run(
                        run_id,
                        status="failed",
                        error_type="unknown_error",
                        error_message=str(exc),
                    )
                    results[connector.provider_id] = {
                        "status": "failed",
                        "error_type": "unknown_error",
                        "message": str(exc),
                    }
            return results


def build_connectors(settings: Settings) -> list[ProviderConnector]:
    statuses = settings.provider_config_status()
    connectors: list[ProviderConnector] = []
    if statuses["openai"]["status"] == "configured":
        connectors.append(OpenAIConnector(settings))
    if statuses["chatgpt_pro"]["status"] == "configured":
        connectors.append(ChatGPTProConnector(settings))
    if statuses["minimax"]["status"] == "configured":
        connectors.append(MiniMaxConnector(settings))
    if statuses["gemini"]["status"] == "configured":
        connectors.append(GeminiConnector(settings))
    if statuses["qianfan"]["status"] == "configured":
        connectors.append(QianfanConnector(settings))
    if statuses["brave"]["status"] == "configured":
        connectors.append(BraveConnector(settings))
    if statuses["digitalocean"]["status"] == "configured":
        connectors.append(DigitalOceanConnector(settings))
    return connectors
```

- [ ] **Step 5: Implement FastAPI app**

Create `src/api_spend_dashboard/main.py` with:

```python
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from api_spend_dashboard.config import Settings, get_settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.services.queries import DashboardQueries
from api_spend_dashboard.services.sync import SyncService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    db = Database(resolved_settings.database_url)
    db.migrate()
    sync_service = SyncService(resolved_settings, db)
    queries = DashboardQueries(db)

    app = FastAPI(title="API Spend Dashboard")
    app.state.settings = resolved_settings
    app.state.db = db
    app.state.sync_service = sync_service
    templates = Jinja2Templates(directory="src/api_spend_dashboard/templates")
    app.mount("/static", StaticFiles(directory="src/api_spend_dashboard/static"), name="static")

    @app.on_event("startup")
    async def start_scheduler() -> None:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            sync_service.sync_all,
            "interval",
            hours=resolved_settings.sync_interval_hours,
            next_run_time=None,
        )
        scheduler.start()
        app.state.scheduler = scheduler

    @app.on_event("shutdown")
    async def stop_scheduler() -> None:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            scheduler.shutdown(wait=False)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/config/status")
    async def config_status():
        return resolved_settings.provider_config_status()

    @app.get("/api/summary")
    async def summary():
        now = datetime.now(UTC)
        month = queries.month_summary(now.year, now.month)
        return {"month": month, "daily_costs": queries.daily_costs()}

    @app.post("/api/sync")
    async def sync_now():
        return await sync_service.sync_all()

    return app


app = create_app()
```

- [ ] **Step 6: Create temporary dashboard template for API smoke test**

Create `src/api_spend_dashboard/templates/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>API Spend Dashboard</title>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body>
    <main id="app">
      <h1>API Spend Dashboard</h1>
      <p>Loading local usage data...</p>
    </main>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="/static/app.js"></script>
  </body>
</html>
```

Create `src/api_spend_dashboard/static/app.css` with:

```css
body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: #f7f8fa;
  color: #16181d;
}

main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px;
}
```

Create `src/api_spend_dashboard/static/app.js` with:

```javascript
console.log("API Spend Dashboard loaded");
```

- [ ] **Step 7: Run sync and API tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_sync.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit sync and API routes**

Run:

```bash
git add src/api_spend_dashboard/services/sync.py src/api_spend_dashboard/main.py src/api_spend_dashboard/templates src/api_spend_dashboard/static tests/test_sync.py tests/test_api.py
git commit -m "feat: add sync service and local api"
```

Expected: commit succeeds.

---

### Task 8: Dashboard Frontend

**Files:**
- Modify: `src/api_spend_dashboard/templates/index.html`
- Modify: `src/api_spend_dashboard/static/app.css`
- Modify: `src/api_spend_dashboard/static/app.js`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Extend API smoke test for dashboard containers**

Append to `tests/test_api.py`:

```python
def test_dashboard_contains_core_regions(temp_db_url):
    app = create_app(Settings(database_url=temp_db_url))
    client = TestClient(app)

    response = client.get("/")

    assert 'id="summary-cards"' in response.text
    assert 'id="trend-chart"' in response.text
    assert 'id="provider-grid"' in response.text
```

- [ ] **Step 2: Run API test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py -q
```

Expected: FAIL because dashboard containers are not present.

- [ ] **Step 3: Implement dashboard HTML**

Replace `src/api_spend_dashboard/templates/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>API Spend Dashboard</title>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body>
    <header class="topbar">
      <div>
        <h1>API Spend Dashboard</h1>
        <p id="sync-status">Local usage monitor</p>
      </div>
      <button id="sync-now" type="button">Sync now</button>
    </header>

    <main>
      <section id="summary-cards" class="summary-grid" aria-label="Monthly summary"></section>

      <section class="charts-grid" aria-label="Charts">
        <div class="panel">
          <h2>30 day spend</h2>
          <canvas id="trend-chart" height="110"></canvas>
        </div>
        <div class="panel">
          <h2>Provider share</h2>
          <canvas id="share-chart" height="110"></canvas>
        </div>
      </section>

      <section>
        <div class="section-heading">
          <h2>Providers</h2>
          <span id="config-hint"></span>
        </div>
        <div id="provider-grid" class="provider-grid"></div>
      </section>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="/static/app.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Implement dashboard CSS**

Replace `src/api_spend_dashboard/static/app.css` with:

```css
:root {
  color-scheme: light;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --text: #171923;
  --muted: #5c6470;
  --line: #d9dee7;
  --accent: #0f766e;
  --danger: #b42318;
  --warning: #9a6700;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 22px;
}

h2 {
  font-size: 16px;
}

button {
  min-height: 40px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: white;
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}

main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric,
.panel,
.provider-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
}

.metric span,
.provider-card span,
#sync-status,
#config-hint {
  color: var(--muted);
  font-size: 13px;
}

.metric strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 22px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.provider-card {
  min-height: 128px;
}

.provider-card h3 {
  margin: 0 0 12px;
  font-size: 15px;
}

.status {
  display: inline-block;
  margin-top: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--line);
}

.status.configured,
.status.success {
  color: var(--accent);
}

.status.missing_config,
.status.failed {
  color: var(--danger);
}

.status.disabled {
  color: var(--warning);
}

@media (max-width: 820px) {
  .summary-grid,
  .charts-grid,
  .provider-grid {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
```

- [ ] **Step 5: Implement dashboard JavaScript**

Replace `src/api_spend_dashboard/static/app.js` with:

```javascript
const summaryCards = document.getElementById("summary-cards");
const providerGrid = document.getElementById("provider-grid");
const syncStatus = document.getElementById("sync-status");
const syncButton = document.getElementById("sync-now");
const configHint = document.getElementById("config-hint");

let trendChart;
let shareChart;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return response.json();
}

function money(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function renderSummary(summary) {
  const month = summary.month;
  const metrics = [
    ["Month spend", money(month.total_cost)],
    ["Today added", "See trend"],
    ["Tokens", Number(month.total_tokens || 0).toLocaleString()],
    ["Requests", Number(month.total_requests || 0).toLocaleString()],
  ];
  summaryCards.innerHTML = metrics
    .map(([label, value]) => `<article class="metric"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
}

function renderProviders(config) {
  const providers = [
    ["openai", "OpenAI API"],
    ["chatgpt_pro", "ChatGPT Pro"],
    ["minimax", "MiniMax"],
    ["gemini", "Gemini"],
    ["qianfan", "Baidu Qianfan"],
    ["brave", "Brave Search"],
    ["digitalocean", "DigitalOcean"],
  ];
  const missingCount = Object.values(config).filter((item) => item.status === "missing_config").length;
  configHint.textContent = missingCount ? `${missingCount} provider(s) need configuration` : "Configuration loaded";
  providerGrid.innerHTML = providers
    .map(([id, name]) => {
      const item = config[id] || { status: "disabled", missing: [] };
      const missing = item.missing && item.missing.length ? `<span>Missing: ${item.missing.join(", ")}</span>` : "<span>Ready or disabled</span>";
      return `<article class="provider-card">
        <h3>${name}</h3>
        ${missing}
        <div class="status ${item.status}">${item.status}</div>
      </article>`;
    })
    .join("");
}

function renderCharts(summary) {
  const rows = summary.daily_costs || [];
  const labels = [...new Set(rows.map((row) => row.date))];
  const totals = labels.map((date) =>
    rows.filter((row) => row.date === date).reduce((sum, row) => sum + Number(row.cost || 0), 0)
  );
  const providerTotals = {};
  for (const row of rows) {
    providerTotals[row.provider_id] = (providerTotals[row.provider_id] || 0) + Number(row.cost || 0);
  }
  if (trendChart) trendChart.destroy();
  if (shareChart) shareChart.destroy();
  trendChart = new Chart(document.getElementById("trend-chart"), {
    type: "line",
    data: { labels, datasets: [{ label: "Spend", data: totals, borderColor: "#0f766e", tension: 0.25 }] },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });
  shareChart = new Chart(document.getElementById("share-chart"), {
    type: "doughnut",
    data: {
      labels: Object.keys(providerTotals),
      datasets: [{ data: Object.values(providerTotals), backgroundColor: ["#0f766e", "#2563eb", "#7c3aed", "#ca8a04", "#dc2626", "#4b5563"] }],
    },
    options: { responsive: true },
  });
}

async function loadDashboard() {
  syncStatus.textContent = "Loading local usage data...";
  const [summary, config] = await Promise.all([fetchJson("/api/summary"), fetchJson("/api/config/status")]);
  renderSummary(summary);
  renderProviders(config);
  renderCharts(summary);
  syncStatus.textContent = "Loaded";
}

syncButton.addEventListener("click", async () => {
  syncButton.disabled = true;
  syncStatus.textContent = "Sync running...";
  try {
    await fetchJson("/api/sync", { method: "POST" });
    await loadDashboard();
  } catch (error) {
    syncStatus.textContent = error.message;
  } finally {
    syncButton.disabled = false;
  }
});

loadDashboard().catch((error) => {
  syncStatus.textContent = error.message;
});
```

- [ ] **Step 6: Run API tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit dashboard frontend**

Run:

```bash
git add src/api_spend_dashboard/templates/index.html src/api_spend_dashboard/static tests/test_api.py
git commit -m "feat: add overview dashboard frontend"
```

Expected: commit succeeds.

---

### Task 9: Documentation And End-To-End Verification

**Files:**
- Create: `README.md`
- Modify: `src/api_spend_dashboard/main.py` if server startup import issues appear during verification.

- [ ] **Step 1: Write README**

Create `README.md` with:

```markdown
# API Spend Dashboard

Local browser dashboard for tracking personal API and infrastructure usage costs.

## Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m uvicorn api_spend_dashboard.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

## Configuration

All secrets live in `.env`. The frontend never receives provider credentials.

### OpenAI API

Set `OPENAI_ENABLED=true` and `OPENAI_ADMIN_API_KEY`. Use an OpenAI Platform key with permission to read organization usage and costs.

### ChatGPT Pro

Set `CHATGPT_PRO_ENABLED=true` and fill plan price, currency, renewal date, and notes. ChatGPT Pro token usage is not automatically available through an official API.

### MiniMax

Set `MINIMAX_ENABLED=true`, `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, and manual plan metadata.

### Gemini

Set up Google Cloud Billing Export to BigQuery. Then set `GEMINI_ENABLED=true`, `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_BILLING_PROJECT_ID`, `GCP_BILLING_DATASET`, and `GCP_BILLING_TABLE`.

### Baidu Qianfan

Set `QIANFAN_ENABLED=true`, `BAIDU_ACCESS_KEY_ID`, and `BAIDU_SECRET_ACCESS_KEY`. The key needs Qianfan read permissions.

### Brave Search

Set `BRAVE_ENABLED=true` and `BRAVE_API_KEY`. Cost is estimated from quota headers and configured request price.

### DigitalOcean

Set `DIGITALOCEAN_ENABLED=true` and `DIGITALOCEAN_TOKEN`.

## Data

SQLite data is stored under `data/` by default and is ignored by git.
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

Run:

```bash
.venv/bin/python -m ruff check .
```

Expected: no lint errors.

- [ ] **Step 4: Start local server**

Run:

```bash
.venv/bin/python -m uvicorn api_spend_dashboard.main:app --host 127.0.0.1 --port 8000
```

Expected: Uvicorn starts and logs that it is running on `http://127.0.0.1:8000`.

- [ ] **Step 5: Verify dashboard route**

In another terminal, run:

```bash
curl -s http://127.0.0.1:8000/ | rg "API Spend Dashboard"
```

Expected: output includes `API Spend Dashboard`.

- [ ] **Step 6: Verify config status route**

Run:

```bash
curl -s http://127.0.0.1:8000/api/config/status | rg "openai|chatgpt_pro|minimax|gemini|qianfan|brave|digitalocean"
```

Expected: output includes provider keys.

- [ ] **Step 7: Stop local server**

Press `Ctrl+C` in the Uvicorn terminal.

Expected: server shuts down cleanly.

- [ ] **Step 8: Commit docs and verification fixes**

Run:

```bash
git add README.md src/api_spend_dashboard/main.py
git commit -m "docs: add local setup guide"
```

Expected: commit succeeds. If `main.py` was unchanged, run:

```bash
git add README.md
git commit -m "docs: add local setup guide"
```

Expected: commit succeeds.

---

## Self-Review Notes

- Spec coverage: all confirmed v1 requirements are mapped to tasks: local FastAPI service, `.env`, SQLite history, internal scheduler, overview dashboard, provider connectors, missing-config status, tests, and setup instructions.
- Provider limitations are explicit: ChatGPT Pro is manual, Brave cost is estimated, Gemini requires BigQuery Billing Export, and Qianfan cost may be token-only if billing data is unavailable.
- No real provider credentials are required for tests.
- The plan starts by initializing git because the current directory is not a repository and checkpoint commits are part of the implementation workflow.
