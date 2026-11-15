MODULE = "suggestions"
TITLE = "module 25 (Purchase suggestions)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- suggesting and supporting
    dict(id="T-SUG-01-a", req="LIB-SUG-01", type="Normal", input="A student suggests a title with author, ISBN-less, reason and branch A", expected="201 `submitted` for the student with `submitted_at`; `book_id`, `quantity`, `purchase_order_id` null", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    s = sug(client, mh(client, m), branch_a, title="Sapiens", author_text="Yuval Noah Harari", reason="Ders için gerekli", publication_year=2015)
    assert (s["member_id"], s["title"], s["author_text"], s["isbn"], s["publication_year"], s["reason"], s["branch_id"], s["status"]) == (m["id"], "Sapiens", "Yuval Noah Harari", None, 2015, "Ders için gerekli", branch_a["id"], "submitted")
    assert same(s["submitted_at"], MON, 9) and (s["book_id"], s["quantity"], s["purchase_order_id"]) == (None, None, None)
'''),
    dict(id="T-SUG-01-b", req="LIB-SUG-01", type="Error", input="Empty title; year 2027; invalid ISBN; a member sends `member_id`; staff omit it; staff with `member_id`", expected="`422` five times; 201 for the member", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert try_sug(client, h, branch_a, title="").status_code == 422
    assert try_sug(client, h, branch_a, publication_year=2027).status_code == 422
    assert try_sug(client, h, branch_a, isbn="9780000000000").status_code == 422
    assert try_sug(client, h, branch_a, member_id=m["id"]).status_code == 422
    assert try_sug(client, librarian, branch_a).status_code == 422
    assert sug(client, librarian, branch_a, member_id=m["id"])["member_id"] == m["id"]
'''),
    dict(id="T-SUG-02-a", req="LIB-SUG-02", type="Normal", input="Suggestion of member A supported by B; read by A, by B and by C", expected="`score` 2, `supporters` 1; A `mine` true, `supported_by_me` false; B `mine` false, `supported_by_me` true; C both false", code='''
def TEST(client, librarian, branch_a):
    s, a, ah = by(client, librarian, branch_a)
    bh, ch = mh(client, member(client, librarian, branch_a)), mh(client, member(client, librarian, branch_a))
    ok(support(client, bh, s), 201)
    rows = [sug_of(client, h, s) for h in (ah, bh, ch)]
    assert [(r["score"], r["supporters"], r["mine"], r["supported_by_me"]) for r in rows] == [(2, 1, True, False), (2, 1, False, True), (2, 1, False, False)]
'''),
    dict(id="T-SUG-03-a", req="LIB-SUG-03", type="Error", input="A passive member suggests; a guest; a suggestion for an inactive branch", expected="`MEMBER_PASSIVE`; `MEMBERSHIP_TYPE_NOT_ALLOWED`; `BRANCH_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_sug(client, mh(client, p), branch_a), 409, "MEMBER_PASSIVE")
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_sug(client, mh(client, g), branch_a), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_sug(client, mh(client, member(client, librarian, branch_a)), qq), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-SUG-03-b", req="LIB-SUG-03", type="Error", input="ISBN of a book with a copy; ISBN of another member's open suggestion", expected="`BOOK_ALREADY_OWNED` with `details.book_id`; `DUPLICATE_SUGGESTION` with `details.suggestion_id`", code='''
def TEST(client, librarian, branch_a):
    owned = create_book(client, librarian)
    add_copy(client, librarian, owned["id"], home_branch_id=branch_a["id"])
    h = mh(client, member(client, librarian, branch_a))
    assert err(try_sug(client, h, branch_a, isbn=owned["isbn"]), 409, "BOOK_ALREADY_OWNED")["details"]["book_id"] == owned["id"]
    isbn = create_book(client, librarian)["isbn"]
    first, _, _ = by(client, librarian, branch_a, isbn=isbn)
    assert err(try_sug(client, h, branch_a, isbn=isbn), 409, "DUPLICATE_SUGGESTION")["details"]["suggestion_id"] == first["id"]
'''),
    dict(id="T-SUG-04-a", req="LIB-SUG-04", type="Boundary", input="A student with 3 open suggestions suggests a fourth; after withdrawing one, again; a staff member's sixth", expected="`SUGGESTION_LIMIT_REACHED` with `details.limit` 3; 201; `limit` 5", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-04-b", req="LIB-SUG-04", type="Boundary", input="Suggestion with an ISBN rejected on 2026-11-02; the same member suggests it on 2027-04-30 and 2027-05-01", expected="`SUGGESTION_RECENTLY_REJECTED` with `details.until` 2027-05-01; 201", code='''
def TEST(client, clock, librarian, branch_a):
    isbn = create_book(client, librarian)["isbn"]
    s, m, h = by(client, librarian, branch_a, isbn=isbn)
    ok(reject(client, librarian, s))
    at(clock, "2027-04-30")
    assert err(try_sug(client, h, branch_a, isbn=isbn), 409, "SUGGESTION_RECENTLY_REJECTED")["details"]["until"] == "2027-05-01"
    at(clock, "2027-05-01")
    sug(client, h, branch_a, isbn=isbn)
'''),
    dict(id="T-SUG-05-a", req="LIB-SUG-05", type="Error", input="Member changes the title; changes the ISBN to an owned book's; after approval changes the title", expected="200; `409 BOOK_ALREADY_OWNED`; `409 INVALID_SUGGESTION_STATUS` with `details.status` `approved`", code='''
def TEST(client, librarian, branch_a):
    s, _, h = by(client, librarian, branch_a)
    url = f"/api/v1/suggestions/{s['id']}"
    assert ok(client.patch(url, headers=h, json={"title": "Yeni Başlık"}))["title"] == "Yeni Başlık"
    owned = create_book(client, librarian)
    add_copy(client, librarian, owned["id"], home_branch_id=branch_a["id"])
    err(client.patch(url, headers=h, json={"isbn": owned["isbn"]}), 409, "BOOK_ALREADY_OWNED")
    approve(client, librarian, s, create_book(client, librarian))
    assert err(client.patch(url, headers=h, json={"title": "X"}), 409, "INVALID_SUGGESTION_STATUS")["details"]["status"] == "approved"
'''),
    dict(id="T-SUG-06-a", req="LIB-SUG-06", type="Normal", input="Member withdraws a submitted suggestion; member withdraws an approved one; staff withdraw it", expected="200 `withdrawn` with `member_request`; `409 INVALID_SUGGESTION_STATUS`; 200", code='''
def TEST(client, librarian, branch_a):
    s1, _, h = by(client, librarian, branch_a)
    out = ok(post(client, h, f"suggestions/{s1['id']}/withdraw"))
    assert (out["status"], out["withdraw_reason"]) == ("withdrawn", "member_request")
    s2 = sug(client, h, branch_a)
    approve(client, librarian, s2, create_book(client, librarian))
    err(post(client, h, f"suggestions/{s2['id']}/withdraw"), 409, "INVALID_SUGGESTION_STATUS")
    assert ok(post(client, librarian, f"suggestions/{s2['id']}/withdraw"))["status"] == "withdrawn"
'''),
    dict(id="T-SUG-07-a", req="LIB-SUG-07", type="Error", input="B supports A's suggestion; B again; A supports own; a guest; a passive member; staff; support of a rejected suggestion", expected="201; `ALREADY_SUPPORTED`; `CANNOT_SUPPORT_OWN`; `MEMBERSHIP_TYPE_NOT_ALLOWED`; `MEMBER_PASSIVE`; `403`; `INVALID_SUGGESTION_STATUS`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-08-a", req="LIB-SUG-08", type="Error", input="B stops supporting; stops again; C supports, the suggestion is rejected, C stops", expected="204 and `supporters` 0; `404`; `409 INVALID_SUGGESTION_STATUS`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-09-a", req="LIB-SUG-09", type="Normal", input="A student's suggestion supported by an academic and a staff member; the academic stops", expected="`score` 4 with 2 supporters; then `score` 2", code='''
def TEST(client, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    ah = mh(client, member(client, librarian, branch_a, membership_type="academic"))
    ok(support(client, ah, s), 201)
    ok(support(client, mh(client, member(client, librarian, branch_a, membership_type="staff")), s), 201)
    out = sug_of(client, librarian, s)
    assert (out["score"], out["supporters"]) == (4, 2)
    assert client.delete(f"/api/v1/suggestions/{s['id']}/support", headers=ah).status_code == 204
    assert sug_of(client, librarian, s)["score"] == 2
'''),
    dict(id="T-SUG-10-a", req="LIB-SUG-10", type="Normal", input="Supporters B (reserve) and C (no reserve); list; a member reads it", expected="[B, C] with `full_name`, `membership_type`, `reserve_on_arrival`; `403`", code='''
def TEST(client, librarian, branch_a):
    s, _, ah = by(client, librarian, branch_a)
    b, c = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    ok(support(client, mh(client, b), s), 201)
    ok(support(client, mh(client, c), s, reserve=False), 201)
    rows = items(get(client, librarian, f"suggestions/{s['id']}/supporters"))
    assert [(r["member_id"], r["full_name"], r["membership_type"], r["reserve_on_arrival"]) for r in rows] == [(b["id"], b["full_name"], "student", True), (c["id"], c["full_name"], "academic", False)]
    assert client.get(f"/api/v1/suggestions/{s['id']}/supporters", headers=ah).status_code == 403
'''),
    dict(id="T-SUG-11-a", req="LIB-SUG-11", type="Normal", input="Member M has own S1, S2 (S2 withdrawn) and supports T1, T2 (T2 rejected); M reads own list; another member reads M's", expected="`own` [S2, S1]; `supported` [T1]; `403`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-12-a", req="LIB-SUG-12", type="Normal", input="S1 (score 1), S2 (score 3), S3 (score 1, rejected); staff list; `status=submitted`; `q`; a member's list; the member reads S3", expected="Staff [S2, S1, S3]; [S2, S1]; member [S2, S1] without `member_id`; `404`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-13-a", req="LIB-SUG-13", type="Boundary", input="A member supports 20 open suggestions and then a 21st", expected="20 × 201; `409 SUPPORT_LIMIT_REACHED` with `details.limit` 20", code='''
def TEST(client, librarian, branch_a):
    sugs = []
    for _ in range(7):
        h = mh(client, member(client, librarian, branch_a))
        sugs += [sug(client, h, branch_a) for _ in range(3)]
    fan = mh(client, member(client, librarian, branch_a))
    for s in sugs[:20]:
        ok(support(client, fan, s), 201)
    assert err(support(client, fan, sugs[20]), 409, "SUPPORT_LIMIT_REACHED")["details"]["limit"] == 20
'''),
    dict(id="T-SUG-14-a", req="LIB-SUG-14", type="Boundary", input="Member withdraws an own suggestion with 3 supporters; one with 2 supporters; staff withdraw the first", expected="`409 SUGGESTION_HAS_SUPPORTERS`; 200; 200", code='''
def TEST(client, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- review
    dict(id="T-SUG-15-a", req="LIB-SUG-15", type="Normal", input="Librarian approves for book X, 2 × 40.00 with a note", expected="200 `approved`, `reviewed_at`, `book_id`, `quantity`, `estimated_price`, `review_note`; one `suggestion_approved` notification with `suggestion_id`", code='''
def TEST(client, librarian, branch_a):
    s, m, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    out = ok(try_approve(client, librarian, s, x, 2, "40.00", "Alındı"))
    assert (out["status"], out["book_id"], out["quantity"], out["estimated_price"], out["review_note"]) == ("approved", x["id"], 2, "40.00", "Alındı") and same(out["reviewed_at"], MON, 9)
    ns = notes(client, librarian, m["id"], "suggestion_approved")
    assert len(ns) == 1 and ns[0]["suggestion_id"] == s["id"]
'''),
    dict(id="T-SUG-15-b", req="LIB-SUG-15", type="Error", input="Approve with quantity 11; price 0.00; an unknown book; a member approves", expected="`422` three times; `403`", code='''
def TEST(client, librarian, branch_a):
    s, _, h = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    assert try_approve(client, librarian, s, x, 11).status_code == 422
    assert try_approve(client, librarian, s, x, 1, "0.00").status_code == 422
    assert try_approve(client, librarian, s, {"id": 999999}).status_code == 422
    assert try_approve(client, h, s, x).status_code == 403
'''),
    dict(id="T-SUG-16-a", req="LIB-SUG-16", type="Error", input="Approve an approved suggestion; a suggestion with ISBN of X for book Y; a second suggestion at A for the same book Y", expected="`INVALID_SUGGESTION_STATUS`; `ISBN_MISMATCH`; 200", code='''
def TEST(client, librarian, branch_a):
    x, y = create_book(client, librarian), create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, y)
    err(try_approve(client, librarian, s1, y), 409, "INVALID_SUGGESTION_STATUS")
    s2, _, _ = by(client, librarian, branch_a, isbn=x["isbn"])
    err(try_approve(client, librarian, s2, y), 409, "ISBN_MISMATCH")
    s3, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s3, y)
'''),
    dict(id="T-SUG-17-a", req="LIB-SUG-17", type="Normal", input="Reject a submitted suggestion `too_expensive`; reject an approved one; reject a rejected one", expected="200 `rejected` with reason and one `suggestion_rejected` notification; 200; `409 INVALID_SUGGESTION_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s1, m, _ = by(client, librarian, branch_a)
    out = ok(reject(client, librarian, s1, "too_expensive"))
    assert (out["status"], out["reject_reason"]) == ("rejected", "too_expensive") and same(out["reviewed_at"], MON, 9)
    assert len(notes(client, librarian, m["id"], "suggestion_rejected")) == 1
    s2, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s2, create_book(client, librarian))
    ok(reject(client, librarian, s2, "not_available"))
    err(reject(client, librarian, s1), 409, "INVALID_SUGGESTION_STATUS")
'''),
    dict(id="T-SUG-18-a", req="LIB-SUG-18", type="Normal", input="Book X whose only copy at A is on loan; suggestion of M (supporters B with, C without reserve) rejected `already_owned` without and with `book_id` X", expected="`422`; 200; M and B have `waiting` reservations of X at A, C none", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-19-a", req="LIB-SUG-19", type="Normal", input="S1 (score 3) and S2 (score 1); the librarian approves S2 first", expected="200 (the order is not enforced)", code='''
def TEST(client, librarian, branch_a):
    s1, _, _ = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a, membership_type="academic")), s1), 201)
    s2, _, _ = by(client, librarian, branch_a)
    assert approve(client, librarian, s2, create_book(client, librarian))["status"] == "approved"
'''),
    dict(id="T-SUG-20-a", req="LIB-SUG-20", type="Error", input="A librarian approves 4 × 100.00 (400.00)", expected="`403`; the suggestion stays `submitted`", code='''
def TEST(client, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    assert try_approve(client, librarian, s, create_book(client, librarian), 4, "100.00").status_code == 403
    assert sug_of(client, librarian, s)["status"] == "submitted"
'''),
    dict(id="T-SUG-21-a", req="LIB-SUG-21", type="Boundary", input="Librarian approves 3 × 100.00; another 3 × 100.01 by a librarian, then by an admin", expected="200; `403`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    s1, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, create_book(client, librarian), 3, "100.00")
    s2, _, _ = by(client, librarian, branch_a)
    b = create_book(client, librarian)
    assert try_approve(client, librarian, s2, b, 3, "100.01").status_code == 403
    approve(client, admin, s2, b, 3, "100.01")
'''),
    dict(id="T-SUG-22-a", req="LIB-SUG-22", type="Error", input="S1 merged into S2; merge into itself; into an unknown suggestion; an approved source; into a rejected target", expected="200 with S2, S1 `merged` with `merged_into_id`; `422`; `404`; `409 INVALID_SUGGESTION_STATUS` twice", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-23-a", req="LIB-SUG-23", type="Normal", input="S1 by A (supported by B), S2 by C (supported by B at 09:00); S1 merged into S2 at 10:00", expected="S2's supporters B, A (A's support is created at the merge); `score` 3", code='''
def TEST(client, clock, librarian, branch_a):
    s1, a, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    b = member(client, librarian, branch_a)
    ok(support(client, mh(client, b), s1), 201)
    ok(support(client, mh(client, b), s2), 201)
    at(clock, MON, 10)
    ok(post(client, librarian, f"suggestions/{s1['id']}/merge", {"into_suggestion_id": s2["id"]}))
    assert [r["member_id"] for r in items(get(client, librarian, f"suggestions/{s2['id']}/supporters"))] == [b["id"], a["id"]]
    assert sug_of(client, librarian, s2)["score"] == 3
'''),
    dict(id="T-SUG-24-a", req="LIB-SUG-24", type="Error", input="Approved 1 × 40.00: change quantity to 3; a librarian changes the price to 120.00; change a submitted suggestion's approval", expected="200 `quantity` 3; `403`; `409 INVALID_SUGGESTION_STATUS`", code='''
def TEST(client, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s, create_book(client, librarian))
    url = f"/api/v1/suggestions/{s['id']}/approval"
    assert ok(client.patch(url, headers=librarian, json={"quantity": 3}))["quantity"] == 3
    assert client.patch(url, headers=librarian, json={"estimated_price": "120.00"}).status_code == 403
    t, _, _ = by(client, librarian, branch_a)
    err(client.patch(f"/api/v1/suggestions/{t['id']}/approval", headers=librarian, json={"quantity": 2}), 409, "INVALID_SUGGESTION_STATUS")
'''),
    dict(id="T-SUG-25-a", req="LIB-SUG-25", type="Normal", input="Book X whose only copy is lost; a member suggests X's ISBN; approved for X", expected="201; 200", code='''
def TEST(client, librarian, branch_a):
    x = create_book(client, librarian)
    cp = add_copy(client, librarian, x["id"], home_branch_id=branch_a["id"])
    report_lost(client, librarian, lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])["id"])
    s, _, _ = by(client, librarian, branch_a, isbn=x["isbn"])
    assert approve(client, librarian, s, x)["book_id"] == x["id"]
'''),
    # ---------------------------------------------------------------- ordering and arrival
    dict(id="T-SUG-26-a", req="LIB-SUG-26", type="Normal", input="Approved S1 (book X, 2 × 40.00) of member M at A; order with supplier P", expected="201 draft order of P at A with line X 2 × 40.00; S1 `ordered` with `purchase_order_id`, `ordered_at`; one `suggestion_ordered` notification", code='''
def TEST(client, librarian, branch_a):
    s, m, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x, 2, "40.00")
    sup = supplier(client, librarian)
    o = ok(order(client, librarian, sup, branch_a, s), 201)
    assert (o["status"], o["supplier_id"], o["branch_id"], [(l["book_id"], l["quantity"], l["unit_price"]) for l in o["lines"]]) == ("draft", sup["id"], branch_a["id"], [(x["id"], 2, "40.00")])
    out = sug_of(client, librarian, s)
    assert (out["status"], out["purchase_order_id"]) == ("ordered", o["id"]) and same(out["ordered_at"], MON, 9)
    assert len(notes(client, librarian, m["id"], "suggestion_ordered")) == 1
'''),
    dict(id="T-SUG-27-a", req="LIB-SUG-27", type="Error", input="Order with an inactive supplier; with a submitted suggestion; with an approved suggestion of branch B; empty list; an id twice", expected="`SUPPLIER_INACTIVE`; `INVALID_SUGGESTION_STATUS` with `details.suggestion_id`; `SUGGESTION_BRANCH_MISMATCH`; `422`; `422`; the good suggestion stays `approved`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-SUG-28-a", req="LIB-SUG-28", type="Normal", input="Approved S1 (X, 2 × 40.00), S2 (X, 1 × 45.00), S3 (Y, 1 × 20.00) at A ordered together", expected="Lines X 3 × 45.00 and Y 1 × 20.00; `total` 155.00", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-29-a", req="LIB-SUG-29", type="Normal", input="Draft order from S1 (X) and S2 (Y); lines replaced by the Y line only; then the order cancelled", expected="S1 `approved` with `purchase_order_id` null, S2 `ordered`; after cancelling S2 `approved`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-30-a", req="LIB-SUG-30", type="Normal", input="Ordered S1 (X) of member M supported by B; the order submitted and 1 copy received on 2026-11-05", expected="S1 `available` with `available_at`; one `suggestion_available` notification each for M and B", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-SUG-31-a", req="LIB-SUG-31", type="Normal", input="S1 approved for 2 copies of X, ordered; 1 copy received on Mon, 1 on Tue", expected="`available_at` Mon 09:00 after both receivings", code='''
def TEST(client, clock, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x, 2)
    o = ordered(client, librarian, branch_a, s)
    receive(client, librarian, o, x)
    at(clock, "2026-11-03")
    receive(client, librarian, o, x)
    out = sug_of(client, librarian, s)
    assert out["status"] == "available" and same(out["available_at"], MON, 9)
'''),
    dict(id="T-SUG-32-a", req="LIB-SUG-32", type="Normal", input="S1 of A for X at branch A, supporters B (reserve) and C (no reserve); ordered; 1 copy received", expected="A's reservation of X `ready` with the new copy; B's `waiting`; C has none; A, B, C get `suggestion_available`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-33-a", req="LIB-SUG-33", type="Normal", input="S1 of A for X supported by D (reserve); D borrows a copy of X at branch B before the arrival; X arrives at A", expected="A gets a reservation; D is skipped (no reservation, the arrival still succeeds)", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-SUG-34-a", req="LIB-SUG-34", type="Boundary", input="Suggestion approved Mon 2026-11-02 09:00; process on 2027-01-31 09:00 and 09:00:01", expected="`expired_approved` 0, then 1; `expired`; one `suggestion_expired` notification", code='''
def TEST(client, clock, librarian, branch_a):
    s, m, _ = by(client, librarian, branch_a)
    approve(client, librarian, s, create_book(client, librarian))
    at(clock, "2027-01-31", 9, 0, 0)
    assert ok(post(client, librarian, "suggestions/process"))["expired_approved"] == 0
    at(clock, "2027-01-31", 9, 0, 1)
    assert ok(post(client, librarian, "suggestions/process"))["expired_approved"] == 1
    assert sug_of(client, librarian, s)["status"] == "expired"
    assert len(notes(client, librarian, m["id"], "suggestion_expired")) == 1
'''),
    dict(id="T-SUG-35-a", req="LIB-SUG-35", type="Boundary", input="Suggestion submitted Mon 2026-11-02 09:00; process on 2027-03-02 09:00 and 09:00:01", expected="`expired_submitted` 0, then 1", code='''
def TEST(client, clock, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    at(clock, "2027-03-02", 9, 0, 0)
    assert ok(post(client, librarian, "suggestions/process"))["expired_submitted"] == 0
    at(clock, "2027-03-02", 9, 0, 1)
    assert ok(post(client, librarian, "suggestions/process"))["expired_submitted"] == 1
    assert sug_of(client, librarian, s)["status"] == "expired"
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-SUG-36-a", req="LIB-SUG-36", type="Normal", input="Member M with a submitted and an approved suggestion, supporting another suggestion T, is deactivated", expected="Submitted → `withdrawn` with `member_deactivated`; approved stays; T has 0 supporters", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-37-a", req="LIB-SUG-37", type="Normal", input="A student with an open suggestion is changed to `guest`; suggests again", expected="The open suggestion stays `submitted`; `409 MEMBERSHIP_TYPE_NOT_ALLOWED`", code='''
def TEST(client, librarian, branch_a):
    s, m, h = by(client, librarian, branch_a)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "+905551112233", "university_id": None}))
    assert sug_of(client, librarian, s)["status"] == "submitted"
    err(try_sug(client, h, branch_a), 409, "MEMBERSHIP_TYPE_NOT_ALLOWED")
'''),
    dict(id="T-SUG-38-a", req="LIB-SUG-38", type="Normal", input="Member with a submitted suggestion, one that arrived, and support of an open suggestion; a member without suggestions", expected="`{open 1, supported 1, available_this_year 1}`; all 0", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-SUG-39-a", req="LIB-SUG-39", type="Error", input="Book without copies that an approved suggestion uses is deleted", expected="`409 IN_USE`", code='''
def TEST(client, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    x = create_book(client, librarian)
    approve(client, librarian, s, x)
    err(client.delete(f"/api/v1/books/{x['id']}", headers=librarian), 409, "IN_USE")
'''),
    dict(id="T-SUG-40-a", req="LIB-SUG-40", type="Normal", input="Order created from S1 and S2; a manual order", expected="`suggestion_ids` [S1, S2]; []", code='''
def TEST(client, librarian, branch_a):
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    approve(client, librarian, s1, create_book(client, librarian)); approve(client, librarian, s2, create_book(client, librarian))
    sup = supplier(client, librarian)
    o = ok(order(client, librarian, sup, branch_a, s2, s1), 201)
    assert get(client, librarian, f"purchase-orders/{o['id']}")["suggestion_ids"] == [s1["id"], s2["id"]]
    manual = ok(post(client, librarian, "purchase-orders", {"supplier_id": sup["id"], "branch_id": branch_a["id"], "lines": []}), 201)
    assert get(client, librarian, f"purchase-orders/{manual['id']}")["suggestion_ids"] == []
'''),
    dict(id="T-SUG-41-a", req="LIB-SUG-41", type="Normal", input="Book X with an approved and an ordered suggestion and a rejected one", expected="`open_suggestions` 2", code='''
def TEST(client, librarian, branch_a):
    x = create_book(client, librarian)
    s1, _, _ = by(client, librarian, branch_a)
    s2, _, _ = by(client, librarian, branch_a)
    s3, _, _ = by(client, librarian, branch_a)
    for s in (s1, s2, s3):
        approve(client, librarian, s, x)
    ok(order(client, librarian, supplier(client, librarian), branch_a, s2), 201)
    ok(reject(client, librarian, s3))
    assert get(client, librarian, f"books/{x['id']}")["open_suggestions"] == 2
'''),
    dict(id="T-SUG-42-a", req="LIB-SUG-42", type="Normal", input="A's suggestion is supported, changed, supported again and merged into another", expected="A has no notifications", code='''
def TEST(client, librarian, branch_a):
    s, a, h = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a)), s), 201)
    ok(client.patch(f"/api/v1/suggestions/{s['id']}", headers=h, json={"reason": "Çok istenen"}))
    t, _, _ = by(client, librarian, branch_a)
    ok(post(client, librarian, f"suggestions/{s['id']}/merge", {"into_suggestion_id": t["id"]}))
    assert get(client, librarian, f"members/{a['id']}/notifications")["total"] == 0
'''),
    dict(id="T-SUG-43-a", req="LIB-SUG-43", type="Normal", input="Suggestions submitted, changed, supported, support removed, approved, approval changed, ordered, arrived, one rejected, one withdrawn, one merged; process; audit log", expected="One entry per event (5 for `suggestion_submitted`)", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-SUG-44-a", req="LIB-SUG-44", type="Normal", input="In the week of 2026-11-02 at A: S1 approved, ordered, arrived on 2026-11-05 (score 2 after a merge); S2 rejected `out_of_scope`; S3 withdrawn; S4 merged into S1; report", expected="`submitted` 4, `approved` 1, `rejected.out_of_scope` 1, `withdrawn` 1, `merged` 1, `average_days_to_available` 3.0, top first S1", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-SUG-44-b", req="LIB-SUG-44", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/suggestions"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-SUG-45-a", req="LIB-SUG-45", type="Normal", input="A suggestion with a supporter exists; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    s, _, _ = by(client, librarian, branch_a)
    ok(support(client, mh(client, member(client, librarian, branch_a)), s), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
    dict(id="T-SUG-46-a", req="LIB-SUG-46", type="Error", input="A withdrawn suggestion: changed by its member, supported, withdrawn, approved, ordered", expected="`409 INVALID_SUGGESTION_STATUS` each", code='''
def TEST(client, librarian, branch_a):
    s, _, h = by(client, librarian, branch_a)
    ok(post(client, h, f"suggestions/{s['id']}/withdraw"))
    err(client.patch(f"/api/v1/suggestions/{s['id']}", headers=h, json={"title": "X"}), 409, "INVALID_SUGGESTION_STATUS")
    err(support(client, mh(client, member(client, librarian, branch_a)), s), 409, "INVALID_SUGGESTION_STATUS")
    err(post(client, librarian, f"suggestions/{s['id']}/withdraw"), 409, "INVALID_SUGGESTION_STATUS")
    err(try_approve(client, librarian, s, create_book(client, librarian)), 409, "INVALID_SUGGESTION_STATUS")
    err(order(client, librarian, supplier(client, librarian), branch_a, s), 409, "INVALID_SUGGESTION_STATUS")
'''),
    dict(id="T-SUG-47-a", req="LIB-SUG-47", type="Error", input="Branch QQ (no copies, no members) with a submitted suggestion is deactivated; after the suggestion is withdrawn", expected="`409 BRANCH_IN_USE`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    s = sug(client, h, qq)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, h, f"suggestions/{s['id']}/withdraw"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
]
