"""End-to-end scenarios of section 21.

LIB-E2E-04, 05, 06, 08, 09 and 11 are exercised in test_fines, test_loans, test_purchasing and test_dataexchange;
the others are here."""

from tests.test_auth import admin_h, audit, err, h, login, make_user, token_of  # noqa: F401
from tests.test_loans import API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret  # noqa: F401
from tests.test_reservations import arrivals, reserve, res


def balance(client, hd, member):
    return client.get(f"{API}/members/{member}/balance", headers=hd).json()


def test_e2e_01_late_return_and_borrowing_block(client, lib, clock):
    at(clock, 2026, 11, 2)
    s = mk_member(client, lib)
    k, k2 = mk_book(client, lib, 0), mk_book(client, lib, 1)
    c1, c2 = new_copy(client, lib, k, "BC-0001"), new_copy(client, lib, k2, "BC-0002")
    loan = lend(client, lib, s, c1)
    assert loan.status_code == 201 and loan.json()["due_date"] == "2026-11-16"
    at(clock, 2026, 12, 14)
    err(lend(client, lib, s, c2), 409, "MEMBER_HAS_OVERDUE")
    at(clock, 2026, 12, 21)
    r = ret(client, lib, loan.json()["id"], branch=1)
    assert r.status_code == 200, r.text
    assert r.json()["late_days"] == 25
    fees = client.get(f"{API}/members/{s}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"]) for f in fees] == [("late_fee", "50.00")]
    assert balance(client, lib, s)["total_debt"] == "50.00" and balance(client, lib, s)["blocked"] is True
    err(lend(client, lib, s, c2), 409, "MEMBER_BLOCKED_BY_DEBT")
    p = client.post(f"{API}/members/{s}/payments", headers=lib, json={"amount": "0.01", "method": "cash"})
    assert p.status_code == 201, p.text
    assert balance(client, lib, s)["total_debt"] == "49.99"
    assert lend(client, lib, s, c2).status_code == 201


def test_e2e_02_reservation_at_another_branch(client, lib, clock):
    at(clock, 2026, 11, 2)
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    k = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, k, "BC-0001", branch=1)
    loan = lend(client, lib, s1, c1).json()
    r = reserve(client, lib, k, 2, s2)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "waiting" and r.json()["queue_position"] == 1
    rid = r.json()["id"]
    at(clock, 2026, 11, 10)
    err(client.post(f"{API}/loans/{loan['id']}/renew", headers=lib), 409, "BOOK_RESERVED")
    at(clock, 2026, 11, 20)
    assert ret(client, lib, loan["id"], branch=1).status_code == 200
    t = client.get(f"{API}/transfers", headers=lib).json()["items"]
    assert len(t) == 1 and t[0]["reason"] == "reservation" and t[0]["to_branch_id"] == 2
    assert res(client, lib, rid)["status"] == "in_transit"
    notes = client.get(f"{API}/members/{s2}/notifications", headers=lib).json()["items"]
    assert [n["type"] for n in notes] == ["reservation_in_transit"]
    at(clock, 2026, 11, 23)
    assert arrivals(client, lib) == 0
    assert res(client, lib, rid)["status"] == "in_transit"
    at(clock, 2026, 11, 24)
    assert arrivals(client, lib) == 1
    r = res(client, lib, rid)
    assert r["status"] == "ready" and r["hold_until"] == "2026-11-27"
    notes = client.get(f"{API}/members/{s2}/notifications", headers=lib).json()["items"]
    assert sorted(n["type"] for n in notes) == ["reservation_in_transit", "reservation_ready"]
    at(clock, 2026, 11, 27)
    assert client.post(f"{API}/loans", headers=lib, json={"member_id": s2, "copy_id": c1}).status_code == 201
    assert res(client, lib, rid)["status"] == "fulfilled"


def test_e2e_03_hold_expires_and_passes_on(client, lib, clock):
    at(clock, 2026, 10, 20)
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    k = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, k, "BC-0001", branch=1)
    loan = lend(client, lib, s3, c1).json()
    r1 = reserve(client, lib, k, 1, s1).json()
    r2 = reserve(client, lib, k, 1, s2).json()
    at(clock, 2026, 10, 28)
    assert ret(client, lib, loan["id"], branch=1).status_code == 200
    r = res(client, lib, r1["id"])
    assert r["status"] == "ready" and r["hold_until"] == "2026-11-03"
    at(clock, 2026, 11, 4)
    assert client.post(f"{API}/reservations/process-expired", headers=lib).json() == {"expired": 1}
    assert res(client, lib, r1["id"])["status"] == "expired"
    r = res(client, lib, r2["id"])
    assert r["status"] == "ready" and r["hold_until"] == "2026-11-09"
    n1 = client.get(f"{API}/members/{s1}/notifications", headers=lib).json()["items"]
    assert "reservation_expired" in [n["type"] for n in n1]
    n2 = client.get(f"{API}/members/{s2}/notifications", headers=lib).json()["items"]
    assert "reservation_ready" in [n["type"] for n in n2]
    assert copy_of(client, lib, c1)["status"] == "on_hold"
    err(lend(client, lib, s1, c1), 409, "COPY_ON_HOLD")


def test_e2e_07_damaged_return_and_repair(client, lib, clock):
    at(clock, 2026, 11, 2)
    s, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    k = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, k, "BC-0001", branch=1, price="120.00")
    loan = lend(client, lib, s, c1).json()
    rid = reserve(client, lib, k, 1, s2).json()["id"]
    at(clock, 2026, 11, 5)
    err(ret(client, lib, loan["id"], condition="damaged", damage_fee="130.00"), 409, "DAMAGE_FEE_EXCEEDS_PRICE")
    r = ret(client, lib, loan["id"], condition="damaged", damage_fee="40.00")
    assert r.status_code == 200, r.text
    fees = client.get(f"{API}/members/{s}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"]) for f in fees] == [("damage_fee", "40.00")]
    assert copy_of(client, lib, c1)["status"] == "damaged"
    assert res(client, lib, rid)["status"] == "waiting"
    at(clock, 2026, 11, 6)
    assert client.post(f"{API}/copies/{c1}/repair", headers=lib).status_code == 200
    r = res(client, lib, rid)
    assert r["status"] == "ready" and r["hold_until"] == "2026-11-11"


def test_e2e_10_login_lockout(client, admin_h, clock):
    make_user(client, admin_h)
    for _ in range(4):
        err(login(client, "lib@example.com", "wrong-pass1"), 401, "INVALID_CREDENTIALS")
    err(login(client, "lib@example.com", "wrong-pass1"), 401, "INVALID_CREDENTIALS")
    err(login(client, "lib@example.com", "Passw0rd1"), 403, "ACCOUNT_LOCKED")
    clock.advance(minutes=15)
    assert login(client, "lib@example.com", "Passw0rd1").status_code == 200
