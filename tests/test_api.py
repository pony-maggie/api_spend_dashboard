import importlib
import json
import sys
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api_spend_dashboard.config import RecurringExpenseConfig, Settings


def test_importing_create_app_has_no_default_database_side_effect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("api_spend_dashboard.main", None)

    main = importlib.import_module("api_spend_dashboard.main")

    assert callable(main.create_app)
    assert not (tmp_path / "data" / "api_spend.sqlite3").exists()


def test_config_status_endpoint(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(
        Settings(
            database_url=temp_db_url,
            openai_enabled=True,
            openai_admin_api_key="",
        ),
        start_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/config/status")

    assert response.status_code == 200
    assert response.json()["openai"]["status"] == "missing_config"


def test_config_status_endpoint_includes_persisted_provider_error(temp_db_url):
    from api_spend_dashboard.db import Database
    from api_spend_dashboard.main import create_app

    db = Database(temp_db_url)
    db.migrate()
    run_id = db.start_sync_run("openai")
    db.finish_sync_run(
        run_id,
        status="failed",
        error_type="auth_error",
        error_message="bad key",
    )

    app = create_app(
        Settings(
            database_url=temp_db_url,
            openai_enabled=True,
            openai_admin_api_key="sk-configured",
        ),
        start_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/config/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openai"]["status"] == "error"
    assert payload["openai"]["missing"] == []
    assert payload["openai"]["last_sync_at"]
    assert payload["openai"]["last_success_at"] is None
    assert payload["openai"]["last_error"] == "bad key"


def test_dashboard_route_loads(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Spend Dashboard" in response.text
    assert "API Spend Dashboard" not in response.text


def test_dashboard_contains_core_regions(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="summary-cards"' in response.text
    assert 'id="codex-token-summary"' in response.text
    assert 'id="codex-daily-usage"' in response.text
    assert 'id="trend-chart"' in response.text
    assert 'id="trend-chart-state"' in response.text
    assert 'id="provider-grid"' in response.text
    assert 'id="recurring-expenses"' in response.text


def test_dashboard_places_codex_token_region_after_providers(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text.index('id="provider-grid"') < response.text.index('id="codex-token-summary"')


def test_summary_endpoint_returns_dashboard_shape(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "summary",
        "daily_costs",
        "provider_totals",
        "month_cost_breakdown",
        "recurring_expenses",
    }
    assert set(payload["summary"]) == {
        "total_cost",
        "cost_totals_by_currency",
        "total_tokens",
        "total_requests",
        "provider_count",
        "recurring_expense_count",
        "converted_total",
    }
    assert isinstance(payload["daily_costs"], list)
    assert isinstance(payload["provider_totals"], list)
    assert isinstance(payload["month_cost_breakdown"], list)
    assert isinstance(payload["recurring_expenses"], list)


def test_summary_endpoint_includes_month_cost_breakdown(temp_db_url):
    from api_spend_dashboard.db import Database
    from api_spend_dashboard.main import create_app
    from api_spend_dashboard.models import UsageSnapshot

    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(
        UsageSnapshot(
            provider_id="chatgpt_pro",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 1, tzinfo=UTC),
            granularity="month",
            currency="USD",
            cost_amount=200.0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={},
        )
    )

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["month_cost_breakdown"] == [
        {
            "provider_id": "chatgpt_pro",
            "currency": "USD",
            "cost": 200.0,
            "cost_available": 1,
            "cost_basis": "month_snapshot",
        }
    ]


def test_summary_endpoint_merges_recurring_expenses_into_month_spend(temp_db_url):
    from api_spend_dashboard.db import Database
    from api_spend_dashboard.main import create_app
    from api_spend_dashboard.models import UsageSnapshot

    db = Database(temp_db_url)
    db.migrate()
    db.upsert_snapshot(
        UsageSnapshot(
            provider_id="chatgpt_pro",
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 1, tzinfo=UTC),
            granularity="month",
            currency="USD",
            cost_amount=200.0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            requests=None,
            quota_limit=None,
            quota_remaining=None,
            quota_reset_at=None,
            raw_summary={},
        )
    )

    app = create_app(
        Settings(
            database_url=temp_db_url,
            recurring_expenses_enabled=True,
            recurring_expenses=[
                RecurringExpenseConfig(
                    id="rent",
                    name="Rent",
                    category="Housing",
                    amount=23500,
                    currency="HKD",
                    due_day=1,
                    payment_method="bank_transfer",
                ),
                RecurringExpenseConfig(
                    id="mobile",
                    name="Mobile",
                    category="Telecom",
                    amount=177,
                    currency="HKD",
                    due_day=6,
                ),
                RecurringExpenseConfig(
                    id="internet",
                    name="Internet",
                    category="Utilities",
                    amount=98,
                    currency="HKD",
                    due_day=26,
                ),
            ],
            display_currency="HKD",
            exchange_rates_to_display={"HKD": 1, "USD": 7.8357},
            exchange_rate_source="manual rates",
        ),
        start_scheduler=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_cost"] is None
    assert payload["summary"]["cost_totals_by_currency"] == [
        {"currency": "HKD", "cost": 23775.0},
        {"currency": "USD", "cost": 200.0},
    ]
    assert payload["summary"]["converted_total"] == {
        "currency": "HKD",
        "amount": 25342.14,
        "source": "manual rates",
        "rates": {"HKD": 1.0, "USD": 7.8357},
        "items": [
            {
                "currency": "HKD",
                "original_cost": 23775.0,
                "rate": 1.0,
                "converted_cost": 23775.0,
            },
            {
                "currency": "USD",
                "original_cost": 200.0,
                "rate": 7.8357,
                "converted_cost": 1567.14,
            },
        ],
    }
    assert payload["summary"]["recurring_expense_count"] == 3
    assert payload["recurring_expenses"] == [
        {
            "id": "rent",
            "name": "Rent",
            "category": "Housing",
            "amount": 23500.0,
            "currency": "HKD",
            "due_day": 1,
            "due_date": "2026-05-01",
            "payment_method": "bank_transfer",
            "notes": "",
            "status": "due_passed",
        },
        {
            "id": "mobile",
            "name": "Mobile",
            "category": "Telecom",
            "amount": 177.0,
            "currency": "HKD",
            "due_day": 6,
            "due_date": "2026-05-06",
            "payment_method": "",
            "notes": "",
            "status": "upcoming",
        },
        {
            "id": "internet",
            "name": "Internet",
            "category": "Utilities",
            "amount": 98.0,
            "currency": "HKD",
            "due_day": 26,
            "due_date": "2026-05-26",
            "payment_method": "",
            "notes": "",
            "status": "upcoming",
        },
    ]
    assert payload["month_cost_breakdown"][-3:] == [
        {
            "source_type": "recurring_expense",
            "expense_id": "rent",
            "name": "Rent",
            "category": "Housing",
            "currency": "HKD",
            "cost": 23500.0,
            "cost_available": 1,
            "cost_basis": "recurring",
            "due_date": "2026-05-01",
        },
        {
            "source_type": "recurring_expense",
            "expense_id": "mobile",
            "name": "Mobile",
            "category": "Telecom",
            "currency": "HKD",
            "cost": 177.0,
            "cost_available": 1,
            "cost_basis": "recurring",
            "due_date": "2026-05-06",
        },
        {
            "source_type": "recurring_expense",
            "expense_id": "internet",
            "name": "Internet",
            "category": "Utilities",
            "currency": "HKD",
            "cost": 98.0,
            "cost_available": 1,
            "cost_basis": "recurring",
            "due_date": "2026-05-26",
        },
    ]


def test_codex_tokens_endpoint_returns_local_usage(temp_db_url, tmp_path, monkeypatch):
    from api_spend_dashboard.main import create_app

    codex_home = tmp_path / "codex"
    rollout = codex_home / "sessions" / "rollout-2026-05-04T09-00-00-api.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 5,
                            "cached_input_tokens": 2,
                            "output_tokens": 7,
                            "reasoning_output_tokens": 3,
                            "total_tokens": 17,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/codex/tokens")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_count"] == 1
    assert payload["total_tokens"] == 17
    assert payload["daily_token_usage"] == [
        {
            "date": "2026-05-04",
            "session_count": 1,
            "input_tokens": 5,
            "cached_input_tokens": 2,
            "output_tokens": 7,
            "reasoning_output_tokens": 3,
            "total_tokens": 17,
        }
    ]
    assert "files" not in payload


def test_static_dashboard_assets_are_served(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        js_response = client.get("/static/app.js")
        css_response = client.get("/static/app.css")

    assert js_response.status_code == 200
    assert "function loadDashboard" in js_response.text
    assert css_response.status_code == 200
    assert ".app-shell" in css_response.text


def test_sync_endpoint_returns_noop_when_no_providers_are_configured(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.post("/api/sync")

    assert response.status_code == 200
    assert response.json() == {"sync": {"status": "completed"}, "providers": {}}


def test_scheduler_opt_out_does_not_start_background_sync(temp_db_url):
    from api_spend_dashboard.db import Database
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app):
        assert not hasattr(app.state, "scheduler")

    assert Database(temp_db_url).recent_sync_runs() == []
