from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 18765
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
            "chatgpt_pro": (
                self.chatgpt_pro_enabled,
                {"CHATGPT_PRO_PRICE": self.chatgpt_pro_price if self.chatgpt_pro_price > 0 else ""},
            ),
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
    return Settings(_env_file=".env")
