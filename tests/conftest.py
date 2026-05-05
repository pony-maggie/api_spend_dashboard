from pathlib import Path

import pytest


PROVIDER_ENV_VARS = (
    "CODEX_HOME",
    "OPENAI_ENABLED",
    "OPENAI_ADMIN_API_KEY",
    "OPENAI_ORG_ID",
    "CHATGPT_PRO_ENABLED",
    "CHATGPT_PRO_PLAN_NAME",
    "CHATGPT_PRO_PRICE",
    "CHATGPT_PRO_CURRENCY",
    "CHATGPT_PRO_BILLING_PERIOD",
    "CHATGPT_PRO_RENEWAL_DATE",
    "CHATGPT_PRO_NOTES",
    "MINIMAX_ENABLED",
    "MINIMAX_API_KEY",
    "MINIMAX_BASE_URL",
    "MINIMAX_PLAN_NAME",
    "MINIMAX_PLAN_PRICE",
    "MINIMAX_PLAN_CURRENCY",
    "MINIMAX_PLAN_START_DATE",
    "MINIMAX_PLAN_END_DATE",
    "GEMINI_ENABLED",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GCP_BILLING_PROJECT_ID",
    "GCP_BILLING_DATASET",
    "GCP_BILLING_TABLE",
    "GEMINI_SERVICE_FILTER",
    "QIANFAN_ENABLED",
    "BAIDU_ACCESS_KEY_ID",
    "BAIDU_SECRET_ACCESS_KEY",
    "QIANFAN_ENDPOINT",
    "QIANFAN_SERVICE_IDS",
    "QIANFAN_APP_IDS",
    "BRAVE_ENABLED",
    "BRAVE_API_KEY",
    "BRAVE_PROBE_QUERY",
    "BRAVE_PRICE_PER_1000_REQUESTS",
    "BRAVE_CURRENCY",
    "DIGITALOCEAN_ENABLED",
    "DIGITALOCEAN_TOKEN",
    "RECURRING_EXPENSES_ENABLED",
    "RECURRING_EXPENSES",
    "DISPLAY_CURRENCY",
    "EXCHANGE_RATES_TO_DISPLAY",
    "EXCHANGE_RATE_SOURCE",
)


@pytest.fixture(autouse=True)
def isolate_settings_from_local_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in PROVIDER_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def temp_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.sqlite3'}"
