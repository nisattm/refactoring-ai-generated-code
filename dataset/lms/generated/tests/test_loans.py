import datetime

import pytest
import sqlalchemy as sa

from lms.branches.models import Transfer
from lms.catalog.models import Copy
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import lib_h, member_body, mk_branch  # noqa: F401
from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


def at(clock, y, m, d, hh=9):
    clock.set(datetime.datetime(y, m, d, hh, 0, tzinfo=TZ))


@pytest.fixture
def lib(client, admin_h, clock):
    """Branches 1 and 2, one author and publisher, a librarian; returns the librarian's headers.

    Tokens last 12 hours, so the headers are refreshed whenever the test moves the clock."""
    mk_branch(client, admin_h, "AAA")
    mk_branch(client, admin_h, "BBB")
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    headers = lib_h(client, admin_h)
    original_set = clock.set

    def set_and_relogin(now):
        original_set(now)
        headers.update(h(token_of(client, "lib@example.com", "Passw0rd1")))

    clock.set = set_and_relogin
    return headers


def mk_book(client, hd, n):
    isbn = ["9780306406157", "9780131103627", "9780201633610", "9780596007126", "9781491950296", "9781449355739"][n]
    r = client.post(f"{API}/books", headers=hd, json=book_body(isbn=isbn, title=f"Book {n}"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mk_member(client, hd, n=1, mtype="student", **kw):
    body = member_body(email=f"m{n}@example.edu.tr", university_id=f"2023{n:04d}", membership_type=mtype, **kw)
    if mtype == "guest":
        body.update(phone="+905321234567")
        del body["university_id"]
    r = client.post(f"{API}/members", headers=hd, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def member_h(client, n=1):
    return h(token_of(client, f"m{n}@example.edu.tr", "Passw0rd1"))


def new_copy(client, hd, book_id, barcode, branch=1, price="50.00"):
    r = mk_copy(client, hd, book_id, barcode, branch, price=price)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lend(client, hd, member_id, copy_id):
    return client.post(f"{API}/loans", headers=hd, json={"member_id": member_id, "copy_id": copy_id})


def copy_of(client, hd, copy_id):
    return client.get(f"{API}/copies/{copy_id}", headers=hd).json()


def ret(client, hd, loan_id, branch=1, condition="good", **kw):
    return client.post(f"{API}/loans/{loan_id}/return", headers=hd, json={"branch_id": branch, "condition": condition, **kw})


# --- lending ------------------------------------------------------------------


def test_lend_basic(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib)
    r = lend(client, lib, m, c)
    assert r.status_code == 201, r.text
    loan = r.json()
    assert loan["id"] == 1 and loan["copy_id"] == c and loan["member_id"] == m and loan["branch_id"] == 1
    assert loan["loan_date"] == "2026-11-02" and loan["due_date"] == "2026-11-16"
    assert (loan["loan_period_days"], loan["max_renewals"], loan["daily_fee"]) == (14, 1, "2.00")
    assert loan["renewal_count"] == 0 and loan["status"] == "open"
    assert loan["returned_on"] is None and loan["return_branch_id"] is None
    assert loan["condition_on_return"] is None and loan["late_days"] is None
    assert loan["created_by"] == 2 and loan["is_overdue"] is False and loan["accrued_late_fee"] == "0.00"
    assert copy_of(client, lib, c)["status"] == "on_loan"
    assert copy_of(client, lib, c)["current_branch_id"] == 1
    assert [a.entity_id for a in audit(app, "loan_created")] == [1]


def test_lend_by_barcode_and_validation(client, lib):
    book = mk_book(client, lib, 0)
    new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib)
    r = client.post(f"{API}/loans", headers=lib, json={"member_id": m, "barcode": " bc-0001 "})
    assert r.status_code == 201 and r.json()["copy_id"] == 1
    for body in ({"member_id": m}, {"member_id": m, "copy_id": 1, "barcode": "BC-0001"}, {"copy_id": 1}, {"member_id": m, "copy_id": 1, "x": 1}):
        assert err(client.post(f"{API}/loans", headers=lib, json=body), 422, "VALIDATION_ERROR")
    e = err(client.post(f"{API}/loans", headers=lib, json={"member_id": m, "barcode": "NOPE-123"}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "barcode", "value": "NOPE-123"}
    e = err(client.post(f"{API}/loans", headers=lib, json={"member_id": 99, "copy_id": 1}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "member_id", "id": 99}
    e = err(client.post(f"{API}/loans", headers=lib, json={"member_id": m, "copy_id": 99}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "copy_id", "id": 99}


def test_lend_permissions(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib)
    body = {"member_id": m, "copy_id": c}
    err(client.post(f"{API}/loans", json=body), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/loans", headers=member_h(client), json=body), 403, "FORBIDDEN")
    err(client.post(f"{API}/loans", headers=member_h(client), json={}), 403, "FORBIDDEN")
    assert client.post(f"{API}/loans", headers=admin_h, json=body).status_code == 201


def test_due_date_rules(client, lib, clock):
    book = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, book, "BC-0001")
    c2 = new_copy(client, lib, book, "BC-0002")
    ac = mk_member(client, lib, 1, "academic")
    at(clock, 2026, 12, 2)
    assert lend(client, lib, ac, c1).json()["due_date"] == "2027-01-04"  # 2027-01-01 is a holiday
    gu = mk_member(client, lib, 2, "guest")
    at(clock, 2026, 11, 2)
    r = lend(client, lib, gu, c2).json()
    assert (r["due_date"], r["loan_period_days"], r["max_renewals"], r["daily_fee"]) == ("2026-11-09", 7, 0, "5.00")


def test_lending_checks_in_order(client, lib, clock, app):
    book = mk_book(client, lib, 0)
    copies = [new_copy(client, lib, book, f"BC-000{i}") for i in range(1, 8)]
    g = mk_member(client, lib, 1, "guest")  # limit 2
    # passive beats everything
    client.post(f"{API}/members/{g}/deactivate", headers=lib)
    err(lend(client, lib, g, copies[0]), 409, "MEMBER_PASSIVE")
    client.post(f"{API}/members/{g}/activate", headers=lib)
    # limit
    assert lend(client, lib, g, copies[0]).status_code == 201
    assert lend(client, lib, g, copies[1]).status_code == 201
    err(lend(client, lib, g, copies[2]), 409, "LOAN_LIMIT_REACHED")
    # expired membership beats overdue
    at(clock, 2027, 2, 15)  # guest valid_until 2027-01-30; loans due 2026-11-09
    err(lend(client, lib, g, copies[2]), 409, "MEMBERSHIP_EXPIRED")
    client.post(f"{API}/members/{g}/renew-membership", headers=lib)
    err(lend(client, lib, g, copies[2]), 409, "MEMBER_HAS_OVERDUE")


def test_copy_status_checks(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    assert lend(client, lib, m1, c).status_code == 201
    e = err(lend(client, lib, m2, c), 409, "COPY_NOT_AVAILABLE")
    assert e["details"]["status"] == "on_loan"
    with app.state.session_factory.begin() as s:
        s.get(Copy, c).status = "on_hold"
    err(lend(client, lib, m2, c), 409, "COPY_ON_HOLD")


def test_debt_boundary(client, lib, clock):
    book = mk_book(client, lib, 0)
    c1, c2 = new_copy(client, lib, book, "BC-0001"), new_copy(client, lib, book, "BC-0002")
    s = mk_member(client, lib)
    loan = lend(client, lib, s, c1).json()
    at(clock, 2026, 12, 21)
    err(lend(client, lib, s, c2), 409, "MEMBER_HAS_OVERDUE")
    r = ret(client, lib, loan["id"])
    assert r.json()["late_days"] == 25 and r.json()["accrued_late_fee"] == "50.00"
    bal = client.get(f"{API}/members/{s}/balance", headers=lib).json()
    assert bal == {"outstanding_fees": "50.00", "accrued_late_fees": "0.00", "total_debt": "50.00", "blocked": True}
    e = err(lend(client, lib, s, c2), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"
    r = client.post(f"{API}/members/{s}/payments", headers=lib, json={"amount": "0.01", "method": "cash"})
    assert r.status_code == 201
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["total_debt"] == "49.99"
    assert lend(client, lib, s, c2).status_code == 201


# --- renewal ------------------------------------------------------------------


def test_renew_dates(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    loan = lend(client, lib, s, c).json()
    at(clock, 2026, 11, 10)
    r = client.post(f"{API}/loans/{loan['id']}/renew", headers=lib)
    assert r.status_code == 200, r.text
    assert r.json()["due_date"] == "2026-11-24" and r.json()["renewal_count"] == 1
    err(client.post(f"{API}/loans/{loan['id']}/renew", headers=lib), 409, "RENEWAL_LIMIT_REACHED")


def test_renew_holiday_keeps_due_date(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    at(clock, 2026, 5, 18)  # 2026-05-18 + 14 = 2026-06-01
    s = mk_member(client, lib)  # registered at the clock, so its membership is valid then
    loan = lend(client, lib, s, c).json()
    assert loan["due_date"] == "2026-06-01"
    at(clock, 2026, 5, 15)
    r = client.post(f"{API}/loans/{loan['id']}/renew", headers=lib)
    assert r.json()["due_date"] == "2026-06-01" and r.json()["renewal_count"] == 1


def test_renew_checks(client, lib, clock, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    loan = lend(client, lib, s, c).json()
    lid = loan["id"]
    # renewal on the due date itself is allowed, after it is not
    at(clock, 2026, 11, 16)
    at_due = client.post(f"{API}/loans/{lid}/renew", headers=lib)
    assert at_due.status_code == 200 and at_due.json()["due_date"] == "2026-11-30"
    at(clock, 2026, 12, 1)
    err(client.post(f"{API}/loans/{lid}/renew", headers=lib), 409, "LOAN_OVERDUE")
    ret(client, lib, lid)
    err(client.post(f"{API}/loans/{lid}/renew", headers=lib), 409, "LOAN_NOT_OPEN")
    err(client.post(f"{API}/loans/99/renew", headers=lib), 404, "NOT_FOUND")


def test_renew_expired_membership_and_order(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    g = mk_member(client, lib, 1, "guest")
    lid = lend(client, lib, g, c).json()["id"]
    err(client.post(f"{API}/loans/{lid}/renew", headers=lib), 409, "RENEWAL_LIMIT_REACHED")
    at(clock, 2027, 2, 1)
    # overdue and expired: membership is checked first
    err(client.post(f"{API}/loans/{lid}/renew", headers=lib), 409, "MEMBERSHIP_EXPIRED")


def test_renew_by_member_ownership(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lid = lend(client, lib, s1, c).json()["id"]
    err(client.post(f"{API}/loans/{lid}/renew", headers=member_h(client, 2)), 403, "FORBIDDEN")
    err(client.post(f"{API}/loans/{lid}/renew"), 401, "UNAUTHENTICATED")
    r = client.post(f"{API}/loans/{lid}/renew", headers=member_h(client, 1))
    assert r.status_code == 200 and r.json()["renewal_count"] == 1


def test_renewal_limits_by_type(client, lib, clock):
    """LIB-E2E-05"""
    book = mk_book(client, lib, 0)
    c1, c2 = new_copy(client, lib, book, "BC-0001"), new_copy(client, lib, book, "BC-0002")
    g, a = mk_member(client, lib, 1, "guest"), mk_member(client, lib, 2, "academic")
    gl = lend(client, lib, g, c1).json()
    assert gl["due_date"] == "2026-11-09"
    err(client.post(f"{API}/loans/{gl['id']}/renew", headers=lib), 409, "RENEWAL_LIMIT_REACHED")
    al = lend(client, lib, a, c2).json()
    assert al["due_date"] == "2026-12-02"
    at(clock, 2026, 11, 20)
    assert client.post(f"{API}/loans/{al['id']}/renew", headers=lib).json()["due_date"] == "2026-12-21"
    at(clock, 2026, 12, 1)
    assert client.post(f"{API}/loans/{al['id']}/renew", headers=lib).json()["due_date"] == "2026-12-31"
    at(clock, 2026, 12, 10)
    err(client.post(f"{API}/loans/{al['id']}/renew", headers=lib), 409, "RENEWAL_LIMIT_REACHED")


def test_type_change_keeps_loan_terms(client, lib, clock):
    """LIB-E2E-06"""
    book = mk_book(client, lib, 0)
    c1, c2 = new_copy(client, lib, book, "BC-0001"), new_copy(client, lib, book, "BC-0002")
    s = mk_member(client, lib)
    l1 = lend(client, lib, s, c1).json()
    assert client.patch(f"{API}/members/{s}", headers=lib, json={"membership_type": "academic"}).status_code == 200
    got = client.get(f"{API}/loans/{l1['id']}", headers=lib).json()
    assert (got["due_date"], got["daily_fee"], got["max_renewals"]) == ("2026-11-16", "2.00", 1)
    at(clock, 2026, 11, 3)
    l2 = lend(client, lib, s, c2).json()
    assert (l2["loan_period_days"], l2["daily_fee"], l2["max_renewals"]) == (30, "1.00", 2)


# --- return -------------------------------------------------------------------


def test_return_late_fee(client, lib, clock, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    at(clock, 2026, 11, 20)
    r = ret(client, lib, lid)
    assert r.status_code == 200, r.text
    loan = r.json()
    assert loan["status"] == "returned" and loan["returned_on"] == "2026-11-20" and loan["return_branch_id"] == 1
    assert loan["condition_on_return"] == "good" and loan["late_days"] == 4
    assert loan["is_overdue"] is False and loan["accrued_late_fee"] == "8.00"
    assert copy_of(client, lib, c)["status"] == "available"
    fees = client.get(f"{API}/members/{s}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"], f["status"], f["loan_id"]) for f in fees] == [("late_fee", "8.00", "open", lid)]
    assert [a.entity_id for a in audit(app, "loan_returned")] == [lid]
    assert len(audit(app, "fee_created")) == 1


def test_return_on_time_creates_no_fee(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    at(clock, 2026, 11, 16)
    r = ret(client, lib, lid).json()
    assert r["late_days"] == 0 and r["accrued_late_fee"] == "0.00"
    assert client.get(f"{API}/fees", headers=lib).json()["total"] == 0


def test_late_fee_cap(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    g = mk_member(client, lib, 1, "guest")
    lid = lend(client, lib, g, c).json()["id"]  # due 2026-11-09
    at(clock, 2026, 12, 15)  # still inside the 90-day membership
    # 25 working days late: 125.00 -> capped at 100.00 (also while the loan is open)
    got = client.get(f"{API}/loans/{lid}", headers=lib).json()
    assert got["is_overdue"] is True and got["accrued_late_fee"] == "100.00"
    r = ret(client, lib, lid).json()
    assert r["late_days"] == 26 and r["accrued_late_fee"] == "100.00"
    assert client.get(f"{API}/fees", headers=lib).json()["items"][0]["amount"] == "100.00"


def test_return_checks(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="100.00")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    url = f"{API}/loans/{lid}/return"
    err(client.post(url, headers=member_h(client), json={"branch_id": 1, "condition": "good"}), 403, "FORBIDDEN")
    err(client.post(url, headers=lib, json={"branch_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=lib, json={"branch_id": 1, "condition": "bad"}), 422, "VALIDATION_ERROR")
    e = err(client.post(url, headers=lib, json={"branch_id": 1, "condition": "good", "damage_fee": "5.00"}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "damage_fee"
    for fee in (None, "0.00", "-1.00", 5, "1.234"):
        body = {"branch_id": 1, "condition": "damaged"}
        if fee is not None:
            body["damage_fee"] = fee
        err(client.post(url, headers=lib, json=body), 422, "VALIDATION_ERROR")
    e = err(client.post(url, headers=lib, json={"branch_id": 99, "condition": "good"}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "branch_id", "id": 99}
    err(client.post(f"{API}/loans/99/return", headers=lib, json={"branch_id": 1, "condition": "good"}), 404, "NOT_FOUND")
    err(client.post(url, headers=lib, json={"branch_id": 1, "condition": "damaged", "damage_fee": "100.01"}), 409, "DAMAGE_FEE_EXCEEDS_PRICE")
    # nothing changed by the failed attempts
    assert client.get(f"{API}/loans/{lid}", headers=lib).json()["status"] == "open"
    assert copy_of(client, lib, c)["status"] == "on_loan"
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(ret(client, lib, lid, branch=2), 409, "BRANCH_INACTIVE")
    assert ret(client, lib, lid).status_code == 200
    err(ret(client, lib, lid), 409, "LOAN_NOT_OPEN")
    # LOAN_NOT_OPEN is checked before BRANCH_INACTIVE (LIB-LOAN-09)
    err(ret(client, lib, lid, branch=2), 409, "LOAN_NOT_OPEN")


def test_damaged_return(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="120.00")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    r = ret(client, lib, lid, branch=2, condition="damaged", damage_fee="120.00")
    assert r.status_code == 200, r.text
    assert r.json()["condition_on_return"] == "damaged" and r.json()["return_branch_id"] == 2
    cp = copy_of(client, lib, c)
    assert cp["status"] == "damaged" and cp["current_branch_id"] == 2
    fees = client.get(f"{API}/members/{s}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"]) for f in fees] == [("damage_fee", "120.00")]
    assert [a.entity_id for a in audit(app, "fee_created")] == [1]


def test_damaged_return_with_late_fee_creates_both(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="120.00")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    at(clock, 2026, 11, 17)
    ret(client, lib, lid, condition="damaged", damage_fee="40.00")
    kinds = [(f["kind"], f["amount"]) for f in client.get(f"{API}/fees", headers=lib).json()["items"]]
    assert kinds == [("late_fee", "2.00"), ("damage_fee", "40.00")]


def test_return_at_other_branch_starts_return_transfer(client, lib, app, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    at(clock, 2026, 11, 6)  # Friday
    assert ret(client, lib, lid, branch=2).status_code == 200
    cp = copy_of(client, lib, c)
    assert cp["status"] == "in_transfer" and cp["current_branch_id"] is None and cp["home_branch_id"] == 1
    with app.state.session_factory() as db:
        t = db.scalar(sa.select(Transfer))
        assert (t.copy_id, t.from_branch_id, t.to_branch_id, t.reason, t.status) == (c, 2, 1, "return_home", "in_transit")
        assert (t.started_on, t.expected_on) == (datetime.date(2026, 11, 6), datetime.date(2026, 11, 10))
    assert len(audit(app, "transfer_started")) == 1


def test_repair_away_from_home_starts_transfer(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    ret(client, lib, lid, branch=2, condition="damaged", damage_fee="10.00")
    assert client.post(f"{API}/copies/{c}/repair", headers=lib).status_code == 200
    assert copy_of(client, lib, c)["status"] == "in_transfer"
    with app.state.session_factory() as db:
        assert db.scalar(sa.select(Transfer.reason)) == "return_home"


# --- lost ---------------------------------------------------------------------


def test_report_lost(client, lib, clock, app):
    """LIB-E2E-04 (loan part)"""
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="180.00")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    err(client.post(f"{API}/loans/{lid}/report-lost", headers=member_h(client)), 403, "FORBIDDEN")
    at(clock, 2026, 11, 18)
    r = client.post(f"{API}/loans/{lid}/report-lost", headers=lib)
    assert r.status_code == 200, r.text
    loan = r.json()
    assert loan["status"] == "lost" and loan["late_days"] == 2 and loan["returned_on"] is None
    assert loan["is_overdue"] is False and loan["accrued_late_fee"] == "4.00"
    cp = copy_of(client, lib, c)
    assert cp["status"] == "lost" and cp["current_branch_id"] is None
    fees = client.get(f"{API}/members/{s}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "4.00"), ("lost_book", "180.00"), ("lost_processing", "25.00")]
    assert client.get(f"{API}/members/{s}/balance", headers=lib).json()["total_debt"] == "209.00"
    err(client.post(f"{API}/loans/{lid}/report-lost", headers=lib), 409, "LOAN_NOT_OPEN")
    err(client.post(f"{API}/loans/99/report-lost", headers=lib), 404, "NOT_FOUND")
    assert [a.entity_id for a in audit(app, "loan_lost")] == [lid]
    assert len(audit(app, "fee_created")) == 3


def test_report_lost_not_late(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="30.00")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    loan = client.post(f"{API}/loans/{lid}/report-lost", headers=lib).json()
    assert loan["late_days"] == 0
    kinds = [f["kind"] for f in client.get(f"{API}/fees", headers=lib).json()["items"]]
    assert kinds == ["lost_book", "lost_processing"]


# --- reading ------------------------------------------------------------------


def test_get_loan_ownership(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lid = lend(client, lib, s1, c).json()["id"]
    assert client.get(f"{API}/loans/{lid}", headers=member_h(client, 1)).status_code == 200
    err(client.get(f"{API}/loans/{lid}", headers=member_h(client, 2)), 403, "FORBIDDEN")
    err(client.get(f"{API}/loans/99", headers=member_h(client, 2)), 404, "NOT_FOUND")
    err(client.get(f"{API}/loans/{lid}"), 401, "UNAUTHENTICATED")
    assert client.get(f"{API}/members/{s1}/loans", headers=member_h(client, 1)).json()["total"] == 1
    err(client.get(f"{API}/members/{s1}/loans", headers=member_h(client, 2)), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/99/loans", headers=lib), 404, "NOT_FOUND")
    err(client.get(f"{API}/loans", headers=member_h(client, 1)), 403, "FORBIDDEN")


def test_list_loans_filters(client, lib, clock):
    b0, b1 = mk_book(client, lib, 0), mk_book(client, lib, 1)
    c1, c2, c3 = new_copy(client, lib, b0, "BC-0001"), new_copy(client, lib, b1, "BC-0002", branch=2), new_copy(client, lib, b1, "BC-0003")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    l1 = lend(client, lib, s1, c1).json()["id"]
    l2 = lend(client, lib, s2, c2).json()["id"]
    at(clock, 2026, 11, 5)
    l3 = lend(client, lib, s2, c3).json()["id"]
    ret(client, lib, l1)

    def ids(q, url="/loans"):
        r = client.get(f"{API}{url}", headers=lib, params=q)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids({}) == [l3, l2, l1]  # newest first
    assert ids({"member_id": s2}) == [l3, l2]
    assert ids({"copy_id": c2}) == [l2]
    assert ids({"book_id": b1}) == [l3, l2]
    assert ids({"branch_id": 2}) == [l2]
    assert ids({"status": "returned"}) == [l1]
    assert ids({"status": "open"}) == [l3, l2]
    assert ids({"due_before": "2026-11-16"}) == [l2, l1]
    assert ids({"due_before": "2026-11-15"}) == []
    at(clock, 2026, 11, 17)
    assert ids({"overdue": "true"}) == [l2]  # l3 is due 2026-11-19
    assert ids({"overdue": "false"}) == [l3, l1]
    assert ids({"book_id": b1}, f"/members/{s2}/loans") == [l3, l2]
    assert ids({}, f"/members/{s1}/loans") == [l1]
    err(client.get(f"{API}/loans", headers=lib, params={"due_before": "2026-13-01"}), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/loans", headers=lib, params={"status": "weird"}), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/loans", headers=lib, params={"page_size": 0}), 422, "VALIDATION_ERROR")
    page = client.get(f"{API}/loans", headers=lib, params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 3 and [i["id"] for i in page["items"]] == [l1]


def test_member_summary_and_deactivate_use_loans(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    lid = lend(client, lib, s, c).json()["id"]
    err(client.post(f"{API}/members/{s}/deactivate", headers=lib), 409, "MEMBER_HAS_OPEN_LOANS")
    at(clock, 2026, 11, 20)
    summ = client.get(f"{API}/members/{s}/summary", headers=lib).json()
    assert (summ["open_loans"], summ["overdue_loans"]) == (1, 1)
    assert summ["balance"]["accrued_late_fees"] == "8.00" and summ["balance"]["total_debt"] == "8.00"
    assert summ["borrowing"] == {"eligible": False, "reasons": ["MEMBER_HAS_OVERDUE"]}
    ret(client, lib, lid)
    summ = client.get(f"{API}/members/{s}/summary", headers=lib).json()
    assert (summ["open_loans"], summ["overdue_loans"]) == (0, 0)
    assert summ["balance"]["outstanding_fees"] == "8.00"
    assert client.post(f"{API}/members/{s}/deactivate", headers=lib).status_code == 200


def test_summary_reasons_in_order(client, lib, clock):
    g = mk_member(client, lib, 1, "guest")
    book = mk_book(client, lib, 0)
    c1, c2 = new_copy(client, lib, book, "BC-0001"), new_copy(client, lib, book, "BC-0002")
    lend(client, lib, g, c1)
    lend(client, lib, g, c2)
    at(clock, 2027, 2, 1)
    summ = client.get(f"{API}/members/{g}/summary", headers=lib).json()
    assert summ["borrowing"]["reasons"] == ["MEMBERSHIP_EXPIRED", "MEMBER_HAS_OVERDUE", "MEMBER_BLOCKED_BY_DEBT", "LOAN_LIMIT_REACHED"]


def test_failed_lend_is_atomic(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s = mk_member(client, lib)
    n = len(audit(app))
    assert lend(client, lib, s, c).status_code == 201
    err(lend(client, lib, s, c), 409, "COPY_NOT_AVAILABLE")
    assert len(audit(app)) == n + 1
