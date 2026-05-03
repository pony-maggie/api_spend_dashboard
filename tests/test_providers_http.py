from datetime import UTC, datetime

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderSyncError
from api_spend_dashboard.providers.brave import BraveConnector
from api_spend_dashboard.providers.digitalocean import DigitalOceanConnector
from api_spend_dashboard.providers.minimax import MiniMaxConnector
from api_spend_dashboard.providers.openai import OpenAIConnector


@pytest.mark.asyncio
@respx.mock
async def test_minimax_remains_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
        minimax_plan_name="Plus",
        minimax_plan_price=99,
        minimax_plan_currency=" usd ",
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={
                "base_resp": {"status_code": 0},
                "data": {"text": {"limit": 4500, "remaining": 3000, "reset_seconds": 7200}},
            },
        )
    )

    result = await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.provider_id == "minimax"
    snapshot = result.snapshots[0]
    assert snapshot.provider_id == "minimax"
    assert snapshot.period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert snapshot.period_end == datetime(2026, 6, 1, tzinfo=UTC)
    assert snapshot.currency == "USD"
    assert snapshot.quota_limit == 4500
    assert snapshot.quota_remaining == 3000
    assert snapshot.cost_amount == 99
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_minimax_model_remains_list_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
        minimax_plan_price=99,
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "current_interval_total_count": 1000,
                        "current_interval_usage_count": 250,
                        "model_name": "model-a",
                    },
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "current_interval_total_count": 500,
                        "current_interval_usage_count": 100,
                        "model_name": "model-b",
                    },
                ],
            },
        )
    )

    result = await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    snapshot = result.snapshots[0]
    assert snapshot.quota_limit == 1500
    assert snapshot.quota_remaining == 1150
    assert snapshot.quota_reset_at == datetime(2026, 5, 2, tzinfo=UTC)
    assert snapshot.raw_summary["quota_payload"]["model_count"] == 2
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_minimax_model_remains_list_accepts_millisecond_timestamps(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={
                "base_resp": {"status_code": 0},
                "model_remains": [
                    {
                        "end_time": 1777680000000,
                        "current_interval_total_count": 1000,
                        "current_interval_usage_count": 250,
                    }
                ],
            },
        )
    )

    result = await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].quota_reset_at == datetime(2026, 5, 2, tzinfo=UTC)


@pytest.mark.asyncio
@respx.mock
async def test_brave_quota_header_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=True, brave_api_key="brave")
    route = respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "1, 15000",
                "X-RateLimit-Remaining": "1, 14900",
                "X-RateLimit-Reset": "1, 1000",
            },
            json={"web": {"results": []}},
        )
    )

    result = await BraveConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    snapshot = result.snapshots[0]
    assert snapshot.quota_limit == 15000
    assert snapshot.quota_remaining == 14900
    assert snapshot.requests == 100
    assert snapshot.cost_amount == 0.5
    assert snapshot.raw_summary["cost_is_estimate"] is True
    request = route.calls.last.request
    assert request.headers["X-Subscription-Token"] == "brave"
    assert request.url.params["q"] == "api spend dashboard"
    assert request.url.params["count"] == "1"
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_digitalocean_balance_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, digitalocean_enabled=True, digitalocean_token="do")
    respx.get("https://api.digitalocean.com/v2/customers/my/balance").mock(
        return_value=httpx.Response(
            200,
            json={
                "month_to_date_balance": "6.25",
                "account_balance": "0.00",
                "month_to_date_usage": "6.25",
            },
        )
    )

    result = await DigitalOceanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    snapshot = result.snapshots[0]
    assert snapshot.provider_id == "digitalocean"
    assert snapshot.currency == "USD"
    assert snapshot.cost_amount == 6.25
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_openai_cost_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key="sk-admin")
    costs_route = respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "results": [{"amount": {"value": 3.5, "currency": "usd"}}],
                    }
                ]
            },
        )
    )
    usage_route = respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": 1777593600,
                        "end_time": 1777680000,
                        "results": [
                            {"input_tokens": 10, "output_tokens": 5, "num_model_requests": 2}
                        ],
                    }
                ]
            },
        )
    )

    result = await OpenAIConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    snapshot = result.snapshots[0]
    assert snapshot.provider_id == "openai"
    assert snapshot.granularity == "day"
    assert snapshot.currency == "USD"
    assert snapshot.cost_amount == 3.5
    assert snapshot.input_tokens == 10
    assert snapshot.output_tokens == 5
    assert snapshot.total_tokens == 15
    assert snapshot.requests == 2
    for route in (costs_route, usage_route):
        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer sk-admin"
        assert request.url.params["bucket_width"] == "1d"
        assert request.url.params["start_time"] == "1777593600"
        assert request.url.params["end_time"] == "1777680000"
        assert request.url.params["limit"] == "31"
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_digitalocean_auth_error_maps_to_provider_sync_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, digitalocean_enabled=True, digitalocean_token="do")
    respx.get("https://api.digitalocean.com/v2/customers/my/balance").mock(
        return_value=httpx.Response(401, json={"id": "Unauthorized"})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await DigitalOceanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "auth_error"


@pytest.mark.asyncio
@respx.mock
async def test_brave_rate_limited_maps_to_provider_sync_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=True, brave_api_key="brave")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(429, json={"error": "too many requests"})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await BraveConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "rate_limited"


@pytest.mark.asyncio
@respx.mock
async def test_minimax_nonzero_base_resp_fails(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
        minimax_plan_price=99,
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(
            200,
            json={"base_resp": {"status_code": 1001, "status_msg": "invalid account"}},
        )
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "provider_error"
    assert "1001" in exc_info.value.message


@pytest.mark.asyncio
@respx.mock
async def test_brave_malformed_rate_limit_headers_map_to_parse_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=True, brave_api_key="brave")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "1, nope",
                "X-RateLimit-Remaining": "1, 14900",
                "X-RateLimit-Reset": "1, 1000",
            },
            json={"web": {"results": []}},
        )
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await BraveConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
async def test_openai_empty_data_returns_db_valid_zero_month_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key="sk-admin")
    respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    result = await OpenAIConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    snapshot = result.snapshots[0]
    assert snapshot.provider_id == "openai"
    assert snapshot.granularity == "month"
    assert snapshot.cost_amount == 0
    assert snapshot.input_tokens == 0
    assert snapshot.output_tokens == 0
    assert snapshot.total_tokens == 0
    assert snapshot.requests == 0
    _assert_can_upsert(temp_db_url, snapshot)


@pytest.mark.asyncio
@respx.mock
async def test_openai_malformed_bucket_maps_to_parse_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key="sk-admin")
    respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "start_time": "not-a-timestamp",
                        "end_time": 1777680000,
                        "results": [{"amount": {"value": 3.5, "currency": "usd"}}],
                    }
                ]
            },
        )
    )
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await OpenAIConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
async def test_openai_invalid_json_maps_to_parse_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, openai_enabled=True, openai_admin_api_key="sk-admin")
    respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(200, content=b"not json")
    )
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await OpenAIConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
async def test_digitalocean_nonnumeric_amount_maps_to_parse_error(temp_db_url):
    settings = Settings(database_url=temp_db_url, digitalocean_enabled=True, digitalocean_token="do")
    respx.get("https://api.digitalocean.com/v2/customers/my/balance").mock(
        return_value=httpx.Response(
            200,
            json={"month_to_date_balance": "nope", "account_balance": "0.00"},
        )
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await DigitalOceanConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


@pytest.mark.asyncio
@respx.mock
async def test_minimax_unexpected_payload_maps_to_parse_error(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        minimax_enabled=True,
        minimax_api_key="sk-test",
        minimax_plan_price=99,
    )
    respx.get("https://www.minimax.io/v1/token_plan/remains").mock(
        return_value=httpx.Response(200, json=["not", "a", "dict"])
    )

    with pytest.raises(ProviderSyncError) as exc_info:
        await MiniMaxConnector(settings).sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "parse_error"


def _assert_can_upsert(temp_db_url: str, snapshot) -> None:
    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(snapshot)
