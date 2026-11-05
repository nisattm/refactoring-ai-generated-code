"""FastAPI dependencies: settings and the per-request database session."""

import typing

from fastapi import Request
from sqlalchemy.orm import Session

from lms.core.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> typing.Iterator[Session]:
    """One database transaction per request (LIB-TECH-08).

    Commits when the endpoint returns. Any exception, including an ApiError that
    becomes an error response, rolls the transaction back.
    """
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
