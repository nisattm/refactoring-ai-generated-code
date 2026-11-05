"""Application factory and health endpoint (section 4.1, 4.4)."""

from fastapi import FastAPI

from lms.api.errors import register_error_handlers
from lms.core.clock import today
from lms.core.database import create_engine, create_schema
from lms.core.routes import router as calendar_router
from lms.core.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    engine = create_engine(settings.database_url)
    create_schema(engine)

    app = FastAPI(title="Library Management System")
    app.state.settings = settings
    app.state.engine = engine  # keeps this application's database connection alive
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "today": today(settings.clock).isoformat()}

    app.include_router(calendar_router)
    return app
