from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
ROLLOUT_DATE_RE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T")


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def collect_codex_token_usage(codex_home: Path | None = None) -> dict[str, Any]:
    home = (codex_home or default_codex_home()).expanduser()
    rollout_files = list(_rollout_files(home))
    totals = {field: 0 for field in TOKEN_FIELDS}
    daily_totals: dict[str, dict[str, int | str]] = {}
    session_count = 0
    last_modified_at: str | None = None

    for path in rollout_files:
        max_usage = _max_token_usage(path)
        last_modified_at = _latest_iso_mtime(last_modified_at, path)
        if max_usage is None:
            continue

        usage, event_timestamp = max_usage
        usage_date = _usage_date(path, event_timestamp)
        session_count += 1
        for field in TOKEN_FIELDS:
            totals[field] += _int_value(usage.get(field))
        _add_daily_usage(daily_totals, usage_date, usage)

    return {
        "available": bool(rollout_files),
        "codex_home": str(home),
        "files_scanned": len(rollout_files),
        "session_count": session_count,
        **totals,
        "daily_token_usage": _daily_rows(daily_totals),
        "last_modified_at": last_modified_at,
    }


def _rollout_files(codex_home: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in ("sessions", "archived_sessions"):
        directory = codex_home / dirname
        if directory.exists():
            files.extend(path for path in directory.rglob("rollout-*.jsonl") if path.is_file())
    return sorted(files)


def _max_token_usage(path: Path) -> tuple[dict[str, Any], str | None] | None:
    usages: list[tuple[dict[str, Any], str | None]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                event = _json_line(line)
                if event is None:
                    continue
                usage = _token_usage_from_event(event)
                if usage is not None:
                    timestamp = event.get("timestamp")
                    usages.append((usage, timestamp if isinstance(timestamp, str) else None))
    except OSError:
        return None

    if not usages:
        return None
    return max(usages, key=lambda item: _int_value(item[0].get("total_tokens")))


def _json_line(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _token_usage_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    usage = info.get("total_token_usage")
    return usage if isinstance(usage, dict) else None


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_date(path: Path, event_timestamp: str | None) -> str:
    filename_match = ROLLOUT_DATE_RE.search(path.name)
    if filename_match:
        return filename_match.group(1)
    if event_timestamp and re.match(r"^\d{4}-\d{2}-\d{2}", event_timestamp):
        return event_timestamp[:10]
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).date().isoformat()
    except OSError:
        return "unknown"


def _add_daily_usage(
    daily_totals: dict[str, dict[str, int | str]],
    usage_date: str,
    usage: dict[str, Any],
) -> None:
    row = daily_totals.setdefault(
        usage_date,
        {
            "date": usage_date,
            "session_count": 0,
            **{field: 0 for field in TOKEN_FIELDS},
        },
    )
    row["session_count"] = int(row["session_count"]) + 1
    for field in TOKEN_FIELDS:
        row[field] = int(row[field]) + _int_value(usage.get(field))


def _daily_rows(daily_totals: dict[str, dict[str, int | str]]) -> list[dict[str, int | str]]:
    return [daily_totals[date] for date in sorted(daily_totals, reverse=True)]


def _latest_iso_mtime(current: str | None, path: Path) -> str | None:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return current
    if current is None or mtime > current:
        return mtime
    return current
