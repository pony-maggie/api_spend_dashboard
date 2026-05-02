from datetime import UTC, datetime

import httpx
import pytest
import respx

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
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
async def test_brave_quota_header_snapshot(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=True, brave_api_key="brave")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
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
    respx.get("https://api.openai.com/v1/organization/costs").mock(
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
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
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
    _assert_can_upsert(temp_db_url, snapshot)


def _assert_can_upsert(temp_db_url: str, snapshot) -> None:
    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(snapshot)
