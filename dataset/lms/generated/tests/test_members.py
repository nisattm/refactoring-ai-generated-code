import datetime

import sqlalchemy as sa

from lms.auth.models import User
from tests.test_auth import admin_h  # noqa: F401  (fixture)
from tests.test_auth import audit, err, h, login, make_user, token_of
from tests.test_branches import lib_h, member_body, mk_branch

TZ = datetime.timezone(datetime.timedelta(hours=3))


def reg(client, admin_h, **kw):
    r = client.post("/api/v1/members", headers=admin_h, json=member_body(**kw))
    assert r.status_code == 201, r.text
    return r.json()


def guest_body(**kw):
    body = member_body(membership_type="guest", phone="+90 532 123 45 67", email="guest@example.com")
    del body["university_id"]
    body.update(kw)
    return body


def setup(client, admin_h):
    mk_branch(client, admin_h)


def test_register_student(client, admin_h, app):
    setup(client, admin_h)
    m = reg(client, admin_h)
    assert m == {
        "id": 1,
        "member_no": "M000001",
        "full_name": "Ayşe Yılmaz",
        "email": "ayse@example.edu.tr",
        "phone": None,
        "membership_type": "student",
        "university_id": "20231234",
        "home_branch_id": 1,
        "status": "active",
        "membership_start": "2026-11-02",
        "valid_until": "2027-11-01",
        "created_at": "2026-11-02T09:30:00+03:00",
        "membership_valid": True,
    }
    # user account with role member, able to log in
    r = login(client, "AYSE@example.edu.tr", "Passw0rd1")
    assert r.status_code == 200
    u = r.json()["user"]
    assert u["role"] == "member" and u["member_id"] == 1 and u["full_name"] == "Ayşe Yılmaz"
    assert [a.event for a in audit(app, "user_created")][-1] == "user_created"


def test_register_validity_by_type(client, admin_h):
    setup(client, admin_h)
    assert reg(client, admin_h, membership_type="academic")["valid_until"] == "2027-11-01"
    assert reg(client, admin_h, membership_type="staff", email="s@example.com", university_id="STAFF01")["valid_until"] == "2027-11-01"
    r = client.post("/api/v1/members", headers=admin_h, json=guest_body())
    assert r.status_code == 201
    g = r.json()
    assert g["valid_until"] == "2027-01-30" and g["university_id"] is None and g["member_no"] == "M000003"


def test_register_type_specific_fields(client, admin_h):
    setup(client, admin_h)
    post = lambda b: client.post("/api/v1/members", headers=admin_h, json=b)
    b = guest_body()
    del b["phone"]
    e = err(post(b), 422, "VALIDATION_ERROR")
    assert [f["field"] for f in e["details"]["fields"]] == ["phone"]
    err(post(guest_body(university_id="12345678")), 422, "VALIDATION_ERROR")
    assert post(guest_body(university_id=None)).status_code == 201
    b = member_body()
    del b["university_id"]
    err(post(b), 422, "VALIDATION_ERROR")
    err(post(member_body(university_id=None)), 422, "VALIDATION_ERROR")


def test_register_field_validation(client, admin_h):
    setup(client, admin_h)
    post = lambda b: client.post("/api/v1/members", headers=admin_h, json=b)
    for kw in (
        {"email": "nope"},
        {"email": "a@b"},
        {"full_name": "   "},
        {"password": "short1"},
        {"password": "onlyletters"},
        {"university_id": "123"},
        {"university_id": "1234-5678"},
        {"phone": "12345"},
        {"phone": "12345678901234567"},
        {"phone": "090-532-123-4567"},
        {"membership_type": "alien"},
        {"home_branch_id": "x"},
    ):
        err(post(member_body(**kw)), 422, "VALIDATION_ERROR")
    err(post({**member_body(), "extra": 1}), 422, "VALIDATION_ERROR")
    assert post(member_body(phone="+90 532 123 45 67")).status_code == 201


def test_register_conflicts(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    e = err(client.post("/api/v1/members", headers=admin_h, json=member_body(email="AYSE@example.edu.tr", university_id="99999999")), 409, "CONFLICT")
    assert e["details"]["field"] == "email"
    e = err(client.post("/api/v1/members", headers=admin_h, json=member_body(email="x@example.com")), 409, "CONFLICT")
    assert e["details"]["field"] == "university_id"
    # e-mail of a staff user also conflicts
    e = err(client.post("/api/v1/members", headers=admin_h, json=member_body(email="admin@library.local", university_id="ZZZZ1")), 409, "CONFLICT")
    assert e["details"]["field"] == "email"
    # nothing was left behind by the failed requests
    with_users = client.get("/api/v1/users", headers=admin_h).json()["total"]
    assert with_users == 2


def test_register_permissions_and_order(client, admin_h):
    setup(client, admin_h)
    lh = lib_h(client, admin_h)
    err(client.post("/api/v1/members", json=member_body()), 401, "UNAUTHENTICATED")
    assert client.post("/api/v1/members", headers=lh, json=member_body()).status_code == 201
    mh = h(token_of(client, "ayse@example.edu.tr", "Passw0rd1"))
    err(client.post("/api/v1/members", headers=mh, json=member_body(email="o@example.com")), 403, "FORBIDDEN")
    # 422 before 404 for the branch reference
    err(client.post("/api/v1/members", headers=lh, json=member_body(99, email="")), 422, "VALIDATION_ERROR")


def test_member_users_cannot_be_created_directly(client, admin_h):
    r = client.post("/api/v1/users", headers=admin_h, json={"email": "m@example.com", "full_name": "M", "role": "member", "password": "Passw0rd1"})
    err(r, 422, "VALIDATION_ERROR")


def test_get_member_and_ownership(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    reg(client, admin_h, email="b@example.com", university_id="BBBB1111")
    mh = h(token_of(client, "ayse@example.edu.tr", "Passw0rd1"))
    assert client.get("/api/v1/members/1", headers=mh).json()["id"] == 1
    err(client.get("/api/v1/members/2", headers=mh), 403, "FORBIDDEN")
    err(client.get("/api/v1/members/99", headers=mh), 404, "NOT_FOUND")
    err(client.get("/api/v1/members/99", headers=admin_h), 404, "NOT_FOUND")
    err(client.get("/api/v1/members/0", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get("/api/v1/members/1"), 401, "UNAUTHENTICATED")
    assert client.get("/api/v1/members/2/summary", headers=mh).status_code == 403
    assert client.get("/api/v1/members/1/summary", headers=mh).status_code == 200
    err(client.get("/api/v1/members", headers=mh), 403, "FORBIDDEN")
    err(client.patch("/api/v1/members/1", headers=mh, json={"full_name": "X"}), 403, "FORBIDDEN")
    err(client.post("/api/v1/members/1/deactivate", headers=mh), 403, "FORBIDDEN")


def test_me(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    mh = h(token_of(client, "ayse@example.edu.tr", "Passw0rd1"))
    assert client.get("/api/v1/members/me", headers=mh).json()["id"] == 1
    err(client.get("/api/v1/members/me", headers=admin_h), 404, "NOT_FOUND")
    err(client.get("/api/v1/members/me"), 401, "UNAUTHENTICATED")


def test_list_members_filters(client, admin_h, clock):
    setup(client, admin_h)
    mk_branch(client, admin_h, "SECOND")
    reg(client, admin_h)
    reg(client, admin_h, full_name="İlker Işık", email="ilker@example.com", university_id="ILK12345", membership_type="academic", home_branch_id=2)
    client.post("/api/v1/members", headers=admin_h, json=guest_body())
    client.post("/api/v1/members/3/deactivate", headers=admin_h)
    get = lambda qs: client.get("/api/v1/members" + qs, headers=admin_h).json()
    assert [m["id"] for m in get("")["items"]] == [1, 2, 3]
    assert [m["id"] for m in get("?q=ilker")["items"]] == [2]
    assert [m["id"] for m in get("?q=IŞIK")["items"]] == [2]
    assert [m["id"] for m in get("?q=m000003")["items"]] == [3]
    assert [m["id"] for m in get("?q=20231")["items"]] == [1]
    assert [m["id"] for m in get("?q=EXAMPLE.COM")["items"]] == [2, 3]
    assert get("?q=EXAMPLE.COM&page_size=1&page=2")["total"] == 2
    assert [m["id"] for m in get("?membership_type=academic")["items"]] == [2]
    assert [m["id"] for m in get("?status=passive")["items"]] == [3]
    assert [m["id"] for m in get("?home_branch_id=2")["items"]] == [2]
    assert [m["id"] for m in get("?membership_valid=true")["items"]] == [1, 2]
    assert [m["id"] for m in get("?membership_valid=false")["items"]] == [3]
    clock.set(datetime.datetime(2027, 11, 2, 9, tzinfo=TZ))
    admin_h.update(h(token_of(client)))
    assert get("?membership_valid=true")["total"] == 0
    err(client.get("/api/v1/members?status=bad", headers=admin_h), 422, "VALIDATION_ERROR")


def test_update_member(client, admin_h, app):
    setup(client, admin_h)
    reg(client, admin_h)
    r = client.patch("/api/v1/members/1", headers=admin_h, json={"full_name": "New Name", "email": "NEW@example.com", "phone": "0532 123 45 67"})
    assert r.status_code == 200
    m = r.json()
    assert m["full_name"] == "New Name" and m["email"] == "new@example.com" and m["valid_until"] == "2027-11-01"
    assert login(client, "new@example.com", "Passw0rd1").json()["user"]["full_name"] == "New Name"
    err(login(client, "ayse@example.edu.tr", "Passw0rd1"), 401, "INVALID_CREDENTIALS")
    assert audit(app, "user_updated")
    assert client.patch("/api/v1/members/1", headers=admin_h, json={}).status_code == 200
    assert client.patch("/api/v1/members/1", headers=admin_h, json={"email": "new@example.com"}).status_code == 200
    err(client.patch("/api/v1/members/1", headers=admin_h, json={"status": "passive"}), 422, "VALIDATION_ERROR")
    err(client.patch("/api/v1/members/1", headers=admin_h, json={"full_name": None}), 422, "VALIDATION_ERROR")
    err(client.patch("/api/v1/members/9", headers=admin_h, json={"full_name": "x"}), 404, "NOT_FOUND")
    err(client.patch("/api/v1/members/1", headers=admin_h, json={"home_branch_id": 9}), 404, "NOT_FOUND")


def test_update_conflicts(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    reg(client, admin_h, email="b@example.com", university_id="BBBB1111")
    e = err(client.patch("/api/v1/members/2", headers=admin_h, json={"email": "ayse@example.edu.tr"}), 409, "CONFLICT")
    assert e["details"]["field"] == "email"
    e = err(client.patch("/api/v1/members/2", headers=admin_h, json={"university_id": "20231234"}), 409, "CONFLICT")
    assert e["details"]["field"] == "university_id"
    err(client.patch("/api/v1/members/2", headers=admin_h, json={"email": "admin@library.local"}), 409, "CONFLICT")


def test_type_change_rules(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    patch = lambda i, b: client.patch(f"/api/v1/members/{i}", headers=admin_h, json=b)
    # to guest requires phone
    e = err(patch(1, {"membership_type": "guest"}), 409, "MEMBER_FIELDS_INVALID")
    assert e["details"]["fields"][0]["field"] == "phone"
    r = patch(1, {"membership_type": "guest", "phone": "05321234567"})
    assert r.status_code == 200 and r.json()["university_id"] is None and r.json()["valid_until"] == "2027-11-01"
    # university id of the old type is free again
    reg(client, admin_h, email="b@example.com")
    # guest cannot get a university id while staying guest
    err(patch(1, {"university_id": "ABCD1234"}), 409, "MEMBER_FIELDS_INVALID")
    # from guest requires university_id in the same request
    err(patch(1, {"membership_type": "academic"}), 409, "MEMBER_FIELDS_INVALID")
    r = patch(1, {"membership_type": "academic", "university_id": "ACAD0001"})
    assert r.status_code == 200 and r.json()["membership_type"] == "academic"
    # clearing a required field
    err(patch(1, {"university_id": None}), 409, "MEMBER_FIELDS_INVALID")


def test_renew_membership(client, admin_h, clock):
    setup(client, admin_h)
    reg(client, admin_h)
    client.post("/api/v1/members", headers=admin_h, json=guest_body())
    renew = lambda i: client.post(f"/api/v1/members/{i}/renew-membership", headers=admin_h)
    assert renew(1).json()["valid_until"] == "2028-10-31"  # 2027-11-01 + 365
    assert renew(2).json()["valid_until"] == "2027-04-30"  # 2027-01-30 + 90
    clock.set(datetime.datetime(2029, 1, 10, 9, tzinfo=TZ))
    admin_h.update(h(token_of(client)))
    r = renew(1).json()
    assert r["valid_until"] == "2030-01-09" and r["membership_valid"] is True  # today + 364
    r = renew(2).json()
    assert r["valid_until"] == "2029-04-09"  # today + 89
    # valid_until == today is still "not in the past": adds the full period
    clock.set(datetime.datetime(2030, 1, 9, 9, tzinfo=TZ))
    admin_h.update(h(token_of(client)))
    assert renew(1).json()["valid_until"] == "2031-01-09"
    client.post("/api/v1/members/1/deactivate", headers=admin_h)
    err(renew(1), 409, "MEMBER_PASSIVE")
    err(client.post("/api/v1/members/9/renew-membership", headers=admin_h), 404, "NOT_FOUND")


def test_deactivate_activate(client, admin_h):
    setup(client, admin_h)
    reg(client, admin_h)
    r = client.post("/api/v1/members/1/deactivate", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "passive" and r.json()["membership_valid"] is False
    err(client.post("/api/v1/members/1/deactivate", headers=admin_h), 409, "MEMBER_PASSIVE")
    # the user account stays active
    mh = h(token_of(client, "ayse@example.edu.tr", "Passw0rd1"))
    assert client.get("/api/v1/members/me", headers=mh).json()["status"] == "passive"
    r = client.post("/api/v1/members/1/activate", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["valid_until"] == "2027-11-01"
    err(client.post("/api/v1/members/1/activate", headers=admin_h), 409, "MEMBER_ALREADY_ACTIVE")


def test_summary(client, admin_h, clock):
    setup(client, admin_h)
    reg(client, admin_h)
    s = client.get("/api/v1/members/1/summary", headers=admin_h).json()
    assert set(s) == {"member", "open_loans", "overdue_loans", "active_reservations", "balance", "borrowing"}
    assert s["member"]["id"] == 1 and s["open_loans"] == 0 and s["overdue_loans"] == 0 and s["active_reservations"] == 0
    assert s["balance"] == {"outstanding_fees": "0.00", "accrued_late_fees": "0.00", "total_debt": "0.00", "blocked": False}
    assert s["borrowing"] == {"eligible": True, "reasons": []}
    client.post("/api/v1/members/1/deactivate", headers=admin_h)
    clock.set(datetime.datetime(2027, 11, 2, 9, tzinfo=TZ))
    admin_h.update(h(token_of(client)))
    s = client.get("/api/v1/members/1/summary", headers=admin_h).json()
    assert s["borrowing"] == {"eligible": False, "reasons": ["MEMBER_PASSIVE", "MEMBERSHIP_EXPIRED"]}
    err(client.get("/api/v1/members/9/summary", headers=admin_h), 404, "NOT_FOUND")


def test_registration_is_atomic(client, admin_h, app):
    setup(client, admin_h)
    reg(client, admin_h)
    err(client.post("/api/v1/members", headers=admin_h, json=member_body(email="z@example.com")), 409, "CONFLICT")
    with app.state.session_factory() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(User)) == 2
