"""Heldout tests: module 11 (Branches and transfers). Generated from cases/branches.md."""
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


def test_t_br_01_b(client, admin, librarian, branch_a):
    """T-BR-01-b (LIB-BR-01): 409 CONFLICT; 422; 403 FORBIDDEN"""
    create_branch(client, admin, "a", expect=409)
    create_branch(client, admin, "X", expect=422)
    create_branch(client, admin, "ABCDEFGHIJK", expect=422)
    create_branch(client, librarian, "LIBX", expect=403)


def test_t_br_02_a(client, admin, librarian, branch_a, branch_b):
    """T-BR-02-a (LIB-BR-02): Ordered by code A, B, C; filter returns the inactive one; member 200"""
    c = create_branch(client, admin, "C")
    deactivate(client, admin, c["id"])
    codes = [b["code"] for b in client.get("/api/v1/branches", headers=admin).json()["items"]]
    assert codes == ["A", "B", "C"]
    inactive = client.get("/api/v1/branches", headers=admin, params={"is_active": "false"}).json()["items"]
    assert [b["code"] for b in inactive] == ["C"]
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    assert client.get("/api/v1/branches", headers=mh).status_code == 200


def test_t_br_03_b(client, admin, librarian, branch_a, branch_b):
    """T-BR-03-b (LIB-BR-03): First 200 (is_active false); second 409 BRANCH_IN_USE"""
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


def test_t_br_04_b(client, admin, librarian, branch_a):
    """T-BR-04-b (LIB-BR-04): 409 BRANCH_INACTIVE (checked before the others)"""
    off = create_branch(client, admin, "OFF")
    deactivate(client, admin, off["id"])
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post("/api/v1/reservations", headers=librarian, json={"book_id": book["id"], "pickup_branch_id": off["id"], "member_id": m["id"]})
    assert error_code(r) == "BRANCH_INACTIVE"


def test_t_br_05_b(client, clock, librarian, branch_a, branch_b):
    """T-BR-05-b (LIB-BR-05): expected_on 2026-11-02"""
    at(clock, 2026, 10, 28)
    lib = login(client, "lib@library.local", "Librarian123")
    c = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch_a["id"])
    assert relocate(client, lib, c["id"], branch_b["id"]).json()["expected_on"] == "2026-11-02"


def test_t_br_06_b(client, admin, librarian, branch_a, branch_b):
    """T-BR-06-b (LIB-BR-06): 409 INVALID_COPY_STATUS; 409 SAME_BRANCH; 409 BRANCH_INACTIVE (first in order)"""
    book = create_book(client, librarian)
    lent = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    free = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], lent["id"])
    assert error_code(relocate(client, librarian, lent["id"], branch_b["id"])) == "INVALID_COPY_STATUS"
    assert error_code(relocate(client, librarian, free["id"], branch_a["id"])) == "SAME_BRANCH"
    off = create_branch(client, admin, "OFF")
    deactivate(client, admin, off["id"])
    assert error_code(relocate(client, librarian, lent["id"], off["id"])) == "BRANCH_INACTIVE"


def test_t_br_07_b(client, clock, librarian, branch_a, branch_b):
    """T-BR-07-b (LIB-BR-07): Copy at A, home still A, available"""
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, register_member(client, librarian, home_branch_id=branch_a["id"])["id"], c["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
    at(clock, 2026, 11, 4)
    lib = login(client, "lib@library.local", "Librarian123")
    arrivals(client, lib)
    cp = copy_of(client, lib, c["id"])
    assert (cp["home_branch_id"], cp["current_branch_id"], cp["status"]) == (branch_a["id"], branch_a["id"], "available")


def test_t_br_07_d(client, clock, librarian, branch_a, branch_b):
    """T-BR-07-d (LIB-BR-07): On arrival the copy is released: return_home transfer B → A starts, copy in_transfer"""
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


def test_t_br_08_a(client, clock, librarian, branch_a, branch_b):
    """T-BR-08-a (LIB-BR-08): 0 received; then 1"""
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
