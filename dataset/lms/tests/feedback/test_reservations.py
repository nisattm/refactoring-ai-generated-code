"""Feedback tests: module 6 (Reservations). Generated from cases/reservations.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, error_code, lend, member_headers, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))


def at(clock, y, m, d, hour=10):
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))


def book_with_copies(client, lib, branch_id, n=1):
    book = create_book(client, lib)
    copies = [add_copy(client, lib, book["id"], home_branch_id=branch_id) for _ in range(n)]
    return book, copies


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def copy_status(client, lib, copy_id):
    return client.get(f"/api/v1/copies/{copy_id}", headers=lib).json()["status"]


def res(client, lib, rid):
    return client.get(f"/api/v1/reservations/{rid}", headers=lib).json()


def process_expired(client, lib):
    r = client.post("/api/v1/reservations/process-expired", headers=lib)
    assert r.status_code == 200, r.text
    return r.json()["expired"]


def lent_out(client, lib, branch):
    """A book with one copy at `branch`, lent to a fresh student; returns (book, copy, loan)."""
    book, (copy,) = book_with_copies(client, lib, branch["id"])
    holder = member(client, lib, branch)
    loan = lend(client, lib, holder["id"], copy["id"])
    return book, copy, loan


def test_t_res_01_a(client, librarian, branch_a):
    """T-RES-01-a (LIB-RES-01): 201, status waiting, member_id = own id, queue_position 1"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, member_headers(client, m), book_id=book["id"], pickup_branch_id=branch_a["id"])
    assert r["status"] == "waiting" and r["member_id"] == m["id"] and r["queue_position"] == 1


def test_t_res_01_c(client, librarian, branch_a):
    """T-RES-01-c (LIB-RES-01): 422 VALIDATION_ERROR"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, member_headers(client, m), book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"], expect=422)


def test_t_res_02_a(client, librarian, branch_a):
    """T-RES-02-a (LIB-RES-02): 409 MEMBER_PASSIVE"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"


def test_t_res_02_c(client, librarian, branch_a):
    """T-RES-02-c (LIB-RES-02): 409 BOOK_NOT_LENDABLE both"""
    m = member(client, librarian, branch_a)
    empty = create_book(client, librarian)
    book, (copy,) = book_with_copies(client, librarian, branch_a["id"])
    client.post(f"/api/v1/copies/{copy['id']}/withdraw", headers=librarian, json={"reason": "Too old to keep"})
    for b in (empty, book):
        r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": b["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
        assert r.status_code == 409 and error_code(r) == "BOOK_NOT_LENDABLE"


def test_t_res_02_e(client, librarian, branch_a):
    """T-RES-02-e (LIB-RES-02): 409 ALREADY_BORROWED"""
    book, (copy,) = book_with_copies(client, librarian, branch_a["id"])
    m = member(client, librarian, branch_a)
    lend(client, librarian, m["id"], copy["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "ALREADY_BORROWED"


def test_t_res_02_g(client, librarian, branch_a):
    """T-RES-02-g (LIB-RES-02): 409 MEMBER_PASSIVE (first failing step)"""
    m = member(client, librarian, branch_a)
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    empty = create_book(client, librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": empty["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert error_code(r) == "MEMBER_PASSIVE"


def test_t_res_03_a(client, librarian, branch_a):
    """T-RES-03-a (LIB-RES-03): 3rd 201; 4th 409 RESERVATION_LIMIT_REACHED"""
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(4)]
    for b in books[:3]:
        reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": books[3]["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "RESERVATION_LIMIT_REACHED"


def test_t_res_04_a(client, librarian, branch_a, branch_b):
    """T-RES-04-a (LIB-RES-04): M1 (first in queue) becomes in_transit; M2 stays waiting"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m1["id"])
    r2 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m2["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r1["id"])["status"] == "in_transit"
    assert res(client, librarian, r2["id"])["status"] == "waiting"


def test_t_res_05_a(client, librarian, branch_a, branch_b):
    """T-RES-05-a (LIB-RES-05): Reservation in_transit at once; copy in_transfer"""
    book, (copy,) = book_with_copies(client, librarian, branch_b["id"])
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    assert res(client, librarian, r["id"])["status"] == "in_transit"
    assert copy_status(client, librarian, copy["id"]) == "in_transfer"


def test_t_res_07_a(client, librarian, branch_a):
    """T-RES-07-a (LIB-RES-07): Only the cancelled one"""
    b1, _, _ = lent_out(client, librarian, branch_a)
    b2, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, book_id=b1["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r2 = reserve(client, librarian, book_id=b2["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    client.post(f"/api/v1/reservations/{r2['id']}/cancel", headers=librarian)
    items = client.get("/api/v1/reservations", headers=librarian, params={"status": "cancelled"}).json()["items"]
    assert [i["id"] for i in items] == [r2["id"]]


def test_t_res_08_a(client, librarian, branch_a):
    """T-RES-08-a (LIB-RES-08): Copy available"""
    _, copy, loan = lent_out(client, librarian, branch_a)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert copy_status(client, librarian, copy["id"]) == "available"


def test_t_res_08_c(client, librarian, branch_a):
    """T-RES-08-c (LIB-RES-08): Reservation ready, copy on_hold and assigned"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "ready" and got["copy_id"] == copy["id"]
    assert copy_status(client, librarian, copy["id"]) == "on_hold"


def test_t_res_09_a(client, librarian, branch_a):
    """T-RES-09-a (LIB-RES-09): ready_on 2026-11-02, hold_until 2026-11-05; notification reservation_ready for the member"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["ready_on"] == "2026-11-02" and got["hold_until"] == "2026-11-05"
    notes = client.get(f"/api/v1/members/{m['id']}/notifications", headers=librarian, params={"type": "reservation_ready"}).json()["items"]
    assert [n["reservation_id"] for n in notes] == [r["id"]]


def test_t_res_10_a(client, librarian, branch_a):
    """T-RES-10-a (LIB-RES-10): Reservation fulfilled, closed_at set; copy on_loan"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    lend(client, librarian, m["id"], copy["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "fulfilled" and got["closed_at"] is not None
    assert copy_status(client, librarian, copy["id"]) == "on_loan"


def test_t_res_10_c(client, librarian, branch_a, branch_b):
    """T-RES-10-c (LIB-RES-10): Reservation fulfilled; transfer of C1 continues (in_transit)"""
    book, (c1, c2) = book_with_copies(client, librarian, branch_a["id"], n=2)
    h1, h2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = lend(client, librarian, h1["id"], c1["id"])
    l2 = lend(client, librarian, h2["id"], c2["id"])
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m["id"])
    return_loan(client, librarian, l1["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r["id"])["status"] == "in_transit"
    return_loan(client, librarian, l2["id"], branch_id=branch_a["id"])
    lend(client, librarian, m["id"], c2["id"])
    assert res(client, librarian, r["id"])["status"] == "fulfilled"
    t = client.get("/api/v1/transfers", headers=librarian, params={"copy_id": c1["id"]}).json()["items"][0]
    assert t["status"] == "in_transit" and copy_status(client, librarian, c1["id"]) == "in_transfer"


def test_t_res_11_a(client, clock, librarian, branch_a):
    """T-RES-11-a (LIB-RES-11): {'expired': 1}; M1 expired; M2 ready with hold_until 2026-11-11; copy stays on_hold"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m1["id"])
    r2 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m2["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 6)
    assert process_expired(client, librarian) == 1
    assert res(client, librarian, r1["id"])["status"] == "expired"
    got = res(client, librarian, r2["id"])
    assert got["status"] == "ready" and got["hold_until"] == "2026-11-11"
    assert copy_status(client, librarian, copy["id"]) == "on_hold"
    notes = client.get(f"/api/v1/members/{m1['id']}/notifications", headers=librarian, params={"type": "reservation_expired"}).json()["items"]
    assert len(notes) == 1


def test_t_res_12_a(client, clock, librarian, branch_a):
    """T-RES-12-a (LIB-RES-12): 0 expired; then 1 expired"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 5, hour=23)
    assert process_expired(client, librarian) == 0
    at(clock, 2026, 11, 6, hour=0)
    assert process_expired(client, librarian) == 1


def test_t_res_13_a(client, librarian, branch_a):
    """T-RES-13-a (LIB-RES-13): 200; cancelled, cancel_reason member_request"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    r = reserve(client, mh, book_id=book["id"], pickup_branch_id=branch_a["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=mh)
    assert got.status_code == 200
    assert got.json()["status"] == "cancelled" and got.json()["cancel_reason"] == "member_request"


def test_t_res_13_c(client, librarian, branch_a):
    """T-RES-13-c (LIB-RES-13): 409 RESERVATION_NOT_ACTIVE"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian)
    again = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian)
    assert again.status_code == 409 and error_code(again) == "RESERVATION_NOT_ACTIVE"
