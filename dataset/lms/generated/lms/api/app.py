"""Application factory (LIB-IF-01 to LIB-IF-03, LIB-IF-10)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from lms.api import auth, branches, calendar, catalog, fines, loans, members, users
from lms.api.errors import register_error_handlers
from lms.auth.bootstrap import ensure_bootstrap_admin
from lms.core.clock import today
from lms.core.db import create_db_engine, create_schema
from lms.core.settings import Settings

API_PREFIX = "/api/v1"


class HealthOut(BaseModel):
    status: str
    today: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    engine = create_db_engine(settings.database_url)
    create_schema(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory.begin() as session:
        ensure_bootstrap_admin(session, settings)

    app = FastAPI(title="Library Management System", version="0.7", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    register_error_handlers(app)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health(request: Request) -> HealthOut:
        return HealthOut(status="ok", today=today(request.app.state.settings.clock).isoformat())

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(calendar.router)
    api.include_router(auth.router)
    api.include_router(users.router)
    api.include_router(branches.router)
    api.include_router(members.router)
    api.include_router(catalog.router)
    api.include_router(loans.router)
    api.include_router(fines.router)
    app.include_router(api)
    return app
