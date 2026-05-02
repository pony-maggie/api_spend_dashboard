from datetime import UTC, datetime, timedelta

import pytest

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


def test_schema_uses_planned_columns(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    assert _column_names(db, "providers") == [
        "id",
        "name",
        "enabled",
        "status",
        "last_sync_at",
        "last_success_at",
        "last_error",
        "created_at",
        "updated_at",
    ]
    provider_columns = _columns_by_name(db, "providers")
    assert provider_columns["enabled"]["dflt_value"] == "0"
    assert provider_columns["status"]["dflt_value"] == "'disabled'"

    assert "snapshots_written" in _column_names(db, "sync_runs")
    assert _column_names(db, "usage_snapshots") == [
        "id",
        "provider_id",
        "period_start",
        "period_end",
        "granularity",
        "currency",
        "cost_amount",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "requests",
        "quota_limit",
        "quota_remaining",
        "quota_reset_at",
        "raw_summary_json",
        "created_at",
    ]
    assert _column_names(db, "manual_items") == [
        "id",
        "provider_id",
        "name",
        "amount",
        "currency",
        "billing_period",
        "start_date",
        "end_date",
        "renewal_date",
        "notes",
    ]
    assert _columns_by_name(db, "manual_items")["start_date"]["notnull"] == 0


def test_daily_costs_excludes_month_granularity(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    period_start = datetime.now(UTC) - timedelta(days=1)

    db.upsert_snapshot(
        _snapshot(
            period_start=period_start,
            period_end=period_start + timedelta(days=1),
            granularity="day",
            cost_amount=5.0,
        )
    )
    db.upsert_snapshot(
        _snapshot(
            period_start=period_start,
            period_end=period_start + timedelta(days=30),
            granularity="month",
            cost_amount=99.0,
        )
    )

    rows = DashboardQueries(db).daily_costs(days=7)

    assert rows == [
        {"date": period_start.date().isoformat(), "provider_id": "openai", "cost": 5.0}
    ]


def test_month_summary_prefers_day_rows_when_provider_has_day_and_month(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.upsert_snapshot(
        _snapshot(
            provider_id="openai",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 5, 2, tzinfo=UTC),
            granularity="day",
            cost_amount=5.0,
            total_tokens=100,
            requests=2,
        )
    )
    db.upsert_snapshot(
        _snapshot(
            provider_id="openai",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 1, tzinfo=UTC),
            granularity="month",
            cost_amount=99.0,
            total_tokens=999,
            requests=99,
        )
    )

    summary = DashboardQueries(db).month_summary(2026, 5)

    assert summary["total_cost"] == 5.0
    assert summary["total_tokens"] == 100
    assert summary["total_requests"] == 2
    assert summary["provider_count"] == 1


def test_month_summary_includes_month_only_provider(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.upsert_snapshot(
        _snapshot(
            provider_id="openai",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 5, 2, tzinfo=UTC),
            granularity="day",
            cost_amount=5.0,
            total_tokens=100,
            requests=2,
        )
    )
    db.upsert_snapshot(
        _snapshot(
            provider_id="chatgpt_pro",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 1, tzinfo=UTC),
            granularity="month",
            cost_amount=20.0,
            total_tokens=None,
            requests=None,
        )
    )

    summary = DashboardQueries(db).month_summary(2026, 5)

    assert summary["total_cost"] == 25.0
    assert summary["total_tokens"] == 100
    assert summary["total_requests"] == 2
    assert summary["provider_count"] == 2


def test_daily_costs_uses_calendar_date_cutoff(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    today = datetime.now(UTC).date()
    cutoff_date = today - timedelta(days=30)

    db.upsert_snapshot(
        _snapshot(
            period_start=datetime.combine(cutoff_date, datetime.min.time(), tzinfo=UTC),
            period_end=datetime.combine(cutoff_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            granularity="day",
            cost_amount=7.0,
        )
    )
    db.upsert_snapshot(
        _snapshot(
            period_start=datetime.combine(cutoff_date - timedelta(days=1), datetime.min.time(), tzinfo=UTC),
            period_end=datetime.combine(cutoff_date, datetime.min.time(), tzinfo=UTC),
            granularity="day",
            cost_amount=8.0,
        )
    )

    rows = DashboardQueries(db).daily_costs(days=30)

    assert rows == [
        {"date": cutoff_date.isoformat(), "provider_id": "openai", "cost": 7.0}
    ]


def test_snapshot_upsert_replaces_existing_row(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()
    snapshot = _snapshot(cost_amount=12.5, total_tokens=150, requests=3)
    replacement = _snapshot(cost_amount=20.0, total_tokens=250, requests=7)

    db.upsert_snapshot(snapshot)
    db.upsert_snapshot(replacement)

    rows = db.query_all("SELECT cost_amount, total_tokens, requests FROM usage_snapshots")

    assert rows == [{"cost_amount": 20.0, "total_tokens": 250, "requests": 7}]


def test_snapshot_upsert_preserves_same_period_with_different_currency(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.upsert_snapshot(_snapshot(cost_amount=12.5, currency="USD"))
    db.upsert_snapshot(_snapshot(cost_amount=8.0, currency="CNY"))

    rows = db.query_all("SELECT currency, cost_amount FROM usage_snapshots ORDER BY currency")

    assert rows == [
        {"currency": "CNY", "cost_amount": 8.0},
        {"currency": "USD", "cost_amount": 12.5},
    ]


def test_ensure_provider_updates_existing_row(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.ensure_provider("openai", name="OpenAI", enabled=True, status="configured")
    db.ensure_provider("openai", name="OpenAI API", enabled=False, status="disabled")

    rows = db.query_all("SELECT name, enabled, status FROM providers WHERE id = ?", ("openai",))

    assert rows == [{"name": "OpenAI API", "enabled": 0, "status": "disabled"}]


def test_ensure_provider_uses_disabled_defaults_for_new_provider(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.ensure_provider("openai")

    rows = db.query_all("SELECT name, enabled, status FROM providers WHERE id = ?", ("openai",))

    assert rows == [{"name": "openai", "enabled": 0, "status": "disabled"}]


def test_ensure_provider_preserves_existing_fields_when_unspecified(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    db.ensure_provider("openai", name="OpenAI API", enabled=False, status="disabled")
    db.ensure_provider("openai")

    rows = db.query_all("SELECT name, enabled, status FROM providers WHERE id = ?", ("openai",))

    assert rows == [{"name": "OpenAI API", "enabled": 0, "status": "disabled"}]


def test_upsert_snapshot_rejects_naive_datetimes(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    with pytest.raises(ValueError, match="timezone-aware"):
        db.upsert_snapshot(_snapshot(period_start=datetime(2026, 5, 1)))


def test_upsert_snapshot_rejects_invalid_foundational_data(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    with pytest.raises(ValueError, match="granularity"):
        db.upsert_snapshot(_snapshot(granularity="hour"))

    with pytest.raises(ValueError, match="period_end"):
        db.upsert_snapshot(
            _snapshot(
                period_start=datetime(2026, 5, 2, tzinfo=UTC),
                period_end=datetime(2026, 5, 1, tzinfo=UTC),
            )
        )

    with pytest.raises(ValueError, match="non-negative"):
        db.upsert_snapshot(_snapshot(cost_amount=-1.0))


def test_finish_sync_run_rejects_nonexistent_run(temp_db_url):
    db = Database(temp_db_url)
    db.migrate()

    with pytest.raises(ValueError, match="No sync run found"):
        db.finish_sync_run(999, status="failed")


def _column_names(db: Database, table_name: str) -> list[str]:
    return [row["name"] for row in db.query_all(f"PRAGMA table_info({table_name})")]


def _columns_by_name(db: Database, table_name: str) -> dict[str, dict[str, object]]:
    return {row["name"]: row for row in db.query_all(f"PRAGMA table_info({table_name})")}


def _snapshot(
    *,
    provider_id: str = "openai",
    period_start: datetime = datetime(2026, 5, 1, tzinfo=UTC),
    period_end: datetime = datetime(2026, 5, 2, tzinfo=UTC),
    granularity: str = "day",
    currency: str = "USD",
    cost_amount: float | None = 12.5,
    total_tokens: int | None = 150,
    requests: int | None = 3,
) -> UsageSnapshot:
    return UsageSnapshot(
        provider_id=provider_id,
        period_start=period_start,
        period_end=period_end,
        granularity=granularity,
        currency=currency,
        cost_amount=cost_amount,
        input_tokens=100,
        output_tokens=50,
        total_tokens=total_tokens,
        requests=requests,
        quota_limit=None,
        quota_remaining=None,
        quota_reset_at=None,
        raw_summary={"source": "test"},
    )
