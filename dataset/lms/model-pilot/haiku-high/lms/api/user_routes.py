"""Module 2 endpoints for user management (section 6.4)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response

from lms.api.auth_schemas import (
    CreateUserIn,
    ResetPasswordIn,
    Role,
    UpdateUserIn,
    UserOut,
)
from lms.api.deps import AdminDep, AuthDep, SessionDep, SettingsDep
from lms.auth import users
from lms.core.errors import ApiError
from lms.core.pagination import page_body

router = APIRouter(prefix="/api/v1/users", tags=["users"])

UserId = Annotated[int, Path(gt=0)]


@router.post("", status_code=201, response_model=UserOut)
def create_user(
    body: CreateUserIn, admin: AdminDep, session: SessionDep, settings: SettingsDep
) -> UserOut:
    user = users.create_user(
        session,
        actor=admin.user,
        now=settings.clock.now(),
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        password=body.password,
    )
    return UserOut.model_validate(user)


@router.get("")
def list_users(
    admin: AdminDep,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: Role | None = None,
    is_active: Literal["true", "false"] | None = None,
    q: str | None = None,
) -> dict:
    found = users.list_users(
        session,
        role=role,
        is_active=None if is_active is None else is_active == "true",
        q=q,
    )
    start = (page - 1) * page_size
    items = [UserOut.model_validate(user) for user in found[start : start + page_size]]
    return page_body(
        [item.model_dump(mode="json") for item in items],
        page=page,
        page_size=page_size,
        total=len(found),
    )


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: UserId, auth: AuthDep, session: SessionDep) -> UserOut:
    # LIB-AUTH-19: a non-admin may read only their own record, and the ownership check comes before existence.
    if auth.user.role != "admin" and user_id != auth.user.id:
        raise ApiError(403, "FORBIDDEN", "You may read only your own account.")
    return UserOut.model_validate(users.get_user(session, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UserId,
    body: UpdateUserIn,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> UserOut:
    target = users.get_user(session, user_id)
    users.update_user(
        session,
        actor=admin.user,
        target=target,
        now=settings.clock.now(),
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
    )
    return UserOut.model_validate(target)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: UserId,
    body: ResetPasswordIn,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    target = users.get_user(session, user_id)
    users.reset_password(
        session,
        actor=admin.user,
        target=target,
        now=settings.clock.now(),
        new_password=body.new_password,
    )
    return Response(status_code=204)
