from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from api_spend_dashboard.config import Settings


def collect_recurring_expenses(
    settings: Settings,
    year: int,
    month: int,
    *,
    today: date,
) -> list[dict[str, Any]]:
    if not settings.recurring_expenses_enabled:
        return []

    rows: list[dict[str, Any]] = []
    for expense in settings.recurring_expenses:
        if not expense.enabled:
            continue
        due_date = _due_date(year, month, expense.due_day)
        rows.append(
            {
                "id": expense.id,
                "name": expense.name,
                "category": expense.category,
                "amount": float(expense.amount),
                "currency": expense.currency.strip().upper(),
                "due_day": expense.due_day,
                "due_date": due_date.isoformat(),
                "payment_method": expense.payment_method,
                "notes": expense.notes,
                "status": _due_status(due_date, today),
            }
        )
    return rows


def merge_cost_totals(
    base_totals: list[dict[str, Any]],
    recurring_expenses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for row in base_totals:
        currency = str(row["currency"]).strip().upper()
        totals[currency] = totals.get(currency, 0.0) + float(row["cost"] or 0)
    for row in recurring_expenses:
        currency = str(row["currency"]).strip().upper()
        totals[currency] = totals.get(currency, 0.0) + float(row["amount"] or 0)
    return [{"currency": currency, "cost": cost} for currency, cost in sorted(totals.items())]


def recurring_expense_breakdown_rows(
    recurring_expenses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "source_type": "recurring_expense",
            "expense_id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "currency": row["currency"],
            "cost": row["amount"],
            "cost_available": 1,
            "cost_basis": "recurring",
            "due_date": row["due_date"],
        }
        for row in recurring_expenses
    ]


def single_currency_total(currency_totals: list[dict[str, Any]]) -> float | int | None:
    if not currency_totals:
        return 0
    if len(currency_totals) == 1:
        return currency_totals[0]["cost"]
    return None


def _due_date(year: int, month: int, due_day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(due_day, last_day))


def _due_status(due_date: date, today: date) -> str:
    if due_date < today:
        return "due_passed"
    if due_date == today:
        return "due_today"
    return "upcoming"
