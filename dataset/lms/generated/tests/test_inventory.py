"""Module 24: Inventory counts (LIB-INV-01 to LIB-INV-34).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), book 0, a librarian (`lib`) and the admin.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.catalog.models import Copy
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err  # noqa: F401
from tests.test_loans import API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret  # noqa: F401
from tests.test_reservations import arrivals, reserve, res  # noqa: F401
from tests.test_catalog import mk_copy
from tests.test_courses import mk_course, mk_item, world  # noqa: F401


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def shelf_copy(client, hd, book, barcode, shelf, branch=1):
    r = mk_copy(client, hd, book, barcode, branch, shelf_location=shelf)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def start(client, hd, branch=1, name="Autumn count", prefix=None, expect=201, **kw):
    body = {"branch_id": branch, "name": name, **kw}
    if prefix is not None:
        body["shelf_prefix"] = prefix
    r = client.post(f"{API}/inventory-counts", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def scan(client, hd, *barcodes, count=1, expect=201):
    r = client.post(f"{API}/inventory-counts/{count}/scans", headers=hd, json={"barcodes": list(barcodes)})
    assert r.status_code == expect, r.text
    return r.json()


def results(client, hd, count, *barcodes):
    return [s["result"] for s in scan(client, hd, *barcodes, count=count)["scans"]]


def step(client, hd, count, action, expect=200):
    r = client.post(f"{API}/inventory-counts/{count}/{action}", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


def get_count(client, hd, count):
    r = client.get(f"{API}/inventory-counts/{count}", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def shelf(client, lib):
    """Book 0 with copies 1 to 3 at branch 1 on shelves A-12, A-13 and B-01."""
    book = mk_book(client, lib, 0)
    shelf_copy(client, lib, book, "BC-0001", "A-12")
    shelf_copy(client, lib, book, "BC-0002", "A-13")
    shelf_copy(client, lib, book, "BC-0003", "B-01")
    return book


# --- starting ---------------------------------------------------------------------------------------


def test_start_count(client, lib, shelf, app):
    c = start(client, lib, prefix="A-")
    assert c["id"] == 1 and c["branch_id"] == 1 and c["name"] == "Autumn count" and c["shelf_prefix"] == "A-"
    assert c["status"] == "open" and c["cancel_reason"] is None
    assert c["started_at"] == "2026-11-02T09:30:00+03:00" and c["closed_at"] is None and c["applied_at"] is None
    assert c["expected"] == [1, 2] and c["expected_count"] == 2
    assert [a.entity_id for a in audit(app, "inventory_count_started")] == [1]
    whole = start(client, lib, prefix=None, expect=409)
    assert whole["error"]["code"] == "COUNT_SCOPE_OVERLAP"


def test_snapshot_rules(client, lib, shelf, app):
    set_status = lambda copy, status: _set(app, copy, status=status)  # noqa: E731
    set_status(2, "on_loan")
    c = start(client, lib)
    assert c["expected"] == [1, 3]
    for status in ("on_hold", "damaged", "on_reserve"):
        set_status(1, status)
    assert get_count(client, lib, 1)["expected"] == [1, 3]


def _set(app, copy_id, **fields):
    with app.state.session_factory.begin() as s:
        copy = s.get(Copy, copy_id)
        for k, v in fields.items():
            setattr(copy, k, v)


def test_prefix_is_case_insensitive_and_needs_a_shelf(client, lib, shelf, app):
    mk_copy(client, lib, shelf, "BC-0004", 1)  # no shelf location: outside a prefixed count
    assert start(client, lib, prefix="a-1")["expected"] == [1, 2]
    whole = start(client, lib, branch=2, expect=409)
    assert whole["error"]["code"] == "COUNT_EMPTY"


def test_start_validation(client, lib, shelf):
    for body in ({}, {"branch_id": 1}, {"branch_id": 1, "name": " "}, {"branch_id": 1, "name": "x" * 201},
                 {"branch_id": 1, "name": "x", "shelf_prefix": ""}, {"branch_id": 1, "name": "x", "shelf_prefix": "x" * 21},
                 {"branch_id": "1", "name": "x"}, {"branch_id": 1, "name": "x", "extra": 1}):
        e = err(client.post(f"{API}/inventory-counts", headers=lib, json=body), 422, "VALIDATION_ERROR")
        assert e["details"]["fields"]
    e = err(client.post(f"{API}/inventory-counts", headers=lib, json={"branch_id": 99, "name": "x"}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "branch_id"
    assert start(client, lib, prefix=None, name="  Spaced  ")["name"] == "Spaced"


def test_start_checks_in_order(client, lib, shelf, admin_h):
    start(client, lib, branch=2, expect=409)  # no copies at branch 2
    r = client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200, r.text
    err(client.post(f"{API}/inventory-counts", headers=lib, json={"branch_id": 2, "name": "x"}), 409, "BRANCH_INACTIVE")


def test_overlap_examples(client, lib, shelf, app):
    _set(app, 3, shelf_location="A-24")
    start(client, lib, prefix="A-1")
    for prefix in ("A-", "a-12", "A-1", None):
        e = err(client.post(f"{API}/inventory-counts", headers=lib,
                            json={"branch_id": 1, "name": "x", **({"shelf_prefix": prefix} if prefix else {})}),
                409, "COUNT_SCOPE_OVERLAP")
        assert e["details"] == {"count_id": 1}
    start(client, lib, prefix="A-2")  # allowed
    step(client, lib, 1, "cancel")
    start(client, lib, prefix="A-1")  # a cancelled count does not overlap


def test_branch_not_open(client, lib, shelf, clock, admin_h):
    at(clock, 2026, 11, 7)  # Saturday
    e = err(client.post(f"{API}/inventory-counts", headers=lib, json={"branch_id": 1, "name": "x"}), 409, "BRANCH_NOT_OPEN")
    assert e["details"]["reason"] == "weekend"
    at(clock, 2026, 11, 9)
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-10", "reason": "Sayım"})
    assert r.status_code == 201, r.text
    at(clock, 2026, 11, 10)
    e = err(client.post(f"{API}/inventory-counts", headers=lib, json={"branch_id": 1, "name": "x"}), 409, "BRANCH_NOT_OPEN")
    assert e["details"]["reason"] == "closure"
    at(clock, 2026, 11, 11)
    start(client, lib)


def test_permissions(client, lib, shelf, admin_h):
    start(client, lib)
    m = mk_member(client, lib)
    mh = member_h(client)
    for method, path, body in (
        ("post", "/inventory-counts", {"branch_id": 1, "name": "x"}), ("get", "/inventory-counts", None),
        ("get", "/inventory-counts/1", None), ("post", "/inventory-counts/1/scans", {"barcodes": ["x"]}),
        ("get", "/inventory-counts/1/scans", None), ("delete", "/inventory-scans/1", None),
        ("post", "/inventory-counts/1/close", None), ("post", "/inventory-counts/1/cancel", None),
        ("post", "/inventory-counts/1/apply", None), ("get", "/inventory-counts/1/lines", None),
        ("post", "/copies/1/found", {"branch_id": 1}), ("post", "/inventory/process", None),
        ("get", "/reports/inventory?year=2026", None),
    ):
        err(client.request(method, API + path, headers=mh, json=body), 403, "FORBIDDEN")
        err(client.request(method, API + path, json=body), 401, "UNAUTHENTICATED")
    assert m == 1
    assert client.get(f"{API}/inventory-counts", headers=admin_h).status_code == 200


def test_read_counts(client, lib, shelf, app, admin_h):
    start(client, lib, prefix="A-")
    mk_book  # noqa: B018
    shelf_copy(client, lib, shelf, "BC-0010", "C-1", branch=2)
    start(client, lib, branch=2)
    step(client, lib, 2, "cancel")
    r = client.get(f"{API}/inventory-counts", headers=lib)
    body = r.json()
    assert [c["id"] for c in body["items"]] == [2, 1] and body["total"] == 2
    assert [c["id"] for c in client.get(f"{API}/inventory-counts?branch_id=1", headers=lib).json()["items"]] == [1]
    assert [c["id"] for c in client.get(f"{API}/inventory-counts?status=cancelled", headers=lib).json()["items"]] == [2]
    err(client.get(f"{API}/inventory-counts?status=nope", headers=lib), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/inventory-counts/9", headers=lib), 404, "NOT_FOUND")
    err(client.get(f"{API}/inventory-counts/0", headers=lib), 422, "VALIDATION_ERROR")
    assert get_count(client, lib, 1)["progress"] == {
        "expected": 2, "scanned_expected": 0, "remaining": 2,
        "problems": {"unknown": 0, "duplicate": 0, "found_lost": 0, "withdrawn": 0, "wrong_branch": 0,
                     "unexpected_status": 0, "out_of_scope": 0},
    }


def test_cancel(client, lib, shelf, app):
    start(client, lib)
    c = step(client, lib, 1, "cancel")
    assert c["status"] == "cancelled" and c["cancel_reason"] == "staff_request"
    e = err(client.post(f"{API}/inventory-counts/1/cancel", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "cancelled"
    assert [a.entity_id for a in audit(app, "inventory_count_cancelled")] == [1]
    start(client, lib)
    step(client, lib, 2, "close")
    assert step(client, lib, 2, "cancel")["status"] == "cancelled"
    start(client, lib)
    scan(client, lib, "BC-0001", count=3)
    step(client, lib, 3, "close")
    step(client, lib, 3, "apply")
    err(client.post(f"{API}/inventory-counts/3/cancel", headers=lib), 409, "INVALID_COUNT_STATUS")


# --- scanning ---------------------------------------------------------------------------------------


def test_scan_results(client, lib, shelf, app, admin_h):
    other = mk_book(client, lib, 1)
    shelf_copy(client, lib, other, "BC-0004", "A-20", branch=2)  # branch B
    lent = shelf_copy(client, lib, other, "BC-0005", "A-30")
    new_copy(client, lib, other, "BC-0006", price="10.00")
    assert lent == 5
    start(client, lib, prefix="A-")  # expected: 1, 2, 5, (6 has no shelf)
    m = mk_member(client, lib)
    assert lend(client, lib, m, 5).status_code == 201  # lent after the start: still expected
    lost = shelf_copy(client, lib, other, "BC-0007", "A-99")
    _set(app, lost, status="lost", current_branch_id=None)
    _set(app, 3, status="available")
    got = results(client, lib, 1, "bc-0001", "BC-0001", "BC-0003", "BC-0007", "NOPE-0001", "BC-0004", "BC-0005")
    assert got == ["expected", "duplicate", "out_of_scope", "found_lost", "unknown", "wrong_branch", "expected"]
    _set(app, 6, status="on_loan")
    assert results(client, lib, 1, "BC-0006") == ["unexpected_status"]
    gone = shelf_copy(client, lib, other, "BC-0009", "A-31")
    _set(app, gone, status="withdrawn")
    assert results(client, lib, 1, "BC-0009", "BC-0002") == ["withdrawn", "expected"]
    mk_copy(client, lib, other, "BC-0008", 1, shelf_location="A-77")
    assert results(client, lib, 1, "BC-0008") == ["out_of_scope"]  # added after the start (LIB-INV-10)
    p = get_count(client, lib, 1)["progress"]
    assert p["expected"] == 3 and p["scanned_expected"] == 3 and p["remaining"] == 0
    assert p["problems"] == {"unknown": 1, "duplicate": 1, "found_lost": 1, "withdrawn": 1, "wrong_branch": 1,
                             "unexpected_status": 1, "out_of_scope": 2}
    assert [a.entity_id for a in audit(app, "inventory_scans_added")] == [1, 1, 1, 1]


def test_scan_response_and_list(client, lib, shelf):
    start(client, lib)
    body = scan(client, lib, "bc-0001", "zz-9999", " BC-0001 ")
    assert body == {"scans": [
        {"id": 1, "barcode": "BC-0001", "copy_id": 1, "result": "expected"},
        {"id": 2, "barcode": "ZZ-9999", "copy_id": None, "result": "unknown"},
        {"id": 3, "barcode": "BC-0001", "copy_id": 1, "result": "duplicate"},
    ]}
    page = client.get(f"{API}/inventory-counts/1/scans", headers=lib).json()
    assert [s["id"] for s in page["items"]] == [1, 2, 3] and page["total"] == 3
    first = page["items"][0]
    assert first["count_id"] == 1 and first["scanned_by"] == 2 and first["scanned_at"] == "2026-11-02T09:30:00+03:00"
    only = client.get(f"{API}/inventory-counts/1/scans?result=unknown", headers=lib).json()
    assert [s["id"] for s in only["items"]] == [2]
    err(client.get(f"{API}/inventory-counts/1/scans?result=x", headers=lib), 422, "VALIDATION_ERROR")


def test_scan_validation_and_status(client, lib, shelf):
    start(client, lib)
    for body in ({}, {"barcodes": []}, {"barcodes": ["a"] * 201}, {"barcodes": [1]}, {"barcodes": ["a"], "x": 1},
                 {"barcodes": [""]}):
        err(client.post(f"{API}/inventory-counts/1/scans", headers=lib, json=body), 422, "VALIDATION_ERROR")
    assert len(scan(client, lib, *["X-0000"] * 200)["scans"]) == 200
    err(client.post(f"{API}/inventory-counts/9/scans", headers=lib, json={"barcodes": ["a"]}), 404, "NOT_FOUND")
    step(client, lib, 1, "close")
    e = err(client.post(f"{API}/inventory-counts/1/scans", headers=lib, json={"barcodes": ["a"]}), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "closed"


def test_undo_scan(client, lib, shelf, app):
    start(client, lib)
    scan(client, lib, "BC-0001", "BC-0001", "BC-0002")
    assert client.delete(f"{API}/inventory-scans/1", headers=lib).status_code == 204
    # the duplicate keeps its result and the copy still counts as scanned
    scans = client.get(f"{API}/inventory-counts/1/scans", headers=lib).json()["items"]
    assert [(s["id"], s["result"]) for s in scans] == [(2, "duplicate"), (3, "expected")]
    assert get_count(client, lib, 1)["progress"]["scanned_expected"] == 2
    assert client.delete(f"{API}/inventory-scans/2", headers=lib).status_code == 204
    assert get_count(client, lib, 1)["progress"]["scanned_expected"] == 1
    assert results(client, lib, 1, "BC-0001") == ["expected"]
    err(client.delete(f"{API}/inventory-scans/99", headers=lib), 404, "NOT_FOUND")
    assert [a.entity_id for a in audit(app, "inventory_scan_removed")] == [1, 2]
    step(client, lib, 1, "close")
    e = err(client.delete(f"{API}/inventory-scans/3", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "closed"


def test_copies_in_a_count(client, lib, shelf, app, admin_h):
    start(client, lib, prefix="A-")
    e = err(client.post(f"{API}/transfers", headers=lib, json={"copy_id": 1, "to_branch_id": 2}), 409, "COPY_IN_COUNT")
    assert e["details"] == {"count_id": 1}
    e = err(client.post(f"{API}/copies/2/withdraw", headers=lib, json={"reason": "worn out"}), 409, "COPY_IN_COUNT")
    assert e["details"] == {"count_id": 1}
    # outside the count, and lending, work as usual
    assert client.post(f"{API}/transfers", headers=lib, json={"copy_id": 3, "to_branch_id": 2}).status_code == 201
    m = mk_member(client, lib)
    assert lend(client, lib, m, 1).status_code == 201
    step(client, lib, 1, "cancel")
    assert client.post(f"{API}/copies/2/withdraw", headers=lib, json={"reason": "worn out"}).status_code == 200


# --- closing ----------------------------------------------------------------------------------------


@pytest.fixture
def five(client, lib):
    """Copies 1 to 5 (BC-0001 to BC-0005) of book 0 at branch 1, shelves A-1 to A-5."""
    book = mk_book(client, lib, 0)
    for n in range(1, 6):
        shelf_copy(client, lib, book, f"BC-000{n}", f"A-{n}")
    return book


def test_close_example(client, lib, five, app):
    start(client, lib)
    m = mk_member(client, lib)
    scan(client, lib, "BC-0001", "BC-0002", "BC-0003")
    assert lend(client, lib, m, 4).status_code == 201
    c = step(client, lib, 1, "close")
    assert c["status"] == "closed" and c["closed_at"] == "2026-11-02T09:30:00+03:00"
    assert c["summary"] == {"expected": 5, "found": 3, "missing": 1, "moved": 1, "accuracy": "75.0"}
    lines = client.get(f"{API}/inventory-counts/1/lines", headers=lib).json()
    assert lines["total"] == 5
    assert [(x["copy_id"], x["outcome"]) for x in lines["items"]] == [(1, "found"), (2, "found"), (3, "found"),
                                                                       (4, "moved"), (5, "missing")]
    assert lines["items"][4] == {"copy_id": 5, "outcome": "missing", "barcode": "BC-0005", "book_title": "Book 0",
                                 "shelf_location": "A-5"}
    only = client.get(f"{API}/inventory-counts/1/lines?outcome=moved", headers=lib).json()
    assert [x["copy_id"] for x in only["items"]] == [4]
    err(client.get(f"{API}/inventory-counts/1/lines?outcome=x", headers=lib), 422, "VALIDATION_ERROR")
    assert get_count(client, lib, 1)["summary"] == c["summary"]
    assert [a.entity_id for a in audit(app, "inventory_count_closed")] == [1]
    e = err(client.post(f"{API}/inventory-counts/1/close", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "closed"


def test_lines_need_a_closed_count(client, lib, five):
    start(client, lib)
    e = err(client.get(f"{API}/inventory-counts/1/lines", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "open"
    step(client, lib, 1, "close")
    assert client.get(f"{API}/inventory-counts/1/lines", headers=lib).status_code == 200
    step(client, lib, 1, "cancel")
    err(client.get(f"{API}/inventory-counts/1/lines", headers=lib), 409, "INVALID_COUNT_STATUS")


def test_accuracy_rounding(client, lib, five):
    start(client, lib)
    assert step(client, lib, 1, "close")["summary"]["accuracy"] == "0.0"
    step(client, lib, 1, "cancel")
    start(client, lib)
    scan(client, lib, "BC-0001", "BC-0002", "BC-0003", "BC-0004", count=2)
    assert step(client, lib, 2, "close")["summary"]["accuracy"] == "80.0"


def test_accuracy_without_found_or_missing(client, lib, five, app):
    start(client, lib)
    for n in range(1, 6):
        _set(app, n, status="withdrawn")
    c = step(client, lib, 1, "close")
    assert c["summary"] == {"expected": 5, "found": 0, "missing": 0, "moved": 5, "accuracy": "100.0"}


# --- applying ---------------------------------------------------------------------------------------


def test_apply_marks_missing(client, lib, five, app):
    start(client, lib)
    scan(client, lib, "BC-0001", "BC-0002", "BC-0003", "BC-0004")
    step(client, lib, 1, "close")
    clock_day = "2026-11-02"
    r = client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    assert r.status_code == 200 and r.json() == {"missing_marked": 1, "found": 0, "relocated": 0}
    c = copy_of(client, lib, 5)
    assert c["status"] == "missing" and c["missing_since"] == clock_day
    applied = get_count(client, lib, 1)
    assert applied["status"] == "applied" and applied["applied_at"] == "2026-11-02T09:30:00+03:00"
    assert [a.entity_id for a in audit(app, "inventory_count_applied")] == [1]
    e = err(client.post(f"{API}/inventory-counts/1/apply", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert e["details"]["status"] == "applied"
    e = err(client.post(f"{API}/inventory-counts/1/close", headers=lib), 409, "INVALID_COUNT_STATUS")
    assert client.get(f"{API}/inventory-counts/1/lines", headers=lib).status_code == 200


def test_apply_needs_closed(client, lib, five):
    start(client, lib)
    err(client.post(f"{API}/inventory-counts/1/apply", headers=lib), 409, "INVALID_COUNT_STATUS")


def test_apply_skips_changed_copies(client, lib, five, app):
    start(client, lib)
    step(client, lib, 1, "close")
    m = mk_member(client, lib)
    assert lend(client, lib, m, 1).status_code == 201  # no longer on the shelf
    _set(app, 2, status="withdrawn")
    r = client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    assert r.json() == {"missing_marked": 3, "found": 0, "relocated": 0}
    assert copy_of(client, lib, 1)["status"] == "on_loan"
    assert [copy_of(client, lib, n)["status"] for n in (3, 4, 5)] == ["missing"] * 3


def test_apply_limit_for_librarians(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    for n in range(12):
        shelf_copy(client, lib, book, f"BC-{n:04d}", f"A-{n}")
    start(client, lib)
    scan(client, lib, "BC-0000")  # 11 missing
    step(client, lib, 1, "close")
    err(client.post(f"{API}/inventory-counts/1/apply", headers=lib), 403, "FORBIDDEN")
    r = client.post(f"{API}/inventory-counts/1/apply", headers=admin_h)
    assert r.status_code == 200 and r.json()["missing_marked"] == 11
    # exactly 10 missing lines: a librarian may apply
    start(client, lib)
    step(client, lib, 2, "cancel")
    book2 = mk_book(client, lib, 1)
    for n in range(10):
        shelf_copy(client, lib, book2, f"BD-{n:04d}", f"B-{n}", branch=2)
    start(client, lib, branch=2)
    step(client, lib, 3, "close")
    assert client.post(f"{API}/inventory-counts/3/apply", headers=lib).json()["missing_marked"] == 10


def test_apply_found_lost_and_wrong_branch(client, lib, five, app):
    other = mk_book(client, lib, 1)
    lost = shelf_copy(client, lib, other, "BC-0006", "Z-1")
    stray = shelf_copy(client, lib, other, "BC-0007", "Z-2", branch=2)
    held_elsewhere = shelf_copy(client, lib, other, "BC-0008", "Z-3", branch=2)
    _set(app, lost, status="lost", current_branch_id=None)
    _set(app, held_elsewhere, status="damaged")
    start(client, lib)
    assert results(client, lib, 1, "BC-0006", "BC-0007", "BC-0008") == ["found_lost", "wrong_branch", "wrong_branch"]
    # nothing changes before the count is applied (LIB-INV-28)
    assert copy_of(client, lib, lost)["status"] == "lost"
    step(client, lib, 1, "close")
    assert copy_of(client, lib, lost)["status"] == "lost"
    r = client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    assert r.json() == {"missing_marked": 5, "found": 1, "relocated": 1}
    c = copy_of(client, lib, lost)
    assert c["status"] == "available" and c["current_branch_id"] == 1 and c["missing_since"] is None
    # the stray copy belongs to branch 2: it is at branch 1 and goes home again
    c = copy_of(client, lib, stray)
    assert c["status"] == "in_transfer" and c["current_branch_id"] is None
    assert copy_of(client, lib, held_elsewhere)["current_branch_id"] == 2


def test_apply_found_missing_copy_serves_reservation(client, lib, five, app):
    start(client, lib)
    step(client, lib, 1, "close")
    client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    assert copy_of(client, lib, 1)["status"] == "missing"
    m = mk_member(client, lib)
    r = reserve(client, lib, 1, 1, m)
    assert r.status_code == 409  # a book of missing copies only is not lendable
    assert r.json()["error"]["code"] == "BOOK_NOT_LENDABLE"


# --- held and reserve copies ---------------------------------------------------------------------


def test_missing_held_copy_goes_back_to_the_queue(client, lib, app):
    book = mk_book(client, lib, 0)
    shelf_copy(client, lib, book, "BC-0001", "A-1")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    loan = lend(client, lib, m1, 1).json()["id"]
    rid = reserve(client, lib, book, 1, m2).json()["id"]
    assert ret(client, lib, loan).status_code == 200
    assert res(client, lib, rid)["status"] == "ready" and copy_of(client, lib, 1)["status"] == "on_hold"
    start(client, lib)
    step(client, lib, 1, "close")
    assert client.post(f"{API}/inventory-counts/1/apply", headers=lib).json()["missing_marked"] == 1
    r = res(client, lib, rid)
    assert r["status"] == "waiting" and r["copy_id"] is None and r["ready_on"] is None and r["hold_until"] is None
    assert r["queue_position"] == 1
    with app.state.session_factory() as s:
        notes = list(s.scalars(sa.select(Notification).where(Notification.type == "reservation_delayed")))
        assert [(n.member_id, n.reservation_id) for n in notes] == [(m2, rid)]
        assert "Book 0" in notes[0].message
    summary = client.get(f"{API}/members/{m2}/summary", headers=lib).json()
    assert summary["active_reservations"] == 1
    # found again: the copy is released and the waiting reservation takes it
    found = client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 1})
    assert found.status_code == 200 and found.json()["status"] == "on_hold"
    assert res(client, lib, rid)["status"] == "ready"


# --- found again --------------------------------------------------------------------------------------


def test_found_copy(client, lib, five, app, admin_h):
    start(client, lib)
    step(client, lib, 1, "close")
    client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    r = client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 1})
    assert r.status_code == 200
    c = r.json()
    assert c["status"] == "available" and c["current_branch_id"] == 1 and c["missing_since"] is None
    e = err(client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 1}), 409, "INVALID_COPY_STATUS")
    err(client.post(f"{API}/copies/2/found", headers=lib, json={"branch_id": 99}), 404, "NOT_FOUND")
    err(client.post(f"{API}/copies/99/found", headers=lib, json={"branch_id": 1}), 404, "NOT_FOUND")
    err(client.post(f"{API}/copies/2/found", headers=lib, json={}), 422, "VALIDATION_ERROR")
    # found at another branch: the copy goes home again
    r = client.post(f"{API}/copies/2/found", headers=lib, json={"branch_id": 2})
    assert r.json()["status"] == "in_transfer" and r.json()["current_branch_id"] is None
    assert [a.entity_id for a in audit(app, "copy_found")] == [1, 2]
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/copies/3/found", headers=lib, json={"branch_id": 2}), 409, "BRANCH_INACTIVE")
    assert e["details"]["status"] == "available"


def test_found_lost_copy_keeps_fees(client, lib, app):
    book = mk_book(client, lib, 0)
    shelf_copy(client, lib, book, "BC-0001", "A-1")
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 1).json()["id"]
    assert client.post(f"{API}/loans/{loan}/report-lost", headers=lib).status_code == 200
    before = client.get(f"{API}/members/{m}/fees", headers=lib).json()
    assert copy_of(client, lib, 1)["status"] == "lost"
    r = client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 2})
    assert r.status_code == 200 and r.json()["status"] == "in_transfer"
    assert client.get(f"{API}/members/{m}/fees", headers=lib).json() == before
    assert client.get(f"{API}/loans/{loan}", headers=lib).json()["status"] == "lost"


def test_found_needs_missing_or_lost(client, lib, five):
    e = err(client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 1}), 409, "INVALID_COPY_STATUS")
    assert e["details"]["status"] == "available"


# --- missing copies in the other modules ------------------------------------------------------------------


def test_missing_copy_in_other_modules(client, lib, five, app):
    m = mk_member(client, lib)
    _set(app, 1, status="missing", missing_since=datetime.date(2026, 10, 1))
    e = err(lend(client, lib, m, 1), 409, "COPY_NOT_AVAILABLE")
    assert e["details"]["status"] == "missing"
    err(client.post(f"{API}/transfers", headers=lib, json={"copy_id": 1, "to_branch_id": 2}), 409, "INVALID_COPY_STATUS")
    book = client.get(f"{API}/books/1", headers=lib).json()
    assert book["availability"] == [{"branch_id": 1, "available": 4, "total": 4, "expected_back": None}]
    listed = client.get(f"{API}/books/1/copies?status=missing", headers=lib).json()
    assert [c["id"] for c in listed["items"]] == [1] and listed["items"][0]["missing_since"] == "2026-10-01"
    r = client.post(f"{API}/copies/1/withdraw", headers=lib, json={"reason": "never found"})
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"


def test_book_with_only_missing_copies(client, lib, shelf, app):
    for n in (1, 2, 3):
        _set(app, n, status="missing")
    m = mk_member(client, lib)
    book = client.get(f"{API}/books/{shelf}", headers=lib).json()
    assert book["availability"] == [{"branch_id": 1, "available": 0, "total": 0, "expected_back": None}]
    e = err(reserve(client, lib, shelf, 1, m), 409, "BOOK_NOT_LENDABLE")
    assert e["details"]["book_id"] == shelf
    _set(app, 3, status="available")
    assert client.get(f"{API}/books/{shelf}", headers=lib).json()["availability"][0]["total"] == 1


def test_inventory_status_report_lists_missing(client, lib, five, app):
    _set(app, 1, status="missing")
    items = client.get(f"{API}/reports/inventory", headers=lib).json()["items"]
    assert items == [{"branch_id": 1, "status": "available", "copies": 4}, {"branch_id": 1, "status": "missing", "copies": 1}]


def test_export_writes_missing_as_lost(client, lib, five, admin_h, app):
    _set(app, 1, status="missing", missing_since=datetime.date(2026, 10, 1))
    data = client.get(f"{API}/export", headers=admin_h).json()
    assert data["copies"][0]["status"] == "lost" and "missing_since" not in data["copies"][0]
    assert not any(c["status"] == "missing" for c in data["copies"])
    csv = client.get(f"{API}/export/copies.csv", headers=admin_h).text
    assert "missing" not in csv


# --- processing ----------------------------------------------------------------------------------------


def test_process_expires_old_counts(client, lib, five, clock, app):
    start(client, lib)  # Mon 2026-11-02 09:30
    at(clock, 2026, 11, 9)
    clock.set(datetime.datetime(2026, 11, 9, 9, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=3))))
    r = client.post(f"{API}/inventory/process", headers=lib)
    assert r.status_code == 200 and r.json() == {"expired_counts": 0, "marked_lost": 0}
    clock.set(datetime.datetime(2026, 11, 9, 9, 30, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=3))))
    r = client.post(f"{API}/inventory/process", headers=lib)
    assert r.json() == {"expired_counts": 1, "marked_lost": 0}
    c = get_count(client, lib, 1)
    assert c["status"] == "cancelled" and c["cancel_reason"] == "expired"
    assert client.post(f"{API}/inventory/process", headers=lib).json() == {"expired_counts": 0, "marked_lost": 0}
    assert len(audit(app, "inventory_processed")) == 3
    start(client, lib)  # the scope is free again
    step(client, lib, 2, "close")
    at(clock, 2026, 12, 9)
    assert client.post(f"{API}/inventory/process", headers=lib).json()["expired_counts"] == 0  # a closed count stays


def test_process_marks_long_missing_copies_lost(client, lib, five, clock, app):
    _set(app, 1, status="missing", missing_since=datetime.date(2026, 11, 2))
    _set(app, 2, status="missing", missing_since=datetime.date(2026, 11, 3))
    tz = datetime.timezone(datetime.timedelta(hours=3))
    clock.set(datetime.datetime(2027, 1, 30, 9, 0, tzinfo=tz))
    assert client.post(f"{API}/inventory/process", headers=lib).json() == {"expired_counts": 0, "marked_lost": 0}
    assert copy_of(client, lib, 1)["status"] == "missing"
    clock.set(datetime.datetime(2027, 1, 31, 9, 0, tzinfo=tz))
    assert client.post(f"{API}/inventory/process", headers=lib).json() == {"expired_counts": 0, "marked_lost": 1}
    c = copy_of(client, lib, 1)
    assert c["status"] == "lost" and c["current_branch_id"] is None
    assert copy_of(client, lib, 2)["status"] == "missing"
    # a lost copy can be found again
    assert client.post(f"{API}/copies/1/found", headers=lib, json={"branch_id": 1}).json()["status"] == "available"


# --- report --------------------------------------------------------------------------------------------


def test_inventory_report(client, lib, five, clock, app):
    book = mk_book(client, lib, 1)
    shelf_copy(client, lib, book, "BD-0001", "B-1", branch=2)
    shelf_copy(client, lib, book, "BD-0002", "B-2", branch=2)
    assert client.get(f"{API}/reports/inventory?year=2026", headers=lib).json() == {"items": []}
    start(client, lib, branch=2)
    scan(client, lib, "BD-0001", "BD-0002")
    step(client, lib, 1, "close")
    client.post(f"{API}/inventory-counts/1/apply", headers=lib)
    start(client, lib)
    scan(client, lib, "BC-0001", "BC-0002", "BC-0003", count=2)
    step(client, lib, 2, "close")
    at(clock, 2026, 11, 3, 10)
    client.post(f"{API}/inventory-counts/2/apply", headers=lib)
    # copies 4 and 5 are missing now; copy 4 is found again
    assert client.post(f"{API}/copies/4/found", headers=lib, json={"branch_id": 1}).status_code == 200
    start(client, lib)
    scan(client, lib, "BC-0004", count=3)
    at(clock, 2026, 11, 4, 10)
    items = client.get(f"{API}/reports/inventory?year=2026", headers=lib).json()["items"]
    assert items == [
        {"branch_id": 1, "counts_applied": 1, "last_applied_on": "2026-11-03", "expected": 5, "found": 3, "missing": 2,
         "accuracy": "60.0", "missing_now": 1, "found_again": 1},
        {"branch_id": 2, "counts_applied": 1, "last_applied_on": "2026-11-02", "expected": 2, "found": 2, "missing": 0,
         "accuracy": "100.0", "missing_now": 0, "found_again": 0},
    ]
    assert client.get(f"{API}/reports/inventory?year=2027", headers=lib).json() == {"items": []}
    err(client.get(f"{API}/reports/inventory?year=1999", headers=lib), 422, "VALIDATION_ERROR")


# --- reserve copies ------------------------------------------------------------------------------------


def test_missing_reserve_copy_returns_the_item_to_requested(client, admin_h, world, app):
    mk_course(client, admin_h)
    for n in (1, 2):
        assert mk_copy(client, admin_h, barcode=f"BC-000{n}", branch=1, shelf_location=f"A-{n}").status_code == 201
    item = mk_item(client, admin_h, copies_wanted=1)
    assert item["status"] == "on_reserve"
    c = start(client, admin_h)
    assert c["expected"] == [1, 2]
    scan(client, admin_h, "BC-0002")
    step(client, admin_h, 1, "close")
    assert client.post(f"{API}/inventory-counts/1/apply", headers=admin_h).json()["missing_marked"] == 1
    copy = client.get(f"{API}/copies/1", headers=admin_h).json()
    assert copy["status"] == "missing" and copy["reserve_item_id"] is None
    items = client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"]
    assert items[0]["status"] == "requested" and items[0]["copies_on_reserve"] == 0


def test_endpoints_are_in_the_openapi_document(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path, methods in {
        "/api/v1/inventory-counts": {"post", "get"},
        "/api/v1/inventory-counts/{count_id}": {"get"},
        "/api/v1/inventory-counts/{count_id}/scans": {"post", "get"},
        "/api/v1/inventory-scans/{scan_id}": {"delete"},
        "/api/v1/inventory-counts/{count_id}/close": {"post"},
        "/api/v1/inventory-counts/{count_id}/cancel": {"post"},
        "/api/v1/inventory-counts/{count_id}/apply": {"post"},
        "/api/v1/inventory-counts/{count_id}/lines": {"get"},
        "/api/v1/copies/{copy_id}/found": {"post"},
        "/api/v1/inventory/process": {"post"},
        "/api/v1/reports/inventory": {"get"},
    }.items():
        assert methods <= set(paths[path]), path
