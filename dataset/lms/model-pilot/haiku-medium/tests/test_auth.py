import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import orm, select

from lms import FixedClock, Settings, create_app
from lms.audit.models import AuditEntry
from lms.auth.passwords import hash_password, verify_password
from lms.core.clock import LOCAL_TZ

ADMIN = "admin@library.local"
ADMIN_PASSWORD = "ChangeMe123"
PASSWORD = "Secret123"


@pytest.fixture
def app(clock: FixedClock):
    return create_app(Settings(database_url="sqlite://", clock=clock))


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def token_for(client, email=ADMIN, password=ADMIN_PASSWORD) -> str:
    response = login(client, email, password)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_staff(client, admin_token, email, role="librarian", password=PASSWORD):
    return client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Staff Person", "role": role, "password": password},
        headers=auth(admin_token),
    )


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_bootstrap_admin_and_login_response(client):
    response = login(client, ADMIN, ADMIN_PASSWORD)
    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) == 43
    assert body["expires_at"] == "2026-11-05T21:30:00+03:00"
    assert body["user"] == {
        "id": 1,
        "email": ADMIN,
        "full_name": "Administrator",
        "role": "admin",
        "is_active": True,
        "member_id": None,
        "created_at": "2026-11-05T09:30:00+03:00",
        "last_login_at": "2026-11-05T09:30:00+03:00",
    }
    assert "password_hash" not in body["user"]


def test_creating_app_twice_does_not_add_second_bootstrap_admin(app, clock):
    create_app(Settings(database_url=app.state.settings.database_url, clock=clock))
    with orm.Session(app.state.engine) as db:
        from lms.auth.models import User

        assert len(list(db.scalars(select(User).where(User.role == "admin")))) == 1


def test_wrong_password_and_unknown_email_give_same_response(client):
    wrong = login(client, ADMIN, "Wrong12345")
    unknown = login(client, "nobody@library.local", "Wrong12345")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert error_code(wrong) == "INVALID_CREDENTIALS"


def test_lockout_after_five_failures_and_recovery_after_15_minutes(client, clock):
    token = token_for(client)
    create_staff(client, token, "lena@library.local")
    for _ in range(4):
        assert error_code(login(client, "lena@library.local", "Wrong12345")) == "INVALID_CREDENTIALS"
    fifth = login(client, "lena@library.local", "Wrong12345")
    assert fifth.status_code == 401  # the fifth failure sets the lock and returns INVALID_CREDENTIALS

    locked = login(client, "lena@library.local", PASSWORD)
    assert locked.status_code == 403
    assert error_code(locked) == "ACCOUNT_LOCKED"
    assert locked.json()["error"]["details"]["locked_until"] == "2026-11-05T09:45:00+03:00"

    clock.advance(minutes=15)
    assert login(client, "lena@library.local", PASSWORD).status_code == 200


def test_disabled_account_with_correct_password_is_not_a_failure(client):
    token = token_for(client)
    user = create_staff(client, token, "tomas@library.local").json()
    patched = client.patch(f"/api/v1/users/{user['id']}", json={"is_active": False}, headers=auth(token))
    assert patched.status_code == 200
    response = login(client, "tomas@library.local", PASSWORD)
    assert response.status_code == 403
    assert error_code(response) == "ACCOUNT_DISABLED"


def test_token_expiry_boundary(app, client, clock):
    token = token_for(client)
    clock.set(datetime.datetime(2026, 11, 5, 21, 29, 59, tzinfo=LOCAL_TZ))
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 200
    clock.set(datetime.datetime(2026, 11, 5, 21, 30, 0, tzinfo=LOCAL_TZ))
    response = client.get("/api/v1/auth/me", headers=auth(token))
    assert response.status_code == 401
    assert error_code(response) == "TOKEN_EXPIRED"


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer", "Bearer a b", "Bearer nope"])
def test_missing_malformed_or_unknown_token_is_unauthenticated(client, header):
    headers = {} if header is None else {"Authorization": header}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


def test_logout_revokes_only_that_session(client):
    first = token_for(client)
    second = token_for(client)
    assert client.post("/api/v1/auth/logout", headers=auth(first)).status_code == 204
    assert error_code(client.get("/api/v1/auth/me", headers=auth(first))) == "UNAUTHENTICATED"
    assert client.get("/api/v1/auth/me", headers=auth(second)).status_code == 200


def test_change_password_checks_and_revokes_other_sessions(client):
    keep = token_for(client)
    other = token_for(client)
    url = "/api/v1/auth/change-password"
    body = {"current_password": ADMIN_PASSWORD, "new_password": "Brand2024"}

    weak = client.post(url, json={**body, "new_password": "short"}, headers=auth(keep))
    assert weak.status_code == 422
    assert error_code(weak) == "VALIDATION_ERROR"

    wrong = client.post(url, json={**body, "current_password": "Wrong12345"}, headers=auth(keep))
    assert error_code(wrong) == "INVALID_CREDENTIALS"

    same = client.post(url, json={**body, "new_password": ADMIN_PASSWORD}, headers=auth(keep))
    assert error_code(same) == "PASSWORD_UNCHANGED"

    assert client.post(url, json=body, headers=auth(keep)).status_code == 204
    assert error_code(client.get("/api/v1/auth/me", headers=auth(other))) == "UNAUTHENTICATED"
    assert client.get("/api/v1/auth/me", headers=auth(keep)).status_code == 200
    assert login(client, ADMIN, "Brand2024").status_code == 200


def test_create_user_rules(client):
    token = token_for(client)
    assert create_staff(client, token, "Ali@Library.local").json()["email"] == "ali@library.local"

    duplicate = create_staff(client, token, "ALI@library.local")
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "CONFLICT"

    member = create_staff(client, token, "mem@library.local", role="member")
    assert member.status_code == 422
    assert error_code(member) == "VALIDATION_ERROR"

    no_digit = create_staff(client, token, "x@library.local", password="Password")
    assert error_code(no_digit) == "VALIDATION_ERROR"
    assert no_digit.json()["error"]["details"]["fields"][0]["field"] == "password"


def test_only_admin_manages_users(client):
    admin = token_for(client)
    create_staff(client, admin, "lib@library.local")
    librarian = token_for(client, "lib@library.local", PASSWORD)

    forbidden = create_staff(client, librarian, "new@library.local")
    assert forbidden.status_code == 403
    assert error_code(forbidden) == "FORBIDDEN"
    # Role check (403) comes before validation (422).
    invalid = client.post("/api/v1/users", json={"role": "member"}, headers=auth(librarian))
    assert invalid.status_code == 403

    assert client.get("/api/v1/users", headers=auth(librarian)).status_code == 403
    assert client.get("/api/v1/users", headers=auth(admin)).status_code == 200


def test_list_users_paginated_filtered_and_normalized(client):
    admin = token_for(client)
    create_staff(client, admin, "ayse@library.local").json()
    create_staff(client, admin, "ismail@library.local", role="admin")
    client.patch(
        "/api/v1/users/2", json={"full_name": "Işık İlhan"}, headers=auth(admin)
    )

    page = client.get("/api/v1/users", params={"page": 1, "page_size": 2}, headers=auth(admin)).json()
    assert page["total"] == 3 and page["page_size"] == 2 and len(page["items"]) == 2
    assert [item["id"] for item in page["items"]] == [1, 2]
    beyond = client.get("/api/v1/users", params={"page": 9}, headers=auth(admin)).json()
    assert beyond["items"] == []

    assert client.get("/api/v1/users", params={"page_size": 101}, headers=auth(admin)).status_code == 422
    assert client.get("/api/v1/users", params={"role": "guest"}, headers=auth(admin)).status_code == 422

    librarians = client.get("/api/v1/users", params={"role": "librarian"}, headers=auth(admin)).json()
    assert [item["email"] for item in librarians["items"]] == ["ayse@library.local"]
    assert client.get("/api/v1/users", params={"is_active": "true"}, headers=auth(admin)).json()["total"] == 3

    # Turkish normalization: "ISIK" matches "Işık" only if the ı and ş rules hold (LIB-SRCH-01).
    found = client.get("/api/v1/users", params={"q": "ILHAN"}, headers=auth(admin)).json()
    assert [item["id"] for item in found["items"]] == [2]
    assert client.get("/api/v1/users", params={"q": "isik"}, headers=auth(admin)).json()["total"] == 0


def test_get_user_ownership_and_not_found(client):
    admin = token_for(client)
    create_staff(client, admin, "lib@library.local")
    librarian = token_for(client, "lib@library.local", PASSWORD)

    assert client.get("/api/v1/users/2", headers=auth(librarian)).status_code == 200
    assert client.get("/api/v1/users/1", headers=auth(librarian)).status_code == 403
    assert client.get("/api/v1/users/999", headers=auth(librarian)).status_code == 403
    assert client.get("/api/v1/users/999", headers=auth(admin)).status_code == 404
    assert client.get("/api/v1/users/0", headers=auth(admin)).status_code == 422


def test_patch_rules(client):
    admin = token_for(client)
    create_staff(client, admin, "lib@library.local")
    url = "/api/v1/users/2"

    assert client.patch(url, json={"role": "member"}, headers=auth(admin)).status_code == 422
    assert client.patch(url, json={"email": "x@y.z"}, headers=auth(admin)).status_code == 422
    assert client.patch(url, json={"is_active": None}, headers=auth(admin)).status_code == 422

    renamed = client.patch(url, json={"full_name": "  New Name "}, headers=auth(admin))
    assert renamed.json()["full_name"] == "New Name"

    self_block = client.patch("/api/v1/users/1", json={"is_active": False}, headers=auth(admin))
    assert error_code(self_block) == "CANNOT_DEACTIVATE_SELF"
    last = client.patch("/api/v1/users/1", json={"role": "librarian"}, headers=auth(admin))
    assert error_code(last) == "LAST_ADMIN"


def test_deactivation_revokes_sessions_and_activation_clears_lock(client, clock):
    admin = token_for(client)
    create_staff(client, admin, "lib@library.local")
    librarian = token_for(client, "lib@library.local", PASSWORD)
    for _ in range(5):
        login(client, "lib@library.local", "Wrong12345")

    assert client.patch("/api/v1/users/2", json={"is_active": False}, headers=auth(admin)).status_code == 200
    assert error_code(client.get("/api/v1/auth/me", headers=auth(librarian))) == "UNAUTHENTICATED"

    client.patch("/api/v1/users/2", json={"is_active": True}, headers=auth(admin))
    response = login(client, "lib@library.local", PASSWORD)
    assert response.status_code == 200


def test_last_admin_can_be_replaced_then_demoted(client):
    admin = token_for(client)
    create_staff(client, admin, "boss@library.local", role="admin")
    other = token_for(client, "boss@library.local", PASSWORD)

    demoted = client.patch("/api/v1/users/1", json={"role": "librarian"}, headers=auth(other))
    assert demoted.status_code == 200 and demoted.json()["role"] == "librarian"
    self_block = client.patch("/api/v1/users/2", json={"is_active": False}, headers=auth(other))
    assert error_code(self_block) == "CANNOT_DEACTIVATE_SELF"
    last = client.patch("/api/v1/users/2", json={"role": "librarian"}, headers=auth(other))
    assert error_code(last) == "LAST_ADMIN"


def test_reset_password_revokes_sessions_and_clears_lock(client):
    admin = token_for(client)
    create_staff(client, admin, "lib@library.local")
    librarian = token_for(client, "lib@library.local", PASSWORD)

    assert client.post("/api/v1/users/2/reset-password", json={"new_password": "Fresh2025"}, headers=auth(admin)).status_code == 204
    assert error_code(client.get("/api/v1/auth/me", headers=auth(librarian))) == "UNAUTHENTICATED"
    assert login(client, "lib@library.local", PASSWORD).status_code == 401
    assert login(client, "lib@library.local", "Fresh2025").status_code == 200

    missing = client.post("/api/v1/users/99/reset-password", json={"new_password": "Fresh2025"}, headers=auth(admin))
    assert missing.status_code == 404


def test_failed_login_keeps_audit_entry(app, client):
    token_for(client)
    login(client, ADMIN, "Wrong12345")
    with orm.Session(app.state.engine) as db:
        events = [entry.event for entry in db.scalars(select(AuditEntry).order_by(AuditEntry.id))]
    assert events == ["user_created", "login_succeeded", "login_failed"]


def test_password_hash_format_and_verification():
    stored = hash_password(PASSWORD)
    scheme, salt, digest = stored.split("$")
    assert scheme == "scrypt" and len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 64
    assert verify_password(PASSWORD, stored)
    assert not verify_password("Other12345", stored)
