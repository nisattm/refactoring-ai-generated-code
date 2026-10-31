"""User management (LIB-AUTH-17 to LIB-AUTH-23)."""
from fastapi import APIRouter, Body, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, auth
from ..auth.models import User
from ..core import db
from ..core.errors import ApiError, business_rule, conflict, forbidden, not_found
from ..core.pagination import page_params, paginate
from ..core.text import normalize
from . import validation as v
from .auth import user_out
from .deps import current_user, now_of, require_admin

router = APIRouter(prefix="/api/v1/users")

STAFF_ROLES = ("librarian", "admin")


def _role(body: dict, fields: list) -> str | None:
    r = body.get("role")
    if not isinstance(r, str) or r not in STAFF_ROLES:
        problem = "role member is not allowed here" if r == "member" else "must be librarian or admin"
        fields.append({"field": "role", "problem": problem})
        return None
    return r


def _user_id(raw: str) -> int:
    try:
        if not raw.lstrip("+-").isdigit():
            raise ValueError
        return int(raw)
    except ValueError:
        raise v.ValidationFailed([{"field": "user_id", "problem": "must be an integer"}])


@router.post("", status_code=201)
def create_user(
    request: Request,
    body: dict = Body(...),
    admin: User = Depends(require_admin),
    session: Session = Depends(db.get_session),
):
    fields: list = []
    keys = {"email", "full_name", "role", "password"}
    v.check_keys(body, keys, keys, fields)
    email = v.email(body, "email", fields) if "email" in body else None
    name = v.text(body, "full_name", fields) if "full_name" in body else None
    role = _role(body, fields) if "role" in body else None
    pw = v.password(body, "password", fields) if "password" in body else None
    v.fail(fields)

    key = auth.email_key(email)
    if session.scalars(select(User.id).where(User.email_key == key)).first() is not None:
        raise conflict("A user with this e-mail already exists", {"field": "email"})
    now = now_of(request)
    user = User(
        email=email.lower(),
        email_key=key,
        full_name=name,
        role=role,
        password_hash=auth.hash_password(pw),
        is_active=True,
        created_at=now,
    )
    session.add(user)
    session.flush()
    audit.record(
        session, now, "user_created", admin.id, "user", user.id,
        {"email": user.email, "full_name": name, "role": role},
    )
    return user_out(user)


@router.get("")
def list_users(
    role: str | None = Query(None),
    is_active: str | None = Query(None),
    q: str | None = Query(None),
    pp: tuple[int, int] = Depends(page_params),
    admin: User = Depends(require_admin),
    session: Session = Depends(db.get_session),
):
    fields: list = []
    if role is not None and role not in auth.ROLES:
        fields.append({"field": "role", "problem": "must be member, librarian or admin"})
    active = None
    if is_active is not None:
        if is_active in ("true", "false"):
            active = is_active == "true"
        else:
            fields.append({"field": "is_active", "problem": "must be true or false"})
    v.fail(fields)

    stmt = select(User).order_by(User.id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active == active)
    users = session.scalars(stmt).all()
    if q is not None and q.strip():
        needle = normalize(q.strip())
        users = [u for u in users if needle in normalize(u.email) or needle in normalize(u.full_name)]
    page, size = pp
    result = paginate(users, page, size)
    result["items"] = [user_out(u) for u in result["items"]]
    return result


@router.get("/{user_id}")
def get_user(
    user_id: str,
    me: User = Depends(current_user),
    session: Session = Depends(db.get_session),
):
    if me.role != "admin":
        if user_id != str(me.id):
            raise forbidden("You may only read your own record")
        return user_out(me)
    uid = _user_id(user_id)
    user = session.get(User, uid)
    if user is None:
        raise not_found()
    return user_out(user)


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    request: Request,
    body: dict = Body(...),
    admin: User = Depends(require_admin),
    session: Session = Depends(db.get_session),
):
    uid = None
    fields: list = []
    v.check_keys(body, {"full_name", "role", "is_active"}, set(), fields)
    name = v.text(body, "full_name", fields) if "full_name" in body else None
    role = _role(body, fields) if "role" in body else None
    active = None
    if "is_active" in body:
        if isinstance(body["is_active"], bool):
            active = body["is_active"]
        else:
            fields.append({"field": "is_active", "problem": "must be a boolean"})
    try:
        uid = _user_id(user_id)
    except v.ValidationFailed as e:
        fields.extend(e.details["fields"])
    v.fail(fields)

    user = session.get(User, uid)
    if user is None:
        raise not_found()
    if "role" in body and user.role == "member":
        raise business_rule("ROLE_CHANGE_NOT_ALLOWED", "The role of a member user cannot be changed")

    now = now_of(request)
    deactivating = active is False and user.is_active
    demoting = role is not None and role != "admin" and user.role == "admin"
    if user.role == "admin" and user.is_active and (deactivating or demoting):
        others = session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active, User.id != user.id)
        )
        if not others:
            raise business_rule("LAST_ADMIN", "At least one active administrator is required")
    if deactivating and user.id == admin.id:
        raise business_rule("CANNOT_DEACTIVATE_SELF", "You cannot deactivate your own account")

    changes: dict = {}
    if name is not None and name != user.full_name:
        changes["full_name"] = {"old": user.full_name, "new": name}
        user.full_name = name
    if role is not None and role != user.role:
        changes["role"] = {"old": user.role, "new": role}
        user.role = role
    if changes:
        audit.record(session, now, "user_updated", admin.id, "user", user.id, changes)

    if active is not None and active != user.is_active:
        user.is_active = active
        if active:
            user.locked_until = None
            user.failed_login_count = 0
        else:
            auth.revoke_sessions(session, user.id, now)
        audit.record(
            session, now, "user_activated" if active else "user_deactivated", admin.id, "user", user.id,
            {"is_active": {"old": not active, "new": active}},
        )
    elif active:
        # Setting is_active to true also clears lockout state (LIB-AUTH-21).
        user.locked_until = None
        user.failed_login_count = 0
    session.flush()
    return user_out(user)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: str,
    request: Request,
    body: dict = Body(...),
    admin: User = Depends(require_admin),
    session: Session = Depends(db.get_session),
):
    fields: list = []
    v.check_keys(body, {"new_password"}, {"new_password"}, fields)
    if "new_password" in body:
        v.password(body, "new_password", fields)
    uid = None
    try:
        uid = _user_id(user_id)
    except v.ValidationFailed as e:
        fields.extend(e.details["fields"])
    v.fail(fields)

    user = session.get(User, uid)
    if user is None:
        raise not_found()
    now = now_of(request)
    user.password_hash = auth.hash_password(body["new_password"])
    user.locked_until = None
    user.failed_login_count = 0
    auth.revoke_sessions(session, user.id, now)
    audit.record(session, now, "password_reset", admin.id, "user", user.id, {})
    return Response(status_code=204)
