"""Feedback tests: module 24 (Inventory counts). Generated from cases/inventory.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    create_book, create_branch, error_code, items, lend, member_headers, register_member, report_lost, reserve, return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py)


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def same(value, day, hh, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    return datetime.fromisoformat(value) == datetime(y, m, d, hh, mm, ss, tzinfo=TR)


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def post(client, headers, path, body=None):
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def copy(client, lib, branch, shelf=None, book=None):
    _seq[0] += 1
    b = book or create_book(client, lib, title="Sayım Kitabı")
    body = {"barcode": f"INV{_seq[0]:05d}", "home_branch_id": branch["id"], "price": "50.00", "acquired_on": "2025-01-01", "shelf_location": shelf}
    return ok(post(client, lib, f"books/{b['id']}/copies", body), 201)


def try_count(client, headers, branch, prefix=None, name="Yıl sonu sayımı"):
    body = {"branch_id": branch["id"], "name": name}
    if prefix is not None:
        body["shelf_prefix"] = prefix
    return post(client, headers, "inventory-counts", body)


def count(client, headers, branch, prefix=None, **kw):
    return ok(try_count(client, headers, branch, prefix, **kw), 201)


def scan(client, headers, count_, *barcodes):
    return post(client, headers, f"inventory-counts/{count_['id']}/scans", {"barcodes": list(barcodes)})


def scanned(client, headers, count_, *copies):
    return ok(scan(client, headers, count_, *[c["barcode"] for c in copies]), 201)["scans"]


def step(client, headers, count_, name):
    return post(client, headers, f"inventory-counts/{count_['id']}/{name}")


def copy_of(client, lib, copy_id):
    return get(client, lib, f"copies/{copy_id}")


def lost_copy(client, lib, branch):
    cp = copy(client, lib, branch)
    report_lost(client, lib, lend(client, lib, member(client, lib, branch)["id"], cp["id"])["id"])
    return cp


def held_copy(client, lib, branch):
    """A copy ``on_hold`` at ``branch`` for a ready reservation: (copy, reservation, member)."""
    b = create_book(client, lib, title="Ayrılmış Kitap")
    cp = copy(client, lib, branch, book=b)
    loan = lend(client, lib, member(client, lib, branch)["id"], cp["id"])
    m = member(client, lib, branch)
    res = reserve(client, lib, book_id=b["id"], pickup_branch_id=branch["id"], member_id=m["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"])
    return cp, res, m


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def test_t_inv_01_a(client, librarian, branch_a):
    """T-INV-01-a (LIB-INV-01): 201 open, started_at, shelf_prefix null, expected_count 3"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    d = copy(client, librarian, branch_a)
    return_loan(client, librarian, lend(client, librarian, member(client, librarian, branch_a)["id"], d["id"])["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="5.00")
    lend(client, librarian, member(client, librarian, branch_a)["id"], copy(client, librarian, branch_a)["id"])
    c = count(client, librarian, branch_a)
    assert (c["branch_id"], c["name"], c["status"], c["shelf_prefix"], c["expected_count"]) == (branch_a["id"], "Yıl sonu sayımı", "open", None, 3)
    assert same(c["started_at"], MON, 9) and c["expected"] == [c1["id"], c2["id"], d["id"]]


def test_t_inv_03_a(client, admin, librarian, branch_a):
    """T-INV-03-a (LIB-INV-03): BRANCH_INACTIVE; COUNT_EMPTY; COUNT_EMPTY"""
    copy(client, librarian, branch_a, "A-01")
    qq = create_branch(client, admin, "QQ")
    err(try_count(client, librarian, qq), 409, "COUNT_EMPTY")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_count(client, librarian, qq), 409, "BRANCH_INACTIVE")
    err(try_count(client, librarian, branch_a, "Z-"), 409, "COUNT_EMPTY")


def test_t_inv_05_a(client, librarian, branch_a, branch_b):
    """T-INV-05-a (LIB-INV-05): [K2, K1]; [K1]; progress {expected 3, scanned_expected 2, remaining 1}, problems.unknown 1"""
    cs = [copy(client, librarian, branch_a) for _ in range(3)]
    copy(client, librarian, branch_b)
    k1, k2 = count(client, librarian, branch_a), count(client, librarian, branch_b)
    ok(scan(client, librarian, k1, cs[0]["barcode"], cs[1]["barcode"], "NOPE-0001"), 201)
    assert [x["id"] for x in items(get(client, librarian, "inventory-counts"))] == [k2["id"], k1["id"]]
    assert [x["id"] for x in items(get(client, librarian, "inventory-counts", branch_id=branch_a["id"]))] == [k1["id"]]
    p = get(client, librarian, f"inventory-counts/{k1['id']}")["progress"]
    assert (p["expected"], p["scanned_expected"], p["remaining"], p["problems"]["unknown"], p["problems"]["duplicate"]) == (3, 2, 1, 1, 0)


def test_t_inv_07_a(client, librarian, branch_a):
    """T-INV-07-a (LIB-INV-07): 201 with expected; 422; 422; 409 INVALID_COUNT_STATUS"""
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    out = ok(scan(client, librarian, k, cp["barcode"].lower()), 201)["scans"]
    assert [(s["barcode"], s["copy_id"], s["result"]) for s in out] == [(cp["barcode"], cp["id"], "expected")]
    assert scan(client, librarian, k).status_code == 422
    assert scan(client, librarian, k, *[f"X{i:05d}" for i in range(201)]).status_code == 422
    ok(step(client, librarian, k, "close"))
    err(scan(client, librarian, k, cp["barcode"]), 409, "INVALID_COUNT_STATUS")


def test_t_inv_09_a(client, librarian, branch_a, branch_b):
    """T-INV-09-a (LIB-INV-09): expected, duplicate, out_of_scope, unexpected_status, wrong_branch, found_lost, unknown"""
    a12, b01 = copy(client, librarian, branch_a, "A-12"), copy(client, librarian, branch_a, "B-01")
    out = copy(client, librarian, branch_a, "A-13")
    other, lost = copy(client, librarian, branch_b), lost_copy(client, librarian, branch_a)
    lend(client, librarian, member(client, librarian, branch_a)["id"], out["id"])
    k = count(client, librarian, branch_a, "A-")
    res = ok(scan(client, librarian, k, a12["barcode"], a12["barcode"], b01["barcode"], out["barcode"], other["barcode"], lost["barcode"], "NOPE-0001"), 201)["scans"]
    assert [s["result"] for s in res] == ["expected", "duplicate", "out_of_scope", "unexpected_status", "wrong_branch", "found_lost", "unknown"]
    assert res[-1]["copy_id"] is None


def test_t_inv_11_a(client, librarian, branch_a):
    """T-INV-11-a (LIB-INV-11): Three scans in order; one unknown"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(scan(client, librarian, k, c1["barcode"], "NOPE-0001", c2["barcode"]), 201)
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/scans"))
    assert [r["barcode"] for r in rows] == [c1["barcode"], "NOPE-0001", c2["barcode"]]
    assert [r["barcode"] for r in items(get(client, librarian, f"inventory-counts/{k['id']}/scans", result="unknown"))] == ["NOPE-0001"]


def test_t_inv_13_a(client, librarian, branch_a, branch_b):
    """T-INV-13-a (LIB-INV-13): COPY_IN_COUNT with details.count_id twice; lending 201; relocation 201"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    assert err(post(client, librarian, "transfers", {"copy_id": c1["id"], "to_branch_id": branch_b["id"]}), 409, "COPY_IN_COUNT")["details"]["count_id"] == k["id"]
    err(post(client, librarian, f"copies/{c1['id']}/withdraw", {"reason": "Eski kopya"}), 409, "COPY_IN_COUNT")
    lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    ok(step(client, librarian, k, "cancel"))
    ok(post(client, librarian, "transfers", {"copy_id": c1["id"], "to_branch_id": branch_b["id"]}), 201)


def test_t_inv_15_a(client, librarian, branch_a):
    """T-INV-15-a (LIB-INV-15): summary {expected 2, found 0, missing 0, moved 2, accuracy 100.0}"""
    cs = [copy(client, librarian, branch_a) for _ in range(2)]
    k = count(client, librarian, branch_a)
    for c in cs:
        lend(client, librarian, member(client, librarian, branch_a)["id"], c["id"])
    assert ok(step(client, librarian, k, "close"))["summary"] == {"expected": 2, "found": 0, "missing": 0, "moved": 2, "accuracy": "100.0"}


def test_t_inv_17_a(client, librarian, branch_a):
    """T-INV-17-a (LIB-INV-17): 409 INVALID_COUNT_STATUS; the missing copy with barcode, book_title, shelf_location"""
    c1, c2 = copy(client, librarian, branch_a, "A-01"), copy(client, librarian, branch_a, "A-02")
    k = count(client, librarian, branch_a)
    err(client.get(f"/api/v1/inventory-counts/{k['id']}/lines", headers=librarian), 409, "INVALID_COUNT_STATUS")
    scanned(client, librarian, k, c1)
    ok(step(client, librarian, k, "close"))
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/lines", outcome="missing"))
    assert [(r["copy_id"], r["barcode"], r["book_title"], r["shelf_location"]) for r in rows] == [(c2["id"], c2["barcode"], "Sayım Kitabı", "A-02")]


def test_t_inv_18_a(client, librarian, branch_a, branch_b):
    """T-INV-18-a (LIB-INV-18): {missing_marked 1, found 1, relocated 1}; C2 missing since today; the lost copy available at A; B's copy in_transfer home; 409 INVALID_COUNT_STATUS"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    lost, other = lost_copy(client, librarian, branch_a), copy(client, librarian, branch_b)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, c1, lost, other)
    ok(step(client, librarian, k, "close"))
    out = ok(step(client, librarian, k, "apply"))
    assert {key: out[key] for key in ("missing_marked", "found", "relocated")} == {"missing_marked": 1, "found": 1, "relocated": 1}
    assert get(client, librarian, f"inventory-counts/{k['id']}")["status"] == "applied"
    m = copy_of(client, librarian, c2["id"])
    assert (m["status"], m["missing_since"]) == ("missing", MON)
    f = copy_of(client, librarian, lost["id"])
    assert (f["status"], f["current_branch_id"]) == ("available", branch_a["id"])
    assert copy_of(client, librarian, other["id"])["status"] == "in_transfer"
    err(step(client, librarian, k, "apply"), 409, "INVALID_COUNT_STATUS")


def test_t_inv_19_a(client, admin, librarian, branch_a, branch_b):
    """T-INV-19-a (LIB-INV-19): 200; 403; 200"""
    for br in (branch_a, branch_b):
        for _ in range(10 if br is branch_a else 11):
            copy(client, librarian, br)
    ka, kb = count(client, librarian, branch_a), count(client, librarian, branch_b)
    for k in (ka, kb):
        ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, ka, "apply"))
    assert step(client, librarian, kb, "apply").status_code == 403
    ok(step(client, admin, kb, "apply"))


def test_t_inv_21_a(client, librarian, branch_a):
    """T-INV-21-a (LIB-INV-21): Copy missing with reserve_item_id null; the item requested"""
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    ins = member(client, librarian, branch_a, membership_type="academic")
    c = ok(post(client, librarian, "courses", {"code": "CENG402", "title": "Kurs", "term": "2026-fall", "instructor_id": ins["id"], "branch_id": branch_a["id"], "starts_on": "2026-10-01", "ends_on": "2027-01-15"}), 201)
    it = ok(post(client, librarian, f"courses/{c['id']}/reading-list", {"book_id": b["id"]}), 201)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    out = copy_of(client, librarian, cp["id"])
    assert (out["status"], out["reserve_item_id"]) == ("missing", None)
    rows = items(get(client, librarian, f"courses/{c['id']}/reading-list"))
    assert [r["status"] for r in rows if r["id"] == it["id"]] == ["requested"]


def test_t_inv_23_a(client, clock, librarian, branch_a, branch_b):
    """T-INV-23-a (LIB-INV-23): {expired_counts 1, marked_lost 1}; count cancelled with expired; copy lost with branch null"""
    copy(client, librarian, branch_a)
    miss = copy(client, librarian, branch_b)
    ka, kb = count(client, librarian, branch_a), count(client, librarian, branch_b)
    ok(step(client, librarian, kb, "close"))
    ok(step(client, librarian, kb, "apply"))
    at(clock, "2027-01-31")
    assert ok(post(client, librarian, "inventory/process")) == {"expired_counts": 1, "marked_lost": 1}
    out = get(client, librarian, f"inventory-counts/{ka['id']}")
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "expired")
    c = copy_of(client, librarian, miss["id"])
    assert (c["status"], c["current_branch_id"]) == ("lost", None)


def test_t_inv_25_a(client, librarian, branch_a):
    """T-INV-25-a (LIB-INV-25): Only the missing copy, with missing_since"""
    b = create_book(client, librarian)
    miss = copy(client, librarian, branch_a, book=b)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    copy(client, librarian, branch_a, book=b)
    rows = items(get(client, librarian, f"books/{b['id']}/copies", status="missing"))
    assert [(r["id"], r["missing_since"]) for r in rows] == [(miss["id"], MON)]


def test_t_inv_27_a(client, librarian, branch_a):
    """T-INV-27-a (LIB-INV-27): No availability row with copies; 409 BOOK_NOT_LENDABLE"""
    b = create_book(client, librarian)
    copy(client, librarian, branch_a, book=b)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert [r for r in get(client, librarian, f"books/{b['id']}")["availability"] if r["total"] > 0] == []
    r = post(client, librarian, "reservations", {"book_id": b["id"], "pickup_branch_id": branch_a["id"], "member_id": member(client, librarian, branch_a)["id"]})
    err(r, 409, "BOOK_NOT_LENDABLE")


def test_t_inv_29_a(client, clock, admin, librarian, branch_a):
    """T-INV-29-a (LIB-INV-29): 409 BRANCH_NOT_OPEN twice; 201"""
    copy(client, librarian, branch_a)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": "2026-11-03", "reason": "Sayım"}), 201)
    at(clock, "2026-11-07", 10)
    err(try_count(client, librarian, branch_a), 409, "BRANCH_NOT_OPEN")
    at(clock, "2026-11-03", 10)
    err(try_count(client, librarian, branch_a), 409, "BRANCH_NOT_OPEN")
    at(clock, "2026-11-09", 10)
    count(client, librarian, branch_a)


def test_t_inv_31_a(client, admin, librarian, branch_a, branch_b):
    """T-INV-31-a (LIB-INV-31): One entry per event (two for inventory_scans_added and inventory_count_started)"""
    c1, c2, c3 = (copy(client, librarian, branch_a) for _ in range(3))
    copy(client, librarian, branch_b)
    k = count(client, librarian, branch_a)
    s = scanned(client, librarian, k, c1)[0]
    scanned(client, librarian, k, c2)
    assert client.delete(f"/api/v1/inventory-scans/{s['id']}", headers=librarian).status_code == 204
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    ok(step(client, librarian, count(client, librarian, branch_b), "cancel"))
    ok(post(client, librarian, f"copies/{c3['id']}/found", {"branch_id": branch_a["id"]}))
    ok(post(client, librarian, "inventory/process"))
    counts = {"inventory_count_started": 2, "inventory_scans_added": 2, "inventory_scan_removed": 1, "inventory_count_closed": 1,
              "inventory_count_applied": 1, "inventory_count_cancelled": 1, "copy_found": 1, "inventory_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name


def test_t_inv_33_a(client, admin, librarian, branch_a):
    """T-INV-33-a (LIB-INV-33): The keys of 22.1; the copy has status lost and no missing_since"""
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == cp["id"]] == ["lost"]
    assert all("missing_since" not in c for c in out["copies"])
