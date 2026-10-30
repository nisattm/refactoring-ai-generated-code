"""Heldout tests: end-to-end scenarios (section 21). Generated from cases/e2e.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    D, add_copy, create_book, error_code, lend, login, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))
LIB = ("lib@library.local", "Librarian123")
ADMIN = ("admin@library.local", "ChangeMe123")


def at(client, clock, y, m, d, hour=10):
    """Move the clock and return fresh librarian headers (tokens expire after 12 hours)."""
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))
    return login(client, *LIB)


def balance(client, lib, mid):
    return client.get(f"/api/v1/members/{mid}/balance", headers=lib).json()


def pay(client, lib, mid, amount):
    return client.post(f"/api/v1/members/{mid}/payments", headers=lib, json={"amount": amount, "method": "cash"})


def res(client, lib, rid):
    return client.get(f"/api/v1/reservations/{rid}", headers=lib).json()


def copy_status(client, lib, cid):
    return client.get(f"/api/v1/copies/{cid}", headers=lib).json()["status"]


def notes(client, lib, mid, kind):
    return client.get(f"/api/v1/members/{mid}/notifications", headers=lib, params={"type": kind}).json()["items"]


def test_t_e2e_02(client, clock, librarian, branch_a, branch_b):
    """T-E2E-02 (LIB-E2E-02): BOOK_RESERVED on renewal; in transit 20 Nov; not received 23 Nov; ready 24 Nov until 27 Nov; fulfilled on 27 Nov"""
    book = create_book(client, librarian)
    c1 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    s1 = register_member(client, librarian, home_branch_id=branch_a["id"])
    s2 = register_member(client, librarian, home_branch_id=branch_b["id"])
    loan = lend(client, librarian, s1["id"], c1["id"])
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=s2["id"])
    assert r["status"] == "waiting" and r["queue_position"] == 1
    lib = at(client, clock, 2026, 11, 10)
    renew = client.post(f"/api/v1/loans/{loan['id']}/renew", headers=lib)
    assert renew.status_code == 409 and error_code(renew) == "BOOK_RESERVED"
    lib = at(client, clock, 2026, 11, 20)
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    assert res(client, lib, r["id"])["status"] == "in_transit"
    assert len(notes(client, lib, s2["id"], "reservation_in_transit")) == 1
    lib = at(client, clock, 2026, 11, 23)
    assert client.post("/api/v1/transfers/process-arrivals", headers=lib).json()["received"] == 0
    lib = at(client, clock, 2026, 11, 24)
    assert client.post("/api/v1/transfers/process-arrivals", headers=lib).json()["received"] == 1
    got = res(client, lib, r["id"])
    assert got["status"] == "ready" and got["hold_until"] == "2026-11-27"
    assert len(notes(client, lib, s2["id"], "reservation_ready")) == 1
    lib = at(client, clock, 2026, 11, 27)
    lend(client, lib, s2["id"], c1["id"])
    assert res(client, lib, r["id"])["status"] == "fulfilled"


def test_t_e2e_04(client, clock, librarian, admin, branch_a):
    """T-E2E-04 (LIB-E2E-04): Fees 4.00, 180.00, 25.00; debt 209.00; 209.01 rejected; 209.00 pays all in order; copy withdrawn"""
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    c1 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"], price="180.00")
    loan = lend(client, librarian, s["id"], c1["id"])
    lib = at(client, clock, 2026, 11, 18)
    assert client.post(f"/api/v1/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    fees = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"]
    assert sorted((f["kind"], f["amount"]) for f in fees) == [("late_fee", "4.00"), ("lost_book", "180.00"), ("lost_processing", "25.00")]
    assert copy_status(client, lib, c1["id"]) == "lost"
    assert balance(client, lib, s["id"])["total_debt"] == "209.00"
    r = pay(client, lib, s["id"], "209.01")
    assert r.status_code == 409 and error_code(r) == "PAYMENT_EXCEEDS_BALANCE"
    p = pay(client, lib, s["id"], "209.00").json()
    order = [f["id"] for f in sorted(fees, key=lambda f: (f["created_on"], f["id"]))]
    assert [a["fee_id"] for a in p["allocations"]] == order
    fees = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"]
    assert {f["status"] for f in fees} == {"paid"}
    adm = login(client, *ADMIN)
    r = client.post(f"/api/v1/copies/{c1['id']}/withdraw", headers=adm, json={"reason": "Lost by member"})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"


def test_t_e2e_06(client, clock, librarian, branch_a):
    """T-E2E-06 (LIB-E2E-06): Old loan due 16 Nov at 2.00; new loan on 3 Nov due 3 Dec at 1.00"""
    book = create_book(client, librarian)
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    l1 = lend(client, librarian, s["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    c2 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    assert client.patch(f"/api/v1/members/{s['id']}", headers=librarian, json={"membership_type": "academic"}).status_code == 200
    lib = at(client, clock, 2026, 11, 3)
    old = client.get(f"/api/v1/loans/{l1['id']}", headers=lib).json()
    assert old["due_date"] == "2026-11-16" and D(old["daily_fee"]) == D("2.00")
    l2 = lend(client, lib, s["id"], c2["id"])
    assert l2["due_date"] == "2026-12-03" and l2["loan_period_days"] == 30 and D(l2["daily_fee"]) == D("1.00")


def test_t_e2e_08(client, clock, librarian, admin, branch_a):
    """T-E2E-08 (LIB-E2E-08): Librarian 403; admin waives; outstanding fees 8.00 → 0.00"""
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    loan = lend(client, librarian, s["id"], add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])["id"])
    lib = at(client, clock, 2026, 11, 20)
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    fee = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"][0]
    assert fee["amount"] == "8.00" and balance(client, lib, s["id"])["outstanding_fees"] == "8.00"
    r = client.post(f"/api/v1/fees/{fee['id']}/waive", headers=lib, json={"reason": "Hospital stay"})
    assert r.status_code == 403
    adm = login(client, *ADMIN)
    r = client.post(f"/api/v1/fees/{fee['id']}/waive", headers=adm, json={"reason": "Hospital stay"})
    assert r.status_code == 200 and r.json()["status"] == "waived"
    assert balance(client, adm, s["id"])["outstanding_fees"] == "0.00"


def test_t_e2e_10(client, clock, librarian):
    """T-E2E-10 (LIB-E2E-10): Fifth wrong 401; correct password 403 ACCOUNT_LOCKED; after 15 minutes 200"""
    for i in range(5):
        r = client.post("/api/v1/auth/login", json={"email": LIB[0], "password": "Wrong0000"})
        assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS", i
    r = client.post("/api/v1/auth/login", json={"email": LIB[0], "password": LIB[1]})
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    clock.advance(minutes=15)
    assert client.post("/api/v1/auth/login", json={"email": LIB[0], "password": LIB[1]}).status_code == 200
