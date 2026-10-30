MODULE = "reports"
TITLE = "module 10 (Reports)"

HEADER = '''
import csv
import io
from datetime import datetime, timedelta, timezone

from support.api import (
    D, add_copy, create_book, lend, login, member_headers, register_member, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))
LIB = ("lib@library.local", "Librarian123")


def at(client, clock, y, m, d, hour=10):
    clock.set(datetime(y, m, d, hour, 0, tzinfo=TR))
    return login(client, *LIB)


def lend_new(client, lib, book_id, branch_id, member=None, **member_kw):
    m = member or register_member(client, lib, home_branch_id=branch_id, **member_kw)
    c = add_copy(client, lib, book_id, home_branch_id=branch_id)
    return m, c, lend(client, lib, m["id"], c["id"])


def get(client, headers, path, **params):
    r = client.get(f"/api/v1/reports/{path}", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()
'''


CASES = [
    dict(id="T-REP-01-a", req="LIB-REP-01", type="Normal", input="November loans: `Zeta` 2, `Alfa` 2, `Beta` 1, `Delta` 0; range 2026-11-01 – 2026-11-30", expected="Alfa (rank 1), Zeta (2), Beta (3); Delta omitted; `limit=2` returns the first two", code='''
def TEST(client, librarian, branch_a):
    books = {t: create_book(client, librarian, title=t) for t in ("Zeta", "Alfa", "Beta", "Delta")}
    for t, n in (("Zeta", 2), ("Alfa", 2), ("Beta", 1)):
        for _ in range(n):
            lend_new(client, librarian, books[t]["id"], branch_a["id"])
    body = get(client, librarian, "most-borrowed", **{"from": "2026-11-01", "to": "2026-11-30"})
    assert [(i["rank"], i["title"], i["loan_count"]) for i in body["items"]] == [(1, "Alfa", 2), (2, "Zeta", 2), (3, "Beta", 1)]
    assert body["from"] == "2026-11-01" and body["to"] == "2026-11-30" and body["branch_id"] is None
    limited = get(client, librarian, "most-borrowed", **{"from": "2026-11-01", "to": "2026-11-30", "limit": 2})
    assert [i["title"] for i in limited["items"]] == ["Alfa", "Zeta"]
'''),
    dict(id="T-REP-01-b", req="LIB-REP-01", type="Boundary", input="Ranges 365 days (2026-01-01 – 2027-01-01) and 366 days; `from` > `to`; `limit` 0 and 101; loans at A and B with `branch_id=B`", expected="200; `422`; `422`; `422`; only the loan at B counts", code='''
def TEST(client, librarian, branch_a, branch_b):
    q = lambda **p: client.get("/api/v1/reports/most-borrowed", headers=librarian, params=p)
    assert q(**{"from": "2026-01-01", "to": "2027-01-01"}).status_code == 200
    assert q(**{"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert q(**{"from": "2026-11-30", "to": "2026-11-01"}).status_code == 422
    for lim in (0, 101):
        assert q(**{"from": "2026-11-01", "to": "2026-11-30", "limit": lim}).status_code == 422
    b = create_book(client, librarian, title="Only")
    lend_new(client, librarian, b["id"], branch_a["id"])
    lend_new(client, librarian, b["id"], branch_b["id"])
    items = q(**{"from": "2026-11-01", "to": "2026-11-30", "branch_id": branch_b["id"]}).json()["items"]
    assert [(i["title"], i["loan_count"]) for i in items] == [("Only", 1)]
'''),
    dict(id="T-REP-01-c", req="LIB-REP-01", type="Error", input="Member requests a report", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian, branch_a):
    mh = member_headers(client, register_member(client, librarian, home_branch_id=branch_a["id"]))
    r = client.get("/api/v1/reports/most-borrowed", headers=mh, params={"from": "2026-11-01", "to": "2026-11-30"})
    assert r.status_code == 403
'''),
    dict(id="T-REP-02-a", req="LIB-REP-02", type="Normal", input="On 2026-11-20: guest loan due 2026-11-09 (9 late days, 45.00) and student loan due 2026-11-16 (4 late days, 8.00); one returned loan", expected="Two rows ordered by due date; `total_accrued` `\"53.00\"`; all documented fields", code='''
def TEST(client, clock, librarian, branch_a):
    k = create_book(client, librarian, title="Kitap")
    g, _, lg = lend_new(client, librarian, k["id"], branch_a["id"], membership_type="guest")
    s, _, ls = lend_new(client, librarian, k["id"], branch_a["id"])
    _, _, done = lend_new(client, librarian, k["id"], branch_a["id"])
    lib = at(client, clock, 2026, 11, 20)
    return_loan(client, lib, done["id"], branch_id=branch_a["id"])
    body = get(client, lib, "overdue")
    rows = body["items"]
    assert [(r["loan_id"], r["due_date"], r["late_days"], r["accrued_late_fee"]) for r in rows] == [
        (lg["id"], "2026-11-09", 9, "45.00"), (ls["id"], "2026-11-16", 4, "8.00")]
    assert body["total_accrued"] == "53.00"
    assert set(rows[0]) >= {"loan_id", "member_id", "member_no", "member_name", "book_id", "title", "copy_barcode", "due_date", "late_days", "accrued_late_fee"}
    assert rows[0]["title"] == "Kitap" and rows[0]["member_no"] == g["member_no"]
'''),
    dict(id="T-REP-02-b", req="LIB-REP-02", type="Normal", input="Overdue loans at A and B; `branch_id=B`; `page_size=1`", expected="Only the loan at B; `total_accrued` covers all matching rows, not only the page", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    k = create_book(client, librarian)
    lend_new(client, librarian, k["id"], branch_a["id"])
    _, _, lb = lend_new(client, librarian, k["id"], branch_b["id"])
    lend_new(client, librarian, k["id"], branch_b["id"])
    lib = at(client, clock, 2026, 11, 20)
    only_b = get(client, lib, "overdue", branch_id=branch_b["id"], page_size=1)
    assert only_b["total"] == 2 and len(only_b["items"]) == 1 and only_b["items"][0]["loan_id"] == lb["id"]
    assert only_b["total_accrued"] == "16.00"
'''),
    dict(id="T-REP-03-a", req="LIB-REP-03", type="Normal", input="Activity in October and November 2026 (one member in October; in November 2 members, 3 loans, 2 returns with 4.00 fees, 1 payment 4.00, 1 waiver 4.00, 1 lost copy (100.00 + 25.00), 1 reservation that expires)", expected="November: new_members 2, loans_created 3, loans_returned 2, loans_lost 1, reservations created 1 / fulfilled 0 / expired 1, fees_created 133.00, payments 4.00, waived 4.00; October: new_members 1, everything else 0", code='''
def TEST(client, clock, librarian, admin, branch_a):
    lib = at(client, clock, 2026, 10, 30)
    m0 = register_member(client, lib, home_branch_id=branch_a["id"])
    lib = at(client, clock, 2026, 11, 2)
    m1 = register_member(client, lib, home_branch_id=branch_a["id"])
    m2 = register_member(client, lib, home_branch_id=branch_a["id"])
    k1, k2 = create_book(client, lib, title="K1"), create_book(client, lib, title="K2")
    c1 = add_copy(client, lib, k1["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, lib, k1["id"], home_branch_id=branch_a["id"])
    c3 = add_copy(client, lib, k2["id"], home_branch_id=branch_a["id"])
    l1 = lend(client, lib, m1["id"], c1["id"])
    l3 = lend(client, lib, m2["id"], c3["id"])
    reserve(client, lib, book_id=k2["id"], pickup_branch_id=branch_a["id"], member_id=m0["id"])
    lib = at(client, clock, 2026, 11, 18)
    return_loan(client, lib, l1["id"], branch_id=branch_a["id"])
    assert client.post(f"/api/v1/members/{m1['id']}/payments", headers=lib, json={"amount": "4.00", "method": "cash"}).status_code == 201
    return_loan(client, lib, l3["id"], branch_id=branch_a["id"])
    fee = client.get(f"/api/v1/members/{m2['id']}/fees", headers=lib).json()["items"][0]
    adm = login(client, "admin@library.local", "ChangeMe123")
    assert client.post(f"/api/v1/fees/{fee['id']}/waive", headers=adm, json={"reason": "Goodwill gesture"}).status_code == 200
    l2 = lend(client, lib, m1["id"], c2["id"])
    lib = at(client, clock, 2026, 11, 20)
    assert client.post(f"/api/v1/loans/{l2['id']}/report-lost", headers=lib).status_code == 200
    lib = at(client, clock, 2026, 11, 24)
    client.post("/api/v1/reservations/process-expired", headers=lib)
    nov = get(client, lib, "monthly-summary", year=2026, month=11)
    assert {k: nov[k] for k in ("new_members", "loans_created", "loans_returned", "loans_lost", "reservations_created", "reservations_fulfilled", "reservations_expired")} == {
        "new_members": 2, "loans_created": 3, "loans_returned": 2, "loans_lost": 1, "reservations_created": 1, "reservations_fulfilled": 0, "reservations_expired": 1}
    assert (nov["fees_created"], nov["payments_received"], nov["fees_waived"]) == ("133.00", "4.00", "4.00")
    octo = get(client, lib, "monthly-summary", year=2026, month=10)
    assert octo["new_members"] == 1 and octo["loans_created"] == 0 and octo["fees_created"] == "0.00"
'''),
    dict(id="T-REP-03-b", req="LIB-REP-03", type="Error", input="On 2026-11-02: December 2026; `month=13`; `month=0`", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, librarian):
    for y, m in ((2026, 12), (2026, 13), (2026, 0)):
        assert client.get("/api/v1/reports/monthly-summary", headers=librarian, params={"year": y, "month": m}).status_code == 422
'''),
    dict(id="T-REP-04-a", req="LIB-REP-04", type="Normal", input="A: 2 available, 1 damaged; B: 1 available; 1 copy in transfer; 1 lost copy", expected="Rows (A, available, 2), (A, damaged, 1), (B, available, 1), (null, in_transfer, 1), (null, lost, 1) in this order", code='''
def TEST(client, librarian, branch_a, branch_b):
    k = create_book(client, librarian)
    for _ in range(2):
        add_copy(client, librarian, k["id"], home_branch_id=branch_a["id"])
    add_copy(client, librarian, k["id"], home_branch_id=branch_b["id"])
    _, cd, ld = lend_new(client, librarian, k["id"], branch_a["id"])
    return_loan(client, librarian, ld["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="10.00")
    _, cl, ll = lend_new(client, librarian, k["id"], branch_a["id"])
    client.post(f"/api/v1/loans/{ll['id']}/report-lost", headers=librarian)
    moving = add_copy(client, librarian, k["id"], home_branch_id=branch_a["id"])
    client.post("/api/v1/transfers", headers=librarian, json={"copy_id": moving["id"], "to_branch_id": branch_b["id"]})
    rows = [(r["branch_id"], r["status"], r["copies"]) for r in get(client, librarian, "inventory")["items"]]
    assert rows == [(branch_a["id"], "available", 2), (branch_a["id"], "damaged", 1), (branch_b["id"], "available", 1),
                    (None, "in_transfer", 1), (None, "lost", 1)]
'''),
    dict(id="T-REP-05-a", req="LIB-REP-05", type="Normal", input="`most-borrowed` with `format=csv`", expected="`text/csv; charset=utf-8`; header `rank,book_id,title,isbn,loan_count`; one row per item", code='''
def TEST(client, librarian, branch_a):
    k = create_book(client, librarian, title="Kar, Kış")
    lend_new(client, librarian, k["id"], branch_a["id"])
    r = client.get("/api/v1/reports/most-borrowed", headers=librarian, params={"from": "2026-11-01", "to": "2026-11-30", "format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0] == ["rank", "book_id", "title", "isbn", "loan_count"]
    assert rows[1] == ["1", str(k["id"]), "Kar, Kış", k["isbn"], "1"]
'''),
    dict(id="T-REP-05-b", req="LIB-REP-05", type="Normal", input="Three overdue loans; `overdue` with `format=csv&page_size=1`", expected="Header plus all three rows (no pagination)", code='''
def TEST(client, clock, librarian, branch_a):
    k = create_book(client, librarian)
    for _ in range(3):
        lend_new(client, librarian, k["id"], branch_a["id"])
    lib = at(client, clock, 2026, 11, 20)
    r = client.get("/api/v1/reports/overdue", headers=lib, params={"format": "csv", "page_size": 1})
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0][:3] == ["loan_id", "member_id", "member_no"] and len(rows) == 4
'''),
]
