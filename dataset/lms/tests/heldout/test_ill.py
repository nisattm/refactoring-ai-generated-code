"""Heldout tests: module 18 (Interlibrary loans). Generated from cases/ill.md."""
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


def test_t_ill_01_b(client, admin, librarian):
    """T-ILL-01-b (LIB-ILL-01): 422 six times; 409 CONFLICT with details.field code; 403"""
    for fields in (dict(code="A"), dict(request_fee="50.01"), dict(daily_late_fee="10.01"), dict(max_outgoing=0), dict(max_outgoing=21), dict(email="x")):
        partner(client, admin, expect=422, **fields)
    partner(client, admin, code="IST")
    assert partner(client, admin, code="ist", expect=409)["error"]["details"]["field"] == "code"
    partner(client, librarian, expect=403)


def test_t_ill_02_b(client, admin, librarian, branch_a):
    """T-ILL-02-b (LIB-ILL-02): ill_request_fee 5.00 (value at send time)"""
    p = partner(client, admin, request_fee="5.00")
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"request_fee": "9.00"}))
    ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "collect"))
    assert fees_of(client, librarian, m["id"]) == [("ill_request_fee", "5.00")]


def test_t_ill_03_b(client, admin, librarian, branch_a):
    """T-ILL-03-b (LIB-ILL-03): 200, received"""
    p = partner(client, admin)
    req = sent(client, librarian, p, member(client, librarian, branch_a))
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"is_active": False}))
    out = ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    assert out["status"] == "received"


def test_t_ill_04_b(client, admin, librarian, branch_a):
    """T-ILL-04-b (LIB-ILL-04): open_incoming 1, open_outgoing 1; member 403"""
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


def test_t_ill_05_b(client, librarian, branch_a):
    """T-ILL-05-b (LIB-ILL-05): 422 each"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert new_request(client, librarian).status_code == 422
    assert new_request(client, mh, m["id"]).status_code == 422
    assert new_request(client, mh, isbn="9780000000000").status_code == 422
    assert new_request(client, mh, title="").status_code == 422


def test_t_ill_06_b(client, librarian, branch_a):
    """T-ILL-06-b (LIB-ILL-06): 409 ILL_NOT_ALLOWED_FOR_TYPE"""
    g = member(client, librarian, branch_a, membership_type="guest")
    err(new_request(client, librarian, g["id"]), 409, "ILL_NOT_ALLOWED_FOR_TYPE")


def test_t_ill_06_d(client, clock, librarian, branch_a):
    """T-ILL-06-d (LIB-ILL-06): 409 MEMBER_HAS_OVERDUE"""
    m = member(client, librarian, branch_a)
    _, copy = book_with_copy(client, librarian, branch_a)
    lend(client, librarian, m["id"], copy["id"])
    at(clock, "2026-11-17")
    err(new_request(client, librarian, m["id"]), 409, "MEMBER_HAS_OVERDUE")


def test_t_ill_06_f(client, librarian, branch_a):
    """T-ILL-06-f (LIB-ILL-06): 409 AVAILABLE_LOCALLY with details.book_id; 201"""
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    free, _ = book_with_copy(client, librarian, branch_a, isbn=isbn13(555000011))
    busy, copy = book_with_copy(client, librarian, branch_a, isbn=isbn13(555000012))
    lend(client, librarian, other["id"], copy["id"])
    assert err(new_request(client, librarian, m["id"], isbn=isbn13(555000011)), 409, "AVAILABLE_LOCALLY")["details"]["book_id"] == free["id"]
    ok(new_request(client, librarian, m["id"], isbn=isbn13(555000012)), 201)


def test_t_ill_06_h(client, librarian, branch_a):
    """T-ILL-06-h (LIB-ILL-06): MEMBER_PASSIVE (checked before the membership type)"""
    pg = member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, pg["id"])
    err(new_request(client, librarian, pg["id"]), 409, "MEMBER_PASSIVE")


def test_t_ill_07_b(client, admin, librarian, branch_a):
    """T-ILL-07-b (LIB-ILL-07): 409 PARTNER_ALREADY_TRIED; 200 with tried_partner_ids [P1, P2]"""
    p1, p2 = partner(client, admin), partner(client, admin)
    req = sent(client, librarian, p1, member(client, librarian, branch_a))
    ok(step(client, librarian, req["id"], "reject", {"reason": "Not lent"}))
    err(step(client, librarian, req["id"], "send", {"partner_id": p1["id"]}), 409, "PARTNER_ALREADY_TRIED")
    out = ok(step(client, librarian, req["id"], "send", {"partner_id": p2["id"]}))
    assert out["tried_partner_ids"] == [p1["id"], p2["id"]]


def test_t_ill_07_d(client, admin, librarian, branch_a):
    """T-ILL-07-d (LIB-ILL-07): 409 INVALID_ILL_STATUS with details.status received and cancelled"""
    p1, p2 = partner(client, admin), partner(client, admin)
    m = member(client, librarian, branch_a)
    rec = received(client, librarian, p1, m, branch_a)
    gone = ok(new_request(client, librarian, m["id"]), 201)
    ok(step(client, librarian, gone["id"], "cancel"))
    for req, status in ((rec, "received"), (gone, "cancelled")):
        e = err(step(client, librarian, req["id"], "send", {"partner_id": p2["id"]}), 409, "INVALID_ILL_STATUS")
        assert e["details"]["status"] == status


def test_t_ill_08_b(client, admin, librarian, branch_a):
    """T-ILL-08-b (LIB-ILL-08): 422; 403"""
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    assert step(client, librarian, req["id"], "reject", {"reason": ""}).status_code == 422
    assert step(client, member_headers(client, m), req["id"], "reject", {"reason": "No"}).status_code == 403


def test_t_ill_09_b(client, admin, librarian, branch_a):
    """T-ILL-09-b (LIB-ILL-09): staff_request and one ill_request_cancelled notification; 403"""
    p = partner(client, admin)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    assert step(client, member_headers(client, other), req["id"], "cancel").status_code == 403
    assert ok(step(client, librarian, req["id"], "cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m["id"], "ill_request_cancelled")) == 1


def test_t_ill_10_b(client, admin, librarian, branch_a):
    """T-ILL-10-b (LIB-ILL-10): 409 BRANCH_INACTIVE; 422; 409 INVALID_ILL_STATUS"""
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


def test_t_ill_12_b(client, clock, admin, librarian, branch_a):
    """T-ILL-12-b (LIB-ILL-12): due_on Tue 2026-10-27 (29 Oct is a holiday)"""
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    at(clock, "2026-10-19")
    req = received(client, librarian, p, m, branch_a, partner_due_on="2026-11-02")
    assert get_req(client, librarian, req["id"])["due_on"] == "2026-10-27"


def test_t_ill_13_b(client, clock, admin, librarian, branch_a):
    """T-ILL-13-b (LIB-ILL-13): 200; 409 ILL_COLLECT_PERIOD_OVER"""
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = received(client, librarian, p, m1, branch_a), received(client, librarian, p, m2, branch_a)
    at(clock, "2026-11-09")
    ok(step(client, librarian, r1["id"], "collect"))
    at(clock, "2026-11-10")
    err(step(client, librarian, r2["id"], "collect"), 409, "ILL_COLLECT_PERIOD_OVER")


def test_t_ill_14_a(client, admin, librarian, branch_a):
    """T-ILL-14-a (LIB-ILL-14): One ill_request_fee 7.50 with ill_request_id; no fee for the second"""
    paid, free = partner(client, admin, request_fee="7.50"), partner(client, admin, request_fee="0.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    req = on_loan(client, librarian, paid, m1, branch_a)
    on_loan(client, librarian, free, m2, branch_a)
    fees = items(member_fees(client, librarian, m1["id"]))
    assert [(f["kind"], f["amount"], f["ill_request_id"]) for f in fees] == [("ill_request_fee", "7.50", req["id"])]
    assert member_fees(client, librarian, m2["id"])["total"] == 0


def test_t_ill_15_b(client, clock, admin, librarian, branch_a):
    """T-ILL-15-b (LIB-ILL-15): 409 ILL_OVERDUE; 409 INVALID_ILL_STATUS"""
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    late = on_loan(client, librarian, p, m1, branch_a)
    waiting = received(client, librarian, p, m2, branch_a)
    err(step(client, librarian, waiting["id"], "renewal-request"), 409, "INVALID_ILL_STATUS")
    at(clock, "2026-11-18")
    err(step(client, librarian, late["id"], "renewal-request"), 409, "ILL_OVERDUE")


def test_t_ill_16_b(client, admin, librarian, branch_a):
    """T-ILL-16-b (LIB-ILL-16): 409 ILL_NO_RENEWAL_REQUESTED; renewal refused and due dates unchanged; 422"""
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a), on_loan(client, librarian, p, m2, branch_a)
    err(step(client, librarian, r1["id"], "renewal-answer", {"approved": False}), 409, "ILL_NO_RENEWAL_REQUESTED")
    ok(step(client, librarian, r1["id"], "renewal-request"))
    out = ok(step(client, librarian, r1["id"], "renewal-answer", {"approved": False}))
    assert (out["renewal"], out["due_on"]) == ("refused", "2026-11-17")
    ok(step(client, librarian, r2["id"], "renewal-request"))
    assert step(client, librarian, r2["id"], "renewal-answer", {"approved": True, "partner_due_on": "2026-11-19"}).status_code == 422


def test_t_ill_18_b(client, clock, admin, librarian, branch_a):
    """T-ILL-18-b (LIB-ILL-18): Fee 5.00 (cap); no fee"""
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


def test_t_ill_19_b(client, clock, admin, librarian, branch_a):
    """T-ILL-19-b (LIB-ILL-19): Request overdue with accrued 7.50; balance accrued_late_fees 7.50, total_debt 7.50"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="2.50"), m, branch_a)
    at(clock, "2026-11-20")
    r = get_req(client, librarian, req["id"])
    assert (r["overdue"], r["accrued_late_fee"]) == (True, "7.50")
    b = balance(client, librarian, m["id"])
    assert (b["accrued_late_fees"], b["total_debt"]) == ("7.50", "7.50")


def test_t_ill_20_a(client, admin, librarian, branch_a):
    """T-ILL-20-a (LIB-ILL-20): 200 closed with closed_on; 409 INVALID_ILL_STATUS"""
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a), on_loan(client, librarian, p, m2, branch_a)
    ok(step(client, librarian, r1["id"], "return", {"branch_id": branch_a["id"]}))
    out = ok(step(client, librarian, r1["id"], "close"))
    assert (out["status"], out["closed_on"]) == ("closed", MON)
    err(step(client, librarian, r2["id"], "close"), 409, "INVALID_ILL_STATUS")


def test_t_ill_21_b(client, admin, librarian, branch_a):
    """T-ILL-21-b (LIB-ILL-21): Only ill_lost; 409 INVALID_ILL_STATUS"""
    p = partner(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = on_loan(client, librarian, p, m1, branch_a, replacement_cost="80.00"), on_loan(client, librarian, p, m2, branch_a)
    ok(step(client, librarian, r1["id"], "report-lost"))
    assert fees_of(client, librarian, m1["id"]) == [("ill_lost", "80.00")]
    ok(step(client, librarian, r2["id"], "return", {"branch_id": branch_a["id"]}))
    err(step(client, librarian, r2["id"], "report-lost"), 409, "INVALID_ILL_STATUS")


def test_t_ill_22_b(client, clock, admin, librarian, branch_a):
    """T-ILL-22-b (LIB-ILL-22): {uncollected: 0, overdue_outgoing: 0}, then overdue_outgoing 1"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    at(clock, "2026-11-30")
    assert process(client, librarian) == {"uncollected": 0, "overdue_outgoing": 0}
    at(clock, "2026-12-01")
    assert process(client, librarian)["overdue_outgoing"] == 1


def test_t_ill_23_b(client, librarian, branch_a):
    """T-ILL-23-b (LIB-ILL-23): 200; 403; 403; 200 with 1 item"""
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = ok(new_request(client, librarian, m["id"]), 201), ok(new_request(client, librarian, other["id"]), 201)
    mh = member_headers(client, m)
    assert client.get(f"/api/v1/ill-requests/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/ill-requests/{foreign['id']}", headers=mh).status_code == 403
    assert client.get("/api/v1/ill-requests", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/ill-requests")["total"] == 1


def test_t_ill_24_a(client, admin, librarian, branch_a):
    """T-ILL-24-a (LIB-ILL-24): 201 requested with copy_id null; 404; 403"""
    p = partner(client, admin)
    book = create_book(client, librarian)
    o = outgoing(client, librarian, p, book)
    assert (o["status"], o["partner_id"], o["book_id"], o["copy_id"]) == ("requested", p["id"], book["id"], None)
    outgoing(client, librarian, p, {"id": 999999}, expect=404)
    mh = member_headers(client, member(client, librarian, branch_a))
    outgoing(client, mh, p, book, expect=403)


def test_t_ill_25_b(client, admin, librarian, branch_a):
    """T-ILL-25-b (LIB-ILL-25): 422; 409 INVALID_COPY_STATUS"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    _, foreign = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    assert out_step(client, librarian, o["id"], "ship", {"copy_id": foreign["id"]}).status_code == 422
    lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"])
    err(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}), 409, "INVALID_COPY_STATUS")


def test_t_ill_26_a(client, admin, librarian, branch_a):
    """T-ILL-26-a (LIB-ILL-26): 200 declined; 409 INVALID_ILL_STATUS"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o1, o2 = outgoing(client, librarian, p, book), outgoing(client, librarian, p, book)
    assert ok(out_step(client, librarian, o1["id"], "decline"))["status"] == "declined"
    ok(out_step(client, librarian, o2["id"], "ship", {"copy_id": copy["id"]}))
    err(out_step(client, librarian, o2["id"], "decline"), 409, "INVALID_ILL_STATUS")


def test_t_ill_28_b(client, admin, librarian, branch_a):
    """T-ILL-28-b (LIB-ILL-28): Copy on_hold; reservation ready"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    res = reserve(client, librarian, book_id=book["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_a["id"]}))
    assert get_copy(client, librarian, copy["id"])["status"] == "on_hold"
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "ready"


def test_t_ill_30_a(client, admin, librarian, branch_a):
    """T-ILL-30-a (LIB-ILL-30): Order O1, O2; O1 book_title Kırmızı, barcode OUT-1; O2 barcode null; status=requested → O2; partner_id P1 → O1"""
    p1, p2 = partner(client, admin), partner(client, admin)
    book = create_book(client, librarian, title="Kırmızı")
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], barcode="OUT-1")
    o1 = outgoing(client, librarian, p1, book)
    ok(out_step(client, librarian, o1["id"], "ship", {"copy_id": copy["id"]}))
    o2 = outgoing(client, librarian, p2, book)
    rows = items(get(client, librarian, "ill-outgoing"))
    assert [(x["id"], x["book_title"], x["barcode"]) for x in rows] == [(o1["id"], "Kırmızı", "OUT-1"), (o2["id"], "Kırmızı", None)]
    assert [x["id"] for x in items(get(client, librarian, "ill-outgoing", status="requested"))] == [o2["id"]]
    assert [x["id"] for x in items(get(client, librarian, "ill-outgoing", partner_id=p1["id"]))] == [o1["id"]]


def test_t_ill_32_b(client, admin, librarian, branch_a):
    """T-ILL-32-b (LIB-ILL-32): Both cancelled with member_deactivated; two ill_request_cancelled notifications"""
    m = member(client, librarian, branch_a)
    r1 = ok(new_request(client, librarian, m["id"]), 201)
    r2 = sent(client, librarian, partner(client, admin), m)
    deactivate_member(client, librarian, m["id"])
    for req in (r1, r2):
        out = get_req(client, librarian, req["id"])
        assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert len(notes(client, librarian, m["id"], "ill_request_cancelled")) == 2


def test_t_ill_34_a(client, clock, admin, librarian, branch_a):
    """T-ILL-34-a (LIB-ILL-34): ill = {open_requests: 2, on_loan: 1, overdue: 1}; borrowing.eligible false with MEMBER_HAS_OVERDUE"""
    m = member(client, librarian, branch_a, membership_type="academic")
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    ok(new_request(client, librarian, m["id"]), 201)
    at(clock, "2026-11-18")
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["ill"] == {"open_requests": 2, "on_loan": 1, "overdue": 1}
    assert s["borrowing"]["eligible"] is False and "MEMBER_HAS_OVERDUE" in s["borrowing"]["reasons"]


def test_t_ill_36_b(client, admin, librarian, branch_a):
    """T-ILL-36-b (LIB-ILL-36): The member's notifications: only ill_request_received"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    req = ok(new_request(client, mh), 201)
    ok(step(client, librarian, req["id"], "send", {"partner_id": partner(client, admin)["id"]}))
    ok(step(client, librarian, req["id"], "receive", {"partner_due_on": "2026-11-20", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "collect"))
    ok(step(client, mh, req["id"], "renewal-request"))
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    assert [n["type"] for n in notes(client, librarian, m["id"])] == ["ill_request_received"]


def test_t_ill_37_b(client, admin, librarian, branch_a):
    """T-ILL-37-b (LIB-ILL-37): One entry each for ill_outgoing_created, ill_outgoing_shipped, ill_outgoing_returned"""
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, partner(client, admin), book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_a["id"]}))
    for event in ("ill_outgoing_created", "ill_outgoing_shipped", "ill_outgoing_returned"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event


def test_t_ill_38_b(client, librarian, branch_a):
    """T-ILL-38-b (LIB-ILL-38): 422; 422; 403; 200"""
    url = "/api/v1/reports/ill-activity"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": "2026-11-05"}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200


def test_t_ill_40_a(client, admin, librarian):
    """T-ILL-40-a (LIB-ILL-40): 409 IN_USE"""
    book = create_book(client, librarian)
    o = outgoing(client, librarian, partner(client, admin), book)
    ok(out_step(client, librarian, o["id"], "decline"))
    err(client.delete(f"/api/v1/books/{book['id']}", headers=librarian), 409, "IN_USE")
