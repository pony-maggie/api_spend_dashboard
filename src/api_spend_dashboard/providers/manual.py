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
