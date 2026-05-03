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
            WITH providers_with_daily AS (
                SELECT DISTINCT provider_id
                FROM usage_snapshots
                WHERE
                    period_start >= ?
                    AND period_start < ?
                    AND granularity = 'day'
            ),
            selected_snapshots AS (
                SELECT *
                FROM usage_snapshots
                WHERE
                    period_start >= ?
                    AND period_start < ?
                    AND (
                        granularity = 'day'
                        OR (
                            granularity = 'month'
                            AND provider_id NOT IN (SELECT provider_id FROM providers_with_daily)
                        )
                    )
            )
            SELECT
                COALESCE(SUM(cost_amount), 0) AS total_cost,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(requests), 0) AS total_requests,
                COUNT(DISTINCT provider_id) AS provider_count
            FROM selected_snapshots
            """,
            (
                self._dt_to_iso(start),
                self._dt_to_iso(end),
                self._dt_to_iso(start),
                self._dt_to_iso(end),
            ),
        )
        row = rows[0]
        return {
            "total_cost": row["total_cost"],
            "total_tokens": row["total_tokens"],
            "total_requests": row["total_requests"],
            "provider_count": row["provider_count"],
        }

    def daily_costs(self, days: int = 30) -> list[dict[str, Any]]:
        start_date = datetime.now(UTC).date() - timedelta(days=days)
        return self.db.query_all(
            """
            SELECT
                date(period_start) AS date,
                provider_id,
                COALESCE(SUM(cost_amount), 0) AS cost
            FROM usage_snapshots
            WHERE date(period_start) >= ? AND granularity = 'day'
            GROUP BY date(period_start), provider_id
            ORDER BY date(period_start), provider_id
            """,
            (start_date.isoformat(),),
        )

    def month_provider_totals(self, year: int, month: int) -> list[dict[str, Any]]:
        start = datetime(year, month, 1, tzinfo=UTC)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month + 1, 1, tzinfo=UTC)

        return self.db.query_all(
            """
            WITH providers_with_daily AS (
                SELECT DISTINCT provider_id
                FROM usage_snapshots
                WHERE
                    period_start >= ?
                    AND period_start < ?
                    AND granularity = 'day'
            ),
            selected_snapshots AS (
                SELECT *
                FROM usage_snapshots
                WHERE
                    period_start >= ?
                    AND period_start < ?
                    AND (
                        granularity = 'day'
                        OR (
                            granularity = 'month'
                            AND provider_id NOT IN (SELECT provider_id FROM providers_with_daily)
                        )
                    )
            )
            SELECT
                provider_id,
                currency,
                COALESCE(SUM(cost_amount), 0) AS cost,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(requests), 0) AS total_requests
            FROM selected_snapshots
            GROUP BY provider_id, currency
            ORDER BY provider_id, currency
            """,
            (
                self._dt_to_iso(start),
                self._dt_to_iso(end),
                self._dt_to_iso(start),
                self._dt_to_iso(end),
            ),
        )

    @staticmethod
    def _dt_to_iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()
