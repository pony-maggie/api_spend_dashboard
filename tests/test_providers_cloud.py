from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderSyncError
from api_spend_dashboard.providers.gemini import rows_to_snapshots
from api_spend_dashboard.providers.qianfan import QianfanConnector


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
                    "metrics": [
                        {
                            "serviceId": "svc-1",
                            "appId": "app-1",
                            "inputTokensTotal": 10,
                            "outputTokensTotal": 4,
                            "requestTotal": 2,
                        },
                        {
                            "serviceId": "svc-2",
                            "appId": "app-1",
                            "inputTokensTotal": "7",
                            "outputTokensTotal": "8",
                            "requestTotal": "3",
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


def _assert_can_upsert(temp_db_url: str, snapshot) -> None:
    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(snapshot)
