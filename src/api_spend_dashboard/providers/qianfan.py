from datetime import UTC, datetime
import hashlib
import hmac
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class QianfanConnector:
    provider_id = "qianfan"
    display_name = "Baidu Qianfan"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        start, end = _month_bounds(now)
        endpoint = self.settings.qianfan_endpoint.rstrip("/")
        url = f"{endpoint}/v2/service"
        params = {"Action": "DescribeServiceMetric"}
        body = {
            "startTime": _iso_z(start),
            "endTime": _iso_z(end),
            "serviceIds": self.settings.csv_values(self.settings.qianfan_service_ids),
            "appIds": self.settings.csv_values(self.settings.qianfan_app_ids),
        }
        headers = _signed_headers(
            access_key_id=self.settings.baidu_access_key_id,
            secret_access_key=self.settings.baidu_secret_access_key,
            method="POST",
            url=url,
            params=params,
            content_type="application/json",
            now=now,
        )

        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.post(url, params=params, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProviderSyncError("provider_error", f"Qianfan request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise ProviderSyncError("auth_error", "Baidu AK/SK was rejected")
        if response.status_code >= 400:
            raise ProviderSyncError("provider_error", f"Qianfan returned HTTP {response.status_code}")

        payload = _json_dict(response)
        aggregate = _aggregate_metrics(payload)
        snapshot = UsageSnapshot(
            provider_id=self.provider_id,
            period_start=start,
            period_end=end,
            granularity="month",
            currency=_currency(self.settings.default_currency),
            cost_amount=None,
            input_tokens=aggregate["input_tokens"],
            output_tokens=aggregate["output_tokens"],
            total_tokens=aggregate["total_tokens"],
            requests=aggregate["requests"],
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={
                "cost_available": False,
                "service_ids": body["serviceIds"],
                "app_ids": body["appIds"],
                "metrics_count": aggregate["metrics_count"],
            },
        )
        return SyncResult(self.provider_id, [snapshot], "Baidu Qianfan service metrics synced")


def _signed_headers(
    *,
    access_key_id: str,
    secret_access_key: str,
    method: str,
    url: str,
    params: dict[str, str],
    content_type: str,
    now: datetime,
) -> dict[str, str]:
    ak = access_key_id.strip()
    sk = secret_access_key.strip()
    if not ak or not sk:
        raise ProviderSyncError("missing_config", "BAIDU_ACCESS_KEY_ID and BAIDU_SECRET_ACCESS_KEY are required")

    timestamp = _iso_z(now.astimezone(UTC))
    parsed = urlparse(url)
    host = parsed.netloc
    headers = {
        "Content-Type": content_type,
        "Host": host,
        "x-bce-date": timestamp,
    }
    signed_header_names = ["content-type", "host", "x-bce-date"]
    canonical_headers = "\n".join(
        f"{_quote(name)}:{_quote(headers[_header_lookup(headers, name)].strip())}"
        for name in signed_header_names
    )
    canonical_request = "\n".join(
        [
            method.upper(),
            _canonical_uri(parsed.path or "/"),
            _canonical_query(params),
            canonical_headers,
        ]
    )
    expiration_seconds = 1800
    auth_prefix = f"bce-auth-v1/{ak}/{timestamp}/{expiration_seconds}"
    signing_key = hmac.new(sk.encode(), auth_prefix.encode(), hashlib.sha256).hexdigest()
    signature = hmac.new(
        signing_key.encode(),
        canonical_request.encode(),
        hashlib.sha256,
    ).hexdigest()
    headers["Authorization"] = (
        f"{auth_prefix}/{'/'.join(signed_header_names)}/{signature}"
    )
    return headers


def _aggregate_metrics(payload: dict[str, Any]) -> dict[str, int]:
    metrics = _metrics_list(payload)
    aggregate = {
        "input_tokens": 0,
        "output_tokens": 0,
        "requests": 0,
        "metrics_count": len(metrics),
    }
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ProviderSyncError("parse_error", "Qianfan metric must be a JSON object")
        aggregate["input_tokens"] += _non_negative_int(metric.get("inputTokensTotal"), "inputTokensTotal")
        aggregate["output_tokens"] += _non_negative_int(metric.get("outputTokensTotal"), "outputTokensTotal")
        aggregate["requests"] += _non_negative_int(metric.get("requestTotal"), "requestTotal")
    aggregate["total_tokens"] = aggregate["input_tokens"] + aggregate["output_tokens"]
    return aggregate


def _metrics_list(payload: dict[str, Any]) -> list[Any]:
    nested_metrics = _service_app_metrics(payload)
    if nested_metrics is not None:
        return nested_metrics

    candidates = [
        payload.get("metrics"),
        payload.get("metric"),
        payload.get("serviceMetrics"),
        payload.get("serviceMetricsList"),
    ]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend(
            [
                result.get("metrics"),
                result.get("metric"),
                result.get("serviceMetrics"),
                result.get("serviceMetricsList"),
                result.get("list"),
            ]
        )
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("metrics"), data.get("list")])

    for candidate in candidates:
        if candidate is None:
            continue
        if not isinstance(candidate, list):
            raise ProviderSyncError("parse_error", "Qianfan metrics payload must be a list")
        return candidate
    raise ProviderSyncError("parse_error", "Qianfan response did not include metrics")


def _service_app_metrics(payload: dict[str, Any]) -> list[Any] | None:
    result = payload.get("result")
    if not isinstance(result, dict) or "serviceList" not in result:
        return None

    service_list = result["serviceList"]
    if not isinstance(service_list, list):
        raise ProviderSyncError("parse_error", "Qianfan serviceList must be a list")

    metrics: list[Any] = []
    for service in service_list:
        if not isinstance(service, dict):
            raise ProviderSyncError("parse_error", "Qianfan service must be a JSON object")
        app_list = service.get("appList", [])
        if not isinstance(app_list, list):
            raise ProviderSyncError("parse_error", "Qianfan appList must be a list")
        for app in app_list:
            if not isinstance(app, dict):
                raise ProviderSyncError("parse_error", "Qianfan app must be a JSON object")
            metric = app.get("metric")
            if not isinstance(metric, dict):
                raise ProviderSyncError("parse_error", "Qianfan app metric must be a JSON object")
            metrics.append(metric)
    return metrics


def _json_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderSyncError("parse_error", "Qianfan response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderSyncError("parse_error", "Qianfan response must be a JSON object")
    return payload


def _non_negative_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", f"Qianfan {field_name} was not an integer") from exc
    if parsed < 0:
        raise ProviderSyncError("parse_error", f"Qianfan {field_name} must be non-negative")
    return parsed


def _currency(value: str) -> str:
    currency = value.strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", "DEFAULT_CURRENCY must be non-empty")
    return currency


def _canonical_query(params: dict[str, str]) -> str:
    return "&".join(f"{_quote(key)}={_quote(value)}" for key, value in sorted(params.items()))


def _canonical_uri(path: str) -> str:
    return quote(path, safe="/~")


def _quote(value: str) -> str:
    return quote(str(value), safe="~")


def _header_lookup(headers: dict[str, str], lowercase_name: str) -> str:
    for name in headers:
        if name.lower() == lowercase_name:
            return name
    raise KeyError(lowercase_name)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
