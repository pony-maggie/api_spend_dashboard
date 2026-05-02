from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from api_spend_dashboard.models import UsageSnapshot


class Database:
    PROVIDER_STATUSES = {"unknown", "configured", "missing_config", "disabled", "error"}
    SYNC_RUN_STATUSES = {"running", "succeeded", "failed"}
    SNAPSHOT_GRANULARITIES = {"day", "month"}

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = self._sqlite_path(database_url)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_sync_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (length(trim(id)) > 0),
                    CHECK (length(trim(name)) > 0),
                    CHECK (enabled IN (0, 1)),
                    CHECK (status IN ('unknown', 'configured', 'missing_config', 'disabled', 'error'))
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL REFERENCES providers(id),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    snapshots_written INTEGER NOT NULL DEFAULT 0,
                    CHECK (length(trim(provider_id)) > 0),
                    CHECK (status IN ('running', 'succeeded', 'failed')),
                    CHECK (snapshots_written >= 0)
                );

                CREATE TABLE IF NOT EXISTS usage_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL REFERENCES providers(id),
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    granularity TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    cost_amount REAL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    requests INTEGER,
                    quota_limit INTEGER,
                    quota_remaining INTEGER,
                    quota_reset_at TEXT,
                    raw_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (provider_id, period_start, period_end, granularity),
                    CHECK (length(trim(provider_id)) > 0),
                    CHECK (period_end > period_start),
                    CHECK (granularity IN ('day', 'month')),
                    CHECK (length(trim(currency)) > 0),
                    CHECK (cost_amount IS NULL OR cost_amount >= 0),
                    CHECK (input_tokens IS NULL OR input_tokens >= 0),
                    CHECK (output_tokens IS NULL OR output_tokens >= 0),
                    CHECK (total_tokens IS NULL OR total_tokens >= 0),
                    CHECK (requests IS NULL OR requests >= 0),
                    CHECK (quota_limit IS NULL OR quota_limit >= 0),
                    CHECK (quota_remaining IS NULL OR quota_remaining >= 0)
                );

                CREATE TABLE IF NOT EXISTS manual_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL REFERENCES providers(id),
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    billing_period TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    renewal_date TEXT,
                    notes TEXT,
                    CHECK (length(trim(provider_id)) > 0),
                    CHECK (length(trim(name)) > 0),
                    CHECK (amount >= 0),
                    CHECK (length(trim(currency)) > 0),
                    CHECK (
                        billing_period IN ('daily', 'weekly', 'monthly', 'annual', 'yearly', 'one_time')
                    )
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def ensure_provider(
        self,
        provider_id: str,
        name: str | None = None,
        *,
        enabled: bool | None = None,
        status: str | None = None,
    ) -> None:
        if not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if name is not None and not name.strip():
            raise ValueError("provider name must be non-empty")
        if status is not None and status not in self.PROVIDER_STATUSES:
            raise ValueError(f"provider status must be one of {sorted(self.PROVIDER_STATUSES)}")

        now = self._dt_to_iso(datetime.now(UTC))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO providers (id, name, enabled, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = CASE WHEN ? THEN excluded.name ELSE providers.name END,
                    enabled = COALESCE(?, providers.enabled),
                    status = COALESCE(?, providers.status),
                    updated_at = excluded.updated_at
                """,
                (
                    provider_id,
                    name or provider_id,
                    int(enabled) if enabled is not None else 1,
                    status or "unknown",
                    now,
                    now,
                    name is not None,
                    int(enabled) if enabled is not None else None,
                    status,
                ),
            )

    def upsert_snapshot(self, snapshot: UsageSnapshot) -> None:
        self._validate_snapshot(snapshot)
        self.ensure_provider(snapshot.provider_id)
        now = self._dt_to_iso(datetime.now(UTC))
        values = (
            snapshot.provider_id,
            self._dt_to_iso(snapshot.period_start),
            self._dt_to_iso(snapshot.period_end),
            snapshot.granularity,
            snapshot.currency,
            snapshot.cost_amount,
            snapshot.input_tokens,
            snapshot.output_tokens,
            snapshot.total_tokens,
            snapshot.requests,
            snapshot.quota_limit,
            snapshot.quota_remaining,
            self._optional_dt_to_iso(snapshot.quota_reset_at),
            json.dumps(snapshot.raw_summary, sort_keys=True),
            now,
            now,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_snapshots (
                    provider_id,
                    period_start,
                    period_end,
                    granularity,
                    currency,
                    cost_amount,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    requests,
                    quota_limit,
                    quota_remaining,
                    quota_reset_at,
                    raw_summary,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, period_start, period_end, granularity)
                DO UPDATE SET
                    currency = excluded.currency,
                    cost_amount = excluded.cost_amount,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    total_tokens = excluded.total_tokens,
                    requests = excluded.requests,
                    quota_limit = excluded.quota_limit,
                    quota_remaining = excluded.quota_remaining,
                    quota_reset_at = excluded.quota_reset_at,
                    raw_summary = excluded.raw_summary,
                    updated_at = excluded.updated_at
                """,
                values,
            )

    def start_sync_run(self, provider_id: str) -> int:
        self.ensure_provider(provider_id)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (provider_id, started_at, status)
                VALUES (?, ?, ?)
                """,
                (provider_id, self._dt_to_iso(datetime.now(UTC)), "running"),
            )
            return int(cursor.lastrowid)

    def finish_sync_run(
        self,
        run_id: int,
        *,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        snapshots_written: int = 0,
    ) -> None:
        if status not in self.SYNC_RUN_STATUSES - {"running"}:
            raise ValueError("finished sync run status must be 'succeeded' or 'failed'")
        if snapshots_written < 0:
            raise ValueError("snapshots_written must be non-negative")

        finished_at = self._dt_to_iso(datetime.now(UTC))
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sync_runs
                SET
                    finished_at = ?,
                    status = ?,
                    error_type = ?,
                    error_message = ?,
                    snapshots_written = ?
                WHERE id = ?
                """,
                (
                    finished_at,
                    status,
                    error_type,
                    error_message,
                    snapshots_written,
                    run_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"No sync run found for id {run_id}")

            if status == "succeeded":
                conn.execute(
                    """
                    UPDATE providers
                    SET
                        last_sync_at = ?,
                        last_success_at = ?,
                        last_error = NULL,
                        status = 'configured',
                        updated_at = ?
                    WHERE id = (SELECT provider_id FROM sync_runs WHERE id = ?)
                    """,
                    (finished_at, finished_at, finished_at, run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE providers
                    SET
                        last_sync_at = ?,
                        last_error = ?,
                        status = 'error',
                        updated_at = ?
                    WHERE id = (SELECT provider_id FROM sync_runs WHERE id = ?)
                    """,
                    (finished_at, error_message, finished_at, run_id),
                )

    def recent_sync_runs(self, provider_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if provider_id is not None:
            where = "WHERE provider_id = ?"
            params.append(provider_id)
        params.append(limit)

        return self.query_all(
            f"""
            SELECT *
            FROM sync_runs
            {where}
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            params,
        )

    def query_all(self, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _sqlite_path(database_url: str) -> Path:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// database URLs are supported")
        raw_path = unquote(database_url[len(prefix) :])
        if not raw_path:
            raise ValueError("SQLite database URL must include a path")
        return Path(raw_path)

    @classmethod
    def _optional_dt_to_iso(cls, value: datetime | None) -> str | None:
        if value is None:
            return None
        return cls._dt_to_iso(value)

    def _validate_snapshot(self, snapshot: UsageSnapshot) -> None:
        if not snapshot.provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if not snapshot.currency.strip():
            raise ValueError("currency must be non-empty")
        if snapshot.granularity not in self.SNAPSHOT_GRANULARITIES:
            raise ValueError(f"granularity must be one of {sorted(self.SNAPSHOT_GRANULARITIES)}")

        period_start = self._require_aware_datetime("period_start", snapshot.period_start)
        period_end = self._require_aware_datetime("period_end", snapshot.period_end)
        self._optional_dt_to_iso(snapshot.quota_reset_at)

        if period_end <= period_start:
            raise ValueError("period_end must be after period_start")

        numeric_fields = {
            "cost_amount": snapshot.cost_amount,
            "input_tokens": snapshot.input_tokens,
            "output_tokens": snapshot.output_tokens,
            "total_tokens": snapshot.total_tokens,
            "requests": snapshot.requests,
            "quota_limit": snapshot.quota_limit,
            "quota_remaining": snapshot.quota_remaining,
        }
        for field_name, value in numeric_fields.items():
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    @classmethod
    def _require_aware_datetime(cls, field_name: str, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _dt_to_iso(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat()
