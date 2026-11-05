"""FastAPI dependencies: settings, the per-request database session, authentication and roles."""

import typing
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from lms.auth.service import Authenticated, authenticate
from lms.core.errors import ApiError
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


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def bearer_token(header: str | None) -> str | None:
    """The token of an 'Authorization: Bearer <token>' header, or None when the header is missing or malformed."""
    if header is None:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def get_authenticated(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Authenticated:
    """LIB-AUTH-12: every non-anonymous endpoint depends on this, so authentication runs before validation."""
    return authenticate(session, settings, bearer_token(request.headers.get("authorization")))


AuthDep = Annotated[Authenticated, Depends(get_authenticated)]


def require_roles(*roles: str) -> typing.Callable[..., Authenticated]:
    """LIB-AUTH-24: a role without the permission gets 403 FORBIDDEN (section 6.6)."""

    def dependency(auth: AuthDep) -> Authenticated:
        if auth.user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Your role does not allow this action.")
        return auth

    return dependency


AdminDep = Annotated[Authenticated, Depends(require_roles("admin"))]
