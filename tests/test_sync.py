from datetime import UTC, datetime, timedelta

import pytest

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.services.sync import SyncService


class GoodConnector:
    provider_id = "good"
    display_name = "Good Provider"

    async def sync(self, now: datetime) -> SyncResult:
        period_start = datetime(2026, 5, 1, tzinfo=UTC)
        return SyncResult(
            provider_id=self.provider_id,
            snapshots=[
                UsageSnapshot(
                    provider_id=self.provider_id,
                    period_start=period_start,
                    period_end=period_start + timedelta(days=1),
                    granularity="day",
                    currency="USD",
                    cost_amount=1.25,
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                    requests=3,
                    quota_limit=None,
                    quota_remaining=None,
                    quota_reset_at=None,
                    raw_summary={"source": "test"},
                )
            ],
            status_message="ok",
        )


class BadConnector:
    provider_id = "bad"
    display_name = "Bad Provider"

    async def sync(self, now: datetime) -> SyncResult:
        raise ProviderSyncError("auth_error", "bad key")


@pytest.mark.asyncio
async def test_sync_all_records_success_and_failure(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    service = SyncService(
        Settings(database_url=temp_db_url),
        db,
        connectors=[GoodConnector(), BadConnector()],
    )

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result["sync"]["status"] == "completed"
    assert result["providers"]["good"] == {
        "status": "succeeded",
        "snapshots_written": 1,
        "message": "ok",
    }
    assert result["providers"]["bad"] == {
        "status": "failed",
        "error_type": "auth_error",
        "error_message": "bad key",
    }

    bad_runs = db.recent_sync_runs("bad", limit=1)
    assert bad_runs[0]["status"] == "failed"
    assert bad_runs[0]["error_type"] == "auth_error"
    assert bad_runs[0]["error_message"] == "bad key"

    good_runs = db.recent_sync_runs("good", limit=1)
    assert good_runs[0]["status"] == "succeeded"
    assert good_runs[0]["snapshots_written"] == 1
