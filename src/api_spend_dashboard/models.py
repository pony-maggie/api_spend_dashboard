from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UsageSnapshot:
    provider_id: str
    period_start: datetime
    period_end: datetime
    granularity: str
    currency: str
    cost_amount: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    requests: int | None
    quota_limit: int | None
    quota_remaining: int | None
    quota_reset_at: datetime | None
    raw_summary: dict[str, Any]
