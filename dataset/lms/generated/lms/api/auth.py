"""Authentication endpoints (sections 6.3): login, logout, me, change password."""

from __future__ import annotations

from fastapi import APIRouter, Response

from lms.auth import service
from lms.auth.deps import CurrentPrincipal
from lms.auth.schemas import ChangePasswordIn, LoginIn, LoginOut, UserOut, user_out
from lms.core.context import NowDep, SettingsDep
from lms.core.db import SessionDep
from lms.core.timeutil import format_datetime

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, settings: SettingsDep, now: NowDep, db: SessionDep) -> LoginOut:
    token, auth_session, user = service.login(db, settings, now, body.email, body.password)
    return LoginOut(
        access_token=token,
        token_type="bearer",
        expires_at=format_datetime(auth_session.expires_at),
        user=user_out(user),
    )


@router.post("/logout", status_code=204)
def logout(now: NowDep, db: SessionDep, principal: CurrentPrincipal) -> Response:
    service.logout(db, now, principal.user, principal.session)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(principal: CurrentPrincipal) -> UserOut:
    return user_out(principal.user)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, now: NowDep, db: SessionDep, principal: CurrentPrincipal) -> Response:
    service.change_password(db, now, principal.user, principal.session, body.current_password, body.new_password)
    return Response(status_code=204)
