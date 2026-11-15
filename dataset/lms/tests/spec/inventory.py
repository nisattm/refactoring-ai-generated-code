MODULE = "inventory"
TITLE = "module 24 (Inventory counts)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- starting
    dict(id="T-INV-01-a", req="LIB-INV-01", type="Normal", input="Branch A with 2 available copies, 1 damaged and 1 on loan; librarian starts a count without prefix", expected="201 `open`, `started_at`, `shelf_prefix` null, `expected_count` 3", code='''
def TEST(client, librarian, branch_a):
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    d = copy(client, librarian, branch_a)
    return_loan(client, librarian, lend(client, librarian, member(client, librarian, branch_a)["id"], d["id"])["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="5.00")
    lend(client, librarian, member(client, librarian, branch_a)["id"], copy(client, librarian, branch_a)["id"])
    c = count(client, librarian, branch_a)
    assert (c["branch_id"], c["name"], c["status"], c["shelf_prefix"], c["expected_count"]) == (branch_a["id"], "Yıl sonu sayımı", "open", None, 3)
    assert same(c["started_at"], MON, 9) and c["expected"] == [c1["id"], c2["id"], d["id"]]
'''),
    dict(id="T-INV-01-b", req="LIB-INV-01", type="Error", input="Empty name; prefix of 21 characters; unknown branch; a member starts a count", expected="`422` three times; `403`", code='''
def TEST(client, librarian, branch_a):
    copy(client, librarian, branch_a)
    assert try_count(client, librarian, branch_a, name="").status_code == 422
    assert try_count(client, librarian, branch_a, prefix="A" * 21).status_code == 422
    assert try_count(client, librarian, {"id": 999999}).status_code == 422
    assert try_count(client, member_headers(client, member(client, librarian, branch_a)), branch_a).status_code == 403
'''),
    dict(id="T-INV-02-a", req="LIB-INV-02", type="Normal", input="At A: copies on shelves `A-12` (available), `a-30` (on hold), `B-01`, no shelf, and a lost copy; count with prefix `A-`", expected="`expected` = the `A-12` and `a-30` copies", code='''
def TEST(client, librarian, branch_a):
    a12 = copy(client, librarian, branch_a, "A-12")
    held, _, _ = held_copy(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/copies/{held['id']}", headers=librarian, json={"shelf_location": "a-30"}))
    copy(client, librarian, branch_a, "B-01")
    copy(client, librarian, branch_a)
    lost = lost_copy(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/copies/{lost['id']}", headers=librarian, json={"shelf_location": "A-99"}))
    c = count(client, librarian, branch_a, "A-")
    assert (c["expected"], c["expected_count"]) == ([a12["id"], held["id"]], 2)
'''),
    dict(id="T-INV-03-a", req="LIB-INV-03", type="Error", input="Inactive branch; an active branch without copies; prefix `Z-` with no copy on such shelves", expected="`BRANCH_INACTIVE`; `COUNT_EMPTY`; `COUNT_EMPTY`", code='''
def TEST(client, admin, librarian, branch_a):
    copy(client, librarian, branch_a, "A-01")
    qq = create_branch(client, admin, "QQ")
    err(try_count(client, librarian, qq), 409, "COUNT_EMPTY")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_count(client, librarian, qq), 409, "BRANCH_INACTIVE")
    err(try_count(client, librarian, branch_a, "Z-"), 409, "COUNT_EMPTY")
'''),
    dict(id="T-INV-04-a", req="LIB-INV-04", type="Boundary", input="Open count with prefix `A-1`; new counts `A-2`, `A-`, `a-12`, without prefix; the same at branch B", expected="201; `COUNT_SCOPE_OVERLAP` with `details.count_id` three times; B 201", code='''
def TEST(client, librarian, branch_a, branch_b):
    for shelf in ("A-10", "A-20", "A-12", "A-30"):
        copy(client, librarian, branch_a, shelf)
    copy(client, librarian, branch_b, "A-11")
    first = count(client, librarian, branch_a, "A-1")
    second = count(client, librarian, branch_a, "A-2")
    assert err(try_count(client, librarian, branch_a, "a-12"), 409, "COUNT_SCOPE_OVERLAP")["details"]["count_id"] == first["id"]
    for prefix in ("A-", None):
        assert err(try_count(client, librarian, branch_a, prefix), 409, "COUNT_SCOPE_OVERLAP")["details"]["count_id"] in (first["id"], second["id"]), prefix
    count(client, librarian, branch_b)
'''),
    dict(id="T-INV-05-a", req="LIB-INV-05", type="Normal", input="Counts K1 (A) and K2 (B); K1 with 3 expected copies, 2 scanned and an unknown barcode; list; `branch_id` A; K1", expected="[K2, K1]; [K1]; `progress` `{expected 3, scanned_expected 2, remaining 1}`, `problems.unknown` 1", code='''
def TEST(client, librarian, branch_a, branch_b):
    cs = [copy(client, librarian, branch_a) for _ in range(3)]
    copy(client, librarian, branch_b)
    k1, k2 = count(client, librarian, branch_a), count(client, librarian, branch_b)
    ok(scan(client, librarian, k1, cs[0]["barcode"], cs[1]["barcode"], "NOPE-0001"), 201)
    assert [x["id"] for x in items(get(client, librarian, "inventory-counts"))] == [k2["id"], k1["id"]]
    assert [x["id"] for x in items(get(client, librarian, "inventory-counts", branch_id=branch_a["id"]))] == [k1["id"]]
    p = get(client, librarian, f"inventory-counts/{k1['id']}")["progress"]
    assert (p["expected"], p["scanned_expected"], p["remaining"], p["problems"]["unknown"], p["problems"]["duplicate"]) == (3, 2, 1, 1, 0)
'''),
    dict(id="T-INV-06-a", req="LIB-INV-06", type="Normal", input="Cancel an open count; cancel it again; cancel an applied count", expected="200 `cancelled` with `staff_request`; `409 INVALID_COUNT_STATUS` with `details.status` `cancelled`; `409 INVALID_COUNT_STATUS`", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    out = ok(step(client, librarian, k, "cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    assert err(step(client, librarian, k, "cancel"), 409, "INVALID_COUNT_STATUS")["details"]["status"] == "cancelled"
    k2 = count(client, librarian, branch_a)
    scanned(client, librarian, k2, cp)
    ok(step(client, librarian, k2, "close"))
    ok(step(client, librarian, k2, "apply"))
    err(step(client, librarian, k2, "cancel"), 409, "INVALID_COUNT_STATUS")
'''),
    # ---------------------------------------------------------------- scanning
    dict(id="T-INV-07-a", req="LIB-INV-07", type="Error", input="Scan a lower-case barcode; scan 0 and 201 barcodes; scan into a closed count", expected="201 with `expected`; `422`; `422`; `409 INVALID_COUNT_STATUS`", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    out = ok(scan(client, librarian, k, cp["barcode"].lower()), 201)["scans"]
    assert [(s["barcode"], s["copy_id"], s["result"]) for s in out] == [(cp["barcode"], cp["id"], "expected")]
    assert scan(client, librarian, k).status_code == 422
    assert scan(client, librarian, k, *[f"X{i:05d}" for i in range(201)]).status_code == 422
    ok(step(client, librarian, k, "close"))
    err(scan(client, librarian, k, cp["barcode"]), 409, "INVALID_COUNT_STATUS")
'''),
    dict(id="T-INV-08-a", req="LIB-INV-08", type="Normal", input="One request: expected copy twice; a withdrawn copy; a copy in transfer to A", expected="`expected`, `duplicate`, `withdrawn`, `wrong_branch`", code='''
def TEST(client, librarian, branch_a, branch_b):
    cp = copy(client, librarian, branch_a)
    w = copy(client, librarian, branch_a)
    ok(post(client, librarian, f"copies/{w['id']}/withdraw", {"reason": "Yıpranmış kopya"}))
    t = copy(client, librarian, branch_b)
    ok(post(client, librarian, "transfers", {"copy_id": t["id"], "to_branch_id": branch_a["id"]}), 201)
    k = count(client, librarian, branch_a)
    out = scanned(client, librarian, k, cp, cp, w, t)
    assert [s["result"] for s in out] == ["expected", "duplicate", "withdrawn", "wrong_branch"]
'''),
    dict(id="T-INV-09-a", req="LIB-INV-09", type="Normal", input="Count of A with prefix `A-`: copy on `A-12`, again, copy on `B-01` at A, copy lent from A (shelf `A-13`), available copy of B, lost copy, `NOPE-0001`", expected="`expected`, `duplicate`, `out_of_scope`, `unexpected_status`, `wrong_branch`, `found_lost`, `unknown`", code='''
def TEST(client, librarian, branch_a, branch_b):
    a12, b01 = copy(client, librarian, branch_a, "A-12"), copy(client, librarian, branch_a, "B-01")
    out = copy(client, librarian, branch_a, "A-13")
    other, lost = copy(client, librarian, branch_b), lost_copy(client, librarian, branch_a)
    lend(client, librarian, member(client, librarian, branch_a)["id"], out["id"])
    k = count(client, librarian, branch_a, "A-")
    res = ok(scan(client, librarian, k, a12["barcode"], a12["barcode"], b01["barcode"], out["barcode"], other["barcode"], lost["barcode"], "NOPE-0001"), 201)["scans"]
    assert [s["result"] for s in res] == ["expected", "duplicate", "out_of_scope", "unexpected_status", "wrong_branch", "found_lost", "unknown"]
    assert res[-1]["copy_id"] is None
'''),
    dict(id="T-INV-10-a", req="LIB-INV-10", type="Normal", input="Count started; a new copy added at A afterwards and scanned", expected="`out_of_scope`; `expected_count` unchanged", code='''
def TEST(client, librarian, branch_a):
    copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    new = copy(client, librarian, branch_a)
    assert [s["result"] for s in scanned(client, librarian, k, new)] == ["out_of_scope"]
    assert get(client, librarian, f"inventory-counts/{k['id']}")["expected_count"] == 1
'''),
    dict(id="T-INV-11-a", req="LIB-INV-11", type="Normal", input="Scans: expected, unknown, expected; list; `result=unknown`", expected="Three scans in order; one `unknown`", code='''
def TEST(client, librarian, branch_a):
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(scan(client, librarian, k, c1["barcode"], "NOPE-0001", c2["barcode"]), 201)
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/scans"))
    assert [r["barcode"] for r in rows] == [c1["barcode"], "NOPE-0001", c2["barcode"]]
    assert [r["barcode"] for r in items(get(client, librarian, f"inventory-counts/{k['id']}/scans", result="unknown"))] == ["NOPE-0001"]
'''),
    dict(id="T-INV-12-a", req="LIB-INV-12", type="Normal", input="Copy scanned twice; the first scan removed; then the second; removing a scan of a closed count", expected="204; still scanned (`remaining` 0); 204 and `remaining` 1; `409 INVALID_COUNT_STATUS`", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    s1, s2 = scanned(client, librarian, k, cp, cp)
    assert client.delete(f"/api/v1/inventory-scans/{s1['id']}", headers=librarian).status_code == 204
    assert get(client, librarian, f"inventory-counts/{k['id']}")["progress"]["remaining"] == 0
    assert client.delete(f"/api/v1/inventory-scans/{s2['id']}", headers=librarian).status_code == 204
    assert get(client, librarian, f"inventory-counts/{k['id']}")["progress"]["remaining"] == 1
    s3 = scanned(client, librarian, k, cp)[0]
    ok(step(client, librarian, k, "close"))
    err(client.delete(f"/api/v1/inventory-scans/{s3['id']}", headers=librarian), 409, "INVALID_COUNT_STATUS")
'''),
    dict(id="T-INV-13-a", req="LIB-INV-13", type="Error", input="Copy expected in an open count: relocation; withdrawal; lending; after cancelling the count, relocation", expected="`COPY_IN_COUNT` with `details.count_id` twice; lending 201; relocation 201", code='''
def TEST(client, librarian, branch_a, branch_b):
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    assert err(post(client, librarian, "transfers", {"copy_id": c1["id"], "to_branch_id": branch_b["id"]}), 409, "COPY_IN_COUNT")["details"]["count_id"] == k["id"]
    err(post(client, librarian, f"copies/{c1['id']}/withdraw", {"reason": "Eski kopya"}), 409, "COPY_IN_COUNT")
    lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    ok(step(client, librarian, k, "cancel"))
    ok(post(client, librarian, "transfers", {"copy_id": c1["id"], "to_branch_id": branch_b["id"]}), 201)
'''),
    # ---------------------------------------------------------------- closing and applying
    dict(id="T-INV-14-a", req="LIB-INV-14", type="Normal", input="Expected C1, C2: C1 scanned; close", expected="200 `closed` with `closed_at`; lines C1 `found`, C2 `missing`", code='''
def TEST(client, librarian, branch_a):
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, c1)
    out = ok(step(client, librarian, k, "close"))
    assert out["status"] == "closed" and same(out["closed_at"], MON, 9)
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/lines"))
    assert [(r["copy_id"], r["outcome"]) for r in rows] == [(c1["id"], "found"), (c2["id"], "missing")]
'''),
    dict(id="T-INV-15-a", req="LIB-INV-15", type="Boundary", input="Count whose two expected copies are both lent before closing", expected="`summary` `{expected 2, found 0, missing 0, moved 2, accuracy 100.0}`", code='''
def TEST(client, librarian, branch_a):
    cs = [copy(client, librarian, branch_a) for _ in range(2)]
    k = count(client, librarian, branch_a)
    for c in cs:
        lend(client, librarian, member(client, librarian, branch_a)["id"], c["id"])
    assert ok(step(client, librarian, k, "close"))["summary"] == {"expected": 2, "found": 0, "missing": 0, "moved": 2, "accuracy": "100.0"}
'''),
    dict(id="T-INV-16-a", req="LIB-INV-16", type="Normal", input="Expected C1–C5: C1–C3 scanned, C4 lent after the start, C5 not scanned; close", expected="`summary` `{expected 5, found 3, missing 1, moved 1, accuracy 75.0}`", code='''
def TEST(client, librarian, branch_a):
    cs = [copy(client, librarian, branch_a) for _ in range(5)]
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, *cs[:3])
    lend(client, librarian, member(client, librarian, branch_a)["id"], cs[3]["id"])
    assert ok(step(client, librarian, k, "close"))["summary"] == {"expected": 5, "found": 3, "missing": 1, "moved": 1, "accuracy": "75.0"}
'''),
    dict(id="T-INV-17-a", req="LIB-INV-17", type="Error", input="Lines of an open count; after closing `outcome=missing`", expected="`409 INVALID_COUNT_STATUS`; the missing copy with `barcode`, `book_title`, `shelf_location`", code='''
def TEST(client, librarian, branch_a):
    c1, c2 = copy(client, librarian, branch_a, "A-01"), copy(client, librarian, branch_a, "A-02")
    k = count(client, librarian, branch_a)
    err(client.get(f"/api/v1/inventory-counts/{k['id']}/lines", headers=librarian), 409, "INVALID_COUNT_STATUS")
    scanned(client, librarian, k, c1)
    ok(step(client, librarian, k, "close"))
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/lines", outcome="missing"))
    assert [(r["copy_id"], r["barcode"], r["book_title"], r["shelf_location"]) for r in rows] == [(c2["id"], c2["barcode"], "Sayım Kitabı", "A-02")]
'''),
    dict(id="T-INV-18-a", req="LIB-INV-18", type="Normal", input="At A: C1 scanned, C2 not scanned, a lost copy of A scanned, an available copy of B scanned; close and apply; apply again", expected="`{missing_marked 1, found 1, relocated 1}`; C2 `missing` since today; the lost copy `available` at A; B's copy `in_transfer` home; `409 INVALID_COUNT_STATUS`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-INV-18-b", req="LIB-INV-18", type="Normal", input="C2 missing at closing but lent before applying", expected="`missing_marked` 0; C2 stays `on_loan`", code='''
def TEST(client, librarian, branch_a):
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, c1)
    ok(step(client, librarian, k, "close"))
    lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    assert ok(step(client, librarian, k, "apply"))["missing_marked"] == 0
    assert copy_of(client, librarian, c2["id"])["status"] == "on_loan"
'''),
    dict(id="T-INV-19-a", req="LIB-INV-19", type="Boundary", input="Count with 10 missing copies applied by a librarian; another with 11 by a librarian, then by an admin", expected="200; `403`; 200", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    for br in (branch_a, branch_b):
        for _ in range(10 if br is branch_a else 11):
            copy(client, librarian, br)
    ka, kb = count(client, librarian, branch_a), count(client, librarian, branch_b)
    for k in (ka, kb):
        ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, ka, "apply"))
    assert step(client, librarian, kb, "apply").status_code == 403
    ok(step(client, admin, kb, "apply"))
'''),
    dict(id="T-INV-20-a", req="LIB-INV-20", type="Normal", input="An `on_hold` copy of a ready reservation is not scanned; close and apply", expected="Copy `missing`; reservation `waiting` with `copy_id`, `ready_on`, `hold_until` null; one `reservation_delayed` notification naming the title", code='''
def TEST(client, librarian, branch_a):
    cp, res, m = held_copy(client, librarian, branch_a)
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "ready"
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert copy_of(client, librarian, cp["id"])["status"] == "missing"
    r = get(client, librarian, f"reservations/{res['id']}")
    assert (r["status"], r["copy_id"], r["ready_on"], r["hold_until"]) == ("waiting", None, None, None)
    ns = notes(client, librarian, m["id"], "reservation_delayed")
    assert len(ns) == 1 and "Ayrılmış Kitap" in ns[0]["message"]
'''),
    dict(id="T-INV-21-a", req="LIB-INV-21", type="Normal", input="The only copy on reserve for a course's item is not scanned; close and apply", expected="Copy `missing` with `reserve_item_id` null; the item `requested`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-INV-22-a", req="LIB-INV-22", type="Error", input="Missing copy found at A; lost copy found at A; available copy found; found at an inactive branch", expected="200 `available` with `missing_since` null twice; `409 INVALID_COPY_STATUS`; `409 BRANCH_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    miss = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    lost = lost_copy(client, librarian, branch_a)
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(post(client, librarian, f"copies/{lost['id']}/found", {"branch_id": qq["id"]}), 409, "BRANCH_INACTIVE")
    for cp in (miss, lost):
        out = ok(post(client, librarian, f"copies/{cp['id']}/found", {"branch_id": branch_a["id"]}))
        assert (out["status"], out["missing_since"], out["current_branch_id"]) == ("available", None, branch_a["id"])
    err(post(client, librarian, f"copies/{miss['id']}/found", {"branch_id": branch_a["id"]}), 409, "INVALID_COPY_STATUS")
'''),
    dict(id="T-INV-23-a", req="LIB-INV-23", type="Normal", input="An open count of A and a missing copy of B; process on 2027-01-31", expected="`{expired_counts 1, marked_lost 1}`; count `cancelled` with `expired`; copy `lost` with branch null", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-INV-24-a", req="LIB-INV-24", type="Boundary", input="Count started Mon 09:00, processed on 2026-11-09 09:00 and 09:00:01; copy missing since 2026-11-02 processed on 2027-01-30 and 2027-01-31", expected="`expired_counts` 0 then 1; `marked_lost` 0 then 1", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    copy(client, librarian, branch_a)
    copy(client, librarian, branch_b)
    count(client, librarian, branch_a)
    kb = count(client, librarian, branch_b)
    ok(step(client, librarian, kb, "close"))
    ok(step(client, librarian, kb, "apply"))
    at(clock, "2026-11-09", 9, 0, 0)
    assert ok(post(client, librarian, "inventory/process"))["expired_counts"] == 0
    at(clock, "2026-11-09", 9, 0, 1)
    assert ok(post(client, librarian, "inventory/process"))["expired_counts"] == 1
    at(clock, "2027-01-30")
    assert ok(post(client, librarian, "inventory/process"))["marked_lost"] == 0
    at(clock, "2027-01-31")
    assert ok(post(client, librarian, "inventory/process"))["marked_lost"] == 1
'''),
    dict(id="T-INV-25-a", req="LIB-INV-25", type="Normal", input="Book with a missing and an available copy; copies with `status=missing`", expected="Only the missing copy, with `missing_since`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    miss = copy(client, librarian, branch_a, book=b)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    copy(client, librarian, branch_a, book=b)
    rows = items(get(client, librarian, f"books/{b['id']}/copies", status="missing"))
    assert [(r["id"], r["missing_since"]) for r in rows] == [(miss["id"], MON)]
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-INV-26-a", req="LIB-INV-26", type="Error", input="A missing copy: lent; relocated; withdrawn", expected="`409 COPY_NOT_AVAILABLE` with `details.status` `missing`; `409 INVALID_COPY_STATUS`; 200", code='''
def TEST(client, librarian, branch_a, branch_b):
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "missing"
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    assert ok(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Bulunamadı"}))["status"] == "withdrawn"
'''),
    dict(id="T-INV-27-a", req="LIB-INV-27", type="Normal", input="Book whose only copy at A becomes missing; book availability; a reservation for it", expected="No `availability` row with copies; `409 BOOK_NOT_LENDABLE`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    copy(client, librarian, branch_a, book=b)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert [r for r in get(client, librarian, f"books/{b['id']}")["availability"] if r["total"] > 0] == []
    r = post(client, librarian, "reservations", {"book_id": b["id"], "pickup_branch_id": branch_a["id"], "member_id": member(client, librarian, branch_a)["id"]})
    err(r, 409, "BOOK_NOT_LENDABLE")
'''),
    dict(id="T-INV-28-a", req="LIB-INV-28", type="Normal", input="A lost copy scanned in an open count", expected="The copy stays `lost` until the count is applied", code='''
def TEST(client, librarian, branch_a):
    copy(client, librarian, branch_a)
    lost = lost_copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    assert [s["result"] for s in scanned(client, librarian, k, lost)] == ["found_lost"]
    assert copy_of(client, librarian, lost["id"])["status"] == "lost"
    ok(step(client, librarian, k, "close"))
    assert copy_of(client, librarian, lost["id"])["status"] == "lost"
'''),
    dict(id="T-INV-29-a", req="LIB-INV-29", type="Error", input="Closure of A on Tue 2026-11-03; counts started on Sat 2026-11-07, on Tue 2026-11-03 and on Mon 2026-11-09", expected="`409 BRANCH_NOT_OPEN` twice; 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
    copy(client, librarian, branch_a)
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": "2026-11-03", "reason": "Sayım"}), 201)
    at(clock, "2026-11-07", 10)
    err(try_count(client, librarian, branch_a), 409, "BRANCH_NOT_OPEN")
    at(clock, "2026-11-03", 10)
    err(try_count(client, librarian, branch_a), 409, "BRANCH_NOT_OPEN")
    at(clock, "2026-11-09", 10)
    count(client, librarian, branch_a)
'''),
    dict(id="T-INV-30-a", req="LIB-INV-30", type="Normal", input="The member whose lost copy is found by a count; the count is applied", expected="The member's notifications do not change", code='''
def TEST(client, librarian, branch_a):
    copy(client, librarian, branch_a)
    cp = copy(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"])
    before = get(client, librarian, f"members/{m['id']}/notifications")["total"]
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, cp)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == before
'''),
    dict(id="T-INV-31-a", req="LIB-INV-31", type="Normal", input="Count started, two scan requests, a scan removed, closed, applied; another started and cancelled; a copy found; process; audit log", expected="One entry per event (two for `inventory_scans_added` and `inventory_count_started`)", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-INV-32-a", req="LIB-INV-32", type="Normal", input="Branch A: count with 4 expected (3 found, 1 missing) and a lost copy found, applied; count of B not applied; report 2026", expected="Only A: `{counts_applied 1, last_applied_on 2026-11-02, expected 4, found 3, missing 1, accuracy 75.0, missing_now 1, found_again 1}`", code='''
def TEST(client, librarian, branch_a, branch_b):
    cs = [copy(client, librarian, branch_a) for _ in range(4)]
    lost = lost_copy(client, librarian, branch_a)
    copy(client, librarian, branch_b)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, *cs[:3], lost)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    count(client, librarian, branch_b)
    rows = items(get(client, librarian, "reports/inventory", year=2026))
    keys = ("branch_id", "counts_applied", "last_applied_on", "expected", "found", "missing", "accuracy", "missing_now", "found_again")
    assert [tuple(r[k] for k in keys) for r in rows] == [(branch_a["id"], 1, MON, 4, 3, 1, "75.0", 1, 1)]
'''),
    dict(id="T-INV-33-a", req="LIB-INV-33", type="Normal", input="A missing copy; `GET /api/v1/export`", expected="The keys of 22.1; the copy has status `lost` and no `missing_since`", code='''
def TEST(client, admin, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == cp["id"]] == ["lost"]
    assert all("missing_since" not in c for c in out["copies"])
'''),
    dict(id="T-INV-34-a", req="LIB-INV-34", type="Normal", input="A member's ready reservation sent back to `waiting` by an applied count; the member summary", expected="`active_reservations` 1", code='''
def TEST(client, librarian, branch_a):
    _, _, m = held_copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert get(client, librarian, f"members/{m['id']}/summary")["active_reservations"] == 1
'''),
]
