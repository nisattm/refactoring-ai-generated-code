"""HTTP behavior of module 11: branches (section 17, LIB-BR-01 to LIB-BR-04)."""

import pytest
from sqlalchemy import select

from lms.audit.models import AuditEntry

ADMIN_EMAIL = "admin@library.local"
ADMIN_PASSWORD = "ChangeMe123"
PASSWORD = "Secret123"


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


def token_of(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(client):
    return {"token": token_of(client, ADMIN_EMAIL, ADMIN_PASSWORD)}


@pytest.fixture
def librarian(client, admin):
    response = client.post(
        "/api/v1/users",
        json={
            "email": "lib@library.local",
            "full_name": "Librarian",
            "role": "librarian",
            "password": PASSWORD,
        },
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 201, response.text
    return {"token": token_of(client, "lib@library.local", PASSWORD)}


def create_branch(client, token, code, name="Central Library", address="Main campus"):
    response = client.post(
        "/api/v1/branches",
        json={"code": code, "name": name, "address": address},
        headers=bearer(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


# LIB-BR-01
def test_create_branch_stores_code_in_upper_case(client, admin):
    response = client.post(
        "/api/v1/branches",
        json={"code": " merkez ", "name": "  Central Library ", "address": ""},
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "MERKEZ"
    assert body["name"] == "Central Library"
    assert body["address"] == ""
    assert body["is_active"] is True
    assert set(body) == {"id", "code", "name", "address", "is_active", "created_at"}
    assert body["created_at"] == "2026-11-05T09:30:00+03:00"


# LIB-BR-01
def test_duplicate_branch_code_is_rejected_case_insensitively(client, admin):
    create_branch(client, admin["token"], "MERKEZ")
    response = client.post(
        "/api/v1/branches",
        json={"code": "merkez", "name": "Other", "address": ""},
        headers=bearer(admin["token"]),
    )
    assert_error(response, 409, "CONFLICT")


# LIB-BR-01: code is 2-10 characters [A-Z0-9]
@pytest.mark.parametrize("code", ["A", "ABCDEFGHIJK", "A-1", "AĞ1"])
def test_invalid_branch_code_is_validation_error(client, admin, code):
    response = client.post(
        "/api/v1/branches",
        json={"code": code, "name": "Central", "address": ""},
        headers=bearer(admin["token"]),
    )
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["code"]


# LIB-BR-01 and section 17.2: only admin creates branches; role is checked before validation.
def test_only_admin_creates_branches(client, librarian):
    response = client.post(
        "/api/v1/branches",
        json={"code": "A", "name": "Central", "address": ""},
        headers=bearer(librarian["token"]),
    )
    assert_error(response, 403, "FORBIDDEN")
    response = client.post(
        "/api/v1/branches", json={"code": "MERKEZ", "name": "Central", "address": ""}
    )
    assert_error(response, 401, "UNAUTHENTICATED")


# LIB-COM-14, LIB-COM-25: the creation is recorded in the audit log.
def test_branch_creation_is_audited(app, client, admin):
    branch = create_branch(client, admin["token"], "MERKEZ")
    with app.state.session_factory() as session:
        entry = session.scalar(select(AuditEntry).where(AuditEntry.event == "branch_created"))
        assert entry.entity_type == "branch"
        assert entry.entity_id == branch["id"]
        assert entry.details["code"] == "MERKEZ"


# LIB-BR-02
def test_list_branches_is_paginated_and_ordered_by_code(client, admin, librarian):
    create_branch(client, admin["token"], "BR3")
    create_branch(client, admin["token"], "BR1")
    create_branch(client, admin["token"], "BR2")
    response = client.get(
        "/api/v1/branches", params={"page_size": 2}, headers=bearer(librarian["token"])
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == ["BR1", "BR2"]
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 3

    response = client.get(
        "/api/v1/branches", params={"page": 2, "page_size": 2}, headers=bearer(librarian["token"])
    )
    assert [item["code"] for item in response.json()["items"]] == ["BR3"]

    response = client.get(
        "/api/v1/branches", params={"page": 9}, headers=bearer(librarian["token"])
    )
    assert response.json()["items"] == []


# LIB-BR-02
def test_list_branches_filters_by_active_state(client, admin):
    create_branch(client, admin["token"], "BR1")
    create_branch(client, admin["token"], "BR2")
    response = client.patch(
        "/api/v1/branches/2", json={"is_active": False}, headers=bearer(admin["token"])
    )
    assert response.status_code == 200, response.text

    active = client.get(
        "/api/v1/branches", params={"is_active": "true"}, headers=bearer(admin["token"])
    ).json()
    inactive = client.get(
        "/api/v1/branches", params={"is_active": "false"}, headers=bearer(admin["token"])
    ).json()
    assert [item["code"] for item in active["items"]] == ["BR1"]
    assert [item["code"] for item in inactive["items"]] == ["BR2"]


# section 17.2: every authenticated user reads branches; anonymous users do not.
def test_all_authenticated_users_read_branches(client, admin, librarian):
    branch = create_branch(client, admin["token"], "MERKEZ")
    for token in (admin["token"], librarian["token"]):
        response = client.get(f"/api/v1/branches/{branch['id']}", headers=bearer(token))
        assert response.status_code == 200, response.text
        assert response.json()["code"] == "MERKEZ"
    assert_error(client.get(f"/api/v1/branches/{branch['id']}"), 401, "UNAUTHENTICATED")


def test_unknown_branch_is_not_found_and_bad_id_is_validation_error(client, admin):
    assert_error(
        client.get("/api/v1/branches/999", headers=bearer(admin["token"])), 404, "NOT_FOUND"
    )
    assert_error(
        client.get("/api/v1/branches/0", headers=bearer(admin["token"])), 422, "VALIDATION_ERROR"
    )


# LIB-BR-03 and section 17.2: PATCH changes name, address and active state; admin only.
def test_patch_changes_name_address_and_is_audited(app, client, admin, librarian):
    branch = create_branch(client, admin["token"], "MERKEZ")
    assert_error(
        client.patch(
            f"/api/v1/branches/{branch['id']}",
            json={"name": "Renamed"},
            headers=bearer(librarian["token"]),
        ),
        403,
        "FORBIDDEN",
    )
    response = client.patch(
        f"/api/v1/branches/{branch['id']}",
        json={"name": " Renamed ", "address": "New address"},
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed"
    assert response.json()["address"] == "New address"
    assert response.json()["code"] == "MERKEZ"
    with app.state.session_factory() as session:
        entry = session.scalar(select(AuditEntry).where(AuditEntry.event == "branch_updated"))
        assert entry.details["name"] == {"old": "Central Library", "new": "Renamed"}


# section 17.2: the code is not changed by PATCH; null is not a value.
@pytest.mark.parametrize(
    "body",
    [{"code": "KAMPUS"}, {"name": None}, {"is_active": None}, {"unknown": True}],
)
def test_patch_rejects_code_and_null_values(client, admin, body):
    branch = create_branch(client, admin["token"], "MERKEZ")
    response = client.patch(
        f"/api/v1/branches/{branch['id']}", json=body, headers=bearer(admin["token"])
    )
    assert_error(response, 422, "VALIDATION_ERROR")


# LIB-BR-03: deactivation is allowed for a branch that no member uses.
def test_branch_without_members_can_be_deactivated_and_reactivated(client, admin):
    branch = create_branch(client, admin["token"], "KAMPUS")
    url = f"/api/v1/branches/{branch['id']}"
    response = client.patch(url, json={"is_active": False}, headers=bearer(admin["token"]))
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False

    response = client.patch(url, json={"is_active": True}, headers=bearer(admin["token"]))
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True


# LIB-BR-03 with LIB-BR-04: a branch that is the home branch of a member cannot be deactivated.
def test_branch_used_as_home_branch_cannot_be_deactivated(client, admin):
    branch = create_branch(client, admin["token"], "MERKEZ")
    response = client.post(
        "/api/v1/members",
        json={
            "full_name": "Ayşe Yılmaz",
            "email": "ayse@example.edu.tr",
            "membership_type": "student",
            "university_id": "20231234",
            "home_branch_id": branch["id"],
            "password": PASSWORD,
        },
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 201, response.text

    response = client.patch(
        f"/api/v1/branches/{branch['id']}",
        json={"is_active": False},
        headers=bearer(admin["token"]),
    )
    assert_error(response, 409, "BRANCH_IN_USE")
    assert (
        client.get(f"/api/v1/branches/{branch['id']}", headers=bearer(admin["token"])).json()[
            "is_active"
        ]
        is True
    )
