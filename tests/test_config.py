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


def test_chatgpt_pro_requires_positive_price(temp_db_url):
    settings = Settings(database_url=temp_db_url, chatgpt_pro_enabled=True, chatgpt_pro_price=0)

    statuses = settings.provider_config_status()

    assert statuses["chatgpt_pro"]["status"] == "missing_config"
    assert statuses["chatgpt_pro"]["missing"] == ["CHATGPT_PRO_PRICE"]


def test_env_file_loading_parses_booleans_and_reports_missing_config(tmp_path, monkeypatch):
    for key in (
        "DATABASE_URL",
        "OPENAI_ENABLED",
        "OPENAI_ADMIN_API_KEY",
        "BRAVE_ENABLED",
        "BRAVE_API_KEY",
        "CHATGPT_PRO_ENABLED",
        "CHATGPT_PRO_PRICE",
    ):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=sqlite:///env.sqlite3",
                "OPENAI_ENABLED=true",
                "OPENAI_ADMIN_API_KEY=",
                "BRAVE_ENABLED=false",
                "BRAVE_API_KEY=",
                "CHATGPT_PRO_ENABLED=true",
                "CHATGPT_PRO_PRICE=0",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    statuses = settings.provider_config_status()

    assert settings.database_url == "sqlite:///env.sqlite3"
    assert settings.openai_enabled is True
    assert settings.brave_enabled is False
    assert statuses["openai"]["status"] == "missing_config"
    assert statuses["openai"]["missing"] == ["OPENAI_ADMIN_API_KEY"]
    assert statuses["brave"]["status"] == "disabled"
    assert statuses["chatgpt_pro"]["status"] == "missing_config"
    assert statuses["chatgpt_pro"]["missing"] == ["CHATGPT_PRO_PRICE"]
