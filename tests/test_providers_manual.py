from datetime import UTC, datetime

import pytest

from api_spend_dashboard.config import Settings
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
