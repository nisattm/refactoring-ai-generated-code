"""Feedback tests: module 25 (Purchase suggestions). Generated from cases/suggestions.md."""
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


def test_t_sug_01_a(client, librarian, branch_a):
    """T-SUG-01-a (LIB-SUG-01): 201 submitted for the student with submitted_at; book_id, quantity, purchase_order_id null"""
    m = member(client, librarian, branch_a)
    s = sug(client, mh(client, m), branch_a, title="Sapiens", author_text="Yuval Noah Harari", reason="Ders için gerekli", publication_year=2015)
    assert (s["member_id"], s["title"], s["author_text"], s["isbn"], s["publication_year"], s["reason"], s["branch_id"], s["status"]) == (m["id"], "Sapiens", "Yuval Noah Harari", None, 2015, "Ders için gerekli", branch_a["id"], "submitted")
    assert same(s["submitted_at"], MON, 9) and (s["book_id"], s["quantity"], s["purchase_order_id"]) == (None, None, None)


def test_t_sug_03_a(client, admin, librarian, branch_a):
    """T-SUG-03-a (LIB-SUG-03): MEMBER_PASSIVE; MEMBERSHIP_TYPE_NOT_ALLOWED; BRANCH_INACTIVE"""
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_sug(client, mh(client, p), branch_a), 409, "MEMBER_PASSIVE")
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_sug(client, mh(client, g), branch_a), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_sug(client, mh(client, member(client, librarian, branch_a)), qq), 409, "BRANCH_INACTIVE")


def test_t_sug_04_a(client, librarian, branch_a):
    """T-SUG-04-a (LIB-SUG-04): SUGGESTION_LIMIT_REACHED with details.limit 3; 201; limit 5"""
    h = mh(client, member(client, librarian, branch_a))
    first = sug(client, h, branch_a)
    sug(client, h, branch_a); sug(client, h, branch_a)
    assert err(try_sug(client, h, branch_a), 409, "SUGGESTION_LIMIT_REACHED")["details"]["limit"] == 3
    ok(post(client, h, f"suggestions/{first['id']}/withdraw"))
    sug(client, h, branch_a)
    sh = mh(client, member(client, librarian, branch_a, membership_type="staff"))
    for _ in range(5):
        sug(client, sh, branch_a)
    assert err(try_sug(client, sh, branch_a), 409, "SUGGESTION_LIMIT_REACHED")["details"]["limit"] == 5


def test_t_sug_05_a(client, librarian, branch_a):
    """T-SUG-05-a (LIB-SUG-05): 200; 409 BOOK_ALREADY_OWNED; 409 INVALID_SUGGESTION_STATUS with details.status approved"""
    s, _, h = by(client, librarian, branch_a)
    url = f"/api/v1/suggestions/{s['id']}"
    assert ok(client.patch(url, headers=h, json={"title": "Yeni Başlık"}))["title"] == "Yeni Başlık"
    owned = create_book(client, librarian)
    add_copy(client, librarian, owned["id"], home_branch_id=branch_a["id"])
    err(client.patch(url, headers=h, json={"isbn": owned["isbn"]}), 409, "BOOK_ALREADY_OWNED")
    approve(client, librarian, s, create_book(client, librarian))
    assert err(client.patch(url, headers=h, json={"title": "X"}), 409, "INVALID_SUGGESTION_STATUS")["details"]["status"] == "approved"


def test_t_sug_07_a(client, librarian, branch_a):
    """T-SUG-07-a (LIB-SUG-07): 201; ALREADY_SUPPORTED; CANNOT_SUPPORT_OWN; MEMBERSHIP_TYPE_NOT_ALLOWED; MEMBER_PASSIVE; 403; INVALID_SUGGESTION_STATUS"""
    s, _, ah = by(client, librarian, branch_a)
    bh = mh(client, member(client, librarian, branch_a))
    assert ok(support(client, bh, s), 201)["supporters"] == 1
    err(support(client, bh, s), 409, "ALREADY_SUPPORTED")
    err(support(client, ah, s), 409, "CANNOT_SUPPORT_OWN")
    err(support(client, mh(client, member(client, librarian, branch_a, membership_type="guest")), s), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
    p = member(client, librarian, branch_a)
    ph = mh(client, p)
    deactivate_member(client, librarian, p["id"])
    err(support(client, ph, s), 409, "MEMBER_PASSIVE")
    assert support(client, librarian, s).status_code == 403
    r, _, _ = by(client, librarian, branch_a)
    ok(reject(client, librarian, r))
    err(support(client, bh, r), 409, "INVALID_SUGGESTION_STATUS")


def test_t_sug_09_a(client, librarian, branch_a):
    """T-SUG-09-a (LIB-SUG-09): score 4 with 2 supporters; then score 2"""
    s, _, _ = by(client, librarian, branch_a)
    ah = mh(client, member(client, librarian, branch_a, membership_type="academic"))
    ok(support(client, ah, s), 201)
    ok(support(client, mh(client, member(client, librarian, branch_a, membership_type="staff")), s), 201)
    out = sug_of(client, librarian, s)
    assert (out["score"], out["supporters"]) == (4, 2)
    assert client.delete(f"/api/v1/suggestions/{s['id']}/support", headers=ah).status_code == 204
    assert sug_of(client, librarian, s)["score"] == 2


def test_t_sug_11_a(client, librarian, branch_a):
    """T-SUG-11-a (LIB-SUG-11): own [S2, S1]; supported [T1]; 403"""
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    s1, s2 = sug(client, h, branch_a), sug(client, h, branch_a)
    ok(post(client, h, f"suggestions/{s2['id']}/withdraw"))
    t1, _, _ = by(client, librarian, branch_a)
    t2, _, _ = by(client, librarian, branch_a)
    ok(support(client, h, t1), 201); ok(support(client, h, t2), 201)
    ok(reject(client, librarian, t2))
    out = get(client, h, f"members/{m['id']}/suggestions")
    assert ([x["id"] for x in out["own"]], [x["id"] for x in out["supported"]]) == ([s2["id"], s1["id"]], [t1["id"]])
    assert client.get(f"/api/v1/members/{m['id']}/suggestions", headers=mh(client, member(client, librarian, branch_a))).status_code == 403


def test_t_sug_13_a(client, librarian, branch_a):
    """T-SUG-13-a (LIB-SUG-13): 20 × 201; 409 SUPPORT_LIMIT_REACHED with details.limit 20"""
    sugs = []
    for _ in range(7):
        h = mh(client, member(client, librarian, branch_a))
        sugs += [sug(client, h, branch_a) for _ in range(3)]
    fan = mh(client, member(client, librarian, branch_a))
    for s in sugs[:20]:
        ok(support(client, fan, s), 201)
    assert err(support(client, fan, sugs[20]), 409, "SUPPORT_LIMIT_REACHED")["details"]["limit"] == 20


def test_t_sug_15_a(client, librarian, branch_a):
    """T-SUG-15-a (LIB-SUG-15): 200 approved, reviewed_at, book_id, quantity, estimated_price, review_note; one suggestion_approved notification with suggestion_id"""
    s, m, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    out = ok(try_approve(client, librarian, s, x, 2, "40.00", "Alındı"))
    assert (out["status"], out["book_id"], out["quantity"], out["estimated_price"], out["review_note"]) == ("approved", x["id"], 2, "40.00", "Alındı") and same(out["reviewed_at"], MON, 9)
    ns = notes(client, librarian, m["id"], "suggestion_approved")
    assert len(ns) == 1 and ns[0]["suggestion_id"] == s["id"]


def test_t_sug_17_a(client, librarian, branch_a):
    """T-SUG-17-a (LIB-SUG-17): 200 rejected with reason and one suggestion_rejected notification; 200; 409 INVALID_SUGGESTION_STATUS"""
    s1, m, _ = by(client, librarian, branch_a)
    out = ok(reject(client, librarian, s1, "too_expensive"))
    assert (out["status"], out["reject_reason"]) == ("rejected", "too_expensive") and same(out["reviewed_at"], MON, 9)
    assert len(notes(client, librarian, m["id"], "suggestion_rejected")) == 1
    s2, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s2, create_book(client, librarian))
    ok(reject(client, librarian, s2, "not_available"))
    err(reject(client, librarian, s1), 409, "INVALID_SUGGESTION_STATUS")


def test_t_sug_19_a(client, librarian, branch_a):
    """T-SUG-19-a (LIB-SUG-19): 200 (the order is not enforced)"""
    s1, _, _ = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a, membership_type="academic")), s1), 201)
    s2, _, _ = by(client, librarian, branch_a)
    assert approve(client, librarian, s2, create_book(client, librarian))["status"] == "approved"


def test_t_sug_21_a(client, admin, librarian, branch_a):
    """T-SUG-21-a (LIB-SUG-21): 200; 403; 200"""
    s1, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, create_book(client, librarian), 3, "100.00")
    s2, _, _ = by(client, librarian, branch_a)
    b = create_book(client, librarian)
    assert try_approve(client, librarian, s2, b, 3, "100.01").status_code == 403
    approve(client, admin, s2, b, 3, "100.01")


def test_t_sug_23_a(client, librarian, branch_a):
    """T-SUG-23-a (LIB-SUG-23): S2's supporters B, A; score 3"""
    s1, a, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    b = member(client, librarian, branch_a)
    ok(support(client, mh(client, b), s1), 201)
    ok(support(client, mh(client, b), s2), 201)
    ok(post(client, librarian, f"suggestions/{s1['id']}/merge", {"into_suggestion_id": s2["id"]}))
    assert [r["member_id"] for r in items(get(client, librarian, f"suggestions/{s2['id']}/supporters"))] == [b["id"], a["id"]]
    assert sug_of(client, librarian, s2)["score"] == 3


def test_t_sug_25_a(client, librarian, branch_a):
    """T-SUG-25-a (LIB-SUG-25): 201; 200"""
    x = create_book(client, librarian)
    cp = add_copy(client, librarian, x["id"], home_branch_id=branch_a["id"])
    report_lost(client, librarian, lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])["id"])
    s, _, _ = by(client, librarian, branch_a, isbn=x["isbn"])
    assert approve(client, librarian, s, x)["book_id"] == x["id"]


def test_t_sug_27_a(client, librarian, branch_a, branch_b):
    """T-SUG-27-a (LIB-SUG-27): SUPPLIER_INACTIVE; INVALID_SUGGESTION_STATUS with details.suggestion_id; SUGGESTION_BRANCH_MISMATCH; 422; 422; the good suggestion stays approved"""
    good, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, good, create_book(client, librarian))
    sup = supplier(client, librarian)
    off = supplier(client, librarian)
    ok(client.patch(f"/api/v1/suppliers/{off['id']}", headers=librarian, json={"is_active": False}))
    err(order(client, librarian, off, branch_a, good), 409, "SUPPLIER_INACTIVE")
    sub, _, _ = by(client, librarian, branch_a)
    assert err(order(client, librarian, sup, branch_a, good, sub), 409, "INVALID_SUGGESTION_STATUS")["details"]["suggestion_id"] == sub["id"]
    other, _, _ = by(client, librarian, branch_b)
    approve(client, librarian, other, create_book(client, librarian))
    assert err(order(client, librarian, sup, branch_a, good, other), 409, "SUGGESTION_BRANCH_MISMATCH")["details"]["suggestion_id"] == other["id"]
    assert order(client, librarian, sup, branch_a).status_code == 422
    assert order(client, librarian, sup, branch_a, good, good).status_code == 422
    assert sug_of(client, librarian, good)["status"] == "approved"


def test_t_sug_29_a(client, librarian, branch_a):
    """T-SUG-29-a (LIB-SUG-29): S1 approved with purchase_order_id null, S2 ordered; after cancelling S2 approved"""
    x, y = create_book(client, librarian), create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, x); approve(client, librarian, s2, y)
    o = ok(order(client, librarian, supplier(client, librarian), branch_a, s1, s2), 201)
    ok(client.patch(f"/api/v1/purchase-orders/{o['id']}", headers=librarian, json={"lines": [{"book_id": y["id"], "quantity": 1, "unit_price": "40.00"}]}))
    a, b = sug_of(client, librarian, s1), sug_of(client, librarian, s2)
    assert (a["status"], a["purchase_order_id"], a["ordered_at"], b["status"]) == ("approved", None, None, "ordered")
    ok(post(client, librarian, f"purchase-orders/{o['id']}/cancel"))
    assert sug_of(client, librarian, s2)["status"] == "approved"


def test_t_sug_31_a(client, clock, librarian, branch_a):
    """T-SUG-31-a (LIB-SUG-31): available_at Mon 09:00 after both receivings"""
    s, _, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x, 2)
    o = ordered(client, librarian, branch_a, s)
    receive(client, librarian, o, x)
    at(clock, "2026-11-03")
    receive(client, librarian, o, x)
    out = sug_of(client, librarian, s)
    assert out["status"] == "available" and same(out["available_at"], MON, 9)


def test_t_sug_33_a(client, librarian, branch_a, branch_b):
    """T-SUG-33-a (LIB-SUG-33): A gets a reservation; D is skipped (no reservation, the arrival still succeeds)"""
    s, a, _ = by(client, librarian, branch_a)
    d = member(client, librarian, branch_a)
    ok(support(client, mh(client, d), s), 201)
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    o = ordered(client, librarian, branch_a, s)
    lend(client, librarian, d["id"], add_copy(client, librarian, x["id"], home_branch_id=branch_b["id"])["id"])
    receive(client, librarian, o, x)
    assert [r["book_id"] for r in reservations_of(client, librarian, a["id"])] == [x["id"]]
    assert reservations_of(client, librarian, d["id"]) == []


def test_t_sug_35_a(client, clock, librarian, branch_a):
    """T-SUG-35-a (LIB-SUG-35): expired_submitted 0, then 1"""
    s, _, _ = by(client, librarian, branch_a)
    at(clock, "2027-03-02", 9, 0, 0)
    assert ok(post(client, librarian, "suggestions/process"))["expired_submitted"] == 0
    at(clock, "2027-03-02", 9, 0, 1)
    assert ok(post(client, librarian, "suggestions/process"))["expired_submitted"] == 1
    assert sug_of(client, librarian, s)["status"] == "expired"


def test_t_sug_37_a(client, librarian, branch_a):
    """T-SUG-37-a (LIB-SUG-37): The open suggestion stays submitted; 409 MEMBERSHIP_TYPE_NOT_ALLOWED"""
    s, m, h = by(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest"}))
    assert sug_of(client, librarian, s)["status"] == "submitted"
    err(try_sug(client, h, branch_a), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")


def test_t_sug_39_a(client, librarian, branch_a):
    """T-SUG-39-a (LIB-SUG-39): 409 IN_USE"""
    s, _, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    err(client.delete(f"/api/v1/books/{x['id']}", headers=librarian), 409, "IN_USE")


def test_t_sug_41_a(client, librarian, branch_a):
    """T-SUG-41-a (LIB-SUG-41): open_suggestions 2"""
    x = create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    s3, _, _ = by(client, librarian, branch_a)
    for s in (s1, s2, s3):
        approve(client, librarian, s, x)
    ok(order(client, librarian, supplier(client, librarian), branch_a, s2), 201)
    ok(reject(client, librarian, s3))
    assert get(client, librarian, f"books/{x['id']}")["open_suggestions"] == 2


def test_t_sug_43_a(client, admin, librarian, branch_a):
    """T-SUG-43-a (LIB-SUG-43): One entry per event (5 for suggestion_submitted)"""
    s, _, h = by(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/suggestions/{s['id']}", headers=h, json={"reason": "Not"}))
    bh = mh(client, member(client, librarian, branch_a))
    ok(support(client, bh, s), 201)
    assert client.delete(f"/api/v1/suggestions/{s['id']}/support", headers=bh).status_code == 204
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    ok(client.patch(f"/api/v1/suggestions/{s['id']}/approval", headers=librarian, json={"quantity": 2}))
    receive(client, librarian, ordered(client, librarian, branch_a, s), x)
    r, _, _ = by(client, librarian, branch_a)
    ok(reject(client, librarian, r))
    w, _, wh = by(client, librarian, branch_a)
    ok(post(client, wh, f"suggestions/{w['id']}/withdraw"))
    g, _, _ = by(client, librarian, branch_a)
    t = sug(client, h, branch_a)
    ok(post(client, librarian, f"suggestions/{g['id']}/merge", {"into_suggestion_id": t["id"]}))
    ok(post(client, librarian, "suggestions/process"))
    counts = {"suggestion_submitted": 5, "suggestion_updated": 1, "suggestion_supported": 1, "suggestion_support_removed": 1, "suggestion_approved": 1,
              "suggestion_approval_changed": 1, "suggestions_ordered": 1, "suggestion_available": 1, "suggestion_rejected": 1, "suggestion_withdrawn": 1,
              "suggestion_merged": 1, "suggestions_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name


def test_t_sug_44_a(client, clock, librarian, branch_a):
    """T-SUG-44-a (LIB-SUG-44): submitted 4, approved 1, rejected.out_of_scope 1, withdrawn 1, merged 1, average_days_to_available 3.0, top first S1"""
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    s3, _, h3 = by(client, librarian, branch_a)
    s4, _, _ = by(client, librarian, branch_a)
    ok(post(client, librarian, f"suggestions/{s4['id']}/merge", {"into_suggestion_id": s1["id"]}))
    x = create_book(client, librarian)
    approve(client, librarian, s1, x)
    o = ordered(client, librarian, branch_a, s1)
    ok(reject(client, librarian, s2))
    ok(post(client, h3, f"suggestions/{s3['id']}/withdraw"))
    at(clock, "2026-11-05", 9)
    receive(client, librarian, o, x)
    r = get(client, librarian, "reports/suggestions", **{"from": MON, "to": "2026-11-08"})
    assert (r["submitted"], r["approved"], r["rejected"]["out_of_scope"], r["withdrawn"], r["merged"], r["average_days_to_available"]) == (4, 1, 1, 1, 1, "3.0")
    assert r["top"][0]["suggestion_id"] == s1["id"] and r["top"][0]["score"] == 2


def test_t_sug_45_a(client, admin, librarian, branch_a):
    """T-SUG-45-a (LIB-SUG-45): The export has exactly the keys of 22.1"""
    s, _, _ = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a)), s), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}


def test_t_sug_47_a(client, admin, librarian, branch_a):
    """T-SUG-47-a (LIB-SUG-47): 409 BRANCH_IN_USE; 200"""
    qq = create_branch(client, admin, "QQ")
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    s = sug(client, h, qq)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, h, f"suggestions/{s['id']}/withdraw"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
