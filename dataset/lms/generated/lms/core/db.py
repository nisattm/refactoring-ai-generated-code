"""Database engine, schema and per-request transaction (LIB-TECH-05 to LIB-TECH-08, LIB-IF-05)."""

from __future__ import annotations

import importlib
import weakref
from collections.abc import Iterator

import sqlalchemy as sa
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from lms.core.text import normalize


class Base(DeclarativeBase):
    """Base of all ORM models. Models set ``__table_args__ = {"sqlite_autoincrement": True}``
    so that ids are never reused (LIB-COM-14)."""


def create_db_engine(database_url: str) -> sa.Engine:
    url = make_url(database_url)
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        # In-memory database: all connections of one application must see the same data.
        kwargs["poolclass"] = StaticPool
    engine = sa.create_engine(url, **kwargs)

    @sa.event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        # Normalization of LIB-COM-30 for columns that have no stored key (used by search, LIB-SRCH-01).
        dbapi_connection.create_function(
            "lms_normalize", 1, lambda text: None if text is None else normalize(text), deterministic=True
        )

    return engine


_MEMORY_ENGINES: dict[int, sa.Engine] = {}


def get_engine(settings) -> sa.Engine:  # noqa: ANN001
    """The engine of ``settings``. An in-memory database exists once per ``Settings`` object, so that
    ``create_app`` and ``import_dataset`` / ``export_dataset`` called with the same settings see the same data."""
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        key = id(settings)
        engine = _MEMORY_ENGINES.get(key)
        if engine is None:
            engine = _MEMORY_ENGINES[key] = create_db_engine(settings.database_url)
            weakref.finalize(settings, _MEMORY_ENGINES.pop, key, None)
        return engine
    return create_db_engine(settings.database_url)


MODEL_MODULES = tuple(
    f"lms.{package}.models"
    for package in (
        "access",
        "audit",
        "auth",
        "branches",
        "catalog",
        "courses",
        "digital",
        "donations",
        "equipment",
        "events",
        "fines",
        "ill",
        "inventory",
        "loans",
        "members",
        "messaging",
        "notifications",
        "preservation",
        "printing",
        "programs",
        "purchasing",
        "reservations",
        "rooms",
        "staff",
        "suggestions",
    )
)


def create_schema(engine: sa.Engine) -> None:
    """LIB-TECH-07: create missing tables."""
    for module in MODEL_MODULES:
        importlib.import_module(module)  # registers the tables on ``Base.metadata``
    Base.metadata.create_all(engine)


def open_database(settings) -> tuple[sa.Engine, sessionmaker[Session]]:  # noqa: ANN001
    """The engine of ``settings`` with its schema created, and a session factory bound to it."""
    engine = get_engine(settings)
    create_schema(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one transaction per request. Any error rolls everything back."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


# ``scope="function"`` makes the transaction end (commit or rollback) before the response is sent.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]
