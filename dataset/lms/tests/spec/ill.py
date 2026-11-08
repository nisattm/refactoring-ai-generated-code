MODULE = "ill"
TITLE = "module 18 (Interlibrary loans)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, get_copy, isbn13,
    items, lend, member_fees, member_headers, pay, register_member, reserve, return_loan, waive,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py)


def at(clock, day, hh=10, mm=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, tzinfo=TR))


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def partner(client, admin, *, code=None, request_fee="0.00", daily_late_fee="1.00", max_outgoing=5, expect=201, **fields):
    _seq[0] += 1
    body = {"code": code if code is not None else f"P{_seq[0]:03d}", "name": f"Partner {_seq[0]}",
            "email": f"partner{_seq[0]}@example.org", "request_fee": request_fee, "daily_late_fee": daily_late_fee,
            "max_outgoing": max_outgoing}
    body.update(fields)
    r = client.post("/api/v1/ill-partners", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def new_request(client, headers, member_id=None, *, title="Uzak Kitap", author="Bir Yazar", isbn=None):
    body = {"title": title, "author": author}
    if isbn is not None:
        body["isbn"] = isbn
    if member_id is not None:
        body["member_id"] = member_id
    return client.post("/api/v1/ill-requests", headers=headers, json=body)


def step(client, headers, request_id, name, body=None):
    return client.post(f"/api/v1/ill-requests/{request_id}/{name}", headers=headers, json=body)


def out_step(client, headers, outgoing_id, name, body=None):
    return client.post(f"/api/v1/ill-outgoing/{outgoing_id}/{name}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def get_req(client, lib, request_id):
    return get(client, lib, f"ill-requests/{request_id}")


def sent(client, lib, p, m, **kw):
    """A request of member ``m`` sent to partner ``p``."""
    req = ok(new_request(client, lib, m["id"], **kw), 201)
    ok(step(client, lib, req["id"], "send", {"partner_id": p["id"]}))
    return req


def received(client, lib, p, m, branch, *, partner_due_on="2026-11-20", replacement_cost="200.00", **kw):
    req = sent(client, lib, p, m, **kw)
    ok(step(client, lib, req["id"], "receive", {"partner_due_on": partner_due_on, "replacement_cost": replacement_cost,
                                                "pickup_branch_id": branch["id"]}))
    return req


def on_loan(client, lib, p, m, branch, **kw):
    """Received on Mon 2026-11-02 (due 2026-11-17 for partner due 2026-11-20) and collected."""
    req = received(client, lib, p, m, branch, **kw)
    ok(step(client, lib, req["id"], "collect"))
    return req


def outgoing(client, lib, p, book, expect=201):
    r = client.post("/api/v1/ill-outgoing", headers=lib, json={"partner_id": p["id"], "book_id": book["id"]})
    assert r.status_code == expect, r.text
    return r.json()


def book_with_copy(client, lib, branch, **kw):
    book = create_book(client, lib, **kw)
    return book, add_copy(client, lib, book["id"], home_branch_id=branch["id"])


def notes(client, lib, member_id, type_=None):
    params = {"type": type_} if type_ else {}
    return items(get(client, lib, f"members/{member_id}/notifications", **params))


def fees_of(client, lib, member_id):
    return sorted((f["kind"], f["amount"]) for f in items(member_fees(client, lib, member_id)))


def debt(client, lib, branch, member_, amount="50.00"):
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def process(client, lib):
    return ok(client.post("/api/v1/ill/process", headers=lib))
'''


CASES = [
    # ---------------------------------------------------------------- partners
    dict(id="T-ILL-01-a", req="LIB-ILL-01", type="Normal", input="Admin creates partner `ank01` (fee 7.50, 2.00 per day, 3 outgoing)", expected="201; code `ANK01`, values kept, active", code='''
def TEST(client, admin):
    p = partner(client, admin, code="ank01", request_fee="7.50", daily_late_fee="2.00", max_outgoing=3)
    assert (p["code"], p["request_fee"], p["daily_late_fee"], p["max_outgoing"], p["is_active"]) == ("ANK01", "7.50", "2.00", 3, True)
'''),
    dict(id="T-ILL-01-b", req="LIB-ILL-01", type="Error", input="Code `A`; fee 50.01; daily 10.01; max_outgoing 0 and 21; email `x`; duplicate code `IST` / `ist`; librarian creates", expected="`422` six times; `409 CONFLICT` with `details.field` `code`; `403`", code='''
def TEST(client, admin, librarian):
    for fields in (dict(code="A"), dict(request_fee="50.01"), dict(daily_late_fee="10.01"), dict(max_outgoing=0), dict(max_outgoing=21), dict(email="x")):
        partner(client, admin, expect=422, **fields)
    partner(client, admin, code="IST")
    assert partner(client, admin, code="ist", expect=409)["error"]["details"]["field"] == "code"
    partner(client, librarian, expect=403)
'''),
    dict(id="T-ILL-02-a", req="LIB-ILL-02", type="Normal", input="PATCH `name` and `request_fee`; PATCH `code`", expected="200 with the new values; `422`", code='''
def TEST(client, admin):
    p = partner(client, admin)
    url = f"/api/v1/ill-partners/{p['id']}"
    out = ok(client.patch(url, headers=admin, json={"name": "Ankara Kütüphanesi", "request_fee": "3.00"}))
    assert (out["name"], out["request_fee"]) == ("Ankara Kütüphanesi", "3.00")
    assert client.patch(url, headers=admin, json={"code": "NEW"}).status_code == 422
'''),
    dict(id="T-ILL-02-b", req="LIB-ILL-02", type="Normal", input="Request sent to a partner with fee 5.00; partner fee changed to 9.00; received and collected", expected="`ill_request_fee` 5.00 (value at send time)", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin, request_fee="5.00")
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"request_fee": "9.00"}))
    ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "collect"))
    assert fees_of(client, librarian, m["id"]) == [("ill_request_fee", "5.00")]
'''),
    dict(id="T-ILL-03-a", req="LIB-ILL-03", type="Error", input="Inactive partner: send a request to it; new outgoing request", expected="`409 PARTNER_INACTIVE` both", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"is_active": False}))
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    err(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}), 409, "PARTNER_INACTIVE")
    assert error_code(outgoing(client, librarian, p, create_book(client, librarian), expect=409)) == "PARTNER_INACTIVE"
'''),
    dict(id="T-ILL-03-b", req="LIB-ILL-03", type="Normal", input="Request sent; partner deactivated; book received", expected="200, `received`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    req = sent(client, librarian, p, member(client, librarian, branch_a))
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"is_active": False}))
    out = ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    assert out["status"] == "received"
'''),
    dict(id="T-ILL-04-a", req="LIB-ILL-04", type="Normal", input="Partners IZM, ANK (name Ankara Merkez), BUR (inactive); list; `q=merkez`; `is_active=false`", expected="ANK, BUR, IZM; ANK; BUR", code='''
def TEST(client, admin, librarian):
    partner(client, admin, code="IZM")
    partner(client, admin, code="ANK", name="Ankara Merkez")
    bur = partner(client, admin, code="BUR")
    ok(client.patch(f"/api/v1/ill-partners/{bur['id']}", headers=admin, json={"is_active": False}))
    codes = lambda **p: [x["code"] for x in items(get(client, librarian, "ill-partners", **p))]
    assert codes() == ["ANK", "BUR", "IZM"]
    assert codes(q="merkez") == ["ANK"]
    assert codes(is_active="false") == ["BUR"]
'''),
    dict(id="T-ILL-04-b", req="LIB-ILL-04", type="Normal", input="Partner with one sent incoming request, one cancelled one and one shipped outgoing request; member reads partners", expected="`open_incoming` 1, `open_outgoing` 1; member `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    sent(client, librarian, p, m)
    other = sent(client, librarian, p, m)
    ok(step(client, librarian, other["id"], "cancel"))
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    out = get(client, librarian, f"ill-partners/{p['id']}")
    assert (out["open_incoming"], out["open_outgoing"]) == (1, 1)
    assert client.get("/api/v1/ill-partners", headers=member_headers(client, m)).status_code == 403
'''),
    # ---------------------------------------------------------------- new incoming request
    dict(id="T-ILL-05-a", req="LIB-ILL-05", type="Normal", input="Member requests a book with a hyphenated ISBN", expected="201: `requested`, own `member_id`, ISBN without hyphens, `tried_partner_ids` empty, `partner_id` null", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    isbn = isbn13(555000001)
    r = ok(new_request(client, member_headers(client, m), title="Nadir Eser", author="Ayşe Yazar", isbn=f"{isbn[:3]}-{isbn[3:]}"), 201)
    assert (r["status"], r["member_id"], r["title"], r["author"], r["isbn"], r["tried_partner_ids"], r["partner_id"]) == ("requested", m["id"], "Nadir Eser", "Ayşe Yazar", isbn, [], None)
'''),
    dict(id="T-ILL-05-b", req="LIB-ILL-05", type="Error", input="Librarian without `member_id`; member with `member_id`; invalid ISBN; empty title", expected="`422` each", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert new_request(client, librarian).status_code == 422
    assert new_request(client, mh, m["id"]).status_code == 422
    assert new_request(client, mh, isbn="9780000000000").status_code == 422
    assert new_request(client, mh, title="").status_code == 422
'''),
    dict(id="T-ILL-06-a", req="LIB-ILL-06", type="Error", input="Passive member; member on 2027-11-02 (membership ended)", expected="`409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, librarian, branch_a):
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(new_request(client, librarian, p["id"]), 409, "MEMBER_PASSIVE")
    at(clock, "2027-11-02")
    err(new_request(client, librarian, m["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-ILL-06-b", req="LIB-ILL-06", type="Error", input="Guest requests", expected="`409 ILL_NOT_ALLOWED_FOR_TYPE`", code='''
def TEST(client, librarian, branch_a):
    g = member(client, librarian, branch_a, membership_type="guest")
    err(new_request(client, librarian, g["id"]), 409, "ILL_NOT_ALLOWED_FOR_TYPE")
'''),
    dict(id="T-ILL-06-c", req="LIB-ILL-06", type="Boundary", input="Member with debt 50.00; member with debt 49.99", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"; 201", code='''
def TEST(client, librarian, branch_a):
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(new_request(client, librarian, m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(new_request(client, librarian, m2["id"]), 201)
'''),
    dict(id="T-ILL-06-d", req="LIB-ILL-06", type="Error", input="Member with a book loan due 2026-11-16 requests on 2026-11-17", expected="`409 MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, librarian, branch_a):
    m = member(client, librarian, branch_a)
    _, copy = book_with_copy(client, librarian, branch_a)
    lend(client, librarian, m["id"], copy["id"])
    at(clock, "2026-11-17")
    err(new_request(client, librarian, m["id"]), 409, "MEMBER_HAS_OVERDUE")
'''),
    dict(id="T-ILL-06-e", req="LIB-ILL-06", type="Boundary", input="Student with 2 open requests (one cancelled request does not count) makes a third", expected="`409 ILL_LIMIT_REACHED` with `details.limit` 2", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    gone = ok(new_request(client, librarian, m["id"]), 201)
    ok(step(client, librarian, gone["id"], "cancel"))
    ok(new_request(client, librarian, m["id"]), 201)
    ok(new_request(client, librarian, m["id"]), 201)
    assert err(new_request(client, librarian, m["id"]), 409, "ILL_LIMIT_REACHED")["details"]["limit"] == 2
'''),
    dict(id="T-ILL-06-f", req="LIB-ILL-06", type="Error", input="ISBN of a catalog book with an available copy; ISBN of a catalog book whose only copy is on loan", expected="`409 AVAILABLE_LOCALLY` with `details.book_id`; 201", code='''
def TEST(client, librarian, branch_a):
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    free, _ = book_with_copy(client, librarian, branch_a, isbn=isbn13(555000011))
    busy, copy = book_with_copy(client, librarian, branch_a, isbn=isbn13(555000012))
    lend(client, librarian, other["id"], copy["id"])
    assert err(new_request(client, librarian, m["id"], isbn=isbn13(555000011)), 409, "AVAILABLE_LOCALLY")["details"]["book_id"] == free["id"]
    ok(new_request(client, librarian, m["id"], isbn=isbn13(555000012)), 201)
'''),
    dict(id="T-ILL-06-g", req="LIB-ILL-06", type="Error", input="Member requests the same ISBN twice", expected="`409 DUPLICATE_ILL_REQUEST`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    ok(new_request(client, librarian, m["id"], isbn=isbn13(555000021)), 201)
    err(new_request(client, librarian, m["id"], isbn=isbn13(555000021)), 409, "DUPLICATE_ILL_REQUEST")
'''),
    dict(id="T-ILL-06-h", req="LIB-ILL-06", type="Error", input="Passive guest requests", expected="`MEMBER_PASSIVE` (checked before the membership type)", code='''
def TEST(client, librarian, branch_a):
    pg = member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, pg["id"])
    err(new_request(client, librarian, pg["id"]), 409, "MEMBER_PASSIVE")
'''),
    # ---------------------------------------------------------------- send, reject, cancel
    dict(id="T-ILL-07-a", req="LIB-ILL-07", type="Normal", input="Librarian sends a request to partner P", expected="200: `sent`, `partner_id` P, `tried_partner_ids` [P]", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    out = ok(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}))
    assert (out["status"], out["partner_id"], out["tried_partner_ids"]) == ("sent", p["id"], [p["id"]])
'''),
    dict(id="T-ILL-07-b", req="LIB-ILL-07", type="Error", input="Sent to P1 and rejected; sent to P1 again; then to P2", expected="`409 PARTNER_ALREADY_TRIED`; 200 with `tried_partner_ids` [P1, P2]", code='''
def TEST(client, admin, librarian, branch_a):
    p1, p2 = partner(client, admin), partner(client, admin)
    req = sent(client, librarian, p1, member(client, librarian, branch_a))
    ok(step(client, librarian, req["id"], "reject", {"reason": "Not lent"}))
    err(step(client, librarian, req["id"], "send", {"partner_id": p1["id"]}), 409, "PARTNER_ALREADY_TRIED")
    out = ok(step(client, librarian, req["id"], "send", {"partner_id": p2["id"]}))
    assert out["tried_partner_ids"] == [p1["id"], p2["id"]]
'''),
    dict(id="T-ILL-07-c", req="LIB-ILL-07", type="Boundary", input="Rejected by three partners; sent to a fourth", expected="`409 ILL_TRY_LIMIT_REACHED`", code='''
def TEST(client, admin, librarian, branch_a):
    ps = [partner(client, admin) for _ in range(4)]
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    for p in ps[:3]:
        ok(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}))
        ok(step(client, librarian, req["id"], "reject", {"reason": "No"}))
    err(step(client, librarian, req["id"], "send", {"partner_id": ps[3]["id"]}), 409, "ILL_TRY_LIMIT_REACHED")
'''),
    dict(id="T-ILL-07-d", req="LIB-ILL-07", type="Error", input="Send a `received` request; send a `cancelled` request", expected="`409 INVALID_ILL_STATUS` with `details.status` `received` and `cancelled`", code='''
def TEST(client, admin, librarian, branch_a):
    p1, p2 = partner(client, admin), partner(client, admin)
    m = member(client, librarian, branch_a)
    rec = received(client, librarian, p1, m, branch_a)
    gone = ok(new_request(client, librarian, m["id"]), 201)
    ok(step(client, librarian, gone["id"], "cancel"))
    for req, status in ((rec, "received"), (gone, "cancelled")):
        e = err(step(client, librarian, req["id"], "send", {"partner_id": p2["id"]}), 409, "INVALID_ILL_STATUS")
        assert e["details"]["status"] == status
'''),
    dict(id="T-ILL-08-a", req="LIB-ILL-08", type="Normal", input="Sent request rejected with a reason; a `requested` request rejected", expected="200 `rejected` with `reject_reason`, one `ill_request_rejected` notification; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    out = ok(step(client, librarian, req["id"], "reject", {"reason": "Kitap ödünç verilmiyor"}))
    assert (out["status"], out["reject_reason"]) == ("rejected", "Kitap ödünç verilmiyor")
    assert len(notes(client, librarian, m["id"], "ill_request_rejected")) == 1
    fresh = ok(new_request(client, librarian, m["id"]), 201)
    err(step(client, librarian, fresh["id"], "reject", {"reason": "No"}), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-08-b", req="LIB-ILL-08", type="Error", input="Reject with an empty reason; member rejects", expected="`422`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    assert step(client, librarian, req["id"], "reject", {"reason": ""}).status_code == 422
    assert step(client, member_headers(client, m), req["id"], "reject", {"reason": "No"}).status_code == 403
'''),
    dict(id="T-ILL-09-a", req="LIB-ILL-09", type="Normal", input="Member cancels own `requested` request; cancels again", expected="200 `cancelled`, `member_request`, `closed_on` today, no notification; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    req = ok(new_request(client, mh), 201)
    out = ok(step(client, mh, req["id"], "cancel"))
    assert (out["status"], out["cancel_reason"], out["closed_on"]) == ("cancelled", "member_request", MON)
    assert notes(client, librarian, m["id"], "ill_request_cancelled") == []
    err(step(client, mh, req["id"], "cancel"), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-09-b", req="LIB-ILL-09", type="Normal", input="Librarian cancels a `sent` request; another member cancels a request", expected="`staff_request` and one `ill_request_cancelled` notification; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    assert step(client, member_headers(client, other), req["id"], "cancel").status_code == 403
    assert ok(step(client, librarian, req["id"], "cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m["id"], "ill_request_cancelled")) == 1
'''),
    dict(id="T-ILL-09-c", req="LIB-ILL-09", type="Error", input="Cancel a `received` request", expected="`409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    err(step(client, librarian, req["id"], "cancel"), 409, "INVALID_ILL_STATUS")
'''),
    # ---------------------------------------------------------------- receive and due dates
    dict(id="T-ILL-10-a", req="LIB-ILL-10", type="Normal", input="Book \"Nadir Eser\" received Mon 2026-11-02 with partner due 2026-11-20, replacement 350.00, pickup at branch A", expected="`received`, `received_on` 11-02, `collect_until` 11-09, `due_on` 11-17; one `ill_request_received` notification with the title", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = received(client, librarian, partner(client, admin), m, branch_a, title="Nadir Eser", replacement_cost="350.00")
    r = get_req(client, librarian, req["id"])
    assert (r["status"], r["received_on"], r["collect_until"], r["partner_due_on"], r["due_on"], r["replacement_cost"], r["pickup_branch_id"]) == ("received", MON, "2026-11-09", "2026-11-20", "2026-11-17", "350.00", branch_a["id"])
    n = notes(client, librarian, m["id"], "ill_request_received")
    assert len(n) == 1 and "Nadir Eser" in n[0]["message"] and n[0]["ill_request_id"] == req["id"]
'''),
    dict(id="T-ILL-10-b", req="LIB-ILL-10", type="Error", input="Receive with an inactive pickup branch; with replacement 0.00; receive a `requested` request", expected="`409 BRANCH_INACTIVE`; `422`; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    zz = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, zz["id"])
    body = {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": zz["id"]}
    err(step(client, librarian, req["id"], "receive", body), 409, "BRANCH_INACTIVE")
    body.update(pickup_branch_id=branch_a["id"], replacement_cost="0.00")
    assert step(client, librarian, req["id"], "receive", body).status_code == 422
    fresh = ok(new_request(client, librarian, m["id"]), 201)
    err(step(client, librarian, fresh["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-11-a", req="LIB-ILL-11", type="Boundary", input="Today Mon 2026-11-02: partner due Wed 2026-11-11 (due_on 11-06); Thu 2026-11-12 (due_on 11-09)", expected="`409 ILL_PERIOD_TOO_SHORT` with `details.due_on` 2026-11-06; then 200 with `due_on` 2026-11-09", code='''
def TEST(client, admin, librarian, branch_a):
    req = sent(client, librarian, partner(client, admin), member(client, librarian, branch_a))
    body = {"partner_due_on": "2026-11-11", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}
    assert err(step(client, librarian, req["id"], "receive", body), 409, "ILL_PERIOD_TOO_SHORT")["details"]["due_on"] == "2026-11-06"
    body["partner_due_on"] = "2026-11-12"
    assert ok(step(client, librarian, req["id"], "receive", body))["due_on"] == "2026-11-09"
'''),
    dict(id="T-ILL-12-a", req="LIB-ILL-12", type="Normal", input="Partner due Mon 2026-11-16", expected="`due_on` Wed 2026-11-11", code='''
def TEST(client, admin, librarian, branch_a):
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a, partner_due_on="2026-11-16")
    assert get_req(client, librarian, req["id"])["due_on"] == "2026-11-11"
'''),
    dict(id="T-ILL-12-b", req="LIB-ILL-12", type="Normal", input="On Mon 2026-10-19 a book is received with partner due Mon 2026-11-02", expected="`due_on` Tue 2026-10-27 (29 Oct is a holiday)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    at(clock, "2026-10-19")
    req = received(client, librarian, p, m, branch_a, partner_due_on="2026-11-02")
    assert get_req(client, librarian, req["id"])["due_on"] == "2026-10-27"
'''),
    dict(id="T-ILL-13-a", req="LIB-ILL-13", type="Normal", input="Received request collected on Mon", expected="200: `on_loan`, `collected_on` 2026-11-02, not overdue, accrued 0.00", code='''
def TEST(client, admin, librarian, branch_a):
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    out = ok(step(client, librarian, req["id"], "collect"))
    assert (out["status"], out["collected_on"], out["overdue"], out["accrued_late_fee"]) == ("on_loan", MON, False, "0.00")
'''),
    dict(id="T-ILL-13-b", req="LIB-ILL-13", type="Boundary", input="Received Mon (collect until 2026-11-09): one collected on 11-09, another on 11-10", expected="200; `409 ILL_COLLECT_PERIOD_OVER`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = received(client, librarian, p, m1, branch_a), received(client, librarian, p, m2, branch_a)
    at(clock, "2026-11-09")
    ok(step(client, librarian, r1["id"], "collect"))
    at(clock, "2026-11-10")
    err(step(client, librarian, r2["id"], "collect"), 409, "ILL_COLLECT_PERIOD_OVER")
'''),
    dict(id="T-ILL-13-c", req="LIB-ILL-13", type="Error", input="Book received; member gets a debt of 50.00; collect", expected="`409 MEMBER_BLOCKED_BY_DEBT`; the request stays `received`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = received(client, librarian, partner(client, admin), m, branch_a)
    debt(client, librarian, branch_a, m, "50.00")
    err(step(client, librarian, req["id"], "collect"), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert get_req(client, librarian, req["id"])["status"] == "received"
'''),
    dict(id="T-ILL-14-a", req="LIB-ILL-14", type="Normal", input="Partner fee 7.50: collected; partner fee 0.00: collected", expected="One `ill_request_fee` 7.50 with `ill_request_id`; no fee for the second", code='''
def TEST(client, admin, librarian, branch_a):
    paid, free = partner(client, admin, request_fee="7.50"), partner(client, admin, request_fee="0.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    req = on_loan(client, librarian, paid, m1, branch_a)
    on_loan(client, librarian, free, m2, branch_a)
    fees = items(member_fees(client, librarian, m1["id"]))
    assert [(f["kind"], f["amount"], f["ill_request_id"]) for f in fees] == [("ill_request_fee", "7.50", req["id"])]
    assert member_fees(client, librarian, m2["id"])["total"] == 0
'''),
    dict(id="T-ILL-15-a", req="LIB-ILL-15", type="Normal", input="Member asks for a renewal of an on-loan request; asks again", expected="200 `renewal` `requested`; `409 ILL_RENEWAL_ALREADY_REQUESTED`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    mh = member_headers(client, m)
    assert ok(step(client, mh, req["id"], "renewal-request"))["renewal"] == "requested"
    err(step(client, mh, req["id"], "renewal-request"), 409, "ILL_RENEWAL_ALREADY_REQUESTED")
'''),
    dict(id="T-ILL-15-b", req="LIB-ILL-15", type="Error", input="Renewal asked on 2026-11-18 (due 11-17); renewal asked for a `received` request", expected="`409 ILL_OVERDUE`; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    late = on_loan(client, librarian, p, m1, branch_a)
    waiting = received(client, librarian, p, m2, branch_a)
    err(step(client, librarian, waiting["id"], "renewal-request"), 409, "INVALID_ILL_STATUS")
    at(clock, "2026-11-18")
    err(step(client, librarian, late["id"], "renewal-request"), 409, "ILL_OVERDUE")
'''),
    dict(id="T-ILL-16-a", req="LIB-ILL-16", type="Normal", input="Renewal requested; partner approves until Fri 2026-12-04", expected="`renewal` `approved`, `partner_due_on` 12-04, `due_on` Tue 2026-12-01; one `ill_renewal_answered` notification", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    ok(step(client, librarian, req["id"], "renewal-request"))
    out = ok(step(client, librarian, req["id"], "renewal-answer", {"approved": True, "partner_due_on": "2026-12-04"}))
    assert (out["renewal"], out["partner_due_on"], out["due_on"]) == ("approved", "2026-12-04", "2026-12-01")
    assert len(notes(client, librarian, m["id"], "ill_renewal_answered")) == 1
'''),
    dict(id="T-ILL-16-b", req="LIB-ILL-16", type="Error", input="Answer without a renewal request; refused answer; approval with a date before the old one", expected="`409 ILL_NO_RENEWAL_REQUESTED`; `renewal` `refused` and due dates unchanged; `422`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a), on_loan(client, librarian, p, m2, branch_a)
    err(step(client, librarian, r1["id"], "renewal-answer", {"approved": False}), 409, "ILL_NO_RENEWAL_REQUESTED")
    ok(step(client, librarian, r1["id"], "renewal-request"))
    out = ok(step(client, librarian, r1["id"], "renewal-answer", {"approved": False}))
    assert (out["renewal"], out["due_on"]) == ("refused", "2026-11-17")
    ok(step(client, librarian, r2["id"], "renewal-request"))
    assert step(client, librarian, r2["id"], "renewal-answer", {"approved": True, "partner_due_on": "2026-11-19"}).status_code == 422
'''),
    # ---------------------------------------------------------------- return, fees, close, lost
    dict(id="T-ILL-17-a", req="LIB-ILL-17", type="Normal", input="On-loan request returned at branch B on 2026-11-10; returned again", expected="200 `returned`, `returned_on` 11-10, no fee; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    at(clock, "2026-11-10")
    out = ok(step(client, librarian, req["id"], "return", {"branch_id": branch_b["id"]}))
    assert (out["status"], out["returned_on"]) == ("returned", "2026-11-10")
    assert member_fees(client, librarian, m["id"])["total"] == 0
    err(step(client, librarian, req["id"], "return", {"branch_id": branch_b["id"]}), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-18-a", req="LIB-ILL-18", type="Normal", input="Due 2026-11-17, 2.50 per day; returned 2026-11-20", expected="`ill_late_fee` 7.50", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="2.50"), m, branch_a)
    at(clock, "2026-11-20")
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    assert fees_of(client, librarian, m["id"]) == [("ill_late_fee", "7.50")]
'''),
    dict(id="T-ILL-18-b", req="LIB-ILL-18", type="Boundary", input="Replacement 5.00, 2.00 per day: one returned 2026-11-20 (3 days late), one returned 2026-11-17", expected="Fee 5.00 (cap); no fee", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin, daily_late_fee="2.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = on_loan(client, librarian, p, m1, branch_a, replacement_cost="5.00")
    r2 = on_loan(client, librarian, p, m2, branch_a)
    at(clock, "2026-11-17")
    ok(step(client, librarian, r2["id"], "return", {"branch_id": branch_a["id"]}))
    at(clock, "2026-11-20")
    ok(step(client, librarian, r1["id"], "return", {"branch_id": branch_a["id"]}))
    assert fees_of(client, librarian, m1["id"]) == [("ill_late_fee", "5.00")]
    assert member_fees(client, librarian, m2["id"])["total"] == 0
'''),
    dict(id="T-ILL-19-a", req="LIB-ILL-19", type="Boundary", input="Request due 2026-11-17; the member borrows a book on 11-17 and another on 11-18", expected="201; `409 MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    (_, c1), (_, c2) = book_with_copy(client, librarian, branch_a), book_with_copy(client, librarian, branch_a)
    at(clock, "2026-11-17")
    lend(client, librarian, m["id"], c1["id"])
    at(clock, "2026-11-18")
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"
'''),
    dict(id="T-ILL-19-b", req="LIB-ILL-19", type="Normal", input="Request due 2026-11-17, 2.50 per day; balance and request read on 2026-11-20", expected="Request overdue with accrued 7.50; balance `accrued_late_fees` 7.50, `total_debt` 7.50", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="2.50"), m, branch_a)
    at(clock, "2026-11-20")
    r = get_req(client, librarian, req["id"])
    assert (r["overdue"], r["accrued_late_fee"]) == (True, "7.50")
    b = balance(client, librarian, m["id"])
    assert (b["accrued_late_fees"], b["total_debt"]) == ("7.50", "7.50")
'''),
    dict(id="T-ILL-20-a", req="LIB-ILL-20", type="Normal", input="Close a `returned` request; close an `on_loan` request", expected="200 `closed` with `closed_on`; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a), on_loan(client, librarian, p, m2, branch_a)
    ok(step(client, librarian, r1["id"], "return", {"branch_id": branch_a["id"]}))
    out = ok(step(client, librarian, r1["id"], "close"))
    assert (out["status"], out["closed_on"]) == ("closed", MON)
    err(step(client, librarian, r2["id"], "close"), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-21-a", req="LIB-ILL-21", type="Normal", input="Request due 2026-11-17 (1.00 per day, replacement 200.00) reported lost on 2026-11-20", expected="`lost`; fees `ill_late_fee` 3.00 and `ill_lost` 200.00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="1.00"), m, branch_a)
    at(clock, "2026-11-20")
    assert ok(step(client, librarian, req["id"], "report-lost"))["status"] == "lost"
    assert fees_of(client, librarian, m["id"]) == [("ill_late_fee", "3.00"), ("ill_lost", "200.00")]
'''),
    dict(id="T-ILL-21-b", req="LIB-ILL-21", type="Error", input="Reported lost before its due date; a returned request reported lost", expected="Only `ill_lost`; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a, replacement_cost="80.00"), on_loan(client, librarian, p, m2, branch_a)
    ok(step(client, librarian, r1["id"], "report-lost"))
    assert fees_of(client, librarian, m1["id"]) == [("ill_lost", "80.00")]
    ok(step(client, librarian, r2["id"], "return", {"branch_id": branch_a["id"]}))
    err(step(client, librarian, r2["id"], "report-lost"), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-22-a", req="LIB-ILL-22", type="Boundary", input="Received Mon (collect until 2026-11-09); process on 11-09 and on 11-10; then close", expected="`uncollected` 0, then 1; status `uncollected`, one `ill_request_uncollected` notification, no fee; close 200", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    req = received(client, librarian, partner(client, admin, request_fee="5.00"), m, branch_a)
    at(clock, "2026-11-09")
    assert process(client, librarian)["uncollected"] == 0
    at(clock, "2026-11-10")
    assert process(client, librarian)["uncollected"] == 1
    assert get_req(client, librarian, req["id"])["status"] == "uncollected"
    assert len(notes(client, librarian, m["id"], "ill_request_uncollected")) == 1
    assert member_fees(client, librarian, m["id"])["total"] == 0
    assert ok(step(client, librarian, req["id"], "close"))["status"] == "closed"
'''),
    dict(id="T-ILL-22-b", req="LIB-ILL-22", type="Boundary", input="Copy shipped to a partner Mon (due 2026-11-30); process on 11-30 and on 12-01", expected="`{uncollected: 0, overdue_outgoing: 0}`, then `overdue_outgoing` 1", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    at(clock, "2026-11-30")
    assert process(client, librarian) == {"uncollected": 0, "overdue_outgoing": 0}
    at(clock, "2026-12-01")
    assert process(client, librarian)["overdue_outgoing"] == 1
'''),
    dict(id="T-ILL-23-a", req="LIB-ILL-23", type="Normal", input="R1 (M1, on loan, due 11-17), R2 (M2, sent to P2), R3 (M1, requested); list on 2026-11-18 and filters", expected="Order R1, R2, R3; `status=sent` → R2; `partner_id` P2 → R2; `overdue=true` → R1; `member_id` M1 → R1, R3", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p1, p2 = partner(client, admin), partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = on_loan(client, librarian, p1, m1, branch_a)
    r2 = sent(client, librarian, p2, m2)
    r3 = ok(new_request(client, librarian, m1["id"]), 201)
    at(clock, "2026-11-18")
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "ill-requests", **p))]
    assert ids() == [r1["id"], r2["id"], r3["id"]]
    assert ids(status="sent") == [r2["id"]]
    assert ids(partner_id=p2["id"]) == [r2["id"]]
    assert ids(overdue="true") == [r1["id"]]
    assert ids(member_id=m1["id"]) == [r1["id"], r3["id"]]
'''),
    dict(id="T-ILL-23-b", req="LIB-ILL-23", type="Error", input="Member reads own request, a request of another member, the general list, own list", expected="200; 403; 403; 200 with 1 item", code='''
def TEST(client, librarian, branch_a):
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = ok(new_request(client, librarian, m["id"]), 201), ok(new_request(client, librarian, other["id"]), 201)
    mh = member_headers(client, m)
    assert client.get(f"/api/v1/ill-requests/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/ill-requests/{foreign['id']}", headers=mh).status_code == 403
    assert client.get("/api/v1/ill-requests", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/ill-requests")["total"] == 1
'''),
    # ---------------------------------------------------------------- outgoing
    dict(id="T-ILL-24-a", req="LIB-ILL-24", type="Normal", input="Librarian creates an outgoing request; one for an unknown book; member creates one", expected="201 `requested` with `copy_id` null; `404`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book = create_book(client, librarian)
    o = outgoing(client, librarian, p, book)
    assert (o["status"], o["partner_id"], o["book_id"], o["copy_id"]) == ("requested", p["id"], book["id"], None)
    outgoing(client, librarian, p, {"id": 999999}, expect=404)
    mh = member_headers(client, member(client, librarian, branch_a))
    outgoing(client, mh, p, book, expect=403)
'''),
    dict(id="T-ILL-25-a", req="LIB-ILL-25", type="Normal", input="Outgoing request shipped with an available copy on Mon", expected="`shipped`, `shipped_on` 11-02, `due_on` 11-30; copy `at_partner`; book availability 0 of 1", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    out = ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    assert (out["status"], out["copy_id"], out["shipped_on"], out["due_on"]) == ("shipped", copy["id"], MON, "2026-11-30")
    assert get_copy(client, librarian, copy["id"])["status"] == "at_partner"
    avail = get(client, librarian, f"books/{book['id']}")["availability"]
    assert [(a["available"], a["total"]) for a in avail] == [(0, 1)]
'''),
    dict(id="T-ILL-25-b", req="LIB-ILL-25", type="Error", input="Ship with a copy of another book; with a copy on loan", expected="`422`; `409 INVALID_COPY_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    _, foreign = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    assert out_step(client, librarian, o["id"], "ship", {"copy_id": foreign["id"]}).status_code == 422
    lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"])
    err(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}), 409, "INVALID_COPY_STATUS")
'''),
    dict(id="T-ILL-25-c", req="LIB-ILL-25", type="Error", input="Partner has a copy due 2026-11-30 not returned; on 12-01 a second request is shipped", expected="`409 PARTNER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = partner(client, admin)
    b1, c1 = book_with_copy(client, librarian, branch_a)
    b2, c2 = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, b1)["id"], "ship", {"copy_id": c1["id"]}))
    o2 = outgoing(client, librarian, p, b2)
    at(clock, "2026-12-01")
    err(out_step(client, librarian, o2["id"], "ship", {"copy_id": c2["id"]}), 409, "PARTNER_HAS_OVERDUE")
'''),
    dict(id="T-ILL-26-a", req="LIB-ILL-26", type="Normal", input="Decline a requested outgoing request; decline a shipped one", expected="200 `declined`; `409 INVALID_ILL_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o1, o2 = outgoing(client, librarian, p, book), outgoing(client, librarian, p, book)
    assert ok(out_step(client, librarian, o1["id"], "decline"))["status"] == "declined"
    ok(out_step(client, librarian, o2["id"], "ship", {"copy_id": copy["id"]}))
    err(out_step(client, librarian, o2["id"], "decline"), 409, "INVALID_ILL_STATUS")
'''),
    dict(id="T-ILL-27-a", req="LIB-ILL-27", type="Boundary", input="Partner with `max_outgoing` 2 and two requested outgoing requests: a third; after one is declined, again", expected="`409 PARTNER_LIMIT_REACHED` with `details.limit` 2; then 201", code='''
def TEST(client, admin, librarian):
    p = partner(client, admin, max_outgoing=2)
    book = create_book(client, librarian)
    o1 = outgoing(client, librarian, p, book)
    outgoing(client, librarian, p, book)
    assert outgoing(client, librarian, p, book, expect=409)["error"]["details"]["limit"] == 2
    ok(out_step(client, librarian, o1["id"], "decline"))
    outgoing(client, librarian, p, book)
'''),
    dict(id="T-ILL-28-a", req="LIB-ILL-28", type="Normal", input="Copy (home branch A) shipped Mon; returned at branch B on 2026-11-10 (no reservation)", expected="Outgoing `returned`, `returned_on` 11-10; copy `in_transfer` (return transfer to its home branch, LIB-RES-08 (a))", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    at(clock, "2026-11-10")
    out = ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_b["id"]}))
    assert (out["status"], out["returned_on"]) == ("returned", "2026-11-10")
    assert get_copy(client, librarian, copy["id"])["status"] == "in_transfer"
'''),
    dict(id="T-ILL-28-b", req="LIB-ILL-28", type="Normal", input="Only copy at a partner; a member reserves the book for pickup at A; copy returned at A", expected="Copy `on_hold`; reservation `ready`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    res = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_a["id"]}))
    assert get_copy(client, librarian, copy["id"])["status"] == "on_hold"
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "ready"
'''),
    dict(id="T-ILL-29-a", req="LIB-ILL-29", type="Normal", input="Copy (price 120.00) shipped; partner reports it lost", expected="Outgoing `lost`, `amount_due` 120.00; copy `lost`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="120.00")
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    out = ok(out_step(client, librarian, o["id"], "report-lost"))
    assert (out["status"], out["amount_due"]) == ("lost", "120.00")
    assert get_copy(client, librarian, copy["id"])["status"] == "lost"
'''),
    dict(id="T-ILL-30-a", req="LIB-ILL-30", type="Normal", input="O1 (P1, book \"Kırmızı\", shipped with barcode OUT-001), O2 (P2, requested); list and filters", expected="Order O1, O2; O1 `book_title` Kırmızı, `barcode` OUT-001; O2 `barcode` null; `status=requested` → O2; `partner_id` P1 → O1", code='''
def TEST(client, admin, librarian, branch_a):
    p1, p2 = partner(client, admin), partner(client, admin)
    book = create_book(client, librarian, title="Kırmızı")
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], barcode="OUT-001")
    o1 = outgoing(client, librarian, p1, book)
    ok(out_step(client, librarian, o1["id"], "ship", {"copy_id": copy["id"]}))
    o2 = outgoing(client, librarian, p2, book)
    rows = items(get(client, librarian, "ill-outgoing"))
    assert [(x["id"], x["book_title"], x["barcode"]) for x in rows] == [(o1["id"], "Kırmızı", "OUT-001"), (o2["id"], "Kırmızı", None)]
    assert [x["id"] for x in items(get(client, librarian, "ill-outgoing", status="requested"))] == [o2["id"]]
    assert [x["id"] for x in items(get(client, librarian, "ill-outgoing", partner_id=p1["id"]))] == [o1["id"]]
'''),
    # ---------------------------------------------------------------- effects on other modules
    dict(id="T-ILL-31-a", req="LIB-ILL-31", type="Normal", input="Copy at a partner: lent to a member; copies listed with `status=at_partner`", expected="`409 COPY_NOT_AVAILABLE` with `details.status` `at_partner`; the copy is listed", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    e = lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"], expect=409)
    assert error_code(e) == "COPY_NOT_AVAILABLE" and e["error"]["details"]["status"] == "at_partner"
    assert [c["id"] for c in items(get(client, librarian, f"books/{book['id']}/copies", status="at_partner"))] == [copy["id"]]
'''),
    dict(id="T-ILL-32-a", req="LIB-ILL-32", type="Error", input="Member with an on-loan request is deactivated", expected="`409 MEMBER_HAS_OPEN_LOANS`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    assert error_code(deactivate_member(client, librarian, m["id"], expect=409)) == "MEMBER_HAS_OPEN_LOANS"
'''),
    dict(id="T-ILL-32-b", req="LIB-ILL-32", type="Normal", input="Member with a `requested` and a `sent` request is deactivated", expected="Both `cancelled` with `member_deactivated`; two `ill_request_cancelled` notifications", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    r1 = ok(new_request(client, librarian, m["id"]), 201)
    r2 = sent(client, librarian, partner(client, admin), m)
    deactivate_member(client, librarian, m["id"])
    for req in (r1, r2):
        out = get_req(client, librarian, req["id"])
        assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert len(notes(client, librarian, m["id"], "ill_request_cancelled")) == 2
'''),
    dict(id="T-ILL-33-a", req="LIB-ILL-33", type="Error", input="Branch QQ is the pickup branch of a received request; QQ deactivated", expected="`409 BRANCH_IN_USE`", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    received(client, librarian, partner(client, admin), member(client, librarian, branch_a), qq)
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
'''),
    dict(id="T-ILL-34-a", req="LIB-ILL-34", type="Normal", input="Academic with an overdue on-loan request (due 11-17) and a requested one; summary on 2026-11-18", expected="`ill` = `{open_requests: 2, on_loan: 1, overdue: 1}`; `borrowing.eligible` false with `MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a, membership_type="academic")
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    ok(new_request(client, librarian, m["id"]), 201)
    at(clock, "2026-11-18")
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["ill"] == {"open_requests": 2, "on_loan": 1, "overdue": 1}
    assert s["borrowing"]["eligible"] is False and "MEMBER_HAS_OVERDUE" in s["borrowing"]["reasons"]
'''),
    dict(id="T-ILL-35-a", req="LIB-ILL-35", type="Normal", input="Request fee 8.00; payment 3.00; admin waives the fee; fee list `kind=ill_request_fee`", expected="Paid 3.00, outstanding 5.00; `waived`; the list has this fee", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin, request_fee="8.00"), m, branch_a)
    pay(client, librarian, m["id"], "3.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["kind"], fee["paid_amount"], fee["outstanding"]) == ("ill_request_fee", "3.00", "5.00")
    assert waive(client, admin, fee["id"])["status"] == "waived"
    assert [f["id"] for f in items(get(client, librarian, "fees", kind="ill_request_fee"))] == [fee["id"]]
'''),
    dict(id="T-ILL-36-a", req="LIB-ILL-36", type="Normal", input="Book \"Mavi Defter\" received with pickup at branch A (collect until 2026-11-09)", expected="`ill_request_received` message contains the title, the branch name and 2026-11-09", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    received(client, librarian, partner(client, admin), m, branch_a, title="Mavi Defter")
    msg = notes(client, librarian, m["id"], "ill_request_received")[0]["message"]
    assert "Mavi Defter" in msg and branch_a["name"] in msg and "2026-11-09" in msg
'''),
    dict(id="T-ILL-36-b", req="LIB-ILL-36", type="Normal", input="Member requests, the request is sent, received, collected (no fee), renewal asked and returned", expected="The member's notifications: only `ill_request_received`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    req = ok(new_request(client, mh), 201)
    ok(step(client, librarian, req["id"], "send", {"partner_id": partner(client, admin)["id"]}))
    ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "collect"))
    ok(step(client, mh, req["id"], "renewal-request"))
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    assert [n["type"] for n in notes(client, librarian, m["id"])] == ["ill_request_received"]
'''),
    dict(id="T-ILL-37-a", req="LIB-ILL-37", type="Normal", input="Partner created; request created, sent, received, collected, returned, closed; audit log filtered by event", expected="One entry each", code='''
def TEST(client, admin, librarian, branch_a):
    req = on_loan(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "close"))
    for event in ("ill_partner_created", "ill_request_created", "ill_request_sent", "ill_request_received", "ill_request_collected", "ill_request_returned", "ill_request_closed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-ILL-37-b", req="LIB-ILL-37", type="Normal", input="Outgoing request created, shipped and returned", expected="One entry each for `ill_outgoing_created`, `ill_outgoing_shipped`, `ill_outgoing_returned`", code='''
def TEST(client, admin, librarian, branch_a):
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, partner(client, admin), book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_a["id"]}))
    for event in ("ill_outgoing_created", "ill_outgoing_shipped", "ill_outgoing_returned"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-ILL-38-a", req="LIB-ILL-38", type="Normal", input="Partners AAA and BBB (unused). AAA: request R1 sent and rejected, R2 sent and received, returned late on 11-20; an outgoing copy (price 90.00) shipped and lost. Report 2026-11-01 – 2026-11-30", expected="AAA `{sent 2, rejected 1, received 1, late_returns 1, outgoing_shipped 1, outgoing_returned 0, outgoing_lost 1, amount_due \"90.00\"}`; BBB all 0 and \"0.00\"", code='''
def TEST(client, clock, admin, librarian, branch_a):
    aaa = partner(client, admin, code="AAA")
    partner(client, admin, code="BBB")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = sent(client, librarian, aaa, m1)
    ok(step(client, librarian, r1["id"], "reject", {"reason": "No"}))
    r2 = on_loan(client, librarian, aaa, m2, branch_a)
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="90.00")
    o = outgoing(client, librarian, aaa, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    ok(out_step(client, librarian, o["id"], "report-lost"))
    at(clock, "2026-11-20")
    ok(step(client, librarian, r2["id"], "return", {"branch_id": branch_a["id"]}))
    keys = ("partner_code", "sent", "rejected", "received", "late_returns", "outgoing_shipped", "outgoing_returned", "outgoing_lost", "amount_due")
    rows = items(get(client, librarian, "reports/ill-activity", **{"from": "2026-11-01", "to": "2026-11-30"}))
    assert [tuple(r[k] for k in keys) for r in rows] == [("AAA", 2, 1, 1, 1, 1, 0, 1, "90.00"), ("BBB", 0, 0, 0, 0, 0, 0, 0, "0.00")]
'''),
    dict(id="T-ILL-38-b", req="LIB-ILL-38", type="Error", input="`from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31", expected="`422`; `422`; `403`; 200", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/ill-activity"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": "2026-11-05"}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200
'''),
    dict(id="T-ILL-39-a", req="LIB-ILL-39", type="Normal", input="Partner, requests and a copy at a partner exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1; the copy is exported with status `at_partner`", code='''
def TEST(client, admin, librarian, branch_a):
    p = partner(client, admin)
    sent(client, librarian, p, member(client, librarian, branch_a))
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == copy["id"]] == ["at_partner"]
'''),
    dict(id="T-ILL-40-a", req="LIB-ILL-40", type="Error", input="Book without copies that has a declined outgoing request is deleted", expected="`409 IN_USE`", code='''
def TEST(client, admin, librarian):
    book = create_book(client, librarian)
    o = outgoing(client, librarian, partner(client, admin), book)
    ok(out_step(client, librarian, o["id"], "decline"))
    err(client.delete(f"/api/v1/books/{book['id']}", headers=librarian), 409, "IN_USE")
'''),
]
