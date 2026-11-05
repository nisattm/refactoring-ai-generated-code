import datetime

import pytest
from fastapi.testclient import TestClient

from lms import FixedClock, Settings, create_app

LOCAL = datetime.timezone(datetime.timedelta(hours=3))
ADMIN = "admin@library.local"
ADMIN_PASSWORD = "ChangeMe123"
PASSWORD = "Secret123"
TODAY = datetime.date(2026, 11, 5)


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


@pytest.fixture
def branch(client, admin) -> int:
    response = client.post("/api/v1/branches", json={"code": "MAIN", "name": "Central", "address": ""}, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def student_body(branch_id, **overrides):
    body = {
        "full_name": "Ayşe Yılmaz",
        "email": "Ayse@Example.edu.tr",
        "phone": None,
        "membership_type": "student",
        "university_id": "20231234",
        "home_branch_id": branch_id,
        "password": PASSWORD,
    }
    body.update(overrides)
    return body


def register(client, staff, branch_id, **overrides):
    return client.post("/api/v1/members", json=student_body(branch_id, **overrides), headers=staff)


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_registration_creates_member_and_linked_account(client, librarian, branch):
    response = register(client, librarian, branch)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "id": 1,
        "member_no": "M000001",
        "full_name": "Ayşe Yılmaz",
        "email": "ayse@example.edu.tr",
        "phone": None,
        "membership_type": "student",
        "university_id": "20231234",
        "home_branch_id": branch,
        "status": "active",
        "membership_start": "2026-11-05",
        "valid_until": "2027-11-04",  # 364 days after today (LIB-MEM-03)
        "created_at": "2026-11-05T09:30:00+03:00",
        "membership_valid": True,
    }
    # The account is a member account that can log in with the e-mail address.
    headers = login(client, "ayse@example.edu.tr")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"] == "member"
    assert me["member_id"] == 1


def test_guest_validity_and_phone(client, librarian, branch):
    guest = {
        "full_name": "Guest Person", "email": "guest@example.com", "phone": "+90 555 123 45 67",
        "membership_type": "guest", "university_id": None, "home_branch_id": branch, "password": PASSWORD,
    }
    response = client.post("/api/v1/members", json=guest, headers=librarian)
    assert response.status_code == 201, response.text
    assert response.json()["valid_until"] == (TODAY + datetime.timedelta(days=89)).isoformat()


@pytest.mark.parametrize(
    "overrides",
    [
        {"membership_type": "guest", "phone": None, "university_id": None},  # guest without phone
        {"membership_type": "guest", "phone": "+90 555 123 45 67"},  # guest with university id
        {"membership_type": "staff", "university_id": None},  # non-guest without university id
        {"phone": "05551234567x"},  # phone with a letter
        {"phone": "123456789"},  # only 9 digits
        {"university_id": "12"},  # too short
        {"password": "short"},  # password policy
        {"unknown": "field"},  # unknown field
    ],
)
def test_invalid_registration_is_validation_error(client, librarian, branch, overrides):
    response = register(client, librarian, branch, **overrides)
    assert response.status_code == 422, response.text
    assert error_code(response) == "VALIDATION_ERROR"


def test_unknown_home_branch_is_not_found(client, librarian):
    response = register(client, librarian, 99)
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"field": "home_branch_id", "id": 99}


def test_duplicate_email_and_university_id_are_conflicts(client, librarian, branch):
    assert register(client, librarian, branch).status_code == 201

    response = register(client, librarian, branch, email="AYSE@example.edu.tr", university_id="x1234")
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"field": "email"}

    response = register(client, librarian, branch, email="other@example.edu.tr", university_id="20231234")
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"field": "university_id"}


def test_university_id_is_unique_case_insensitively(client, librarian, branch):
    assert register(client, librarian, branch, university_id="ABCD1234").status_code == 201
    response = register(client, librarian, branch, email="b@example.edu.tr", university_id="abcd1234")
    assert error_code(response) == "CONFLICT"


def test_only_librarian_and_admin_register(client, librarian, branch):
    register(client, librarian, branch)
    member_headers = login(client, "ayse@example.edu.tr")
    response = register(client, member_headers, branch, email="x@example.edu.tr", university_id="99998888")
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_list_is_ordered_paginated_and_filtered(client, librarian, branch):
    register(client, librarian, branch)
    register(client, librarian, branch, full_name="İlker Demir", email="ilker@example.edu.tr", university_id="11112222")
    register(client, librarian, branch, full_name="Staff Person", email="staff@example.edu.tr",
             membership_type="staff", university_id="33334444")

    everything = client.get("/api/v1/members?page_size=2", headers=librarian).json()
    assert everything["total"] == 3
    assert [m["id"] for m in everything["items"]] == [1, 2]

    # Case-insensitive, Turkish-aware substring match (LIB-SRCH-01).
    found = client.get("/api/v1/members?q=ILKER", headers=librarian).json()
    assert [m["member_no"] for m in found["items"]] == ["M000002"]
    assert [m["member_no"] for m in client.get("/api/v1/members?q=m000003", headers=librarian).json()["items"]] == ["M000003"]

    staff_only = client.get("/api/v1/members?membership_type=staff", headers=librarian).json()
    assert [m["id"] for m in staff_only["items"]] == [3]

    assert client.get(f"/api/v1/members?home_branch_id={branch}", headers=librarian).json()["total"] == 3
    assert client.get("/api/v1/members?home_branch_id=99", headers=librarian).status_code == 404


def test_member_sees_only_own_record(client, librarian, branch):
    register(client, librarian, branch)
    register(client, librarian, branch, email="other@example.edu.tr", university_id="99998888")
    member = login(client, "ayse@example.edu.tr")

    own = client.get("/api/v1/members/me", headers=member)
    assert own.status_code == 200
    assert own.json()["member_no"] == "M000001"

    assert client.get("/api/v1/members/2", headers=member).status_code == 403
    assert client.get("/api/v1/members/99", headers=member).status_code == 404
    assert client.get("/api/v1/members/1", headers=member).status_code == 200
    assert client.get("/api/v1/members/me", headers=librarian).status_code == 403


def test_update_changes_user_account_and_keeps_validity(client, librarian, branch):
    register(client, librarian, branch)
    response = client.patch(
        "/api/v1/members/1", json={"full_name": "Ayşe Demir", "email": "new@example.edu.tr"}, headers=librarian
    )
    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Ayşe Demir"
    assert response.json()["valid_until"] == "2027-11-04"
    assert login(client, "new@example.edu.tr")  # the user account follows the e-mail change


def test_change_to_guest_needs_phone_and_clears_university_id(client, librarian, branch):
    register(client, librarian, branch)
    response = client.patch("/api/v1/members/1", json={"membership_type": "guest"}, headers=librarian)
    assert response.status_code == 409
    assert error_code(response) == "MEMBER_FIELDS_INVALID"
    assert response.json()["error"]["details"]["fields"][0]["field"] == "phone"

    response = client.patch(
        "/api/v1/members/1", json={"membership_type": "guest", "phone": "05551234567"}, headers=librarian
    )
    assert response.status_code == 200, response.text
    assert response.json()["university_id"] is None


def test_change_from_guest_needs_university_id(client, librarian, branch):
    client.post(
        "/api/v1/members",
        json={
            "full_name": "Guest", "email": "g@example.com", "phone": "05551234567", "membership_type": "guest",
            "home_branch_id": branch, "password": PASSWORD,
        },
        headers=librarian,
    )
    response = client.patch("/api/v1/members/1", json={"membership_type": "academic"}, headers=librarian)
    assert error_code(response) == "MEMBER_FIELDS_INVALID"
    response = client.patch(
        "/api/v1/members/1", json={"membership_type": "academic", "university_id": "ACAD2024"}, headers=librarian
    )
    assert response.status_code == 200, response.text


def test_renewal_extends_active_and_restarts_expired(client, clock, librarian, branch):
    register(client, librarian, branch)
    renewed = client.post("/api/v1/members/1/renew-membership", headers=librarian)
    assert renewed.status_code == 200
    assert renewed.json()["valid_until"] == "2028-11-03"  # +365 days while still valid (2028 is a leap year)

    clock.set(datetime.datetime(2029, 1, 10, 9, 0, tzinfo=LOCAL))
    librarian = login(client, "lib@library.local")  # the earlier token has expired
    expired = client.get("/api/v1/members/1", headers=librarian).json()
    assert expired["membership_valid"] is False
    renewed = client.post("/api/v1/members/1/renew-membership", headers=librarian).json()
    assert renewed["valid_until"] == "2030-01-09"  # today + 364 days


def test_deactivate_and_activate_cycle(client, librarian, branch):
    register(client, librarian, branch)
    deactivated = client.post("/api/v1/members/1/deactivate", headers=librarian)
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "passive"
    assert deactivated.json()["membership_valid"] is False
    assert error_code(client.post("/api/v1/members/1/deactivate", headers=librarian)) == "MEMBER_PASSIVE"
    assert error_code(client.post("/api/v1/members/1/renew-membership", headers=librarian)) == "MEMBER_PASSIVE"

    # The account stays active, so the member can still log in.
    assert login(client, "ayse@example.edu.tr")

    activated = client.post("/api/v1/members/1/activate", headers=librarian)
    assert activated.status_code == 200
    assert activated.json()["valid_until"] == "2027-11-04"
    assert error_code(client.post("/api/v1/members/1/activate", headers=librarian)) == "MEMBER_ALREADY_ACTIVE"


def test_membership_valid_filter_uses_today(client, clock, librarian, branch):
    register(client, librarian, branch)
    clock.set(datetime.datetime(2027, 12, 1, 9, 0, tzinfo=LOCAL))
    librarian = login(client, "lib@library.local")  # the earlier token has expired
    assert client.get("/api/v1/members?membership_valid=false", headers=librarian).json()["total"] == 1
    assert client.get("/api/v1/members?membership_valid=true", headers=librarian).json()["total"] == 0
