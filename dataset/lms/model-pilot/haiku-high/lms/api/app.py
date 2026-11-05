"""Application factory (section 4.1) and health endpoint (section 4.4)."""

from fastapi import Depends, FastAPI
from sqlalchemy.orm import sessionmaker

from lms.api import calendar_routes
from lms.api.deps import get_settings
from lms.api.errors import install_error_handlers
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

    install_error_handlers(app)
    app.include_router(calendar_routes.router)

    @app.get("/health", tags=["core"])
    def health(settings: Settings = Depends(get_settings)) -> dict:
        return {"status": "ok", "today": today(settings.clock).isoformat()}

    return app
