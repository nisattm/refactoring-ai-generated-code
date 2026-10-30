MODULE = "e2e"
TITLE = "end-to-end scenarios (section 21)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    D, add_copy, create_book, error_code, lend, login, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))
LIB = ("lib@library.local", "Librarian123")
ADMIN = ("admin@library.local", "ChangeMe123")


def at(client, clock, y, m, d, hour=10):
    """Move the clock and return fresh librarian headers (tokens expire after 12 hours)."""
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))
    return login(client, *LIB)


def balance(client, lib, mid):
    return client.get(f"/api/v1/members/{mid}/balance", headers=lib).json()


def pay(client, lib, mid, amount):
    return client.post(f"/api/v1/members/{mid}/payments", headers=lib, json={"amount": amount, "method": "cash"})


def res(client, lib, rid):
    return client.get(f"/api/v1/reservations/{rid}", headers=lib).json()


def copy_status(client, lib, cid):
    return client.get(f"/api/v1/copies/{cid}", headers=lib).json()["status"]


def notes(client, lib, mid, kind):
    return client.get(f"/api/v1/members/{mid}/notifications", headers=lib, params={"type": kind}).json()["items"]
'''


CASES = [
    dict(id="T-E2E-01", req="LIB-E2E-01", type="Scenario", input="Late return and borrowing block (section 21)", expected="Overdue blocks; 25 late days = 50.00 blocks; paying 0.01 allows lending", code='''
def TEST(client, clock, librarian, branch_a):
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    c1 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, s["id"], c1["id"])
    assert loan["due_date"] == "2026-11-16"
    lib = at(client, clock, 2026, 12, 14)
    r = client.post("/api/v1/loans", headers=lib, json={"member_id": s["id"], "copy_id": c2["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBER_HAS_OVERDUE"
    lib = at(client, clock, 2026, 12, 21)
    closed = return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    assert closed["late_days"] == 25
    b = balance(client, lib, s["id"])
    assert b["total_debt"] == "50.00" and b["blocked"] is True
    r = client.post("/api/v1/loans", headers=lib, json={"member_id": s["id"], "copy_id": c2["id"]})
    assert r.status_code == 409 and error_code(r) == "MEMBER_BLOCKED_BY_DEBT"
    assert pay(client, lib, s["id"], "0.01").status_code == 201
    assert balance(client, lib, s["id"])["total_debt"] == "49.99"
    lend(client, lib, s["id"], c2["id"])
'''),
    dict(id="T-E2E-02", req="LIB-E2E-02", type="Scenario", input="Reservation at another branch (section 21)", expected="BOOK_RESERVED on renewal; in transit 20 Nov; not received 23 Nov; ready 24 Nov until 27 Nov; fulfilled on 27 Nov", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    book = create_book(client, librarian)
    c1 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    s1 = register_member(client, librarian, home_branch_id=branch_a["id"])
    s2 = register_member(client, librarian, home_branch_id=branch_b["id"])
    loan = lend(client, librarian, s1["id"], c1["id"])
    r = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_b["id"], member_id=s2["id"])
    assert r["status"] == "waiting" and r["queue_position"] == 1
    lib = at(client, clock, 2026, 11, 10)
    renew = client.post(f"/api/v1/loans/{loan['id']}/renew", headers=lib)
    assert renew.status_code == 409 and error_code(renew) == "BOOK_RESERVED"
    lib = at(client, clock, 2026, 11, 20)
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    assert res(client, lib, r["id"])["status"] == "in_transit"
    assert len(notes(client, lib, s2["id"], "reservation_in_transit")) == 1
    lib = at(client, clock, 2026, 11, 23)
    assert client.post("/api/v1/transfers/process-arrivals", headers=lib).json()["received"] == 0
    lib = at(client, clock, 2026, 11, 24)
    assert client.post("/api/v1/transfers/process-arrivals", headers=lib).json()["received"] == 1
    got = res(client, lib, r["id"])
    assert got["status"] == "ready" and got["hold_until"] == "2026-11-27"
    assert len(notes(client, lib, s2["id"], "reservation_ready")) == 1
    lib = at(client, clock, 2026, 11, 27)
    lend(client, lib, s2["id"], c1["id"])
    assert res(client, lib, r["id"])["status"] == "fulfilled"
'''),
    dict(id="T-E2E-03", req="LIB-E2E-03", type="Scenario", input="Hold expires and passes on (section 21)", expected="S1 ready until 3 Nov; on 4 Nov S1 expired, S2 ready until 9 Nov; C1 on hold; lending to S1 COPY_ON_HOLD", code='''
def TEST(client, clock, librarian, branch_a):
    lib = at(client, clock, 2026, 10, 20)
    book = create_book(client, lib)
    c1 = add_copy(client, lib, book["id"], home_branch_id=branch_a["id"])
    s3 = register_member(client, lib, home_branch_id=branch_a["id"])
    s1 = register_member(client, lib, home_branch_id=branch_a["id"])
    s2 = register_member(client, lib, home_branch_id=branch_a["id"])
    loan = lend(client, lib, s3["id"], c1["id"])
    r1 = reserve(client, lib, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=s1["id"])
    r2 = reserve(client, lib, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    lib = at(client, clock, 2026, 10, 28)
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    assert res(client, lib, r1["id"])["hold_until"] == "2026-11-03"
    lib = at(client, clock, 2026, 11, 4)
    client.post("/api/v1/reservations/process-expired", headers=lib)
    assert res(client, lib, r1["id"])["status"] == "expired"
    assert len(notes(client, lib, s1["id"], "reservation_expired")) == 1
    got = res(client, lib, r2["id"])
    assert got["status"] == "ready" and got["hold_until"] == "2026-11-09"
    assert len(notes(client, lib, s2["id"], "reservation_ready")) == 1
    assert copy_status(client, lib, c1["id"]) == "on_hold"
    r = client.post("/api/v1/loans", headers=lib, json={"member_id": s1["id"], "copy_id": c1["id"]})
    assert r.status_code == 409 and error_code(r) == "COPY_ON_HOLD"
'''),
    dict(id="T-E2E-04", req="LIB-E2E-04", type="Scenario", input="Lost book (section 21)", expected="Fees 4.00, 180.00, 25.00; debt 209.00; 209.01 rejected; 209.00 pays all in order; copy withdrawn", code='''
def TEST(client, clock, librarian, admin, branch_a):
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    c1 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"], price="180.00")
    loan = lend(client, librarian, s["id"], c1["id"])
    lib = at(client, clock, 2026, 11, 18)
    assert client.post(f"/api/v1/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    fees = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"]
    assert sorted((f["kind"], f["amount"]) for f in fees) == [("late_fee", "4.00"), ("lost_book", "180.00"), ("lost_processing", "25.00")]
    assert copy_status(client, lib, c1["id"]) == "lost"
    assert balance(client, lib, s["id"])["total_debt"] == "209.00"
    r = pay(client, lib, s["id"], "209.01")
    assert r.status_code == 409 and error_code(r) == "PAYMENT_EXCEEDS_BALANCE"
    p = pay(client, lib, s["id"], "209.00").json()
    order = [f["id"] for f in sorted(fees, key=lambda f: (f["created_on"], f["id"]))]
    assert [a["fee_id"] for a in p["allocations"]] == order
    fees = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"]
    assert {f["status"] for f in fees} == {"paid"}
    adm = login(client, *ADMIN)
    r = client.post(f"/api/v1/copies/{c1['id']}/withdraw", headers=adm, json={"reason": "Lost by member"})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
'''),
    dict(id="T-E2E-05", req="LIB-E2E-05", type="Scenario", input="Renewal limits by type (section 21)", expected="Guest: RENEWAL_LIMIT_REACHED; academic: 2 Dec → 21 Dec → 31 Dec; third renewal RENEWAL_LIMIT_REACHED", code='''
def TEST(client, clock, librarian, branch_a):
    book = create_book(client, librarian)
    g = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="guest")
    a1 = register_member(client, librarian, home_branch_id=branch_a["id"], membership_type="academic")
    lg = lend(client, librarian, g["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    la = lend(client, librarian, a1["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    assert lg["due_date"] == "2026-11-09" and la["due_date"] == "2026-12-02"
    r = client.post(f"/api/v1/loans/{lg['id']}/renew", headers=librarian)
    assert r.status_code == 409 and error_code(r) == "RENEWAL_LIMIT_REACHED"
    lib = at(client, clock, 2026, 11, 20)
    assert client.post(f"/api/v1/loans/{la['id']}/renew", headers=lib).json()["due_date"] == "2026-12-21"
    lib = at(client, clock, 2026, 12, 1)
    assert client.post(f"/api/v1/loans/{la['id']}/renew", headers=lib).json()["due_date"] == "2026-12-31"
    lib = at(client, clock, 2026, 12, 10)
    r = client.post(f"/api/v1/loans/{la['id']}/renew", headers=lib)
    assert r.status_code == 409 and error_code(r) == "RENEWAL_LIMIT_REACHED"
'''),
    dict(id="T-E2E-06", req="LIB-E2E-06", type="Scenario", input="Type change keeps open loan terms (section 21)", expected="Old loan due 16 Nov at 2.00; new loan on 3 Nov due 3 Dec at 1.00", code='''
def TEST(client, clock, librarian, branch_a):
    book = create_book(client, librarian)
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    l1 = lend(client, librarian, s["id"], add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])["id"])
    c2 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"])
    assert client.patch(f"/api/v1/members/{s['id']}", headers=librarian, json={"membership_type": "academic"}).status_code == 200
    lib = at(client, clock, 2026, 11, 3)
    old = client.get(f"/api/v1/loans/{l1['id']}", headers=lib).json()
    assert old["due_date"] == "2026-11-16" and D(old["daily_fee"]) == D("2.00")
    l2 = lend(client, lib, s["id"], c2["id"])
    assert l2["due_date"] == "2026-12-03" and l2["loan_period_days"] == 30 and D(l2["daily_fee"]) == D("1.00")
'''),
    dict(id="T-E2E-07", req="LIB-E2E-07", type="Scenario", input="Damaged return and repair (section 21)", expected="130.00 rejected (DAMAGE_FEE_EXCEEDS_PRICE); 40.00 accepted, copy damaged, reservation waiting; repair → ready until 11 Nov", code='''
def TEST(client, clock, librarian, branch_a):
    book = create_book(client, librarian)
    c1 = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="120.00")
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    s2 = register_member(client, librarian, home_branch_id=branch_a["id"])
    loan = lend(client, librarian, s["id"], c1["id"])
    r2 = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=s2["id"])
    lib = at(client, clock, 2026, 11, 5)
    r = client.post(f"/api/v1/loans/{loan['id']}/return", headers=lib, json={"branch_id": branch_a["id"], "condition": "damaged", "damage_fee": "130.00"})
    assert r.status_code == 409 and error_code(r) == "DAMAGE_FEE_EXCEEDS_PRICE"
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="40.00")
    fees = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"]
    assert [(f["kind"], f["amount"]) for f in fees] == [("damage_fee", "40.00")]
    assert copy_status(client, lib, c1["id"]) == "damaged"
    assert res(client, lib, r2["id"])["status"] == "waiting"
    lib = at(client, clock, 2026, 11, 6)
    client.post(f"/api/v1/copies/{c1['id']}/repair", headers=lib)
    got = res(client, lib, r2["id"])
    assert got["status"] == "ready" and got["hold_until"] == "2026-11-11"
'''),
    dict(id="T-E2E-08", req="LIB-E2E-08", type="Scenario", input="Waiver by admin only (section 21): late fee 8.00 from a 4-day late return", expected="Librarian 403; admin waives; outstanding fees 8.00 → 0.00", code='''
def TEST(client, clock, librarian, admin, branch_a):
    s = register_member(client, librarian, home_branch_id=branch_a["id"])
    loan = lend(client, librarian, s["id"], add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])["id"])
    lib = at(client, clock, 2026, 11, 20)
    return_loan(client, lib, loan["id"], branch_id=branch_a["id"])
    fee = client.get(f"/api/v1/members/{s['id']}/fees", headers=lib).json()["items"][0]
    assert fee["amount"] == "8.00" and balance(client, lib, s["id"])["outstanding_fees"] == "8.00"
    r = client.post(f"/api/v1/fees/{fee['id']}/waive", headers=lib, json={"reason": "Hospital stay"})
    assert r.status_code == 403
    adm = login(client, *ADMIN)
    r = client.post(f"/api/v1/fees/{fee['id']}/waive", headers=adm, json={"reason": "Hospital stay"})
    assert r.status_code == 200 and r.json()["status"] == "waived"
    assert balance(client, adm, s["id"])["outstanding_fees"] == "0.00"
'''),
    dict(id="T-E2E-09", req="LIB-E2E-09", type="Scenario", input="Purchasing to shelf (section 21)", expected="total 286.50; partially received with 2 copies at 95.50; over-receiving rejected with nothing created; then received", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    sup = client.post("/api/v1/suppliers", headers=librarian, json={"name": "Kitap Dağıtım A.Ş."}).json()
    order = client.post("/api/v1/purchase-orders", headers=librarian, json={
        "supplier_id": sup["id"], "branch_id": branch_a["id"],
        "lines": [{"book_id": book["id"], "quantity": 3, "unit_price": "95.50"}]}).json()
    assert order["status"] == "draft" and order["total"] == "286.50"
    oid, line = order["id"], order["lines"][0]["id"]
    assert client.post(f"/api/v1/purchase-orders/{oid}/submit", headers=librarian).json()["status"] == "ordered"
    r = client.post(f"/api/v1/purchase-orders/{oid}/receive", headers=librarian, json={"lines": [{"line_id": line, "barcodes": ["PO-0001", "PO-0002"]}]})
    assert r.json()["status"] == "partially_received"
    copies = client.get(f"/api/v1/books/{book['id']}/copies", headers=librarian).json()["items"]
    assert [(c["status"], c["price"], c["home_branch_id"]) for c in copies] == [("available", "95.50", branch_a["id"])] * 2
    r = client.post(f"/api/v1/purchase-orders/{oid}/receive", headers=librarian, json={"lines": [{"line_id": line, "barcodes": ["PO-0003", "PO-0004"]}]})
    assert r.status_code == 409 and error_code(r) == "RECEIVE_EXCEEDS_ORDERED"
    assert client.get(f"/api/v1/books/{book['id']}/copies", headers=librarian).json()["total"] == 2
    r = client.post(f"/api/v1/purchase-orders/{oid}/receive", headers=librarian, json={"lines": [{"line_id": line, "barcodes": ["PO-0003"]}]})
    assert r.json()["status"] == "received"
'''),
    dict(id="T-E2E-10", req="LIB-E2E-10", type="Scenario", input="Login lockout (section 21)", expected="Fifth wrong 401; correct password 403 ACCOUNT_LOCKED; after 15 minutes 200", code='''
def TEST(client, clock, librarian):
    for i in range(5):
        r = client.post("/api/v1/auth/login", json={"email": LIB[0], "password": "Wrong0000"})
        assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS", i
    r = client.post("/api/v1/auth/login", json={"email": LIB[0], "password": LIB[1]})
    assert r.status_code == 403 and error_code(r) == "ACCOUNT_LOCKED"
    clock.advance(minutes=15)
    assert client.post("/api/v1/auth/login", json={"email": LIB[0], "password": LIB[1]}).status_code == 200
'''),
    dict(id="T-E2E-11", req="LIB-E2E-11", type="Scenario", input="Import, export, search (section 21) on an empty database", expected="Export equals the imported records; `q=istanbul` finds `İstanbul Hatırası`; imported member login 401", code='''
def TEST(client, admin):
    data = {
        "format_version": 1,
        "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True},
                     {"id": 2, "code": "KAMPUS", "name": "Campus", "address": "", "is_active": True}],
        "authors": [{"id": 1, "name": "Ahmet Ümit"}],
        "publishers": [{"id": 1, "name": "Example Publishing"}],
        "books": [
            {"id": 1, "isbn": "9780306406157", "title": "İstanbul Hatırası", "subtitle": None, "author_ids": [1], "publisher_id": 1, "publication_year": 2010, "language": "tr", "classification": "813.54"},
            {"id": 2, "isbn": "9780140449136", "title": "Beyoğlu Rapsodisi", "subtitle": None, "author_ids": [1], "publisher_id": 1, "publication_year": 2003, "language": "tr", "classification": "813.54"},
            {"id": 3, "isbn": "9791090636071", "title": "Kavim", "subtitle": None, "author_ids": [1], "publisher_id": 1, "publication_year": 2006, "language": "tr", "classification": "813.54"}],
        "copies": [
            {"id": i, "book_id": b, "barcode": f"C00000{i}", "home_branch_id": h, "current_branch_id": h, "price": "150.00",
             "status": "on_loan" if i == 1 else "available", "acquired_on": "2025-09-01", "shelf_location": None}
            for i, b, h in [(1, 1, 1), (2, 1, 2), (3, 2, 1), (4, 3, 1), (5, 3, 2)]],
        "members": [
            {"id": 1, "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr", "phone": None, "membership_type": "student", "university_id": "20231234",
             "home_branch_id": 1, "status": "active", "membership_start": "2026-09-15", "valid_until": "2027-09-14"},
            {"id": 2, "full_name": "John Smith", "email": "john@example.com", "phone": "+905320000000", "membership_type": "guest", "university_id": None,
             "home_branch_id": 2, "status": "active", "membership_start": "2026-10-01", "valid_until": "2026-12-29"}],
        "loans": [{"id": 1, "copy_id": 1, "member_id": 1, "branch_id": 1, "loan_date": "2026-10-26", "due_date": "2026-11-09",
                   "renewal_count": 0, "status": "open", "returned_on": None, "return_branch_id": None}],
    }
    r = client.post("/api/v1/import", headers=admin, json=data)
    assert r.status_code == 200
    assert r.json()["imported"] == {"branches": 2, "authors": 1, "publishers": 1, "books": 3, "copies": 5, "members": 2, "loans": 1}
    assert client.get("/api/v1/export", headers=admin).json() == data
    found = client.get("/api/v1/search/books", headers=admin, params={"q": "istanbul"}).json()["items"]
    assert [i["book"]["title"] for i in found] == ["İstanbul Hatırası"]
    r = client.post("/api/v1/auth/login", json={"email": "ayse@example.edu.tr", "password": "Member1234"})
    assert r.status_code == 401 and error_code(r) == "INVALID_CREDENTIALS"
'''),
]
