"""Heldout tests: module 24 (Inventory counts). Generated from cases/inventory.md."""
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


def test_t_inv_01_b(client, librarian, branch_a):
    """T-INV-01-b (LIB-INV-01): 422 three times; 403"""
    copy(client, librarian, branch_a)
    assert try_count(client, librarian, branch_a, name="").status_code == 422
    assert try_count(client, librarian, branch_a, prefix="A" * 21).status_code == 422
    assert try_count(client, librarian, {"id": 999999}).status_code == 422
    assert try_count(client, member_headers(client, member(client, librarian, branch_a)), branch_a).status_code == 403


def test_t_inv_02_a(client, librarian, branch_a):
    """T-INV-02-a (LIB-INV-02): expected = the A-12 and a-30 copies"""
    a12 = copy(client, librarian, branch_a, "A-12")
    held, _, _ = held_copy(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/copies/{held['id']}", headers=librarian, json={"shelf_location": "a-30"}))
    copy(client, librarian, branch_a, "B-01")
    copy(client, librarian, branch_a)
    lost = lost_copy(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/copies/{lost['id']}", headers=librarian, json={"shelf_location": "A-99"}))
    c = count(client, librarian, branch_a, "A-")
    assert (c["expected"], c["expected_count"]) == ([a12["id"], held["id"]], 2)


def test_t_inv_04_a(client, librarian, branch_a, branch_b):
    """T-INV-04-a (LIB-INV-04): 201; COUNT_SCOPE_OVERLAP with details.count_id three times; B 201"""
    for shelf in ("A-10", "A-20", "A-12", "A-30"):
        copy(client, librarian, branch_a, shelf)
    copy(client, librarian, branch_b, "A-11")
    first = count(client, librarian, branch_a, "A-1")
    second = count(client, librarian, branch_a, "A-2")
    assert err(try_count(client, librarian, branch_a, "a-12"), 409, "COUNT_SCOPE_OVERLAP")["details"]["count_id"] == first["id"]
    for prefix in ("A-", None):
        assert err(try_count(client, librarian, branch_a, prefix), 409, "COUNT_SCOPE_OVERLAP")["details"]["count_id"] in (first["id"], second["id"]), prefix
    count(client, librarian, branch_b)


def test_t_inv_06_a(client, librarian, branch_a):
    """T-INV-06-a (LIB-INV-06): 200 cancelled with staff_request; 409 INVALID_COUNT_STATUS with details.status cancelled; 409 INVALID_COUNT_STATUS"""
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


def test_t_inv_08_a(client, librarian, branch_a, branch_b):
    """T-INV-08-a (LIB-INV-08): expected, duplicate, withdrawn, wrong_branch"""
    cp = copy(client, librarian, branch_a)
    w = copy(client, librarian, branch_a)
    ok(post(client, librarian, f"copies/{w['id']}/withdraw", {"reason": "Yıpranmış kopya"}))
    t = copy(client, librarian, branch_b)
    ok(post(client, librarian, "transfers", {"copy_id": t["id"], "to_branch_id": branch_a["id"]}), 201)
    k = count(client, librarian, branch_a)
    out = scanned(client, librarian, k, cp, cp, w, t)
    assert [s["result"] for s in out] == ["expected", "duplicate", "withdrawn", "wrong_branch"]


def test_t_inv_10_a(client, librarian, branch_a):
    """T-INV-10-a (LIB-INV-10): out_of_scope; expected_count unchanged"""
    copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    new = copy(client, librarian, branch_a)
    assert [s["result"] for s in scanned(client, librarian, k, new)] == ["out_of_scope"]
    assert get(client, librarian, f"inventory-counts/{k['id']}")["expected_count"] == 1


def test_t_inv_12_a(client, librarian, branch_a):
    """T-INV-12-a (LIB-INV-12): 204; still scanned (remaining 0); 204 and remaining 1; 409 INVALID_COUNT_STATUS"""
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


def test_t_inv_14_a(client, librarian, branch_a):
    """T-INV-14-a (LIB-INV-14): 200 closed with closed_at; lines C1 found, C2 missing"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, c1)
    out = ok(step(client, librarian, k, "close"))
    assert out["status"] == "closed" and same(out["closed_at"], MON, 9)
    rows = items(get(client, librarian, f"inventory-counts/{k['id']}/lines"))
    assert [(r["copy_id"], r["outcome"]) for r in rows] == [(c1["id"], "found"), (c2["id"], "missing")]


def test_t_inv_16_a(client, librarian, branch_a):
    """T-INV-16-a (LIB-INV-16): summary {expected 5, found 3, missing 1, moved 1, accuracy 75.0}"""
    cs = [copy(client, librarian, branch_a) for _ in range(5)]
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, *cs[:3])
    lend(client, librarian, member(client, librarian, branch_a)["id"], cs[3]["id"])
    assert ok(step(client, librarian, k, "close"))["summary"] == {"expected": 5, "found": 3, "missing": 1, "moved": 1, "accuracy": "75.0"}


def test_t_inv_18_b(client, librarian, branch_a):
    """T-INV-18-b (LIB-INV-18): missing_marked 0; C2 stays on_loan"""
    c1, c2 = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    scanned(client, librarian, k, c1)
    ok(step(client, librarian, k, "close"))
    lend(client, librarian, member(client, librarian, branch_a)["id"], c2["id"])
    assert ok(step(client, librarian, k, "apply"))["missing_marked"] == 0
    assert copy_of(client, librarian, c2["id"])["status"] == "on_loan"


def test_t_inv_20_a(client, librarian, branch_a):
    """T-INV-20-a (LIB-INV-20): Copy missing; reservation waiting with copy_id, ready_on, hold_until null; one reservation_delayed notification naming the title"""
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


def test_t_inv_22_a(client, admin, librarian, branch_a):
    """T-INV-22-a (LIB-INV-22): 200 available with missing_since null twice; 409 INVALID_COPY_STATUS; 409 BRANCH_INACTIVE"""
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


def test_t_inv_24_a(client, clock, librarian, branch_a, branch_b):
    """T-INV-24-a (LIB-INV-24): expired_counts 0 then 1; marked_lost 0 then 1"""
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


def test_t_inv_26_a(client, librarian, branch_a, branch_b):
    """T-INV-26-a (LIB-INV-26): 409 COPY_NOT_AVAILABLE with details.status missing; 409 INVALID_COPY_STATUS; 200"""
    cp = copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "missing"
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    assert ok(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Bulunamadı"}))["status"] == "withdrawn"


def test_t_inv_28_a(client, librarian, branch_a):
    """T-INV-28-a (LIB-INV-28): The copy stays lost until the count is applied"""
    copy(client, librarian, branch_a)
    lost = lost_copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    assert [s["result"] for s in scanned(client, librarian, k, lost)] == ["found_lost"]
    assert copy_of(client, librarian, lost["id"])["status"] == "lost"
    ok(step(client, librarian, k, "close"))
    assert copy_of(client, librarian, lost["id"])["status"] == "lost"


def test_t_inv_30_a(client, librarian, branch_a):
    """T-INV-30-a (LIB-INV-30): The member's notifications do not change"""
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


def test_t_inv_32_a(client, librarian, branch_a, branch_b):
    """T-INV-32-a (LIB-INV-32): Only A: {counts_applied 1, last_applied_on 2026-11-02, expected 4, found 3, missing 1, accuracy 75.0, missing_now 1, found_again 1}"""
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


def test_t_inv_34_a(client, librarian, branch_a):
    """T-INV-34-a (LIB-INV-34): active_reservations 1"""
    _, _, m = held_copy(client, librarian, branch_a)
    k = count(client, librarian, branch_a)
    ok(step(client, librarian, k, "close"))
    ok(step(client, librarian, k, "apply"))
    assert get(client, librarian, f"members/{m['id']}/summary")["active_reservations"] == 1
