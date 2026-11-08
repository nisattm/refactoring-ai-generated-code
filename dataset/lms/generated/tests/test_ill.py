"""Module 18: Interlibrary loans (LIB-ILL-01 to LIB-ILL-40)."""

import datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

import lms
from lms.catalog.models import Copy
from lms.core.holidays import DEFAULT_HOLIDAYS
from lms.fines.models import Fee
from lms.ill.rules import member_due_on
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import lib_h, member_body, mk_branch  # noqa: F401
from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


@pytest.fixture
def lib(client, admin_h, clock):
    mk_branch(client, admin_h, "AAA")
    mk_branch(client, admin_h, "BBB")
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    headers = lib_h(client, admin_h)
    original_set = clock.set

    def set_and_relogin(now):
        original_set(now)
        headers.update(h(token_of(client, "lib@example.com", "Passw0rd1")))
        admin_h.update(h(token_of(client)))

    clock.set = set_and_relogin
    return headers


def mk_member(client, hd, n=1, mtype="student"):
    body = member_body(email=f"m{n}@example.edu.tr", university_id=f"2023{n:04d}", membership_type=mtype)
    if mtype == "guest":
        body.update(phone="+905321234567")
        del body["university_id"]
    r = client.post(f"{API}/members", headers=hd, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mh(client, n=1):
    return h(token_of(client, f"m{n}@example.edu.tr", "Passw0rd1"))


def mk_partner(client, admin_h, code="ODTU", **kw):
    body = {"code": code, "name": f"Partner {code}", "email": f"{code.lower()}@lib.example.org",
            "request_fee": "10.00", "daily_late_fee": "2.50", "max_outgoing": 2}
    body.update(kw)
    r = client.post(f"{API}/ill-partners", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def request(client, headers, expect=201, **kw):
    body = {"title": "A Rare Book", "author": "Some Author", **kw}
    r = client.post(f"{API}/ill-requests", headers=headers, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def step(client, headers, rid, action, expect=200, **body):
    r = client.post(f"{API}/ill-requests/{rid}/{action}", headers=headers, json=body or None)
    assert r.status_code == expect, r.text
    return r.json()


def to_received(client, lib, admin_h, rid=1, partner_due="2026-11-20", cost="40.00", partner=None):
    if partner is None:
        partner = mk_partner(client, admin_h)["id"]
    step(client, lib, rid, "send", partner_id=partner)
    return step(client, lib, rid, "receive", partner_due_on=partner_due, replacement_cost=cost, pickup_branch_id=1)


def at(clock, y, m, d, hh=9):
    clock.set(datetime.datetime(y, m, d, hh, 0, tzinfo=TZ))


def fees(app):
    with app.state.session_factory() as s:
        return [(f.kind, f.amount, f.ill_request_id) for f in s.scalars(sa.select(Fee).order_by(Fee.id))]


# --- partners -----------------------------------------------------------------


def test_partner_create_and_read(client, admin_h, lib, app):
    p = mk_partner(client, admin_h, code="odtu")
    assert p == {"id": 1, "code": "ODTU", "name": "Partner odtu", "email": "odtu@lib.example.org",
                 "request_fee": "10.00", "daily_late_fee": "2.50", "max_outgoing": 2, "is_active": True,
                 "open_incoming": 0, "open_outgoing": 0}
    assert len(audit(app, "ill_partner_created")) == 1
    assert client.get(f"{API}/ill-partners/1", headers=lib).json()["code"] == "ODTU"
    err(client.get(f"{API}/ill-partners/9", headers=lib), 404, "NOT_FOUND")
    err(client.post(f"{API}/ill-partners", headers=admin_h, json={"code": "ODTU", "name": "x", "email": "a@b.co",
        "request_fee": "1.00", "daily_late_fee": "1.00", "max_outgoing": 1}), 409, "CONFLICT")


@pytest.mark.parametrize("patch", [
    {"code": "X1"}, {"request_fee": "50.01"}, {"daily_late_fee": "10.01"}, {"max_outgoing": 0}, {"max_outgoing": 21},
    {"email": "bad"}, {"name": ""}, {"request_fee": 5}, {"is_active": None},
])
def test_partner_patch_validation(client, admin_h, lib, patch):
    mk_partner(client, admin_h)
    err(client.patch(f"{API}/ill-partners/1", headers=admin_h, json=patch), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("change", [
    {"code": "A"}, {"code": "TOOLONGCODE1"}, {"code": "A-B"}, {"request_fee": "-1.00"}, {"request_fee": "51.00"},
    {"daily_late_fee": "10.50"}, {"max_outgoing": 21}, {"email": "nope"}, {"request_fee": "1.234"},
])
def test_partner_create_validation(client, admin_h, change):
    body = {"code": "ODTU", "name": "x", "email": "a@b.co", "request_fee": "1.00", "daily_late_fee": "1.00",
            "max_outgoing": 1, **change}
    err(client.post(f"{API}/ill-partners", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_partner_permissions(client, admin_h, lib):
    mk_partner(client, admin_h)
    body = {"code": "BILKENT", "name": "x", "email": "a@b.co", "request_fee": "1.00", "daily_late_fee": "1.00",
            "max_outgoing": 1}
    err(client.post(f"{API}/ill-partners", headers=lib, json=body), 403, "FORBIDDEN")
    err(client.patch(f"{API}/ill-partners/1", headers=lib, json={"name": "y"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/ill-partners", json=body), 401, "UNAUTHENTICATED")
    mk = mk_member(client, lib)
    err(client.get(f"{API}/ill-partners", headers=mh(client)), 403, "FORBIDDEN")
    assert mk == 1


def test_partner_list_filters(client, admin_h, lib, app):
    mk_partner(client, admin_h, "ZETA")
    mk_partner(client, admin_h, "ALFA")
    mk_partner(client, admin_h, "BETA")
    client.patch(f"{API}/ill-partners/3", headers=admin_h, json={"is_active": False, "name": "İstanbul Lib"})
    items = client.get(f"{API}/ill-partners", headers=lib).json()
    assert [p["code"] for p in items["items"]] == ["ALFA", "BETA", "ZETA"] and items["total"] == 3
    assert [p["code"] for p in client.get(f"{API}/ill-partners?is_active=false", headers=lib).json()["items"]] == ["BETA"]
    assert [p["code"] for p in client.get(f"{API}/ill-partners?q=ISTANBUL", headers=lib).json()["items"]] == ["BETA"]
    assert [p["code"] for p in client.get(f"{API}/ill-partners?q=al", headers=lib).json()["items"]] == ["ALFA"]
    assert len(audit(app, "ill_partner_updated")) == 1


# --- dates ---------------------------------------------------------------------


@pytest.mark.parametrize("partner_due,expected", [("2026-11-20", "2026-11-17"), ("2026-11-16", "2026-11-11"),
                                                    ("2026-11-02", "2026-10-27")])
def test_member_due_on(partner_due, expected):
    assert member_due_on(datetime.date.fromisoformat(partner_due), DEFAULT_HOLIDAYS).isoformat() == expected


# --- incoming requests ---------------------------------------------------------


def test_create_request_member_and_staff(client, admin_h, lib, app):
    mk_member(client, lib)
    mk_member(client, lib, 2)
    r = request(client, mh(client), isbn="0-306-40615-2")
    assert r["status"] == "requested" and r["member_id"] == 1 and r["isbn"] == "9780306406157"
    assert r["tried_partner_ids"] == [] and r["renewal"] == "none" and r["overdue"] is False
    assert r["accrued_late_fee"] == "0.00" and "stored_request_fee" not in r
    assert request(client, lib, member_id=2, isbn=None)["member_id"] == 2
    request(client, mh(client), expect=422, member_id=1)
    request(client, lib, expect=422)
    request(client, lib, expect=404, member_id=99)
    request(client, mh(client), expect=422, isbn="123")
    request(client, mh(client), expect=422, title=" ")
    assert len(audit(app, "ill_request_created")) == 2


def test_request_checks(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    g = mk_member(client, lib, 2, "guest")
    err(client.post(f"{API}/ill-requests", headers=lib, json={"title": "x", "author": "y", "member_id": g}), 409,
        "ILL_NOT_ALLOWED_FOR_TYPE")
    # limit of a student: 2
    request(client, mh(client), isbn="9780306406157")
    request(client, mh(client))
    e = err(client.post(f"{API}/ill-requests", headers=mh(client), json={"title": "x", "author": "y"}), 409,
            "ILL_LIMIT_REACHED")
    assert e["details"] == {"limit": 2}


def test_request_duplicate_and_available_locally(client, admin_h, lib):
    mk_member(client, lib)
    client.post(f"{API}/books", headers=lib, json=book_body())
    mk_copy(client, lib)
    e = err(client.post(f"{API}/ill-requests", headers=mh(client), json={"title": "x", "author": "y",
            "isbn": "9780306406157"}), 409, "AVAILABLE_LOCALLY")
    assert e["details"] == {"book_id": 1}
    # a book without an available copy can be requested; then a duplicate is rejected
    with client.app.state.session_factory.begin() as s:
        s.get(Copy, 1).status = "on_loan"
    request(client, mh(client), isbn="9780306406157")
    err(client.post(f"{API}/ill-requests", headers=mh(client), json={"title": "x", "author": "y",
        "isbn": "9780306406157"}), 409, "DUPLICATE_ILL_REQUEST")


def test_request_blocked_by_state(client, admin_h, lib, app, clock):
    mid = mk_member(client, lib)
    body = {"title": "x", "author": "y"}
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=mid, kind="late_fee", amount=Decimal("50.00"), created_on=datetime.date(2026, 11, 2)))
    e = err(client.post(f"{API}/ill-requests", headers=mh(client), json=body), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"] == {"total_debt": "50.00"}
    client.post(f"{API}/members/{mid}/deactivate", headers=lib)
    err(client.post(f"{API}/ill-requests", headers=lib, json={**body, "member_id": mid}), 409, "MEMBER_PASSIVE")
    client.post(f"{API}/members/{mid}/activate", headers=lib)
    at(clock, 2027, 11, 5)
    err(client.post(f"{API}/ill-requests", headers=lib, json={**body, "member_id": mid}), 409, "MEMBERSHIP_EXPIRED")


def test_request_blocked_by_overdue_book_loan(client, admin_h, lib, clock):
    mk_member(client, lib)
    client.post(f"{API}/books", headers=lib, json=book_body())
    mk_copy(client, lib)
    assert client.post(f"{API}/loans", headers=lib, json={"member_id": 1, "copy_id": 1}).status_code == 201
    at(clock, 2026, 11, 20)
    err(client.post(f"{API}/ill-requests", headers=lib, json={"title": "x", "author": "y", "member_id": 1}), 409,
        "MEMBER_HAS_OVERDUE")


def test_read_requests_and_ownership(client, admin_h, lib):
    mk_member(client, lib)
    mk_member(client, lib, 2)
    request(client, mh(client))
    request(client, mh(client, 2))
    assert client.get(f"{API}/ill-requests/1", headers=mh(client)).status_code == 200
    err(client.get(f"{API}/ill-requests/2", headers=mh(client)), 403, "FORBIDDEN")
    err(client.get(f"{API}/ill-requests/9", headers=mh(client)), 404, "NOT_FOUND")
    err(client.get(f"{API}/ill-requests", headers=mh(client)), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/2/ill-requests", headers=mh(client)), 403, "FORBIDDEN")
    assert client.get(f"{API}/members/1/ill-requests", headers=mh(client)).json()["total"] == 1
    assert client.get(f"{API}/ill-requests?member_id=2", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/ill-requests?status=sent", headers=lib).json()["total"] == 0
    err(client.get(f"{API}/ill-requests?status=bogus", headers=lib), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/ill-requests?overdue=false", headers=lib).json()["total"] == 2


def test_send_reject_and_try_limit(client, admin_h, lib, app):
    mk_member(client, lib)
    request(client, mh(client))
    for code in ("AAA1", "BBB1", "CCC1", "DDD1"):
        mk_partner(client, admin_h, code, request_fee=str(len(code)) + ".00")
    r = step(client, lib, 1, "send", partner_id=1)
    assert r["status"] == "sent" and r["partner_id"] == 1 and r["tried_partner_ids"] == [1]
    err(client.post(f"{API}/ill-requests/1/send", headers=lib, json={"partner_id": 2}), 409, "INVALID_ILL_STATUS")
    err(client.post(f"{API}/ill-requests/1/send", headers=lib, json={"partner_id": 99}), 404, "NOT_FOUND")
    r = step(client, lib, 1, "reject", reason="not available")
    assert r["status"] == "rejected" and r["reject_reason"] == "not available"
    err(client.post(f"{API}/ill-requests/1/reject", headers=lib, json={"reason": "x"}), 409, "INVALID_ILL_STATUS")
    err(client.post(f"{API}/ill-requests/1/send", headers=lib, json={"partner_id": 1}), 409, "PARTNER_ALREADY_TRIED")
    client.patch(f"{API}/ill-partners/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/ill-requests/1/send", headers=lib, json={"partner_id": 2}), 409, "PARTNER_INACTIVE")
    client.patch(f"{API}/ill-partners/2", headers=admin_h, json={"is_active": True})
    step(client, lib, 1, "send", partner_id=2)
    step(client, lib, 1, "reject", reason="no")
    step(client, lib, 1, "send", partner_id=3)
    step(client, lib, 1, "reject", reason="no")
    e = err(client.post(f"{API}/ill-requests/1/send", headers=lib, json={"partner_id": 4}), 409, "ILL_TRY_LIMIT_REACHED")
    assert e["details"] == {"limit": 3}
    got = client.get(f"{API}/ill-requests/1", headers=lib).json()
    assert got["tried_partner_ids"] == [1, 2, 3]
    err(client.post(f"{API}/ill-requests/1/reject", headers=mh(client), json={"reason": "x"}), 403, "FORBIDDEN")
    with app.state.session_factory() as s:
        kinds = [n.type for n in s.scalars(sa.select(Notification).order_by(Notification.id))]
    assert kinds == ["ill_request_rejected"] * 3
    assert len(audit(app, "ill_request_sent")) == 3


def test_cancel(client, admin_h, lib, app):
    mk_member(client, lib)
    mk_member(client, lib, 2)
    request(client, mh(client))
    request(client, mh(client))
    err(client.post(f"{API}/ill-requests/1/cancel", headers=mh(client, 2)), 403, "FORBIDDEN")
    r = client.post(f"{API}/ill-requests/1/cancel", headers=mh(client)).json()
    assert r["status"] == "cancelled" and r["cancel_reason"] == "member_request" and r["closed_on"] == "2026-11-02"
    err(client.post(f"{API}/ill-requests/1/cancel", headers=mh(client)), 409, "INVALID_ILL_STATUS")
    r = client.post(f"{API}/ill-requests/2/cancel", headers=lib).json()
    assert r["cancel_reason"] == "staff_request"
    with app.state.session_factory() as s:
        notes = list(s.scalars(sa.select(Notification)))
    assert [(n.type, n.ill_request_id, n.member_id) for n in notes] == [("ill_request_cancelled", 2, 1)]
    assert len(audit(app, "ill_request_cancelled")) == 2


def test_receive_collect_return_late_fee(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    err(client.post(f"{API}/ill-requests/1/receive", headers=lib, json={
        "partner_due_on": "2026-11-20", "replacement_cost": "40.00", "pickup_branch_id": 1}), 409, "INVALID_ILL_STATUS")
    mk_partner(client, admin_h)
    step(client, lib, 1, "send", partner_id=1)
    base = {"partner_due_on": "2026-11-20", "replacement_cost": "40.00", "pickup_branch_id": 1}
    for bad in ({"replacement_cost": "0.00"}, {"replacement_cost": "100000.01"}, {"partner_due_on": "x"}):
        err(client.post(f"{API}/ill-requests/1/receive", headers=lib, json={**base, **bad}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/ill-requests/1/receive", headers=lib, json={**base, "pickup_branch_id": 9}), 404, "NOT_FOUND")
    e = err(client.post(f"{API}/ill-requests/1/receive", headers=lib, json={**base, "partner_due_on": "2026-11-11"}),
            409, "ILL_PERIOD_TOO_SHORT")
    assert e["details"] == {"due_on": "2026-11-06"}
    mk_branch(client, admin_h, "CCC")
    client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/ill-requests/1/receive", headers=lib, json={**base, "pickup_branch_id": 3}), 409, "BRANCH_INACTIVE")
    client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": True})
    r = step(client, lib, 1, "receive", **{**base, "pickup_branch_id": 3})
    assert (r["status"], r["received_on"], r["collect_until"], r["due_on"], r["replacement_cost"], r["pickup_branch_id"]) == (
        "received", "2026-11-02", "2026-11-09", "2026-11-17", "40.00", 3)
    with app.state.session_factory() as s:
        note = s.scalars(sa.select(Notification).where(Notification.type == "ill_request_received")).one()
    assert "A Rare Book" in note.message and "Central Library" in note.message and "2026-11-09" in note.message
    # the pickup branch is in use while the book is received
    err(client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    r = step(client, lib, 1, "collect")
    assert r["status"] == "on_loan" and r["collected_on"] == "2026-11-02"
    assert fees(app) == [("ill_request_fee", Decimal("10.00"), 1)]
    # renewal not allowed twice, return 3 days late: 3 * 2.50
    at(clock, 2026, 11, 20)
    r = client.get(f"{API}/ill-requests/1", headers=lib).json()
    assert r["overdue"] is True and r["accrued_late_fee"] == "7.50"
    s = client.get(f"{API}/members/1/summary", headers=lib).json()
    assert s["ill"] == {"open_requests": 1, "on_loan": 1, "overdue": 1}
    assert "MEMBER_HAS_OVERDUE" in s["borrowing"]["reasons"]
    assert s["balance"]["accrued_late_fees"] == "7.50" and s["balance"]["outstanding_fees"] == "10.00"
    err(client.post(f"{API}/ill-requests/1/renewal-request", headers=mh(client)), 409, "ILL_OVERDUE")
    r = step(client, lib, 1, "return", branch_id=2)
    assert r["status"] == "returned" and r["returned_on"] == "2026-11-20"
    assert fees(app)[1:] == [("ill_late_fee", Decimal("7.50"), 1)]
    r = step(client, lib, 1, "close")
    assert r["status"] == "closed" and r["closed_on"] == "2026-11-20"
    err(client.post(f"{API}/ill-requests/1/close", headers=lib), 409, "INVALID_ILL_STATUS")
    fee = client.get(f"{API}/members/1/fees", headers=lib).json()["items"][0]
    assert fee["ill_request_id"] == 1
    assert client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}).status_code == 200
    assert [e.entity_id for e in audit(app, "ill_request_returned")] == [1]


def test_late_fee_capped_at_replacement_cost(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h, cost="5.00", partner_due="2026-11-20")
    step(client, lib, 1, "collect")
    at(clock, 2026, 12, 20)
    step(client, lib, 1, "return", branch_id=1)
    assert fees(app)[-1] == ("ill_late_fee", Decimal("5.00"), 1)


def test_fee_values_are_stored_at_send_time(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    mk_partner(client, admin_h)
    step(client, lib, 1, "send", partner_id=1)
    client.patch(f"{API}/ill-partners/1", headers=admin_h, json={"request_fee": "20.00", "daily_late_fee": "1.00"})
    step(client, lib, 1, "receive", partner_due_on="2026-11-20", replacement_cost="40.00", pickup_branch_id=1)
    step(client, lib, 1, "collect")
    assert fees(app) == [("ill_request_fee", Decimal("10.00"), 1)]


def test_no_request_fee_when_zero(client, admin_h, lib, app):
    mk_member(client, lib)
    request(client, mh(client))
    p = mk_partner(client, admin_h, request_fee="0.00")
    to_received(client, lib, admin_h, partner=p["id"])
    step(client, lib, 1, "collect")
    assert fees(app) == []


def test_collect_rules(client, admin_h, lib, app, clock):
    mid = mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h)
    # blocked by debt: the book keeps waiting
    with app.state.session_factory.begin() as s:
        s.add(Fee(member_id=mid, kind="late_fee", amount=Decimal("60.00"), created_on=datetime.date(2026, 11, 2)))
    e = err(client.post(f"{API}/ill-requests/1/collect", headers=lib), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"] == {"total_debt": "60.00"}
    assert client.get(f"{API}/ill-requests/1", headers=lib).json()["status"] == "received"
    with app.state.session_factory.begin() as s:
        s.execute(sa.update(Fee).values(status="waived"))
    err(client.post(f"{API}/ill-requests/1/collect", headers=mh(client)), 403, "FORBIDDEN")
    at(clock, 2026, 11, 9)
    step(client, lib, 1, "collect")
    # new request, past the collect period
    request(client, mh(client))
    step(client, lib, 2, "send", partner_id=1)
    step(client, lib, 2, "receive", partner_due_on="2026-12-18", replacement_cost="10.00", pickup_branch_id=2)
    at(clock, 2026, 11, 17)
    err(client.post(f"{API}/ill-requests/2/collect", headers=lib), 409, "ILL_COLLECT_PERIOD_OVER")


def test_renewal_flow(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    err(client.post(f"{API}/ill-requests/1/renewal-request", headers=mh(client)), 409, "INVALID_ILL_STATUS")
    to_received(client, lib, admin_h)
    step(client, lib, 1, "collect")
    err(client.post(f"{API}/ill-requests/1/renewal-answer", headers=lib, json={"approved": False}), 409,
        "ILL_NO_RENEWAL_REQUESTED")
    r = client.post(f"{API}/ill-requests/1/renewal-request", headers=mh(client)).json()
    assert r["renewal"] == "requested"
    err(client.post(f"{API}/ill-requests/1/renewal-request", headers=lib), 409, "ILL_RENEWAL_ALREADY_REQUESTED")
    err(client.post(f"{API}/ill-requests/1/renewal-answer", headers=mh(client), json={"approved": False}), 403, "FORBIDDEN")
    err(client.post(f"{API}/ill-requests/1/renewal-answer", headers=lib, json={"approved": True}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/ill-requests/1/renewal-answer", headers=lib,
        json={"approved": True, "partner_due_on": "2026-11-20"}), 422, "VALIDATION_ERROR")
    r = step(client, lib, 1, "renewal-answer", approved=True, partner_due_on="2026-11-27")
    assert (r["renewal"], r["partner_due_on"], r["due_on"]) == ("approved", "2026-11-27", "2026-11-24")
    err(client.post(f"{API}/ill-requests/1/renewal-request", headers=mh(client)), 409, "ILL_RENEWAL_ALREADY_REQUESTED")
    with app.state.session_factory() as s:
        assert s.scalars(sa.select(Notification).where(Notification.type == "ill_renewal_answered")).one().ill_request_id == 1
    assert len(audit(app, "ill_renewal_requested")) == 1 and len(audit(app, "ill_renewal_answered")) == 1


def test_renewal_refused(client, admin_h, lib):
    mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h)
    step(client, lib, 1, "collect")
    step(client, lib, 1, "renewal-request")
    r = step(client, lib, 1, "renewal-answer", approved=False)
    assert r["renewal"] == "refused" and r["due_on"] == "2026-11-17"


def test_report_lost(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h, cost="40.00")
    step(client, lib, 1, "collect")
    at(clock, 2026, 11, 19)
    r = step(client, lib, 1, "report-lost")
    assert r["status"] == "lost" and r["closed_on"] == "2026-11-19"
    assert fees(app)[1:] == [("ill_late_fee", Decimal("5.00"), 1), ("ill_lost", Decimal("40.00"), 1)]
    err(client.post(f"{API}/ill-requests/1/report-lost", headers=lib), 409, "INVALID_ILL_STATUS")
    assert len(audit(app, "ill_request_lost")) == 1


def test_process_uncollected(client, admin_h, lib, app, clock):
    mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h)
    r = client.post(f"{API}/ill/process", headers=lib).json()
    assert r == {"uncollected": 0, "overdue_outgoing": 0}
    at(clock, 2026, 11, 10)
    assert client.post(f"{API}/ill/process", headers=lib).json() == {"uncollected": 1, "overdue_outgoing": 0}
    assert client.post(f"{API}/ill/process", headers=lib).json()["uncollected"] == 0
    assert client.get(f"{API}/ill-requests/1", headers=lib).json()["status"] == "uncollected"
    assert fees(app) == []
    err(client.post(f"{API}/ill/process", headers=mh(client)), 403, "FORBIDDEN")
    assert step(client, lib, 1, "close")["status"] == "closed"
    with app.state.session_factory() as s:
        assert [n.type for n in s.scalars(sa.select(Notification))][-1] == "ill_request_uncollected"


def test_member_deactivation(client, admin_h, lib, app):
    mk_member(client, lib)
    request(client, mh(client))
    request(client, mh(client))
    to_received(client, lib, admin_h)
    err(client.post(f"{API}/members/1/deactivate", headers=lib), 409, "MEMBER_HAS_OPEN_LOANS")
    step(client, lib, 1, "collect")
    err(client.post(f"{API}/members/1/deactivate", headers=lib), 409, "MEMBER_HAS_OPEN_LOANS")
    step(client, lib, 1, "return", branch_id=1)
    assert client.post(f"{API}/members/1/deactivate", headers=lib).status_code == 200
    r = client.get(f"{API}/ill-requests/2", headers=lib).json()
    assert r["status"] == "cancelled" and r["cancel_reason"] == "member_deactivated"
    assert client.get(f"{API}/ill-requests/1", headers=lib).json()["status"] == "returned"
    with app.state.session_factory() as s:
        types = [n.type for n in s.scalars(sa.select(Notification).where(Notification.ill_request_id == 2))]
    assert types == ["ill_request_cancelled"]


def test_overdue_request_counts_in_debt(client, admin_h, lib, app, clock):
    mid = mk_member(client, lib)
    request(client, mh(client))
    to_received(client, lib, admin_h, cost="100.00")
    step(client, lib, 1, "collect")
    at(clock, 2026, 12, 7)  # 20 days late * 2.50 = 50.00
    s = client.get(f"{API}/members/{mid}/summary", headers=lib).json()
    assert s["balance"]["accrued_late_fees"] == "50.00" and s["balance"]["blocked"] is True
    assert client.get(f"{API}/ill-requests?overdue=true", headers=lib).json()["total"] == 1
    client.post(f"{API}/books", headers=lib, json=book_body())
    mk_copy(client, lib)
    err(client.post(f"{API}/loans", headers=lib, json={"member_id": mid, "copy_id": 1}), 409, "MEMBER_HAS_OVERDUE")


# --- outgoing ------------------------------------------------------------------


def mk_book_with_copy(client, lib, barcode="BC-0001"):
    client.post(f"{API}/books", headers=lib, json=book_body())
    return mk_copy(client, lib, 1, barcode).json()


def outgoing(client, lib, expect=201, partner_id=1, book_id=1):
    r = client.post(f"{API}/ill-outgoing", headers=lib, json={"partner_id": partner_id, "book_id": book_id})
    assert r.status_code == expect, r.text
    return r.json()


def test_outgoing_flow(client, admin_h, lib, app, clock):
    mk_partner(client, admin_h)
    mk_book_with_copy(client, lib)
    o = outgoing(client, lib)
    assert o["status"] == "requested" and o["copy_id"] is None and o["barcode"] is None and o["book_title"]
    err(client.post(f"{API}/ill-outgoing/1/returned", headers=lib, json={"branch_id": 1}), 409, "INVALID_ILL_STATUS")
    err(client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 9}), 404, "NOT_FOUND")
    r = client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1}).json()
    assert (r["status"], r["copy_id"], r["shipped_on"], r["due_on"], r["barcode"]) == (
        "shipped", 1, "2026-11-02", "2026-11-30", "BC-0001")
    assert client.get(f"{API}/copies/1", headers=lib).json()["status"] == "at_partner"
    assert client.get(f"{API}/books/1", headers=lib).json()["availability"][0]["available"] == 0
    assert client.get(f"{API}/ill-partners/1", headers=lib).json()["open_outgoing"] == 1
    err(client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1}), 409, "INVALID_ILL_STATUS")
    err(client.delete(f"{API}/books/1", headers=admin_h), 409, "BOOK_HAS_COPIES")
    at(clock, 2026, 12, 1)
    assert client.post(f"{API}/ill/process", headers=lib).json() == {"uncollected": 0, "overdue_outgoing": 1}
    assert client.get(f"{API}/ill-outgoing?overdue=true", headers=lib).json()["total"] == 1
    r = client.post(f"{API}/ill-outgoing/1/returned", headers=lib, json={"branch_id": 1}).json()
    assert r["status"] == "returned" and r["returned_on"] == "2026-12-01"
    assert client.get(f"{API}/copies/1", headers=lib).json()["status"] == "available"
    assert [e.entity_id for e in audit(app, "ill_outgoing_returned")] == [1]


def test_outgoing_returned_to_other_branch_starts_transfer(client, admin_h, lib):
    mk_partner(client, admin_h)
    mk_book_with_copy(client, lib)
    outgoing(client, lib)
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    client.post(f"{API}/ill-outgoing/1/returned", headers=lib, json={"branch_id": 2})
    c = client.get(f"{API}/copies/1", headers=lib).json()
    assert c["status"] == "in_transfer"


def test_outgoing_checks(client, admin_h, lib):
    mk_partner(client, admin_h, max_outgoing=2)
    mk_book_with_copy(client, lib)
    client.post(f"{API}/books", headers=lib, json=book_body(isbn="9780131103627", title="Other"))
    mk_copy(client, lib, 2, "BC-0002")
    err(client.post(f"{API}/ill-outgoing", headers=lib, json={"partner_id": 1, "book_id": 9}), 404, "NOT_FOUND")
    err(client.post(f"{API}/ill-outgoing", headers=lib, json={"partner_id": 9, "book_id": 1}), 404, "NOT_FOUND")
    outgoing(client, lib)
    outgoing(client, lib)
    e = err(client.post(f"{API}/ill-outgoing", headers=lib, json={"partner_id": 1, "book_id": 1}), 409,
            "PARTNER_LIMIT_REACHED")
    assert e["details"] == {"limit": 2}
    err(client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 2}), 422, "VALIDATION_ERROR")
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    err(client.post(f"{API}/ill-outgoing/2/ship", headers=lib, json={"copy_id": 1}), 409, "INVALID_COPY_STATUS")
    assert client.post(f"{API}/ill-outgoing/2/decline", headers=lib).json()["status"] == "declined"
    err(client.post(f"{API}/ill-outgoing/2/decline", headers=lib), 409, "INVALID_ILL_STATUS")
    client.patch(f"{API}/ill-partners/1", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/ill-outgoing", headers=lib, json={"partner_id": 1, "book_id": 1}), 409, "PARTNER_INACTIVE")
    err(client.get(f"{API}/ill-outgoing"), 401, "UNAUTHENTICATED")


def test_outgoing_partner_has_overdue_and_lost(client, admin_h, lib, app, clock):
    mk_partner(client, admin_h, max_outgoing=5)
    mk_book_with_copy(client, lib)
    mk_copy(client, lib, 1, "BC-0002")
    outgoing(client, lib)
    outgoing(client, lib)
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    at(clock, 2026, 12, 1)
    err(client.post(f"{API}/ill-outgoing/2/ship", headers=lib, json={"copy_id": 2}), 409, "PARTNER_HAS_OVERDUE")
    r = client.post(f"{API}/ill-outgoing/1/report-lost", headers=lib).json()
    assert r["status"] == "lost" and r["amount_due"] == "50.00"
    assert client.get(f"{API}/copies/1", headers=lib).json()["status"] == "lost"
    assert fees(app) == []
    err(client.post(f"{API}/ill-outgoing/1/report-lost", headers=lib), 409, "INVALID_ILL_STATUS")
    assert len(audit(app, "ill_outgoing_lost")) == 1


def test_outgoing_read_filters(client, admin_h, lib):
    mk_partner(client, admin_h, "AAA1")
    mk_partner(client, admin_h, "BBB1")
    mk_book_with_copy(client, lib)
    outgoing(client, lib, partner_id=1)
    outgoing(client, lib, partner_id=2)
    assert client.get(f"{API}/ill-outgoing?partner_id=2", headers=lib).json()["items"][0]["id"] == 2
    assert client.get(f"{API}/ill-outgoing?status=shipped", headers=lib).json()["total"] == 0
    assert client.get(f"{API}/ill-outgoing/1", headers=lib).json()["book_title"]
    err(client.get(f"{API}/ill-outgoing/9", headers=lib), 404, "NOT_FOUND")


def test_delete_book_with_outgoing(client, admin_h, lib):
    mk_partner(client, admin_h)
    client.post(f"{API}/books", headers=lib, json=book_body())
    outgoing(client, lib)
    err(client.delete(f"{API}/books/1", headers=lib), 409, "IN_USE")


def test_at_partner_copy_rules(client, admin_h, lib, app):
    mk_member(client, lib)
    mk_partner(client, admin_h)
    mk_book_with_copy(client, lib)
    outgoing(client, lib)
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    err(client.post(f"{API}/loans", headers=lib, json={"member_id": 1, "copy_id": 1}), 409, "COPY_NOT_AVAILABLE")
    err(client.post(f"{API}/copies/1/withdraw", headers=lib, json={"reason": "gone away"}), 409, "INVALID_COPY_STATUS")
    inv = client.get(f"{API}/reports/inventory", headers=lib).json()["items"]
    assert {"branch_id": 1, "status": "at_partner", "copies": 1} in inv
    r = client.get(f"{API}/search/books?available_only=true", headers=lib).json()
    assert r["total"] == 0


def test_activity_report(client, admin_h, lib, clock):
    mk_member(client, lib)
    mk_partner(client, admin_h, "AAA1")
    mk_partner(client, admin_h, "BBB1")
    request(client, mh(client))
    to_received(client, lib, admin_h, partner=1)
    step(client, lib, 1, "collect")
    at(clock, 2026, 11, 20)
    step(client, lib, 1, "return", branch_id=1)
    request(client, mh(client))
    step(client, lib, 2, "send", partner_id=2)
    step(client, lib, 2, "reject", reason="no")
    mk_book_with_copy(client, lib)
    outgoing(client, lib, partner_id=2)
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    client.post(f"{API}/ill-outgoing/1/report-lost", headers=lib)
    r = client.get(f"{API}/reports/ill-activity?from=2026-11-01&to=2026-11-30", headers=lib).json()
    assert r["total"] == 2
    assert r["items"][0] == {"partner_id": 1, "partner_code": "AAA1", "sent": 1, "rejected": 0, "received": 1,
                             "late_returns": 1, "outgoing_shipped": 0, "outgoing_returned": 0, "outgoing_lost": 0,
                             "amount_due": "0.00"}
    assert r["items"][1] == {"partner_id": 2, "partner_code": "BBB1", "sent": 1, "rejected": 1, "received": 0,
                             "late_returns": 0, "outgoing_shipped": 1, "outgoing_returned": 0, "outgoing_lost": 1,
                             "amount_due": "50.00"}
    empty = client.get(f"{API}/reports/ill-activity?from=2027-01-01&to=2027-01-02", headers=lib).json()
    assert empty["total"] == 2 and empty["items"][0]["sent"] == 0
    for q in ("", "?from=2026-11-01", "?from=2026-11-05&to=2026-11-01", "?from=2025-01-01&to=2026-11-01"):
        err(client.get(f"{API}/reports/ill-activity{q}", headers=lib), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/ill-activity?from=2026-11-01&to=2026-11-02", headers=mh(client)), 403, "FORBIDDEN")


def test_import_rejects_at_partner(client, admin_h, lib, app):
    mk_partner(client, admin_h)
    mk_book_with_copy(client, lib)
    outgoing(client, lib)
    client.post(f"{API}/ill-outgoing/1/ship", headers=lib, json={"copy_id": 1})
    doc = client.get(f"{API}/export", headers=admin_h).json()
    assert doc["copies"][0]["status"] == "at_partner"
    r = client.post(f"{API}/import", headers=admin_h, json=doc)
    assert r.status_code == 422
