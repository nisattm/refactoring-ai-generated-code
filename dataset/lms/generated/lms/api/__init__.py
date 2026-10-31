import fastapi

from ..core import db
from ..core.clock import today
from ..core.settings import Settings
from .calendar import router as calendar_router
from .errors import install_error_handlers


def build_app(settings: Settings) -> fastapi.FastAPI:
    app = fastapi.FastAPI(title="Library Management System", openapi_url="/openapi.json")
    app.state.settings = settings
    engine = db.make_engine(settings.database_url)
    db.create_schema(engine)
    app.state.engine = engine
    app.state.session_factory = db.make_session_factory(engine)
    install_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok", "today": today(settings.clock).isoformat()}

    app.include_router(calendar_router)
    return app
