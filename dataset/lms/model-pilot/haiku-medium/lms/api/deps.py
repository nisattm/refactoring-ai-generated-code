"""Dependencies shared by all routers: settings and a database session per request."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import orm

from lms.core.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[orm.Session]:
    """One session per request. Endpoints call commit() when they succeed; any other exit rolls back (LIB-TECH-08)."""
    with orm.Session(request.app.state.engine) as session:
        yield session
