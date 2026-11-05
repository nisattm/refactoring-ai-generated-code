"""Authentication and role checks as FastAPI dependencies (LIB-AUTH-12, LIB-AUTH-24)."""

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy import orm, select

from lms.api.deps import get_db, get_settings
from lms.api.errors import ApiError
from lms.auth.models import AuthSession, User
from lms.auth.service import hash_token
from lms.core.settings import Settings


def current_session(
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
) -> AuthSession:
    unauthenticated = ApiError(401, "UNAUTHENTICATED", "Authentication is required.")
    if authorization is None:
        raise unauthenticated
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise unauthenticated

    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is None or session.revoked_at is not None or not session.user.is_active:
        raise unauthenticated
    if settings.clock.now() >= session.expires_at:
        raise ApiError(401, "TOKEN_EXPIRED", "The token has expired.")
    return session


def current_user(session: AuthSession = Depends(current_session)) -> User:
    return session.user


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency that admits only the given roles (section 6.6)."""

    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Your role does not allow this action.")
        return user

    return check


require_admin = require_roles("admin")
