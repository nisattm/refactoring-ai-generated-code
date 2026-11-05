"""HTTP behavior of module 3: members (section 7, LIB-MEM-01 to LIB-MEM-13)."""

import pytest
from helpers import local_datetime
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


def student_body(branch_id, **changes):
    body = {
        "full_name": "Ayşe Yılmaz",
        "email": "Ayse@Example.edu.tr",
        "membership_type": "student",
        "university_id": "20231234",
        "home_branch_id": branch_id,
        "password": PASSWORD,
    }
    body.update(changes)
    return body


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


@pytest.fixture
def branch(client, admin):
    response = client.post(
        "/api/v1/branches",
        json={"code": "MERKEZ", "name": "Central Library", "address": ""},
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def other_branch(client, admin):
    response = client.post(
        "/api/v1/branches",
        json={"code": "KAMPUS", "name": "Campus Library", "address": ""},
        headers=bearer(admin["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def register(client, token, body):
    return client.post("/api/v1/members", json=body, headers=bearer(token))


def register_ok(client, token, body):
    response = register(client, token, body)
    assert response.status_code == 201, response.text
    return response.json()


# LIB-MEM-01, LIB-MEM-03, LIB-AUTH-04
def test_registration_creates_member_and_member_account(client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    assert set(member) == {
        "id",
        "member_no",
        "full_name",
        "email",
        "phone",
        "membership_type",
        "university_id",
        "home_branch_id",
        "status",
        "membership_start",
        "valid_until",
        "membership_valid",
        "created_at",
    }
    assert member["member_no"] == "M000001"
    assert member["email"] == "ayse@example.edu.tr"
    assert member["phone"] is None
    assert member["status"] == "active"
    assert member["membership_start"] == "2026-11-05"
    assert member["valid_until"] == "2027-11-04"
    assert member["membership_valid"] is True
    assert member["created_at"] == "2026-11-05T09:30:00+03:00"

    token = token_of(client, "ayse@example.edu.tr", PASSWORD)
    me = client.get("/api/v1/auth/me", headers=bearer(token)).json()
    assert me["role"] == "member"
    assert me["member_id"] == member["id"]


# LIB-MEM-03 examples
def test_validity_examples_of_section_7(client, clock, librarian, branch):
    clock.set(local_datetime(2026, 11, 2, 9, 30))
    student = register_ok(client, librarian["token"], student_body(branch["id"]))
    guest = register_ok(
        client,
        librarian["token"],
        student_body(
            branch["id"],
            email="guest@example.com",
            membership_type="guest",
            university_id=None,
            phone="+90 532 123 45 67",
        ),
    )
    assert student["valid_until"] == "2027-11-01"
    assert guest["valid_until"] == "2027-01-30"


# LIB-MEM-02
def test_guest_needs_phone_and_no_university_id(client, librarian, branch):
    body = student_body(branch["id"], membership_type="guest", university_id=None)
    error = assert_error(register(client, librarian["token"], body), 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["phone"]

    body = student_body(branch["id"], membership_type="guest", phone="+90 532 123 45 67")
    error = assert_error(register(client, librarian["token"], body), 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["university_id"]


# LIB-MEM-02, LIB-MEM-03: a guest registration has 90 days and no university ID
def test_guest_registration(client, librarian, branch):
    member = register_ok(
        client,
        librarian["token"],
        student_body(
            branch["id"],
            membership_type="guest",
            university_id=None,
            phone=" +90 532 123 45 67 ",
        ),
    )
    assert member["university_id"] is None
    assert member["phone"] == "+90 532 123 45 67"
    assert member["valid_until"] == "2027-02-02"


# LIB-MEM-02: university_id is required for non-guests
@pytest.mark.parametrize("membership_type", ["student", "academic", "staff"])
def test_non_guest_needs_university_id(client, librarian, branch, membership_type):
    body = student_body(branch["id"], membership_type=membership_type, university_id=None)
    error = assert_error(register(client, librarian["token"], body), 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["university_id"]


# section 7.2: phone and university ID formats
@pytest.mark.parametrize("phone", ["12345", "abcdefghij", "+", "90 532 123 45 67 89 01 23"])
def test_invalid_phone_is_rejected(client, librarian, branch, phone):
    body = student_body(branch["id"], phone=phone)
    error = assert_error(register(client, librarian["token"], body), 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["phone"]


@pytest.mark.parametrize("university_id", ["abc", "ab-1234", "A" * 21])
def test_invalid_university_id_is_rejected(client, librarian, branch, university_id):
    body = student_body(branch["id"], university_id=university_id)
    error = assert_error(register(client, librarian["token"], body), 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["university_id"]


# LIB-MEM-05, LIB-AUTH-05
def test_duplicate_e_mail_is_conflict_with_field(client, librarian, branch):
    register_ok(client, librarian["token"], student_body(branch["id"]))
    response = register(
        client,
        librarian["token"],
        student_body(branch["id"], email="AYSE@example.edu.tr", university_id="99999999"),
    )
    error = assert_error(response, 409, "CONFLICT")
    assert error["details"] == {"field": "email"}

    response = register(
        client,
        librarian["token"],
        student_body(branch["id"], email="lib@library.local", university_id="99999999"),
    )
    assert_error(response, 409, "CONFLICT")


# LIB-MEM-05 with LIB-COM-30: university IDs are compared case-insensitively
def test_duplicate_university_id_is_conflict_with_field(client, librarian, branch):
    register_ok(client, librarian["token"], student_body(branch["id"], university_id="ab12cd"))
    response = register(
        client,
        librarian["token"],
        student_body(branch["id"], email="other@example.edu.tr", university_id="AB12CD"),
    )
    error = assert_error(response, 409, "CONFLICT")
    assert error["details"] == {"field": "university_id"}


# LIB-COM-29
def test_unknown_home_branch_is_not_found(client, librarian):
    response = register(client, librarian["token"], student_body(999))
    error = assert_error(response, 404, "NOT_FOUND")
    assert error["details"] == {"field": "home_branch_id", "id": 999}


# LIB-BR-04: an inactive branch cannot be a home branch, checked before other 409 checks
def test_inactive_home_branch_is_rejected_first(client, admin, librarian, branch, other_branch):
    register_ok(client, librarian["token"], student_body(branch["id"]))
    client.patch(
        f"/api/v1/branches/{other_branch['id']}",
        json={"is_active": False},
        headers=bearer(admin["token"]),
    )
    response = register(
        client,
        librarian["token"],
        student_body(other_branch["id"], email="ayse@example.edu.tr", university_id="99999999"),
    )
    assert_error(response, 409, "BRANCH_INACTIVE")


# LIB-COM-28: role before validation, validation before existence
def test_registration_check_order(client, librarian, branch):
    body = student_body(branch["id"])
    token_response = client.post("/api/v1/members", json=body)
    assert_error(token_response, 401, "UNAUTHENTICATED")

    member_token = register_ok_member(client, librarian, branch)
    response = register(client, member_token, student_body(branch["id"], email="x@example.com"))
    assert_error(response, 403, "FORBIDDEN")

    response = register(client, librarian["token"], student_body(999, password="short"))
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert [field["field"] for field in error["details"]["fields"]] == ["password"]


def register_ok_member(client, librarian, branch):
    register_ok(client, librarian["token"], student_body(branch["id"]))
    return token_of(client, "ayse@example.edu.tr", PASSWORD)


# LIB-MEM-06
def test_list_members_filters_and_text_search(client, clock, librarian, branch, other_branch):
    register_ok(client, librarian["token"], student_body(branch["id"]))
    register_ok(
        client,
        librarian["token"],
        student_body(
            branch["id"],
            full_name="Mehmet Demir",
            email="mehmet@example.edu.tr",
            membership_type="academic",
            university_id="MD2024",
        ),
    )
    register_ok(
        client,
        librarian["token"],
        student_body(
            other_branch["id"],
            full_name="Zeynep Kaya",
            email="zeynep@example.com",
            membership_type="guest",
            university_id=None,
            phone="+90 555 123 45 67",
        ),
    )
    url = "/api/v1/members"
    headers = bearer(librarian["token"])

    everyone = client.get(url, headers=headers).json()
    assert everyone["total"] == 3
    assert [item["id"] for item in everyone["items"]] == [1, 2, 3]

    def names(params):
        response = client.get(url, params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [item["full_name"] for item in response.json()["items"]]

    # LIB-COM-30: "Yılmaz" matches "YILMAZ" and "yilmaz"; "AYŞE" matches "Ayşe".
    assert names({"q": "YILMAZ"}) == ["Ayşe Yılmaz"]
    assert names({"q": "AYŞE"}) == ["Ayşe Yılmaz"]
    assert names({"q": "md2024"}) == ["Mehmet Demir"]
    assert names({"q": "M000003"}) == ["Zeynep Kaya"]
    assert names({"q": "zeynep@"}) == ["Zeynep Kaya"]
    assert names({"membership_type": "academic"}) == ["Mehmet Demir"]
    assert names({"status": "passive"}) == []
    assert names({"home_branch_id": other_branch["id"]}) == ["Zeynep Kaya"]

    page = client.get(url, params={"page": 2, "page_size": 2}, headers=headers).json()
    assert [item["id"] for item in page["items"]] == [3]
    assert page["total"] == 3

    # LIB-MEM-04: after valid_until (2027-11-04) the membership is no longer valid.
    # The librarian's token lasts 12 hours, so log in again after moving the clock.
    clock.set(local_datetime(2027, 11, 5, 9, 30))
    headers = bearer(token_of(client, "lib@library.local", PASSWORD))
    assert names({"membership_valid": "false"}) == ["Ayşe Yılmaz", "Mehmet Demir", "Zeynep Kaya"]
    assert names({"membership_valid": "true"}) == []

    # LIB-COM-29: a home branch filter must name an existing branch.
    error = assert_error(
        client.get(url, params={"home_branch_id": 999}, headers=headers), 404, "NOT_FOUND"
    )
    assert error["details"] == {"field": "home_branch_id", "id": 999}


# LIB-MEM-06, LIB-COM-18: paging parameters are validated
def test_list_members_rejects_bad_paging_and_roles(client, librarian, branch):
    assert_error(
        client.get(
            "/api/v1/members", params={"page_size": 101}, headers=bearer(librarian["token"])
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(client.get("/api/v1/members"), 401, "UNAUTHENTICATED")
    member_token = register_ok_member(client, librarian, branch)
    assert_error(client.get("/api/v1/members", headers=bearer(member_token)), 403, "FORBIDDEN")


# LIB-AUTH-25, LIB-COM-28, LIB-MEM-13
def test_members_read_only_their_own_record(client, librarian, branch):
    own = register_ok(client, librarian["token"], student_body(branch["id"]))
    other = register_ok(
        client,
        librarian["token"],
        student_body(branch["id"], email="mehmet@example.edu.tr", university_id="MD2024"),
    )
    token = token_of(client, "ayse@example.edu.tr", PASSWORD)

    assert client.get(f"/api/v1/members/{own['id']}", headers=bearer(token)).status_code == 200
    assert_error(
        client.get(f"/api/v1/members/{other['id']}", headers=bearer(token)), 403, "FORBIDDEN"
    )
    # A member asking for a record that does not exist gets 404, not 403.
    assert_error(client.get("/api/v1/members/999", headers=bearer(token)), 404, "NOT_FOUND")
    assert_error(client.get("/api/v1/members/0", headers=bearer(token)), 422, "VALIDATION_ERROR")

    me = client.get("/api/v1/members/me", headers=bearer(token))
    assert me.status_code == 200, me.text
    assert me.json()["id"] == own["id"]
    assert_error(
        client.get("/api/v1/members/me", headers=bearer(librarian["token"])), 403, "FORBIDDEN"
    )
    assert_error(client.get("/api/v1/members/me"), 401, "UNAUTHENTICATED")

    staff_view = client.get(f"/api/v1/members/{other['id']}", headers=bearer(librarian["token"]))
    assert staff_view.status_code == 200
    assert staff_view.json()["id"] == other["id"]


# LIB-MEM-07: name and e-mail changes are also made on the user account
def test_update_changes_member_and_user_account(client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    response = client.patch(
        f"/api/v1/members/{member['id']}",
        json={
            "full_name": "Ayşe Demir",
            "email": "ayse.demir@example.edu.tr",
            "phone": "05321234567",
        },
        headers=bearer(librarian["token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Ayşe Demir"
    assert body["email"] == "ayse.demir@example.edu.tr"
    assert body["phone"] == "05321234567"
    assert body["membership_start"] == "2026-11-05"
    assert body["valid_until"] == "2027-11-04"

    assert_error(
        client.post(
            "/api/v1/auth/login",
            json={"email": "ayse@example.edu.tr", "password": PASSWORD},
        ),
        401,
        "INVALID_CREDENTIALS",
    )
    token = token_of(client, "ayse.demir@example.edu.tr", PASSWORD)
    me = client.get("/api/v1/auth/me", headers=bearer(token)).json()
    assert me["full_name"] == "Ayşe Demir"
    assert me["member_id"] == member["id"]


# LIB-MEM-05 applies to updates too
def test_update_rejects_taken_e_mail_and_university_id(client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    register_ok(
        client,
        librarian["token"],
        student_body(branch["id"], email="mehmet@example.edu.tr", university_id="MD2024"),
    )
    url = f"/api/v1/members/{member['id']}"
    headers = bearer(librarian["token"])
    error = assert_error(
        client.patch(url, json={"email": "lib@library.local"}, headers=headers), 409, "CONFLICT"
    )
    assert error["details"] == {"field": "email"}
    error = assert_error(
        client.patch(url, json={"university_id": "md2024"}, headers=headers), 409, "CONFLICT"
    )
    assert error["details"] == {"field": "university_id"}


# LIB-MEM-07, LIB-MEM-08: the resulting member must satisfy LIB-MEM-02 (409 MEMBER_FIELDS_INVALID)
def test_type_change_keeps_type_specific_rules(client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    url = f"/api/v1/members/{member['id']}"
    headers = bearer(librarian["token"])

    error = assert_error(
        client.patch(url, json={"membership_type": "guest"}, headers=headers),
        409,
        "MEMBER_FIELDS_INVALID",
    )
    assert error["details"]["fields"] == [{"field": "phone", "problem": "is required for guests"}]

    # A change to guest with a phone sets university_id to null (LIB-MEM-08).
    response = client.patch(
        url, json={"membership_type": "guest", "phone": "+90 532 123 45 67"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["university_id"] is None
    assert response.json()["valid_until"] == "2027-11-04"

    # A change from guest requires university_id in the same request.
    error = assert_error(
        client.patch(url, json={"membership_type": "student"}, headers=headers),
        409,
        "MEMBER_FIELDS_INVALID",
    )
    assert error["details"]["fields"][0]["field"] == "university_id"
    response = client.patch(
        url, json={"membership_type": "student", "university_id": "20231234"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["membership_type"] == "student"

    # Removing university_id from a non-guest is invalid.
    assert_error(
        client.patch(url, json={"university_id": None}, headers=headers),
        409,
        "MEMBER_FIELDS_INVALID",
    )


# LIB-MEM-07, LIB-BR-04: PATCH validation and the branch rules
def test_update_validation_and_branch_rules(client, admin, librarian, branch, other_branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    url = f"/api/v1/members/{member['id']}"
    headers = bearer(librarian["token"])

    for body in (
        {"full_name": None},
        {"membership_type": "member"},
        {"member_no": "M1"},
        {"valid_until": "2030-01-01"},
    ):
        assert_error(client.patch(url, json=body, headers=headers), 422, "VALIDATION_ERROR")

    client.patch(
        f"/api/v1/branches/{other_branch['id']}",
        json={"is_active": False},
        headers=bearer(admin["token"]),
    )
    assert_error(
        client.patch(url, json={"home_branch_id": other_branch["id"]}, headers=headers),
        409,
        "BRANCH_INACTIVE",
    )
    assert_error(client.patch(url, json={"home_branch_id": 999}, headers=headers), 404, "NOT_FOUND")

    member_token = token_of(client, "ayse@example.edu.tr", PASSWORD)
    assert_error(
        client.patch(url, json={"full_name": "Mine"}, headers=bearer(member_token)),
        403,
        "FORBIDDEN",
    )


# LIB-MEM-09
def test_renew_membership_extends_or_restarts_validity(client, clock, librarian, branch):
    student = register_ok(client, librarian["token"], student_body(branch["id"]))
    guest = register_ok(
        client,
        librarian["token"],
        student_body(
            branch["id"],
            email="guest@example.com",
            membership_type="guest",
            university_id=None,
            phone="+90 532 123 45 67",
        ),
    )
    headers = bearer(librarian["token"])

    # valid_until >= today: extended by 365 days (guest: 90).
    renewed = client.post(f"/api/v1/members/{student['id']}/renew-membership", headers=headers)
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["valid_until"] == "2028-11-03"
    guest_renewed = client.post(f"/api/v1/members/{guest['id']}/renew-membership", headers=headers)
    assert guest_renewed.json()["valid_until"] == "2027-05-03"

    # valid_until < today: restarts at today + 364 days (guest: today + 89).
    # The librarian's token lasts 12 hours, so log in again after moving the clock.
    clock.set(local_datetime(2028, 12, 1, 9, 30))
    headers = bearer(token_of(client, "lib@library.local", PASSWORD))
    assert (
        client.get(f"/api/v1/members/{student['id']}", headers=headers).json()["membership_valid"]
        is False
    )
    restarted = client.post(f"/api/v1/members/{student['id']}/renew-membership", headers=headers)
    assert restarted.json()["valid_until"] == "2029-11-30"
    assert restarted.json()["membership_valid"] is True
    guest_restarted = client.post(
        f"/api/v1/members/{guest['id']}/renew-membership", headers=headers
    )
    assert guest_restarted.json()["valid_until"] == "2029-02-28"

    member_token = token_of(client, "ayse@example.edu.tr", PASSWORD)
    assert_error(
        client.post(
            f"/api/v1/members/{student['id']}/renew-membership", headers=bearer(member_token)
        ),
        403,
        "FORBIDDEN",
    )


# LIB-MEM-09, LIB-MEM-10, LIB-MEM-11
def test_deactivate_and_activate(client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    headers = bearer(librarian["token"])
    base = f"/api/v1/members/{member['id']}"

    response = client.post(f"{base}/deactivate", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "passive"
    assert response.json()["membership_valid"] is False
    assert_error(client.post(f"{base}/deactivate", headers=headers), 409, "MEMBER_PASSIVE")
    assert_error(client.post(f"{base}/renew-membership", headers=headers), 409, "MEMBER_PASSIVE")

    # The user account stays active: the member can still log in and read own data.
    token = token_of(client, "ayse@example.edu.tr", PASSWORD)
    assert client.get("/api/v1/members/me", headers=bearer(token)).json()["status"] == "passive"

    response = client.post(f"{base}/activate", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["valid_until"] == "2027-11-04"
    assert_error(client.post(f"{base}/activate", headers=headers), 409, "MEMBER_ALREADY_ACTIVE")

    member_token = token
    assert_error(client.post(f"{base}/deactivate", headers=bearer(member_token)), 403, "FORBIDDEN")


# LIB-MEM-07 to LIB-MEM-11: each change is audited with the affected member
def test_member_events_are_audited(app, client, librarian, branch):
    member = register_ok(client, librarian["token"], student_body(branch["id"]))
    base = f"/api/v1/members/{member['id']}"
    headers = bearer(librarian["token"])
    client.patch(base, json={"full_name": "Ayşe Demir"}, headers=headers)
    client.post(f"{base}/renew-membership", headers=headers)
    client.post(f"{base}/deactivate", headers=headers)
    client.post(f"{base}/activate", headers=headers)

    with app.state.session_factory() as session:
        entries = session.scalars(
            select(AuditEntry).where(AuditEntry.entity_type == "member").order_by(AuditEntry.id)
        ).all()
        events = [entry.event for entry in entries]
        assert events == [
            "member_registered",
            "member_updated",
            "membership_renewed",
            "member_deactivated",
            "member_activated",
        ]
        assert all(entry.entity_id == member["id"] for entry in entries)
        assert entries[1].details["full_name"] == {"old": "Ayşe Yılmaz", "new": "Ayşe Demir"}
        assert "password" not in str(entries[0].details).lower()
