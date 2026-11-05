"""Login, sessions, own password and the bootstrap administrator (section 6.2, 6.3)."""

import dataclasses
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from lms.audit.service import record_event
from lms.auth.credentials import (
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from lms.auth.models import AuthSession, User
from lms.core.errors import ApiError
from lms.core.localtime import format_datetime
from lms.core.settings import Settings
from lms.core.text import clean_email, email_key

# LIB-AUTH-09
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = datetime.timedelta(minutes=15)


@dataclasses.dataclass(frozen=True)
class Authenticated:
    """The user and session of an authenticated request (LIB-AUTH-12)."""

    user: User
    session: AuthSession


@dataclasses.dataclass(frozen=True)
class LoginResult:
    token: str
    session: AuthSession
    user: User


def invalid_credentials() -> ApiError:
    # LIB-AUTH-08: the same response for an unknown e-mail and a wrong password.
    return ApiError(401, "INVALID_CREDENTIALS", "The e-mail or password is incorrect.")


def unauthenticated() -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", "Authentication is required.")


def revoke_sessions(
    session: Session, user: User, now: datetime.datetime, *, except_id: int | None = None
) -> None:
    """Revoke every session of the user that is not revoked yet, optionally keeping one."""
    statement = select(AuthSession).where(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
    )
    if except_id is not None:
        statement = statement.where(AuthSession.id != except_id)
    for auth_session in session.scalars(statement):
        auth_session.revoked_at = now


def login(session: Session, settings: Settings, *, email: str, password: str) -> LoginResult:
    """LIB-AUTH-06 to LIB-AUTH-11.

    Failed logins are committed before the error is raised (LIB-TECH-08 exception),
    so the failure count, the lock and the audit entry survive the error response.
    """
    now = settings.clock.now()
    user = session.scalar(select(User).where(User.email_key == email_key(email)))

    if user is None:
        record_event(
            session,
            at=now,
            event="login_failed",
            entity_type="user",
            entity_id=None,
            actor_user_id=None,
            details={"email": clean_email(email)},
        )
        session.commit()
        raise invalid_credentials()

    if user.locked_until is not None and now < user.locked_until:
        raise ApiError(
            403,
            "ACCOUNT_LOCKED",
            "The account is locked after too many failed logins.",
            {"locked_until": format_datetime(user.locked_until)},
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        record_event(
            session,
            at=now,
            event="login_failed",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=None,
            details={"email": clean_email(email)},
        )
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = now + LOCKOUT_DURATION
            user.failed_login_count = 0
            record_event(
                session,
                at=now,
                event="account_locked",
                entity_type="user",
                entity_id=user.id,
                actor_user_id=None,
                details={"locked_until": {"old": None, "new": format_datetime(user.locked_until)}},
            )
        session.commit()
        raise invalid_credentials()

    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "The account is disabled.")

    token = new_session_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        created_at=now,
        expires_at=now + datetime.timedelta(hours=settings.token_ttl_hours),
        revoked_at=None,
    )
    session.add(auth_session)
    user.failed_login_count = 0
    user.last_login_at = now
    record_event(
        session,
        at=now,
        event="login_succeeded",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        details={"email": clean_email(email)},
    )
    return LoginResult(token=token, session=auth_session, user=user)


def authenticate(session: Session, settings: Settings, token: str | None) -> Authenticated:
    """LIB-AUTH-12, LIB-AUTH-13: resolve a bearer token to its user and session."""
    if not token:
        raise unauthenticated()
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    if auth_session is None or auth_session.revoked_at is not None:
        raise unauthenticated()
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise unauthenticated()
    if settings.clock.now() >= auth_session.expires_at:
        raise ApiError(401, "TOKEN_EXPIRED", "The token has expired.")
    return Authenticated(user=user, session=auth_session)


def logout(session: Session, settings: Settings, auth: Authenticated) -> None:
    """LIB-AUTH-14: revoke the session of the token used."""
    now = settings.clock.now()
    auth.session.revoked_at = now
    record_event(
        session,
        at=now,
        event="logout",
        entity_type="user",
        entity_id=auth.user.id,
        actor_user_id=auth.user.id,
    )


def change_password(
    session: Session,
    settings: Settings,
    auth: Authenticated,
    *,
    current_password: str,
    new_password: str,
) -> None:
    """LIB-AUTH-16. The policy check of new_password is done by the request schema (422) first."""
    now = settings.clock.now()
    user = auth.user
    if not verify_password(current_password, user.password_hash):
        raise invalid_credentials()
    if verify_password(new_password, user.password_hash):
        raise ApiError(
            409, "PASSWORD_UNCHANGED", "The new password must differ from the current one."
        )
    user.password_hash = hash_password(new_password)
    revoke_sessions(session, user, now, except_id=auth.session.id)
    record_event(
        session,
        at=now,
        event="password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
    )


def ensure_bootstrap_admin(session: Session, settings: Settings) -> None:
    """LIB-AUTH-01: create the first administrator when no admin exists."""
    if session.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        return
    email = settings.bootstrap_admin_email
    session.add(
        User(
            email=clean_email(email),
            email_key=email_key(email),
            full_name="Administrator",
            role="admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_active=True,
            failed_login_count=0,
            locked_until=None,
            member_id=None,
            created_at=settings.clock.now(),
            last_login_at=None,
        )
    )
    session.flush()
