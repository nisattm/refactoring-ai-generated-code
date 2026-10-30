"""Heldout tests: module 6 (Reservations). Generated from cases/reservations.md."""
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


def test_t_res_01_b(client, librarian, branch_a):
    """T-RES-01-b (LIB-RES-01): 422 VALIDATION_ERROR"""
    book, _, _ = lent_out(client, librarian, branch_a)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], expect=422)


def test_t_res_02_b(client, clock, librarian, branch_a):
    """T-RES-02-b (LIB-RES-02): First 201; second 409 MEMBERSHIP_EXPIRED"""
    book, _, _ = lent_out(client, librarian, branch_a)
    book2, _, _ = lent_out(client, librarian, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    at(clock, 2027, 1, 30)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=g["id"])
    at(clock, 2027, 1, 31)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book2["id"], "pickup_branch_id": branch_a["id"], "member_id": g["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBERSHIP_EXPIRED"


def test_t_res_02_d(client, librarian, branch_a):
    """T-RES-02-d (LIB-RES-02): 409 DUPLICATE_RESERVATION"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "DUPLICATE_RESERVATION"


def test_t_res_02_f(client, librarian, branch_a):
    """T-RES-02-f (LIB-RES-02): 409 COPY_AVAILABLE_AT_BRANCH"""
    book, _ = book_with_copies(client, librarian, branch_a["id"])
    m = member(client, librarian, branch_a)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "COPY_AVAILABLE_AT_BRANCH"


def test_t_res_02_h(client, librarian, branch_a):
    """T-RES-02-h (LIB-RES-02): 409 DUPLICATE_RESERVATION"""
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(3)]
    for b in books:
        reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": books[0]["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert error_code(r) == "DUPLICATE_RESERVATION"


def test_t_res_03_b(client, librarian, branch_a):
    """T-RES-03-b (LIB-RES-03): 201 (cancelled does not count)"""
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(4)]
    rs = [reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"]) for b in books[:3]]
    client.post(f"/api/v1/reservations/{rs[0]['id']}/cancel", headers=librarian)
    reserve(client, librarian, book_id=books[3]["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])


def test_t_res_04_b(client, librarian, branch_a):
    """T-RES-04-b (LIB-RES-04): Guest's reservation becomes ready (no priority by type)"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    a = member(client, librarian, branch_a, membership_type="academic")
    rg = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=g["id"])
    ra = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=a["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, rg["id"])["status"] == "ready"
    assert res(client, librarian, ra["id"])["status"] == "waiting"


def test_t_res_06_a(client, librarian, branch_a):
    """T-RES-06-a (LIB-RES-06): Queue view lists them in creation order with queue_position 1, 2, 3"""
    book, _, _ = lent_out(client, librarian, branch_a)
    ms = [member(client, librarian, branch_a) for _ in range(3)]
    for m in ms:
        reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    items = client.get(f"/api/v1/books/{book['id']}/reservations", headers=librarian).json()["items"]
    assert [i["member_id"] for i in items] == [m["id"] for m in ms]
    assert [i["queue_position"] for i in items] == [1, 2, 3]


def test_t_res_08_b(client, librarian, branch_a, branch_b):
    """T-RES-08-b (LIB-RES-08): Copy in_transfer; a return_home transfer B → A exists"""
    _, copy, loan = lent_out(client, librarian, branch_a)
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
    assert copy_status(client, librarian, copy["id"]) == "in_transfer"
    items = client.get("/api/v1/transfers", headers=librarian, params={"copy_id": copy["id"]}).json()["items"]
    assert [(t["reason"], t["from_branch_id"], t["to_branch_id"]) for t in items] == [("return_home", branch_b["id"], branch_a["id"])]


def test_t_res_08_d(client, librarian, branch_a, branch_b):
    """T-RES-08-d (LIB-RES-08): Reservation in_transit with copy_id; reservation transfer A → B"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "in_transit" and got["copy_id"] == copy["id"]
    items = client.get("/api/v1/transfers", headers=librarian, params={"copy_id": copy["id"]}).json()["items"]
    assert [(t["reason"], t["to_branch_id"], t["reservation_id"]) for t in items] == [("reservation", branch_b["id"], r["id"])]


def test_t_res_09_b(client, clock, librarian, branch_a):
    """T-RES-09-b (LIB-RES-09): hold_until 2026-11-03"""
    at(clock, 2026, 10, 26)
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    at(clock, 2026, 10, 28)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r["id"])["hold_until"] == "2026-11-03"


def test_t_res_10_b(client, librarian, branch_a):
    """T-RES-10-b (LIB-RES-10): Reservation fulfilled; C1 released (available)"""
    book, (c1, c2) = book_with_copies(client, librarian, branch_a["id"], n=2)
    h1, h2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = lend(client, librarian, h1["id"], c1["id"])
    l2 = lend(client, librarian, h2["id"], c2["id"])
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, l1["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r["id"])["copy_id"] == c1["id"]
    return_loan(client, librarian, l2["id"], branch_id=branch_a["id"])
    lend(client, librarian, m["id"], c2["id"])
    assert res(client, librarian, r["id"])["status"] == "fulfilled"
    assert copy_status(client, librarian, c1["id"]) == "available"


def test_t_res_11_b(client, clock, librarian, branch_a):
    """T-RES-11-b (LIB-RES-11): Reservation is expired first; copy becomes available and the loan is created; reservation stays expired"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 6)
    lend(client, librarian, m["id"], copy["id"])
    assert res(client, librarian, r["id"])["status"] == "expired"


def test_t_res_12_b(client, clock, librarian, branch_a):
    """T-RES-12-b (LIB-RES-12): Loan created; reservation fulfilled"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 5, hour=17)
    lend(client, librarian, m["id"], copy["id"])
    assert res(client, librarian, r["id"])["status"] == "fulfilled"


def test_t_res_13_b(client, librarian, branch_a):
    """T-RES-13-b (LIB-RES-13): cancel_reason staff_request; copy available"""
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian).json()
    assert got["cancel_reason"] == "staff_request"
    assert copy_status(client, librarian, copy["id"]) == "available"


def test_t_res_13_d(client, librarian, branch_a):
    """T-RES-13-d (LIB-RES-13): 403 FORBIDDEN"""
    book, _, _ = lent_out(client, librarian, branch_a)
    owner, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=owner["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=member_headers(client, other))
    assert got.status_code == 403


def test_t_res_14_a(client, clock, librarian, branch_a):
    """T-RES-14-a (LIB-RES-14): Still waiting; 0 expired"""
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    clock.advance(days=200)
    assert process_expired(client, librarian) == 0
    assert res(client, librarian, r["id"])["status"] == "waiting"
