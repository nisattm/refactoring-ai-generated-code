"""Database engine and schema (LIB-TECH-05 to LIB-TECH-07, LIB-IF-03, LIB-IF-05)."""

import sqlalchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class of all ORM models. Module packages import their models so they are registered here."""


def create_engine_for(database_url: str) -> Engine:
    """A new engine per application, so that applications share no state (LIB-IF-03).

    An in-memory database uses one shared connection, so every request of the
    application sees the same data (LIB-IF-05).
    """
    url = sqlalchemy.make_url(database_url)
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        kwargs["poolclass"] = StaticPool
    engine = sqlalchemy.create_engine(database_url, **kwargs)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """LIB-TECH-07: create missing tables at start-up. No migrations."""
    Base.metadata.create_all(engine)
