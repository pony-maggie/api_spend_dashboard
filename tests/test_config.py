from api_spend_dashboard.config import Settings


def test_provider_missing_config_is_reported(temp_db_url):
    settings = Settings(
        database_url=temp_db_url,
        openai_enabled=True,
        openai_admin_api_key="",
        minimax_enabled=True,
        minimax_api_key="sk-minimax",
    )

    statuses = settings.provider_config_status()

    assert statuses["openai"]["status"] == "missing_config"
    assert statuses["openai"]["missing"] == ["OPENAI_ADMIN_API_KEY"]
    assert statuses["minimax"]["status"] == "configured"
    assert statuses["minimax"]["missing"] == []


def test_disabled_provider_is_not_missing_config(temp_db_url):
    settings = Settings(database_url=temp_db_url, brave_enabled=False, brave_api_key="")

    statuses = settings.provider_config_status()

    assert statuses["brave"]["status"] == "disabled"
    assert statuses["brave"]["missing"] == []
