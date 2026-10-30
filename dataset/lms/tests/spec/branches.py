MODULE = "branches"
TITLE = "module 11 (Branches and transfers)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, error_code, lend, login, member_headers, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))


def at(clock, y, m, d, hour=10):
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))


def copy_of(client, lib, cid):
    return client.get(f"/api/v1/copies/{cid}", headers=lib).json()


def relocate(client, lib, copy_id, to_branch_id):
    return client.post("/api/v1/transfers", headers=lib, json={"copy_id": copy_id, "to_branch_id": to_branch_id})


def arrivals(client, lib):
    r = client.post("/api/v1/transfers/process-arrivals", headers=lib)
    assert r.status_code == 200, r.text
    return r.json()["received"]


def deactivate(client, admin, branch_id):
    return client.patch(f"/api/v1/branches/{branch_id}", headers=admin, json={"is_active": False})
'''


CASES = [
    dict(id="T-BR-01-a", req="LIB-BR-01", type="Normal", input="Admin creates branch `kampus` named `Kampüs`", expected="201; `code` `KAMPUS`, `is_active` true", code='''
def TEST(client, admin):
    b = create_branch(client, admin, "kampus", name="Kampüs")
    assert b["code"] == "KAMPUS" and b["name"] == "Kampüs" and b["is_active"] is True
'''),
    dict(id="T-BR-01-b", req="LIB-BR-01", type="Error", input="Code `A` again as `a`; code `X` (1 char) and 11 chars; librarian creates a branch", expected="`409 CONFLICT`; `422`; `403 FORBIDDEN`", code='''
def TEST(client, admin, librarian, branch_a):
    create_branch(client, admin, "a", expect=409)
    create_branch(client, admin, "X", expect=422)
    create_branch(client, admin, "ABCDEFGHIJK", expect=422)
    create_branch(client, librarian, "LIBX", expect=403)
'''),
    dict(id="T-BR-02-a", req="LIB-BR-02", type="Normal", input="Branches `C`, `A` (fixture), `B` (fixture), one inactive; list; filter `is_active=false`; member reads list", expected="Ordered by code A, B, C; filter returns the inactive one; member 200", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    c = create_branch(client, admin, "C")
    deactivate(client, admin, c["id"])
    codes = [b["code"] for b in client.get("/api/v1/branches", headers=admin).json()["items"]]
    assert codes == ["A", "B", "C"]
    inactive = client.get("/api/v1/branches", headers=admin, params={"is_active": "false"}).json()["items"]
    assert [b["code"] for b in inactive] == ["C"]
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.get("/api/v1/branches", headers=mh).status_code == 200
'''),
    dict(id="T-BR-03-a", req="LIB-BR-03", type="Error", input="Deactivate a branch that is a member's home branch; one that holds a copy", expected="`409 BRANCH_IN_USE` both", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    register_member(client, librarian, home_branch_id=branch_a["id"])
    add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_b["id"])
    for b in (branch_a, branch_b):
        r = deactivate(client, admin, b["id"])
        assert r.status_code == 409 and error_code(r) == "BRANCH_IN_USE"
'''),
    dict(id="T-BR-03-b", req="LIB-BR-03", type="Boundary", input="Branch whose only copy is withdrawn and with no members; branch that is the pickup branch of an active reservation", expected="First 200 (`is_active` false); second `409 BRANCH_IN_USE`", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    c = create_branch(client, admin, "C")
    book = create_book(client, librarian)
    cp = add_copy(client, librarian, book["id"], home_branch_id=c["id"])
    client.post(f"/api/v1/copies/{cp['id']}/withdraw", headers=librarian, json={"reason": "Damaged beyond repair"})
    r = deactivate(client, admin, c["id"])
    assert r.status_code == 200 and r.json()["is_active"] is False
    d = create_branch(client, admin, "D")
    book2 = create_book(client, librarian)
    c2 = add_copy(client, librarian, book2["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c2["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    reserve(client, librarian, book_id=book2["id"], pickup_branch_id=d["id"], member_id=m["id"])
    r = deactivate(client, admin, d["id"])
    assert r.status_code == 409 and error_code(r) == "BRANCH_IN_USE"
'''),
    dict(id="T-BR-04-a", req="LIB-BR-04", type="Error", input="Inactive branch used as member home branch, copy home branch, pickup branch", expected="`409 BRANCH_INACTIVE` each", code='''
def TEST(client, admin, librarian, branch_a):
    off = create_branch(client, admin, "OFF")
    deactivate(client, admin, off["id"])
    r = client.post("/api/v1/members", headers=librarian, json={"full_name": "M", "email": "m@uni.edu.tr", "membership_type": "student",
                                                                  "university_id": "U7001", "home_branch_id": off["id"], "password": "Member1234"})
    assert error_code(r) == "BRANCH_INACTIVE"
    book = create_book(client, librarian)
    r = client.post(f"/api/v1/books/{book['id']}/copies", headers=librarian, json={"barcode": "OFF-0001", "home_branch_id": off["id"], "price": "10.00", "acquired_on": "2026-11-01"})
    assert error_code(r) == "BRANCH_INACTIVE"
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": off["id"], "member_id": m["id"]})
    assert r.status_code == 409 and error_code(r) == "BRANCH_INACTIVE"
'''),
    dict(id="T-BR-04-b", req="LIB-BR-04", type="Error", input="Passive member reserves with an inactive pickup branch (two 409 checks fail)", expected="`409 BRANCH_INACTIVE` (checked before the others)", code='''
def TEST(client, admin, librarian, branch_a):
    off = create_branch(client, admin, "OFF")
    deactivate(client, admin, off["id"])
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": off["id"], "member_id": m["id"]})
    assert error_code(r) == "BRANCH_INACTIVE"
'''),
    dict(id="T-BR-05-a", req="LIB-BR-05", type="Normal", input="Relocation started Friday 2026-11-06", expected="`started_on` 2026-11-06, `expected_on` 2026-11-10, `status` `in_transit`; copy `in_transfer` with `current_branch_id` null", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    at(clock, 2026, 11, 6)
    lib = login(client, "lib@library.local", "Librarian123")
    c = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch_a["id"])
    t = relocate(client, lib, c["id"], branch_b["id"]).json()
    assert (t["started_on"], t["expected_on"], t["status"], t["reason"]) == ("2026-11-06", "2026-11-10", "in_transit", "relocation")
    cp = copy_of(client, lib, c["id"])
    assert cp["status"] == "in_transfer" and cp["current_branch_id"] is None
'''),
    dict(id="T-BR-05-b", req="LIB-BR-05", type="Boundary", input="Transfer started on 2026-10-28 (29 Oct holiday)", expected="`expected_on` 2026-11-02", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    at(clock, 2026, 10, 28)
    lib = login(client, "lib@library.local", "Librarian123")
    c = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch_a["id"])
    assert relocate(client, lib, c["id"], branch_b["id"]).json()["expected_on"] == "2026-11-02"
'''),
    dict(id="T-BR-06-a", req="LIB-BR-06", type="Normal", input="Relocate an available copy from A to B", expected="201 with the transfer (`from_branch_id` A, `to_branch_id` B)", code='''
def TEST(client, librarian, branch_a, branch_b):
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    r = relocate(client, librarian, c["id"], branch_b["id"])
    assert r.status_code == 201
    assert (r.json()["from_branch_id"], r.json()["to_branch_id"]) == (branch_a["id"], branch_b["id"])
'''),
    dict(id="T-BR-06-b", req="LIB-BR-06", type="Error", input="Relocate a lent copy; relocate to its own branch; relocate a lent copy to an inactive branch", expected="`409 INVALID_COPY_STATUS`; `409 SAME_BRANCH`; `409 BRANCH_INACTIVE` (first in order)", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    book = create_book(client, librarian)
    lent = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    free = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], lent["id"])
    assert error_code(relocate(client, librarian, lent["id"], branch_b["id"])) == "INVALID_COPY_STATUS"
    assert error_code(relocate(client, librarian, free["id"], branch_a["id"])) == "SAME_BRANCH"
    off = create_branch(client, admin, "OFF")
    deactivate(client, admin, off["id"])
    assert error_code(relocate(client, librarian, lent["id"], off["id"])) == "BRANCH_INACTIVE"
'''),
    dict(id="T-BR-07-a", req="LIB-BR-07", type="Normal", input="Relocation A → B received", expected="Transfer `received` on 2026-11-04; copy home and current branch B, `available`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    t = relocate(client, librarian, c["id"], branch_b["id"]).json()
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    assert arrivals(client, lib) == 1
    got = client.get(f"/api/v1/transfers/{t['id']}", headers=lib).json()
    assert got["status"] == "received" and got["received_on"] == "2026-11-04"
    cp = copy_of(client, lib, c["id"])
    assert (cp["home_branch_id"], cp["current_branch_id"], cp["status"]) == (branch_b["id"], branch_b["id"], "available")
'''),
    dict(id="T-BR-07-b", req="LIB-BR-07", type="Normal", input="Copy returned at B (home A) → `return_home` transfer; received", expected="Copy at A, home still A, `available`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    arrivals(client, lib)
    cp = copy_of(client, lib, c["id"])
    assert (cp["home_branch_id"], cp["current_branch_id"], cp["status"]) == (branch_a["id"], branch_a["id"], "available")
'''),
    dict(id="T-BR-07-c", req="LIB-BR-07", type="Normal", input="Reservation transfer arrives while the reservation is still `in_transit`", expected="Reservation `ready` at the pickup branch with `hold_until` = arrival + 3 working days; copy `on_hold`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    res = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    arrivals(client, lib)
    got = client.get(f"/api/v1/reservations/{res['id']}", headers=lib).json()
    assert got["status"] == "ready" and got["ready_on"] == "2026-11-04" and got["hold_until"] == "2026-11-09"
    assert copy_of(client, lib, c["id"])["status"] == "on_hold"
'''),
    dict(id="T-BR-07-d", req="LIB-BR-07", type="Normal", input="Reservation cancelled while its copy travels to B; nobody else waiting", expected="On arrival the copy is released: `return_home` transfer B → A starts, copy `in_transfer`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    res = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=m["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    client.post(f"/api/v1/reservations/{res['id']}/cancel", headers=librarian)
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    arrivals(client, lib)
    assert copy_of(client, lib, c["id"])["status"] == "in_transfer"
    pending = client.get("/api/v1/transfers", headers=lib, params={"copy_id": c["id"], "status": "in_transit"}).json()["items"]
    assert [(t["reason"], t["from_branch_id"], t["to_branch_id"]) for t in pending] == [("return_home", branch_b["id"], branch_a["id"])]
'''),
    dict(id="T-BR-08-a", req="LIB-BR-08", type="Boundary", input="Transfer started 2026-11-06 (expected 2026-11-10): `process-arrivals` on 2026-11-09, then 2026-11-10", expected="0 received; then 1", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    at(clock, 2026, 11, 6)
    lib = login(client, "lib@library.local", "Librarian123")
    c = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch_a["id"])
    relocate(client, lib, c["id"], branch_b["id"])
    at(clock, 2026, 11, 9, hour=23)
    lib = login(client, "lib@library.local", "Librarian123")
    assert arrivals(client, lib) == 0
    at(clock, 2026, 11, 10, hour=8)
    lib = login(client, "lib@library.local", "Librarian123")
    assert arrivals(client, lib) == 1
'''),
    dict(id="T-BR-09-a", req="LIB-BR-09", type="Normal", input="Two relocations; filters `status`, `reason`, `to_branch_id`; order", expected="Ordered by `id` descending; filters match", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    c_branch = create_branch(client, admin, "C")
    book = create_book(client, librarian)
    c1 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    t1 = relocate(client, librarian, c1["id"], branch_b["id"]).json()
    t2 = relocate(client, librarian, c2["id"], c_branch["id"]).json()
    ids = [t["id"] for t in client.get("/api/v1/transfers", headers=librarian).json()["items"]]
    assert ids == [t2["id"], t1["id"]]
    to_b = client.get("/api/v1/transfers", headers=librarian, params={"to_branch_id": branch_b["id"], "reason": "relocation", "status": "in_transit"}).json()["items"]
    assert [t["id"] for t in to_b] == [t1["id"]]
'''),
]
