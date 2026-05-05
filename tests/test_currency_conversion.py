from api_spend_dashboard.services.currency_conversion import convert_cost_totals


def test_convert_cost_totals_returns_unified_display_total():
    result = convert_cost_totals(
        [
            {"currency": "HKD", "cost": 23775.0},
            {"currency": "RMB", "cost": 1190.0},
            {"currency": "USD", "cost": 201.93},
        ],
        display_currency="HKD",
        exchange_rates={"HKD": 1, "RMB": 1.1475, "USD": 7.8357},
        source="manual rates",
    )

    assert result == {
        "currency": "HKD",
        "amount": 26722.787901,
        "source": "manual rates",
        "rates": {"HKD": 1.0, "RMB": 1.1475, "USD": 7.8357},
        "items": [
            {
                "currency": "HKD",
                "original_cost": 23775.0,
                "rate": 1.0,
                "converted_cost": 23775.0,
            },
            {
                "currency": "RMB",
                "original_cost": 1190.0,
                "rate": 1.1475,
                "converted_cost": 1365.525,
            },
            {
                "currency": "USD",
                "original_cost": 201.93,
                "rate": 7.8357,
                "converted_cost": 1582.262901,
            },
        ],
    }


def test_convert_cost_totals_reports_missing_rates():
    result = convert_cost_totals(
        [{"currency": "USD", "cost": 10.0}],
        display_currency="HKD",
        exchange_rates={"HKD": 1},
        source="manual rates",
    )

    assert result["amount"] is None
    assert result["missing_rates"] == ["USD"]
