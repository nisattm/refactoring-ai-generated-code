"""Shared rules of module 2: tokens, sessions, lockout constants and the bootstrap administrator."""

import datetime
import hashlib
import secrets

from sqlalchemy import orm, select

from lms.audit.log import record_event
from lms.auth.models import AuthSession, User
from lms.auth.passwords import hash_password
from lms.core.settings import Settings
from lms.core.text import clean_email, normalize_text

MAX_FAILED_LOGINS = 5  # LIB-AUTH-09
LOCK_DURATION = datetime.timedelta(minutes=15)


def new_token() -> str:
    # 32 random bytes, base64url without padding: 43 characters (LIB-AUTH-07).
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def open_session(
    db: orm.Session, settings: Settings, user: User, now: datetime.datetime
) -> tuple[str, datetime.datetime]:
    """Create a session for user; return its token and expiry. Earlier sessions stay valid (LIB-AUTH-07)."""
    token = new_token()
    expires_at = now + datetime.timedelta(hours=settings.token_ttl_hours)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    return token, expires_at


def revoke_sessions(
    db: orm.Session,
    user_id: int,
    now: datetime.datetime,
    *,
    keep_session_id: int | None = None,
) -> None:
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    )
    for session in sessions:
        if session.id != keep_session_id:
            session.revoked_at = now


def ensure_bootstrap_admin(db: orm.Session, settings: Settings) -> None:
    """Create the bootstrap administrator when no admin exists (LIB-AUTH-01, LIB-IF-02)."""
    if db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
        return
    email = clean_email(settings.bootstrap_admin_email)
    user = User(
        email=email,
        email_key=normalize_text(email),
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
    db.add(user)
    db.flush()
    record_event(
        db,
        settings.clock,
        "user_created",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "full_name": user.full_name, "role": user.role},
    )
    db.commit()
