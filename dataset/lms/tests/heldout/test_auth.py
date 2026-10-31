"""Heldout tests: module 2 (Identity and access). Generated from cases/auth.md."""
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


def test_t_auth_02_b(client, admin):
    """T-AUTH-02-b (LIB-AUTH-02): 422 VALIDATION_ERROR with field password each"""
    for i, pw in enumerate(("abcdef1", "abcdefgh", "12345678", "a" * 128 + "1")):
        r = client.post("/api/v1/users", headers=admin, json={"email": f"bad{i}@library.local", "full_name": "S", "role": "librarian", "password": pw})
        assert r.status_code == 422, pw
        assert "password" in {f["field"] for f in r.json()["error"]["details"]["fields"]}


def test_t_auth_04_a(client, admin):
    """T-AUTH-04-a (LIB-AUTH-04): 422 VALIDATION_ERROR"""
    r = client.post("/api/v1/users", headers=admin, json={"email": "m@library.local", "full_name": "M", "role": "member", "password": "Passw0rd1"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_t_auth_06_a(client, librarian):
    """T-AUTH-06-a (LIB-AUTH-06): 200 with access_token, token_type bearer, expires_at, user (no password fields)"""
    body = raw_login(client, *LIB).json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["expires_at"]
    assert body["user"]["email"] == "lib@library.local" and body["user"]["role"] == "librarian"
    assert "password" not in str(body["user"]).lower()


def test_t_auth_08_a(client, librarian):
    """T-AUTH-08-a (LIB-AUTH-08): Both 401 INVALID_CREDENTIALS with the same body"""
    r1 = raw_login(client, "nobody@library.local", "Wrong0000")
    r2 = raw_login(client, "lib@library.local", "Wrong0000")
    assert r1.status_code == r2.status_code == 401
    assert error_code(r1) == "INVALID_CREDENTIALS" and r1.json() == r2.json()


def test_t_auth_09_b(client, clock, librarian):
    """T-AUTH-09-b (LIB-AUTH-09): 09:14 403 ACCOUNT_LOCKED; 09:15 success"""
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    clock.advance(minutes=14)
    assert raw_login(client, *LIB).status_code == 403
    clock.advance(minutes=1)
    assert raw_login(client, *LIB).status_code == 200


def test_t_auth_09_d(client, clock, librarian):
    """T-AUTH-09-d (LIB-AUTH-09): Attempts while locked return 403 and do not count; after 15 min success"""
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    for _ in range(6):
        r = raw_login(client, "lib@library.local", "Wrong0000")
        assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    clock.advance(minutes=15)
    assert raw_login(client, *LIB).status_code == 200


def test_t_auth_10_a(client, admin):
    """T-AUTH-10-a (LIB-AUTH-10): Correct: 403 ACCOUNT_DISABLED; wrong: 401 INVALID_CREDENTIALS"""
    uid = new_user(client, admin, email="off@library.local")["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = raw_login(client, "off@library.local", "Passw0rd1")
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_DISABLED"
    r = raw_login(client, "off@library.local", "Wrong0000")
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"


def test_t_auth_12_b(client, clock, librarian):
    """T-AUTH-12-b (LIB-AUTH-12): 401 TOKEN_EXPIRED"""
    headers = login(client, *LIB)
    clock.advance(hours=12)
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401 and error_code(r) == "TOKEN_EXPIRED"


def test_t_auth_14_a(client, librarian):
    """T-AUTH-14-a (LIB-AUTH-14): 204; reuse 401 UNAUTHENTICATED; the other session still works"""
    other = login(client, *LIB)
    assert client.post("/api/v1/auth/logout", headers=librarian).status_code == 204
    r = client.get("/api/v1/auth/me", headers=librarian)
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
    assert client.get("/api/v1/auth/me", headers=other).status_code == 200


def test_t_auth_16_b(client, librarian):
    """T-AUTH-16-b (LIB-AUTH-16): 401 INVALID_CREDENTIALS each; login still works (no lockout)"""
    for _ in range(5):
        r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Wrong0000", "new_password": "NewPassw0rd"})
        assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
    assert raw_login(client, *LIB).status_code == 200


def test_t_auth_16_d(client, librarian):
    """T-AUTH-16-d (LIB-AUTH-16): 422 VALIDATION_ERROR (policy checked first)"""
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Wrong0000", "new_password": "nodigitshere"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_t_auth_17_b(client, librarian):
    """T-AUTH-17-b (LIB-AUTH-17): 403 FORBIDDEN"""
    r = client.post("/api/v1/users", headers=librarian, json={"email": "z@library.local", "full_name": "Z", "role": "librarian", "password": "Passw0rd1"})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_t_auth_18_a(client, admin, librarian):
    """T-AUTH-18-a (LIB-AUTH-18): Only matching users"""
    uid = new_user(client, admin, email="gone@library.local")["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    roles = {u["role"] for u in client.get("/api/v1/users", headers=admin, params={"role": "librarian"}).json()["items"]}
    assert roles == {"librarian"}
    inactive = [u["email"] for u in client.get("/api/v1/users", headers=admin, params={"is_active": "false"}).json()["items"]]
    assert inactive == ["gone@library.local"]
    found = [u["email"] for u in client.get("/api/v1/users", headers=admin, params={"q": "LIB@"}).json()["items"]]
    assert found == ["lib@library.local"]


def test_t_auth_19_b(client, librarian):
    """T-AUTH-19-b (LIB-AUTH-19): 403 FORBIDDEN both (ownership before existence)"""
    for uid in (1, 9999):
        r = client.get(f"/api/v1/users/{uid}", headers=librarian)
        assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_t_auth_20_b(client, admin):
    """T-AUTH-20-b (LIB-AUTH-20): 422 VALIDATION_ERROR"""
    uid = new_user(client, admin)["id"]
    assert client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "member"}).status_code == 422


def test_t_auth_21_b(client, admin, librarian):
    """T-AUTH-21-b (LIB-AUTH-21): Login succeeds at once (lock cleared)"""
    uid = user_id_of(client, admin, "lib@library.local")
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": True})
    assert raw_login(client, *LIB).status_code == 200


def test_t_auth_22_b(client, admin):
    """T-AUTH-22-b (LIB-AUTH-22): 409 CANNOT_DEACTIVATE_SELF; then 200"""
    second = new_user(client, admin, email="admin2@library.local", role="admin")["id"]
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"is_active": False})
    assert r.status_code == 409 and error_code(r) == "CANNOT_DEACTIVATE_SELF"
    assert client.patch(f"/api/v1/users/{second}", headers=admin, json={"is_active": False}).status_code == 200


def test_t_auth_23_b(client, admin, librarian):
    """T-AUTH-23-b (LIB-AUTH-23): 403 FORBIDDEN"""
    r = client.post("/api/v1/users/1/reset-password", headers=librarian, json={"new_password": "Reset1234"})
    assert r.status_code == 403


def test_t_auth_24_b(client):
    """T-AUTH-24-b (LIB-AUTH-24): 401 UNAUTHENTICATED"""
    r = client.get("/api/v1/books")
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
