from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderSyncError
from api_spend_dashboard.providers.gemini import rows_to_snapshots
from api_spend_dashboard.providers.qianfan import QianfanConnector, _signed_headers


def test_gemini_rows_to_snapshots(temp_db_url):
    settings = Settings(database_url=temp_db_url, default_currency="usd")
    rows = [
        SimpleNamespace(
            usage_start_time=datetime(2026, 5, 1, tzinfo=UTC),
            usage_end_time=datetime(2026, 5, 2, tzinfo=UTC),
            cost="3.25",
            currency="cny",
            service_description="Gemini API",
        )
    ]

    snapshots = rows_to_snapshots(settings, rows)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.provider_id == "gemini"
    assert snapshot.period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert snapshot.period_end == datetime(2026, 5, 2, tzinfo=UTC)
    assert snapshot.granularity == "day"
    assert snapshot.currency == "CNY"
    assert snapshot.cost_amount == 3.25
    assert snapshot.raw_summary["service_description"] == "Gemini API"
    _assert_can_upsert(temp_db_url, snapshot)


def test_gemini_rows_to_snapshots_aggregates_duplicate_daily_rows(temp_db_url):
    settings = Settings(database_url=temp_db_url, default_currency="usd")
    rows = [
        SimpleNamespace(
            usage_start_time=datetime(2026, 5, 1, 0, 0, tzinfo=UTC),
            usage_end_time=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            cost="3.25",
            currency="usd",
            service_description="Gemini API",
        ),
        SimpleNamespace(
            usage_start_time=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            usage_end_time=datetime(2026, 5, 2, 0, 0, tzinfo=UTC),
            cost="2.75",
            currency="usd",
            service_description="Vertex AI Gemini",
        ),
    ]

    snapshots = rows_to_snapshots(settings, rows)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert snapshot.period_end == datetime(2026, 5, 2, tzinfo=UTC)
    assert snapshot.currency == "USD"
    assert snapshot.cost_amount == 6.0
    assert snapshot.raw_summary == {
        "row_count": 2,
        "service_descriptions": ["Gemini API", "Vertex AI Gemini"],
    }
    _assert_can_upsert(temp_db_url, snapshot)


def test_gemini_rows_reject_single_row_spanning_multiple_utc_dates(temp_db_url):
    settings = Settings(database_url=temp_db_url)
    rows = [
        {
            "usage_start_time": "2026-05-01T23:00:00Z",
            "usage_end_time": "2026-05-02T01:00:00Z",
            "cost": "1.00",
            "service_description": "Gemini API",
        }
    ]

    with pytest.raises(ProviderSyncError) as exc_info:
        rows_to_snapshots(settings, rows)

    assert exc_info.value.error_type == "parse_error"


def test_gemini_row_parse_errors_are_provider_sync_errors(temp_db_url):
    settings = Settings(database_url=temp_db_url)
    rows = [
        {
            "usage_start_time": "2026-05-02T00:00:00Z",
            "usage_end_time": "2026-05-01T00:00:00Z",
            "cost": "1.00",
            "service_description": "Gemini API",
        }
    ]

    with pytest.raises(ProviderSyncError) as exc_info:
        rows_to_snapshots(settings, rows)

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.parametrize("cost", ["nan", "inf", "-inf"])
def test_gemini_non_finite_cost_maps_to_parse_error(temp_db_url, cost):
    settings = Settings(database_url=temp_db_url)
    rows = [
        {
            "usage_start_time": "2026-05-01T00:00:00Z",
            "usage_end_time": "2026-05-02T00:00:00Z",
            "cost": cost,
            "service_description": "Gemini API",
        }
    ]

    with pytest.raises(ProviderSyncError) as exc_info:
        rows_to_snapshots(settings, rows)

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
async def test_qianfan_metric_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        default_currency="usd",
        qianfan_enabled=True,
        baidu_access_key_id="ak",
        baidu_secret_access_key="sk",
        qianfan_service_ids="svc-1, svc-2",
        qianfan_app_ids="app-1",
    )
    route = respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "serviceList": [
                        {
                            "serviceId": "svc-1",
                            "appList": [
                                {
                                    "appId": "app-1",
                                    "metric": {
                                        "inputTokensTotal": 10,
                                        "outputTokensTotal": 4,
                                        "requestTotal": 2,
                                    },
                                }
                            ],
                        },
                        {
                            "serviceId": "svc-2",
                            "appList": [
                                {
                                    "appId": "app-1",
                                    "metric": {
                                        "inputTokensTotal": "7",
                                        "outputTokensTotal": "8",
                                        "requestTotal": "3",
                                    },
                                }
                            ],
                        },
                    ]
                }
            },
        )
    )

    result = await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.provider_id == "qianfan"
    snapshot = result.snapshots[0]
    assert snapshot.provider_id == "qianfan"
    assert snapshot.period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert snapshot.period_end == datetime(2026, 6, 1, tzinfo=UTC)
    assert snapshot.granularity == "month"
    assert snapshot.currency == "USD"
    assert snapshot.cost_amount is None
    assert snapshot.input_tokens == 17
    assert snapshot.output_tokens == 12
    assert snapshot.total_tokens == 29
    assert snapshot.requests == 5
    assert snapshot.raw_summary["cost_available"] is False
    request = route.calls.last.request
    assert request.url.params["Action"] == "DescribeServiceMetric"
    assert request.headers["Authorization"].startswith("bce-auth-v1/ak/")
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Host"] == "qianfan.baidubce.com"
    assert request.headers["x-bce-date"]
    body = request.read().decode()
    assert "svc-1" in body
    assert "svc-2" in body
    assert "app-1" in body
    _assert_can_upsert(temp_db_url, snapshot)


def test_qianfan_signed_headers_use_semicolon_signed_header_names():
    headers = _signed_headers(
        access_key_id="ak",
        secret_access_key="sk",
        method="POST",
        url="https://qianfan.baidubce.com/v2/service",
        params={"Action": "DescribeServiceMetric"},
        content_type="application/json",
        now=datetime(2026, 5, 2, 3, 4, 5, tzinfo=UTC),
    )

    authorization = headers["Authorization"]
    assert authorization.startswith("bce-auth-v1/ak/2026-05-02T03:04:05Z/1800/")
    assert "/content-type;host;x-bce-date/" in authorization
    assert "/content-type/host/x-bce-date/" not in authorization


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("metric", "expected_message"),
    [
        ({"outputTokensTotal": 4, "requestTotal": 2}, "inputTokensTotal"),
        (
            {"inputTokensTotal": -1, "outputTokensTotal": 4, "requestTotal": 2},
            "inputTokensTotal",
        ),
        (
            {"inputTokensTotal": 1.5, "outputTokensTotal": 4, "requestTotal": 2},
            "inputTokensTotal",
        ),
    ],
)
async def test_qianfan_malformed_metric_values_map_to_parse_error(
    temp_db_url, metric, expected_message
):
    settings = _qianfan_settings(temp_db_url)
    respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(200, json=_qianfan_payload(metric))
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"
    assert expected_message in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_qianfan_invalid_json_maps_to_parse_error(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        qianfan_enabled=True,
        baidu_access_key_id="ak",
        baidu_secret_access_key="sk",
    )
    respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(200, content=b"not json")
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("status_code", [401, 403])
async def test_qianfan_auth_errors_map_to_provider_sync_error(temp_db_url, status_code):
    settings = _qianfan_settings(temp_db_url)
    respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(status_code, json={"error": "unauthorized"})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "auth_error"


@pytest.mark.asyncio
@respx.mock
async def test_qianfan_server_error_maps_to_provider_sync_error(temp_db_url):
    settings = _qianfan_settings(temp_db_url)
    respx.post("https://qianfan.baidubce.com/v2/service").mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await QianfanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "provider_error"
    assert "500" in exc_info.value.message


def _qianfan_settings(temp_db_url: str) -> Settings:
    return Settings(
        database_url=temp_db_url,
        qianfan_enabled=True,
        baidu_access_key_id="ak",
        baidu_secret_access_key="sk",
    )


def _qianfan_payload(metric: dict) -> dict:
    return {
        "result": {
            "serviceList": [
                {
                    "serviceId": "svc-1",
                    "appList": [{"appId": "app-1", "metric": metric}],
                }
            ]
        }
    }


def _assert_can_upsert(temp_db_url: str, snapshot) -> None:
    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(snapshot)
