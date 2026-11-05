"""Application factory (section 4.1) and health endpoint (section 4.4)."""

from fastapi import Depends, FastAPI
from sqlalchemy.orm import sessionmaker

import lms.audit.models  # noqa: F401  (registers the tables before create_schema)
import lms.auth.models  # noqa: F401
from lms.api import auth_routes, calendar_routes, user_routes
from lms.api.deps import get_settings
from lms.api.errors import install_error_handlers
from lms.auth.service import ensure_bootstrap_admin
from lms.core.db import create_engine_for, create_schema
from lms.core.localtime import today
from lms.core.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    engine = create_engine_for(settings.database_url)
    create_schema(engine)

    app = FastAPI(title="Library Management System", version="1.0.0")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # LIB-IF-02, LIB-AUTH-01: create the bootstrap administrator if no admin exists yet.
    with app.state.session_factory() as session:
        ensure_bootstrap_admin(session, settings)
        session.commit()

    install_error_handlers(app)
    app.include_router(calendar_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(user_routes.router)

    @app.get("/health", tags=["core"])
    def health(settings: Settings = Depends(get_settings)) -> dict:
        return {"status": "ok", "today": today(settings.clock).isoformat()}

    return app
