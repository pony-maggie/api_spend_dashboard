from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class OpenAIConnector:
    provider_id = "openai"
    display_name = "OpenAI API"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        start, _ = _month_bounds(now)
        now_utc = now.astimezone(UTC)
        start_time = int(start.timestamp())
        end_time = int(now_utc.timestamp())
        headers = {"Authorization": f"Bearer {self.settings.openai_admin_api_key}"}
        if self.settings.openai_org_id.strip():
            headers["OpenAI-Organization"] = self.settings.openai_org_id.strip()

        params = {
            "start_time": start_time,
            "end_time": end_time,
            "bucket_width": "1d",
            "limit": 31,
        }
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            costs = await client.get(
                "https://api.openai.com/v1/organization/costs",
                headers=headers,
                params=params,
            )
            usage = await client.get(
                "https://api.openai.com/v1/organization/usage/completions",
                headers=headers,
                params=params,
            )

        for response in (costs, usage):
            if response.status_code in {401, 403}:
                raise ProviderSyncError("auth_error", "OpenAI admin API key was rejected")
            if response.status_code >= 400:
                raise ProviderSyncError(
                    "provider_error", f"OpenAI returned HTTP {response.status_code}"
                )

        usage_payload = _json_dict(usage, "OpenAI usage response must be a JSON object")
        costs_payload = _json_dict(costs, "OpenAI costs response must be a JSON object")
        usage_by_start = _usage_by_start(usage_payload)
        snapshots = _cost_snapshots(costs_payload, usage_by_start, self.settings.default_currency)
        if not snapshots:
            snapshots.append(_empty_month_snapshot(start, now_utc, self.settings.default_currency))
        return SyncResult(self.provider_id, snapshots, "OpenAI usage and costs synced")


def _cost_snapshots(
    payload: dict[str, Any], usage_by_start: dict[int, dict[str, int]], default_currency: str
) -> list[UsageSnapshot]:
    snapshots: list[UsageSnapshot] = []
    data = _data_list(payload, "OpenAI costs data must be a list")
    for bucket in data:
        if not isinstance(bucket, dict):
            raise ProviderSyncError("parse_error", "OpenAI costs bucket must be a JSON object")
        bucket_start_ts = _bucket_timestamp(bucket, "start_time", "OpenAI costs")
        bucket_end_ts = _bucket_timestamp(bucket, "end_time", "OpenAI costs")
        bucket_start = datetime.fromtimestamp(bucket_start_ts, tz=UTC)
        bucket_end = datetime.fromtimestamp(bucket_end_ts, tz=UTC)
        amount = 0.0
        currency = _currency(default_currency)
        results = bucket.get("results", [])
        if not isinstance(results, list):
            raise ProviderSyncError("parse_error", "OpenAI costs bucket results must be a list")
        for result in results:
            if not isinstance(result, dict):
                raise ProviderSyncError("parse_error", "OpenAI costs result must be a JSON object")
            amount_payload = result.get("amount", {})
            if not isinstance(amount_payload, dict):
                raise ProviderSyncError("parse_error", "OpenAI amount must be a JSON object")
            amount += _non_negative_float(amount_payload.get("value"))
            currency = _currency(str(amount_payload.get("currency") or currency))

        usage_bucket = usage_by_start.get(bucket_start_ts, {})
        input_tokens = usage_bucket.get("input_tokens")
        output_tokens = usage_bucket.get("output_tokens")
        total_tokens = None
        if input_tokens is not None or output_tokens is not None:
            total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

        snapshots.append(
            UsageSnapshot(
                provider_id=OpenAIConnector.provider_id,
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
    return snapshots


def _usage_by_start(payload: dict[str, Any]) -> dict[int, dict[str, int]]:
    by_start: dict[int, dict[str, int]] = {}
    data = _data_list(payload, "OpenAI usage data must be a list")
    for bucket in data:
        if not isinstance(bucket, dict):
            raise ProviderSyncError("parse_error", "OpenAI usage bucket must be a JSON object")
        bucket_start_ts = _bucket_timestamp(bucket, "start_time", "OpenAI usage")
        aggregate = {"input_tokens": 0, "output_tokens": 0, "num_model_requests": 0}
        results = bucket.get("results", [])
        if not isinstance(results, list):
            raise ProviderSyncError("parse_error", "OpenAI usage bucket results must be a list")
        for result in results:
            if not isinstance(result, dict):
                raise ProviderSyncError("parse_error", "OpenAI usage result must be a JSON object")
            aggregate["input_tokens"] += _non_negative_int(result.get("input_tokens"))
            aggregate["output_tokens"] += _non_negative_int(result.get("output_tokens"))
            aggregate["num_model_requests"] += _non_negative_int(result.get("num_model_requests"))
        by_start[bucket_start_ts] = aggregate
    return by_start


def _empty_month_snapshot(start: datetime, now_utc: datetime, default_currency: str) -> UsageSnapshot:
    period_end = now_utc if now_utc > start else start + timedelta(seconds=1)
    return UsageSnapshot(
        provider_id=OpenAIConnector.provider_id,
        period_start=start,
        period_end=period_end,
        granularity="month",
        currency=_currency(default_currency),
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


def _non_negative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", "OpenAI usage value was not an integer") from exc


def _non_negative_float(value: Any) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", "OpenAI cost amount was not numeric") from exc


def _currency(value: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", "currency must be non-empty")
    return currency


def _json_dict(response: httpx.Response, message: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderSyncError("parse_error", "OpenAI response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderSyncError("parse_error", message)
    return payload


def _data_list(payload: dict[str, Any], message: str) -> list[Any]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ProviderSyncError("parse_error", message)
    return data


def _bucket_timestamp(bucket: dict[str, Any], field_name: str, label: str) -> int:
    try:
        return int(bucket[field_name])
    except KeyError as exc:
        raise ProviderSyncError("parse_error", f"{label} bucket missing {field_name}") from exc
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", f"{label} bucket {field_name} was malformed") from exc
