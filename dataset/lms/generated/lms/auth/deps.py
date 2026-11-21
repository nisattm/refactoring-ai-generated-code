"""Authentication and role checks as FastAPI dependencies (LIB-AUTH-12, LIB-AUTH-24)."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, Request

from lms.auth.models import AuthSession, User
from lms.core.context import request_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, Unauthenticated


@dataclasses.dataclass
class Principal:
    """The authenticated user and the session of the token that was used."""

    user: User
    session: AuthSession


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def authenticate(request: Request, db: SessionDep) -> Principal:
    token = _bearer_token(request)
    if token is None:
        raise Unauthenticated("Authentication required")
    auth_session = db.scalar(sa.select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if auth_session is None or auth_session.revoked_at is not None:
        raise Unauthenticated("Invalid or revoked token")
    if request_now(request) >= auth_session.expires_at:
        raise Unauthenticated("Token has expired", code="TOKEN_EXPIRED")
    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise Unauthenticated("Invalid or revoked token")
    return Principal(user=user, session=auth_session)


CurrentPrincipal = Annotated[Principal, Depends(authenticate)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency factory: authenticated (401), then role allowed (403)."""

    def check(principal: CurrentPrincipal) -> Principal:
        if principal.user.role not in roles:
            raise Forbidden("Your role does not allow this action")
        return principal

    return check


def own_member_check(message: str) -> Callable[[Principal, int], None]:
    """LIB-AUTH-25: a check that a ``member`` user addresses only records of their own member record
    (403 with ``message`` otherwise). Librarians and admins may address every member."""

    def check(principal: Principal, member_id: int) -> None:
        if principal.user.role == "member" and principal.user.member_id != member_id:
            raise Forbidden(message)

    return check


AnyUser = CurrentPrincipal
AdminOnly = Annotated[Principal, Depends(require_roles("admin"))]
StaffOnly = Annotated[Principal, Depends(require_roles("librarian", "admin"))]
