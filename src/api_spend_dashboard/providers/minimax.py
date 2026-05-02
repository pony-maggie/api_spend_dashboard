from datetime import UTC, datetime, timedelta
from typing import Any

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
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "MiniMax API key was rejected")
        if response.status_code >= 400:
            raise ProviderSyncError(
                "provider_error", f"MiniMax returned HTTP {response.status_code}"
            )

        payload = response.json()
        quota_payload = _quota_payload(payload)
        limit = _first_non_negative_int(
            quota_payload, ["limit", "total", "quota", "max", "quota_limit", "total_quota"]
        )
        remaining = _first_non_negative_int(
            quota_payload, ["remaining", "remain", "available", "quota_remaining", "balance"]
        )
        reset_at = _reset_at(quota_payload, now)
        currency = _currency(self.settings.minimax_plan_currency, "MINIMAX_PLAN_CURRENCY")
        cost = _non_negative_float(
            self.settings.minimax_plan_price, "MINIMAX_PLAN_PRICE must be non-negative"
        )
        start, end = _month_bounds(now)

        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=currency,
            cost_amount=cost,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=limit,
            quota_remaining=remaining,
            quota_reset_at=reset_at,
            raw_summary={
                "plan_name": self.settings.minimax_plan_name,
                "plan_start_date": self.settings.minimax_plan_start_date,
                "plan_end_date": self.settings.minimax_plan_end_date,
                "quota_payload": quota_payload,
            },
        )
        return SyncResult(
            provider_id=self.provider_id,
            snapshots=[snapshot],
            status_message="MiniMax Token Plan remains synced",
        )


def _quota_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return data
    for key in ("text", "m2_7", "token", "tokens", "quota", "plan"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def _first_non_negative_int(payload: Any, keys: list[str]) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        return max(parsed, 0)
    return None


def _reset_at(payload: Any, now: datetime) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    seconds = _first_non_negative_int(payload, ["reset_seconds", "reset_in", "reset_after_seconds"])
    if seconds is not None:
        return now.astimezone(UTC) + timedelta(seconds=seconds)
    timestamp = _first_non_negative_int(payload, ["reset_at", "reset_time", "reset_timestamp", "reset"])
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _currency(value: str, setting_name: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", f"{setting_name} must be non-empty")
    return currency


def _non_negative_float(value: float, message: str) -> float:
    amount = float(value)
    if amount < 0:
        raise ProviderSyncError("missing_config", message)
    return amount
