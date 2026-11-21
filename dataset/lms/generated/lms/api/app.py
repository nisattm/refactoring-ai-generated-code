"""Application factory (LIB-IF-01 to LIB-IF-03, LIB-IF-10)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel

from lms.api import (
    audit,
    auth,
    branches,
    calendar,
    catalog,
    dataexchange,
    fines,
    loans,
    members,
    notifications,
    purchasing,
    reports,
    reservations,
    search,
    transfers,
    users,
)
from lms.api.errors import register_error_handlers
from lms.auth.bootstrap import ensure_bootstrap_admin
from lms.core.context import request_today
from lms.core.db import create_session_factory, open_database
from lms.core.settings import Settings

API_PREFIX = "/api/v1"

# The order of inclusion is the order of the routes.
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
)


class HealthOut(BaseModel):
    status: str
    today: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    engine = open_database(settings)
    session_factory = create_session_factory(engine)
    with session_factory.begin() as session:
        ensure_bootstrap_admin(session, settings)

    app = FastAPI(title="Library Management System", version="0.7", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    register_error_handlers(app)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health(request: Request) -> HealthOut:
        return HealthOut(status="ok", today=request_today(request).isoformat())

    api = APIRouter(prefix=API_PREFIX)
    for module in ROUTER_MODULES:
        api.include_router(module.router)
    app.include_router(api)
    return app
