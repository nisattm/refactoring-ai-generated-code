"""Heldout tests: module 10 (Reports). Generated from cases/reports.md."""
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


def test_t_rep_01_b(client, librarian, branch_a, branch_b):
    """T-REP-01-b (LIB-REP-01): 200; 422; 422; 422; only the loan at B counts"""
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


def test_t_rep_02_b(client, clock, librarian, branch_a, branch_b):
    """T-REP-02-b (LIB-REP-02): Only the loan at B; total_accrued covers all matching rows, not only the page"""
    k = create_book(client, librarian)
    lend_new(client, librarian, k["id"], branch_a["id"])
    _, _, lb = lend_new(client, librarian, k["id"], branch_b["id"])
    lend_new(client, librarian, k["id"], branch_b["id"])
    lib = at(client, clock, 2026, 11, 20)
    only_b = get(client, lib, "overdue", branch_id=branch_b["id"], page_size=1)
    assert only_b["total"] == 2 and len(only_b["items"]) == 1 and only_b["items"][0]["loan_id"] == lb["id"]
    assert only_b["total_accrued"] == "16.00"


def test_t_rep_03_b(client, librarian):
    """T-REP-03-b (LIB-REP-03): 422 VALIDATION_ERROR each"""
    for y, m in ((2026, 12), (2026, 13), (2026, 0)):
        assert client.get("/api/v1/reports/monthly-summary", headers=librarian, params={"year": y, "month": m}).status_code == 422


def test_t_rep_04_a(client, librarian, branch_a, branch_b):
    """T-REP-04-a (LIB-REP-04): Rows (A, available, 2), (A, damaged, 1), (B, available, 1), (null, in_transfer, 1), (null, lost, 1) in this order"""
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


def test_t_rep_05_b(client, clock, librarian, branch_a):
    """T-REP-05-b (LIB-REP-05): Header plus all three rows (no pagination)"""
    k = create_book(client, librarian)
    for _ in range(3):
        lend_new(client, librarian, k["id"], branch_a["id"])
    lib = at(client, clock, 2026, 11, 20)
    r = client.get("/api/v1/reports/overdue", headers=lib, params={"format": "csv", "page_size": 1})
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    assert rows[0][:3] == ["loan_id", "member_id", "member_no"] and len(rows) == 4
