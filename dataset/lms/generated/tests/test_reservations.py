import pytest

from tests.test_loans import (  # noqa: F401
    API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret,
)
from tests.test_auth import admin_h, audit, err  # noqa: F401


def reserve(client, hd, book, branch=1, member=None):
    body = {"book_id": book, "pickup_branch_id": branch}
    if member is not None:
        body["member_id"] = member
    return client.post(f"{API}/reservations", headers=hd, json=body)


def res(client, hd, rid):
    r = client.get(f"{API}/reservations/{rid}", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()


def arrivals(client, hd):
    r = client.post(f"{API}/transfers/process-arrivals", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()["received"]


def test_create_and_queue(client, lib, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2, m3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    assert lend(client, lib, m1, c).status_code == 201
    r1 = reserve(client, lib, book, 1, m2)
    assert r1.status_code == 201, r1.text
    body = r1.json()
    assert body["status"] == "waiting" and body["queue_position"] == 1 and body["copy_id"] is None
    assert body["ready_on"] is None and body["hold_until"] is None and body["closed_at"] is None
    assert body["cancel_reason"] is None and body["created_at"].endswith("+03:00")
    r2 = reserve(client, member_h(client, 3), book, 2)
    assert r2.status_code == 201 and r2.json()["member_id"] == m3 and r2.json()["queue_position"] == 2
    q = client.get(f"{API}/books/{book}/reservations", headers=lib).json()
    assert [(i["id"], i["queue_position"]) for i in q["items"]] == [(1, 1), (2, 2)] and q["total"] == 2
    assert [a.entity_id for a in audit(app, "reservation_created")] == [1, 2]


def test_create_roles_and_validation(client, lib):
    book = mk_book(client, lib, 0)
    new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, m1, 1)
    assert err(reserve(client, lib, book, 1), 422, "VALIDATION_ERROR")  # staff must send member_id
    mh = member_h(client, 2)
    assert err(reserve(client, mh, book, 1, m2), 422, "VALIDATION_ERROR")  # member must not
    assert err(client.post(f"{API}/reservations", headers=mh, json={"book_id": book}), 422, "VALIDATION_ERROR")
    assert err(client.post(f"{API}/reservations", json={"book_id": book, "pickup_branch_id": 1}), 401, "UNAUTHENTICATED")
    e = err(reserve(client, lib, 99, 1, m2), 404, "NOT_FOUND")
    assert e["details"] == {"field": "book_id", "id": 99}
    e = err(reserve(client, lib, book, 9, m2), 404, "NOT_FOUND")
    assert e["details"] == {"field": "pickup_branch_id", "id": 9}
    e = err(reserve(client, lib, book, 1, 99), 404, "NOT_FOUND")
    assert e["details"] == {"field": "member_id", "id": 99}


def test_creation_checks_in_order(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    book2 = mk_book(client, lib, 1)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    # (3) not lendable: no copies at all
    assert err(reserve(client, lib, book2, 1, m2), 409, "BOOK_NOT_LENDABLE")
    # (7) copy available at the pickup branch
    assert err(reserve(client, lib, book, 1, m2), 409, "COPY_AVAILABLE_AT_BRANCH")
    lend(client, lib, m1, c)
    # (5) already borrowed
    assert err(reserve(client, lib, book, 1, m1), 409, "ALREADY_BORROWED")
    assert reserve(client, lib, book, 1, m2).status_code == 201
    # (4) duplicate
    assert err(reserve(client, lib, book, 2, m2), 409, "DUPLICATE_RESERVATION")
    # passive member
    client.post(f"{API}/members/{m2}/deactivate", headers=lib)
    assert err(reserve(client, lib, book, 1, m2), 409, "MEMBER_PASSIVE")
    # inactive branch is checked first
    client.post(f"{API}/members/{m2}/activate", headers=lib)
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    assert err(reserve(client, lib, book, 2, m1), 409, "BRANCH_INACTIVE")


def test_membership_expired_and_limit(client, lib, clock):
    books = [mk_book(client, lib, n) for n in range(4)]
    for i, b in enumerate(books):
        new_copy(client, lib, b, f"BC-000{i}")
    holder = mk_member(client, lib, 1)
    m2 = mk_member(client, lib, 2)
    # the holder has all four books out, so the limit of 5 is not an issue
    for i in range(4):
        assert lend(client, lib, holder, i + 1).status_code == 201
    for b in books[:3]:
        assert reserve(client, lib, b, 1, m2).status_code == 201
    assert err(reserve(client, lib, books[3], 1, m2), 409, "RESERVATION_LIMIT_REACHED")
    # cancelled reservations do not count
    assert client.post(f"{API}/reservations/1/cancel", headers=lib).status_code == 200
    assert reserve(client, lib, books[3], 1, m2).status_code == 201
    at(clock, 2027, 11, 5)
    assert err(reserve(client, lib, books[0], 1, m2), 409, "MEMBERSHIP_EXPIRED")


def test_immediate_assignment_and_arrival(client, lib, app):
    """LIB-RES-05 and LIB-BR-05/07: a copy available elsewhere is sent at once."""
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", branch=1)
    m = mk_member(client, lib, 1)
    r = reserve(client, lib, book, 2, m)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "in_transit" and r.json()["copy_id"] == c and r.json()["queue_position"] is None
    cp = copy_of(client, lib, c)
    assert cp["status"] == "in_transfer" and cp["current_branch_id"] is None
    t = client.get(f"{API}/transfers/1", headers=lib).json()
    assert t["reason"] == "reservation" and t["reservation_id"] == 1
    assert (t["from_branch_id"], t["to_branch_id"], t["expected_on"]) == (1, 2, "2026-11-04")
    assert [a.entity_id for a in audit(app, "reservation_in_transit")] == [1]


def test_e2e_02_reservation_at_another_branch(client, lib, clock, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    loan = lend(client, lib, s1, c).json()
    r = reserve(client, lib, book, 2, s2)
    assert r.json()["status"] == "waiting" and r.json()["queue_position"] == 1
    at(clock, 2026, 11, 10)
    assert err(client.post(f"{API}/loans/{loan['id']}/renew", headers=lib), 409, "BOOK_RESERVED")
    at(clock, 2026, 11, 20)
    assert ret(client, lib, loan["id"], branch=1).status_code == 200
    assert res(client, lib, 1)["status"] == "in_transit"
    t = client.get(f"{API}/transfers", headers=lib).json()["items"]
    assert [(x["reason"], x["status"], x["expected_on"]) for x in t] == [("reservation", "in_transit", "2026-11-24")]
    at(clock, 2026, 11, 23)
    assert arrivals(client, lib) == 0
    at(clock, 2026, 11, 24)
    assert arrivals(client, lib) == 1
    got = res(client, lib, 1)
    assert (got["status"], got["ready_on"], got["hold_until"]) == ("ready", "2026-11-24", "2026-11-27")
    cp = copy_of(client, lib, c)
    assert cp["status"] == "on_hold" and cp["current_branch_id"] == 2
    t = client.get(f"{API}/transfers/1", headers=lib).json()
    assert t["status"] == "received" and t["received_on"] == "2026-11-24"
    assert [a.entity_id for a in audit(app, "reservation_ready")] == [1]
    assert [a.entity_id for a in audit(app, "transfer_received")] == [1]
    at(clock, 2026, 11, 27)
    r = lend(client, lib, s2, c)
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == 2
    got = res(client, lib, 1)
    assert got["status"] == "fulfilled" and got["closed_at"] is not None
    assert copy_of(client, lib, c)["status"] == "on_loan"


def test_e2e_03_hold_expires_and_passes_on(client, lib, clock):
    book = mk_book(client, lib, 0)
    at(clock, 2026, 10, 20)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s3, c)
    assert reserve(client, lib, book, 1, s1).status_code == 201
    assert reserve(client, lib, book, 1, s2).status_code == 201
    at(clock, 2026, 10, 28)
    assert ret(client, lib, 1, branch=1).status_code == 200
    r1 = res(client, lib, 1)
    assert (r1["status"], r1["hold_until"]) == ("ready", "2026-11-03")
    assert res(client, lib, 2)["queue_position"] == 1
    at(clock, 2026, 11, 3)  # hold boundary
    r = client.post(f"{API}/reservations/process-expired", headers=lib)
    assert r.status_code == 200 and r.json() == {"expired": 0}
    at(clock, 2026, 11, 4)
    r = client.post(f"{API}/reservations/process-expired", headers=lib)
    assert r.json() == {"expired": 1}
    assert res(client, lib, 1)["status"] == "expired" and res(client, lib, 1)["closed_at"] is not None
    r2 = res(client, lib, 2)
    assert (r2["status"], r2["hold_until"]) == ("ready", "2026-11-09")
    assert copy_of(client, lib, c)["status"] == "on_hold"
    assert err(lend(client, lib, s1, c), 409, "COPY_ON_HOLD")
    # only the holder can borrow the held copy
    assert lend(client, lib, s2, c).status_code == 201
    assert res(client, lib, 2)["status"] == "fulfilled"


def test_lend_expires_stale_hold_first(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s3, c)
    reserve(client, lib, book, 1, s1)
    assert ret(client, lib, 1).status_code == 200
    assert res(client, lib, 1)["hold_until"] == "2026-11-05"
    at(clock, 2026, 11, 5)
    assert lend(client, lib, s2, c).status_code == 409  # still held for s1
    at(clock, 2026, 11, 6)
    r = lend(client, lib, s2, c)  # hold passed and nobody waits: the copy is free again
    assert r.status_code == 201, r.text
    assert res(client, lib, 1)["status"] == "expired"


def test_e2e_07_damaged_return_and_repair(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="120.00")
    s, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    loan = lend(client, lib, s, c).json()
    assert reserve(client, lib, book, 1, s2).status_code == 201
    at(clock, 2026, 11, 5)
    assert err(ret(client, lib, loan["id"], condition="damaged", damage_fee="130.00"), 409, "DAMAGE_FEE_EXCEEDS_PRICE")
    assert ret(client, lib, loan["id"], condition="damaged", damage_fee="40.00").status_code == 200
    assert copy_of(client, lib, c)["status"] == "damaged"
    assert res(client, lib, 1)["status"] == "waiting"
    at(clock, 2026, 11, 6)
    assert client.post(f"{API}/copies/{c}/repair", headers=lib).status_code == 200
    got = res(client, lib, 1)
    assert (got["status"], got["hold_until"]) == ("ready", "2026-11-11")


def test_new_copy_serves_waiting_reservation(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, s1, c)
    reserve(client, lib, book, 2, s2)
    c2 = new_copy(client, lib, book, "BC-0002", branch=1)
    assert res(client, lib, 1)["status"] == "in_transit" and res(client, lib, 1)["copy_id"] == c2
    c3 = new_copy(client, lib, book, "BC-0003", branch=2)
    assert copy_of(client, lib, c3)["status"] == "available"


def test_cancel_by_member_and_staff(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s1, c)
    reserve(client, lib, book, 1, s2)
    reserve(client, lib, book, 1, s3)
    # another member cannot cancel it
    e = err(client.post(f"{API}/reservations/1/cancel", headers=member_h(client, 3)), 403, "FORBIDDEN")
    assert err(client.post(f"{API}/reservations/9/cancel", headers=member_h(client, 3)), 404, "NOT_FOUND")
    r = client.post(f"{API}/reservations/1/cancel", headers=member_h(client, 2))
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "member_request"
    assert res(client, lib, 2)["queue_position"] == 1
    assert err(client.post(f"{API}/reservations/1/cancel", headers=lib), 409, "RESERVATION_NOT_ACTIVE")
    r = client.post(f"{API}/reservations/2/cancel", headers=lib)
    assert r.json()["cancel_reason"] == "staff_request" and r.json()["queue_position"] is None


def test_cancel_ready_releases_copy_to_next(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s1, c)
    reserve(client, lib, book, 1, s2)
    reserve(client, lib, book, 2, s3)
    ret(client, lib, 1)
    assert res(client, lib, 1)["status"] == "ready"
    client.post(f"{API}/reservations/1/cancel", headers=lib)
    got = res(client, lib, 2)
    assert got["status"] == "in_transit"
    assert copy_of(client, lib, c)["status"] == "in_transfer"
    # cancelling an in-transit reservation: the transfer continues, the copy is released on arrival
    client.post(f"{API}/reservations/2/cancel", headers=lib)
    assert copy_of(client, lib, c)["status"] == "in_transfer"


def test_in_transit_fulfilled_copy_released_on_arrival(client, lib, clock):
    """LIB-RES-10 (c): the transfer continues and the copy is released when it arrives."""
    book = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, book, "BC-0001")
    c2 = new_copy(client, lib, book, "BC-0002", branch=2)
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s1, c1)
    lend(client, lib, s3, c2)
    reserve(client, lib, book, 2, s2)
    ret(client, lib, 1, branch=1)  # c1 goes to branch 2 for the reservation
    assert res(client, lib, 1)["status"] == "in_transit"
    ret(client, lib, 2, branch=2)  # c2 is free at branch 2 (nobody waits any more)
    assert copy_of(client, lib, c2)["status"] == "available"
    assert lend(client, lib, s2, c2).status_code == 201
    assert res(client, lib, 1)["status"] == "fulfilled"
    assert copy_of(client, lib, c1)["status"] == "in_transfer"
    at(clock, 2026, 11, 4)
    assert arrivals(client, lib) == 1
    # c1 is released at branch 2, away from its home branch 1: it starts a return transfer
    cp = copy_of(client, lib, c1)
    assert cp["status"] == "in_transfer"
    reasons = [t["reason"] for t in client.get(f"{API}/transfers", headers=lib).json()["items"]]
    assert reasons == ["return_home", "reservation"]


def test_fulfil_with_other_copy_releases_held_copy(client, lib):
    book = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, book, "BC-0001")
    c2 = new_copy(client, lib, book, "BC-0002")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, s1, c1)
    s3 = mk_member(client, lib, 3)
    lend(client, lib, s3, c2)
    reserve(client, lib, book, 1, s2)
    ret(client, lib, 1)  # c1 -> held for s2
    assert copy_of(client, lib, c1)["status"] == "on_hold"
    ret(client, lib, 2)  # c2 returned: no waiting reservation, becomes available
    assert copy_of(client, lib, c2)["status"] == "available"
    r = lend(client, lib, s2, c2)
    assert r.status_code == 201
    assert res(client, lib, 1)["status"] == "fulfilled"
    assert copy_of(client, lib, c1)["status"] == "available"


def test_deactivate_cancels_reservations(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    lend(client, lib, s1, c)
    reserve(client, lib, book, 1, s2)
    reserve(client, lib, book, 1, s3)
    ret(client, lib, 1)
    assert res(client, lib, 1)["status"] == "ready"
    r = client.post(f"{API}/members/{s2}/deactivate", headers=lib)
    assert r.status_code == 200, r.text
    got = res(client, lib, 1)
    assert got["status"] == "cancelled" and got["cancel_reason"] == "member_deactivated"
    assert res(client, lib, 2)["status"] == "ready"
    summary = client.get(f"{API}/members/{s2}/summary", headers=lib).json()
    assert summary["active_reservations"] == 0
    summary = client.get(f"{API}/members/{s3}/summary", headers=lib).json()
    assert summary["active_reservations"] == 1


def test_lists_and_permissions(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, s1, c)
    reserve(client, lib, book, 1, s2)
    mh1, mh2 = member_h(client, 1), member_h(client, 2)
    assert client.get(f"{API}/reservations", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/reservations?status=waiting&member_id={s2}&book_id={book}&pickup_branch_id=1", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/reservations?status=expired", headers=lib).json()["total"] == 0
    assert err(client.get(f"{API}/reservations?status=bogus", headers=lib), 422, "VALIDATION_ERROR")
    assert err(client.get(f"{API}/reservations", headers=mh2), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/books/{book}/reservations", headers=mh2), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/books/99/reservations", headers=lib), 404, "NOT_FOUND")
    assert err(client.post(f"{API}/reservations/process-expired", headers=mh2), 403, "FORBIDDEN")
    assert client.get(f"{API}/reservations/1", headers=mh2).status_code == 200
    assert err(client.get(f"{API}/reservations/1", headers=mh1), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/reservations/9", headers=lib), 404, "NOT_FOUND")
    assert client.get(f"{API}/members/{s2}/reservations", headers=mh2).json()["total"] == 1
    assert err(client.get(f"{API}/members/{s2}/reservations", headers=mh1), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/members/99/reservations", headers=lib), 404, "NOT_FOUND")
    assert client.get(f"{API}/members/{s1}/reservations", headers=lib).json()["items"] == []


def test_branch_in_use_by_active_reservation(client, lib, admin_h):
    from tests.test_branches import mk_branch

    mk_branch(client, admin_h, "CCC")
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    s1, s2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, s1, c)
    reserve(client, lib, book, 3, s2)
    assert err(client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/reservations/1/cancel", headers=lib)
    assert client.patch(f"{API}/branches/3", headers=admin_h, json={"is_active": False}).status_code == 200
