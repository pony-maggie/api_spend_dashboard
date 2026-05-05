from api_spend_dashboard.config import Settings


def test_default_settings_ignores_dotenv_in_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_ENABLED=true",
                "OPENAI_ADMIN_API_KEY=real-key-from-dotenv",
                "CHATGPT_PRO_PRICE=200",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(database_url="sqlite:///isolated.sqlite3")

    assert settings.openai_enabled is False
    assert settings.openai_admin_api_key == ""
    assert settings.chatgpt_pro_price == 0


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


def test_env_file_loading_parses_recurring_expenses(tmp_path, monkeypatch):
    monkeypatch.delenv("RECURRING_EXPENSES_ENABLED", raising=False)
    monkeypatch.delenv("RECURRING_EXPENSES", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RECURRING_EXPENSES_ENABLED=true",
                (
                    'RECURRING_EXPENSES=[{"id":"rent","name":"Rent","category":"Housing",'
                    '"amount":23500,"currency":"HKD","due_day":1,'
                    '"payment_method":"bank_transfer"},'
                    '{"id":"mobile","name":"Mobile","category":"Telecom",'
                    '"amount":177,"currency":"HKD","due_day":6}]'
                ),
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.recurring_expenses_enabled is True
    assert len(settings.recurring_expenses) == 2
    assert settings.recurring_expenses[0].id == "rent"
    assert settings.recurring_expenses[0].amount == 23500
    assert settings.recurring_expenses[0].currency == "HKD"
    assert settings.recurring_expenses[0].due_day == 1
    assert settings.recurring_expenses[0].payment_method == "bank_transfer"


def test_env_file_loading_parses_display_currency_rates(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY_CURRENCY", raising=False)
    monkeypatch.delenv("EXCHANGE_RATES_TO_DISPLAY", raising=False)
    monkeypatch.delenv("EXCHANGE_RATE_SOURCE", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DISPLAY_CURRENCY=HKD",
                'EXCHANGE_RATES_TO_DISPLAY={"HKD":1,"USD":7.8357,"RMB":1.1475}',
                "EXCHANGE_RATE_SOURCE=manual rates",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.display_currency == "HKD"
    assert settings.exchange_rates_to_display == {"HKD": 1.0, "USD": 7.8357, "RMB": 1.1475}
    assert settings.exchange_rate_source == "manual rates"
