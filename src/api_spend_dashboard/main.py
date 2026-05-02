from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api_spend_dashboard.config import Settings, get_settings
from api_spend_dashboard.db import Database
from api_spend_dashboard.services.queries import DashboardQueries
from api_spend_dashboard.services.sync import SyncService


PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    db = Database(app_settings.database_url)
    db.migrate()
    sync_service = SyncService(app_settings, db)
    queries = DashboardQueries(db)
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            sync_service.sync_all,
            "interval",
            hours=app_settings.sync_interval_hours,
            id="sync_all",
            replace_existing=True,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="API Spend Dashboard", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.db = db
    app.state.sync_service = sync_service
    app.state.queries = queries
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/api/config/status")
    async def config_status() -> dict:
        return app_settings.provider_config_status()

    @app.get("/api/summary")
    async def summary() -> dict:
        now = datetime.now(UTC)
        return {
            "summary": queries.month_summary(now.year, now.month),
            "daily_costs": queries.daily_costs(),
        }

    @app.post("/api/sync")
    async def sync() -> dict:
        return await sync_service.sync_all()

    return app


app = create_app()
