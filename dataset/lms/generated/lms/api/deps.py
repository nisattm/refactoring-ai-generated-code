"""Authentication and permission dependencies (LIB-AUTH-12, LIB-AUTH-24)."""
import datetime
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .. import auth
from ..auth.models import User, UserSession
from ..core import db
from ..core.errors import forbidden


@dataclass
class Auth:
    user: User
    session: UserSession


def now_of(request: Request) -> datetime.datetime:
    return request.app.state.settings.clock.now()


def current_auth(request: Request, session: Session = Depends(db.get_session)) -> Auth:
    user, sess = auth.authenticate(session, request.headers.get("authorization"), now_of(request))
    return Auth(user, sess)


def current_user(a: Auth = Depends(current_auth)) -> User:
    return a.user


def require_roles(*roles: str):
    def dep(a: Auth = Depends(current_auth)) -> User:
        if a.user.role not in roles:
            raise forbidden("Insufficient permissions")
        return a.user

    return dep


require_admin = require_roles("admin")
