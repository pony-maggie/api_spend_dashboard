import json
from pathlib import Path

from api_spend_dashboard.services.codex_usage import collect_codex_token_usage


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def token_count(total: dict[str, int], timestamp: str | None = None) -> dict:
    event = {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": total,
            },
        },
    }
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event


def test_collect_codex_token_usage_sums_max_token_count_per_rollout_file(tmp_path):
    codex_home = tmp_path / "codex"
    write_jsonl(
        codex_home / "sessions" / "2026" / "05" / "01" / "rollout-2026-05-01T10-00-00-one.jsonl",
        [
            {"type": "event_msg", "payload": {"type": "other"}},
            token_count(
                {
                    "input_tokens": 3,
                    "cached_input_tokens": 1,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 6,
                },
                timestamp="2026-05-01T02:00:00Z",
            ),
            token_count(
                {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 3,
                    "total_tokens": 20,
                },
                timestamp="2026-05-01T02:03:00Z",
            ),
        ],
    )
    write_jsonl(
        codex_home / "archived_sessions" / "2026" / "05" / "02" / "rollout-2026-05-02T12-00-00-two.jsonl",
        [
            token_count(
                {
                    "input_tokens": 1,
                    "output_tokens": 3,
                    "total_tokens": 4,
                },
                timestamp="2026-05-02T04:00:00Z",
            )
        ],
    )
    write_jsonl(codex_home / "sessions" / "rollout-empty.jsonl", [{"type": "noop"}])

    usage = collect_codex_token_usage(codex_home)

    assert usage == {
        "available": True,
        "codex_home": str(codex_home),
        "files_scanned": 3,
        "session_count": 2,
        "input_tokens": 11,
        "cached_input_tokens": 2,
        "output_tokens": 8,
        "reasoning_output_tokens": 3,
        "total_tokens": 24,
        "daily_token_usage": [
            {
                "date": "2026-05-02",
                "session_count": 1,
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 3,
                "reasoning_output_tokens": 0,
                "total_tokens": 4,
            },
            {
                "date": "2026-05-01",
                "session_count": 1,
                "input_tokens": 10,
                "cached_input_tokens": 2,
                "output_tokens": 5,
                "reasoning_output_tokens": 3,
                "total_tokens": 20,
            },
        ],
        "last_modified_at": usage["last_modified_at"],
    }
    assert usage["last_modified_at"] is not None


def test_collect_codex_token_usage_handles_missing_session_directories(tmp_path):
    usage = collect_codex_token_usage(tmp_path / "missing-codex")

    assert usage == {
        "available": False,
        "codex_home": str(tmp_path / "missing-codex"),
        "files_scanned": 0,
        "session_count": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
        "daily_token_usage": [],
        "last_modified_at": None,
    }


def test_collect_codex_token_usage_uses_rollout_filename_date_for_daily_totals(tmp_path):
    codex_home = tmp_path / "codex"
    write_jsonl(
        codex_home / "sessions" / "rollout-2026-05-03T00-15-00-cross-midnight.jsonl",
        [
            token_count(
                {
                    "input_tokens": 2,
                    "cached_input_tokens": 1,
                    "output_tokens": 1,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 3,
                },
                timestamp="2026-05-02T16:15:00Z",
            )
        ],
    )

    usage = collect_codex_token_usage(codex_home)

    assert usage["daily_token_usage"] == [
        {
            "date": "2026-05-03",
            "session_count": 1,
            "input_tokens": 2,
            "cached_input_tokens": 1,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
            "total_tokens": 3,
        }
    ]
