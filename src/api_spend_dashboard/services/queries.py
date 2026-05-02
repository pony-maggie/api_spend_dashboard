from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from api_spend_dashboard.db import Database


class DashboardQueries:
    def __init__(self, db: Database) -> None:
        self.db = db

    def month_summary(self, year: int, month: int) -> dict[str, Any]:
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)

        rows = self.db.query_all(
            """
            SELECT
                COALESCE(SUM(cost_amount), 0) AS total_cost,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(requests), 0) AS total_requests,
                COUNT(DISTINCT provider_id) AS provider_count
            FROM usage_snapshots
            WHERE period_start >= ? AND period_start < ?
            """,
            (self._dt_to_iso(start), self._dt_to_iso(end)),
        )
        row = rows[0]
        return {
            "total_cost": row["total_cost"],
            "total_tokens": row["total_tokens"],
            "total_requests": row["total_requests"],
            "provider_count": row["provider_count"],
        }

    def daily_costs(self, days: int = 30) -> list[dict[str, Any]]:
        start = datetime.now(UTC) - timedelta(days=days)
        return self.db.query_all(
            """
            SELECT
                date(period_start) AS date,
                provider_id,
                COALESCE(SUM(cost_amount), 0) AS cost
            FROM usage_snapshots
            WHERE period_start >= ?
            GROUP BY date(period_start), provider_id
            ORDER BY date(period_start), provider_id
            """,
            (self._dt_to_iso(start),),
        )

    @staticmethod
    def _dt_to_iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()
