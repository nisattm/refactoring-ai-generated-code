"""Feedback tests: module 2 (Identity and access). Generated from cases/auth.md."""
from datetime import datetime, timedelta, timezone

from support.api import create_branch, error_code, login, member_headers, register_member

TR = timezone(timedelta(hours=3))
LIB = ("lib@library.local", "Librarian123")


def raw_login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def new_user(client, admin, email="staff@library.local", role="librarian", password="Passw0rd1"):
    r = client.post("/api/v1/users", headers=admin, json={"email": email, "full_name": "Staff", "role": role, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def user_id_of(client, admin, email):
    items = client.get("/api/v1/users", headers=admin, params={"q": email}).json()["items"]
    return [u for u in items if u["email"] == email][0]["id"]


def test_t_auth_01_a(client):
    """T-AUTH-01-a (LIB-AUTH-01): 200; user.role admin, full_name Administrator, active"""
    r = raw_login(client, "admin@library.local", "ChangeMe123")
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["role"] == "admin" and user["full_name"] == "Administrator" and user["is_active"] is True


def test_t_auth_02_a(client, admin):
    """T-AUTH-02-a (LIB-AUTH-02): Both accepted"""
    new_user(client, admin, email="p8@library.local", password="abcdefg1")
    new_user(client, admin, email="p128@library.local", password="a" * 127 + "1")


def test_t_auth_05_a(client, admin, librarian):
    """T-AUTH-05-a (LIB-AUTH-05): 409 CONFLICT"""
    r = client.post("/api/v1/users", headers=admin, json={"email": "LIB@library.local", "full_name": "X", "role": "librarian", "password": "Passw0rd1"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"


def test_t_auth_07_a(client, librarian):
    """T-AUTH-07-a (LIB-AUTH-07): Two different 43-character URL-safe tokens; both valid"""
    t1 = raw_login(client, *LIB).json()["access_token"]
    t2 = raw_login(client, *LIB).json()["access_token"]
    assert t1 != t2 and len(t1) == 43 and len(t2) == 43
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(t1) <= allowed
    for t in (t1, t2):
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"}).status_code == 200


def test_t_auth_09_a(client, librarian):
    """T-AUTH-09-a (LIB-AUTH-09): Fifth: 401; then 403 ACCOUNT_LOCKED with details.locked_until 2026-11-02T09:15:00+03:00"""
    for _ in range(5):
        assert raw_login(client, "lib@library.local", "Wrong0000").status_code == 401
    r = raw_login(client, *LIB)
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    assert datetime.fromisoformat(r.json()["error"]["details"]["locked_until"]) == datetime(2026, 11, 2, 9, 15, tzinfo=TR)


def test_t_auth_09_c(client, librarian):
    """T-AUTH-09-c (LIB-AUTH-09): Last login succeeds (success resets the counter)"""
    for _ in range(4):
        raw_login(client, "lib@library.local", "Wrong0000")
    assert raw_login(client, *LIB).status_code == 200
    for _ in range(4):
        raw_login(client, "lib@library.local", "Wrong0000")
    assert raw_login(client, *LIB).status_code == 200


def test_t_auth_11_a(client, admin):
    """T-AUTH-11-a (LIB-AUTH-11): 403 ACCOUNT_LOCKED (lock is checked before active)"""
    uid = new_user(client, admin, email="both@library.local")["id"]
    for _ in range(5):
        raw_login(client, "both@library.local", "Wrong0000")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = raw_login(client, "both@library.local", "Passw0rd1")
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"


def test_t_auth_12_a(client):
    """T-AUTH-12-a (LIB-AUTH-12): 401 UNAUTHENTICATED both"""
    for headers in ({}, {"Authorization": "Bearer unknown-token"}):
        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"


def test_t_auth_13_a(client, clock, librarian):
    """T-AUTH-13-a (LIB-AUTH-13): 200, then 401 TOKEN_EXPIRED"""
    headers = login(client, *LIB)
    clock.set(datetime(2026, 11, 2, 20, 59, 59, tzinfo=TR))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    clock.set(datetime(2026, 11, 2, 21, 0, 0, tzinfo=TR))
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401 and error_code(r) == "TOKEN_EXPIRED"


def test_t_auth_15_a(client, librarian):
    """T-AUTH-15-a (LIB-AUTH-15): UserOut with exactly the documented fields"""
    me = client.get("/api/v1/auth/me", headers=librarian).json()
    assert set(me) == {"id", "email", "full_name", "role", "is_active", "member_id", "created_at", "last_login_at"}
    assert me["email"] == "lib@library.local" and me["member_id"] is None and me["last_login_at"] is not None


def test_t_auth_16_a(client, librarian):
    """T-AUTH-16-a (LIB-AUTH-16): 204; session 1 valid, session 2 revoked; new password works, old does not"""
    other = login(client, *LIB)
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Librarian123", "new_password": "NewPassw0rd"})
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=librarian).status_code == 200
    assert client.get("/api/v1/auth/me", headers=other).status_code == 401
    assert raw_login(client, "lib@library.local", "NewPassw0rd").status_code == 200
    assert raw_login(client, *LIB).status_code == 401


def test_t_auth_16_c(client, librarian):
    """T-AUTH-16-c (LIB-AUTH-16): 409 PASSWORD_UNCHANGED"""
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Librarian123", "new_password": "Librarian123"})
    assert r.status_code == 409 and error_code(r) == "PASSWORD_UNCHANGED"


def test_t_auth_17_a(client, admin):
    """T-AUTH-17-a (LIB-AUTH-17): 201 with UserOut, role admin"""
    user = new_user(client, admin, email="admin2@library.local", role="admin")
    assert user["role"] == "admin" and user["is_active"] is True and "id" in user


def test_t_auth_19_a(client, librarian, branch_a):
    """T-AUTH-19-a (LIB-AUTH-19): 200 with own UserOut; member_id set"""
    member = register_member(client, librarian, home_branch_id=branch_a["id"])
    mh = member_headers(client, member)
    me = client.get("/api/v1/auth/me", headers=mh).json()
    r = client.get(f"/api/v1/users/{me['id']}", headers=mh)
    assert r.status_code == 200 and r.json()["member_id"] == member["id"]


def test_t_auth_19_c(client, admin):
    """T-AUTH-19-c (LIB-AUTH-19): 404 NOT_FOUND"""
    r = client.get("/api/v1/users/9999", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


def test_t_auth_20_a(client, admin):
    """T-AUTH-20-a (LIB-AUTH-20): 200 with new values"""
    uid = new_user(client, admin)["id"]
    r = client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "admin", "full_name": "Chief"})
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["full_name"] == "Chief"


def test_t_auth_20_c(client, admin, librarian, branch_a):
    """T-AUTH-20-c (LIB-AUTH-20): 409 ROLE_CHANGE_NOT_ALLOWED"""
    member = register_member(client, librarian, home_branch_id=branch_a["id"])
    uid = user_id_of(client, admin, member["email"])
    r = client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "librarian"})
    assert r.status_code == 409 and error_code(r) == "ROLE_CHANGE_NOT_ALLOWED"


def test_t_auth_21_a(client, admin, librarian):
    """T-AUTH-21-a (LIB-AUTH-21): Its token returns 401 UNAUTHENTICATED"""
    uid = user_id_of(client, admin, "lib@library.local")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = client.get("/api/v1/auth/me", headers=librarian)
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"


def test_t_auth_22_a(client, admin):
    """T-AUTH-22-a (LIB-AUTH-22): 409 LAST_ADMIN; 409 (LAST_ADMIN or CANNOT_DEACTIVATE_SELF)"""
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"role": "librarian"})
    assert r.status_code == 409 and error_code(r) == "LAST_ADMIN"
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"is_active": False})
    assert r.status_code == 409 and error_code(r) in {"LAST_ADMIN", "CANNOT_DEACTIVATE_SELF"}


def test_t_auth_23_a(client, admin, librarian):
    """T-AUTH-23-a (LIB-AUTH-23): 204; old session 401; new password logs in at once"""
    uid = user_id_of(client, admin, "lib@library.local")
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    r = client.post(f"/api/v1/users/{uid}/reset-password", headers=admin, json={"new_password": "Reset1234"})
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=librarian).status_code == 401
    assert raw_login(client, "lib@library.local", "Reset1234").status_code == 200


def test_t_auth_24_a(client, librarian, branch_a):
    """T-AUTH-24-a (LIB-AUTH-24): 403 FORBIDDEN both"""
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.get("/api/v1/users", headers=mh).status_code == 403
    r = client.post("/api/v1/branches", headers=mh, json={"code": "Z", "name": "Z", "address": ""})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_t_auth_25_a(client, librarian, branch_a):
    """T-AUTH-25-a (LIB-AUTH-25): 403 FORBIDDEN; 404 NOT_FOUND"""
    a = register_member(client, librarian, home_branch_id=branch_a["id"])
    b = register_member(client, librarian, home_branch_id=branch_a["id"])
    ha = member_headers(client, a)
    r = client.get(f"/api/v1/members/{b['id']}", headers=ha)
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
    r = client.get("/api/v1/members/9999", headers=ha)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
