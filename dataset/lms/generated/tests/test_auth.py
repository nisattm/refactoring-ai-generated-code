import datetime
import hashlib

import pytest
import sqlalchemy as sa

import lms
from lms.audit.models import AuditEntry
from lms.auth.models import AuthSession, User

ADMIN = {"email": "admin@library.local", "password": "ChangeMe123"}


def err(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


def login(client, email=ADMIN["email"], password=ADMIN["password"]):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def token_of(client, email=ADMIN["email"], password=ADMIN["password"]):
    r = login(client, email, password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_h(client):
    return h(token_of(client))


def make_user(client, admin_h, email="lib@example.com", role="librarian", password="Passw0rd1", name="Lib Rarian"):
    r = client.post(
        "/api/v1/users", headers=admin_h, json={"email": email, "full_name": name, "role": role, "password": password}
    )
    assert r.status_code == 201, r.text
    return r.json()


def audit(app, event=None):
    with app.state.session_factory() as s:
        stmt = sa.select(AuditEntry).order_by(AuditEntry.id)
        if event:
            stmt = stmt.where(AuditEntry.event == event)
        return list(s.scalars(stmt))


def db_user(app, email):
    with app.state.session_factory() as s:
        return s.scalar(sa.select(User).where(User.email == email))


# --- bootstrap ----------------------------------------------------------------


def test_bootstrap_admin_once(settings):
    a = lms.create_app(settings)
    lms.create_app(settings)
    with a.state.session_factory() as s:
        users = s.scalars(sa.select(User)).all()
    assert len(users) == 1 and users[0].role == "admin" and users[0].full_name == "Administrator"
    assert users[0].password_hash.startswith("scrypt$")
    _, salt, digest = users[0].password_hash.split("$")
    assert len(salt) == 32 and len(digest) == 128
    assert hashlib.scrypt(b"ChangeMe123", salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=64).hex() == digest


# --- login --------------------------------------------------------------------


def test_login_success(client, app):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert len(body["access_token"]) == 43 and body["token_type"] == "bearer"
    assert body["expires_at"] == "2026-11-02T21:30:00+03:00"
    u = body["user"]
    assert set(u) == {"id", "email", "full_name", "role", "is_active", "member_id", "created_at", "last_login_at"}
    assert u["role"] == "admin" and u["member_id"] is None and u["created_at"] == "2026-11-02T09:30:00+03:00"
    assert u["last_login_at"] == "2026-11-02T09:30:00+03:00"
    with app.state.session_factory() as s:
        sess = s.scalar(sa.select(AuthSession))
    assert sess.token_hash == hashlib.sha256(body["access_token"].encode()).hexdigest()
    assert [e.event for e in audit(app)] == ["login_succeeded"]


def test_login_email_case_insensitive_and_multiple_sessions(client):
    t1 = token_of(client, email="ADMIN@Library.Local")
    t2 = token_of(client)
    assert t1 != t2
    assert client.get("/api/v1/auth/me", headers=h(t1)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h(t2)).status_code == 200


def test_login_same_response_unknown_and_wrong(client):
    a = err(login(client, email="nobody@example.com"), 401, "INVALID_CREDENTIALS")
    b = err(login(client, password="Wrong1234"), 401, "INVALID_CREDENTIALS")
    assert a["message"] == b["message"]


def test_login_validation(client):
    assert client.post("/api/v1/auth/login", json={"email": "a@b.co"}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x", "z": 1}).status_code == 422


def test_lockout(client, app, clock):
    for i in range(4):
        err(login(client, password="Wrong1234"), 401, "INVALID_CREDENTIALS")
    assert db_user(app, ADMIN["email"]).failed_login_count == 4
    err(login(client, password="Wrong1234"), 401, "INVALID_CREDENTIALS")
    u = db_user(app, ADMIN["email"])
    assert u.failed_login_count == 0 and u.locked_until == clock.now() + datetime.timedelta(minutes=15)
    e = err(login(client), 403, "ACCOUNT_LOCKED")  # correct password, still locked
    assert e["details"]["locked_until"] == "2026-11-02T09:45:00+03:00"
    assert db_user(app, ADMIN["email"]).failed_login_count == 0
    clock.advance(minutes=14, )
    err(login(client), 403, "ACCOUNT_LOCKED")
    clock.advance(minutes=1)
    assert login(client).status_code == 200
    events = [e.event for e in audit(app)]
    assert events.count("login_failed") >= 5 and events.count("account_locked") == 1


def test_success_resets_failed_count(client, app):
    for _ in range(3):
        login(client, password="Wrong1234")
    assert login(client).status_code == 200
    assert db_user(app, ADMIN["email"]).failed_login_count == 0
    for _ in range(4):
        login(client, password="Wrong1234")
    assert login(client).status_code == 200  # not locked: counter was reset


def test_disabled_account(client, admin_h, app):
    u = make_user(client, admin_h)
    assert client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"is_active": False}).status_code == 200
    err(login(client, "lib@example.com", "Passw0rd1"), 403, "ACCOUNT_DISABLED")
    assert db_user(app, "lib@example.com").failed_login_count == 0
    err(login(client, "lib@example.com", "Wrong1234"), 401, "INVALID_CREDENTIALS")
    assert db_user(app, "lib@example.com").failed_login_count == 1


# --- tokens -------------------------------------------------------------------


@pytest.mark.parametrize("header", [None, "", "Bearer", "Token abc", "Bearer a b", "Bearer unknown-token"])
def test_unauthenticated(client, header):
    hd = {} if header is None else {"Authorization": header}
    err(client.get("/api/v1/auth/me", headers=hd), 401, "UNAUTHENTICATED")


def test_expiry_boundary(settings, clock):
    app = lms.create_app(lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=12))
    from fastapi.testclient import TestClient

    c = TestClient(app)
    clock.set(datetime.datetime(2026, 11, 2, 9, 0, tzinfo=clock.now().tzinfo))
    t = token_of(c)
    clock.set(datetime.datetime(2026, 11, 2, 20, 59, 59, tzinfo=clock.now().tzinfo))
    assert c.get("/api/v1/auth/me", headers=h(t)).status_code == 200
    clock.set(datetime.datetime(2026, 11, 2, 21, 0, 0, tzinfo=clock.now().tzinfo))
    err(c.get("/api/v1/auth/me", headers=h(t)), 401, "TOKEN_EXPIRED")


def test_logout(client, app):
    t = token_of(client)
    assert client.post("/api/v1/auth/logout", headers=h(t)).status_code == 204
    err(client.get("/api/v1/auth/me", headers=h(t)), 401, "UNAUTHENTICATED")
    err(client.post("/api/v1/auth/logout"), 401, "UNAUTHENTICATED")
    assert len(audit(app, "logout")) == 1


def test_me(client, admin_h):
    r = client.get("/api/v1/auth/me", headers=admin_h)
    assert r.status_code == 200 and r.json()["email"] == "admin@library.local"
    assert "password_hash" not in r.json()


# --- change password ----------------------------------------------------------


def test_change_password(client, admin_h, app):
    other = h(token_of(client))
    body = {"current_password": "ChangeMe123", "new_password": "NewPass456"}
    assert client.post("/api/v1/auth/change-password", headers=admin_h, json=body).status_code == 204
    assert client.get("/api/v1/auth/me", headers=admin_h).status_code == 200
    err(client.get("/api/v1/auth/me", headers=other), 401, "UNAUTHENTICATED")
    err(login(client), 401, "INVALID_CREDENTIALS")
    assert login(client, password="NewPass456").status_code == 200
    assert len(audit(app, "password_changed")) == 1


def test_change_password_order(client, admin_h, app):
    url = "/api/v1/auth/change-password"
    e = err(client.post(url, headers=admin_h, json={"current_password": "bad", "new_password": "short"}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "new_password"
    for _ in range(6):
        err(client.post(url, headers=admin_h, json={"current_password": "bad", "new_password": "NewPass456"}), 401, "INVALID_CREDENTIALS")
    assert login(client).status_code == 200  # no lockout
    err(client.post(url, headers=admin_h, json={"current_password": "ChangeMe123", "new_password": "ChangeMe123"}), 409, "PASSWORD_UNCHANGED")


@pytest.mark.parametrize("pw", ["short1", "nodigitsatall", "12345678", "a1" * 65, ""])
def test_password_policy(client, admin_h, pw):
    r = client.post("/api/v1/users", headers=admin_h, json={"email": "x@y.zz", "full_name": "X", "role": "librarian", "password": pw})
    e = err(r, 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "password"


def test_password_not_trimmed(client, admin_h):
    make_user(client, admin_h, password="  Pass1  ")  # 10 chars incl. spaces
    assert login(client, "lib@example.com", "  Pass1  ").status_code == 200
    assert login(client, "lib@example.com", "Pass1").status_code == 401


# --- user management ----------------------------------------------------------


def test_create_user(client, admin_h, app):
    u = make_user(client, admin_h, email=" Lib@Example.COM ")
    assert u["email"] == "lib@example.com" and u["role"] == "librarian" and u["is_active"] is True
    assert u["last_login_at"] is None and u["member_id"] is None
    r = client.post("/api/v1/users", headers=admin_h, json={"email": "LIB@example.com", "full_name": "D", "role": "admin", "password": "Passw0rd1"})
    err(r, 409, "CONFLICT")
    ev = audit(app, "user_created")
    assert len(ev) == 1 and "Passw0rd1" not in str(ev[0].details) and ev[0].actor_user_id == 1


@pytest.mark.parametrize(
    "patch",
    [{"role": "member"}, {"email": "no-at.example.com"}, {"email": "a@b"}, {"email": "a@@b.co"}, {"full_name": "  "}, {"role": "boss"}, {"zzz": 1}],
)
def test_create_validation(client, admin_h, patch):
    body = {"email": "x@y.zz", "full_name": "X", "role": "librarian", "password": "Passw0rd1", **patch}
    err(client.post("/api/v1/users", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_permissions(client, admin_h):
    make_user(client, admin_h)
    lib = h(token_of(client, "lib@example.com", "Passw0rd1"))
    body = {"email": "x@y.zz", "full_name": "X", "role": "librarian", "password": "Passw0rd1"}
    err(client.post("/api/v1/users", headers=lib, json=body), 403, "FORBIDDEN")
    err(client.post("/api/v1/users", json=body), 401, "UNAUTHENTICATED")
    err(client.post("/api/v1/users", headers=lib, json={}), 403, "FORBIDDEN")  # 403 before 422
    err(client.get("/api/v1/users", headers=lib), 403, "FORBIDDEN")
    err(client.patch("/api/v1/users/1", headers=lib, json={}), 403, "FORBIDDEN")
    err(client.post("/api/v1/users/1/reset-password", headers=lib, json={"new_password": "Passw0rd2"}), 403, "FORBIDDEN")
    err(client.get("/api/v1/users?page=0"), 401, "UNAUTHENTICATED")


def test_get_user(client, admin_h):
    u = make_user(client, admin_h)
    lib = h(token_of(client, "lib@example.com", "Passw0rd1"))
    assert client.get(f"/api/v1/users/{u['id']}", headers=lib).json() == u | {"last_login_at": client.get(f"/api/v1/users/{u['id']}", headers=lib).json()["last_login_at"]}
    err(client.get("/api/v1/users/1", headers=lib), 403, "FORBIDDEN")
    err(client.get("/api/v1/users/999", headers=lib), 403, "FORBIDDEN")
    assert client.get("/api/v1/users/1", headers=admin_h).status_code == 200
    err(client.get("/api/v1/users/999", headers=admin_h), 404, "NOT_FOUND")
    err(client.get("/api/v1/users/abc", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get("/api/v1/users/0", headers=admin_h), 422, "VALIDATION_ERROR")


def test_list_users(client, admin_h):
    make_user(client, admin_h, "a@x.com", name="Işık Yılmaz")
    make_user(client, admin_h, "b@x.com", role="admin", name="Bob")
    r = client.get("/api/v1/users", headers=admin_h)
    body = r.json()
    assert [u["id"] for u in body["items"]] == [1, 2, 3] and body["total"] == 3 and body["page"] == 1 and body["page_size"] == 20
    assert client.get("/api/v1/users?role=admin", headers=admin_h).json()["total"] == 2
    assert client.get("/api/v1/users?is_active=false", headers=admin_h).json()["total"] == 0
    assert [u["id"] for u in client.get("/api/v1/users?q=IŞIK", headers=admin_h).json()["items"]] == [2]
    assert [u["id"] for u in client.get("/api/v1/users?q=B@X", headers=admin_h).json()["items"]] == [3]
    assert client.get("/api/v1/users?page=2&page_size=2", headers=admin_h).json()["items"][0]["id"] == 3
    assert client.get("/api/v1/users?page=9", headers=admin_h).json()["items"] == []
    err(client.get("/api/v1/users?role=boss", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get("/api/v1/users?page_size=101", headers=admin_h), 422, "VALIDATION_ERROR")


def test_patch_user(client, admin_h, app):
    u = make_user(client, admin_h)
    r = client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"full_name": " New Name ", "role": "admin"})
    assert r.status_code == 200 and r.json()["full_name"] == "New Name" and r.json()["role"] == "admin"
    assert audit(app, "user_updated")[0].details == {
        "full_name": {"old": "Lib Rarian", "new": "New Name"},
        "role": {"old": "librarian", "new": "admin"},
    }
    assert client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={}).status_code == 200
    err(client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"role": "member"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"is_active": None}), 422, "VALIDATION_ERROR")
    err(client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"email": "z@z.zz"}), 422, "VALIDATION_ERROR")
    err(client.patch("/api/v1/users/99", headers=admin_h, json={"role": "admin"}), 404, "NOT_FOUND")
    err(client.patch("/api/v1/users/99", headers=admin_h, json={"role": "member"}), 422, "VALIDATION_ERROR")


def test_member_role_change(client, app, admin_h):
    with app.state.session_factory.begin() as s:
        s.add(User(email="m@x.com", email_key="m@x.com", full_name="M", role="member", password_hash="!", member_id=7,
                   created_at=datetime.datetime.now(datetime.timezone.utc)))
    err(client.patch("/api/v1/users/2", headers=admin_h, json={"role": "librarian"}), 409, "ROLE_CHANGE_NOT_ALLOWED")
    r = client.patch("/api/v1/users/2", headers=admin_h, json={"is_active": False, "full_name": "MM"})
    assert r.status_code == 200 and r.json()["member_id"] == 7
    err(login(client, "m@x.com", "whatever1"), 401, "INVALID_CREDENTIALS")


def test_deactivate_revokes_sessions_and_activate_clears_lock(client, admin_h, app):
    u = make_user(client, admin_h)
    t = token_of(client, "lib@example.com", "Passw0rd1")
    client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"is_active": False})
    err(client.get("/api/v1/auth/me", headers=h(t)), 401, "UNAUTHENTICATED")
    for _ in range(5):
        login(client, "lib@example.com", "Wrong1234")
    client.patch(f"/api/v1/users/{u['id']}", headers=admin_h, json={"is_active": True})
    assert db_user(app, "lib@example.com").locked_until is None
    assert login(client, "lib@example.com", "Passw0rd1").status_code == 200
    assert len(audit(app, "user_deactivated")) == 1 and len(audit(app, "user_activated")) == 1


def test_last_admin_and_self(client, admin_h):
    err(client.patch("/api/v1/users/1", headers=admin_h, json={"role": "librarian"}), 409, "LAST_ADMIN")
    err(client.patch("/api/v1/users/1", headers=admin_h, json={"is_active": False}), 409, "LAST_ADMIN")
    second = make_user(client, admin_h, "a2@x.com", role="admin")
    err(client.patch("/api/v1/users/1", headers=admin_h, json={"is_active": False}), 409, "CANNOT_DEACTIVATE_SELF")
    assert client.patch("/api/v1/users/1", headers=admin_h, json={"role": "librarian"}).status_code == 200
    a2 = h(token_of(client, "a2@x.com", "Passw0rd1"))
    err(client.patch(f"/api/v1/users/{second['id']}", headers=a2, json={"is_active": False}), 409, "LAST_ADMIN")


def test_deactivate_other_admin(client, admin_h):
    second = make_user(client, admin_h, "a2@x.com", role="admin")
    assert client.patch(f"/api/v1/users/{second['id']}", headers=admin_h, json={"is_active": False}).status_code == 200


def test_reset_password(client, admin_h, app):
    u = make_user(client, admin_h)
    t = token_of(client, "lib@example.com", "Passw0rd1")
    for _ in range(5):
        login(client, "lib@example.com", "Wrong1234")
    err(login(client, "lib@example.com", "Passw0rd1"), 403, "ACCOUNT_LOCKED")
    r = client.post(f"/api/v1/users/{u['id']}/reset-password", headers=admin_h, json={"new_password": "Another99"})
    assert r.status_code == 204
    err(client.get("/api/v1/auth/me", headers=h(t)), 401, "UNAUTHENTICATED")
    assert login(client, "lib@example.com", "Another99").status_code == 200
    err(client.post(f"/api/v1/users/{u['id']}/reset-password", headers=admin_h, json={"new_password": "weak"}), 422, "VALIDATION_ERROR")
    err(client.post("/api/v1/users/99/reset-password", headers=admin_h, json={"new_password": "Another99"}), 404, "NOT_FOUND")
    ev = audit(app, "password_reset")
    assert len(ev) == 1 and "Another99" not in str(ev[0].details)


def test_failed_login_audit_persists_and_other_failures_roll_back(client, app, admin_h):
    login(client, "ghost@x.com", "Wrong1234")
    e = audit(app, "login_failed")
    assert len(e) == 1 and e[0].actor_user_id is None and e[0].entity_id is None
    before = len(audit(app))
    err(client.patch("/api/v1/users/1", headers=admin_h, json={"is_active": False}), 409, "LAST_ADMIN")
    assert len(audit(app)) == before


def test_content_type(client, admin_h):
    r = client.post("/api/v1/users", headers={**admin_h, "Content-Type": "text/plain"}, content='{"x":1}')
    err(r, 422, "VALIDATION_ERROR")
