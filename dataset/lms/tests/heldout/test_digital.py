"""Heldout tests: module 17 (Digital resources). Generated from cases/digital.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, deactivate_member, error_code, items, lend, member_headers, register_member, return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, THU, FRI = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"
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


def resource(client, headers, *, kind="ebook", title=None, provider="Provider", expect=201, **fields):
    _seq[0] += 1
    body = {"kind": kind, "title": title or f"Resource {_seq[0]:03d}", "provider": provider}
    body.update(fields)
    r = client.post("/api/v1/digital-resources", headers=headers, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def license_(client, admin, resource_id, *, copies=1, model="perpetual", starts_on="2026-11-01", ends_on=None, cost="100.00", order_id=None, expect=201):
    body = {"model": model, "copies": copies, "starts_on": starts_on, "cost": cost}
    if ends_on is not None:
        body["ends_on"] = ends_on
    if order_id is not None:
        body["order_id"] = order_id
    r = client.post(f"/api/v1/digital-resources/{resource_id}/licenses", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def ebook(client, admin, *, copies=1, loan_days=14, **fields):
    """Active e-book with a perpetual license of ``copies`` copies from 2026-11-01."""
    res = resource(client, admin, loan_days=loan_days, **fields)
    license_(client, admin, res["id"], copies=copies)
    return res


def database(client, admin, *, seats=1, **fields):
    res = resource(client, admin, kind="database", **fields)
    license_(client, admin, res["id"], copies=seats)
    return res


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def _act(client, headers, path, resource_id, member_id):
    body = {"resource_id": resource_id}
    if member_id is not None:
        body["member_id"] = member_id
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def borrow(client, headers, resource_id, member_id=None):
    return _act(client, headers, "digital-loans", resource_id, member_id)


def hold(client, headers, resource_id, member_id=None):
    return _act(client, headers, "digital-holds", resource_id, member_id)


def session(client, headers, resource_id, member_id=None):
    return _act(client, headers, "digital-sessions", resource_id, member_id)


def post(client, headers, path, body=None):
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def holds_of(client, lib, member_id, **params):
    return items(get(client, lib, f"members/{member_id}/digital-holds", **params))


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def process(client, lib):
    return ok(post(client, lib, "digital/process"))


def debt(client, lib, branch, member_, amount="50.00"):
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def order(client, lib, branch, *, submit=True):
    _seq[0] += 1
    book = create_book(client, lib)
    sup = ok(client.post("/api/v1/suppliers", headers=lib, json={"name": f"Supplier {_seq[0]}"}), 201)
    o = ok(client.post("/api/v1/purchase-orders", headers=lib, json={"supplier_id": sup["id"], "branch_id": branch["id"],
           "lines": [{"book_id": book["id"], "quantity": 1, "unit_price": "10.00"}]}), 201)
    if submit:
        ok(post(client, lib, f"purchase-orders/{o['id']}/submit"))
    return o


def test_t_dig_01_b(client, librarian, branch_a):
    """T-DIG-01-b (LIB-DIG-01): 422 seven times; 403"""
    book = create_book(client, librarian)
    for fields in (dict(kind="database", loan_days=7), dict(kind="database", book_id=book["id"]), dict(loan_days=22),
                   dict(loan_days=0), dict(book_id=999999), dict(kind="audio"), dict(title="")):
        resource(client, librarian, expect=422, **fields)
    resource(client, member_headers(client, member(client, librarian, branch_a)), expect=403)


def test_t_dig_02_b(client, admin, librarian, branch_a):
    """T-DIG-02-b (LIB-DIG-02): M1 due 2026-11-16 09:00 (unchanged); M2 due 2026-11-09 09:00"""
    r = ebook(client, admin, copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"loan_days": 7}))
    l2 = ok(borrow(client, librarian, r["id"], m2["id"]), 201)
    assert same(get(client, librarian, f"digital-loans/{l1['id']}")["due_at"], "2026-11-16", 9) and same(l2["due_at"], "2026-11-09", 9)


def test_t_dig_03_b(client, admin, librarian, branch_a):
    """T-DIG-03-b (LIB-DIG-03): The session has closed_at and open false; 409 RESOURCE_INACTIVE"""
    r = database(client, admin, seats=3)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(session(client, librarian, r["id"], m1["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    s = items(get(client, librarian, f"members/{m1['id']}/digital-sessions"))[0]
    assert s["closed_at"] is not None and s["open"] is False
    err(session(client, librarian, r["id"], m2["id"]), 409, "RESOURCE_INACTIVE")


def test_t_dig_04_b(client, admin, librarian, branch_a):
    """T-DIG-04-b (LIB-DIG-04): E-book capacity 2, in_use 2, available 0, waiting_holds 1; database 3, 1, 2, 0"""
    e, d = ebook(client, admin, copies=2), database(client, admin, seats=3)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, e["id"], m1["id"]), 201)
    ok(borrow(client, librarian, e["id"], m2["id"]), 201)
    ok(hold(client, librarian, e["id"], m3["id"]), 201)
    ok(session(client, librarian, d["id"], m1["id"]), 201)
    keys = ("capacity", "in_use", "available", "waiting_holds")
    mh = member_headers(client, m3)
    assert tuple(get(client, mh, f"digital-resources/{e['id']}")[k] for k in keys) == (2, 2, 0, 1)
    assert tuple(get(client, mh, f"digital-resources/{d['id']}")[k] for k in keys) == (3, 1, 2, 0)


def test_t_dig_05_b(client, admin, librarian):
    """T-DIG-05-b (LIB-DIG-05): 422 seven times (database 500 seats: 201); 403"""
    e, d = resource(client, librarian), resource(client, librarian, kind="database")
    license_(client, admin, e["id"], ends_on="2026-12-31", expect=422)
    license_(client, admin, e["id"], model="subscription", expect=422)
    license_(client, admin, e["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-11-09", expect=422)
    license_(client, admin, e["id"], copies=0, expect=422)
    license_(client, admin, e["id"], copies=101, expect=422)
    license_(client, admin, d["id"], copies=501, expect=422)
    license_(client, admin, d["id"], copies=500)
    license_(client, admin, e["id"], cost="-1.00", expect=422)
    license_(client, librarian, e["id"], expect=403)


def test_t_dig_06_b(client, admin, librarian, branch_a):
    """T-DIG-06-b (LIB-DIG-06): 409 INVALID_ORDER_STATUS"""
    r = resource(client, librarian)
    o = order(client, librarian, branch_a, submit=False)
    ok(post(client, librarian, f"purchase-orders/{o['id']}/cancel"))
    assert error_code(license_(client, admin, r["id"], order_id=o["id"], expect=409)) == "INVALID_ORDER_STATUS"


def test_t_dig_07_b(client, admin, librarian):
    """T-DIG-07-b (LIB-DIG-07): 409 INVALID_LICENSE_STATUS"""
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"], model="subscription", starts_on="2026-10-01", ends_on="2026-11-01")
    assert lic["status"] == "ended"
    err(post(client, admin, f"digital-licenses/{lic['id']}/cancel"), 409, "INVALID_LICENSE_STATUS")


def test_t_dig_08_a(client, admin, librarian, branch_a):
    """T-DIG-08-a (LIB-DIG-08): Order 2026-10-01, 2026-11-10; filter → the pending one; member 403"""
    r = resource(client, librarian)
    later = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    first = license_(client, admin, r["id"], starts_on="2026-10-01")
    url = f"digital-resources/{r['id']}/licenses"
    assert [x["id"] for x in items(get(client, librarian, url))] == [first["id"], later["id"]]
    assert [x["id"] for x in items(get(client, librarian, url, status="pending"))] == [later["id"]]
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/{url}", headers=mh).status_code == 403


def test_t_dig_10_b(client, admin, librarian):
    """T-DIG-10-b (LIB-DIG-10): 409 INVALID_LICENSE_STATUS; 403"""
    r = resource(client, librarian)
    ended = license_(client, admin, r["id"], model="subscription", starts_on="2026-10-01", ends_on="2026-10-31")
    pend = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    err(client.patch(f"/api/v1/digital-licenses/{ended['id']}", headers=admin, json={"ends_on": "2026-12-31"}), 409, "INVALID_LICENSE_STATUS")
    assert client.patch(f"/api/v1/digital-licenses/{pend['id']}", headers=librarian, json={"copies": 2}).status_code == 403


def test_t_dig_11_b(client, admin, librarian):
    """T-DIG-11-b (LIB-DIG-11): 409 NOT_A_SUBSCRIPTION; 409 INVALID_LICENSE_STATUS; 422"""
    r = resource(client, librarian)
    perp = license_(client, admin, r["id"])
    pend = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    sub = license_(client, admin, r["id"], model="subscription", ends_on="2026-11-30")
    body = {"ends_on": "2027-03-31", "cost": "10.00"}
    err(post(client, admin, f"digital-licenses/{perp['id']}/renew", body), 409, "NOT_A_SUBSCRIPTION")
    err(post(client, admin, f"digital-licenses/{pend['id']}/renew", body), 409, "INVALID_LICENSE_STATUS")
    assert post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2026-11-30", "cost": "10.00"}).status_code == 422


def test_t_dig_12_b(client, librarian, branch_a):
    """T-DIG-12-b (LIB-DIG-12): 422 twice; 403"""
    for n in (0, 366):
        assert client.get("/api/v1/digital-licenses", headers=librarian, params={"ending_within_days": n}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get("/api/v1/digital-licenses", headers=mh).status_code == 403


def test_t_dig_13_b(client, librarian):
    """T-DIG-13-b (LIB-DIG-13): 422 both"""
    r = resource(client, librarian)
    url = f"/api/v1/digital-resources/{r['id']}/calendar"
    assert client.get(url, headers=librarian, params={"from": "2026-11-01", "to": "2027-02-15"}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": "2026-11-04"}).status_code == 422


def test_t_dig_14_b(client, clock, admin, librarian):
    """T-DIG-14-b (LIB-DIG-14): 1, 0; 0, 2"""
    r = resource(client, librarian)
    perp = license_(client, admin, r["id"])
    license_(client, admin, r["id"], model="subscription", copies=2, starts_on="2026-11-10", ends_on="2026-12-31")
    at(clock, WED, 10)
    ok(post(client, admin, f"digital-licenses/{perp['id']}/cancel"))
    cal = lambda a, b: [d["capacity"] for d in get(client, librarian, f"digital-resources/{r['id']}/calendar", **{"from": a, "to": b})["days"]]
    assert cal("2026-11-03", "2026-11-04") == [1, 0]
    assert cal("2026-11-09", "2026-11-10") == [0, 2]


def test_t_dig_15_b(client, admin, librarian, branch_a):
    """T-DIG-15-b (LIB-DIG-15): 422 both"""
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    assert borrow(client, librarian, r["id"]).status_code == 422
    assert borrow(client, member_headers(client, m), r["id"], m["id"]).status_code == 422


def test_t_dig_16_b(client, clock, admin, librarian, branch_a):
    """T-DIG-16-b (LIB-DIG-16): 409 MEMBER_PASSIVE; 409 DIGITAL_NOT_ALLOWED_FOR_TYPE; 409 MEMBERSHIP_EXPIRED"""
    r = ebook(client, admin, copies=3)
    p, g, m = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(borrow(client, librarian, r["id"], p["id"]), 409, "MEMBER_PASSIVE")
    err(borrow(client, librarian, r["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    at(clock, "2027-11-02", 10)
    err(borrow(client, librarian, r["id"], m["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_dig_16_d(client, admin, librarian, branch_a):
    """T-DIG-16-d (LIB-DIG-16): 409 ALREADY_BORROWED"""
    r = ebook(client, admin, copies=2)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    err(borrow(client, librarian, r["id"], m["id"]), 409, "ALREADY_BORROWED")


def test_t_dig_16_f(client, admin, librarian, branch_a):
    """T-DIG-16-f (LIB-DIG-16): 409 NO_ACTIVE_LICENSE both"""
    bare, later = resource(client, librarian), resource(client, librarian)
    license_(client, admin, later["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    m = member(client, librarian, branch_a)
    err(borrow(client, librarian, bare["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")
    err(borrow(client, librarian, later["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")


def test_t_dig_16_h(client, admin, librarian, branch_a):
    """T-DIG-16-h (LIB-DIG-16): WRONG_RESOURCE_KIND; RESOURCE_INACTIVE (resource checks before member checks)"""
    d, e = database(client, admin), ebook(client, admin)
    for r in (d, e):
        ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(borrow(client, librarian, d["id"], p["id"]), 409, "WRONG_RESOURCE_KIND")
    err(borrow(client, librarian, e["id"], p["id"]), 409, "RESOURCE_INACTIVE")


def test_t_dig_18_b(client, clock, admin, librarian, branch_a):
    """T-DIG-18-b (LIB-DIG-18): 201 (a finished loan is not ALREADY_BORROWED)"""
    r = ebook(client, admin, loan_days=1)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    at(clock, TUE, 9, 0)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)


def test_t_dig_19_b(client, clock, admin, librarian, branch_a):
    """T-DIG-19-b (LIB-DIG-19): 409 LOAN_NOT_OPEN; 403"""
    a, b = ebook(client, admin, loan_days=1), ebook(client, admin)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1, l2 = ok(borrow(client, librarian, a["id"], m["id"]), 201), ok(borrow(client, librarian, b["id"], m["id"]), 201)
    assert post(client, member_headers(client, other), f"digital-loans/{l2['id']}/return").status_code == 403
    at(clock, TUE, 9)
    err(post(client, librarian, f"digital-loans/{l1['id']}/return"), 409, "LOAN_NOT_OPEN")


def test_t_dig_20_b(client, admin, librarian, branch_a):
    """T-DIG-20-b (LIB-DIG-20): 200; 403; 403; 200 with 1 item"""
    r = ebook(client, admin, copies=2)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = ok(borrow(client, librarian, r["id"], m["id"]), 201), ok(borrow(client, librarian, r["id"], other["id"]), 201)
    mh = member_headers(client, m)
    assert client.get(f"/api/v1/digital-loans/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/digital-loans/{foreign['id']}", headers=mh).status_code == 403
    assert client.get("/api/v1/digital-loans", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/digital-loans")["total"] == 1


def test_t_dig_21_b(client, admin, librarian, branch_a):
    """T-DIG-21-b (LIB-DIG-21): 409 RESOURCE_HAS_HOLDS"""
    r = ebook(client, admin, loan_days=3)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "RESOURCE_HAS_HOLDS")


def test_t_dig_21_d(client, admin, librarian, branch_a):
    """T-DIG-21-d (LIB-DIG-21): Due Thu 2026-11-12 09:00 (current loan_days)"""
    r = ebook(client, admin, loan_days=3)
    loan = ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"loan_days": 7}))
    assert same(ok(post(client, librarian, f"digital-loans/{loan['id']}/renew"))["due_at"], "2026-11-12", 9)


def test_t_dig_22_a(client, admin, librarian, branch_a):
    """T-DIG-22-a (LIB-DIG-22): 201 waiting with position 1; 201 with position 2"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h2 = ok(hold(client, member_headers(client, m2), r["id"]), 201)
    assert (h2["status"], h2["member_id"], h2["position"], h2["ready_until"]) == ("waiting", m2["id"], 1, None)
    assert ok(hold(client, librarian, r["id"], m3["id"]), 201)["position"] == 2


def test_t_dig_23_b(client, admin, librarian, branch_a):
    """T-DIG-23-b (LIB-DIG-23): 409 HOLD_NOT_NEEDED; 409 NO_ACTIVE_LICENSE"""
    free, bare = ebook(client, admin), resource(client, librarian)
    m = member(client, librarian, branch_a)
    err(hold(client, librarian, free["id"], m["id"]), 409, "HOLD_NOT_NEEDED")
    err(hold(client, librarian, bare["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")


def test_t_dig_23_d(client, admin, librarian, branch_a):
    """T-DIG-23-d (LIB-DIG-23): 409 DIGITAL_NOT_ALLOWED_FOR_TYPE; 409 WRONG_RESOURCE_KIND"""
    r, d = ebook(client, admin), database(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    g, m = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a)
    err(hold(client, librarian, r["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    err(hold(client, librarian, d["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")


def test_t_dig_24_a(client, clock, admin, librarian, branch_a):
    """T-DIG-24-a (LIB-DIG-24): Queue M3 (position 1), M2 (2); after the return: waiting M2 (position 1), ready M3"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    at(clock, MON, 10)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, MON, 9, 30)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    q = lambda **p: [(x["member_id"], x["position"]) for x in items(get(client, librarian, f"digital-resources/{r['id']}/holds", **p))]
    assert q() == [(m3["id"], 1), (m2["id"], 2)]
    at(clock, MON, 11)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    assert q() == [(m2["id"], 1)]
    assert q(status="ready") == [(m3["id"], None)]


def test_t_dig_25_b(client, admin, librarian, branch_a):
    """T-DIG-25-b (LIB-DIG-25): staff_request and one digital_hold_cancelled notification for M2; M3's hold becomes ready"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h2 = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    assert ok(post(client, librarian, f"digital-holds/{h2['id']}/cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m2["id"], "digital_hold_cancelled")) == 1
    assert holds_of(client, librarian, m3["id"])[0]["status"] == "ready"


def test_t_dig_26_b(client, admin, librarian, branch_a):
    """T-DIG-26-b (LIB-DIG-26): Both holds ready"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    license_(client, admin, r["id"], copies=2)
    assert [holds_of(client, librarian, m["id"])[0]["status"] for m in (m2, m3)] == ["ready", "ready"]


def test_t_dig_27_b(client, clock, admin, librarian, branch_a):
    """T-DIG-27-b (LIB-DIG-27): 201 with hold_id"""
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    at(clock, THU, 10)
    assert ok(borrow(client, librarian, r["id"], m2["id"]), 201)["hold_id"] == h["id"]


def test_t_dig_28_b(client, admin, librarian, branch_a):
    """T-DIG-28-b (LIB-DIG-28): 409 WRONG_RESOURCE_KIND; 409 SESSION_ALREADY_OPEN with details.session_id; 409 SESSION_LIMIT_REACHED with details.limit 1"""
    e, d1, d2 = ebook(client, admin), database(client, admin, seats=5), database(client, admin, seats=5)
    m = member(client, librarian, branch_a)
    err(session(client, librarian, e["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")
    s = ok(session(client, librarian, d1["id"], m["id"]), 201)
    assert err(session(client, librarian, d1["id"], m["id"]), 409, "SESSION_ALREADY_OPEN")["details"]["session_id"] == s["id"]
    assert err(session(client, librarian, d2["id"], m["id"]), 409, "SESSION_LIMIT_REACHED")["details"]["limit"] == 1


def test_t_dig_28_d(client, admin, librarian, branch_a):
    """T-DIG-28-d (LIB-DIG-28): DIGITAL_NOT_ALLOWED_FOR_TYPE; MEMBER_BLOCKED_BY_DEBT; third SESSION_LIMIT_REACHED with details.limit 2"""
    dbs = [database(client, admin, seats=5) for _ in range(3)]
    g, m, a = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    debt(client, librarian, branch_a, m, "50.00")
    err(session(client, librarian, dbs[0]["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    err(session(client, librarian, dbs[0]["id"], m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    ok(session(client, librarian, dbs[0]["id"], a["id"]), 201)
    ok(session(client, librarian, dbs[1]["id"], a["id"]), 201)
    assert err(session(client, librarian, dbs[2]["id"], a["id"]), 409, "SESSION_LIMIT_REACHED")["details"]["limit"] == 2


def test_t_dig_29_b(client, clock, admin, librarian, branch_a):
    """T-DIG-29-b (LIB-DIG-29): 403; 409 SESSION_NOT_OPEN"""
    d = database(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    s = ok(session(client, librarian, d["id"], m1["id"]), 201)
    assert post(client, member_headers(client, m2), f"digital-sessions/{s['id']}/close").status_code == 403
    at(clock, MON, 11)
    err(post(client, member_headers(client, m1), f"digital-sessions/{s['id']}/close"), 409, "SESSION_NOT_OPEN")


def test_t_dig_30_a(client, clock, admin, librarian, branch_a):
    """T-DIG-30-a (LIB-DIG-30): 7th 409 DAILY_SESSION_LIMIT_REACHED; Tuesday 201"""
    d = database(client, admin)
    m = member(client, librarian, branch_a)
    for i in range(6):
        at(clock, MON, 10 + i)
        s = ok(session(client, librarian, d["id"], m["id"]), 201)
        ok(post(client, librarian, f"digital-sessions/{s['id']}/close"))
    at(clock, MON, 17)
    err(session(client, librarian, d["id"], m["id"]), 409, "DAILY_SESSION_LIMIT_REACHED")
    at(clock, TUE, 10)
    ok(session(client, librarian, d["id"], m["id"]), 201)


def test_t_dig_32_a(client, clock, admin, librarian, branch_a):
    """T-DIG-32-a (LIB-DIG-32): S2, S1; then only S2"""
    d = database(client, admin)
    m = member(client, librarian, branch_a)
    at(clock, MON, 10)
    s1 = ok(session(client, librarian, d["id"], m["id"]), 201)
    ok(post(client, librarian, f"digital-sessions/{s1['id']}/close"))
    at(clock, MON, 12)
    s2 = ok(session(client, librarian, d["id"], m["id"]), 201)
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, f"members/{m['id']}/digital-sessions", **p))]
    assert ids() == [s2["id"], s1["id"]]
    assert ids(open="true") == [s2["id"]]


def test_t_dig_33_b(client, admin, librarian, branch_a):
    """T-DIG-33-b (LIB-DIG-33): The member has no notifications"""
    a, b, d = ebook(client, admin), ebook(client, admin, loan_days=3), database(client, admin)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    la, lb = ok(borrow(client, mh, a["id"]), 201), ok(borrow(client, mh, b["id"]), 201)
    ok(post(client, mh, f"digital-loans/{lb['id']}/renew"))
    ok(post(client, mh, f"digital-loans/{la['id']}/return"))
    ok(session(client, mh, d["id"]), 201)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0


def test_t_dig_34_a(client, clock, admin, librarian, branch_a):
    """T-DIG-34-a (LIB-DIG-34): due_soon_notices 1, 0; Tue 1 (and expired_loans 1); 2 digital_loan_due_soon notifications"""
    a, b = ebook(client, admin, loan_days=1), ebook(client, admin, loan_days=2)
    m = member(client, librarian, branch_a)
    la, lb = ok(borrow(client, librarian, a["id"], m["id"]), 201), ok(borrow(client, librarian, b["id"], m["id"]), 201)
    assert process(client, librarian)["due_soon_notices"] == 1
    assert process(client, librarian)["due_soon_notices"] == 0
    at(clock, TUE, 9)
    out = process(client, librarian)
    assert (out["due_soon_notices"], out["expired_loans"]) == (1, 1)
    assert sorted(x["digital_loan_id"] for x in notes(client, librarian, m["id"], "digital_loan_due_soon")) == sorted([la["id"], lb["id"]])


def test_t_dig_35_b(client, clock, admin, librarian, branch_a):
    """T-DIG-35-b (LIB-DIG-35): Second call all counts 0; member 403"""
    r = ebook(client, admin, loan_days=1)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    at(clock, WED, 9)
    assert process(client, librarian)["expired_loans"] == 1
    assert process(client, librarian) == {"expired_loans": 0, "expired_holds": 0, "holds_ready": 0, "due_soon_notices": 0}
    assert post(client, member_headers(client, m), "digital/process").status_code == 403


def test_t_dig_36_a(client, admin, librarian, branch_a):
    """T-DIG-36-a (LIB-DIG-36): digital = {open_loans: 1, waiting_holds: 1, ready_holds: 1}; borrowing.eligible true"""
    a, b, c = ebook(client, admin), ebook(client, admin), ebook(client, admin)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(borrow(client, librarian, a["id"], m["id"]), 201)
    ok(borrow(client, librarian, b["id"], o["id"]), 201)
    ok(hold(client, librarian, b["id"], m["id"]), 201)
    lc = ok(borrow(client, librarian, c["id"], o["id"]), 201)
    ok(hold(client, librarian, c["id"], m["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{lc['id']}/return"))
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["digital"] == {"open_loans": 1, "waiting_holds": 1, "ready_holds": 1}
    assert s["borrowing"]["eligible"] is True


def test_t_dig_37_b(client, admin, librarian, branch_a):
    """T-DIG-37-b (LIB-DIG-37): M2's hold ready"""
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    deactivate_member(client, librarian, m1["id"])
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "ready"


def test_t_dig_38_b(client, admin, librarian):
    """T-DIG-38-b (LIB-DIG-38): One entry each for digital_license_cancelled and digital_processed"""
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"])
    ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    process(client, librarian)
    for event in ("digital_license_cancelled", "digital_processed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event


def test_t_dig_39_b(client, librarian, branch_a):
    """T-DIG-39-b (LIB-DIG-39): 422; 422; 403; 200"""
    url = "/api/v1/reports/digital-usage"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": WED}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200


def test_t_dig_40_a(client, admin, librarian, branch_a):
    """T-DIG-40-a (LIB-DIG-40): The export has exactly the keys of 22.1 (no digital data)"""
    r = ebook(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
