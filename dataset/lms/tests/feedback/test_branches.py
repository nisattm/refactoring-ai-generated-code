"""Feedback tests: module 11 (Branches and transfers). Generated from cases/branches.md."""
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


def test_t_br_01_a(client, admin):
    """T-BR-01-a (LIB-BR-01): 201; code KAMPUS, is_active true"""
    b = create_branch(client, admin, "kampus", name="Kampüs")
    assert b["code"] == "KAMPUS" and b["name"] == "Kampüs" and b["is_active"] is True


def test_t_br_03_a(client, admin, librarian, branch_a, branch_b):
    """T-BR-03-a (LIB-BR-03): 409 BRANCH_IN_USE both"""
    register_member(client, librarian, home_branch_id=branch_a["id"])
    add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_b["id"])
    for b in (branch_a, branch_b):
        r = deactivate(client, admin, b["id"])
        assert r.status_code == 409 and error_code(r) == "BRANCH_IN_USE"


def test_t_br_04_a(client, admin, librarian, branch_a):
    """T-BR-04-a (LIB-BR-04): 409 BRANCH_INACTIVE each"""
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


def test_t_br_05_a(client, clock, librarian, branch_a, branch_b):
    """T-BR-05-a (LIB-BR-05): started_on 2026-11-06, expected_on 2026-11-10, status in_transit; copy in_transfer with current_branch_id null"""
    at(clock, 2026, 11, 6)
    lib = login(client, "lib@library.local", "Librarian123")
    c = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch_a["id"])
    t = relocate(client, lib, c["id"], branch_b["id"]).json()
    assert (t["started_on"], t["expected_on"], t["status"], t["reason"]) == ("2026-11-06", "2026-11-10", "in_transit", "relocation")
    cp = copy_of(client, lib, c["id"])
    assert cp["status"] == "in_transfer" and cp["current_branch_id"] is None


def test_t_br_06_a(client, librarian, branch_a, branch_b):
    """T-BR-06-a (LIB-BR-06): 201 with the transfer (from_branch_id A, to_branch_id B)"""
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    r = relocate(client, librarian, c["id"], branch_b["id"])
    assert r.status_code == 201
    assert (r.json()["from_branch_id"], r.json()["to_branch_id"]) == (branch_a["id"], branch_b["id"])


def test_t_br_07_a(client, clock, librarian, branch_a, branch_b):
    """T-BR-07-a (LIB-BR-07): Transfer received on 2026-11-04; copy home and current branch B, available"""
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    t = relocate(client, librarian, c["id"], branch_b["id"]).json()
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    assert arrivals(client, lib) == 1
    got = client.get(f"/api/v1/transfers/{t['id']}", headers=lib).json()
    assert got["status"] == "received" and got["received_on"] == "2026-11-04"
    cp = copy_of(client, lib, c["id"])
    assert (cp["home_branch_id"], cp["current_branch_id"], cp["status"]) == (branch_b["id"], branch_b["id"], "available")


def test_t_br_07_c(client, clock, librarian, branch_a, branch_b):
    """T-BR-07-c (LIB-BR-07): Reservation ready at the pickup branch with hold_until = arrival + 3 working days; copy on_hold"""
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


def test_t_br_09_a(client, admin, librarian, branch_a, branch_b):
    """T-BR-09-a (LIB-BR-09): Ordered by id descending; filters match"""
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
