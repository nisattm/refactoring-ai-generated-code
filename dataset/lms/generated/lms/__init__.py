"""Library Management System: fixed service interface (section 4)."""
import fastapi

from .core.clock import Clock, FixedClock, SystemClock
from .core.holidays import DEFAULT_HOLIDAYS
from .core.settings import Settings

__all__ = ["create_app", "Settings", "Clock", "SystemClock", "FixedClock", "DEFAULT_HOLIDAYS"]


def create_app(settings: Settings | None = None) -> fastapi.FastAPI:
    from .api import build_app

    return build_app(settings if settings is not None else Settings())
