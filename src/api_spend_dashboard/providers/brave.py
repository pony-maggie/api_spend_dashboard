from datetime import UTC, datetime, timedelta

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
        used = _used_requests(monthly_limit, monthly_remaining)
        price_per_1000 = max(float(self.settings.brave_price_per_1000_requests), 0)
        cost = used * price_per_1000 / 1000 if used is not None else None
        reset_at = None
        if reset_values:
            reset_at = now.astimezone(UTC) + timedelta(seconds=max(reset_values[-1], 0))

        start, end = _month_bounds(now)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=_currency(self.settings.brave_currency, "BRAVE_CURRENCY"),
            cost_amount=cost,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=used,
            quota_limit=monthly_limit,
            quota_remaining=monthly_remaining,
            quota_reset_at=reset_at,
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
        if not part:
            continue
        numbers.append(max(int(part), 0))
    return numbers


def _used_requests(limit: int | None, remaining: int | None) -> int | None:
    if limit is None or remaining is None:
        return None
    return max(limit - remaining, 0)


def _currency(value: str, setting_name: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", f"{setting_name} must be non-empty")
    return currency
