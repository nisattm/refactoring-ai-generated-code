"""Login, logout, current user, change password (LIB-AUTH-06 to LIB-AUTH-16)."""
import datetime

from fastapi import APIRouter, Body, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, auth
from ..auth.models import User, UserSession
from ..core import db
from ..core.clock import to_local
from ..core.errors import ApiError, business_rule
from . import validation as v
from .deps import Auth, current_auth, now_of

router = APIRouter(prefix="/api/v1/auth")

LOCK_THRESHOLD = 5
LOCK_MINUTES = 15


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "member_id": u.member_id,
        "created_at": to_local(u.created_at).isoformat(),
        "last_login_at": to_local(u.last_login_at).isoformat() if u.last_login_at else None,
    }


def _invalid() -> ApiError:
    return ApiError(401, "INVALID_CREDENTIALS", "Invalid e-mail or password")


@router.post("/login")
def login(request: Request, body: dict = Body(...), session: Session = Depends(db.get_session)):
    fields: list = []
    v.check_keys(body, {"email", "password"}, {"email", "password"}, fields)
    email = v.string_raw(body, "email", fields) if "email" in body else None
    pw = v.string_raw(body, "password", fields) if "password" in body else None
    v.fail(fields)

    settings = request.app.state.settings
    now = now_of(request)
    user = session.scalars(select(User).where(User.email_key == auth.email_key(email.strip()))).first()
    if user is None:
        audit.record(session, now, "login_failed", None, "user", None, {"email": email.strip().lower()})
        session.commit()
        raise _invalid()

    if user.locked_until is not None and now < user.locked_until:
        raise ApiError(
            403,
            "ACCOUNT_LOCKED",
            "Account is temporarily locked",
            {"locked_until": to_local(user.locked_until).isoformat()},
        )

    if not auth.verify_password(pw, user.password_hash):
        user.failed_login_count += 1
        audit.record(
            session, now, "login_failed", None, "user", user.id,
            {"email": user.email, "failed_login_count": user.failed_login_count},
        )
        if user.failed_login_count >= LOCK_THRESHOLD:
            user.locked_until = now + datetime.timedelta(minutes=LOCK_MINUTES)
            user.failed_login_count = 0
            audit.record(
                session, now, "account_locked", None, "user", user.id,
                {"locked_until": to_local(user.locked_until).isoformat()},
            )
        session.commit()
        raise _invalid()

    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "Account is disabled")

    token = auth.new_token()
    expires = now + datetime.timedelta(hours=settings.token_ttl_hours)
    session.add(
        UserSession(user_id=user.id, token_hash=auth.token_digest(token), created_at=now, expires_at=expires)
    )
    user.failed_login_count = 0
    user.last_login_at = now
    audit.record(session, now, "login_succeeded", user.id, "user", user.id, {"email": user.email})
    session.flush()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": to_local(expires).isoformat(),
        "user": user_out(user),
    }


@router.post("/logout", status_code=204)
def logout(request: Request, a: Auth = Depends(current_auth), session: Session = Depends(db.get_session)):
    now = now_of(request)
    a.session.revoked_at = now
    audit.record(session, now, "logout", a.user.id, "user", a.user.id, {})
    return Response(status_code=204)


@router.get("/me")
def me(a: Auth = Depends(current_auth)):
    return user_out(a.user)


@router.post("/change-password", status_code=204)
def change_password(
    request: Request,
    body: dict = Body(...),
    a: Auth = Depends(current_auth),
    session: Session = Depends(db.get_session),
):
    fields: list = []
    v.check_keys(body, {"current_password", "new_password"}, {"current_password", "new_password"}, fields)
    if "current_password" in body:
        v.string_raw(body, "current_password", fields)
    if "new_password" in body:
        v.password(body, "new_password", fields)
    v.fail(fields)

    user = a.user
    if not auth.verify_password(body["current_password"], user.password_hash):
        raise _invalid()
    if body["new_password"] == body["current_password"]:
        raise business_rule("PASSWORD_UNCHANGED", "New password must differ from the current password")
    now = now_of(request)
    user.password_hash = auth.hash_password(body["new_password"])
    auth.revoke_sessions(session, user.id, now, except_id=a.session.id)
    audit.record(session, now, "password_changed", user.id, "user", user.id, {})
    return Response(status_code=204)
