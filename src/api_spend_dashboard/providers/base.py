from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from api_spend_dashboard.models import UsageSnapshot


class ProviderSyncError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


@dataclass(frozen=True)
class SyncResult:
    provider_id: str
    snapshots: list[UsageSnapshot]
    status_message: str


class ProviderConnector(Protocol):
    provider_id: str
    display_name: str

    async def sync(self, now: datetime) -> SyncResult:
        ...
