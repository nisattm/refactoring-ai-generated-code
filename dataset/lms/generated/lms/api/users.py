"""User management endpoints (section 6.4)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request, Response

from lms.auth import service
from lms.auth.deps import AdminOnly, CurrentPrincipal
from lms.auth.models import User
from lms.auth.schemas import ResetPasswordIn, Role, UserCreateIn, UserOut, UserPatchIn, user_out
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.text import normalize

router = APIRouter(prefix="/users", tags=["users"])

UserId = Annotated[int, Path(ge=1)]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> UserOut:
    now = local_now(request.app.state.settings.clock)
    user = service.create_user(db, now, admin.user, body.email, body.full_name, body.role, body.password)
    return user_out(user)


@router.get("", response_model=Page[UserOut])
def list_users(
    db: SessionDep,
    admin: AdminOnly,
    page: PageDep,
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Page[UserOut]:
    stmt = sa.select(User).order_by(User.id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    needle = normalize(q.strip()) if q is not None else ""
    if not needle:
        return paginate(db, stmt, page, user_out)
    # Case-insensitive matching follows LIB-COM-30, which SQLite cannot do for Turkish letters.
    matches = [
        user_out(u)
        for u in db.scalars(stmt)
        if needle in u.email_key or needle in normalize(u.full_name)
    ]
    return paginate_sequence(matches, page)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: UserId, db: SessionDep, principal: CurrentPrincipal) -> UserOut:
    # For non-admins the ownership check comes before the existence check (LIB-AUTH-19).
    if principal.user.role != "admin" and user_id != principal.user.id:
        raise Forbidden("Only your own user record can be read")
    return user_out(service.get_user_or_404(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: UserId, body: UserPatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> UserOut:
    now = local_now(request.app.state.settings.clock)
    user = service.get_user_or_404(db, user_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return user_out(service.update_user(db, now, admin.user, user, fields))


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: UserId, body: ResetPasswordIn, request: Request, db: SessionDep, admin: AdminOnly) -> Response:
    now = local_now(request.app.state.settings.clock)
    user = service.get_user_or_404(db, user_id)
    service.reset_password(db, now, admin.user, user, body.new_password)
    return Response(status_code=204)
