from fastapi.testclient import TestClient

from api_spend_dashboard.config import Settings
from api_spend_dashboard.main import create_app


def test_config_status_endpoint(temp_db_url):
    app = create_app(
        Settings(
            database_url=temp_db_url,
            openai_enabled=True,
            openai_admin_api_key="",
        )
    )

    response = TestClient(app).get("/api/config/status")

    assert response.status_code == 200
    assert response.json()["openai"]["status"] == "missing_config"


def test_dashboard_route_loads(temp_db_url):
    app = create_app(Settings(database_url=temp_db_url))

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "API Spend Dashboard" in response.text
