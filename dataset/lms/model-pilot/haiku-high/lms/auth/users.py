"""User management by administrators (section 6.4)."""

import datetime
import typing

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lms.audit.service import record_event
from lms.auth.credentials import hash_password
from lms.auth.models import User
from lms.auth.service import revoke_sessions
from lms.core.errors import ApiError
from lms.core.localtime import format_datetime
from lms.core.text import clean_email, email_key, normalize


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "The user does not exist.")
    return user


def _json_value(value: typing.Any) -> typing.Any:
    """Audit details hold JSON values only (LIB-AUD-02)."""
    if isinstance(value, datetime.datetime):
        return format_datetime(value)
    return value


def create_user(
    session: Session,
    *,
    actor: User,
    now: datetime.datetime,
    email: str,
    full_name: str,
    role: str,
    password: str,
) -> User:
    """LIB-AUTH-17. The request schema has already checked the formats and the password policy."""
    key = email_key(email)
    if session.scalar(select(User.id).where(User.email_key == key)) is not None:
        raise ApiError(409, "CONFLICT", "An account with this e-mail address already exists.")
    stored_email = clean_email(email)
    user = User(
        email=stored_email,
        email_key=key,
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
        is_active=True,
        failed_login_count=0,
        locked_until=None,
        member_id=None,
        created_at=now,
        last_login_at=None,
    )
    session.add(user)
    session.flush()
    record_event(
        session,
        at=now,
        event="user_created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor.id,
        details={"email": stored_email, "full_name": full_name, "role": role},
    )
    return user


def list_users(
    session: Session,
    *,
    role: str | None,
    is_active: bool | None,
    q: str | None,
) -> list[User]:
    """LIB-AUTH-18: filtered users ordered by id. The text filter uses LIB-COM-30 normalization."""
    statement = select(User).order_by(User.id)
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    users = list(session.scalars(statement))
    if q is None or not q.strip():
        return users
    needle = normalize(q.strip())
    return [
        user
        for user in users
        if needle in normalize(user.email) or needle in normalize(user.full_name)
    ]


def update_user(
    session: Session,
    *,
    actor: User,
    target: User,
    now: datetime.datetime,
    full_name: str | None,
    role: str | None,
    is_active: bool | None,
) -> User:
    """LIB-AUTH-20 to LIB-AUTH-22. Only the fields that are given are changed."""
    # LIB-AUTH-20: a member's role cannot be changed here; "member" itself is rejected by the schema.
    if role is not None and target.role == "member":
        raise ApiError(409, "ROLE_CHANGE_NOT_ALLOWED", "The role of a member cannot be changed.")
    # LIB-AUTH-22
    if is_active is False and target.id == actor.id:
        raise ApiError(
            409, "CANNOT_DEACTIVATE_SELF", "An administrator cannot deactivate their own account."
        )
    was_active_admin = target.role == "admin" and target.is_active
    will_be_active_admin = (role or target.role) == "admin" and (
        target.is_active if is_active is None else is_active
    )
    if was_active_admin and not will_be_active_admin:
        other_active_admins = session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True), User.id != target.id)
        )
        if not other_active_admins:
            raise ApiError(409, "LAST_ADMIN", "At least one active administrator must remain.")

    changes: dict[str, dict[str, typing.Any]] = {}

    def change(field: str, new: typing.Any) -> None:
        old = getattr(target, field)
        if old != new:
            changes[field] = {"old": _json_value(old), "new": _json_value(new)}
            setattr(target, field, new)

    if full_name is not None:
        change("full_name", full_name)
    if role is not None:
        change("role", role)
    if is_active is not None:
        change("is_active", is_active)
        if is_active:
            # LIB-AUTH-21: activation also clears the lock.
            change("locked_until", None)
            change("failed_login_count", 0)
        else:
            revoke_sessions(session, target, now)

    activation_change = changes.pop("is_active", None)
    if activation_change is not None:
        event = "user_activated" if target.is_active else "user_deactivated"
        record_event(
            session,
            at=now,
            event=event,
            entity_type="user",
            entity_id=target.id,
            actor_user_id=actor.id,
            details={"is_active": activation_change},
        )
    if changes:
        record_event(
            session,
            at=now,
            event="user_updated",
            entity_type="user",
            entity_id=target.id,
            actor_user_id=actor.id,
            details=changes,
        )
    return target


def reset_password(
    session: Session,
    *,
    actor: User,
    target: User,
    now: datetime.datetime,
    new_password: str,
) -> None:
    """LIB-AUTH-23."""
    target.password_hash = hash_password(new_password)
    target.locked_until = None
    target.failed_login_count = 0
    revoke_sessions(session, target, now)
    record_event(
        session,
        at=now,
        event="password_reset",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=actor.id,
    )
