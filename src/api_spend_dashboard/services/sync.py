from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from api_spend_dashboard.config import Settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.providers.base import ProviderConnector, ProviderSyncError


PROVIDER_NAMES = {
    "openai": "OpenAI API",
    "chatgpt_pro": "ChatGPT Pro",
    "minimax": "MiniMax Token Plan",
    "gemini": "Gemini API",
    "qianfan": "Baidu Qianfan",
    "brave": "Brave Search API",
    "digitalocean": "DigitalOcean",
}


class SyncService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        connectors: list[ProviderConnector] | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.connectors = connectors if connectors is not None else build_connectors(settings)
        self._lock = asyncio.Lock()

    async def sync_all(self, now: datetime | None = None) -> dict[str, Any]:
        if self._lock.locked():
            return {"sync": {"status": "already_running"}}

        async with self._lock:
            sync_time = now or datetime.now(UTC)
            self._record_provider_config_status()
            results: dict[str, dict[str, Any]] = {}

            for connector in self.connectors:
                self.db.ensure_provider(
                    connector.provider_id,
                    connector.display_name,
                    enabled=True,
                    status="configured",
                )
                run_id = self.db.start_sync_run(connector.provider_id)
                try:
                    result = await connector.sync(sync_time)
                    snapshots_written = 0
                    for snapshot in result.snapshots:
                        self.db.upsert_snapshot(snapshot)
                        snapshots_written += 1
                    self.db.finish_sync_run(
                        run_id,
                        status="succeeded",
                        snapshots_written=snapshots_written,
                    )
                    results[connector.provider_id] = {
                        "status": "succeeded",
                        "snapshots_written": snapshots_written,
                        "message": result.status_message,
                    }
                except ProviderSyncError as exc:
                    self.db.finish_sync_run(
                        run_id,
                        status="failed",
                        error_type=exc.error_type,
                        error_message=exc.message,
                    )
                    results[connector.provider_id] = {
                        "status": "failed",
                        "error_type": exc.error_type,
                        "error_message": exc.message,
                    }
                except Exception as exc:
                    self.db.finish_sync_run(
                        run_id,
                        status="failed",
                        error_type="unknown_error",
                        error_message=str(exc),
                    )
                    results[connector.provider_id] = {
                        "status": "failed",
                        "error_type": "unknown_error",
                        "error_message": str(exc),
                    }

            return {"sync": {"status": "completed"}, "providers": results}

    def _record_provider_config_status(self) -> None:
        for provider_id, config_status in self.settings.provider_config_status().items():
            status = config_status["status"]
            self.db.ensure_provider(
                provider_id,
                PROVIDER_NAMES[provider_id],
                enabled=status != "disabled",
                status=status,
            )


def build_connectors(settings: Settings) -> list[ProviderConnector]:
    statuses = settings.provider_config_status()
    connectors: list[ProviderConnector] = []

    if statuses["openai"]["status"] == "configured":
        from api_spend_dashboard.providers.openai import OpenAIConnector

        connectors.append(OpenAIConnector(settings))
    if statuses["chatgpt_pro"]["status"] == "configured":
        from api_spend_dashboard.providers.manual import ChatGPTProConnector

        connectors.append(ChatGPTProConnector(settings))
    if statuses["minimax"]["status"] == "configured":
        from api_spend_dashboard.providers.minimax import MiniMaxConnector

        connectors.append(MiniMaxConnector(settings))
    if statuses["gemini"]["status"] == "configured":
        from api_spend_dashboard.providers.gemini import GeminiConnector

        connectors.append(GeminiConnector(settings))
    if statuses["qianfan"]["status"] == "configured":
        from api_spend_dashboard.providers.qianfan import QianfanConnector

        connectors.append(QianfanConnector(settings))
    if statuses["brave"]["status"] == "configured":
        from api_spend_dashboard.providers.brave import BraveConnector

        connectors.append(BraveConnector(settings))
    if statuses["digitalocean"]["status"] == "configured":
        from api_spend_dashboard.providers.digitalocean import DigitalOceanConnector

        connectors.append(DigitalOceanConnector(settings))

    return connectors
