MODULE = "reservations"
TITLE = "module 6 (Reservations)"

HEADER = '''
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
'''


CASES = [
    dict(id="T-RES-01-a", req="LIB-RES-01", type="Normal", input="Member reserves a lent-out book for themselves (no `member_id`)", expected="201, `status` `waiting`, `member_id` = own id, `queue_position` 1", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, member_headers(client, m), book_id=book["id"], pickup_branch_id=branch_a["id"])
    assert r["status"] == "waiting" and r["member_id"] == m["id"] and r["queue_position"] == 1
'''),
    dict(id="T-RES-01-b", req="LIB-RES-01", type="Error", input="Librarian without `member_id`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], expect=422)
'''),
    dict(id="T-RES-01-c", req="LIB-RES-01", type="Error", input="Member sends `member_id` (own id)", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, member_headers(client, m), book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"], expect=422)
'''),
    dict(id="T-RES-02-a", req="LIB-RES-02", type="Error", input="Passive member reserves", expected="`409 MEMBER_PASSIVE`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"
'''),
    dict(id="T-RES-02-b", req="LIB-RES-02", type="Boundary", input="Guest registered 2026-11-02 reserves on 2027-01-30 and on 2027-01-31", expected="First 201; second `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    book2, _, _ = lent_out(client, librarian, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    at(clock, 2027, 1, 30)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=g["id"])
    at(clock, 2027, 1, 31)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book2["id"], "pickup_branch_id": branch_a["id"], "member_id": g["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBERSHIP_EXPIRED"
'''),
    dict(id="T-RES-02-c", req="LIB-RES-02", type="Error", input="Book without copies; book whose only copy is withdrawn", expected="`409 BOOK_NOT_LENDABLE` both", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    empty = create_book(client, librarian)
    book, (copy,) = book_with_copies(client, librarian, branch_a["id"])
    client.post(f"/api/v1/copies/{copy['id']}/withdraw", headers=librarian, json={"reason": "Too old to keep"})
    for b in (empty, book):
        r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": b["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
        assert r.status_code == 409 and error_code(r) == "BOOK_NOT_LENDABLE"
'''),
    dict(id="T-RES-02-d", req="LIB-RES-02", type="Error", input="Same member reserves the same book twice", expected="`409 DUPLICATE_RESERVATION`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "DUPLICATE_RESERVATION"
'''),
    dict(id="T-RES-02-e", req="LIB-RES-02", type="Error", input="Member reserves the book they are borrowing", expected="`409 ALREADY_BORROWED`", code='''
def TEST(client, librarian, branch_a):
    book, (copy,) = book_with_copies(client, librarian, branch_a["id"])
    m = member(client, librarian, branch_a)
    lend(client, librarian, m["id"], copy["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "ALREADY_BORROWED"
'''),
    dict(id="T-RES-02-f", req="LIB-RES-02", type="Error", input="Copy of the book `available` at the pickup branch", expected="`409 COPY_AVAILABLE_AT_BRANCH`", code='''
def TEST(client, librarian, branch_a):
    book, _ = book_with_copies(client, librarian, branch_a["id"])
    m = member(client, librarian, branch_a)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "COPY_AVAILABLE_AT_BRANCH"
'''),
    dict(id="T-RES-02-g", req="LIB-RES-02", type="Error", input="Passive member, book without copies (steps 1 and 3 fail)", expected="`409 MEMBER_PASSIVE` (first failing step)", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    empty = create_book(client, librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": empty["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert error_code(r) == "MEMBER_PASSIVE"
'''),
    dict(id="T-RES-02-h", req="LIB-RES-02", type="Error", input="Member already reserved the book and has 3 active reservations (steps 4 and 6 fail)", expected="`409 DUPLICATE_RESERVATION`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(3)]
    for b in books:
        reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": books[0]["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert error_code(r) == "DUPLICATE_RESERVATION"
'''),
    dict(id="T-RES-03-a", req="LIB-RES-03", type="Boundary", input="Member with 2 active reservations makes a 3rd, then a 4th", expected="3rd 201; 4th `409 RESERVATION_LIMIT_REACHED`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(4)]
    for b in books[:3]:
        reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": books[3]["id"], "pickup_branch_id": branch_a["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "RESERVATION_LIMIT_REACHED"
'''),
    dict(id="T-RES-03-b", req="LIB-RES-03", type="Boundary", input="3 active reservations; one is cancelled; new reservation", expected="201 (cancelled does not count)", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    books = [lent_out(client, librarian, branch_a)[0] for _ in range(4)]
    rs = [reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=m["id"]) for b in books[:3]]
    client.post(f"/api/v1/reservations/{rs[0]['id']}/cancel", headers=librarian)
    reserve(client, librarian, book_id=books[3]["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
'''),
    dict(id="T-RES-04-a", req="LIB-RES-04", type="Normal", input="M1 reserves with pickup B, then M2 with pickup A; copy returned at A", expected="M1 (first in queue) becomes `in_transit`; M2 stays `waiting`", code='''
def TEST(client, librarian, branch_a, branch_b):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m1["id"])
    r2 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m2["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r1["id"])["status"] == "in_transit"
    assert res(client, librarian, r2["id"])["status"] == "waiting"
'''),
    dict(id="T-RES-04-b", req="LIB-RES-04", type="Normal", input="Guest reserves before an academic; copy returned at the pickup branch", expected="Guest's reservation becomes `ready` (no priority by type)", code='''
def TEST(client, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    a = member(client, librarian, branch_a, membership_type="academic")
    rg = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=g["id"])
    ra = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=a["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, rg["id"])["status"] == "ready"
    assert res(client, librarian, ra["id"])["status"] == "waiting"
'''),
    dict(id="T-RES-05-a", req="LIB-RES-05", type="Normal", input="Only copy is `available` at B; member reserves with pickup A", expected="Reservation `in_transit` at once; copy `in_transfer`", code='''
def TEST(client, librarian, branch_a, branch_b):
    book, (copy,) = book_with_copies(client, librarian, branch_b["id"])
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    assert res(client, librarian, r["id"])["status"] == "in_transit"
    assert copy_status(client, librarian, copy["id"]) == "in_transfer"
'''),
    dict(id="T-RES-06-a", req="LIB-RES-06", type="Normal", input="Three members reserve the same book", expected="Queue view lists them in creation order with `queue_position` 1, 2, 3", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    ms = [member(client, librarian, branch_a) for _ in range(3)]
    for m in ms:
        reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    items = client.get(f"/api/v1/books/{book['id']}/reservations", headers=librarian).json()["items"]
    assert [i["member_id"] for i in items] == [m["id"] for m in ms]
    assert [i["queue_position"] for i in items] == [1, 2, 3]
'''),
    dict(id="T-RES-07-a", req="LIB-RES-07", type="Normal", input="One waiting and one cancelled reservation; filter `status=cancelled`", expected="Only the cancelled one", code='''
def TEST(client, librarian, branch_a):
    b1, _, _ = lent_out(client, librarian, branch_a)
    b2, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, book_id=b1["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    r2 = reserve(client, librarian, book_id=b2["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    client.post(f"/api/v1/reservations/{r2['id']}/cancel", headers=librarian)
    items = client.get("/api/v1/reservations", headers=librarian, params={"status": "cancelled"}).json()["items"]
    assert [i["id"] for i in items] == [r2["id"]]
'''),
    dict(id="T-RES-08-a", req="LIB-RES-08", type="Normal", input="Good return at the home branch, no reservation", expected="Copy `available`", code='''
def TEST(client, librarian, branch_a):
    _, copy, loan = lent_out(client, librarian, branch_a)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert copy_status(client, librarian, copy["id"]) == "available"
'''),
    dict(id="T-RES-08-b", req="LIB-RES-08", type="Normal", input="Good return at a foreign branch (B), no reservation", expected="Copy `in_transfer`; a `return_home` transfer B → A exists", code='''
def TEST(client, librarian, branch_a, branch_b):
    _, copy, loan = lent_out(client, librarian, branch_a)
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
    assert copy_status(client, librarian, copy["id"]) == "in_transfer"
    items = client.get("/api/v1/transfers", headers=librarian, params={"copy_id": copy["id"]}).json()["items"]
    assert [(t["reason"], t["from_branch_id"], t["to_branch_id"]) for t in items] == [("return_home", branch_b["id"], branch_a["id"])]
'''),
    dict(id="T-RES-08-c", req="LIB-RES-08", type="Normal", input="Waiting reservation with pickup A; copy returned at A", expected="Reservation `ready`, copy `on_hold` and assigned", code='''
def TEST(client, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "ready" and got["copy_id"] == copy["id"]
    assert copy_status(client, librarian, copy["id"]) == "on_hold"
'''),
    dict(id="T-RES-08-d", req="LIB-RES-08", type="Normal", input="Waiting reservation with pickup B; copy returned at A", expected="Reservation `in_transit` with `copy_id`; `reservation` transfer A → B", code='''
def TEST(client, librarian, branch_a, branch_b):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "in_transit" and got["copy_id"] == copy["id"]
    items = client.get("/api/v1/transfers", headers=librarian, params={"copy_id": copy["id"]}).json()["items"]
    assert [(t["reason"], t["to_branch_id"], t["reservation_id"]) for t in items] == [("reservation", branch_b["id"], r["id"])]
'''),
    dict(id="T-RES-09-a", req="LIB-RES-09", type="Normal", input="Reservation becomes ready on Monday 2026-11-02", expected="`ready_on` 2026-11-02, `hold_until` 2026-11-05; notification `reservation_ready` for the member", code='''
def TEST(client, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = res(client, librarian, r["id"])
    assert got["ready_on"] == "2026-11-02" and got["hold_until"] == "2026-11-05"
    notes = client.get(f"/api/v1/members/{m['id']}/notifications", headers=librarian, params={"type": "reservation_ready"}).json()["items"]
    assert [n["reservation_id"] for n in notes] == [r["id"]]
'''),
    dict(id="T-RES-09-b", req="LIB-RES-09", type="Boundary", input="Reservation becomes ready on 2026-10-28 (29 Oct holiday, weekend follows)", expected="`hold_until` 2026-11-03", code='''
def TEST(client, clock, librarian, branch_a):
    at(clock, 2026, 10, 26)
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    at(clock, 2026, 10, 28)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert res(client, librarian, r["id"])["hold_until"] == "2026-11-03"
'''),
    dict(id="T-RES-10-a", req="LIB-RES-10", type="Normal", input="Member borrows the held copy", expected="Reservation `fulfilled`, `closed_at` set; copy `on_loan`", code='''
def TEST(client, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    lend(client, librarian, m["id"], copy["id"])
    got = res(client, librarian, r["id"])
    assert got["status"] == "fulfilled" and got["closed_at"] is not None
    assert copy_status(client, librarian, copy["id"]) == "on_loan"
'''),
    dict(id="T-RES-10-b", req="LIB-RES-10", type="Normal", input="Ready reservation (copy C1 held); member borrows another copy C2 that became available", expected="Reservation `fulfilled`; C1 released (`available`)", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-RES-10-c", req="LIB-RES-10", type="Normal", input="In-transit reservation (copy C1 travelling to B); member borrows copy C2 at A", expected="Reservation `fulfilled`; transfer of C1 continues (`in_transit`)", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-RES-11-a", req="LIB-RES-11", type="Normal", input="Ready 2026-11-02 (hold until 2026-11-05) for M1, M2 waiting; `process-expired` on 2026-11-06", expected="`{\"expired\": 1}`; M1 `expired`; M2 `ready` with `hold_until` 2026-11-11; copy stays `on_hold`", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-RES-11-b", req="LIB-RES-11", type="Boundary", input="Hold expired (no other reservation); librarian lends the copy to the same member without running `process-expired`", expected="Reservation is expired first; copy becomes `available` and the loan is created; reservation stays `expired`", code='''
def TEST(client, clock, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 6)
    lend(client, librarian, m["id"], copy["id"])
    assert res(client, librarian, r["id"])["status"] == "expired"
'''),
    dict(id="T-RES-12-a", req="LIB-RES-12", type="Boundary", input="`hold_until` 2026-11-05: `process-expired` on 2026-11-05, then on 2026-11-06", expected="0 expired; then 1 expired", code='''
def TEST(client, clock, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 5, hour=23)
    assert process_expired(client, librarian) == 0
    at(clock, 2026, 11, 6, hour=0)
    assert process_expired(client, librarian) == 1
'''),
    dict(id="T-RES-12-b", req="LIB-RES-12", type="Boundary", input="Member collects on the last hold day (2026-11-05)", expected="Loan created; reservation `fulfilled`", code='''
def TEST(client, clock, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 5, hour=17)
    lend(client, librarian, m["id"], copy["id"])
    assert res(client, librarian, r["id"])["status"] == "fulfilled"
'''),
    dict(id="T-RES-13-a", req="LIB-RES-13", type="Normal", input="Member cancels own waiting reservation", expected="200; `cancelled`, `cancel_reason` `member_request`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    r = reserve(client, mh, book_id=book["id"], pickup_branch_id=branch_a["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=mh)
    assert got.status_code == 200
    assert got.json()["status"] == "cancelled" and got.json()["cancel_reason"] == "member_request"
'''),
    dict(id="T-RES-13-b", req="LIB-RES-13", type="Normal", input="Librarian cancels a ready reservation; nobody else waiting", expected="`cancel_reason` `staff_request`; copy `available`", code='''
def TEST(client, librarian, branch_a):
    book, copy, loan = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian).json()
    assert got["cancel_reason"] == "staff_request"
    assert copy_status(client, librarian, copy["id"]) == "available"
'''),
    dict(id="T-RES-13-c", req="LIB-RES-13", type="Error", input="Cancel an already cancelled reservation", expected="`409 RESERVATION_NOT_ACTIVE`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian)
    again = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=librarian)
    assert again.status_code == 409 and error_code(again) == "RESERVATION_NOT_ACTIVE"
'''),
    dict(id="T-RES-13-d", req="LIB-RES-13", type="Error", input="Member cancels another member's reservation", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    owner, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=owner["id"])
    got = client.post(f"/api/v1/reservations/{r['id']}/cancel", headers=member_headers(client, other))
    assert got.status_code == 403
'''),
    dict(id="T-RES-14-a", req="LIB-RES-14", type="Boundary", input="Waiting reservation; 200 days later `process-expired`", expected="Still `waiting`; 0 expired", code='''
def TEST(client, clock, librarian, branch_a):
    book, _, _ = lent_out(client, librarian, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    clock.advance(days=200)
    assert process_expired(client, librarian) == 0
    assert res(client, librarian, r["id"])["status"] == "waiting"
'''),
]
