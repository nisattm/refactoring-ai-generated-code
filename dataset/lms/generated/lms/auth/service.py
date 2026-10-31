"""Business logic of module 2: login, sessions and user management (sections 6.2 to 6.4)."""

from __future__ import annotations

import datetime
import secrets
from typing import NoReturn

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.deps import hash_token
from lms.auth.models import AuthSession, User
from lms.auth.passwords import hash_password, verify_password
from lms.core.errors import ApiError, Conflict, Forbidden, NotFound
from lms.core.settings import Settings
from lms.core.text import normalize
from lms.core.timeutil import format_datetime

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
TOKEN_BYTES = 32

INVALID_CREDENTIALS_MESSAGE = "Invalid e-mail or password"

# Verified against when the e-mail is unknown, so that both failures take about the same time.
_DUMMY_HASH = hash_password("dummy-password-1")


class _InvalidCredentials(ApiError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class _AccountLocked(Forbidden):
    code = "ACCOUNT_LOCKED"


class _AccountDisabled(Forbidden):
    code = "ACCOUNT_DISABLED"


def invalid_credentials() -> ApiError:
    return _InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)


# --- sessions ---------------------------------------------------------------


def revoke_sessions(db: Session, user_id: int, now: datetime.datetime, *, except_id: int | None = None) -> None:
    stmt = (
        sa.update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if except_id is not None:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt)


# --- login ------------------------------------------------------------------


def _failed_login(db: Session, now: datetime.datetime, user: User | None, email: str, reason: str) -> None:
    record(
        db,
        at=now,
        event="login_failed",
        entity_type="user",
        entity_id=user.id if user else None,
        details={"email": email, "reason": reason},
    )


def login(db: Session, settings: Settings, now: datetime.datetime, email: str, password: str) -> tuple[str, AuthSession, User]:
    """LIB-AUTH-06 to LIB-AUTH-11.

    A failed login keeps its changes (LIB-TECH-08): the changes are committed before the error is raised.
    """
    email = email.strip().lower()
    user = db.scalar(sa.select(User).where(User.email_key == normalize(email)))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        _failed_login(db, now, None, email, "unknown_email")
        _commit_and_raise(db, invalid_credentials())
    assert user is not None

    if user.locked_until is not None and now < user.locked_until:
        _failed_login(db, now, user, email, "account_locked")
        _commit_and_raise(
            db,
            _AccountLocked(
                "Account is locked because of too many failed logins",
                details={"locked_until": format_datetime(user.locked_until)},
            ),
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        _failed_login(db, now, user, email, "wrong_password")
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + datetime.timedelta(minutes=LOCK_MINUTES)
            user.failed_login_count = 0
            record(
                db,
                at=now,
                event="account_locked",
                entity_type="user",
                entity_id=user.id,
                details={"locked_until": format_datetime(user.locked_until)},
            )
        _commit_and_raise(db, invalid_credentials())

    if not user.is_active:
        _failed_login(db, now, user, email, "account_disabled")
        _commit_and_raise(db, _AccountDisabled("Account is disabled"))

    token = secrets.token_urlsafe(TOKEN_BYTES)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + datetime.timedelta(hours=settings.token_ttl_hours),
    )
    db.add(auth_session)
    user.failed_login_count = 0
    user.last_login_at = now
    db.flush()
    record(
        db,
        at=now,
        event="login_succeeded",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "session_id": auth_session.id},
    )
    return token, auth_session, user


def _commit_and_raise(db: Session, error: ApiError) -> NoReturn:
    db.commit()
    raise error


# --- own account ------------------------------------------------------------


def logout(db: Session, now: datetime.datetime, user: User, auth_session: AuthSession) -> None:
    auth_session.revoked_at = now
    record(
        db,
        at=now,
        event="logout",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        details={"session_id": auth_session.id},
    )


def change_password(
    db: Session, now: datetime.datetime, user: User, auth_session: AuthSession, current: str, new: str
) -> None:
    """LIB-AUTH-16. ``new`` has already passed the password policy."""
    if not verify_password(current, user.password_hash):
        raise invalid_credentials()
    if verify_password(new, user.password_hash):
        raise Conflict("The new password must differ from the current password", code="PASSWORD_UNCHANGED")
    user.password_hash = hash_password(new)
    revoke_sessions(db, user.id, now, except_id=auth_session.id)
    record(db, at=now, event="password_changed", actor_user_id=user.id, entity_type="user", entity_id=user.id)


# --- user management --------------------------------------------------------


def create_user(db: Session, now: datetime.datetime, actor: User, email: str, full_name: str, role: str, password: str) -> User:
    key = normalize(email)
    if db.scalar(sa.select(User.id).where(User.email_key == key)) is not None:
        raise Conflict("A user with this e-mail address already exists", details={"field": "email"})
    user = User(
        email=email,
        email_key=key,
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
        is_active=True,
        failed_login_count=0,
        created_at=now,
    )
    db.add(user)
    db.flush()
    record(
        db,
        at=now,
        event="user_created",
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        details={"email": email, "full_name": full_name, "role": role},
    )
    return user


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound(f"User {user_id} does not exist", details={"resource": "user", "id": user_id})
    return user


def update_user(db: Session, now: datetime.datetime, actor: User, user: User, fields: dict[str, object]) -> User:
    """LIB-AUTH-20 to LIB-AUTH-22. ``fields`` holds only the fields present in the request."""
    new_role = fields.get("role")
    new_active = fields.get("is_active")

    if new_role is not None and user.role == "member":
        raise Conflict("The role of a member user cannot be changed", code="ROLE_CHANGE_NOT_ALLOWED")

    loses_admin = user.role == "admin" and user.is_active and (
        (new_role is not None and new_role != "admin") or new_active is False
    )
    if loses_admin:
        other_admins = db.scalar(
            sa.select(sa.func.count()).select_from(User).where(User.role == "admin", User.is_active, User.id != user.id)
        )
        if not other_admins:
            raise Conflict("There must be at least one active administrator", code="LAST_ADMIN")
    if new_active is False and user.id == actor.id:
        raise Conflict("Administrators cannot deactivate their own account", code="CANNOT_DEACTIVATE_SELF")

    descriptive = {k: v for k, v in fields.items() if k in ("full_name", "role")}
    diff = changes({k: getattr(user, k) for k in descriptive}, descriptive)
    for name, value in descriptive.items():
        setattr(user, name, value)
    if diff:
        record(
            db, at=now, event="user_updated", actor_user_id=actor.id, entity_type="user", entity_id=user.id, details=diff
        )

    if new_active is not None:
        was_active = user.is_active
        user.is_active = bool(new_active)
        if new_active:
            user.locked_until = None
            user.failed_login_count = 0
        else:
            revoke_sessions(db, user.id, now)
        if was_active != user.is_active:
            record(
                db,
                at=now,
                event="user_activated" if new_active else "user_deactivated",
                actor_user_id=actor.id,
                entity_type="user",
                entity_id=user.id,
                details={"is_active": {"old": was_active, "new": user.is_active}},
            )
    return user


def reset_password(db: Session, now: datetime.datetime, actor: User, user: User, new_password: str) -> None:
    """LIB-AUTH-23."""
    user.password_hash = hash_password(new_password)
    user.locked_until = None
    user.failed_login_count = 0
    revoke_sessions(db, user.id, now)
    record(db, at=now, event="password_reset", actor_user_id=actor.id, entity_type="user", entity_id=user.id)
