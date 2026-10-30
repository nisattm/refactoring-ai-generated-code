MODULE = "members"
TITLE = "module 3 (Members)"

HEADER = '''
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
'''


CASES = [
    dict(id="T-MEM-01-a", req="LIB-MEM-01", type="Normal", input="Register student Ayşe Yılmaz on 2026-11-02", expected="201 `MemberOut`: `member_no` `M000001`, `status` `active`, `membership_valid` true; user account can log in with role `member`", code='''
def TEST(client, librarian, branch_a):
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"]))
    assert r.status_code == 201
    m = r.json()
    assert m["member_no"] == "M000001" and m["status"] == "active" and m["membership_valid"] is True
    assert "user_id" not in m
    me = client.get("/api/v1/auth/me", headers=login(client, "ayse@uni.edu.tr", "Member1234")).json()
    assert me["role"] == "member" and me["member_id"] == m["id"] and me["full_name"] == "Ayşe Yılmaz"
'''),
    dict(id="T-MEM-01-b", req="LIB-MEM-01", type="Error", input="Registration by a member; password `short1`", expected="`403 FORBIDDEN`; `422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    other = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.post("/api/v1/members", headers=member_headers(client, other), json=payload(branch_a["id"]))
    assert r.status_code == 403
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], password="short1"))
    assert r.status_code == 422
'''),
    dict(id="T-MEM-02-a", req="LIB-MEM-02", type="Error", input="Guest without `phone`; guest with `university_id`", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, librarian, branch_a):
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="guest", university_id=...))
    assert r.status_code == 422
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="guest", phone="+90 532 000 0000"))
    assert r.status_code == 422
'''),
    dict(id="T-MEM-02-b", req="LIB-MEM-02", type="Error", input="Academic without `university_id`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, librarian, branch_a):
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], membership_type="academic", university_id=...))
    assert r.status_code == 422
'''),
    dict(id="T-MEM-02-c", req="LIB-MEM-02", type="Boundary", input="Guest with phone of 10 digits, 15 digits; 9 and 16 digits; `university_id` of 3 and 21 characters", expected="10 and 15 accepted; the others `422`", code='''
def TEST(client, librarian, branch_a):
    base = dict(membership_type="guest", university_id=...)
    assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="g1@x.com", phone="5320000000", **base)).status_code == 201
    assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="g2@x.com", phone="+905320000000123", **base)).status_code == 201
    for i, ph in enumerate(("532000000", "+9053200000001234")):
        assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email=f"g3{i}@x.com", phone=ph, **base)).status_code == 422
    for i, uid in enumerate(("ABC", "A" * 21)):
        assert client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email=f"s{i}@x.com", university_id=uid)).status_code == 422
'''),
    dict(id="T-MEM-03-a", req="LIB-MEM-03", type="Normal", input="Student and guest registered 2026-11-02", expected="`membership_start` 2026-11-02; `valid_until` 2027-11-01 and 2027-01-30", code='''
def TEST(client, librarian, branch_a):
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    assert s["membership_start"] == "2026-11-02" and s["valid_until"] == "2027-11-01"
    assert g["valid_until"] == "2027-01-30"
'''),
    dict(id="T-MEM-04-a", req="LIB-MEM-04", type="Boundary", input="Guest registered 2026-11-02; read on 2027-01-30 and 2027-01-31", expected="`membership_valid` true, then false", code='''
def TEST(client, clock, librarian, branch_a):
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    at(clock, 2027, 1, 30)
    lib = login(client, "lib@library.local", "Librarian123")
    assert get_member(client, lib, g["id"])["membership_valid"] is True
    at(clock, 2027, 1, 31)
    lib = login(client, "lib@library.local", "Librarian123")
    assert get_member(client, lib, g["id"])["membership_valid"] is False
'''),
    dict(id="T-MEM-04-b", req="LIB-MEM-04", type="Normal", input="Active, unexpired member is deactivated", expected="`membership_valid` false", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    out = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian).json()
    assert out["status"] == "passive" and out["membership_valid"] is False
'''),
    dict(id="T-MEM-05-a", req="LIB-MEM-05", type="Error", input="Second member with the same `university_id`", expected="`409 CONFLICT`, `details.field` `university_id`", code='''
def TEST(client, librarian, branch_a):
    client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"]))
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="other@uni.edu.tr"))
    assert r.status_code == 409 and r.json()["error"]["details"]["field"] == "university_id"
'''),
    dict(id="T-MEM-05-b", req="LIB-MEM-05", type="Error", input="Member e-mail equal to the librarian's e-mail (different case)", expected="`409 CONFLICT`, `details.field` `email`", code='''
def TEST(client, librarian, branch_a):
    r = client.post("/api/v1/members", headers=librarian, json=payload(branch_a["id"], email="LIB@library.local"))
    assert r.status_code == 409 and r.json()["error"]["details"]["field"] == "email"
'''),
    dict(id="T-MEM-06-a", req="LIB-MEM-06", type="Normal", input="Members Işık (student), Can (guest); filters `q=ISIK`, `membership_type=guest`, `q=M000002`", expected="Işık; Can; Can", code='''
def TEST(client, librarian, branch_a):
    register_member(client, librarian, home_branch_id=branch_a["id"], full_name="Işık Demir")
    register_member(client, librarian, home_branch_id=branch_a["id"], full_name="Can Kaya", membership_type="guest")
    q = lambda **p: [m["full_name"] for m in client.get("/api/v1/members", headers=librarian, params=p).json()["items"]]
    assert q(q="ISIK") == ["Işık Demir"]
    assert q(membership_type="guest") == ["Can Kaya"]
    assert q(q="M000002") == ["Can Kaya"]
'''),
    dict(id="T-MEM-06-b", req="LIB-MEM-06", type="Normal", input="One expired guest, one valid student; filter `membership_valid=false`; ordering", expected="Only the guest; list ordered by `id`", code='''
def TEST(client, clock, librarian, branch_a):
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    register_member(client, librarian, home_branch_id=branch_a["id"])
    at(clock, 2027, 2, 1)
    lib = login(client, "lib@library.local", "Librarian123")
    items = client.get("/api/v1/members", headers=lib, params={"membership_valid": "false"}).json()["items"]
    assert [m["id"] for m in items] == [g["id"]]
    ids = [m["id"] for m in client.get("/api/v1/members", headers=lib).json()["items"]]
    assert ids == sorted(ids)
'''),
    dict(id="T-MEM-07-a", req="LIB-MEM-07", type="Normal", input="PATCH `email` and `full_name`", expected="200; user account login works with the new e-mail and shows the new name", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"email": "new@uni.edu.tr", "full_name": "New Name"})
    assert r.status_code == 200 and r.json()["valid_until"] == m["valid_until"]
    me = client.get("/api/v1/auth/me", headers=login(client, "new@uni.edu.tr", "Member1234")).json()
    assert me["full_name"] == "New Name"
'''),
    dict(id="T-MEM-07-b", req="LIB-MEM-07", type="Error", input="PATCH a guest: `university_id` only (type stays guest)", expected="`409 MEMBER_FIELDS_INVALID`", code='''
def TEST(client, librarian, branch_a):
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    r = client.patch(f"/api/v1/members/{g['id']}", headers=librarian, json={"university_id": "U5555"})
    assert r.status_code == 409 and error_code(r) == "MEMBER_FIELDS_INVALID"
'''),
    dict(id="T-MEM-08-a", req="LIB-MEM-08", type="Normal", input="Student with an open loan (due 2026-11-16) becomes academic; new loan on 2026-11-03", expected="Old loan unchanged (due 2026-11-16, 2.00 TL); new loan due 2026-12-03, 1.00 TL", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MEM-08-b", req="LIB-MEM-08", type="Normal", input="Student → guest with `phone`; guest → staff without `university_id`", expected="First 200 with `university_id` null; second `409 MEMBER_FIELDS_INVALID`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "5320000000"})
    assert r.status_code == 200 and r.json()["university_id"] is None
    r = client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "staff"})
    assert r.status_code == 409 and error_code(r) == "MEMBER_FIELDS_INVALID"
'''),
    dict(id="T-MEM-09-a", req="LIB-MEM-09", type="Normal", input="Student (valid until 2027-11-01) renewed on 2026-11-02; guest renewed the same day", expected="2028-10-31 (+365 days); guest 2027-04-30 (+90)", code='''
def TEST(client, librarian, branch_a):
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    r = client.post(f"/api/v1/members/{s['id']}/renew-membership", headers=librarian)
    assert r.status_code == 200 and r.json()["valid_until"] == "2028-10-31"
    assert client.post(f"/api/v1/members/{g['id']}/renew-membership", headers=librarian).json()["valid_until"] == "2027-04-30"
'''),
    dict(id="T-MEM-09-b", req="LIB-MEM-09", type="Boundary", input="Guest (valid until 2027-01-30) renewed on 2027-01-30 and another on 2027-02-15", expected="2027-04-30 (+90); 2027-05-15 (today + 89)", code='''
def TEST(client, clock, librarian, branch_a):
    g1 = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    g2 = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    at(clock, 2027, 1, 30)
    lib = login(client, "lib@library.local", "Librarian123")
    assert client.post(f"/api/v1/members/{g1['id']}/renew-membership", headers=lib).json()["valid_until"] == "2027-04-30"
    at(clock, 2027, 2, 15)
    lib = login(client, "lib@library.local", "Librarian123")
    assert client.post(f"/api/v1/members/{g2['id']}/renew-membership", headers=lib).json()["valid_until"] == "2027-05-15"
'''),
    dict(id="T-MEM-09-c", req="LIB-MEM-09", type="Error", input="Renew a passive member", expected="`409 MEMBER_PASSIVE`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/renew-membership", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"
'''),
    dict(id="T-MEM-10-a", req="LIB-MEM-10", type="Error", input="Deactivate a member with an open loan", expected="`409 MEMBER_HAS_OPEN_LOANS`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    book = create_book(client, librarian)
    lend(client, librarian, m["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    r = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_HAS_OPEN_LOANS"
'''),
    dict(id="T-MEM-10-b", req="LIB-MEM-10", type="Normal", input="Member with an unpaid late fee (no open loan) and a waiting reservation is deactivated", expected="200 `passive`; reservation `cancelled` with `member_deactivated`; member can still log in", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-MEM-10-c", req="LIB-MEM-10", type="Error", input="Deactivate a passive member", expected="`409 MEMBER_PASSIVE`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_PASSIVE"
'''),
    dict(id="T-MEM-11-a", req="LIB-MEM-11", type="Normal", input="Activate a passive member", expected="200 `active`; `valid_until` unchanged", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian)
    r = client.post(f"/api/v1/members/{m['id']}/activate", headers=librarian)
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["valid_until"] == m["valid_until"]
'''),
    dict(id="T-MEM-11-b", req="LIB-MEM-11", type="Error", input="Activate an active member", expected="`409 MEMBER_ALREADY_ACTIVE`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.post(f"/api/v1/members/{m['id']}/activate", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "MEMBER_ALREADY_ACTIVE"
'''),
    dict(id="T-MEM-12-a", req="LIB-MEM-12", type="Normal", input="New member without loans", expected="`open_loans` 0, `overdue_loans` 0, `active_reservations` 0, `total_debt` `\"0.00\"`, `borrowing` eligible with no reasons", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    s = client.get(f"/api/v1/members/{m['id']}/summary", headers=librarian).json()
    assert s["member"]["id"] == m["id"]
    assert (s["open_loans"], s["overdue_loans"], s["active_reservations"]) == (0, 0, 0)
    assert s["balance"]["total_debt"] == "0.00" and s["balance"]["blocked"] is False
    assert s["borrowing"] == {"eligible": True, "reasons": []}
'''),
    dict(id="T-MEM-12-b", req="LIB-MEM-12", type="Boundary", input="Guest with 2 open loans from 2026-11-02 (both overdue, accrued fees capped at 100.00 each); read on 2027-01-31 after the membership expired", expected="`reasons` = [`MEMBERSHIP_EXPIRED`, `MEMBER_HAS_OVERDUE`, `MEMBER_BLOCKED_BY_DEBT`, `LOAN_LIMIT_REACHED`] in this order; not eligible", code='''
def TEST(client, clock, librarian, branch_a):
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    book = create_book(client, librarian)
    for _ in range(2):
        lend(client, librarian, g["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    at(clock, 2027, 1, 31)
    lib = login(client, "lib@library.local", "Librarian123")
    s = client.get(f"/api/v1/members/{g['id']}/summary", headers=lib).json()
    assert s["open_loans"] == 2 and s["overdue_loans"] == 2
    assert s["borrowing"] == {"eligible": False, "reasons": ["MEMBERSHIP_EXPIRED", "MEMBER_HAS_OVERDUE", "MEMBER_BLOCKED_BY_DEBT", "LOAN_LIMIT_REACHED"]}
'''),
    dict(id="T-MEM-12-c", req="LIB-MEM-12", type="Error", input="Member reads another member's summary", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian, branch_a):
    a = register_member(client, librarian, home_branch_id=branch_a["id"])
    b = register_member(client, librarian, home_branch_id=branch_a["id"])
    assert client.get(f"/api/v1/members/{b['id']}/summary", headers=member_headers(client, a)).status_code == 403
'''),
    dict(id="T-MEM-13-a", req="LIB-MEM-13", type="Normal", input="Member calls `GET /api/v1/members/me`", expected="Own `MemberOut`", code='''
def TEST(client, librarian, branch_a):
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    r = client.get("/api/v1/members/me", headers=member_headers(client, m))
    assert r.status_code == 200 and r.json()["id"] == m["id"]
'''),
    dict(id="T-MEM-13-b", req="LIB-MEM-13", type="Error", input="Librarian (no linked member) calls `/members/me`", expected="`404 NOT_FOUND`", code='''
def TEST(client, librarian):
    r = client.get("/api/v1/members/me", headers=librarian)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
'''),
]
