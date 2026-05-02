from datetime import UTC, datetime

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    utc_now = now.astimezone(UTC)
    start = datetime(utc_now.year, utc_now.month, 1, tzinfo=UTC)
    if utc_now.month == 12:
        end = datetime(utc_now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(utc_now.year, utc_now.month + 1, 1, tzinfo=UTC)
    return start, end


class ChatGPTProConnector:
    provider_id = "chatgpt_pro"
    display_name = "ChatGPT Pro"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        if self.settings.chatgpt_pro_price <= 0:
            raise ProviderSyncError("missing_config", "CHATGPT_PRO_PRICE must be positive")

        currency = self.settings.chatgpt_pro_currency.strip().upper()
        if not currency:
            raise ProviderSyncError("missing_config", "CHATGPT_PRO_CURRENCY must be non-empty")

        start, end = _month_bounds(now)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=currency,
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
