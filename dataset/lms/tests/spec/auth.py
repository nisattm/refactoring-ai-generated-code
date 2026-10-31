MODULE = "auth"
TITLE = "module 2 (Identity and access)"

HEADER = '''
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
'''


def static(cid, req, inp, exp):
    return dict(id=cid, req=req, type="Static", input=inp, expected=exp, code=None)


CASES = [
    dict(id="T-AUTH-01-a", req="LIB-AUTH-01", type="Normal", input="Fresh application; login with the bootstrap credentials", expected="200; `user.role` `admin`, `full_name` `Administrator`, active", code='''
def TEST(client):
    r = raw_login(client, "admin@library.local", "ChangeMe123")
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["role"] == "admin" and user["full_name"] == "Administrator" and user["is_active"] is True
'''),
    dict(id="T-AUTH-02-a", req="LIB-AUTH-02", type="Boundary", input="Passwords `abcdefg1` (8 chars) and 128 chars with a digit", expected="Both accepted", code='''
def TEST(client, admin):
    new_user(client, admin, email="p8@library.local", password="abcdefg1")
    new_user(client, admin, email="p128@library.local", password="a" * 127 + "1")
'''),
    dict(id="T-AUTH-02-b", req="LIB-AUTH-02", type="Boundary", input="Passwords `abcdef1` (7), `abcdefgh` (no digit), `12345678` (no letter), 129 chars", expected="`422 VALIDATION_ERROR` with field `password` each", code='''
def TEST(client, admin):
    for i, pw in enumerate(("abcdef1", "abcdefgh", "12345678", "a" * 128 + "1")):
        r = client.post("/api/v1/users", headers=admin, json={"email": f"bad{i}@library.local", "full_name": "S", "role": "librarian", "password": pw})
        assert r.status_code == 422, pw
        assert "password" in {f["field"] for f in r.json()["error"]["details"]["fields"]}
'''),
    static("T-AUTH-03-a", "LIB-AUTH-03", "Database row of a user", "`password_hash` matches `scrypt$<32 hex>$<128 hex>` and verifies with n=16384, r=8, p=1, dklen=64"),
    dict(id="T-AUTH-04-a", req="LIB-AUTH-04", type="Error", input="`POST /api/v1/users` with `role` `member`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    r = client.post("/api/v1/users", headers=admin, json={"email": "m@library.local", "full_name": "M", "role": "member", "password": "Passw0rd1"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
    dict(id="T-AUTH-05-a", req="LIB-AUTH-05", type="Error", input="Create a user with the librarian's e-mail in upper case", expected="`409 CONFLICT`", code='''
def TEST(client, admin, librarian):
    r = client.post("/api/v1/users", headers=admin, json={"email": "LIB@library.local", "full_name": "X", "role": "librarian", "password": "Passw0rd1"})
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
'''),
    dict(id="T-AUTH-06-a", req="LIB-AUTH-06", type="Normal", input="Librarian logs in", expected="200 with `access_token`, `token_type` `bearer`, `expires_at`, `user` (no password fields)", code='''
def TEST(client, librarian):
    body = raw_login(client, *LIB).json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["expires_at"]
    assert body["user"]["email"] == "lib@library.local" and body["user"]["role"] == "librarian"
    assert "password" not in str(body["user"]).lower()
'''),
    dict(id="T-AUTH-07-a", req="LIB-AUTH-07", type="Normal", input="Two logins of the librarian", expected="Two different 43-character URL-safe tokens; both valid", code='''
def TEST(client, librarian):
    t1 = raw_login(client, *LIB).json()["access_token"]
    t2 = raw_login(client, *LIB).json()["access_token"]
    assert t1 != t2 and len(t1) == 43 and len(t2) == 43
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(t1) <= allowed
    for t in (t1, t2):
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"}).status_code == 200
'''),
    dict(id="T-AUTH-08-a", req="LIB-AUTH-08", type="Error", input="Unknown e-mail; known e-mail with wrong password", expected="Both `401 INVALID_CREDENTIALS` with the same body", code='''
def TEST(client, librarian):
    r1 = raw_login(client, "nobody@library.local", "Wrong0000")
    r2 = raw_login(client, "lib@library.local", "Wrong0000")
    assert r1.status_code == r2.status_code == 401
    assert error_code(r1) == "INVALID_CREDENTIALS" and r1.json() == r2.json()
'''),
    dict(id="T-AUTH-09-a", req="LIB-AUTH-09", type="Boundary", input="Five wrong passwords at 09:00; then the correct password", expected="Fifth: 401; then `403 ACCOUNT_LOCKED` with `details.locked_until` 2026-11-02T09:15:00+03:00", code='''
def TEST(client, librarian):
    for _ in range(5):
        assert raw_login(client, "lib@library.local", "Wrong0000").status_code == 401
    r = raw_login(client, *LIB)
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    assert datetime.fromisoformat(r.json()["error"]["details"]["locked_until"]) == datetime(2026, 11, 2, 9, 15, tzinfo=TR)
'''),
    dict(id="T-AUTH-09-b", req="LIB-AUTH-09", type="Boundary", input="Locked at 09:00; login at 09:14 and at 09:15", expected="09:14 `403 ACCOUNT_LOCKED`; 09:15 success", code='''
def TEST(client, clock, librarian):
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    clock.advance(minutes=14)
    assert raw_login(client, *LIB).status_code == 403
    clock.advance(minutes=1)
    assert raw_login(client, *LIB).status_code == 200
'''),
    dict(id="T-AUTH-09-c", req="LIB-AUTH-09", type="Normal", input="Four wrong, one correct, four wrong, then correct", expected="Last login succeeds (success resets the counter)", code='''
def TEST(client, librarian):
    for _ in range(4):
        raw_login(client, "lib@library.local", "Wrong0000")
    assert raw_login(client, *LIB).status_code == 200
    for _ in range(4):
        raw_login(client, "lib@library.local", "Wrong0000")
    assert raw_login(client, *LIB).status_code == 200
'''),
    dict(id="T-AUTH-09-d", req="LIB-AUTH-09", type="Boundary", input="Locked; wrong passwords while locked; login after 15 minutes", expected="Attempts while locked return 403 and do not count; after 15 min success", code='''
def TEST(client, clock, librarian):
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    for _ in range(6):
        r = raw_login(client, "lib@library.local", "Wrong0000")
        assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    clock.advance(minutes=15)
    assert raw_login(client, *LIB).status_code == 200
'''),
    dict(id="T-AUTH-10-a", req="LIB-AUTH-10", type="Error", input="Admin deactivates a librarian; login with correct and with wrong password", expected="Correct: `403 ACCOUNT_DISABLED`; wrong: `401 INVALID_CREDENTIALS`", code='''
def TEST(client, admin):
    uid = new_user(client, admin, email="off@library.local")["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = raw_login(client, "off@library.local", "Passw0rd1")
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_DISABLED"
    r = raw_login(client, "off@library.local", "Wrong0000")
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
'''),
    dict(id="T-AUTH-11-a", req="LIB-AUTH-11", type="Boundary", input="Lock a librarian (5 failures), then deactivate it; login with the correct password", expected="`403 ACCOUNT_LOCKED` (lock is checked before active)", code='''
def TEST(client, admin):
    uid = new_user(client, admin, email="both@library.local")["id"]
    for _ in range(5):
        raw_login(client, "both@library.local", "Wrong0000")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = raw_login(client, "both@library.local", "Passw0rd1")
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
'''),
    dict(id="T-AUTH-12-a", req="LIB-AUTH-12", type="Error", input="`GET /api/v1/auth/me` without header; with `Bearer unknown`", expected="`401 UNAUTHENTICATED` both", code='''
def TEST(client):
    for headers in ({}, {"Authorization": "Bearer unknown-token"}):
        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
'''),
    dict(id="T-AUTH-12-b", req="LIB-AUTH-12", type="Error", input="Token used 12 hours after login", expected="`401 TOKEN_EXPIRED`", code='''
def TEST(client, clock, librarian):
    clock.advance(hours=12)
    r = client.get("/api/v1/auth/me", headers=librarian)
    assert r.status_code == 401 and error_code(r) == "TOKEN_EXPIRED"
'''),
    dict(id="T-AUTH-13-a", req="LIB-AUTH-13", type="Boundary", input="Login 09:00; request at 20:59:59 and at 21:00:00", expected="200, then `401 TOKEN_EXPIRED`", code='''
def TEST(client, clock, librarian):
    headers = login(client, *LIB)
    clock.set(datetime(2026, 11, 2, 20, 59, 59, tzinfo=TR))
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    clock.set(datetime(2026, 11, 2, 21, 0, 0, tzinfo=TR))
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401 and error_code(r) == "TOKEN_EXPIRED"
'''),
    dict(id="T-AUTH-14-a", req="LIB-AUTH-14", type="Normal", input="Logout, then reuse the token; a second session of the same user", expected="204; reuse `401 UNAUTHENTICATED`; the other session still works", code='''
def TEST(client, librarian):
    other = login(client, *LIB)
    assert client.post("/api/v1/auth/logout", headers=librarian).status_code == 204
    r = client.get("/api/v1/auth/me", headers=librarian)
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
    assert client.get("/api/v1/auth/me", headers=other).status_code == 200
'''),
    dict(id="T-AUTH-15-a", req="LIB-AUTH-15", type="Normal", input="`GET /api/v1/auth/me` as librarian", expected="`UserOut` with exactly the documented fields", code='''
def TEST(client, librarian):
    me = client.get("/api/v1/auth/me", headers=librarian).json()
    assert set(me) == {"id", "email", "full_name", "role", "is_active", "member_id", "created_at", "last_login_at"}
    assert me["email"] == "lib@library.local" and me["member_id"] is None and me["last_login_at"] is not None
'''),
    dict(id="T-AUTH-16-a", req="LIB-AUTH-16", type="Normal", input="Two sessions; change password with session 1", expected="204; session 1 valid, session 2 revoked; new password works, old does not", code='''
def TEST(client, librarian):
    other = login(client, *LIB)
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Librarian123", "new_password": "NewPassw0rd"})
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=librarian).status_code == 200
    assert client.get("/api/v1/auth/me", headers=other).status_code == 401
    assert raw_login(client, "lib@library.local", "NewPassw0rd").status_code == 200
    assert raw_login(client, *LIB).status_code == 401
'''),
    dict(id="T-AUTH-16-b", req="LIB-AUTH-16", type="Error", input="Wrong `current_password` five times, then normal login", expected="`401 INVALID_CREDENTIALS` each; login still works (no lockout)", code='''
def TEST(client, librarian):
    for _ in range(5):
        r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Wrong0000", "new_password": "NewPassw0rd"})
        assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
    assert raw_login(client, *LIB).status_code == 200
'''),
    dict(id="T-AUTH-16-c", req="LIB-AUTH-16", type="Error", input="`new_password` equal to the current one", expected="`409 PASSWORD_UNCHANGED`", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Librarian123", "new_password": "Librarian123"})
    assert r.status_code == 409 and error_code(r) == "PASSWORD_UNCHANGED"
'''),
    dict(id="T-AUTH-16-d", req="LIB-AUTH-16", type="Error", input="Wrong `current_password` and a `new_password` without digit", expected="`422 VALIDATION_ERROR` (policy checked first)", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/auth/change-password", headers=librarian, json={"current_password": "Wrong0000", "new_password": "nodigitshere"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
    dict(id="T-AUTH-17-a", req="LIB-AUTH-17", type="Normal", input="Admin creates an admin", expected="201 with `UserOut`, `role` `admin`", code='''
def TEST(client, admin):
    user = new_user(client, admin, email="admin2@library.local", role="admin")
    assert user["role"] == "admin" and user["is_active"] is True and "id" in user
'''),
    dict(id="T-AUTH-17-b", req="LIB-AUTH-17", type="Error", input="Librarian calls `POST /api/v1/users`", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian):
    r = client.post("/api/v1/users", headers=librarian, json={"email": "z@library.local", "full_name": "Z", "role": "librarian", "password": "Passw0rd1"})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
'''),
    dict(id="T-AUTH-18-a", req="LIB-AUTH-18", type="Normal", input="Filters `role=librarian`, `is_active=false`, `q=LIB@`", expected="Only matching users", code='''
def TEST(client, admin, librarian):
    uid = new_user(client, admin, email="gone@library.local")["id"]
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    roles = {u["role"] for u in client.get("/api/v1/users", headers=admin, params={"role": "librarian"}).json()["items"]}
    assert roles == {"librarian"}
    inactive = [u["email"] for u in client.get("/api/v1/users", headers=admin, params={"is_active": "false"}).json()["items"]]
    assert inactive == ["gone@library.local"]
    found = [u["email"] for u in client.get("/api/v1/users", headers=admin, params={"q": "LIB@"}).json()["items"]]
    assert found == ["lib@library.local"]
'''),
    dict(id="T-AUTH-19-a", req="LIB-AUTH-19", type="Normal", input="Member reads own user record (id from `/auth/me`)", expected="200 with own `UserOut`; `member_id` set", code='''
def TEST(client, librarian, branch_a):
    member = register_member(client, librarian, home_branch_id=branch_a["id"])
    mh = member_headers(client, member)
    me = client.get("/api/v1/auth/me", headers=mh).json()
    r = client.get(f"/api/v1/users/{me['id']}", headers=mh)
    assert r.status_code == 200 and r.json()["member_id"] == member["id"]
'''),
    dict(id="T-AUTH-19-b", req="LIB-AUTH-19", type="Error", input="Librarian reads the admin's record and id 9999", expected="`403 FORBIDDEN` both (ownership before existence)", code='''
def TEST(client, librarian):
    for uid in (1, 9999):
        r = client.get(f"/api/v1/users/{uid}", headers=librarian)
        assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
'''),
    dict(id="T-AUTH-19-c", req="LIB-AUTH-19", type="Error", input="Admin reads id 9999", expected="`404 NOT_FOUND`", code='''
def TEST(client, admin):
    r = client.get("/api/v1/users/9999", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
'''),
    dict(id="T-AUTH-20-a", req="LIB-AUTH-20", type="Normal", input="Admin changes a librarian's `role` to `admin` and `full_name`", expected="200 with new values", code='''
def TEST(client, admin):
    uid = new_user(client, admin)["id"]
    r = client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "admin", "full_name": "Chief"})
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["full_name"] == "Chief"
'''),
    dict(id="T-AUTH-20-b", req="LIB-AUTH-20", type="Error", input="`role` `member` in the request", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    uid = new_user(client, admin)["id"]
    assert client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "member"}).status_code == 422
'''),
    dict(id="T-AUTH-20-c", req="LIB-AUTH-20", type="Error", input="Change the role of a member's user to `librarian`", expected="`409 ROLE_CHANGE_NOT_ALLOWED`", code='''
def TEST(client, admin, librarian, branch_a):
    member = register_member(client, librarian, home_branch_id=branch_a["id"])
    uid = user_id_of(client, admin, member["email"])
    r = client.patch(f"/api/v1/users/{uid}", headers=admin, json={"role": "librarian"})
    assert r.status_code == 409 and error_code(r) == "ROLE_CHANGE_NOT_ALLOWED"
'''),
    dict(id="T-AUTH-21-a", req="LIB-AUTH-21", type="Normal", input="Deactivate a logged-in librarian", expected="Its token returns `401 UNAUTHENTICATED`", code='''
def TEST(client, admin, librarian):
    uid = user_id_of(client, admin, "lib@library.local")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    r = client.get("/api/v1/auth/me", headers=librarian)
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
'''),
    dict(id="T-AUTH-21-b", req="LIB-AUTH-21", type="Normal", input="Locked librarian is deactivated and activated again", expected="Login succeeds at once (lock cleared)", code='''
def TEST(client, admin, librarian):
    uid = user_id_of(client, admin, "lib@library.local")
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": True})
    assert raw_login(client, *LIB).status_code == 200
'''),
    dict(id="T-AUTH-22-a", req="LIB-AUTH-22", type="Error", input="Only admin demotes itself to librarian; deactivates itself", expected="`409 LAST_ADMIN`; `409` (`LAST_ADMIN` or `CANNOT_DEACTIVATE_SELF`)", code='''
def TEST(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"role": "librarian"})
    assert r.status_code == 409 and error_code(r) == "LAST_ADMIN"
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"is_active": False})
    assert r.status_code == 409 and error_code(r) in {"LAST_ADMIN", "CANNOT_DEACTIVATE_SELF"}
'''),
    dict(id="T-AUTH-22-b", req="LIB-AUTH-22", type="Error", input="Two admins; admin 1 deactivates itself; then deactivates admin 2", expected="`409 CANNOT_DEACTIVATE_SELF`; then 200", code='''
def TEST(client, admin):
    second = new_user(client, admin, email="admin2@library.local", role="admin")["id"]
    me = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/api/v1/users/{me}", headers=admin, json={"is_active": False})
    assert r.status_code == 409 and error_code(r) == "CANNOT_DEACTIVATE_SELF"
    assert client.patch(f"/api/v1/users/{second}", headers=admin, json={"is_active": False}).status_code == 200
'''),
    dict(id="T-AUTH-23-a", req="LIB-AUTH-23", type="Normal", input="Locked librarian with an open session; admin resets the password", expected="204; old session 401; new password logs in at once", code='''
def TEST(client, admin, librarian):
    uid = user_id_of(client, admin, "lib@library.local")
    for _ in range(5):
        raw_login(client, "lib@library.local", "Wrong0000")
    r = client.post(f"/api/v1/users/{uid}/reset-password", headers=admin, json={"new_password": "Reset1234"})
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=librarian).status_code == 401
    assert raw_login(client, "lib@library.local", "Reset1234").status_code == 200
'''),
    dict(id="T-AUTH-23-b", req="LIB-AUTH-23", type="Error", input="Librarian calls reset-password", expected="`403 FORBIDDEN`", code='''
def TEST(client, admin, librarian):
    r = client.post("/api/v1/users/1/reset-password", headers=librarian, json={"new_password": "Reset1234"})
    assert r.status_code == 403
'''),
    dict(id="T-AUTH-24-a", req="LIB-AUTH-24", type="Error", input="Member calls `GET /api/v1/users` and `POST /api/v1/branches`", expected="`403 FORBIDDEN` both", code='''
def TEST(client, librarian, branch_a):
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.get("/api/v1/users", headers=mh).status_code == 403
    r = client.post("/api/v1/branches", headers=mh, json={"code": "ZZ", "name": "Z", "address": ""})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
'''),
    dict(id="T-AUTH-24-b", req="LIB-AUTH-24", type="Error", input="No token: `GET /api/v1/books`", expected="`401 UNAUTHENTICATED`", code='''
def TEST(client):
    r = client.get("/api/v1/books")
    assert r.status_code == 401 and error_code(r) == "UNAUTHENTICATED"
'''),
    dict(id="T-AUTH-25-a", req="LIB-AUTH-25", type="Error", input="Member A reads member B's record; member A reads member id 9999", expected="`403 FORBIDDEN`; `404 NOT_FOUND`", code='''
def TEST(client, librarian, branch_a):
    a = register_member(client, librarian, home_branch_id=branch_a["id"])
    b = register_member(client, librarian, home_branch_id=branch_a["id"])
    ha = member_headers(client, a)
    r = client.get(f"/api/v1/members/{b['id']}", headers=ha)
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
    r = client.get("/api/v1/members/9999", headers=ha)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
'''),
]
