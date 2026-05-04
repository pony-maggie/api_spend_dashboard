from datetime import UTC, datetime, time, timedelta
import math
from typing import Any, Iterable

from google.oauth2 import service_account

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
            client = _bigquery_client(self.settings, bigquery)
            rows = client.query(query, job_config=job_config).result()
        except Exception as exc:
            raise ProviderSyncError(
                "provider_error", f"Gemini BigQuery query failed: {exc}"
            ) from exc

        snapshots = rows_to_snapshots(self.settings, rows)
        return SyncResult(self.provider_id, snapshots, "Gemini BigQuery billing synced")


def _bigquery_client(settings: Settings, bigquery: Any) -> Any:
    credentials_path = settings.google_application_credentials.strip()
    credentials = None
    if credentials_path:
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
    return bigquery.Client(project=settings.gcp_billing_project_id, credentials=credentials)


def rows_to_snapshots(settings: Settings, rows: Iterable[Any]) -> list[UsageSnapshot]:
    aggregated: dict[tuple[datetime, str], dict[str, Any]] = {}
    for row in rows:
        period_start = _as_datetime(_row_value(row, "usage_start_time"), "usage_start_time")
        period_end = _as_datetime(_row_value(row, "usage_end_time"), "usage_end_time")
        if period_end <= period_start:
            raise ProviderSyncError("parse_error", "Gemini usage_end_time must be after usage_start_time")

        utc_day = period_start.date()
        day_start = datetime.combine(utc_day, time.min, tzinfo=UTC)
        next_day_start = day_start + timedelta(days=1)
        if period_end > next_day_start:
            raise ProviderSyncError(
                "parse_error",
                "Gemini billing rows spanning multiple UTC dates are not supported",
            )
        if period_end.date() != utc_day and period_end != next_day_start:
            raise ProviderSyncError(
                "parse_error",
                "Gemini billing rows spanning multiple UTC dates are not supported",
            )

        currency = _currency(_row_value(row, "currency", settings.default_currency), settings)
        key = (day_start, currency)
        summary = aggregated.setdefault(
            key,
            {
                "cost_amount": 0.0,
                "row_count": 0,
                "service_descriptions": [],
            },
        )
        summary["cost_amount"] += _non_negative_float(_row_value(row, "cost", 0))
        summary["row_count"] += 1
        service_description = str(_row_value(row, "service_description", "")).strip()
        if service_description and service_description not in summary["service_descriptions"]:
            summary["service_descriptions"].append(service_description)

    snapshots: list[UsageSnapshot] = []
    for (day_start, currency), summary in sorted(aggregated.items()):
        raw_summary = {
            "row_count": summary["row_count"],
            "service_descriptions": summary["service_descriptions"],
        }
        if summary["row_count"] == 1 and summary["service_descriptions"]:
            raw_summary["service_description"] = summary["service_descriptions"][0]
        snapshots.append(
            UsageSnapshot(
                provider_id=GeminiConnector.provider_id,
                period_start=day_start,
                period_end=day_start + timedelta(days=1),
                granularity="day",
                currency=currency,
                cost_amount=summary["cost_amount"],
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                requests=None,
                quota_limit=None,
                quota_remaining=None,
                quota_reset_at=None,
                raw_summary=raw_summary,
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
    if not math.isfinite(amount):
        raise ProviderSyncError("parse_error", "Gemini cost amount must be finite")
    if amount < 0:
        raise ProviderSyncError("parse_error", "Gemini cost amount must be non-negative")
    return amount


def _currency(value: Any, settings: Settings) -> str:
    currency = str(value or settings.default_currency).strip().upper()
    if not currency:
        raise ProviderSyncError("missing_config", "currency must be non-empty")
    return currency
