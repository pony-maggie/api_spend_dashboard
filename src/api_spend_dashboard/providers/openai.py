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

        params = {"start_time": start_time, "end_time": end_time, "bucket_width": "1d"}
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

        usage_by_start = _usage_by_start(usage.json())
        snapshots = _cost_snapshots(costs.json(), usage_by_start, self.settings.default_currency)
        if not snapshots:
            snapshots.append(_empty_month_snapshot(start, now_utc, self.settings.default_currency))
        return SyncResult(self.provider_id, snapshots, "OpenAI usage and costs synced")


def _cost_snapshots(
    payload: dict[str, Any], usage_by_start: dict[int, dict[str, int]], default_currency: str
) -> list[UsageSnapshot]:
    snapshots: list[UsageSnapshot] = []
    for bucket in payload.get("data", []):
        bucket_start_ts = int(bucket["start_time"])
        bucket_start = datetime.fromtimestamp(bucket_start_ts, tz=UTC)
        bucket_end = datetime.fromtimestamp(int(bucket["end_time"]), tz=UTC)
        amount = 0.0
        currency = _currency(default_currency)
        for result in bucket.get("results", []):
            amount_payload = result.get("amount", {})
            amount += max(float(amount_payload.get("value") or 0), 0.0)
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
    for bucket in payload.get("data", []):
        aggregate = {"input_tokens": 0, "output_tokens": 0, "num_model_requests": 0}
        for result in bucket.get("results", []):
            aggregate["input_tokens"] += _non_negative_int(result.get("input_tokens"))
            aggregate["output_tokens"] += _non_negative_int(result.get("output_tokens"))
            aggregate["num_model_requests"] += _non_negative_int(result.get("num_model_requests"))
        by_start[int(bucket["start_time"])] = aggregate
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
    return max(int(value or 0), 0)


def _currency(value: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", "currency must be non-empty")
    return currency
