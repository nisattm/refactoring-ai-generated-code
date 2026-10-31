import sqlalchemy as sa

from tests.test_auth import audit, err, h, make_user, token_of  # noqa: F401
from tests.test_auth import admin_h  # noqa: F401  (fixture)


def mk_branch(client, admin_h, code="MERKEZ", name="Central Library", address="Main St", **kw):
    r = client.post("/api/v1/branches", headers=admin_h, json={"code": code, "name": name, "address": address, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def lib_h(client, admin_h):
    make_user(client, admin_h)
    return h(token_of(client, "lib@example.com", "Passw0rd1"))


def test_create_branch(client, admin_h, app):
    r = client.post("/api/v1/branches", headers=admin_h, json={"code": "kampus2", "name": " North ", "address": ""})
    assert r.status_code == 201
    b = r.json()
    assert b["id"] == 1 and b["code"] == "KAMPUS2" and b["name"] == "North" and b["is_active"] is True
    assert b["created_at"].endswith("+03:00")
    assert [a.entity_id for a in audit(app, "branch_created")] == [1]


def test_create_branch_address_optional(client, admin_h):
    r = client.post("/api/v1/branches", headers=admin_h, json={"code": "AB", "name": "x"})
    assert r.status_code == 201 and r.json()["address"] == ""


def test_create_branch_validation(client, admin_h):
    for body in (
        {"code": "A", "name": "x", "address": ""},
        {"code": "ABCDEFGHIJK", "name": "x", "address": ""},
        {"code": "A-B", "name": "x", "address": ""},
        {"code": "AB", "name": "  ", "address": ""},
        {"code": "AB", "name": "x", "address": "a" * 301},
        {"code": "AB", "name": "x", "address": "", "is_active": False},
    ):
        err(client.post("/api/v1/branches", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_create_branch_duplicate_case_insensitive(client, admin_h):
    mk_branch(client, admin_h, "AB")
    e = err(client.post("/api/v1/branches", headers=admin_h, json={"code": "ab", "name": "y", "address": ""}), 409, "CONFLICT")
    assert e["details"]["field"] == "code"


def test_branch_permissions(client, admin_h):
    mk_branch(client, admin_h)
    lh = lib_h(client, admin_h)
    err(client.post("/api/v1/branches", json={"code": "AB", "name": "x"}), 401, "UNAUTHENTICATED")
    err(client.post("/api/v1/branches", headers=lh, json={"code": "AB", "name": "x"}), 403, "FORBIDDEN")
    err(client.patch("/api/v1/branches/1", headers=lh, json={"name": "x"}), 403, "FORBIDDEN")
    err(client.get("/api/v1/branches"), 401, "UNAUTHENTICATED")
    assert client.get("/api/v1/branches", headers=lh).status_code == 200
    assert client.get("/api/v1/branches/1", headers=lh).status_code == 200


def test_list_branches_order_filter_pagination(client, admin_h):
    for code in ("ZETA", "ALFA", "MID"):
        mk_branch(client, admin_h, code)
    client.patch("/api/v1/branches/3", headers=admin_h, json={"is_active": False})
    r = client.get("/api/v1/branches", headers=admin_h).json()
    assert [b["code"] for b in r["items"]] == ["ALFA", "MID", "ZETA"] and r["total"] == 3
    r = client.get("/api/v1/branches?is_active=false", headers=admin_h).json()
    assert [b["code"] for b in r["items"]] == ["MID"]
    r = client.get("/api/v1/branches?page_size=2&page=2", headers=admin_h).json()
    assert [b["code"] for b in r["items"]] == ["ZETA"] and r["page"] == 2 and r["total"] == 3
    err(client.get("/api/v1/branches?page_size=101", headers=admin_h), 422, "VALIDATION_ERROR")


def test_get_branch_404_and_422(client, admin_h):
    err(client.get("/api/v1/branches/99", headers=admin_h), 404, "NOT_FOUND")
    err(client.get("/api/v1/branches/abc", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.patch("/api/v1/branches/99", headers=admin_h, json={"name": "x"}), 404, "NOT_FOUND")


def test_patch_branch(client, admin_h, app):
    mk_branch(client, admin_h)
    r = client.patch("/api/v1/branches/1", headers=admin_h, json={"name": "New", "address": "Addr"})
    assert r.status_code == 200 and r.json()["name"] == "New" and r.json()["address"] == "Addr"
    assert audit(app, "branch_updated")[0].details == {
        "name": {"old": "Central Library", "new": "New"},
        "address": {"old": "Main St", "new": "Addr"},
    }
    err(client.patch("/api/v1/branches/1", headers=admin_h, json={"code": "XX"}), 422, "VALIDATION_ERROR")
    err(client.patch("/api/v1/branches/1", headers=admin_h, json={"name": None}), 422, "VALIDATION_ERROR")


def test_deactivate_and_reactivate_branch(client, admin_h):
    mk_branch(client, admin_h)
    r = client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": False}).status_code == 200
    r = client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": True})
    assert r.json()["is_active"] is True


def member_body(branch_id=1, **kw):
    body = {
        "full_name": "Ayşe Yılmaz",
        "email": "ayse@example.edu.tr",
        "membership_type": "student",
        "university_id": "20231234",
        "home_branch_id": branch_id,
        "password": "Passw0rd1",
    }
    body.update(kw)
    return body


def test_branch_in_use_by_member(client, admin_h, app):
    mk_branch(client, admin_h)
    mk_branch(client, admin_h, "SECOND")
    assert client.post("/api/v1/members", headers=admin_h, json=member_body()).status_code == 201
    e = err(client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    assert e["details"]["id"] == 1
    assert client.get("/api/v1/branches/1", headers=admin_h).json()["is_active"] is True
    assert audit(app, "branch_updated") == []
    # a passive member still blocks the branch
    client.post("/api/v1/members/1/deactivate", headers=admin_h)
    err(client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    # moving the member frees the branch
    client.patch("/api/v1/members/1", headers=admin_h, json={"home_branch_id": 2})
    assert client.patch("/api/v1/branches/1", headers=admin_h, json={"is_active": False}).status_code == 200


def test_inactive_branch_rejected_for_members(client, admin_h):
    mk_branch(client, admin_h)
    mk_branch(client, admin_h, "SECOND")
    client.patch("/api/v1/branches/2", headers=admin_h, json={"is_active": False})
    e = err(client.post("/api/v1/members", headers=admin_h, json=member_body(2)), 409, "BRANCH_INACTIVE")
    assert e["details"]["field"] == "home_branch_id"
    # BRANCH_INACTIVE comes before the duplicate-e-mail conflict (LIB-BR-04)
    assert client.post("/api/v1/members", headers=admin_h, json=member_body(1)).status_code == 201
    err(client.post("/api/v1/members", headers=admin_h, json=member_body(2)), 409, "BRANCH_INACTIVE")
    err(client.patch("/api/v1/members/1", headers=admin_h, json={"home_branch_id": 2}), 409, "BRANCH_INACTIVE")
    e = err(client.post("/api/v1/members", headers=admin_h, json=member_body(99)), 404, "NOT_FOUND")
    assert e["details"] == {"field": "home_branch_id", "id": 99}
