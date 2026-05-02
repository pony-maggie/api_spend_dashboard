from datetime import UTC, datetime
from typing import Any, Iterable

from api_spend_dashboard.config import Settings
from api_spend_dashboard.models import UsageSnapshot
from api_spend_dashboard.providers.base import ProviderSyncError, SyncResult
from api_spend_dashboard.providers.manual import _month_bounds


class GeminiConnector:
    provider_id = "gemini"
    display_name = "Gemini API"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync(self, now: datetime) -> SyncResult:
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise ProviderSyncError(
                "missing_config", "google-cloud-bigquery is required for Gemini billing sync"
            ) from exc

        start, end = _month_bounds(now)
        table_id = _billing_table_id(self.settings)
        query = f"""
            SELECT
              usage_start_time,
              usage_end_time,
              cost,
              currency,
              service.description AS service_description
            FROM `{table_id}`
            WHERE usage_start_time >= @period_start
              AND usage_start_time < @period_end
              AND service.description LIKE @service_filter
            ORDER BY usage_start_time
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("period_start", "TIMESTAMP", start),
                bigquery.ScalarQueryParameter("period_end", "TIMESTAMP", end),
                bigquery.ScalarQueryParameter(
                    "service_filter", "STRING", f"%{self.settings.gemini_service_filter}%"
                ),
            ]
        )
        try:
            client = bigquery.Client(project=self.settings.gcp_billing_project_id)
            rows = client.query(query, job_config=job_config).result()
        except Exception as exc:
            raise ProviderSyncError(
                "provider_error", f"Gemini BigQuery query failed: {exc}"
            ) from exc

        snapshots = rows_to_snapshots(self.settings, rows)
        return SyncResult(self.provider_id, snapshots, "Gemini BigQuery billing synced")


def rows_to_snapshots(settings: Settings, rows: Iterable[Any]) -> list[UsageSnapshot]:
    snapshots: list[UsageSnapshot] = []
    for row in rows:
        period_start = _as_datetime(_row_value(row, "usage_start_time"), "usage_start_time")
        period_end = _as_datetime(_row_value(row, "usage_end_time"), "usage_end_time")
        if period_end <= period_start:
            raise ProviderSyncError("parse_error", "Gemini usage_end_time must be after usage_start_time")

        snapshots.append(
            UsageSnapshot(
                provider_id=GeminiConnector.provider_id,
                period_start=period_start,
                period_end=period_end,
                granularity="day",
                currency=_currency(_row_value(row, "currency", settings.default_currency), settings),
                cost_amount=_non_negative_float(_row_value(row, "cost", 0)),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                requests=None,
                quota_limit=None,
                quota_remaining=None,
                quota_reset_at=None,
                raw_summary={
                    "service_description": str(_row_value(row, "service_description", "")),
                },
            )
        )
    return snapshots


def _billing_table_id(settings: Settings) -> str:
    project = settings.gcp_billing_project_id.strip()
    dataset = settings.gcp_billing_dataset.strip()
    table = settings.gcp_billing_table.strip()
    if not project or not dataset or not table:
        raise ProviderSyncError(
            "missing_config",
            "GCP_BILLING_PROJECT_ID, GCP_BILLING_DATASET, and GCP_BILLING_TABLE are required",
        )
    return f"{project}.{dataset}.{table}"


def _row_value(row: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(field_name, default)
    return getattr(row, field_name, default)


def _as_datetime(value: Any, field_name: str = "datetime") -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ProviderSyncError("parse_error", f"Gemini {field_name} was malformed") from exc
    else:
        raise ProviderSyncError("parse_error", f"Gemini {field_name} was malformed")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProviderSyncError("parse_error", f"Gemini {field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _non_negative_float(value: Any) -> float:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ProviderSyncError("parse_error", "Gemini cost amount was not numeric") from exc
    if amount < 0:
        raise ProviderSyncError("parse_error", "Gemini cost amount must be non-negative")
    return amount


def _currency(value: Any, settings: Settings) -> str:
    currency = str(value or settings.default_currency).strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", "currency must be non-empty")
    return currency
