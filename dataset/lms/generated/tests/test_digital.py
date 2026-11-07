"""Module 17: Digital resources (LIB-DIG-01 to LIB-DIG-40)."""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import lib_h, mk_branch
from tests.test_loans import mk_book, mk_member, member_h  # noqa: F401
from tests.test_catalog import mk_author, mk_publisher
from tests.test_purchasing import mk_order, mk_supplier

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def dt(day, hhmm="10:00", month=11, sec=0):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, month, day, hour, minute, sec, tzinfo=TZ)


def mk_res(client, hd, kind="ebook", title="Deep Learning", expect=201, **kw):
    body = {"kind": kind, "title": title, "provider": "Acme"}
    body.update(kw)
    r = client.post(f"{API}/digital-resources", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def mk_lic(client, ah, rid=1, expect=201, **kw):
    body = {"model": "perpetual", "copies": 1, "starts_on": "2026-11-01", "cost": "100.00"}
    body.update(kw)
    r = client.post(f"{API}/digital-resources/{rid}/licenses", headers=ah, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def borrow(client, hd, rid=1, member=None, expect=201):
    body = {"resource_id": rid}
    if member is not None:
        body["member_id"] = member
    r = client.post(f"{API}/digital-loans", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def hold(client, hd, rid=1, member=None, expect=201):
    body = {"resource_id": rid}
    if member is not None:
        body["member_id"] = member
    r = client.post(f"{API}/digital-holds", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def session(client, hd, rid=1, member=None, expect=201):
    body = {"resource_id": rid}
    if member is not None:
        body["member_id"] = member
    r = client.post(f"{API}/digital-sessions", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def process(client, hd, expect=200):
    r = client.post(f"{API}/digital/process", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def world(client, admin_h, clock):
    """Monday 2026-11-02 09:30; a librarian, members 1-3 (students) with their headers, one e-book with 1 copy."""
    mk_branch(client, admin_h)
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    lh = lib_h(client, admin_h)
    for n in (1, 2, 3):
        mk_member(client, admin_h, n)
    mk_res(client, admin_h)
    mk_lic(client, admin_h)
    mh = {n: member_h(client, n) for n in (1, 2, 3)}
    logins = {"lh": ("lib@example.com", lh), "admin": ("admin@library.local", admin_h)}
    logins.update({n: (f"m{n}@example.edu.tr", mh[n]) for n in mh})
    original_set = clock.set
    last = [clock.now()]

    def set_and_relogin(now):
        original_set(now)
        if now - last[0] >= datetime.timedelta(days=5):  # tokens last at most 7 days
            last[0] = now
            for email, headers in logins.values():
                password = "ChangeMe123" if email.startswith("admin") else "Passw0rd1"
                headers.update(h(token_of(client, email, password)))

    clock.set = set_and_relogin
    return {"lh": lh, "mh": mh}


def notes(app, type_=None):
    with app.state.session_factory() as s:
        stmt = sa.select(Notification).order_by(Notification.id)
        if type_:
            stmt = stmt.where(Notification.type == type_)
        return list(s.scalars(stmt))


# --- resources -------------------------------------------------------------------------------


def test_create_resource(client, admin_h, world, app):
    book = mk_book(client, admin_h, 0)
    r = mk_res(client, admin_h, title=" Nature Online ", kind="database", provider="Springer")
    assert r["id"] == 2 and r["title"] == "Nature Online" and r["loan_days"] is None and r["book_id"] is None
    assert r["is_active"] is True and r["capacity"] == 0 and r["available"] == 0 and r["waiting_holds"] == 0
    e = mk_res(client, admin_h, book_id=book, loan_days=7, title="Linked")
    assert e["book_id"] == book and e["loan_days"] == 7
    assert world and mk_res(client, admin_h, title="Default days")["loan_days"] == 14
    assert [a.entity_id for a in audit(app, "digital_resource_created")] == [1, 2, 3, 4]
    for bad in ({"book_id": 9}, {"loan_days": 0}, {"loan_days": 22}, {"provider": ""}, {"kind": "journal"}, {"bogus": 1}):
        r = client.post(f"{API}/digital-resources", headers=admin_h, json={"kind": "ebook", "title": "T", "provider": "P", **bad})
        err(r, 422, "VALIDATION_ERROR")
    for bad in ({"book_id": book}, {"loan_days": 5}):
        r = client.post(f"{API}/digital-resources", headers=admin_h, json={"kind": "database", "title": "T", "provider": "P", **bad})
        err(r, 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/digital-resources", headers=admin_h, json={"kind": "ebook", "title": "T", "provider": "P", "book_id": 99})
    assert err(r, 422, "VALIDATION_ERROR")["details"]["fields"][0]["field"] == "book_id"


def test_resource_permissions(client, admin_h, world):
    body = {"kind": "ebook", "title": "T", "provider": "P"}
    err(client.post(f"{API}/digital-resources", json=body), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/digital-resources", headers=world["mh"][1], json=body), 403, "FORBIDDEN")
    assert client.post(f"{API}/digital-resources", headers=world["lh"], json=body).status_code == 201
    err(client.patch(f"{API}/digital-resources/1", headers=world["mh"][1], json={"title": "x"}), 403, "FORBIDDEN")
    assert client.get(f"{API}/digital-resources", headers=world["mh"][1]).status_code == 200
    assert client.get(f"{API}/digital-resources/1", headers=world["mh"][1]).status_code == 200
    err(client.get(f"{API}/digital-resources/9", headers=world["mh"][1]), 404, "NOT_FOUND")


def test_patch_resource(client, admin_h, world, app):
    r = client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"title": "Renamed", "loan_days": 7})
    assert r.status_code == 200 and r.json()["title"] == "Renamed" and r.json()["loan_days"] == 7
    assert len(audit(app, "digital_resource_updated")) == 1
    err(client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"kind": "database"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"loan_days": 30}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"book_id": 9}), 422, "VALIDATION_ERROR")
    mk_res(client, admin_h, kind="database", title="DB")
    err(client.patch(f"{API}/digital-resources/2", headers=admin_h, json={"loan_days": 7}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/digital-resources/9", headers=admin_h, json={"title": "x"}), 404, "NOT_FOUND")


def test_list_resources_and_filters(client, admin_h, world):
    mk_res(client, admin_h, title="alpha", provider="Wiley")
    mk_res(client, admin_h, kind="database", title="Çınar", provider="ACME")
    mk_res(client, admin_h, title="Ibis")
    r = client.get(f"{API}/digital-resources", headers=world["mh"][1]).json()
    assert [i["title"] for i in r["items"]] == ["alpha", "Deep Learning", "Ibis", "Çınar"] and r["total"] == 4
    assert [i["id"] for i in client.get(f"{API}/digital-resources?kind=database", headers=admin_h).json()["items"]] == [3]
    assert [i["id"] for i in client.get(f"{API}/digital-resources?q=wiley", headers=admin_h).json()["items"]] == [2]
    assert [i["id"] for i in client.get(f"{API}/digital-resources?q=IBIS", headers=admin_h).json()["items"]] == [4]
    client.patch(f"{API}/digital-resources/2", headers=admin_h, json={"is_active": False})
    assert [i["id"] for i in client.get(f"{API}/digital-resources?is_active=false", headers=admin_h).json()["items"]] == [2]
    err(client.get(f"{API}/digital-resources?kind=x", headers=admin_h), 422, "VALIDATION_ERROR")


def test_resource_availability_fields(client, admin_h, world):
    borrow(client, world["mh"][1])
    r = client.get(f"{API}/digital-resources/1", headers=admin_h).json()
    assert (r["capacity"], r["in_use"], r["available"], r["waiting_holds"]) == (1, 1, 0, 0)
    hold(client, world["mh"][2])
    r = client.get(f"{API}/digital-resources/1", headers=admin_h).json()
    assert r["waiting_holds"] == 1


def test_book_digital_resources(client, admin_h, world):
    book = mk_book(client, admin_h, 0)
    mk_res(client, admin_h, title="E1", book_id=book)
    mk_res(client, admin_h, title="E2", book_id=book)
    mk_res(client, admin_h, title="E3", book_id=book)
    client.patch(f"{API}/digital-resources/3", headers=admin_h, json={"is_active": False})
    r = client.get(f"{API}/books/{book}/digital-resources", headers=world["mh"][1])
    assert r.status_code == 200 and [i["id"] for i in r.json()] == [2, 4]
    assert "capacity" in r.json()[0]
    err(client.get(f"{API}/books/99/digital-resources", headers=admin_h), 404, "NOT_FOUND")


# --- licenses --------------------------------------------------------------------------------


def test_license_capacity_examples(client, admin_h, world):
    mk_res(client, admin_h, title="Cap")
    a = mk_lic(client, admin_h, 2, copies=2)
    assert a["status"] == "active" and a["ends_on"] is None and a["cost"] == "100.00" and a["order_id"] is None
    b = mk_lic(client, admin_h, 2, model="subscription", copies=3, ends_on="2026-11-30")
    c = mk_lic(client, admin_h, 2, model="subscription", copies=4, starts_on="2026-11-10", ends_on="2026-12-10")
    assert c["status"] == "pending"
    cal = client.get(f"{API}/digital-resources/2/calendar?from=2026-11-09&to=2026-12-01", headers=world["mh"][1]).json()
    caps = {d["date"]: d["capacity"] for d in cal["days"]}
    assert cal["resource_id"] == 2 and len(cal["days"]) == 23
    assert caps["2026-11-09"] == 5 and caps["2026-11-10"] == 9 and caps["2026-11-30"] == 9 and caps["2026-12-01"] == 6
    client.post(f"{API}/digital-licenses/{c['id']}/cancel", headers=admin_h)
    cal = client.get(f"{API}/digital-resources/2/calendar?from=2026-11-09&to=2026-11-10", headers=admin_h).json()
    assert [d["capacity"] for d in cal["days"]] == [5, 5]
    assert b["status"] == "active"


def test_license_validation_and_permissions(client, admin_h, world):
    url = f"{API}/digital-resources/1/licenses"
    base = {"model": "perpetual", "copies": 1, "starts_on": "2026-11-01", "cost": "1.00"}
    err(client.post(url, headers=world["lh"], json=base), 403, "FORBIDDEN")
    err(client.post(url, headers=world["mh"][1], json=base), 403, "FORBIDDEN")
    for bad in ({"copies": 0}, {"copies": 101}, {"cost": "1000000.01"}, {"cost": 5}, {"ends_on": "2026-12-01"},
                {"model": "subscription"}, {"model": "subscription", "ends_on": "2026-10-31"}, {"starts_on": "x"},
                {"order_id": 99}, {"model": "lease"}):
        err(client.post(url, headers=admin_h, json={**base, **bad}), 422, "VALIDATION_ERROR")
    mk_res(client, admin_h, kind="database", title="DB")
    assert mk_lic(client, admin_h, 2, copies=500)["copies"] == 500
    err(client.post(f"{API}/digital-resources/2/licenses", headers=admin_h, json={**base, "copies": 501}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/digital-resources/9/licenses", headers=admin_h, json=base), 404, "NOT_FOUND")
    assert client.get(url, headers=world["lh"]).status_code == 200
    err(client.get(url, headers=world["mh"][1]), 403, "FORBIDDEN")
    client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"is_active": False})
    assert mk_lic(client, admin_h, 1)["status"] == "active"


def test_license_list_and_filter(client, admin_h, world):
    mk_lic(client, admin_h, model="subscription", starts_on="2026-10-01", ends_on="2026-10-31")
    mk_lic(client, admin_h, starts_on="2026-12-01")
    r = client.get(f"{API}/digital-resources/1/licenses", headers=world["lh"]).json()
    assert [(i["id"], i["status"]) for i in r["items"]] == [(2, "ended"), (1, "active"), (3, "pending")]
    r = client.get(f"{API}/digital-resources/1/licenses?status=pending", headers=world["lh"]).json()
    assert [i["id"] for i in r["items"]] == [3]


def test_license_order(client, admin_h, world):
    lh = world["lh"]
    book = mk_book(client, lh, 0)
    mk_supplier(client, lh)
    mk_order(client, lh, lines=[{"book_id": book, "quantity": 1, "unit_price": "10.00"}])
    err(client.post(f"{API}/digital-resources/1/licenses", headers=admin_h,
                    json={"model": "perpetual", "copies": 1, "starts_on": "2026-11-01", "cost": "1.00", "order_id": 1}),
        409, "INVALID_ORDER_STATUS")
    assert client.post(f"{API}/purchase-orders/1/submit", headers=lh).status_code == 200
    lic = mk_lic(client, admin_h, order_id=1)
    assert lic["order_id"] == 1
    e = err(client.post(f"{API}/purchase-orders/1/cancel", headers=lh), 409, "ORDER_HAS_LICENSE")
    assert e["details"] == {"id": 1}
    mk_order(client, lh, lines=[{"book_id": book, "quantity": 1, "unit_price": "10.00"}])
    client.post(f"{API}/purchase-orders/2/cancel", headers=lh)
    err(client.post(f"{API}/digital-resources/1/licenses", headers=admin_h,
                    json={"model": "perpetual", "copies": 1, "starts_on": "2026-11-01", "cost": "1.00", "order_id": 2}),
        409, "INVALID_ORDER_STATUS")


def test_cancel_license(client, admin_h, world, app):
    r = client.post(f"{API}/digital-licenses/1/cancel", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancelled_on"] == "2026-11-02"
    err(client.post(f"{API}/digital-licenses/1/cancel", headers=admin_h), 409, "INVALID_LICENSE_STATUS")
    err(client.post(f"{API}/digital-licenses/1/cancel", headers=world["lh"]), 403, "FORBIDDEN")
    err(client.post(f"{API}/digital-licenses/9/cancel", headers=admin_h), 404, "NOT_FOUND")
    assert len(audit(app, "digital_license_cancelled")) == 1
    mk_lic(client, admin_h, model="subscription", starts_on="2026-10-01", ends_on="2026-10-31")
    err(client.post(f"{API}/digital-licenses/2/cancel", headers=admin_h), 409, "INVALID_LICENSE_STATUS")
    err(client.post(f"{API}/digital-loans", headers=world["mh"][1], json={"resource_id": 1}), 409, "NO_ACTIVE_LICENSE")


def test_patch_license(client, admin_h, world):
    mk_lic(client, admin_h, starts_on="2026-12-01", copies=2)
    r = client.patch(f"{API}/digital-licenses/2", headers=admin_h, json={"copies": 5, "cost": "9.90"})
    assert r.status_code == 200 and r.json()["copies"] == 5 and r.json()["cost"] == "9.90"
    err(client.patch(f"{API}/digital-licenses/1", headers=admin_h, json={"copies": 5}), 409, "INVALID_LICENSE_STATUS")
    err(client.patch(f"{API}/digital-licenses/1", headers=admin_h, json={"cost": "5.00"}), 409, "INVALID_LICENSE_STATUS")
    err(client.patch(f"{API}/digital-licenses/1", headers=admin_h, json={"ends_on": "2027-01-01"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/digital-licenses/2", headers=admin_h, json={"copies": 0}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/digital-licenses/1", headers=world["lh"], json={"copies": 5}), 403, "FORBIDDEN")
    s = mk_lic(client, admin_h, model="subscription", ends_on="2026-12-31")
    r = client.patch(f"{API}/digital-licenses/{s['id']}", headers=admin_h, json={"ends_on": "2027-02-01"})
    assert r.status_code == 200 and r.json()["ends_on"] == "2027-02-01"
    for bad in ("2026-11-01", "2026-10-01"):
        err(client.patch(f"{API}/digital-licenses/{s['id']}", headers=admin_h, json={"ends_on": bad}), 422, "VALIDATION_ERROR")
    assert client.patch(f"{API}/digital-licenses/{s['id']}", headers=admin_h, json={"ends_on": "2026-11-02"}).status_code == 200
    err(client.patch(f"{API}/digital-licenses/{s['id']}", headers=admin_h, json={"copies": 2}), 409, "INVALID_LICENSE_STATUS")


def test_renew_license(client, admin_h, world, app):
    s = mk_lic(client, admin_h, model="subscription", copies=2, starts_on="2026-10-01", ends_on="2026-11-30")
    url = f"{API}/digital-licenses/{s['id']}/renew"
    err(client.post(url, headers=world["lh"], json={"ends_on": "2027-11-30", "cost": "5.00"}), 403, "FORBIDDEN")
    err(client.post(url, headers=admin_h, json={"ends_on": "2026-11-30", "cost": "5.00"}), 422, "VALIDATION_ERROR")
    r = client.post(url, headers=admin_h, json={"ends_on": "2027-11-30", "cost": "5.00"})
    assert r.status_code == 201
    n = r.json()
    assert (n["model"], n["copies"], n["starts_on"], n["ends_on"], n["status"]) == ("subscription", 2, "2026-12-01", "2027-11-30", "pending")
    err(client.post(url, headers=admin_h, json={"ends_on": "2028-11-30", "cost": "5.00"}), 409, "ALREADY_RENEWED")
    err(client.post(f"{API}/digital-licenses/1/renew", headers=admin_h, json={"ends_on": "2028-11-30", "cost": "5.00"}), 409, "NOT_A_SUBSCRIPTION")
    err(client.post(f"{API}/digital-licenses/{n['id']}/renew", headers=admin_h, json={"ends_on": "2028-11-30", "cost": "5.00"}), 409, "INVALID_LICENSE_STATUS")
    assert len(audit(app, "digital_license_added")) == 3


def test_expiring_licenses(client, admin_h, world):
    mk_res(client, admin_h, title="AAA")
    mk_lic(client, admin_h, 2, model="subscription", ends_on="2026-12-01")
    mk_lic(client, admin_h, 1, model="subscription", ends_on="2026-11-10")
    mk_lic(client, admin_h, 1, model="subscription", ends_on="2027-03-01")
    r = client.get(f"{API}/digital-licenses", headers=world["lh"]).json()
    assert [(i["id"], i["resource_title"]) for i in r["items"]] == [(3, "Deep Learning"), (2, "AAA")]
    r = client.get(f"{API}/digital-licenses?ending_within_days=10", headers=world["lh"]).json()
    assert [i["id"] for i in r["items"]] == [3]
    client.post(f"{API}/digital-licenses/3/renew", headers=admin_h, json={"ends_on": "2027-11-10", "cost": "1.00"})
    assert [i["id"] for i in client.get(f"{API}/digital-licenses?ending_within_days=10", headers=admin_h).json()["items"]] == []
    for bad in (0, 366):
        err(client.get(f"{API}/digital-licenses?ending_within_days={bad}", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/digital-licenses", headers=world["mh"][1]), 403, "FORBIDDEN")


def test_calendar_validation(client, admin_h, world):
    url = f"{API}/digital-resources/1/calendar"
    assert len(client.get(f"{url}?from=2026-11-01&to=2027-01-31", headers=admin_h).json()["days"]) == 92
    for q in ("from=2026-11-01&to=2027-02-01", "from=2026-11-05&to=2026-11-01", "from=2026-11-01", "from=x&to=2026-11-01"):
        err(client.get(f"{url}?{q}", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/digital-resources/9/calendar?from=2026-11-01&to=2026-11-02", headers=admin_h), 404, "NOT_FOUND")


# --- loans -----------------------------------------------------------------------------------


def test_borrow_and_due_time(client, admin_h, world, app, clock):
    clock.set(dt(2, "09:00", sec=7))
    ln = borrow(client, world["mh"][1])
    assert ln == {"id": 1, "resource_id": 1, "member_id": 1, "hold_id": None, "borrowed_at": "2026-11-02T09:00:07+03:00",
                  "due_at": "2026-11-16T09:00:07+03:00", "renewed": False, "renewed_at": None, "status": "open", "ended_at": None}
    assert client.get(f"{API}/digital-loans/1", headers=world["mh"][1]).json() == ln
    assert len(audit(app, "digital_loan_created")) == 1 and notes(app) == []
    # a member sends no member_id, staff must
    err(client.post(f"{API}/digital-loans", headers=world["mh"][2], json={"resource_id": 1, "member_id": 2}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/digital-loans", headers=world["lh"], json={"resource_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/digital-loans", headers=world["lh"], json={"resource_id": 9, "member_id": 2}), 404, "NOT_FOUND")
    e = err(client.post(f"{API}/digital-loans", headers=world["lh"], json={"resource_id": 1, "member_id": 9}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "member_id", "id": 9}
    e = err(client.post(f"{API}/digital-loans", headers=world["mh"][2], json={"resource_id": 1}), 409, "NO_COPY_AVAILABLE")
    assert e["details"] == {"waiting": 0}
    err(client.post(f"{API}/digital-loans", headers=world["mh"][1], json={"resource_id": 1}), 409, "ALREADY_BORROWED")
    err(client.post(f"{API}/digital-loans", headers=world["mh"][2], json={}), 422, "VALIDATION_ERROR")


def test_loan_access_and_lists(client, admin_h, world):
    mk_res(client, admin_h, title="Second")
    mk_lic(client, admin_h, 2)
    borrow(client, world["mh"][1])
    borrow(client, world["mh"][1], 2)
    borrow(client, world["lh"], 2, member=2, expect=409)
    err(client.get(f"{API}/digital-loans/1", headers=world["mh"][2]), 403, "FORBIDDEN")
    err(client.get(f"{API}/digital-loans/9", headers=world["mh"][2]), 404, "NOT_FOUND")
    err(client.get(f"{API}/digital-loans", headers=world["mh"][1]), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/1/digital-loans", headers=world["mh"][2]), 403, "FORBIDDEN")
    assert client.get(f"{API}/members/1/digital-loans", headers=world["mh"][1]).json()["total"] == 2
    assert client.get(f"{API}/digital-loans?resource_id=2", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/digital-loans?member_id=2", headers=world["lh"]).json()["total"] == 0
    assert client.get(f"{API}/digital-loans?status=open", headers=world["lh"]).json()["total"] == 2
    assert client.get(f"{API}/digital-loans?status=returned", headers=world["lh"]).json()["total"] == 0
    err(client.get(f"{API}/digital-loans?status=lost", headers=world["lh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/members/9/digital-loans", headers=world["lh"]), 404, "NOT_FOUND")


def test_borrow_check_order(client, admin_h, world, clock, app):
    mh, lh = world["mh"], world["lh"]
    mk_res(client, admin_h, kind="database", title="DB")
    mk_lic(client, admin_h, 2)
    e = err(client.post(f"{API}/digital-loans", headers=mh[1], json={"resource_id": 2}), 409, "WRONG_RESOURCE_KIND")
    client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/digital-loans", headers=mh[1], json={"resource_id": 1}), 409, "RESOURCE_INACTIVE")
    client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"is_active": True})
    # guest
    mk_member(client, admin_h, 4, "guest")
    err(client.post(f"{API}/digital-loans", headers=lh, json={"resource_id": 1, "member_id": 4}), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    # debt
    client.post(f"{API}/members/3/deactivate", headers=lh)
    err(client.post(f"{API}/digital-loans", headers=lh, json={"resource_id": 1, "member_id": 3}), 409, "MEMBER_PASSIVE")
    client.post(f"{API}/members/3/activate", headers=lh)
    clock.set(dt(2, "09:30", month=12) + datetime.timedelta(days=400))
    lh2 = h(token_of(client, "lib@example.com", "Passw0rd1"))
    err(client.post(f"{API}/digital-loans", headers=lh2, json={"resource_id": 1, "member_id": 2}), 409, "MEMBERSHIP_EXPIRED")
    assert e["details"] == {"kind": "database"}


def test_loan_limit_and_no_license(client, admin_h, world):
    for i in range(6):
        mk_res(client, admin_h, title=f"R{i}")
        mk_lic(client, admin_h, 2 + i)
    for i in range(5):
        borrow(client, world["mh"][1], 2 + i)
    e = err(client.post(f"{API}/digital-loans", headers=world["mh"][1], json={"resource_id": 7}), 409, "DIGITAL_LOAN_LIMIT_REACHED")
    assert e["details"] == {"limit": 5}
    mk_res(client, admin_h, title="Empty")
    err(client.post(f"{API}/digital-loans", headers=world["mh"][2], json={"resource_id": 8}), 409, "NO_ACTIVE_LICENSE")


def test_loan_finished_at_due_time(client, admin_h, world, clock, app):
    mh = world["mh"]
    clock.set(dt(2, "09:00"))
    borrow(client, mh[1])
    clock.set(dt(16, "08:59", sec=59))
    assert client.get(f"{API}/digital-loans/1", headers=mh[1]).json()["status"] == "open"
    err(client.post(f"{API}/digital-loans", headers=mh[2], json={"resource_id": 1}), 409, "NO_COPY_AVAILABLE")
    clock.set(dt(16, "09:00"))
    loan = client.get(f"{API}/digital-loans/1", headers=mh[1]).json()
    assert loan["status"] == "expired" and loan["ended_at"] == "2026-11-16T09:00:00+03:00"
    assert client.get(f"{API}/digital-loans?status=expired", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/digital-loans?status=open", headers=world["lh"]).json()["total"] == 0
    err(client.post(f"{API}/digital-loans/1/return", headers=mh[1]), 409, "LOAN_NOT_OPEN")
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "LOAN_NOT_OPEN")
    borrow(client, mh[2])  # the copy is free again
    assert client.get(f"{API}/members/1/summary", headers=mh[1]).json()["digital"]["open_loans"] == 0
    r = process(client, world["lh"])
    assert r == {"expired_loans": 1, "expired_holds": 0, "holds_ready": 0, "due_soon_notices": 0}
    loan = client.get(f"{API}/digital-loans/1", headers=mh[1]).json()
    assert loan["status"] == "expired" and loan["ended_at"] == "2026-11-16T09:00:00+03:00"
    assert [n.member_id for n in notes(app, "digital_loan_expired")] == [1]
    assert notes(app, "digital_loan_expired")[0].digital_loan_id == 1
    assert len(audit(app, "digital_loan_expired")) == 1 and len(audit(app, "digital_processed")) == 1
    assert process(client, world["lh"])["expired_loans"] == 0


def test_return_early(client, admin_h, world, app):
    borrow(client, world["mh"][1])
    err(client.post(f"{API}/digital-loans/1/return", headers=world["mh"][2]), 403, "FORBIDDEN")
    r = client.post(f"{API}/digital-loans/1/return", headers=world["mh"][1])
    assert r.status_code == 200 and r.json()["status"] == "returned" and r.json()["ended_at"] == "2026-11-02T09:30:00+03:00"
    err(client.post(f"{API}/digital-loans/1/return", headers=world["lh"]), 409, "LOAN_NOT_OPEN")
    err(client.post(f"{API}/digital-loans/9/return", headers=world["lh"]), 404, "NOT_FOUND")
    assert len(audit(app, "digital_loan_returned")) == 1 and notes(app) == []
    borrow(client, world["mh"][2])


def test_renew_loan(client, admin_h, world, clock, app):
    mh = world["mh"]
    clock.set(dt(2, "09:00"))
    borrow(client, mh[1])
    e = err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "RENEWAL_TOO_EARLY")
    assert e["details"] == {"renewable_from": "2026-11-13T09:00:00+03:00"}
    clock.set(dt(13, "08:59", sec=59))
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "RENEWAL_TOO_EARLY")
    clock.set(dt(13, "09:00"))
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[2]), 403, "FORBIDDEN")
    r = client.post(f"{API}/digital-loans/1/renew", headers=mh[1])
    assert r.status_code == 200
    assert (r.json()["due_at"], r.json()["renewed"], r.json()["renewed_at"]) == ("2026-11-30T09:00:00+03:00", True, "2026-11-13T09:00:00+03:00")
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "RENEWAL_LIMIT_REACHED")
    assert len(audit(app, "digital_loan_renewed")) == 1


def test_renew_blocked_by_holds_and_license(client, admin_h, world, clock):
    mh = world["mh"]
    clock.set(dt(2, "09:00"))
    borrow(client, mh[1])
    hold(client, mh[2])
    clock.set(dt(14, "09:00"))
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "RESOURCE_HAS_HOLDS")
    client.post(f"{API}/digital-holds/1/cancel", headers=mh[2])
    client.post(f"{API}/digital-licenses/1/cancel", headers=admin_h)
    err(client.post(f"{API}/digital-loans/1/renew", headers=mh[1]), 409, "NO_ACTIVE_LICENSE")


# --- holds -----------------------------------------------------------------------------------


def test_hold_checks(client, admin_h, world):
    mh, lh = world["mh"], world["lh"]
    mk_lic(client, admin_h, copies=1)
    err(client.post(f"{API}/digital-holds", headers=mh[1], json={"resource_id": 1}), 409, "HOLD_NOT_NEEDED")
    borrow(client, mh[1])
    borrow(client, mh[3])
    err(client.post(f"{API}/digital-holds", headers=mh[1], json={"resource_id": 1}), 409, "ALREADY_BORROWED")
    h2 = hold(client, mh[2])
    assert h2["status"] == "waiting" and h2["position"] == 1 and h2["ready_at"] is None and h2["cancel_reason"] is None
    err(client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 1}), 409, "DUPLICATE_HOLD")
    mk_member(client, admin_h, 4)
    assert hold(client, lh, member=4)["position"] == 2
    mk_res(client, admin_h, title="Empty")
    err(client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 2}), 409, "NO_ACTIVE_LICENSE")
    mk_res(client, admin_h, kind="database", title="DB")
    err(client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 3}), 409, "WRONG_RESOURCE_KIND")
    err(client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 9}), 404, "NOT_FOUND")


def test_hold_limit(client, admin_h, world):
    for i in range(6):
        mk_res(client, admin_h, title=f"R{i}")
        mk_lic(client, admin_h, 2 + i)
        borrow(client, world["mh"][2], 2 + i, expect=201 if i < 5 else 409)
    borrow(client, world["mh"][3], 7)
    for i in range(5):
        hold(client, world["mh"][1], 2 + i)
    e = err(client.post(f"{API}/digital-holds", headers=world["mh"][1], json={"resource_id": 7}), 409, "DIGITAL_HOLD_LIMIT_REACHED")
    assert e["details"] == {"limit": 5}


def test_queue_and_ready_flow(client, admin_h, world, clock, app):
    mh, lh = world["mh"], world["lh"]
    clock.set(dt(3, "09:00"))
    borrow(client, mh[1])
    hold(client, mh[2])
    clock.set(dt(3, "09:30"))
    hold(client, mh[3])
    q = client.get(f"{API}/digital-resources/1/holds", headers=lh).json()
    assert [(i["member_id"], i["position"]) for i in q["items"]] == [(2, 1), (3, 2)]
    err(client.get(f"{API}/digital-resources/1/holds", headers=mh[2]), 403, "FORBIDDEN")
    err(client.get(f"{API}/digital-resources/9/holds", headers=lh), 404, "NOT_FOUND")
    # member 3 cannot jump the queue
    e = err(client.post(f"{API}/digital-loans", headers=mh[3], json={"resource_id": 1}), 409, "NO_COPY_AVAILABLE")
    assert e["details"] == {"waiting": 2}
    clock.set(dt(3, "10:00"))
    assert client.post(f"{API}/digital-loans/1/return", headers=mh[1]).status_code == 200
    q = client.get(f"{API}/members/2/digital-holds", headers=mh[2]).json()["items"][0]
    assert q["status"] == "ready" and q["ready_at"] == "2026-11-03T10:00:00+03:00" and q["ready_until"] == "2026-11-05T10:00:00+03:00"
    assert q["position"] is None
    assert [n.digital_hold_id for n in notes(app, "digital_hold_ready")] == [1]
    assert "2026-11-05T10:00:00+03:00" in notes(app, "digital_hold_ready")[0].message
    assert "Deep Learning" in notes(app, "digital_hold_ready")[0].message
    assert [h_["position"] for h_ in client.get(f"{API}/digital-resources/1/holds", headers=lh).json()["items"]] == [1]
    assert client.get(f"{API}/digital-resources/1/holds?status=ready", headers=lh).json()["total"] == 1
    # only member 2 may borrow the kept copy
    err(client.post(f"{API}/digital-loans", headers=mh[3], json={"resource_id": 1}), 409, "NO_COPY_AVAILABLE")
    summary = client.get(f"{API}/members/2/summary", headers=mh[2]).json()
    assert summary["digital"] == {"open_loans": 0, "waiting_holds": 0, "ready_holds": 1}
    assert summary["borrowing"]["eligible"] is True
    clock.set(dt(5, "10:00"))
    ln = borrow(client, mh[2])
    assert ln["hold_id"] == 1
    hd = client.get(f"{API}/members/2/digital-holds", headers=mh[2]).json()["items"][0]
    assert hd["status"] == "fulfilled" and hd["closed_at"] == "2026-11-05T10:00:00+03:00"
    err(client.post(f"{API}/digital-holds/1/cancel", headers=mh[2]), 409, "HOLD_NOT_ACTIVE")


def test_lapsed_ready_hold(client, admin_h, world, clock, app):
    mh, lh = world["mh"], world["lh"]
    clock.set(dt(3, "09:00"))
    borrow(client, mh[1])
    hold(client, mh[2])
    hold(client, mh[3])
    clock.set(dt(3, "10:00"))
    client.post(f"{API}/digital-loans/1/return", headers=mh[1])
    clock.set(dt(5, "10:00", sec=1))
    hd = client.get(f"{API}/members/2/digital-holds", headers=mh[2]).json()["items"][0]
    assert hd["status"] == "ready"  # lapsed but stored as ready until processing
    err(client.post(f"{API}/digital-holds/1/cancel", headers=mh[2]), 409, "HOLD_NOT_ACTIVE")
    assert client.get(f"{API}/members/2/summary", headers=mh[2]).json()["digital"]["ready_holds"] == 0
    r = process(client, lh)
    assert r == {"expired_loans": 0, "expired_holds": 1, "holds_ready": 1, "due_soon_notices": 0}
    holds = {i["id"]: i for i in client.get(f"{API}/members/2/digital-holds", headers=mh[2]).json()["items"]}
    assert holds[1]["status"] == "expired" and holds[1]["closed_at"] == "2026-11-05T10:00:01+03:00"
    assert client.get(f"{API}/members/3/digital-holds", headers=mh[3]).json()["items"][0]["status"] == "ready"
    assert [n.member_id for n in notes(app, "digital_hold_expired")] == [2]
    assert len(audit(app, "digital_hold_expired")) == 1


def test_cancel_hold(client, admin_h, world, clock, app):
    mh, lh = world["mh"], world["lh"]
    borrow(client, mh[1])
    hold(client, mh[2])
    hold(client, mh[3])
    err(client.post(f"{API}/digital-holds/1/cancel", headers=mh[3]), 403, "FORBIDDEN")
    r = client.post(f"{API}/digital-holds/1/cancel", headers=mh[2])
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "member_request"
    assert notes(app, "digital_hold_cancelled") == []
    r = client.post(f"{API}/digital-holds/2/cancel", headers=lh)
    assert r.json()["cancel_reason"] == "staff_request"
    assert [n.member_id for n in notes(app, "digital_hold_cancelled")] == [3]
    assert len(audit(app, "digital_hold_cancelled")) == 2
    err(client.post(f"{API}/digital-holds/9/cancel", headers=lh), 404, "NOT_FOUND")
    # cancelling a ready hold passes the copy on
    client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 1})
    hold(client, mh[3])
    client.post(f"{API}/digital-loans/1/return", headers=mh[1])
    assert client.post(f"{API}/digital-holds/3/cancel", headers=mh[2]).status_code == 200
    assert client.get(f"{API}/members/3/digital-holds?status=ready", headers=mh[3]).json()["total"] == 1


def test_license_increase_moves_queue(client, admin_h, world, app):
    mh = world["mh"]
    borrow(client, mh[1])
    hold(client, mh[2])
    hold(client, mh[3])
    mk_lic(client, admin_h, copies=1)
    assert client.get(f"{API}/digital-resources/1/holds?status=ready", headers=world["lh"]).json()["total"] == 1
    r = client.get(f"{API}/digital-resources/1", headers=admin_h).json()
    assert (r["capacity"], r["in_use"], r["waiting_holds"], r["available"]) == (2, 1, 1, 0)
    mk_lic(client, admin_h, copies=3)
    assert client.get(f"{API}/digital-resources/1/holds?status=ready", headers=world["lh"]).json()["total"] == 2
    assert len(audit(app, "digital_hold_ready")) == 2


# --- sessions --------------------------------------------------------------------------------


@pytest.fixture
def dbworld(client, admin_h, world):
    mk_res(client, admin_h, kind="database", title="Nature")
    mk_lic(client, admin_h, 2, copies=2)
    return world


def test_open_and_close_session(client, admin_h, dbworld, clock, app):
    mh = dbworld["mh"]
    clock.set(dt(2, "10:00"))
    s = session(client, mh[1], 2)
    assert s == {"id": 1, "resource_id": 2, "member_id": 1, "started_at": "2026-11-02T10:00:00+03:00",
                 "expires_at": "2026-11-02T11:00:00+03:00", "closed_at": None, "open": True}
    e = err(client.post(f"{API}/digital-sessions", headers=mh[1], json={"resource_id": 2}), 409, "SESSION_ALREADY_OPEN")
    assert e["details"] == {"session_id": 1}
    e = err(client.post(f"{API}/digital-sessions", headers=mh[1], json={"resource_id": 1}), 409, "WRONG_RESOURCE_KIND")
    assert len(audit(app, "digital_session_opened")) == 1
    err(client.post(f"{API}/digital-sessions/1/close", headers=mh[2]), 403, "FORBIDDEN")
    r = client.post(f"{API}/digital-sessions/1/close", headers=mh[1])
    assert r.status_code == 200 and r.json()["closed_at"] == "2026-11-02T10:00:00+03:00" and r.json()["open"] is False
    err(client.post(f"{API}/digital-sessions/1/close", headers=mh[1]), 409, "SESSION_NOT_OPEN")
    err(client.post(f"{API}/digital-sessions/9/close", headers=mh[1]), 404, "NOT_FOUND")
    assert audit(app, "digital_session_closed") == [] and notes(app) == []
    assert e["details"] == {"kind": "ebook"}


def test_session_seats_and_expiry(client, admin_h, dbworld, clock):
    mh = dbworld["mh"]
    clock.set(dt(2, "10:00"))
    session(client, mh[1], 2)
    clock.set(dt(2, "10:20"))
    session(client, mh[2], 2)
    e = err(client.post(f"{API}/digital-sessions", headers=mh[3], json={"resource_id": 2}), 409, "NO_SEAT_AVAILABLE")
    assert e["details"] == {"next_free_at": "2026-11-02T11:00:00+03:00"}
    r = client.get(f"{API}/digital-resources/2", headers=mh[3]).json()
    assert (r["capacity"], r["in_use"], r["available"]) == (2, 2, 0)
    clock.set(dt(2, "10:59", sec=59))
    assert client.get(f"{API}/members/1/digital-sessions?open=true", headers=mh[1]).json()["total"] == 1
    clock.set(dt(2, "11:00"))
    s = client.get(f"{API}/members/1/digital-sessions", headers=mh[1]).json()["items"][0]
    assert s["open"] is False and s["closed_at"] is None
    assert client.get(f"{API}/members/1/digital-sessions?open=true", headers=mh[1]).json()["total"] == 0
    assert client.get(f"{API}/members/1/digital-sessions?open=false", headers=mh[1]).json()["total"] == 1
    err(client.post(f"{API}/digital-sessions/1/close", headers=mh[1]), 409, "SESSION_NOT_OPEN")
    session(client, mh[3], 2)
    process(client, dbworld["lh"])
    assert client.get(f"{API}/members/1/digital-sessions", headers=mh[1]).json()["items"][0]["closed_at"] is None


def test_session_limit_and_no_license(client, admin_h, dbworld, clock):
    mh = dbworld["mh"]
    mk_res(client, admin_h, kind="database", title="Other")
    mk_lic(client, admin_h, 3)
    mk_res(client, admin_h, kind="database", title="Unlicensed")
    clock.set(dt(2, "10:00"))
    session(client, mh[1], 2)
    e = err(client.post(f"{API}/digital-sessions", headers=mh[1], json={"resource_id": 3}), 409, "SESSION_LIMIT_REACHED")
    assert e["details"] == {"limit": 1}
    err(client.post(f"{API}/digital-sessions", headers=mh[2], json={"resource_id": 4}), 409, "NO_ACTIVE_LICENSE")
    err(client.post(f"{API}/digital-sessions", headers=mh[2], json={"member_id": 2, "resource_id": 3}), 422, "VALIDATION_ERROR")
    assert session(client, dbworld["lh"], 3, member=2)["member_id"] == 2


def test_daily_session_limit(client, admin_h, dbworld, clock):
    mh = dbworld["mh"]
    clock.set(dt(2, "08:00"))
    for i in range(6):
        s = session(client, mh[1], 2)
        assert client.post(f"{API}/digital-sessions/{s['id']}/close", headers=mh[1]).status_code == 200
        clock.advance(minutes=5)
    e = err(client.post(f"{API}/digital-sessions", headers=mh[1], json={"resource_id": 2}), 409, "DAILY_SESSION_LIMIT_REACHED")
    session(client, mh[2], 2)
    clock.set(dt(3, "08:00"))
    session(client, mh[1], 2)
    assert e["details"] != {}


def test_session_lists(client, admin_h, dbworld, clock):
    mh = dbworld["mh"]
    clock.set(dt(2, "08:00"))
    s1 = session(client, mh[1], 2)
    client.post(f"{API}/digital-sessions/{s1['id']}/close", headers=mh[1])
    clock.set(dt(2, "09:00"))
    session(client, mh[1], 2)
    items = client.get(f"{API}/members/1/digital-sessions", headers=dbworld["lh"]).json()["items"]
    assert [i["id"] for i in items] == [2, 1]
    assert client.get(f"{API}/members/1/digital-sessions?resource_id=1", headers=mh[1]).json()["total"] == 0
    err(client.get(f"{API}/members/1/digital-sessions", headers=mh[2]), 403, "FORBIDDEN")


def test_inactive_resource_effects(client, admin_h, world, clock, app):
    mh = world["mh"]
    mk_res(client, admin_h, kind="database", title="DB")
    mk_lic(client, admin_h, 2)
    session(client, mh[1], 2)
    borrow(client, mh[1])
    hold(client, mh[2])
    client.post(f"{API}/digital-loans/1/return", headers=mh[1])  # hold 1 ready
    borrow(client, mh[3], expect=409)
    hold(client, mh[3])
    r = client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200
    reasons = [i["cancel_reason"] for i in client.get(f"{API}/members/2/digital-holds", headers=mh[2]).json()["items"]]
    assert reasons == ["resource_inactive"]
    assert [n.member_id for n in notes(app, "digital_hold_cancelled")] == [2, 3]
    assert len(audit(app, "digital_hold_cancelled")) == 2
    err(client.post(f"{API}/digital-loans", headers=mh[2], json={"resource_id": 1}), 409, "RESOURCE_INACTIVE")
    err(client.post(f"{API}/digital-holds", headers=mh[2], json={"resource_id": 1}), 409, "RESOURCE_INACTIVE")
    client.patch(f"{API}/digital-resources/2", headers=admin_h, json={"is_active": False})
    s = client.get(f"{API}/members/1/digital-sessions", headers=mh[1]).json()["items"][0]
    assert s["closed_at"] == "2026-11-02T09:30:00+03:00" and s["open"] is False
    err(client.post(f"{API}/digital-sessions", headers=mh[2], json={"resource_id": 2}), 409, "RESOURCE_INACTIVE")


def test_inactive_resource_keeps_open_loans(client, admin_h, world):
    borrow(client, world["mh"][1])
    client.patch(f"{API}/digital-resources/1", headers=admin_h, json={"is_active": False})
    assert client.get(f"{API}/digital-loans/1", headers=world["mh"][1]).json()["status"] == "open"
    assert client.post(f"{API}/digital-loans/1/return", headers=world["mh"][1]).status_code == 200


# --- processing ------------------------------------------------------------------------------


def test_due_soon_notices(client, admin_h, world, clock, app):
    mh, lh = world["mh"], world["lh"]
    clock.set(dt(2, "09:00"))
    borrow(client, mh[1])
    clock.set(dt(15, "08:59"))
    assert process(client, lh)["due_soon_notices"] == 0
    clock.set(dt(15, "09:00"))
    assert process(client, lh) == {"expired_loans": 0, "expired_holds": 0, "holds_ready": 0, "due_soon_notices": 1}
    assert process(client, lh)["due_soon_notices"] == 0
    n = notes(app, "digital_loan_due_soon")
    assert len(n) == 1 and n[0].digital_loan_id == 1 and n[0].member_id == 1
    err(client.post(f"{API}/digital/process", headers=mh[1]), 403, "FORBIDDEN")
    err(client.post(f"{API}/digital/process"), 401, "UNAUTHENTICATED")
    r = client.get(f"{API}/members/1/notifications?type=digital_loan_due_soon", headers=mh[1]).json()
    assert r["total"] == 1 and r["items"][0]["digital_loan_id"] == 1 and r["items"][0]["digital_hold_id"] is None


# --- member effects --------------------------------------------------------------------------


def test_member_deactivation(client, admin_h, world, app):
    mh, lh = world["mh"], world["lh"]
    mk_res(client, admin_h, kind="database", title="DB")
    mk_lic(client, admin_h, 2)
    session(client, mh[1], 2)
    borrow(client, mh[1])
    hold(client, mh[2])
    hold(client, mh[3])
    r = client.post(f"{API}/members/1/deactivate", headers=lh)
    assert r.status_code == 200
    ln = client.get(f"{API}/digital-loans/1", headers=lh).json()
    assert ln["status"] == "returned" and ln["ended_at"] == "2026-11-02T09:30:00+03:00"
    s = client.get(f"{API}/members/1/digital-sessions", headers=lh).json()["items"][0]
    assert s["open"] is False and s["closed_at"] == "2026-11-02T09:30:00+03:00"
    assert client.get(f"{API}/members/2/digital-holds?status=ready", headers=lh).json()["total"] == 1
    # deactivating a member with a waiting hold cancels it
    client.post(f"{API}/members/3/deactivate", headers=lh)
    h3 = client.get(f"{API}/members/3/digital-holds", headers=lh).json()["items"][0]
    assert h3["status"] == "cancelled" and h3["cancel_reason"] == "member_deactivated"
    assert [n.member_id for n in notes(app, "digital_hold_cancelled")] == [3]
    # a ready hold is cancelled too
    client.post(f"{API}/members/2/deactivate", headers=lh)
    assert client.get(f"{API}/members/2/digital-holds", headers=lh).json()["items"][0]["cancel_reason"] == "member_deactivated"


def test_member_summary_digital(client, admin_h, world):
    mh = world["mh"]
    r = client.get(f"{API}/members/1/summary", headers=mh[1]).json()
    assert r["digital"] == {"open_loans": 0, "waiting_holds": 0, "ready_holds": 0}
    borrow(client, mh[1])
    hold(client, mh[2])
    assert client.get(f"{API}/members/1/summary", headers=mh[1]).json()["digital"]["open_loans"] == 1
    assert client.get(f"{API}/members/2/summary", headers=mh[2]).json()["digital"]["waiting_holds"] == 1
    assert client.get(f"{API}/members/1/summary", headers=mh[1]).json()["open_loans"] == 0


# --- report ----------------------------------------------------------------------------------


def test_usage_report(client, admin_h, world, clock):
    mh, lh = world["mh"], world["lh"]
    mk_res(client, admin_h, kind="database", title="Aardvark DB")
    mk_lic(client, admin_h, 2, copies=3, cost="50.50", starts_on="2026-11-05")
    mk_res(client, admin_h, title="Idle", loan_days=3)
    clock.set(dt(2, "09:00"))
    borrow(client, mh[1])
    hold(client, mh[2])
    clock.set(dt(3, "09:00"))
    client.post(f"{API}/digital-loans/1/return", headers=mh[1])  # hold 1 ready
    borrow(client, mh[3], expect=409)
    clock.set(dt(6, "09:00"))
    session(client, mh[1], 2)
    process(client, lh)  # hold 1 lapsed
    r = client.get(f"{API}/reports/digital-usage?from=2026-11-01&to=2026-11-30", headers=lh)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["title"] for i in items] == ["Aardvark DB", "Deep Learning", "Idle"]
    assert items[0] == {"resource_id": 2, "kind": "database", "title": "Aardvark DB", "loans": 0, "renewals": 0,
                        "holds_placed": 0, "holds_expired": 0, "sessions": 1, "license_cost": "50.50"}
    assert items[1] == {"resource_id": 1, "kind": "ebook", "title": "Deep Learning", "loans": 1, "renewals": 0,
                        "holds_placed": 1, "holds_expired": 1, "sessions": 0, "license_cost": "100.00"}
    assert items[2]["loans"] == 0 and items[2]["license_cost"] == "0.00"
    only = client.get(f"{API}/reports/digital-usage?from=2026-11-02&to=2026-11-02&kind=ebook", headers=lh).json()["items"]
    assert [(i["resource_id"], i["loans"], i["holds_placed"], i["holds_expired"], i["license_cost"]) for i in only] == [(1, 1, 1, 0, "0.00"), (3, 0, 0, 0, "0.00")]
    for q in ("from=2026-11-02", "from=2026-11-05&to=2026-11-02", "from=2026-01-01&to=2027-01-02", "from=2026-11-01&to=2026-11-02&kind=x"):
        err(client.get(f"{API}/reports/digital-usage?{q}", headers=lh), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/reports/digital-usage?from=2026-01-01&to=2026-12-31", headers=lh).status_code == 200
    err(client.get(f"{API}/reports/digital-usage?from=2026-11-01&to=2026-11-02", headers=mh[1]), 403, "FORBIDDEN")


def test_renewal_counted_in_report(client, admin_h, world, clock):
    clock.set(dt(2, "09:00"))
    borrow(client, world["mh"][1])
    clock.set(dt(14, "09:00"))
    client.post(f"{API}/digital-loans/1/renew", headers=world["mh"][1])
    items = client.get(f"{API}/reports/digital-usage?from=2026-11-14&to=2026-11-14", headers=world["lh"]).json()["items"]
    assert items[0]["renewals"] == 1 and items[0]["loans"] == 0


def test_digital_data_is_not_exported(client, admin_h, world, app):
    data = lms.export_dataset(app.state.settings)
    assert not any("digital" in key for key in data)
