from datetime import UTC, datetime, timedelta, timezone

import pytest

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderSyncError
from api_spend_dashboard.providers.manual import ChatGPTProConnector


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        chatgpt_pro_price=200,
        chatgpt_pro_currency="USD",
        chatgpt_pro_renewal_date="2026-05-20",
    )
    connector = ChatGPTProConnector(settings)

    result = await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.provider_id == "chatgpt_pro"
    assert len(result.snapshots) == 1
    assert result.snapshots[0].cost_amount == 200
    assert result.snapshots[0].raw_summary["automatic_token_usage"] is False


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_period_bounds(temp_db_url):
    connector = ChatGPTProConnector(_settings(temp_db_url))

    result = await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert result.snapshots[0].period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert result.snapshots[0].period_end == datetime(2026, 6, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_december_rollover(temp_db_url):
    connector = ChatGPTProConnector(_settings(temp_db_url))

    result = await connector.sync(datetime(2026, 12, 31, tzinfo=UTC))

    assert result.snapshots[0].period_start == datetime(2026, 12, 1, tzinfo=UTC)
    assert result.snapshots[0].period_end == datetime(2027, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_normalizes_aware_now_to_utc(temp_db_url):
    connector = ChatGPTProConnector(_settings(temp_db_url))

    result = await connector.sync(datetime(2026, 6, 1, 7, 30, tzinfo=timezone(timedelta(hours=8))))

    assert result.snapshots[0].period_start == datetime(2026, 5, 1, tzinfo=UTC)
    assert result.snapshots[0].period_end == datetime(2026, 6, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_rejects_naive_now(temp_db_url):
    connector = ChatGPTProConnector(_settings(temp_db_url))

    with pytest.raises(ValueError, match="timezone-aware"):
        await connector.sync(datetime(2026, 5, 2))


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_can_be_upserted(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    connector = ChatGPTProConnector(_settings(temp_db_url, chatgpt_pro_currency=" usd "))

    result = await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))
    db.upsert_snapshot(result.snapshots[0])

    rows = db.query_all(
        """
        SELECT provider_id, period_start, period_end, granularity, currency, cost_amount
        FROM usage_snapshots
        """
    )

    assert rows == [
        {
            "provider_id": "chatgpt_pro",
            "period_start": "2026-05-01T00:00:00+00:00",
            "period_end": "2026-06-01T00:00:00+00:00",
            "granularity": "month",
            "currency": "USD",
            "cost_amount": 200.0,
        }
    ]


@pytest.mark.asyncio
async def test_chatgpt_pro_monthly_snapshot_rejects_blank_currency(temp_db_url):
    connector = ChatGPTProConnector(_settings(temp_db_url, chatgpt_pro_currency=" "))

    with pytest.raises(ProviderSyncError, match="CHATGPT_PRO_CURRENCY must be non-empty"):
        await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [0, -1])
async def test_chatgpt_pro_monthly_snapshot_rejects_non_positive_price(temp_db_url, price):
    connector = ChatGPTProConnector(_settings(temp_db_url, chatgpt_pro_price=price))

    with pytest.raises(ProviderSyncError, match="CHATGPT_PRO_PRICE must be positive") as exc_info:
        await connector.sync(datetime(2026, 5, 2, tzinfo=UTC))

    assert exc_info.value.error_type == "missing_config"


def _settings(temp_db_url: str, **overrides: object) -> Settings:
    values = {
        "database_url": temp_db_url,
        "chatgpt_pro_price": 200,
        "chatgpt_pro_currency": "USD",
        "chatgpt_pro_renewal_date": "2026-05-20",
    }
    values.update(overrides)
    return Settings(**values)
