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

        payload = _json_dict(response)
        _raise_for_base_resp(payload)
        quota_payload = _quota_payload(payload)
        if not isinstance(quota_payload, dict):
            raise ProviderSyncError("parse_error", "MiniMax quota payload must be a JSON object")
        limit = _first_non_negative_int(
            quota_payload, ["limit", "total", "quota", "max", "quota_limit", "total_quota"]
        )
        remaining = _first_non_negative_int(
            quota_payload, ["remaining", "remain", "available", "quota_remaining", "balance"]
        )
        if limit is None and remaining is None:
            raise ProviderSyncError("parse_error", "MiniMax quota payload did not include quota fields")
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
    model_remains = payload.get("model_remains") if isinstance(payload, dict) else None
    if isinstance(model_remains, list):
        return _model_remains_quota(model_remains)

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return data
    for key in ("text", "m2_7", "token", "tokens", "quota", "plan"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def _model_remains_quota(model_remains: list[Any]) -> dict[str, Any]:
    limit = 0
    used = 0
    reset_timestamps: list[int] = []
    model_names: list[str] = []
    for item in model_remains:
        if not isinstance(item, dict):
            raise ProviderSyncError("parse_error", "MiniMax model_remains item must be a JSON object")
        limit += _required_non_negative_int(item, "current_interval_total_count")
        used += _required_non_negative_int(item, "current_interval_usage_count")
        reset_at = _first_non_negative_int(item, ["end_time"])
        if reset_at is not None:
            reset_timestamps.append(reset_at)
        model_name = str(item.get("model_name") or "").strip()
        if model_name:
            model_names.append(model_name)
    quota = {
        "limit": limit,
        "remaining": max(limit - used, 0),
        "used": used,
        "model_count": len(model_remains),
    }
    if reset_timestamps:
        quota["reset_at"] = min(reset_timestamps)
    if model_names:
        quota["model_names"] = model_names
    return quota


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


def _required_non_negative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", f"MiniMax {key} was not an integer") from exc
    if parsed < 0:
        raise ProviderSyncError("parse_error", f"MiniMax {key} must be non-negative")
    return parsed


def _reset_at(payload: Any, now: datetime) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    seconds = _first_non_negative_int(payload, ["reset_seconds", "reset_in", "reset_after_seconds"])
    if seconds is not None:
        return now.astimezone(UTC) + timedelta(seconds=seconds)
    timestamp = _first_non_negative_int(payload, ["reset_at", "reset_time", "reset_timestamp", "reset"])
    if timestamp is None:
        return None
    if timestamp >= 10_000_000_000:
        timestamp = timestamp // 1000
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


def _json_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderSyncError("parse_error", "MiniMax response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderSyncError("parse_error", "MiniMax response must be a JSON object")
    return payload


def _raise_for_base_resp(payload: dict[str, Any]) -> None:
    base_resp = payload.get("base_resp")
    if base_resp is None:
        return
    if not isinstance(base_resp, dict):
        raise ProviderSyncError("parse_error", "MiniMax base_resp must be a JSON object")
    status_code = base_resp.get("status_code", 0)
    try:
        parsed_status = int(status_code)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", "MiniMax base_resp.status_code was malformed") from exc
    if parsed_status != 0:
        status_msg = str(base_resp.get("status_msg") or base_resp.get("message") or "unknown error")
        raise ProviderSyncError(
            "provider_error", f"MiniMax base_resp status {parsed_status}: {status_msg}"
        )
