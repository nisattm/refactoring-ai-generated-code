"""Heldout tests: module 25 (Purchase suggestions). Generated from cases/suggestions.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_member, error_code, items, lend, member_headers, register_member,
    report_lost,
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


def mh(client, m):
    return member_headers(client, m)


def try_sug(client, headers, branch, **fields):
    _seq[0] += 1
    body = {"title": f"Önerilen Kitap {_seq[0]:03d}", "branch_id": branch["id"]}
    body.update(fields)
    return post(client, headers, "suggestions", body)


def sug(client, headers, branch, **fields):
    return ok(try_sug(client, headers, branch, **fields), 201)


def by(client, lib, branch, type_="student", **fields):
    """A suggestion of a new member of ``type_``: (suggestion, member, headers)."""
    m = member(client, lib, branch, membership_type=type_)
    h = mh(client, m)
    return sug(client, h, branch, **fields), m, h


def try_approve(client, headers, s, book, qty=1, price="40.00", note=None):
    body = {"book_id": book["id"], "quantity": qty, "estimated_price": price}
    if note is not None:
        body["review_note"] = note
    return post(client, headers, f"suggestions/{s['id']}/approve", body)


def approve(client, headers, s, book, qty=1, price="40.00"):
    return ok(try_approve(client, headers, s, book, qty, price))


def reject(client, headers, s, reason="out_of_scope", **extra):
    return post(client, headers, f"suggestions/{s['id']}/reject", {"reject_reason": reason, "review_note": "", **extra})


def support(client, headers, s, reserve=None):
    body = {} if reserve is None else {"reserve_on_arrival": reserve}
    return post(client, headers, f"suggestions/{s['id']}/support", body)


def supplier(client, lib):
    _seq[0] += 1
    return ok(post(client, lib, "suppliers", {"name": f"Yayın Dağıtım {_seq[0]}", "email": None, "phone": None}), 201)


def order(client, lib, sup, branch, *sugs):
    return post(client, lib, "suggestions/order", {"supplier_id": sup["id"], "branch_id": branch["id"], "suggestion_ids": [s["id"] for s in sugs]})


def receive(client, lib, order_, book, n=1):
    line = [l for l in order_["lines"] if l["book_id"] == book["id"]][0]
    _seq[0] += 1
    codes = [f"SG{_seq[0]:04d}{i}" for i in range(n)]
    return ok(post(client, lib, f"purchase-orders/{order_['id']}/receive", {"lines": [{"line_id": line["id"], "barcodes": codes}]}))


def ordered(client, lib, branch, *sugs):
    """Submit an order of the approved ``sugs`` at ``branch``."""
    o = ok(order(client, lib, supplier(client, lib), branch, *sugs), 201)
    ok(post(client, lib, f"purchase-orders/{o['id']}/submit"))
    return o


def sug_of(client, headers, s):
    return get(client, headers, f"suggestions/{s['id']}")


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def reservations_of(client, lib, member_id):
    return items(get(client, lib, f"members/{member_id}/reservations"))


def test_t_sug_01_b(client, librarian, branch_a):
    """T-SUG-01-b (LIB-SUG-01): 422 five times; 201 for the member"""
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert try_sug(client, h, branch_a, title="").status_code == 422
    assert try_sug(client, h, branch_a, publication_year=2027).status_code == 422
    assert try_sug(client, h, branch_a, isbn="9780000000000").status_code == 422
    assert try_sug(client, h, branch_a, member_id=m["id"]).status_code == 422
    assert try_sug(client, librarian, branch_a).status_code == 422
    assert sug(client, librarian, branch_a, member_id=m["id"])["member_id"] == m["id"]


def test_t_sug_02_a(client, librarian, branch_a):
    """T-SUG-02-a (LIB-SUG-02): score 2, supporters 1; A mine true, supported_by_me false; B mine false, supported_by_me true; C both false"""
    s, a, ah = by(client, librarian, branch_a)
    bh, ch = mh(client, member(client, librarian, branch_a)), mh(client, member(client, librarian, branch_a))
    ok(support(client, bh, s), 201)
    rows = [sug_of(client, h, s) for h in (ah, bh, ch)]
    assert [(r["score"], r["supporters"], r["mine"], r["supported_by_me"]) for r in rows] == [(2, 1, True, False), (2, 1, False, True), (2, 1, False, False)]


def test_t_sug_03_b(client, librarian, branch_a):
    """T-SUG-03-b (LIB-SUG-03): BOOK_ALREADY_OWNED with details.book_id; DUPLICATE_SUGGESTION with details.suggestion_id"""
    owned = create_book(client, librarian)
    add_copy(client, librarian, owned["id"], home_branch_id=branch_a["id"])
    h = mh(client, member(client, librarian, branch_a))
    assert err(try_sug(client, h, branch_a, isbn=owned["isbn"]), 409, "BOOK_ALREADY_OWNED")["details"]["book_id"] == owned["id"]
    isbn = create_book(client, librarian)["isbn"]
    first, _, _ = by(client, librarian, branch_a, isbn=isbn)
    assert err(try_sug(client, h, branch_a, isbn=isbn), 409, "DUPLICATE_SUGGESTION")["details"]["suggestion_id"] == first["id"]


def test_t_sug_04_b(client, clock, librarian, branch_a):
    """T-SUG-04-b (LIB-SUG-04): SUGGESTION_RECENTLY_REJECTED with details.until 2027-05-01; 201"""
    isbn = create_book(client, librarian)["isbn"]
    s, m, h = by(client, librarian, branch_a, isbn=isbn)
    ok(reject(client, librarian, s))
    at(clock, "2027-04-30")
    assert err(try_sug(client, h, branch_a, isbn=isbn), 409, "SUGGESTION_RECENTLY_REJECTED")["details"]["until"] == "2027-05-01"
    at(clock, "2027-05-01")
    sug(client, h, branch_a, isbn=isbn)


def test_t_sug_06_a(client, librarian, branch_a):
    """T-SUG-06-a (LIB-SUG-06): 200 withdrawn with member_request; 409 INVALID_SUGGESTION_STATUS; 200"""
    s1, _, h = by(client, librarian, branch_a)
    out = ok(post(client, h, f"suggestions/{s1['id']}/withdraw"))
    assert (out["status"], out["withdraw_reason"]) == ("withdrawn", "member_request")
    s2 = sug(client, h, branch_a)
    approve(client, librarian, s2, create_book(client, librarian))
    err(post(client, h, f"suggestions/{s2['id']}/withdraw"), 409, "INVALID_SUGGESTION_STATUS")
    assert ok(post(client, librarian, f"suggestions/{s2['id']}/withdraw"))["status"] == "withdrawn"


def test_t_sug_08_a(client, librarian, branch_a):
    """T-SUG-08-a (LIB-SUG-08): 204 and supporters 0; 404; 409 INVALID_SUGGESTION_STATUS"""
    s, _, _ = by(client, librarian, branch_a)
    bh, ch = mh(client, member(client, librarian, branch_a)), mh(client, member(client, librarian, branch_a))
    ok(support(client, bh, s), 201)
    url = f"/api/v1/suggestions/{s['id']}/support"
    assert client.delete(url, headers=bh).status_code == 204
    assert sug_of(client, librarian, s)["supporters"] == 0
    assert client.delete(url, headers=bh).status_code == 404
    ok(support(client, ch, s), 201)
    ok(reject(client, librarian, s))
    err(client.delete(url, headers=ch), 409, "INVALID_SUGGESTION_STATUS")


def test_t_sug_10_a(client, librarian, branch_a):
    """T-SUG-10-a (LIB-SUG-10): [B, C] with full_name, membership_type, reserve_on_arrival; 403"""
    s, _, ah = by(client, librarian, branch_a)
    b, c = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    ok(support(client, mh(client, b), s), 201)
    ok(support(client, mh(client, c), s, reserve=False), 201)
    rows = items(get(client, librarian, f"suggestions/{s['id']}/supporters"))
    assert [(r["member_id"], r["full_name"], r["membership_type"], r["reserve_on_arrival"]) for r in rows] == [(b["id"], b["full_name"], "student", True), (c["id"], c["full_name"], "academic", False)]
    assert client.get(f"/api/v1/suggestions/{s['id']}/supporters", headers=ah).status_code == 403


def test_t_sug_12_a(client, librarian, branch_a):
    """T-SUG-12-a (LIB-SUG-12): Staff [S2, S1, S3]; [S2, S1]; member [S2, S1] without member_id; 404"""
    s1, _, _ = by(client, librarian, branch_a, title="Kozmos")
    s2, _, _ = by(client, librarian, branch_a, title="Simyacı")
    ok(support(client, mh(client, member(client, librarian, branch_a, membership_type="academic")), s2), 201)
    s3, _, _ = by(client, librarian, branch_a)
    ok(reject(client, librarian, s3))
    ids = lambda h, **p: [x["id"] for x in items(get(client, h, "suggestions", **p))]
    assert ids(librarian) == [s2["id"], s1["id"], s3["id"]]
    assert ids(librarian, status="submitted") == [s2["id"], s1["id"]]
    assert ids(librarian, q="kozm") == [s1["id"]]
    h = mh(client, member(client, librarian, branch_a))
    rows = items(get(client, h, "suggestions"))
    assert [r["id"] for r in rows] == [s2["id"], s1["id"]] and all("member_id" not in r or r["member_id"] is None for r in rows)
    assert client.get(f"/api/v1/suggestions/{s3['id']}", headers=h).status_code == 404


def test_t_sug_14_a(client, librarian, branch_a):
    """T-SUG-14-a (LIB-SUG-14): 409 SUGGESTION_HAS_SUPPORTERS; 200; 200"""
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    big, small = sug(client, h, branch_a), sug(client, h, branch_a)
    for i in range(3):
        sh = mh(client, member(client, librarian, branch_a))
        ok(support(client, sh, big), 201)
        if i < 2:
            ok(support(client, sh, small), 201)
    err(post(client, h, f"suggestions/{big['id']}/withdraw"), 409, "SUGGESTION_HAS_SUPPORTERS")
    ok(post(client, h, f"suggestions/{small['id']}/withdraw"))
    ok(post(client, librarian, f"suggestions/{big['id']}/withdraw"))


def test_t_sug_15_b(client, librarian, branch_a):
    """T-SUG-15-b (LIB-SUG-15): 422 three times; 403"""
    s, _, h = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    assert try_approve(client, librarian, s, x, 11).status_code == 422
    assert try_approve(client, librarian, s, x, 1, "0.00").status_code == 422
    assert try_approve(client, librarian, s, {"id": 999999}).status_code == 422
    assert try_approve(client, h, s, x).status_code == 403


def test_t_sug_16_a(client, librarian, branch_a):
    """T-SUG-16-a (LIB-SUG-16): INVALID_SUGGESTION_STATUS; ISBN_MISMATCH; 200"""
    x, y = create_book(client, librarian), create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, y)
    err(try_approve(client, librarian, s1, y), 409, "INVALID_SUGGESTION_STATUS")
    s2, _, _ = by(client, librarian, branch_a, isbn=x["isbn"])
    err(try_approve(client, librarian, s2, y), 409, "ISBN_MISMATCH")
    s3, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s3, y)


def test_t_sug_18_a(client, librarian, branch_a):
    """T-SUG-18-a (LIB-SUG-18): 422; 200; M and B have waiting reservations of X at A, C none"""
    x = create_book(client, librarian)
    cp = add_copy(client, librarian, x["id"], home_branch_id=branch_a["id"])
    lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    s, m, _ = by(client, librarian, branch_a)
    b, c = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(support(client, mh(client, b), s), 201)
    ok(support(client, mh(client, c), s, reserve=False), 201)
    assert reject(client, librarian, s, "already_owned").status_code == 422
    ok(reject(client, librarian, s, "already_owned", book_id=x["id"]))
    got = [[(r["book_id"], r["pickup_branch_id"], r["status"]) for r in reservations_of(client, librarian, p["id"])] for p in (m, b, c)]
    assert got == [[(x["id"], branch_a["id"], "waiting")], [(x["id"], branch_a["id"], "waiting")], []]


def test_t_sug_20_a(client, librarian, branch_a):
    """T-SUG-20-a (LIB-SUG-20): 403; the suggestion stays submitted"""
    s, _, _ = by(client, librarian, branch_a)
    assert try_approve(client, librarian, s, create_book(client, librarian), 4, "100.00").status_code == 403
    assert sug_of(client, librarian, s)["status"] == "submitted"


def test_t_sug_22_a(client, librarian, branch_a):
    """T-SUG-22-a (LIB-SUG-22): 200 with S2, S1 merged with merged_into_id; 422; 404; 409 INVALID_SUGGESTION_STATUS twice"""
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    assert post(client, librarian, f"suggestions/{s1['id']}/merge", {"into_suggestion_id": s1["id"]}).status_code == 422
    assert post(client, librarian, f"suggestions/{s1['id']}/merge", {"into_suggestion_id": 999999}).status_code == 404
    assert ok(post(client, librarian, f"suggestions/{s1['id']}/merge", {"into_suggestion_id": s2["id"]}))["id"] == s2["id"]
    out = sug_of(client, librarian, s1)
    assert (out["status"], out["merged_into_id"]) == ("merged", s2["id"])
    a, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, a, create_book(client, librarian))
    err(post(client, librarian, f"suggestions/{a['id']}/merge", {"into_suggestion_id": s2["id"]}), 409, "INVALID_SUGGESTION_STATUS")
    r, _, _ = by(client, librarian, branch_a)
    ok(reject(client, librarian, r))
    s3, _, _ = by(client, librarian, branch_a)
    err(post(client, librarian, f"suggestions/{s3['id']}/merge", {"into_suggestion_id": r["id"]}), 409, "INVALID_SUGGESTION_STATUS")


def test_t_sug_24_a(client, librarian, branch_a):
    """T-SUG-24-a (LIB-SUG-24): 200 quantity 3; 403; 409 INVALID_SUGGESTION_STATUS"""
    s, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s, create_book(client, librarian))
    url = f"/api/v1/suggestions/{s['id']}/approval"
    assert ok(client.patch(url, headers=librarian, json={"quantity": 3}))["quantity"] == 3
    assert client.patch(url, headers=librarian, json={"estimated_price": "120.00"}).status_code == 403
    t, _, _ = by(client, librarian, branch_a)
    err(client.patch(f"/api/v1/suggestions/{t['id']}/approval", headers=librarian, json={"quantity": 2}), 409, "INVALID_SUGGESTION_STATUS")


def test_t_sug_26_a(client, librarian, branch_a):
    """T-SUG-26-a (LIB-SUG-26): 201 draft order of P at A with line X 2 × 40.00; S1 ordered with purchase_order_id, ordered_at; one suggestion_ordered notification"""
    s, m, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x, 2, "40.00")
    sup = supplier(client, librarian)
    o = ok(order(client, librarian, sup, branch_a, s), 201)
    assert (o["status"], o["supplier_id"], o["branch_id"], [(l["book_id"], l["quantity"], l["unit_price"]) for l in o["lines"]]) == ("draft", sup["id"], branch_a["id"], [(x["id"], 2, "40.00")])
    out = sug_of(client, librarian, s)
    assert (out["status"], out["purchase_order_id"]) == ("ordered", o["id"]) and same(out["ordered_at"], MON, 9)
    assert len(notes(client, librarian, m["id"], "suggestion_ordered")) == 1


def test_t_sug_28_a(client, librarian, branch_a):
    """T-SUG-28-a (LIB-SUG-28): Lines X 3 × 45.00 and Y 1 × 20.00; total 155.00"""
    x, y = create_book(client, librarian), create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    s3, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, x, 2, "40.00")
    approve(client, librarian, s2, x, 1, "45.00")
    approve(client, librarian, s3, y, 1, "20.00")
    o = ok(order(client, librarian, supplier(client, librarian), branch_a, s1, s2, s3), 201)
    assert sorted((l["book_id"], l["quantity"], l["unit_price"]) for l in o["lines"]) == sorted([(x["id"], 3, "45.00"), (y["id"], 1, "20.00")])
    assert o["total"] == "155.00"


def test_t_sug_30_a(client, clock, librarian, branch_a):
    """T-SUG-30-a (LIB-SUG-30): S1 available with available_at; one suggestion_available notification each for M and B"""
    s, m, _ = by(client, librarian, branch_a)
    b = member(client, librarian, branch_a)
    ok(support(client, mh(client, b), s), 201)
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    o = ordered(client, librarian, branch_a, s)
    at(clock, "2026-11-05", 10)
    receive(client, librarian, o, x)
    out = sug_of(client, librarian, s)
    assert out["status"] == "available" and same(out["available_at"], "2026-11-05", 10)
    assert [len(notes(client, librarian, p["id"], "suggestion_available")) for p in (m, b)] == [1, 1]


def test_t_sug_32_a(client, librarian, branch_a):
    """T-SUG-32-a (LIB-SUG-32): A's reservation of X ready with the new copy; B's waiting; C has none; A, B, C get suggestion_available"""
    s, a, _ = by(client, librarian, branch_a)
    b, c = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(support(client, mh(client, b), s), 201)
    ok(support(client, mh(client, c), s, reserve=False), 201)
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    receive(client, librarian, ordered(client, librarian, branch_a, s), x)
    ra, rb = reservations_of(client, librarian, a["id"]), reservations_of(client, librarian, b["id"])
    assert [(r["book_id"], r["status"]) for r in ra] == [(x["id"], "ready")] and ra[0]["copy_id"] is not None
    assert [(r["book_id"], r["status"]) for r in rb] == [(x["id"], "waiting")]
    assert reservations_of(client, librarian, c["id"]) == []
    assert [len(notes(client, librarian, p["id"], "suggestion_available")) for p in (a, b, c)] == [1, 1, 1]


def test_t_sug_34_a(client, clock, librarian, branch_a):
    """T-SUG-34-a (LIB-SUG-34): expired_approved 0, then 1; expired; one suggestion_expired notification"""
    s, m, _ = by(client, librarian, branch_a)
    approve(client, librarian, s, create_book(client, librarian))
    at(clock, "2027-01-31", 9, 0, 0)
    assert ok(post(client, librarian, "suggestions/process"))["expired_approved"] == 0
    at(clock, "2027-01-31", 9, 0, 1)
    assert ok(post(client, librarian, "suggestions/process"))["expired_approved"] == 1
    assert sug_of(client, librarian, s)["status"] == "expired"
    assert len(notes(client, librarian, m["id"], "suggestion_expired")) == 1


def test_t_sug_36_a(client, librarian, branch_a):
    """T-SUG-36-a (LIB-SUG-36): Submitted → withdrawn with member_deactivated; approved stays; T has 0 supporters"""
    s1, m, h = by(client, librarian, branch_a)
    s2 = sug(client, h, branch_a)
    approve(client, librarian, s2, create_book(client, librarian))
    t, _, _ = by(client, librarian, branch_a)
    ok(support(client, h, t), 201)
    deactivate_member(client, librarian, m["id"])
    o1 = sug_of(client, librarian, s1)
    assert (o1["status"], o1["withdraw_reason"]) == ("withdrawn", "member_deactivated")
    assert sug_of(client, librarian, s2)["status"] == "approved"
    assert sug_of(client, librarian, t)["supporters"] == 0


def test_t_sug_38_a(client, librarian, branch_a):
    """T-SUG-38-a (LIB-SUG-38): {open 1, supported 1, available_this_year 1}; all 0"""
    s1, m, h = by(client, librarian, branch_a)
    s2 = sug(client, h, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s2, x)
    receive(client, librarian, ordered(client, librarian, branch_a, s2), x)
    t, _, _ = by(client, librarian, branch_a)
    ok(support(client, h, t), 201)
    assert get(client, librarian, f"members/{m['id']}/summary")["suggestions"] == {"open": 1, "supported": 1, "available_this_year": 1}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["suggestions"] == {"open": 0, "supported": 0, "available_this_year": 0}


def test_t_sug_40_a(client, librarian, branch_a):
    """T-SUG-40-a (LIB-SUG-40): suggestion_ids [S1, S2]; []"""
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, create_book(client, librarian)); approve(client, librarian, s2, create_book(client, librarian))
    sup = supplier(client, librarian)
    o = ok(order(client, librarian, sup, branch_a, s2, s1), 201)
    assert get(client, librarian, f"purchase-orders/{o['id']}")["suggestion_ids"] == [s1["id"], s2["id"]]
    manual = ok(post(client, librarian, "purchase-orders", {"supplier_id": sup["id"], "branch_id": branch_a["id"], "lines": []}), 201)
    assert get(client, librarian, f"purchase-orders/{manual['id']}")["suggestion_ids"] == []


def test_t_sug_42_a(client, librarian, branch_a):
    """T-SUG-42-a (LIB-SUG-42): A has no notifications"""
    s, a, h = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a)), s), 201)
    ok(client.patch(f"/api/v1/suggestions/{s['id']}", headers=h, json={"reason": "Çok istenen"}))
    t, _, _ = by(client, librarian, branch_a)
    ok(post(client, librarian, f"suggestions/{s['id']}/merge", {"into_suggestion_id": t["id"]}))
    assert get(client, librarian, f"members/{a['id']}/notifications")["total"] == 0


def test_t_sug_44_b(client, librarian, branch_a):
    """T-SUG-44-b (LIB-SUG-44): 422; 422; 403"""
    url = "/api/v1/reports/suggestions"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_sug_46_a(client, librarian, branch_a):
    """T-SUG-46-a (LIB-SUG-46): 409 INVALID_SUGGESTION_STATUS each"""
    s, _, h = by(client, librarian, branch_a)
    ok(post(client, h, f"suggestions/{s['id']}/withdraw"))
    err(client.patch(f"/api/v1/suggestions/{s['id']}", headers=h, json={"title": "X"}), 409, "INVALID_SUGGESTION_STATUS")
    err(support(client, mh(client, member(client, librarian, branch_a)), s), 409, "INVALID_SUGGESTION_STATUS")
    err(post(client, librarian, f"suggestions/{s['id']}/withdraw"), 409, "INVALID_SUGGESTION_STATUS")
    err(try_approve(client, librarian, s, create_book(client, librarian)), 409, "INVALID_SUGGESTION_STATUS")
    err(order(client, librarian, supplier(client, librarian), branch_a, s), 409, "INVALID_SUGGESTION_STATUS")
