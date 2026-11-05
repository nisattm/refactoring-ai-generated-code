"""Module 2 endpoints for the current account: login, logout, me, change password (section 6.3)."""

from fastapi import APIRouter, Response

from lms.api.auth_schemas import ChangePasswordIn, LoginIn, LoginOut, UserOut
from lms.api.deps import AuthDep, SessionDep, SettingsDep
from lms.auth import service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, session: SessionDep, settings: SettingsDep) -> LoginOut:
    result = service.login(session, settings, email=body.email, password=body.password)
    return LoginOut(
        access_token=result.token,
        expires_at=result.session.expires_at,
        user=UserOut.model_validate(result.user),
    )


@router.post("/logout", status_code=204)
def logout(auth: AuthDep, session: SessionDep, settings: SettingsDep) -> Response:
    service.logout(session, settings, auth)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(auth: AuthDep) -> UserOut:
    return UserOut.model_validate(auth.user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordIn,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    service.change_password(
        session,
        settings,
        auth,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return Response(status_code=204)
