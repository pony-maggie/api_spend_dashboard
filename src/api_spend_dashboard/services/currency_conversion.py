from __future__ import annotations

from typing import Any


def convert_cost_totals(
    cost_totals: list[dict[str, Any]],
    *,
    display_currency: str,
    exchange_rates: dict[str, float],
    source: str,
) -> dict[str, Any]:
    normalized_display_currency = display_currency.strip().upper()
    normalized_rates = {
        currency.strip().upper(): float(rate) for currency, rate in exchange_rates.items()
    }
    normalized_rates.setdefault(normalized_display_currency, 1.0)

    items: list[dict[str, Any]] = []
    missing_rates: list[str] = []
    total = 0.0

    for row in cost_totals:
        currency = str(row["currency"]).strip().upper()
        original_cost = float(row["cost"] or 0)
        rate = normalized_rates.get(currency)
        if rate is None:
            missing_rates.append(currency)
            continue

        converted_cost = round(original_cost * rate, 6)
        total += converted_cost
        items.append(
            {
                "currency": currency,
                "original_cost": original_cost,
                "rate": rate,
                "converted_cost": converted_cost,
            }
        )

    result = {
        "currency": normalized_display_currency,
        "amount": None if missing_rates else round(total, 6),
        "source": source,
        "rates": normalized_rates,
        "items": items,
    }
    if missing_rates:
        result["missing_rates"] = sorted(set(missing_rates))
    return result
