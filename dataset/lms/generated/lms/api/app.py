"""Application factory (LIB-IF-01 to LIB-IF-03, LIB-IF-10)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lms.api import (
    access,
    audit,
    auth,
    branches,
    calendar,
    catalog,
    courses,
    dataexchange,
    digital,
    donations,
    equipment,
    events,
    fines,
    ill,
    inventory,
    loans,
    members,
    messaging,
    notifications,
    preservation,
    printing,
    programs,
    purchasing,
    reports,
    reservations,
    rooms,
    search,
    staff,
    suggestions,
    transfers,
    users,
)
from lms.api.errors import register_error_handlers
from lms.auth.bootstrap import ensure_bootstrap_admin
from lms.core.clock import today
from lms.core.db import open_database
from lms.core.settings import Settings

API_PREFIX = "/api/v1"
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
UI_PREFIX = "/ui"

# The order decides which route wins where paths overlap (e.g. fixed segments before ``{id}``): keep it.
ROUTER_MODULES = (
    calendar,
    auth,
    users,
    branches,
    members,
    catalog,
    loans,
    reservations,
    fines,
    transfers,
    notifications,
    search,
    reports,
    purchasing,
    audit,
    dataexchange,
    rooms,
    equipment,
    digital,
    ill,
    staff,
    events,
    courses,
    donations,
    preservation,
    inventory,
    suggestions,
    programs,
    messaging,
    access,
    printing,
)


class HealthOut(BaseModel):
    status: str
    today: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    engine, session_factory = open_database(settings)
    with session_factory.begin() as session:
        ensure_bootstrap_admin(session, settings)

    app = FastAPI(title="Library Management System", version="0.21", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    register_error_handlers(app)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health(request: Request) -> HealthOut:
        return HealthOut(status="ok", today=today(request.app.state.settings.clock).isoformat())

    api = APIRouter(prefix=API_PREFIX)
    for module in ROUTER_MODULES:
        api.include_router(module.router)
    app.include_router(api)
    if WEB_DIR.is_dir():  # LIB-UI-GEN-02: the web interface is optional
        app.mount(UI_PREFIX, StaticFiles(directory=WEB_DIR, html=True), name="ui")
    return app
