"""Heldout tests: module 3 (Members). Generated from cases/members.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    D, add_copy, create_book, error_code, lend, login, member_headers, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))


def at(clock, y, m, d, hour=10):
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))


def payload(branch_id, **kw):
    data = {"full_name": "Ayşe Yılmaz", "email": "ayse@uni.edu.tr", "membership_type": "student",
            "university_id": "20231234", "home_branch_id": branch_id, "password": "Member1234"}
    data.update(kw)
    return {k: v for k, v in data.items() if v is not ...}


def get_member(client, lib, mid):
    return client.get(f"/api/v1/members/{mid}", headers=lib).json()


def test_t_mem_01_b(client, librarian, branch_a):
    """T-MEM-01-b (LIB-MEM-01): 403 FORBIDDEN; 422 VALIDATION_ERROR"""
    other = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.post("/api/v1/members", headers=member_headers(client, other), json=payload(branch_a["id"]))
    assert r.status_code == 403
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], password="short1"))
    assert r.status_code == 422


def test_t_mem_02_b(client, librarian, branch_a):
    """T-MEM-02-b (LIB-MEM-02): 422 VALIDATION_ERROR"""
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="academic", university_id=...))
    assert r.status_code == 422


def test_t_mem_04_b(client, librarian, branch_a):
    """T-MEM-04-b (LIB-MEM-04): membership_valid false"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    out = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian).json()
    assert out["status"] == "passive" and out["membership_valid"] is False


def test_t_mem_05_b(client, librarian, branch_a):
    """T-MEM-05-b (LIB-MEM-05): 409 CONFLICT, details.field email"""
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="LIB@library.local"))
    assert r.status_code == 409 and r.json()["error"]["details"]["field"] == "email"


def test_t_mem_06_b(client, clock, librarian, branch_a):
    """T-MEM-06-b (LIB-MEM-06): Only the guest; list ordered by id"""
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    register_member(client, librarian, home_branch_id=branch_a["id"])
    at(clock, 2027, 2, 1)
    lib = login(client, "lib@library.local", "Librarian123")
    items = client.get("/api/v1/members", headers=lib, params={"membership_valid": "false"}).json()["items"]
    assert [m["id"] for m in items] == [g["id"]]
    ids = [m["id"] for m in client.get("/api/v1/members", headers=lib).json()["items"]]
    assert ids == sorted(ids)


def test_t_mem_07_b(client, librarian, branch_a):
    """T-MEM-07-b (LIB-MEM-07): 409 MEMBER_FIELDS_INVALID"""
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    r = client.patch(f"/api/v1/members/{g['id']}", headers=librarian, json={"university_id": "U5555"})
    assert r.status_code == 409 and error_code(r) == "MEMBER_FIELDS_INVALID"


def test_t_mem_08_b(client, librarian, branch_a):
    """T-MEM-08-b (LIB-MEM-08): First 200 with university_id null; second 409 MEMBER_FIELDS_INVALID"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "5320000000"})
    assert r.status_code == 200 and r.json()["university_id"] is None
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "staff"})
    assert r.status_code == 409 and error_code(r) == "MEMBER_FIELDS_INVALID"


def test_t_mem_09_b(client, clock, librarian, branch_a):
    """T-MEM-09-b (LIB-MEM-09): 2027-04-30 (+90); 2027-05-15 (today + 89)"""
    g1 = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    g2 = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    at(clock, 2027, 1, 30)
    lib = login(client, "lib@library.local", "Librarian123")
    assert client.post(f"/api/v1/members/{g1['id']}/renew-membership", headers=lib).json()["valid_until"] == "2027-04-30"
    at(clock, 2027, 2, 15)
    lib = login(client, "lib@library.local", "Librarian123")
    assert client.post(f"/api/v1/members/{g2['id']}/renew-membership", headers=lib).json()["valid_until"] == "2027-05-15"


def test_t_mem_10_b(client, clock, librarian, branch_a):
    """T-MEM-10-b (LIB-MEM-10): 200 passive; reservation cancelled with member_deactivated; member can still log in"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    book = create_book(client, librarian)
    c = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], c["id"])
    other_book = create_book(client, librarian)
    oc = add_copy(client, librarian, other_book["id"], home_branch_id=branch_a["id"])
    holder = register_member(client, librarian, home_branch_id=branch_a["id"])
    lend(client, librarian, holder["id"], oc["id"])
    res = reserve(client, librarian, book_id=other_book["id"], pickup_branch_id=branch_a["id"], member_id=m["id"])
    at(clock, 2026, 11, 18)
    lib = login(client, "lib@library.local", "Librarian123")
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    r = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=lib)
    assert r.status_code == 200 and r.json()["status"] == "passive"
    got = client.get(f"/api/v1/reservations/{res['id']}", headers=lib).json()
    assert got["status"] == "cancelled" and got["cancel_reason"] == "member_deactivated"
    member_headers(client, m)


def test_t_mem_11_b(client, librarian, branch_a):
    """T-MEM-11-b (LIB-MEM-11): 409 MEMBER_ALREADY_ACTIVE"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/members/{m['id']}/activate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_ALREADY_ACTIVE"


def test_t_mem_12_b(client, clock, librarian, branch_a):
    """T-MEM-12-b (LIB-MEM-12): reasons = [MEMBERSHIP_EXPIRED, MEMBER_HAS_OVERDUE, MEMBER_BLOCKED_BY_DEBT, LOAN_LIMIT_REACHED] in this order; not eligible"""
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    book = create_book(client, librarian)
    for _ in range(2):
        lend(client, librarian, g["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    at(clock, 2027, 1, 31)
    lib = login(client, "lib@library.local", "Librarian123")
    s = client.get(f"/api/v1/members/{g['id']}/summary", headers=lib).json()
    assert s["open_loans"] == 2 and s["overdue_loans"] == 2
    assert s["borrowing"] == {"eligible": False, "reasons": ["MEMBERSHIP_EXPIRED", "MEMBER_HAS_OVERDUE", "MEMBER_BLOCKED_BY_DEBT", "LOAN_LIMIT_REACHED"]}


def test_t_mem_13_b(client, librarian):
    """T-MEM-13-b (LIB-MEM-13): 404 NOT_FOUND"""
    r = client.get("/api/v1/members/me", headers=librarian)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
