"""Feedback tests: module 3 (Members). Generated from cases/members.md."""
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


def test_t_mem_01_a(client, librarian, branch_a):
    """T-MEM-01-a (LIB-MEM-01): 201 MemberOut: member_no M000001, status active, membership_valid true; user account can log in with role member"""
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"]))
    assert r.status_code == 201
    m = r.json()
    assert m["member_no"] == "M000001" and m["status"] == "active" and m["membership_valid"] is True
    assert "user_id" not in m
    me = client.get("/api/v1/auth/me", headers=login(client, "ayse@uni.edu.tr", "Member1234")).json()
    assert me["role"] == "member" and me["member_id"] == m["id"] and me["full_name"] == "Ayşe Yılmaz"


def test_t_mem_02_a(client, librarian, branch_a):
    """T-MEM-02-a (LIB-MEM-02): 422 VALIDATION_ERROR both"""
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="guest", university_id=...))
    assert r.status_code == 422
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="guest", phone="+90 532 000 0000"))
    assert r.status_code == 422


def test_t_mem_02_c(client, librarian, branch_a):
    """T-MEM-02-c (LIB-MEM-02): 10 and 15 accepted; the others 422"""
    base = dict(membership_type="guest", university_id=...)
    assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="g1@x.com", phone="5320000000", **base)).status_code == 201
    assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="g2@x.com", phone="+905320000000123", **base)).status_code == 201
    for i, ph in enumerate(("532000000", "+9053200000001234")):
        assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email=f"g3{i}@x.com", phone=ph, **base)).status_code == 422
    for i, uid in enumerate(("ABC", "A" * 21)):
        assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email=f"s{i}@x.com", university_id=uid)).status_code == 422


def test_t_mem_03_a(client, librarian, branch_a):
    """T-MEM-03-a (LIB-MEM-03): membership_start 2026-11-02; valid_until 2027-11-01 and 2027-01-30"""
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    assert s["membership_start"] == "2026-11-02" and s["valid_until"] == "2027-11-01"
    assert g["valid_until"] == "2027-01-30"


def test_t_mem_04_a(client, clock, librarian, branch_a):
    """T-MEM-04-a (LIB-MEM-04): membership_valid true, then false"""
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    at(clock, 2027, 1, 30)
    lib = login(client, "lib@library.local", "Librarian123")
    assert get_member(client, lib, g["id"])["membership_valid"] is True
    at(clock, 2027, 1, 31)
    lib = login(client, "lib@library.local", "Librarian123")
    assert get_member(client, lib, g["id"])["membership_valid"] is False


def test_t_mem_05_a(client, librarian, branch_a):
    """T-MEM-05-a (LIB-MEM-05): 409 CONFLICT, details.field university_id"""
    client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"]))
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="other@uni.edu.tr"))
    assert r.status_code == 409 and r.json()["error"]["details"]["field"] == "university_id"


def test_t_mem_06_a(client, librarian, branch_a):
    """T-MEM-06-a (LIB-MEM-06): Işık; Can; Can"""
    register_member(client, librarian, home_branch_id=branch_a["id"], full_name="Işık Demir")
    register_member(client, librarian, home_branch_id=branch_a["id"], full_name="Can Kaya", membership_type="guest")
    q = lambda **p: [m["full_name"] for m in client.get("/api/v1/members", headers=librarian, params=p).json()["items"]]
    assert q(q="ISIK") == ["Işık Demir"]
    assert q(membership_type="guest") == ["Can Kaya"]
    assert q(q="M000002") == ["Can Kaya"]


def test_t_mem_07_a(client, librarian, branch_a):
    """T-MEM-07-a (LIB-MEM-07): 200; user account login works with the new e-mail and shows the new name"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"email": "new@uni.edu.tr", "full_name": "New Name"})
    assert r.status_code == 200 and r.json()["valid_until"] == m["valid_until"]
    me = client.get("/api/v1/auth/me", headers=login(client, "new@uni.edu.tr", "Member1234")).json()
    assert me["full_name"] == "New Name"


def test_t_mem_08_a(client, clock, librarian, branch_a):
    """T-MEM-08-a (LIB-MEM-08): Old loan unchanged (due 2026-11-16, 2.00 TL); new loan due 2026-12-03, 1.00 TL"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    book = create_book(client, librarian)
    c1 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    l1 = lend(client, librarian, m["id"], c1["id"])
    client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "academic"})
    at(clock, 2026, 11, 3)
    lib = login(client, "lib@library.local", "Librarian123")
    l2 = lend(client, lib, m["id"], c2["id"])
    old = client.get(f"/api/v1/loans/{l1['id']}", headers=lib).json()
    assert old["due_date"] == "2026-11-16" and D(old["daily_fee"]) == D("2.00")
    assert l2["due_date"] == "2026-12-03" and D(l2["daily_fee"]) == D("1.00")


def test_t_mem_09_a(client, librarian, branch_a):
    """T-MEM-09-a (LIB-MEM-09): 2028-10-31 (+365 days); guest 2027-04-30 (+90)"""
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    r = client.post(f"/api/v1/members/{s['id']}/renew-membership", headers=librarian)
    assert r.status_code == 200 and r.json()["valid_until"] == "2028-10-31"
    assert client.post(f"/api/v1/members/{g['id']}/renew-membership", headers=librarian).json()["valid_until"] == "2027-04-30"


def test_t_mem_09_c(client, librarian, branch_a):
    """T-MEM-09-c (LIB-MEM-09): 409 MEMBER_PASSIVE"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/renew-membership", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"


def test_t_mem_10_a(client, librarian, branch_a):
    """T-MEM-10-a (LIB-MEM-10): 409 MEMBER_HAS_OPEN_LOANS"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    book = create_book(client, librarian)
    lend(client, librarian, m["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    r = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_HAS_OPEN_LOANS"


def test_t_mem_10_c(client, librarian, branch_a):
    """T-MEM-10-c (LIB-MEM-10): 409 MEMBER_PASSIVE"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"


def test_t_mem_11_a(client, librarian, branch_a):
    """T-MEM-11-a (LIB-MEM-11): 200 active; valid_until unchanged"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/activate", headers=librarian)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["valid_until"] == m["valid_until"]


def test_t_mem_12_a(client, librarian, branch_a):
    """T-MEM-12-a (LIB-MEM-12): open_loans 0, overdue_loans 0, active_reservations 0, total_debt '0.00', borrowing eligible with no reasons"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    s = client.get(f"/api/v1/members/{m['id']}/summary", headers=librarian).json()
    assert s["member"]["id"] == m["id"]
    assert (s["open_loans"], s["overdue_loans"], s["active_reservations"]) == (0, 0, 0)
    assert s["balance"]["total_debt"] == "0.00" and s["balance"]["blocked"] is False
    assert s["borrowing"] == {"eligible": True, "reasons": []}


def test_t_mem_12_c(client, librarian, branch_a):
    """T-MEM-12-c (LIB-MEM-12): 403 FORBIDDEN"""
    a = register_member(client, librarian, home_branch_id=branch_a["id"])
    b = register_member(client, librarian, home_branch_id=branch_a["id"])
    assert client.get(f"/api/v1/members/{b['id']}/summary", headers=member_headers(client, a)).status_code == 403


def test_t_mem_13_a(client, librarian, branch_a):
    """T-MEM-13-a (LIB-MEM-13): Own MemberOut"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.get("/api/v1/members/me", headers=member_headers(client, m))
    assert r.status_code == 200 and r.json()["id"] == m["id"]
