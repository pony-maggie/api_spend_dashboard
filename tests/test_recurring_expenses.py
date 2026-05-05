from datetime import date

from api_spend_dashboard.config import RecurringExpenseConfig, Settings
from api_spend_dashboard.services.recurring_expenses import (
    collect_recurring_expenses,
    merge_cost_totals,
)


def test_collect_recurring_expenses_builds_current_month_rows():
    settings = Settings(
        recurring_expenses_enabled=True,
        recurring_expenses=[
            RecurringExpenseConfig(
                id="rent",
                name="Rent",
                category="Housing",
                amount=23500,
                currency="hkd",
                due_day=1,
                payment_method="bank_transfer",
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
    )

    rows = collect_recurring_expenses(settings, 2026, 5, today=date(2026, 5, 5))

    assert rows == [
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


def test_collect_recurring_expenses_clamps_due_day_to_month_end():
    settings = Settings(
        recurring_expenses_enabled=True,
        recurring_expenses=[
            RecurringExpenseConfig(
                id="billing",
                name="Billing",
                category="Test",
                amount=10,
                currency="HKD",
                due_day=31,
            )
        ],
    )

    rows = collect_recurring_expenses(settings, 2026, 2, today=date(2026, 2, 28))

    assert rows[0]["due_date"] == "2026-02-28"
    assert rows[0]["status"] == "due_today"


def test_merge_cost_totals_adds_recurring_expenses_by_currency():
    merged = merge_cost_totals(
        [
            {"currency": "RMB", "cost": 1190.0},
            {"currency": "USD", "cost": 201.93},
        ],
        [
            {"currency": "HKD", "amount": 23500.0},
            {"currency": "HKD", "amount": 177.0},
            {"currency": "HKD", "amount": 98.0},
        ],
    )

    assert merged == [
        {"currency": "HKD", "cost": 23775.0},
        {"currency": "RMB", "cost": 1190.0},
        {"currency": "USD", "cost": 201.93},
    ]
