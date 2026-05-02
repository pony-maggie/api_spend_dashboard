from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from api_spend_dashboard.models import UsageSnapshot


class Database:
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
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL REFERENCES providers(id),
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT
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
                    UNIQUE (provider_id, period_start, period_end, granularity)
                );

                CREATE TABLE IF NOT EXISTS manual_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL REFERENCES providers(id),
                    label TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def ensure_provider(self, provider_id: str, display_name: str | None = None) -> None:
        now = self._dt_to_iso(datetime.now(UTC))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO providers (id, display_name, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (provider_id, display_name or provider_id, now),
            )

    def upsert_snapshot(self, snapshot: UsageSnapshot) -> None:
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
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, error_type = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    self._dt_to_iso(datetime.now(UTC)),
                    status,
                    error_type,
                    error_message,
                    run_id,
                ),
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

    @staticmethod
    def _dt_to_iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
