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


def test_scheduler_opt_out_does_not_start_background_sync(temp_db_url):
    from api_spend_dashboard.db import Database
    from api_spend_dashboard.main import create_app

    app = create_app(Settings(database_url=temp_db_url), start_scheduler=False)

    with TestClient(app):
        assert not hasattr(app.state, "scheduler")

    assert Database(temp_db_url).recent_sync_runs() == []
