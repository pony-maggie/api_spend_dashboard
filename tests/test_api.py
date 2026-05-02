import importlib
import sys

from fastapi.testclient import TestClient

from api_spend_dashboard.config import Settings


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


def test_dashboard_route_loads(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "API Spend Dashboard" in response.text


def test_dashboard_contains_core_regions(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="summary-cards"' in response.text
    assert 'id="trend-chart"' in response.text
    assert 'id="trend-chart-state"' in response.text
    assert 'id="provider-grid"' in response.text


def test_summary_endpoint_returns_dashboard_shape(temp_db_url):
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"summary", "daily_costs"}
    assert set(payload["summary"]) == {
        "total_cost",
        "total_tokens",
        "total_requests",
        "provider_count",
    }
    assert isinstance(payload["daily_costs"], list)


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
