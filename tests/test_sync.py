import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.services.sync import SyncService, build_connectors


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


class UnknownErrorConnector:
    provider_id = "unknown"
    display_name = "Unknown Error Provider"

    async def sync(self, now: datetime) -> SyncResult:
        raise RuntimeError("socket closed")


class SlowConnector:
    provider_id = "slow"
    display_name = "Slow Provider"

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def sync(self, now: datetime) -> SyncResult:
        self.started.set()
        await self.release.wait()
        return SyncResult(self.provider_id, [], "ok")


class PartialConnector:
    provider_id = "partial"
    display_name = "Partial Provider"

    async def sync(self, now: datetime) -> SyncResult:
        first_start = datetime(2026, 5, 1, tzinfo=UTC)
        invalid_start = datetime(2026, 5, 2, tzinfo=UTC)
        return SyncResult(
            provider_id=self.provider_id,
            snapshots=[
                _snapshot(self.provider_id, first_start),
                _snapshot(self.provider_id, invalid_start, period_end=invalid_start),
            ],
            status_message="partial",
        )


class StartFailureDatabase(Database):
    def start_sync_run(self, provider_id: str) -> int:
        if provider_id == "bad_start":
            raise RuntimeError("database locked")
        return super().start_sync_run(provider_id)


class FinishFailureDatabase(Database):
    def finish_sync_run(self, run_id: int, **kwargs: Any) -> None:
        if kwargs["status"] == "failed":
            raise RuntimeError("finish failed")
        super().finish_sync_run(run_id, **kwargs)


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


@pytest.mark.asyncio
async def test_sync_all_returns_already_running_when_lock_is_held(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    connector = SlowConnector()
    service = SyncService(Settings(database_url=temp_db_url), db, connectors=[connector])

    running = asyncio.create_task(service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC)))
    await connector.started.wait()

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result == {"sync": {"status": "already_running"}}
    connector.release.set()
    await running


@pytest.mark.asyncio
async def test_unknown_connector_error_does_not_skip_later_connectors(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    service = SyncService(
        Settings(database_url=temp_db_url),
        db,
        connectors=[UnknownErrorConnector(), GoodConnector()],
    )

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result["providers"]["unknown"]["status"] == "failed"
    assert result["providers"]["unknown"]["error_type"] == "unknown_error"
    assert result["providers"]["unknown"]["error_message"] == "socket closed"
    assert result["providers"]["good"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_start_sync_run_database_error_does_not_skip_later_connectors(temp_db_url):
    db = StartFailureDatabase(temp_db_url)
    db.migrate()
    bad_start = GoodConnector()
    bad_start.provider_id = "bad_start"
    service = SyncService(
        Settings(database_url=temp_db_url),
        db,
        connectors=[bad_start, GoodConnector()],
    )

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result["providers"]["bad_start"] == {
        "status": "failed",
        "error_type": "unknown_error",
        "error_message": "database locked",
        "snapshots_written": 0,
    }
    assert result["providers"]["good"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_finish_failure_is_reported_without_skipping_later_connectors(temp_db_url):
    db = FinishFailureDatabase(temp_db_url)
    db.migrate()
    service = SyncService(
        Settings(database_url=temp_db_url),
        db,
        connectors=[BadConnector(), GoodConnector()],
    )

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result["providers"]["bad"] == {
        "status": "failed",
        "error_type": "auth_error",
        "error_message": "bad key",
        "finish_error": "finish failed",
    }
    assert result["providers"]["good"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_partial_snapshot_write_count_is_recorded_on_failure(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    service = SyncService(
        Settings(database_url=temp_db_url),
        db,
        connectors=[PartialConnector()],
    )

    result = await service.sync_all(now=datetime(2026, 5, 2, tzinfo=UTC))

    assert result["providers"]["partial"]["status"] == "failed"
    assert result["providers"]["partial"]["error_type"] == "unknown_error"
    assert result["providers"]["partial"]["snapshots_written"] == 1
    partial_runs = db.recent_sync_runs("partial", limit=1)
    assert partial_runs[0]["status"] == "failed"
    assert partial_runs[0]["snapshots_written"] == 1


def test_build_connectors_skips_unconfigured_and_preserves_configured_order(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        openai_enabled=True,
        openai_admin_api_key="sk-openai",
        chatgpt_pro_enabled=True,
        chatgpt_pro_price=20,
        minimax_enabled=False,
        minimax_api_key="sk-minimax",
        brave_enabled=True,
        brave_api_key="sk-brave",
        digitalocean_enabled=True,
        digitalocean_token="do-token",
    )

    connectors = build_connectors(settings)

    assert [connector.provider_id for connector in connectors] == [
        "openai",
        "chatgpt_pro",
        "brave",
        "digitalocean",
    ]


def _snapshot(
    provider_id: str,
    period_start: datetime,
    *,
    period_end: datetime | None = None,
) -> UsageSnapshot:
    return UsageSnapshot(
        provider_id=provider_id,
        period_start=period_start,
        period_end=period_end or period_start + timedelta(days=1),
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
