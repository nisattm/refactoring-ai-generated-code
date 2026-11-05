"""Application factory and health endpoint (section 4.1, 4.4)."""

from fastapi import FastAPI

from sqlalchemy import orm

from lms.api.errors import register_error_handlers
from lms.audit import models as _audit_models  # noqa: F401  registers the tables before create_schema
from lms.auth import models as _auth_models  # noqa: F401
from lms.auth.routes import auth_router, users_router
from lms.auth.service import ensure_bootstrap_admin
from lms.core.clock import today
from lms.core.database import create_engine, create_schema
from lms.core.routes import router as calendar_router
from lms.core.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    engine = create_engine(settings.database_url)
    create_schema(engine)
    with orm.Session(engine) as db:
        ensure_bootstrap_admin(db, settings)

    app = FastAPI(title="Library Management System")
    app.state.settings = settings
    app.state.engine = engine  # keeps this application's database connection alive
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "today": today(settings.clock).isoformat()}

    app.include_router(calendar_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    return app
