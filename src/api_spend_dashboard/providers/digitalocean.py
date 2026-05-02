from datetime import datetime
from typing import Any

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
            raise ProviderSyncError(
                "provider_error", f"DigitalOcean returned HTTP {response.status_code}"
            )

        payload = _json_dict(response)
        start, end = _month_bounds(now)
        amount = _non_negative_float(
            payload.get("month_to_date_usage") or payload.get("month_to_date_balance") or 0
        )
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


def _non_negative_float(value: Any) -> float:
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", "DigitalOcean balance amount was not numeric") from exc


def _json_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderSyncError("parse_error", "DigitalOcean response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderSyncError("parse_error", "DigitalOcean response must be a JSON object")
    return payload
