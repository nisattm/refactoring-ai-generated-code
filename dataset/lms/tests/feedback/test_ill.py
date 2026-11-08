"""Feedback tests: module 18 (Interlibrary loans). Generated from cases/ill.md."""
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


def test_t_ill_01_a(client, admin):
    """T-ILL-01-a (LIB-ILL-01): 201; code ANK01, values kept, active"""
    p = partner(client, admin, code="ank01", request_fee="7.50", daily_late_fee="2.00", max_outgoing=3)
    assert (p["code"], p["request_fee"], p["daily_late_fee"], p["max_outgoing"], p["is_active"]) == ("ANK01", "7.50", "2.00", 3, True)


def test_t_ill_02_a(client, admin):
    """T-ILL-02-a (LIB-ILL-02): 200 with the new values; 422"""
    p = partner(client, admin)
    url = f"/api/v1/ill-partners/{p['id']}"
    out = ok(client.patch(url, headers=admin, json={"name": "Ankara Kütüphanesi", "request_fee": "3.00"}))
    assert (out["name"], out["request_fee"]) == ("Ankara Kütüphanesi", "3.00")
    assert client.patch(url, headers=admin, json={"code": "NEW"}).status_code == 422


def test_t_ill_03_a(client, admin, librarian, branch_a):
    """T-ILL-03-a (LIB-ILL-03): 409 PARTNER_INACTIVE both"""
    p = partner(client, admin)
    ok(client.patch(f"/api/v1/ill-partners/{p['id']}", headers=admin, json={"is_active": False}))
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    err(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}), 409, "PARTNER_INACTIVE")
    assert error_code(outgoing(client, librarian, p, create_book(client, librarian), expect=409)) == "PARTNER_INACTIVE"


def test_t_ill_04_a(client, admin, librarian):
    """T-ILL-04-a (LIB-ILL-04): ANK, BUR, IZM; ANK; BUR"""
    partner(client, admin, code="IZM")
    partner(client, admin, code="ANK", name="Ankara Merkez")
    bur = partner(client, admin, code="BUR")
    ok(client.patch(f"/api/v1/ill-partners/{bur['id']}", headers=admin, json={"is_active": False}))
    codes = lambda **p: [x["code"] for x in items(get(client, librarian, "ill-partners", **p))]
    assert codes() == ["ANK", "BUR", "IZM"]
    assert codes(q="merkez") == ["ANK"]
    assert codes(is_active="false") == ["BUR"]


def test_t_ill_05_a(client, librarian, branch_a):
    """T-ILL-05-a (LIB-ILL-05): 201: requested, own member_id, ISBN without hyphens, tried_partner_ids empty, partner_id null"""
    m = member(client, librarian, branch_a)
    isbn = isbn13(555000001)
    r = ok(new_request(client, member_headers(client, m), title="Nadir Eser", author="Ayşe Yazar", isbn=f"{isbn[:3]}-{isbn[3:]}"), 201)
    assert (r["status"], r["member_id"], r["title"], r["author"], r["isbn"], r["tried_partner_ids"], r["partner_id"]) == ("requested", m["id"], "Nadir Eser", "Ayşe Yazar", isbn, [], None)


def test_t_ill_06_a(client, clock, librarian, branch_a):
    """T-ILL-06-a (LIB-ILL-06): 409 MEMBER_PASSIVE; 409 MEMBERSHIP_EXPIRED"""
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(new_request(client, librarian, p["id"]), 409, "MEMBER_PASSIVE")
    at(clock, "2027-11-02")
    err(new_request(client, librarian, m["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_ill_06_c(client, librarian, branch_a):
    """T-ILL-06-c (LIB-ILL-06): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'; 201"""
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(new_request(client, librarian, m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(new_request(client, librarian, m2["id"]), 201)


def test_t_ill_06_e(client, librarian, branch_a):
    """T-ILL-06-e (LIB-ILL-06): 409 ILL_LIMIT_REACHED with details.limit 2"""
    m = member(client, librarian, branch_a)
    gone = ok(new_request(client, librarian, m["id"]), 201)
    ok(step(client, librarian, gone["id"], "cancel"))
    ok(new_request(client, librarian, m["id"]), 201)
    ok(new_request(client, librarian, m["id"]), 201)
    assert err(new_request(client, librarian, m["id"]), 409, "ILL_LIMIT_REACHED")["details"]["limit"] == 2


def test_t_ill_06_g(client, librarian, branch_a):
    """T-ILL-06-g (LIB-ILL-06): 409 DUPLICATE_ILL_REQUEST"""
    m = member(client, librarian, branch_a)
    ok(new_request(client, librarian, m["id"], isbn=isbn13(555000021)), 201)
    err(new_request(client, librarian, m["id"], isbn=isbn13(555000021)), 409, "DUPLICATE_ILL_REQUEST")


def test_t_ill_07_a(client, admin, librarian, branch_a):
    """T-ILL-07-a (LIB-ILL-07): 200: sent, partner_id P, tried_partner_ids [P]"""
    p = partner(client, admin)
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    out = ok(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}))
    assert (out["status"], out["partner_id"], out["tried_partner_ids"]) == ("sent", p["id"], [p["id"]])


def test_t_ill_07_c(client, admin, librarian, branch_a):
    """T-ILL-07-c (LIB-ILL-07): 409 ILL_TRY_LIMIT_REACHED"""
    ps = [partner(client, admin) for _ in range(4)]
    req = ok(new_request(client, librarian, member(client, librarian, branch_a)["id"]), 201)
    for p in ps[:3]:
        ok(step(client, librarian, req["id"], "send", {"partner_id": p["id"]}))
        ok(step(client, librarian, req["id"], "reject", {"reason": "No"}))
    err(step(client, librarian, req["id"], "send", {"partner_id": ps[3]["id"]}), 409, "ILL_TRY_LIMIT_REACHED")


def test_t_ill_08_a(client, admin, librarian, branch_a):
    """T-ILL-08-a (LIB-ILL-08): 200 rejected with reject_reason, one ill_request_rejected notification; 409 INVALID_ILL_STATUS"""
    p = partner(client, admin)
    m = member(client, librarian, branch_a)
    req = sent(client, librarian, p, m)
    out = ok(step(client, librarian, req["id"], "reject", {"reason": "Kitap ödünç verilmiyor"}))
    assert (out["status"], out["reject_reason"]) == ("rejected", "Kitap ödünç verilmiyor")
    assert len(notes(client, librarian, m["id"], "ill_request_rejected")) == 1
    fresh = ok(new_request(client, librarian, m["id"]), 201)
    err(step(client, librarian, fresh["id"], "reject", {"reason": "No"}), 409, "INVALID_ILL_STATUS")


def test_t_ill_09_a(client, librarian, branch_a):
    """T-ILL-09-a (LIB-ILL-09): 200 cancelled, member_request, closed_on today, no notification; 409 INVALID_ILL_STATUS"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    req = ok(new_request(client, mh), 201)
    out = ok(step(client, mh, req["id"], "cancel"))
    assert (out["status"], out["cancel_reason"], out["closed_on"]) == ("cancelled", "member_request", MON)
    assert notes(client, librarian, m["id"], "ill_request_cancelled") == []
    err(step(client, mh, req["id"], "cancel"), 409, "INVALID_ILL_STATUS")


def test_t_ill_09_c(client, admin, librarian, branch_a):
    """T-ILL-09-c (LIB-ILL-09): 409 INVALID_ILL_STATUS"""
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    err(step(client, librarian, req["id"], "cancel"), 409, "INVALID_ILL_STATUS")


def test_t_ill_10_a(client, admin, librarian, branch_a):
    """T-ILL-10-a (LIB-ILL-10): received, received_on 11-02, collect_until 11-09, due_on 11-17; one ill_request_received notification with the title"""
    m = member(client, librarian, branch_a)
    req = received(client, librarian, partner(client, admin), m, branch_a, title="Nadir Eser", replacement_cost="350.00")
    r = get_req(client, librarian, req["id"])
    assert (r["status"], r["received_on"], r["collect_until"], r["partner_due_on"], r["due_on"], r["replacement_cost"], r["pickup_branch_id"]) == ("received", MON, "2026-11-09", "2026-11-20", "2026-11-17", "350.00", branch_a["id"])
    n = notes(client, librarian, m["id"], "ill_request_received")
    assert len(n) == 1 and "Nadir Eser" in n[0]["message"] and n[0]["ill_request_id"] == req["id"]


def test_t_ill_11_a(client, admin, librarian, branch_a):
    """T-ILL-11-a (LIB-ILL-11): 409 ILL_PERIOD_TOO_SHORT with details.due_on 2026-11-06; then 200 with due_on 2026-11-09"""
    req = sent(client, librarian, partner(client, admin), member(client, librarian, branch_a))
    body = {"partner_due_on": "2026-11-11", "replacement_cost": "200.00", "pickup_branch_id": branch_a["id"]}
    assert err(step(client, librarian, req["id"], "receive", body), 409, "ILL_PERIOD_TOO_SHORT")["details"]["due_on"] == "2026-11-06"
    body["partner_due_on"] = "2026-11-12"
    assert ok(step(client, librarian, req["id"], "receive", body))["due_on"] == "2026-11-09"


def test_t_ill_12_a(client, admin, librarian, branch_a):
    """T-ILL-12-a (LIB-ILL-12): due_on Wed 2026-11-11"""
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a, partner_due_on="2026-11-16")
    assert get_req(client, librarian, req["id"])["due_on"] == "2026-11-11"


def test_t_ill_13_a(client, admin, librarian, branch_a):
    """T-ILL-13-a (LIB-ILL-13): 200: on_loan, collected_on 2026-11-02, not overdue, accrued 0.00"""
    req = received(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    out = ok(step(client, librarian, req["id"], "collect"))
    assert (out["status"], out["collected_on"], out["overdue"], out["accrued_late_fee"]) == ("on_loan", MON, False, "0.00")


def test_t_ill_13_c(client, admin, librarian, branch_a):
    """T-ILL-13-c (LIB-ILL-13): 409 MEMBER_BLOCKED_BY_DEBT; the request stays received"""
    m = member(client, librarian, branch_a)
    req = received(client, librarian, partner(client, admin), m, branch_a)
    debt(client, librarian, branch_a, m, "50.00")
    err(step(client, librarian, req["id"], "collect"), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert get_req(client, librarian, req["id"])["status"] == "received"


def test_t_ill_15_a(client, admin, librarian, branch_a):
    """T-ILL-15-a (LIB-ILL-15): 200 renewal requested; 409 ILL_RENEWAL_ALREADY_REQUESTED"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    mh = member_headers(client, m)
    assert ok(step(client, mh, req["id"], "renewal-request"))["renewal"] == "requested"
    err(step(client, mh, req["id"], "renewal-request"), 409, "ILL_RENEWAL_ALREADY_REQUESTED")


def test_t_ill_16_a(client, admin, librarian, branch_a):
    """T-ILL-16-a (LIB-ILL-16): renewal approved, partner_due_on 12-04, due_on Tue 2026-12-01; one ill_renewal_answered notification"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    ok(step(client, librarian, req["id"], "renewal-request"))
    out = ok(step(client, librarian, req["id"], "renewal-answer", {"approved": True, "partner_due_on": "2026-12-04"}))
    assert (out["renewal"], out["partner_due_on"], out["due_on"]) == ("approved", "2026-12-04", "2026-12-01")
    assert len(notes(client, librarian, m["id"], "ill_renewal_answered")) == 1


def test_t_ill_17_a(client, clock, admin, librarian, branch_a, branch_b):
    """T-ILL-17-a (LIB-ILL-17): 200 returned, returned_on 11-10, no fee; 409 INVALID_ILL_STATUS"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin), m, branch_a)
    at(clock, "2026-11-10")
    out = ok(step(client, librarian, req["id"], "return", {"branch_id": branch_b["id"]}))
    assert (out["status"], out["returned_on"]) == ("returned", "2026-11-10")
    assert member_fees(client, librarian, m["id"])["total"] == 0
    err(step(client, librarian, req["id"], "return", {"branch_id": branch_b["id"]}), 409, "INVALID_ILL_STATUS")


def test_t_ill_18_a(client, clock, admin, librarian, branch_a):
    """T-ILL-18-a (LIB-ILL-18): ill_late_fee 7.50"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="2.50"), m, branch_a)
    at(clock, "2026-11-20")
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    assert fees_of(client, librarian, m["id"]) == [("ill_late_fee", "7.50")]


def test_t_ill_19_a(client, clock, admin, librarian, branch_a):
    """T-ILL-19-a (LIB-ILL-19): 201; 409 MEMBER_HAS_OVERDUE"""
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    (_, c1), (_, c2) = book_with_copy(client, librarian, branch_a), book_with_copy(client, librarian, branch_a)
    at(clock, "2026-11-17")
    lend(client, librarian, m["id"], c1["id"])
    at(clock, "2026-11-18")
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"


def test_t_ill_21_a(client, clock, admin, librarian, branch_a):
    """T-ILL-21-a (LIB-ILL-21): lost; fees ill_late_fee 3.00 and ill_lost 200.00"""
    m = member(client, librarian, branch_a)
    req = on_loan(client, librarian, partner(client, admin, daily_late_fee="1.00"), m, branch_a)
    at(clock, "2026-11-20")
    assert ok(step(client, librarian, req["id"], "report-lost"))["status"] == "lost"
    assert fees_of(client, librarian, m["id"]) == [("ill_late_fee", "3.00"), ("ill_lost", "200.00")]


def test_t_ill_22_a(client, clock, admin, librarian, branch_a):
    """T-ILL-22-a (LIB-ILL-22): uncollected 0, then 1; status uncollected, one ill_request_uncollected notification, no fee; close 200"""
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


def test_t_ill_23_a(client, clock, admin, librarian, branch_a):
    """T-ILL-23-a (LIB-ILL-23): Order R1, R2, R3; status=sent → R2; partner_id P2 → R2; overdue=true → R1; member_id M1 → R1, R3"""
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


def test_t_ill_25_a(client, admin, librarian, branch_a):
    """T-ILL-25-a (LIB-ILL-25): shipped, shipped_on 11-02, due_on 11-30; copy at_partner; book availability 0 of 1"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    out = ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    assert (out["status"], out["copy_id"], out["shipped_on"], out["due_on"]) == ("shipped", copy["id"], MON, "2026-11-30")
    assert get_copy(client, librarian, copy["id"])["status"] == "at_partner"
    avail = get(client, librarian, f"books/{book['id']}")["availability"]
    assert [(a["available"], a["total"]) for a in avail] == [(0, 1)]


def test_t_ill_25_c(client, clock, admin, librarian, branch_a):
    """T-ILL-25-c (LIB-ILL-25): 409 PARTNER_HAS_OVERDUE"""
    p = partner(client, admin)
    b1, c1 = book_with_copy(client, librarian, branch_a)
    b2, c2 = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, b1)["id"], "ship", {"copy_id": c1["id"]}))
    o2 = outgoing(client, librarian, p, b2)
    at(clock, "2026-12-01")
    err(out_step(client, librarian, o2["id"], "ship", {"copy_id": c2["id"]}), 409, "PARTNER_HAS_OVERDUE")


def test_t_ill_27_a(client, admin, librarian):
    """T-ILL-27-a (LIB-ILL-27): 409 PARTNER_LIMIT_REACHED with details.limit 2; then 201"""
    p = partner(client, admin, max_outgoing=2)
    book = create_book(client, librarian)
    o1 = outgoing(client, librarian, p, book)
    outgoing(client, librarian, p, book)
    assert outgoing(client, librarian, p, book, expect=409)["error"]["details"]["limit"] == 2
    ok(out_step(client, librarian, o1["id"], "decline"))
    outgoing(client, librarian, p, book)


def test_t_ill_28_a(client, clock, admin, librarian, branch_a, branch_b):
    """T-ILL-28-a (LIB-ILL-28): Outgoing returned, returned_on 11-10; copy in_transfer (return transfer to its home branch, LIB-RES-08 (a))"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    at(clock, "2026-11-10")
    out = ok(out_step(client, librarian, o["id"], "returned", {"branch_id": branch_b["id"]}))
    assert (out["status"], out["returned_on"]) == ("returned", "2026-11-10")
    assert get_copy(client, librarian, copy["id"])["status"] == "in_transfer"


def test_t_ill_29_a(client, admin, librarian, branch_a):
    """T-ILL-29-a (LIB-ILL-29): Outgoing lost, amount_due 120.00; copy lost"""
    p = partner(client, admin)
    book = create_book(client, librarian)
    copy = add_copy(client, librarian, book["id"], home_branch_id=branch_a["id"], price="120.00")
    o = outgoing(client, librarian, p, book)
    ok(out_step(client, librarian, o["id"], "ship", {"copy_id": copy["id"]}))
    out = ok(out_step(client, librarian, o["id"], "report-lost"))
    assert (out["status"], out["amount_due"]) == ("lost", "120.00")
    assert get_copy(client, librarian, copy["id"])["status"] == "lost"


def test_t_ill_31_a(client, admin, librarian, branch_a):
    """T-ILL-31-a (LIB-ILL-31): 409 COPY_NOT_AVAILABLE with details.status at_partner; the copy is listed"""
    p = partner(client, admin)
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    e = lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"], expect=409)
    assert error_code(e) == "COPY_NOT_AVAILABLE" and e["error"]["details"]["status"] == "at_partner"
    assert [c["id"] for c in items(get(client, librarian, f"books/{book['id']}/copies", status="at_partner"))] == [copy["id"]]


def test_t_ill_32_a(client, admin, librarian, branch_a):
    """T-ILL-32-a (LIB-ILL-32): 409 MEMBER_HAS_OPEN_LOANS"""
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin), m, branch_a)
    assert error_code(deactivate_member(client, librarian, m["id"], expect=409)) == "MEMBER_HAS_OPEN_LOANS"


def test_t_ill_33_a(client, admin, librarian, branch_a):
    """T-ILL-33-a (LIB-ILL-33): 409 BRANCH_IN_USE"""
    qq = create_branch(client, admin, "QQ")
    received(client, librarian, partner(client, admin), member(client, librarian, branch_a), qq)
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_t_ill_35_a(client, admin, librarian, branch_a):
    """T-ILL-35-a (LIB-ILL-35): Paid 3.00, outstanding 5.00; waived; the list has this fee"""
    m = member(client, librarian, branch_a)
    on_loan(client, librarian, partner(client, admin, request_fee="8.00"), m, branch_a)
    pay(client, librarian, m["id"], "3.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["kind"], fee["paid_amount"], fee["outstanding"]) == ("ill_request_fee", "3.00", "5.00")
    assert waive(client, admin, fee["id"])["status"] == "waived"
    assert [f["id"] for f in items(get(client, librarian, "fees", kind="ill_request_fee"))] == [fee["id"]]


def test_t_ill_36_a(client, admin, librarian, branch_a):
    """T-ILL-36-a (LIB-ILL-36): ill_request_received message contains the title, the branch name and 2026-11-09"""
    m = member(client, librarian, branch_a)
    received(client, librarian, partner(client, admin), m, branch_a, title="Mavi Defter")
    msg = notes(client, librarian, m["id"], "ill_request_received")[0]["message"]
    assert "Mavi Defter" in msg and branch_a["name"] in msg and "2026-11-09" in msg


def test_t_ill_37_a(client, admin, librarian, branch_a):
    """T-ILL-37-a (LIB-ILL-37): One entry each"""
    req = on_loan(client, librarian, partner(client, admin), member(client, librarian, branch_a), branch_a)
    ok(step(client, librarian, req["id"], "return", {"branch_id": branch_a["id"]}))
    ok(step(client, librarian, req["id"], "close"))
    for event in ("ill_partner_created", "ill_request_created", "ill_request_sent", "ill_request_received", "ill_request_collected", "ill_request_returned", "ill_request_closed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event


def test_t_ill_38_a(client, clock, admin, librarian, branch_a):
    """T-ILL-38-a (LIB-ILL-38): AAA {sent 2, rejected 1, received 1, late_returns 1, outgoing_shipped 1, outgoing_returned 0, outgoing_lost 1, amount_due '90.00'}; BBB all 0 and '0.00'"""
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


def test_t_ill_39_a(client, admin, librarian, branch_a):
    """T-ILL-39-a (LIB-ILL-39): The export has exactly the keys of 22.1; the copy is exported with status at_partner"""
    p = partner(client, admin)
    sent(client, librarian, p, member(client, librarian, branch_a))
    book, copy = book_with_copy(client, librarian, branch_a)
    ok(out_step(client, librarian, outgoing(client, librarian, p, book)["id"], "ship", {"copy_id": copy["id"]}))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == copy["id"]] == ["at_partner"]
