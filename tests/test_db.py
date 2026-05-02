from datetime import UTC, datetime

from api_spend_dashboard.db import Database
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.services.queries import DashboardQueries


def test_snapshot_upsert_and_month_summary(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    snapshot = UsageSnapshot(
        provider_id="openai",
        period_start=datetime(2026, 5, 1, tzinfo=UTC),
        period_end=datetime(2026, 5, 2, tzinfo=UTC),
        granularity="day",
        currency="USD",
        cost_amount=12.5,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        requests=3,
        quota_limit=None,
        quota_remaining=None,
        quota_reset_at=None,
        raw_summary={"source": "test"},
    )

    db.upsert_snapshot(snapshot)
    db.upsert_snapshot(snapshot)

    summary = DashboardQueries(db).month_summary(2026, 5)

    assert summary["total_cost"] == 12.5
    assert summary["total_tokens"] == 150
    assert summary["total_requests"] == 3
    assert summary["provider_count"] == 1


def test_sync_run_records_error(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    run_id = db.start_sync_run("openai")
    db.finish_sync_run(
        run_id, status="failed", error_type="auth_error", error_message="bad key"
    )

    runs = db.recent_sync_runs("openai", limit=1)

    assert runs[0]["status"] == "failed"
    assert runs[0]["error_type"] == "auth_error"
    assert runs[0]["error_message"] == "bad key"
