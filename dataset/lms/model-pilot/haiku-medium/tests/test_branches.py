import datetime

import pytest
from fastapi.testclient import TestClient

from lms import FixedClock, Settings, create_app

LOCAL = datetime.timezone(datetime.timedelta(hours=3))
ADMIN = "admin@library.local"
ADMIN_PASSWORD = "ChangeMe123"
PASSWORD = "Secret123"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime.datetime(2026, 11, 5, 9, 30, tzinfo=LOCAL))


@pytest.fixture
def client(clock: FixedClock) -> TestClient:
    return TestClient(create_app(Settings(database_url="sqlite://", clock=clock)))


def login(client, email, password=PASSWORD) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin(client) -> dict:
    return login(client, ADMIN, ADMIN_PASSWORD)


@pytest.fixture
def librarian(client, admin) -> dict:
    response = client.post(
        "/api/v1/users",
        json={"email": "lib@library.local", "full_name": "Librarian", "role": "librarian", "password": PASSWORD},
        headers=admin,
    )
    assert response.status_code == 201, response.text
    return login(client, "lib@library.local")


def error_code(response) -> str:
    return response.json()["error"]["code"]


def create_branch(client, headers, code="MAIN", name="Central", address="Campus"):
    return client.post(
        "/api/v1/branches",
        json={"code": code, "name": name, "address": address},
        headers=headers,
    )


def test_create_branch_stores_upper_case_code(client, admin):
    response = create_branch(client, admin, code="  merkez ", name=" Central Library ", address="")
    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "code": "MERKEZ",
        "name": "Central Library",
        "address": "",
        "is_active": True,
        "created_at": "2026-11-05T09:30:00+03:00",
    }


def test_duplicate_branch_code_is_conflict(client, admin):
    create_branch(client, admin, code="MAIN")
    response = create_branch(client, admin, code="main")
    assert response.status_code == 409
    assert error_code(response) == "CONFLICT"


def test_invalid_branch_code_is_validation_error(client, admin):
    response = create_branch(client, admin, code="A")
    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["fields"][0]["field"] == "code"


def test_only_admin_creates_branches(client, librarian):
    response = create_branch(client, librarian)
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_list_is_ordered_by_code_and_filters_by_active(client, admin):
    create_branch(client, admin, code="ZETA")
    create_branch(client, admin, code="ALFA")
    client.patch("/api/v1/branches/1", json={"is_active": False}, headers=admin)

    everything = client.get("/api/v1/branches", headers=admin).json()
    assert everything["total"] == 2
    assert [b["code"] for b in everything["items"]] == ["ALFA", "ZETA"]

    inactive = client.get("/api/v1/branches?is_active=false", headers=admin).json()
    assert [b["code"] for b in inactive["items"]] == ["ZETA"]


def test_any_authenticated_user_reads_branches(client, admin, librarian):
    create_branch(client, admin)
    assert client.get("/api/v1/branches/1", headers=librarian).status_code == 200
    assert client.get("/api/v1/branches", headers=librarian).status_code == 200
    assert client.get("/api/v1/branches/99", headers=admin).status_code == 404
    assert client.get("/api/v1/branches/1").status_code == 401


def test_patch_changes_name_address_and_state(client, admin, librarian):
    create_branch(client, admin)
    response = client.patch("/api/v1/branches/1", json={"name": "Main", "address": "North"}, headers=admin)
    assert response.status_code == 200
    assert response.json()["name"] == "Main"
    assert response.json()["address"] == "North"
    assert client.patch("/api/v1/branches/1", json={"code": "B"}, headers=admin).status_code == 422
    assert client.patch("/api/v1/branches/1", json={"name": "X"}, headers=librarian).status_code == 403


def test_branch_with_members_cannot_be_deactivated(client, admin, librarian):
    create_branch(client, admin)
    registered = client.post(
        "/api/v1/members",
        json={
            "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr", "membership_type": "student",
            "university_id": "20231234", "home_branch_id": 1, "password": PASSWORD,
        },
        headers=librarian,
    )
    assert registered.status_code == 201, registered.text

    response = client.patch("/api/v1/branches/1", json={"is_active": False}, headers=admin)
    assert response.status_code == 409
    assert error_code(response) == "BRANCH_IN_USE"


def test_unused_branch_can_be_deactivated_and_reactivated(client, admin):
    create_branch(client, admin)
    assert client.patch("/api/v1/branches/1", json={"is_active": False}, headers=admin).json()["is_active"] is False
    assert client.patch("/api/v1/branches/1", json={"is_active": True}, headers=admin).json()["is_active"] is True


def test_inactive_branch_cannot_be_a_home_branch(client, admin, librarian):
    create_branch(client, admin)
    client.patch("/api/v1/branches/1", json={"is_active": False}, headers=admin)
    response = client.post(
        "/api/v1/members",
        json={
            "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr", "membership_type": "student",
            "university_id": "20231234", "home_branch_id": 1, "password": PASSWORD,
        },
        headers=librarian,
    )
    assert response.status_code == 409
    assert error_code(response) == "BRANCH_INACTIVE"
