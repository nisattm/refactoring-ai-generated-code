"""Module 2 endpoints: login, own account (section 6.3) and user management (section 6.4)."""

import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import func, orm, select

from lms.api.deps import get_db, get_settings
from lms.api.errors import ApiError
from lms.audit.log import record_event
from lms.auth.deps import current_session, current_user, require_admin
from lms.auth.models import AuthSession, User
from lms.auth.passwords import hash_password, verify_password
from lms.auth.schemas import (
    ChangePasswordIn,
    LoginIn,
    ResetPasswordIn,
    TokenOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from lms.auth.service import (
    LOCK_DURATION,
    MAX_FAILED_LOGINS,
    open_session,
    revoke_sessions,
)
from lms.core.pagination import Page, PageParams, paginate
from lms.core.settings import Settings
from lms.core.text import normalize_text

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])

def _invalid_credentials() -> ApiError:
    # The same response for an unknown e-mail and a wrong password (LIB-AUTH-08).
    return ApiError(401, "INVALID_CREDENTIALS", "The e-mail address or password is incorrect.")


def _not_found(message: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# --- Login, own account --------------------------------------------------------------------


@auth_router.post("/login", response_model=TokenOut)
def login(
    body: LoginIn,
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    now = settings.clock.now()
    user = db.scalar(select(User).where(User.email_key == normalize_text(body.email)))

    if user is None:
        record_event(
            db, settings.clock, "login_failed",
            entity_type="user", entity_id=None, details={"email": body.email},
        )
        db.commit()  # a failed login keeps its audit entry (LIB-TECH-08)
        raise _invalid_credentials()

    if user.locked_until is not None and now < user.locked_until:
        raise ApiError(
            403, "ACCOUNT_LOCKED", "The account is locked after too many failed logins.",
            {"locked_until": _iso(user.locked_until)},
        )

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        record_event(
            db, settings.clock, "login_failed",
            entity_type="user", entity_id=user.id, details={"email": user.email},
        )
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCK_DURATION
            user.failed_login_count = 0
            record_event(
                db, settings.clock, "account_locked",
                entity_type="user", entity_id=user.id,
                details={"locked_until": _iso(user.locked_until)},
            )
        db.commit()  # the failure counter and lock are kept although the request fails (LIB-AUTH-09)
        raise _invalid_credentials()

    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "The account is inactive.")

    user.failed_login_count = 0
    user.last_login_at = now
    token, expires_at = open_session(db, settings, user, now)
    record_event(
        db, settings.clock, "login_succeeded",
        actor_user_id=user.id, entity_type="user", entity_id=user.id,
    )
    db.commit()
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@auth_router.post("/logout", status_code=204)
def logout(
    session: AuthSession = Depends(current_session),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    session.revoked_at = settings.clock.now()
    record_event(
        db, settings.clock, "logout",
        actor_user_id=session.user_id, entity_type="user", entity_id=session.user_id,
    )
    db.commit()
    return Response(status_code=204)


@auth_router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@auth_router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordIn,
    session: AuthSession = Depends(current_session),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = session.user
    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "The current password is incorrect.")
    if body.new_password == body.current_password:
        raise ApiError(409, "PASSWORD_UNCHANGED", "The new password must differ from the current one.")

    now = settings.clock.now()
    user.password_hash = hash_password(body.new_password)
    revoke_sessions(db, user.id, now, keep_session_id=session.id)
    record_event(
        db, settings.clock, "password_changed",
        actor_user_id=user.id, entity_type="user", entity_id=user.id,
    )
    db.commit()
    return Response(status_code=204)


# --- User management (admin) ---------------------------------------------------------------


@users_router.post("", status_code=201, response_model=UserOut)
def create_user(
    body: UserCreate,
    admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    key = normalize_text(body.email)
    if db.scalar(select(User.id).where(User.email_key == key)) is not None:
        raise ApiError(409, "CONFLICT", "An account with this e-mail address already exists.", {"field": "email"})

    user = User(
        email=body.email,
        email_key=key,
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
        is_active=True,
        failed_login_count=0,
        locked_until=None,
        member_id=None,
        created_at=settings.clock.now(),
        last_login_at=None,
    )
    db.add(user)
    db.flush()
    record_event(
        db, settings.clock, "user_created",
        actor_user_id=admin.id, entity_type="user", entity_id=user.id,
        details={"email": user.email, "full_name": user.full_name, "role": user.role},
    )
    db.commit()
    return user


@users_router.get("", response_model=Page[UserOut])
def list_users(
    role: Literal["member", "librarian", "admin"] | None = Query(default=None),
    is_active: Literal["true", "false"] | None = Query(default=None),
    q: str | None = Query(default=None),
    params: PageParams = Depends(),
    _admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
) -> Page[UserOut]:
    statement = select(User).order_by(User.id)
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active.is_(is_active == "true"))
    users = list(db.scalars(statement))
    # Substring match on the normalized text, which SQL lower() cannot do for Turkish letters (LIB-SRCH-01).
    needle = normalize_text((q or "").strip())
    if needle:
        users = [
            user for user in users
            if needle in normalize_text(user.email) or needle in normalize_text(user.full_name)
        ]
    return paginate(users, params, UserOut.model_validate)


@users_router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int = Path(gt=0),
    current: User = Depends(current_user),
    db: orm.Session = Depends(get_db),
) -> User:
    # Non-admins may only read their own record; the ownership check comes before existence (LIB-AUTH-19).
    if current.role != "admin" and current.id != user_id:
        raise ApiError(403, "FORBIDDEN", "You may only read your own user record.")
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("The user does not exist.")
    return user


@users_router.patch("/{user_id}", response_model=UserOut)
def update_user(
    body: UserUpdate,
    user_id: int = Path(gt=0),
    admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("The user does not exist.")

    fields = body.model_fields_set
    new_role = body.role if "role" in fields else user.role
    new_active = body.is_active if "is_active" in fields else user.is_active

    if "role" in fields and user.role == "member":
        raise ApiError(409, "ROLE_CHANGE_NOT_ALLOWED", "The role of a member account cannot be changed here.")
    if "is_active" in fields and body.is_active is False and user.id == admin.id:
        raise ApiError(409, "CANNOT_DEACTIVATE_SELF", "An administrator cannot deactivate their own account.")
    if user.role == "admin" and user.is_active and not (new_role == "admin" and new_active):
        other_admins = db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True), User.id != user.id)
        )
        if other_admins == 0:
            raise ApiError(409, "LAST_ADMIN", "The last active administrator cannot be removed or demoted.")

    now = settings.clock.now()
    changes: dict[str, dict] = {}
    if "full_name" in fields and body.full_name != user.full_name:
        changes["full_name"] = {"old": user.full_name, "new": body.full_name}
        user.full_name = body.full_name
    if "role" in fields and body.role != user.role:
        changes["role"] = {"old": user.role, "new": body.role}
        user.role = body.role

    active_change = None
    if "is_active" in fields and body.is_active != user.is_active:
        active_change = {"is_active": {"old": user.is_active, "new": body.is_active}}
        user.is_active = body.is_active
        if body.is_active:
            # Activation clears the lockout state (LIB-AUTH-21).
            _clear_lock(user, changes)
        else:
            revoke_sessions(db, user.id, now)
    elif body.is_active is True:
        _clear_lock(user, changes)

    if changes:
        record_event(
            db, settings.clock, "user_updated",
            actor_user_id=admin.id, entity_type="user", entity_id=user.id, details=changes,
        )
    if active_change is not None:
        event = "user_activated" if body.is_active else "user_deactivated"
        record_event(
            db, settings.clock, event,
            actor_user_id=admin.id, entity_type="user", entity_id=user.id, details=active_change,
        )
    db.commit()
    return user


def _clear_lock(user: User, changes: dict[str, dict]) -> None:
    if user.locked_until is not None:
        changes["locked_until"] = {"old": _iso(user.locked_until), "new": None}
        user.locked_until = None
    if user.failed_login_count != 0:
        changes["failed_login_count"] = {"old": user.failed_login_count, "new": 0}
        user.failed_login_count = 0


@users_router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    body: ResetPasswordIn,
    user_id: int = Path(gt=0),
    admin: User = Depends(require_admin),
    db: orm.Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("The user does not exist.")

    user.password_hash = hash_password(body.new_password)
    user.locked_until = None
    user.failed_login_count = 0
    revoke_sessions(db, user.id, settings.clock.now())
    record_event(
        db, settings.clock, "password_reset",
        actor_user_id=admin.id, entity_type="user", entity_id=user.id,
    )
    db.commit()
    return Response(status_code=204)
