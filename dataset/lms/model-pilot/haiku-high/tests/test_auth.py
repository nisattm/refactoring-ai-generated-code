"""HTTP behavior of module 2: identity and access (section 6)."""

import datetime

import pytest
from fastapi.testclient import TestClient
from helpers import local_datetime
from sqlalchemy import select

from lms import Settings, create_app
from lms.audit.models import AuditEntry
from lms.auth.models import User

ADMIN_EMAIL = "admin@library.local"
ADMIN_PASSWORD = "ChangeMe123"


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def admin_token(client):
    response = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def create_staff(client, token, email, role="librarian", password="Secret123"):
    response = client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Staff Member", "role": role, "password": password},
        headers=bearer(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def admin(client):
    return {"token": admin_token(client)}


# LIB-AUTH-01, LIB-IF-02
def test_bootstrap_admin_is_created_once(clock, tmp_path):
    url = f"sqlite:///{tmp_path / 'lms.db'}"
    create_app(Settings(database_url=url, clock=clock))
    app = create_app(Settings(database_url=url, clock=clock))
    client = TestClient(app, raise_server_exceptions=False)
    token = admin_token(client)
    users = client.get("/api/v1/users", headers=bearer(token)).json()
    admins = [u for u in users["items"] if u["role"] == "admin"]
    assert len(admins) == 1
    assert admins[0]["full_name"] == "Administrator"
    assert admins[0]["email"] == ADMIN_EMAIL


# LIB-AUTH-03
def test_password_is_stored_as_scrypt_and_token_is_not_stored(app, client):
    token = admin_token(client)
    with app.state.session_factory() as session:
        stored = session.scalar(select(User.password_hash).where(User.email == ADMIN_EMAIL))
        assert stored.startswith("scrypt$")
        _, salt_hex, hash_hex = stored.split("$")
        assert len(bytes.fromhex(salt_hex)) == 16
        assert len(bytes.fromhex(hash_hex)) == 64
        assert token not in stored


# LIB-AUTH-06, LIB-AUTH-07, LIB-AUTH-15
def test_login_returns_token_and_user(client, clock):
    response = login(client, "ADMIN@library.local", ADMIN_PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert len(body["access_token"]) == 43
    assert body["token_type"] == "bearer"
    assert body["expires_at"] == "2026-11-05T21:30:00+03:00"
    user = body["user"]
    assert set(user) == {
        "id",
        "email",
        "full_name",
        "role",
        "is_active",
        "member_id",
        "created_at",
        "last_login_at",
    }
    assert user["created_at"] == "2026-11-05T09:30:00+03:00"
    assert user["last_login_at"] == "2026-11-05T09:30:00+03:00"
    me = client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


# LIB-AUTH-08
def test_unknown_email_and_wrong_password_look_the_same(client):
    unknown = login(client, "nobody@library.local", "Whatever1")
    wrong = login(client, ADMIN_EMAIL, "Wrong1234")
    assert_error(unknown, 401, "INVALID_CREDENTIALS")
    assert unknown.json() == wrong.json()


# LIB-AUTH-09, LIB-E2E-10
def test_lockout_after_five_failures_then_expiry(client, clock, admin):
    token = admin["token"]
    create_staff(client, token, "lena@library.local")
    for _ in range(4):
        assert_error(login(client, "lena@library.local", "Wrong1234"), 401, "INVALID_CREDENTIALS")
    # The fifth failure sets the lock and still returns 401.
    assert_error(login(client, "lena@library.local", "Wrong1234"), 401, "INVALID_CREDENTIALS")

    locked = login(client, "lena@library.local", "Secret123")
    error = assert_error(locked, 403, "ACCOUNT_LOCKED")
    assert error["details"]["locked_until"] == "2026-11-05T09:45:00+03:00"

    clock.advance(minutes=15)
    assert login(client, "lena@library.local", "Secret123").status_code == 200


# LIB-AUTH-09: a locked attempt is not a failure, and a success resets the count
def test_successful_login_resets_failure_count(client, admin):
    create_staff(client, admin["token"], "omar@library.local")
    for _ in range(4):
        login(client, "omar@library.local", "Wrong1234")
    assert login(client, "omar@library.local", "Secret123").status_code == 200
    for _ in range(4):
        login(client, "omar@library.local", "Wrong1234")
    # Still not locked: the count restarted at the successful login.
    assert login(client, "omar@library.local", "Secret123").status_code == 200


# LIB-AUTH-10, LIB-AUTH-11
def test_disabled_account_order_of_checks(client, admin):
    token = admin["token"]
    user = create_staff(client, token, "kemal@library.local")
    response = client.patch(
        f"/api/v1/users/{user['id']}", json={"is_active": False}, headers=bearer(token)
    )
    assert response.status_code == 200
    assert_error(login(client, "kemal@library.local", "Secret123"), 403, "ACCOUNT_DISABLED")
    # A wrong password on a disabled account is a counted failure.
    assert_error(login(client, "kemal@library.local", "Wrong1234"), 401, "INVALID_CREDENTIALS")


# LIB-AUTH-12, LIB-AUTH-13
def test_expiry_boundary(client, clock):
    clock.set(local_datetime(2026, 11, 2, 9, 0))
    token = login(client, ADMIN_EMAIL, ADMIN_PASSWORD).json()["access_token"]
    clock.set(local_datetime(2026, 11, 2, 20, 59, 59))
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    clock.set(local_datetime(2026, 11, 2, 21, 0, 0))
    assert_error(client.get("/api/v1/auth/me", headers=bearer(token)), 401, "TOKEN_EXPIRED")


# LIB-AUTH-12
@pytest.mark.parametrize(
    "header",
    [None, "Basic abc", "Bearer", "Bearer a b", "Bearer not-a-real-token"],
)
def test_missing_malformed_or_unknown_token(client, header):
    headers = {} if header is None else {"Authorization": header}
    assert_error(client.get("/api/v1/auth/me", headers=headers), 401, "UNAUTHENTICATED")


# LIB-AUTH-14
def test_logout_revokes_only_this_session(client):
    token = admin_token(client)
    other = admin_token(client)
    assert client.post("/api/v1/auth/logout", headers=bearer(token)).status_code == 204
    assert_error(client.get("/api/v1/auth/me", headers=bearer(token)), 401, "UNAUTHENTICATED")
    assert client.get("/api/v1/auth/me", headers=bearer(other)).status_code == 200


# LIB-AUTH-16
def test_change_password_checks_and_revokes_other_sessions(client):
    token = admin_token(client)
    other = admin_token(client)
    url = "/api/v1/auth/change-password"

    weak = client.post(
        url,
        json={"current_password": ADMIN_PASSWORD, "new_password": "short1"},
        headers=bearer(token),
    )
    assert_error(weak, 422, "VALIDATION_ERROR")

    wrong = client.post(
        url,
        json={"current_password": "Wrong1234", "new_password": "Better123"},
        headers=bearer(token),
    )
    assert_error(wrong, 401, "INVALID_CREDENTIALS")

    same = client.post(
        url,
        json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
        headers=bearer(token),
    )
    assert_error(same, 409, "PASSWORD_UNCHANGED")

    done = client.post(
        url,
        json={"current_password": ADMIN_PASSWORD, "new_password": "Better123"},
        headers=bearer(token),
    )
    assert done.status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    assert_error(client.get("/api/v1/auth/me", headers=bearer(other)), 401, "UNAUTHENTICATED")
    assert login(client, ADMIN_EMAIL, "Better123").status_code == 200


# LIB-AUTH-02, LIB-COM-23
@pytest.mark.parametrize(
    "body",
    [
        {"email": "x@library.local", "full_name": "X", "role": "librarian", "password": "abcdefgh"},
        {"email": "x@library.local", "full_name": "X", "role": "librarian", "password": "12345678"},
        {"email": "x@library.local", "full_name": "X", "role": "librarian", "password": "a1"},
        {"email": "x@library.local", "full_name": "X", "role": "librarian", "password": "a" * 129},
        {
            "email": "x@library.local",
            "full_name": "X",
            "role": "librarian",
            "password": "Abc12345",
            "extra": 1,
        },
    ],
)
def test_create_user_rejects_bad_input(client, admin, body):
    response = client.post("/api/v1/users", json=body, headers=bearer(admin["token"]))
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert error["details"]["fields"]


# LIB-AUTH-04
def test_member_role_cannot_be_created_or_assigned(client, admin):
    token = admin["token"]
    response = client.post(
        "/api/v1/users",
        json={
            "email": "m@library.local",
            "full_name": "M",
            "role": "member",
            "password": "Secret123",
        },
        headers=bearer(token),
    )
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert error["details"]["fields"][0]["field"] == "role"

    other = create_staff(client, token, "pinar@library.local")
    response = client.patch(
        f"/api/v1/users/{other['id']}", json={"role": "member"}, headers=bearer(token)
    )
    assert_error(response, 422, "VALIDATION_ERROR")


# LIB-AUTH-17, LIB-AUTH-05
def test_create_user_and_duplicate_email(client, admin):
    token = admin["token"]
    created = create_staff(client, token, "  Deniz@Library.Local ")
    assert created["email"] == "deniz@library.local"
    assert created["role"] == "librarian"
    assert created["is_active"] is True
    assert created["member_id"] is None
    assert created["last_login_at"] is None

    duplicate = client.post(
        "/api/v1/users",
        json={
            "email": "DENIZ@library.local",
            "full_name": "Other",
            "role": "admin",
            "password": "Secret123",
        },
        headers=bearer(token),
    )
    assert_error(duplicate, 409, "CONFLICT")


# LIB-AUTH-24
def test_librarian_cannot_manage_users(client, admin):
    create_staff(client, admin["token"], "ece@library.local")
    token = login(client, "ece@library.local", "Secret123").json()["access_token"]
    assert_error(client.get("/api/v1/users", headers=bearer(token)), 403, "FORBIDDEN")
    response = client.post(
        "/api/v1/users",
        json={
            "email": "z@library.local",
            "full_name": "Z",
            "role": "librarian",
            "password": "Secret123",
        },
        headers=bearer(token),
    )
    assert_error(response, 403, "FORBIDDEN")
    # Unauthenticated access is 401, not 403 (LIB-AUTH-24).
    assert_error(client.get("/api/v1/users"), 401, "UNAUTHENTICATED")


# LIB-AUTH-18, LIB-COM-18 to LIB-COM-20
def test_list_users_filters_order_and_pagination(client, admin):
    token = admin["token"]
    create_staff(client, token, "ayla@library.local", role="librarian")
    create_staff(client, token, "burak@library.local", role="admin")
    create_staff(client, token, "ISIL@library.local", role="librarian")

    response = client.get("/api/v1/users", params={"role": "librarian"}, headers=bearer(token))
    body = response.json()
    assert body["total"] == 2
    assert [u["email"] for u in body["items"]] == ["ayla@library.local", "isil@library.local"]
    assert body["page"] == 1 and body["page_size"] == 20

    # q uses LIB-COM-30 normalization: "ısıl" matches "ISIL" and "Isil".
    by_name = client.get("/api/v1/users", params={"q": "ısıl"}, headers=bearer(token)).json()
    assert by_name["total"] == 1

    inactive = client.get("/api/v1/users", params={"is_active": "false"}, headers=bearer(token))
    assert inactive.json()["items"] == []

    page = client.get("/api/v1/users", params={"page": 2, "page_size": 2}, headers=bearer(token))
    assert page.json()["total"] == 4
    assert [u["id"] for u in page.json()["items"]] == [3, 4]
    beyond = client.get("/api/v1/users", params={"page": 9, "page_size": 2}, headers=bearer(token))
    assert beyond.status_code == 200 and beyond.json()["items"] == []

    # "member" is one of the three roles, so it is a valid filter; "owner" is not.
    assert (
        client.get("/api/v1/users", params={"role": "member"}, headers=bearer(token)).json()[
            "total"
        ]
        == 0
    )
    assert_error(
        client.get("/api/v1/users", params={"role": "owner"}, headers=bearer(token)),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        client.get("/api/v1/users", params={"page_size": 101}, headers=bearer(token)),
        422,
        "VALIDATION_ERROR",
    )


# LIB-AUTH-19
def test_get_user_ownership_before_existence(client, admin):
    token = admin["token"]
    created = create_staff(client, token, "fatma@library.local")
    own = login(client, "fatma@library.local", "Secret123").json()["access_token"]

    assert client.get(f"/api/v1/users/{created['id']}", headers=bearer(own)).status_code == 200
    assert_error(client.get("/api/v1/users/1", headers=bearer(own)), 403, "FORBIDDEN")
    assert_error(client.get("/api/v1/users/999", headers=bearer(own)), 403, "FORBIDDEN")
    assert_error(client.get("/api/v1/users/999", headers=bearer(token)), 404, "NOT_FOUND")
    assert_error(client.get("/api/v1/users/0", headers=bearer(token)), 422, "VALIDATION_ERROR")


# LIB-AUTH-20, LIB-AUTH-21
def test_patch_user_fields_and_activation_clears_lock(client, admin):
    token = admin["token"]
    created = create_staff(client, token, "gul@library.local")
    for _ in range(5):
        login(client, "gul@library.local", "Wrong1234")
    assert_error(login(client, "gul@library.local", "Secret123"), 403, "ACCOUNT_LOCKED")

    response = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"full_name": " Gül Demir ", "role": "admin", "is_active": True},
        headers=bearer(token),
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Gül Demir"
    assert response.json()["role"] == "admin"
    # Activation clears the lock immediately.
    assert login(client, "gul@library.local", "Secret123").status_code == 200


# LIB-AUTH-20: a member's role cannot be changed through this endpoint
def test_member_role_change_is_not_allowed(client, admin, app):
    from lms.auth.credentials import hash_password

    with app.state.session_factory() as session:
        member = User(
            email="member@library.local",
            email_key="member@library.local",
            full_name="Member",
            role="member",
            password_hash=hash_password("Secret123"),
            is_active=True,
            failed_login_count=0,
            created_at=local_datetime(2026, 11, 5, 9, 30),
        )
        session.add(member)
        session.commit()
        member_id = member.id

    response = client.patch(
        f"/api/v1/users/{member_id}", json={"role": "librarian"}, headers=bearer(admin["token"])
    )
    assert_error(response, 409, "ROLE_CHANGE_NOT_ALLOWED")


# LIB-AUTH-22
def test_last_admin_and_self_deactivation(client, admin):
    token = admin["token"]
    me = client.get("/api/v1/auth/me", headers=bearer(token)).json()

    assert_error(
        client.patch(
            f"/api/v1/users/{me['id']}", json={"role": "librarian"}, headers=bearer(token)
        ),
        409,
        "LAST_ADMIN",
    )
    assert_error(
        client.patch(f"/api/v1/users/{me['id']}", json={"is_active": False}, headers=bearer(token)),
        409,
        "CANNOT_DEACTIVATE_SELF",
    )

    second = create_staff(client, token, "hale@library.local", role="admin")
    # With a second active admin, the first may be demoted.
    demoted = client.patch(
        f"/api/v1/users/{me['id']}", json={"role": "librarian"}, headers=bearer(token)
    )
    assert demoted.status_code == 200
    # The first admin token is now a librarian token, so it cannot manage users any more.
    assert_error(client.get("/api/v1/users", headers=bearer(token)), 403, "FORBIDDEN")

    hale = login(client, "hale@library.local", "Secret123").json()["access_token"]
    assert_error(
        client.patch(
            f"/api/v1/users/{second['id']}", json={"is_active": False}, headers=bearer(hale)
        ),
        409,
        "CANNOT_DEACTIVATE_SELF",
    )


# LIB-AUTH-21
def test_deactivation_revokes_sessions(client, admin):
    token = admin["token"]
    user = create_staff(client, token, "ilhan@library.local")
    session_token = login(client, "ilhan@library.local", "Secret123").json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=bearer(session_token)).status_code == 200

    client.patch(f"/api/v1/users/{user['id']}", json={"is_active": False}, headers=bearer(token))
    assert_error(
        client.get("/api/v1/auth/me", headers=bearer(session_token)), 401, "UNAUTHENTICATED"
    )


# LIB-AUTH-23
def test_reset_password_revokes_sessions_and_clears_lock(client, admin):
    token = admin["token"]
    user = create_staff(client, token, "jale@library.local")
    session_token = login(client, "jale@library.local", "Secret123").json()["access_token"]
    for _ in range(5):
        login(client, "jale@library.local", "Wrong1234")

    url = f"/api/v1/users/{user['id']}/reset-password"
    assert_error(
        client.post(url, json={"new_password": "nodigitsHere"}, headers=bearer(token)),
        422,
        "VALIDATION_ERROR",
    )
    response = client.post(url, json={"new_password": "Fresh4567"}, headers=bearer(token))
    assert response.status_code == 204
    assert_error(
        client.get("/api/v1/auth/me", headers=bearer(session_token)), 401, "UNAUTHENTICATED"
    )
    assert login(client, "jale@library.local", "Fresh4567").status_code == 200


# LIB-AUTH-24: only admins reset passwords
def test_reset_password_is_admin_only(client, admin):
    create_staff(client, admin["token"], "kaan@library.local")
    token = login(client, "kaan@library.local", "Secret123").json()["access_token"]
    response = client.post(
        "/api/v1/users/1/reset-password", json={"new_password": "Fresh4567"}, headers=bearer(token)
    )
    assert_error(response, 403, "FORBIDDEN")


# LIB-AUD-01, LIB-AUD-02, LIB-TECH-08 (failed login keeps its audit entry)
def test_audit_entries_for_module_two(app, client, admin):
    token = admin["token"]
    create_staff(client, token, "lale@library.local")
    login(client, "lale@library.local", "Wrong1234")
    login(client, "lale@library.local", "Secret123")
    client.post("/api/v1/auth/logout", headers=bearer(token))

    with app.state.session_factory() as session:
        entries = session.scalars(select(AuditEntry).order_by(AuditEntry.id)).all()
        events = [e.event for e in entries]
        assert "user_created" in events
        assert "login_failed" in events
        assert "login_succeeded" in events
        assert "logout" in events
        for entry in entries:
            assert "password" not in str(entry.details).lower()
            assert "Secret123" not in str(entry.details)
            assert "Wrong1234" not in str(entry.details)
            assert isinstance(entry.at, datetime.datetime)
        failed = next(e for e in entries if e.event == "login_failed")
        assert failed.actor_user_id is None
        assert failed.entity_type == "user"


# LIB-API-05
def test_body_must_be_json(client):
    response = client.post(
        "/api/v1/auth/login",
        content=b'{"email": "admin@library.local", "password": "ChangeMe123"}',
        headers={"Content-Type": "text/plain"},
    )
    assert_error(response, 422, "VALIDATION_ERROR")


# LIB-API-04
def test_openapi_lists_every_module_two_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in [
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/users",
        "/api/v1/users/{user_id}",
        "/api/v1/users/{user_id}/reset-password",
    ]:
        assert path in paths, path
