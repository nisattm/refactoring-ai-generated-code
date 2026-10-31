"""Database engine, schema and per-request transaction (LIB-TECH-05 to LIB-TECH-08, LIB-IF-05)."""

from __future__ import annotations

from collections.abc import Iterator

import sqlalchemy as sa
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


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

    return engine


def create_schema(engine: sa.Engine) -> None:
    """LIB-TECH-07: create missing tables."""
    import lms.audit.models  # noqa: F401  (register models)
    import lms.auth.models  # noqa: F401
    import lms.branches.models  # noqa: F401
    import lms.catalog.models  # noqa: F401
    import lms.fines.models  # noqa: F401
    import lms.loans.models  # noqa: F401
    import lms.members.models  # noqa: F401
    import lms.reservations.models  # noqa: F401

    Base.metadata.create_all(engine)


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
