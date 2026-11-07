"""Feedback tests: module 17 (Digital resources). Generated from cases/digital.md."""
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


def test_t_dig_01_a(client, librarian):
    """T-DIG-01-a (LIB-DIG-01): 201; loan_days 14, active, book_id set"""
    book = create_book(client, librarian)
    r = resource(client, librarian, title="Dijital Kitap", book_id=book["id"])
    assert (r["kind"], r["title"], r["book_id"], r["loan_days"], r["is_active"]) == ("ebook", "Dijital Kitap", book["id"], 14, True)


def test_t_dig_02_a(client, librarian):
    """T-DIG-02-a (LIB-DIG-02): 200 with the new values; 422"""
    r = resource(client, librarian)
    url = f"/api/v1/digital-resources/{r['id']}"
    out = ok(client.patch(url, headers=librarian, json={"title": "Yeni Ad", "loan_days": 7}))
    assert (out["title"], out["loan_days"]) == ("Yeni Ad", 7)
    assert client.patch(url, headers=librarian, json={"kind": "database"}).status_code == 422


def test_t_dig_03_a(client, admin, librarian, branch_a):
    """T-DIG-03-a (LIB-DIG-03): M2's hold cancelled with resource_inactive and one digital_hold_cancelled notification; M1's loan still open; 409 RESOURCE_INACTIVE twice"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    h = holds_of(client, librarian, m2["id"])[0]
    assert (h["status"], h["cancel_reason"]) == ("cancelled", "resource_inactive")
    assert len(notes(client, librarian, m2["id"], "digital_hold_cancelled")) == 1
    assert get(client, librarian, f"digital-loans/{loan['id']}")["status"] == "open"
    err(borrow(client, librarian, r["id"], m3["id"]), 409, "RESOURCE_INACTIVE")
    err(hold(client, librarian, r["id"], m3["id"]), 409, "RESOURCE_INACTIVE")


def test_t_dig_04_a(client, admin, librarian, branch_a):
    """T-DIG-04-a (LIB-DIG-04): Order Alfa, Beta, Delta; q=springer → Delta; kind=database → Delta; is_active=false → Beta"""
    beta = resource(client, librarian, title="Beta")
    resource(client, librarian, title="Alfa")
    resource(client, librarian, kind="database", title="Delta", provider="Springer Nature")
    ok(client.patch(f"/api/v1/digital-resources/{beta['id']}", headers=librarian, json={"is_active": False}))
    mh = member_headers(client, member(client, librarian, branch_a))
    titles = lambda **p: [x["title"] for x in items(get(client, mh, "digital-resources", **p))]
    assert titles() == ["Alfa", "Beta", "Delta"]
    assert titles(q="springer") == ["Delta"]
    assert titles(kind="database") == ["Delta"]
    assert titles(is_active="false") == ["Beta"]


def test_t_dig_05_a(client, admin, librarian):
    """T-DIG-05-a (LIB-DIG-05): 201 active with the values; 201 pending"""
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30", cost="1200.00")
    assert (lic["resource_id"], lic["model"], lic["copies"], lic["starts_on"], lic["ends_on"], lic["cost"], lic["status"]) == (r["id"], "subscription", 3, "2026-11-01", "2026-11-30", "1200.00", "active")
    assert license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")["status"] == "pending"


def test_t_dig_05_c(client, admin, librarian):
    """T-DIG-05-c (LIB-DIG-05): 201"""
    r = resource(client, librarian)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    assert license_(client, admin, r["id"])["status"] == "active"


def test_t_dig_06_a(client, admin, librarian, branch_a):
    """T-DIG-06-a (LIB-DIG-06): 201 with order_id; 409 INVALID_ORDER_STATUS; 422; cancel 409 ORDER_HAS_LICENSE"""
    r = resource(client, librarian)
    o, draft = order(client, librarian, branch_a), order(client, librarian, branch_a, submit=False)
    assert license_(client, admin, r["id"], order_id=o["id"])["order_id"] == o["id"]
    assert error_code(license_(client, admin, r["id"], order_id=draft["id"], expect=409)) == "INVALID_ORDER_STATUS"
    license_(client, admin, r["id"], order_id=999999, expect=422)
    err(post(client, librarian, f"purchase-orders/{o['id']}/cancel"), 409, "ORDER_HAS_LICENSE")


def test_t_dig_07_a(client, admin, librarian, branch_a):
    """T-DIG-07-a (LIB-DIG-07): 200, cancelled_on 2026-11-02, cancelled; 409 INVALID_LICENSE_STATUS; M2 409 NO_ACTIVE_LICENSE; M1's loan stays open"""
    r = resource(client, librarian, loan_days=14)
    lic = license_(client, admin, r["id"], copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    out = ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    assert (out["cancelled_on"], out["status"]) == (MON, "cancelled")
    err(post(client, admin, f"digital-licenses/{lic['id']}/cancel"), 409, "INVALID_LICENSE_STATUS")
    err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_ACTIVE_LICENSE")
    assert get(client, librarian, f"digital-loans/{loan['id']}")["status"] == "open"


def test_t_dig_09_a(client, admin, librarian, branch_a):
    """T-DIG-09-a (LIB-DIG-09): Only the active e-book with available 0; 404 NOT_FOUND"""
    book = create_book(client, librarian)
    active = ebook(client, admin, book_id=book["id"])
    gone = ebook(client, admin, book_id=book["id"])
    ok(client.patch(f"/api/v1/digital-resources/{gone['id']}", headers=librarian, json={"is_active": False}))
    ok(borrow(client, librarian, active["id"], member(client, librarian, branch_a)["id"]), 201)
    out = get(client, librarian, f"books/{book['id']}/digital-resources")
    rows = out if isinstance(out, list) else out["items"]
    assert [(x["id"], x["available"]) for x in rows] == [(active["id"], 0)]
    assert client.get("/api/v1/books/999999/digital-resources", headers=librarian).status_code == 404


def test_t_dig_10_a(client, admin, librarian):
    """T-DIG-10-a (LIB-DIG-10): 200; 409 INVALID_LICENSE_STATUS, then 200; 422; 422"""
    r = resource(client, librarian)
    pend = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    sub = license_(client, admin, r["id"], model="subscription", ends_on="2026-11-30")
    perp = license_(client, admin, r["id"])
    url = lambda lic: f"/api/v1/digital-licenses/{lic['id']}"
    out = ok(client.patch(url(pend), headers=admin, json={"copies": 5, "cost": "50.00"}))
    assert (out["copies"], out["cost"]) == (5, "50.00")
    err(client.patch(url(sub), headers=admin, json={"copies": 4}), 409, "INVALID_LICENSE_STATUS")
    assert ok(client.patch(url(sub), headers=admin, json={"ends_on": "2026-12-15"}))["ends_on"] == "2026-12-15"
    assert client.patch(url(perp), headers=admin, json={"ends_on": "2026-12-31"}).status_code == 422
    assert client.patch(url(sub), headers=admin, json={"ends_on": "2026-11-01"}).status_code == 422


def test_t_dig_11_a(client, admin, librarian):
    """T-DIG-11-a (LIB-DIG-11): 201: new subscription 2026-12-01 – 2026-12-31, 3 copies, 900.00, pending; then 409 ALREADY_RENEWED"""
    r = resource(client, librarian)
    sub = license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    new = ok(post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2026-12-31", "cost": "900.00"}), 201)
    assert (new["resource_id"], new["model"], new["copies"], new["starts_on"], new["ends_on"], new["cost"], new["status"]) == (r["id"], "subscription", 3, "2026-12-01", "2026-12-31", "900.00", "pending")
    err(post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2027-01-31", "cost": "900.00"}), 409, "ALREADY_RENEWED")


def test_t_dig_12_a(client, admin, librarian):
    """T-DIG-12-a (LIB-DIG-12): D, A (with resource_title); then only D"""
    ids = {}
    for name, ends in (("A", "2026-11-20"), ("B", "2026-12-31"), ("C", "2026-11-10"), ("D", "2026-11-05")):
        r = resource(client, librarian, title=f"Abonelik {name}")
        ids[name] = license_(client, admin, r["id"], model="subscription", ends_on=ends)["id"]
    ok(post(client, admin, f"digital-licenses/{ids['C']}/renew", {"ends_on": "2026-12-31", "cost": "10.00"}), 201)
    rows = items(get(client, librarian, "digital-licenses"))
    assert [(x["id"], x["resource_title"]) for x in rows] == [(ids["D"], "Abonelik D"), (ids["A"], "Abonelik A")]
    assert [x["id"] for x in items(get(client, librarian, "digital-licenses", ending_within_days=3))] == [ids["D"]]


def test_t_dig_13_a(client, admin, librarian):
    """T-DIG-13-a (LIB-DIG-13): Capacities 5, 5, 5, 2, 2"""
    r = resource(client, librarian)
    license_(client, admin, r["id"], copies=2)
    license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    out = get(client, librarian, f"digital-resources/{r['id']}/calendar", **{"from": "2026-11-28", "to": "2026-12-02"})
    assert out["resource_id"] == r["id"]
    assert [(d["date"], d["capacity"]) for d in out["days"]] == [("2026-11-28", 5), ("2026-11-29", 5), ("2026-11-30", 5), ("2026-12-01", 2), ("2026-12-02", 2)]


def test_t_dig_14_a(client, clock, admin, librarian):
    """T-DIG-14-a (LIB-DIG-14): capacity 5, then 2"""
    r = resource(client, librarian)
    license_(client, admin, r["id"], copies=2)
    license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    at(clock, "2026-11-30", 23, 59, 59)
    assert get(client, librarian, f"digital-resources/{r['id']}")["capacity"] == 5
    at(clock, "2026-12-01", 0, 0)
    assert get(client, librarian, f"digital-resources/{r['id']}")["capacity"] == 2


def test_t_dig_15_a(client, admin, librarian, branch_a):
    """T-DIG-15-a (LIB-DIG-15): 201: own member_id, open, hold_id null, renewed false, ended_at null"""
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    loan = ok(borrow(client, member_headers(client, m), r["id"]), 201)
    assert (loan["resource_id"], loan["member_id"], loan["status"], loan["hold_id"], loan["renewed"], loan["ended_at"]) == (r["id"], m["id"], "open", None, False, None)
    assert same(loan["borrowed_at"], MON, 9)


def test_t_dig_15_c(client, admin, librarian, branch_a):
    """T-DIG-15-c (LIB-DIG-15): Loan with hold_id of M2's hold; the hold fulfilled with closed_at"""
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{l1['id']}/return"))
    loan = ok(borrow(client, member_headers(client, m2), r["id"]), 201)
    assert loan["hold_id"] == h["id"]
    out = holds_of(client, librarian, m2["id"])[0]
    assert out["status"] == "fulfilled" and out["closed_at"] is not None


def test_t_dig_16_a(client, admin, librarian, branch_a):
    """T-DIG-16-a (LIB-DIG-16): 409 WRONG_RESOURCE_KIND; 409 RESOURCE_INACTIVE"""
    d, e = database(client, admin), ebook(client, admin)
    ok(client.patch(f"/api/v1/digital-resources/{e['id']}", headers=librarian, json={"is_active": False}))
    m = member(client, librarian, branch_a)
    err(borrow(client, librarian, d["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")
    err(borrow(client, librarian, e["id"], m["id"]), 409, "RESOURCE_INACTIVE")


def test_t_dig_16_c(client, admin, librarian, branch_a):
    """T-DIG-16-c (LIB-DIG-16): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'; 201"""
    r = ebook(client, admin, copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(borrow(client, librarian, r["id"], m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(borrow(client, librarian, r["id"], m2["id"]), 201)


def test_t_dig_16_e(client, admin, librarian, branch_a):
    """T-DIG-16-e (LIB-DIG-16): 409 DIGITAL_LOAN_LIMIT_REACHED with details.limit 5"""
    books = [ebook(client, admin) for _ in range(6)]
    m = member(client, librarian, branch_a)
    for r in books[:5]:
        ok(borrow(client, librarian, r["id"], m["id"]), 201)
    assert err(borrow(client, librarian, books[5]["id"], m["id"]), 409, "DIGITAL_LOAN_LIMIT_REACHED")["details"]["limit"] == 5


def test_t_dig_16_g(client, admin, librarian, branch_a):
    """T-DIG-16-g (LIB-DIG-16): 409 NO_COPY_AVAILABLE with details.waiting 0, then 1"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    assert err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 0
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    assert err(borrow(client, librarian, r["id"], m3["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 1


def test_t_dig_17_a(client, clock, admin, librarian, branch_a):
    """T-DIG-17-a (LIB-DIG-17): Due Mon 2026-11-16 09:00; due Thu 2026-11-05 09:00:30"""
    a, b = ebook(client, admin, loan_days=14), ebook(client, admin, loan_days=3)
    m = member(client, librarian, branch_a)
    assert same(ok(borrow(client, librarian, a["id"], m["id"]), 201)["due_at"], "2026-11-16", 9)
    at(clock, MON, 9, 0, 30)
    assert same(ok(borrow(client, librarian, b["id"], m["id"]), 201)["due_at"], THU, 9, 0, 30)


def test_t_dig_18_a(client, clock, admin, librarian, branch_a):
    """T-DIG-18-a (LIB-DIG-18): 409 NO_COPY_AVAILABLE; then 201; M1's loan shown expired with ended_at Tue 09:00"""
    r = ebook(client, admin, loan_days=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    at(clock, TUE, 8, 59, 59)
    err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_COPY_AVAILABLE")
    at(clock, TUE, 9, 0)
    ok(borrow(client, librarian, r["id"], m2["id"]), 201)
    out = get(client, librarian, f"digital-loans/{l1['id']}")
    assert out["status"] == "expired" and same(out["ended_at"], TUE, 9)


def test_t_dig_19_a(client, clock, admin, librarian, branch_a):
    """T-DIG-19-a (LIB-DIG-19): 200 returned, ended_at 12:00; then 409 LOAN_NOT_OPEN"""
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    loan = ok(borrow(client, mh, r["id"]), 201)
    at(clock, MON, 12)
    out = ok(post(client, mh, f"digital-loans/{loan['id']}/return"))
    assert out["status"] == "returned" and same(out["ended_at"], MON, 12)
    err(post(client, mh, f"digital-loans/{loan['id']}/return"), 409, "LOAN_NOT_OPEN")


def test_t_dig_20_a(client, clock, admin, librarian, branch_a):
    """T-DIG-20-a (LIB-DIG-20): Order L1, L2, L3; status=expired → L1; returned → L3; open → L2; resource_id R2 → L2, L3; member_id M1 → L1, L3"""
    r1, r2 = ebook(client, admin, loan_days=1, copies=2), ebook(client, admin, copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    l2 = ok(borrow(client, librarian, r2["id"], m2["id"]), 201)
    at(clock, MON, 9)
    l1 = ok(borrow(client, librarian, r1["id"], m1["id"]), 201)
    at(clock, MON, 11)
    l3 = ok(borrow(client, librarian, r2["id"], m1["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{l3['id']}/return"))
    at(clock, TUE, 10)
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "digital-loans", **p))]
    assert ids() == [l1["id"], l2["id"], l3["id"]]
    assert ids(status="expired") == [l1["id"]]
    assert ids(status="returned") == [l3["id"]]
    assert ids(status="open") == [l2["id"]]
    assert ids(resource_id=r2["id"]) == [l2["id"], l3["id"]]
    assert ids(member_id=m1["id"]) == [l1["id"], l3["id"]]


def test_t_dig_21_a(client, clock, admin, librarian, branch_a):
    """T-DIG-21-a (LIB-DIG-21): 409 RENEWAL_TOO_EARLY with renewable_from 2026-11-13 09:00; 200 due 2026-11-30 09:00, renewed true, renewed_at set; 409 RENEWAL_LIMIT_REACHED"""
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    loan = ok(borrow(client, mh, r["id"]), 201)
    at(clock, "2026-11-13", 8, 59, 59)
    e = err(post(client, mh, f"digital-loans/{loan['id']}/renew"), 409, "RENEWAL_TOO_EARLY")
    assert same(e["details"]["renewable_from"], "2026-11-13", 9)
    at(clock, "2026-11-13", 9)
    out = ok(post(client, mh, f"digital-loans/{loan['id']}/renew"))
    assert same(out["due_at"], "2026-11-30", 9) and out["renewed"] is True and same(out["renewed_at"], "2026-11-13", 9)
    err(post(client, mh, f"digital-loans/{loan['id']}/renew"), 409, "RENEWAL_LIMIT_REACHED")


def test_t_dig_21_c(client, clock, admin, librarian, branch_a):
    """T-DIG-21-c (LIB-DIG-21): 409 NO_ACTIVE_LICENSE; 409 LOAN_NOT_OPEN"""
    r = resource(client, librarian, loan_days=3)
    lic = license_(client, admin, r["id"])
    loan = ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "NO_ACTIVE_LICENSE")
    at(clock, THU, 9)
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "LOAN_NOT_OPEN")


def test_t_dig_23_a(client, admin, librarian, branch_a):
    """T-DIG-23-a (LIB-DIG-23): 409 DUPLICATE_HOLD; 409 ALREADY_BORROWED"""
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    err(hold(client, librarian, r["id"], m2["id"]), 409, "DUPLICATE_HOLD")
    err(hold(client, librarian, r["id"], m1["id"]), 409, "ALREADY_BORROWED")


def test_t_dig_23_c(client, admin, librarian, branch_a):
    """T-DIG-23-c (LIB-DIG-23): 409 DIGITAL_HOLD_LIMIT_REACHED with details.limit 5"""
    books = [ebook(client, admin) for _ in range(6)]
    a, s = member(client, librarian, branch_a, membership_type="academic"), member(client, librarian, branch_a)
    for r in books:
        ok(borrow(client, librarian, r["id"], a["id"]), 201)
    for r in books[:5]:
        ok(hold(client, librarian, r["id"], s["id"]), 201)
    assert err(hold(client, librarian, books[5]["id"], s["id"]), 409, "DIGITAL_HOLD_LIMIT_REACHED")["details"]["limit"] == 5


def test_t_dig_25_a(client, admin, librarian, branch_a):
    """T-DIG-25-a (LIB-DIG-25): cancelled, member_request, closed_at set, no notification; then 409 HOLD_NOT_ACTIVE"""
    r = ebook(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    h = ok(hold(client, mh, r["id"]), 201)
    out = ok(post(client, mh, f"digital-holds/{h['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_request") and out["closed_at"] is not None
    assert notes(client, librarian, m["id"], "digital_hold_cancelled") == []
    err(post(client, mh, f"digital-holds/{h['id']}/cancel"), 409, "HOLD_NOT_ACTIVE")


def test_t_dig_25_c(client, clock, admin, librarian, branch_a):
    """T-DIG-25-c (LIB-DIG-25): 409 HOLD_NOT_ACTIVE; 403"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, MON, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    assert post(client, member_headers(client, m3), f"digital-holds/{h['id']}/cancel").status_code == 403
    at(clock, WED, 10, 0, 1)
    err(post(client, librarian, f"digital-holds/{h['id']}/cancel"), 409, "HOLD_NOT_ACTIVE")


def test_t_dig_26_a(client, clock, admin, librarian, branch_a):
    """T-DIG-26-a (LIB-DIG-26): M2 ready, ready_until Thu 10:00, one digital_hold_ready notification containing the title; M3 waiting with position 1"""
    r = ebook(client, admin, title="Kayıp Şehir")
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    h2, h3 = holds_of(client, librarian, m2["id"])[0], holds_of(client, librarian, m3["id"])[0]
    assert h2["status"] == "ready" and same(h2["ready_at"], TUE, 10) and same(h2["ready_until"], THU, 10)
    assert (h3["status"], h3["position"]) == ("waiting", 1)
    n = notes(client, librarian, m2["id"], "digital_hold_ready")
    assert len(n) == 1 and "Kayıp Şehir" in n[0]["message"] and n[0]["digital_hold_id"] == h2["id"]


def test_t_dig_26_c(client, clock, admin, librarian, branch_a):
    """T-DIG-26-c (LIB-DIG-26): M2 still waiting; 409 NO_COPY_AVAILABLE with waiting 1; process gives holds_ready 1 and M2 ready"""
    r = ebook(client, admin, loan_days=1)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, TUE, 9)
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "waiting"
    assert err(borrow(client, librarian, r["id"], m3["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 1
    assert process(client, librarian)["holds_ready"] == 1
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "ready"


def test_t_dig_27_a(client, clock, admin, librarian, branch_a):
    """T-DIG-27-a (LIB-DIG-27): 409 NO_COPY_AVAILABLE twice; then 201 (lapsed hold keeps no copy)"""
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    for day, hh, ss in ((TUE, 11, 0), (THU, 10, 0)):
        at(clock, day, hh, 0, ss)
        err(borrow(client, librarian, r["id"], m3["id"]), 409, "NO_COPY_AVAILABLE")
    at(clock, THU, 10, 0, 1)
    ok(borrow(client, librarian, r["id"], m3["id"]), 201)


def test_t_dig_28_a(client, clock, admin, librarian, branch_a):
    """T-DIG-28-a (LIB-DIG-28): 201: expires_at 11:00, open true, closed_at null"""
    d = database(client, admin)
    m = member(client, librarian, branch_a)
    at(clock, MON, 10)
    s = ok(session(client, member_headers(client, m), d["id"]), 201)
    assert (s["resource_id"], s["member_id"], s["open"], s["closed_at"]) == (d["id"], m["id"], True, None)
    assert same(s["started_at"], MON, 10) and same(s["expires_at"], MON, 11)


def test_t_dig_28_c(client, clock, admin, librarian, branch_a):
    """T-DIG-28-c (LIB-DIG-28): 409 NO_SEAT_AVAILABLE with next_free_at 11:00; 409 NO_ACTIVE_LICENSE"""
    d, bare = database(client, admin), resource(client, librarian, kind="database")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    ok(session(client, librarian, d["id"], m1["id"]), 201)
    at(clock, MON, 10, 20)
    e = err(session(client, librarian, d["id"], m2["id"]), 409, "NO_SEAT_AVAILABLE")
    assert same(e["details"]["next_free_at"], MON, 11)
    err(session(client, librarian, bare["id"], m2["id"]), 409, "NO_ACTIVE_LICENSE")


def test_t_dig_29_a(client, clock, admin, librarian, branch_a):
    """T-DIG-29-a (LIB-DIG-29): 200 with closed_at 10:15, open false; 409 SESSION_NOT_OPEN; M2 201"""
    d = database(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    mh = member_headers(client, m1)
    at(clock, MON, 10)
    s = ok(session(client, mh, d["id"]), 201)
    at(clock, MON, 10, 15)
    out = ok(post(client, mh, f"digital-sessions/{s['id']}/close"))
    assert same(out["closed_at"], MON, 10, 15) and out["open"] is False
    err(post(client, mh, f"digital-sessions/{s['id']}/close"), 409, "SESSION_NOT_OPEN")
    ok(session(client, librarian, d["id"], m2["id"]), 201)


def test_t_dig_31_a(client, clock, admin, librarian, branch_a):
    """T-DIG-31-a (LIB-DIG-31): 409 NO_SEAT_AVAILABLE; 201; M1's session open false, closed_at null"""
    d = database(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    ok(session(client, librarian, d["id"], m1["id"]), 201)
    at(clock, MON, 10, 59, 59)
    err(session(client, librarian, d["id"], m2["id"]), 409, "NO_SEAT_AVAILABLE")
    at(clock, MON, 11)
    ok(session(client, librarian, d["id"], m2["id"]), 201)
    s = items(get(client, librarian, f"members/{m1['id']}/digital-sessions"))[0]
    assert (s["open"], s["closed_at"]) == (False, None)


def test_t_dig_33_a(client, admin, librarian, branch_a):
    """T-DIG-33-a (LIB-DIG-33): One digital_hold_ready notification for M2 with digital_hold_id"""
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    n = notes(client, librarian, m2["id"], "digital_hold_ready")
    assert [x["digital_hold_id"] for x in n] == [h["id"]]


def test_t_dig_35_a(client, clock, admin, librarian, branch_a):
    """T-DIG-35-a (LIB-DIG-35): {expired_loans: 1, expired_holds: 1, holds_ready: 1, due_soon_notices: 0}; M1's loan stored expired; M4's hold expired; M2 ready; notifications digital_loan_expired (M1) and digital_hold_expired (M4)"""
    r1, r2 = ebook(client, admin, loan_days=1), ebook(client, admin)
    m1, m2, m3, m4 = (member(client, librarian, branch_a) for _ in range(4))
    l1 = ok(borrow(client, librarian, r1["id"], m1["id"]), 201)
    ok(hold(client, librarian, r1["id"], m2["id"]), 201)
    l3 = ok(borrow(client, librarian, r2["id"], m3["id"]), 201)
    ok(hold(client, librarian, r2["id"], m4["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{l3['id']}/return"))
    at(clock, WED, 9, 0, 1)
    assert process(client, librarian) == {"expired_loans": 1, "expired_holds": 1, "holds_ready": 1, "due_soon_notices": 0}
    assert get(client, librarian, f"digital-loans/{l1['id']}")["status"] == "expired"
    assert holds_of(client, librarian, m4["id"])[0]["status"] == "expired"
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "ready"
    assert len(notes(client, librarian, m1["id"], "digital_loan_expired")) == 1
    assert len(notes(client, librarian, m4["id"], "digital_hold_expired")) == 1


def test_t_dig_37_a(client, admin, librarian, branch_a):
    """T-DIG-37-a (LIB-DIG-37): 200; loan returned; hold cancelled with member_deactivated and one digital_hold_cancelled notification; session closed"""
    a, b, d = ebook(client, admin), ebook(client, admin), database(client, admin)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, a["id"], m["id"]), 201)
    ok(borrow(client, librarian, b["id"], o["id"]), 201)
    ok(hold(client, librarian, b["id"], m["id"]), 201)
    ok(session(client, librarian, d["id"], m["id"]), 201)
    deactivate_member(client, librarian, m["id"])
    assert get(client, librarian, f"digital-loans/{loan['id']}")["status"] == "returned"
    h = holds_of(client, librarian, m["id"])[0]
    assert (h["status"], h["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert len(notes(client, librarian, m["id"], "digital_hold_cancelled")) == 1
    s = items(get(client, librarian, f"members/{m['id']}/digital-sessions"))[0]
    assert s["open"] is False and s["closed_at"] is not None


def test_t_dig_38_a(client, admin, librarian, branch_a):
    """T-DIG-38-a (LIB-DIG-38): One entry each for digital_resource_created (2), digital_license_added (2), digital_loan_created, digital_loan_returned, digital_hold_created, digital_session_opened"""
    r, d = ebook(client, admin), database(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    ok(session(client, librarian, d["id"], m1["id"]), 201)
    expected = {"digital_resource_created": 2, "digital_license_added": 2, "digital_loan_created": 1, "digital_loan_returned": 1,
                "digital_hold_created": 1, "digital_session_opened": 1}
    for event, count in expected.items():
        assert len(items(get(client, admin, "audit-log", event=event))) == count, event


def test_t_dig_39_a(client, clock, admin, librarian, branch_a):
    """T-DIG-39-a (LIB-DIG-39): Alfa {loans 2, renewals 1, holds_placed 1, holds_expired 0, sessions 0, license_cost '300.00'}; Beta sessions 2, cost '50.00'; Gamma all 0 and '0.00'; kind=database → Beta"""
    alfa = resource(client, librarian, title="Alfa", loan_days=3)
    license_(client, admin, alfa["id"], cost="300.00")
    beta = resource(client, librarian, kind="database", title="Beta")
    license_(client, admin, beta["id"], cost="50.00")
    gamma = resource(client, librarian, title="Gamma")
    ok(client.patch(f"/api/v1/digital-resources/{gamma['id']}", headers=librarian, json={"is_active": False}))
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    l1 = ok(borrow(client, librarian, alfa["id"], m1["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{l1['id']}/renew"))
    ok(hold(client, librarian, alfa["id"], m2["id"]), 201)
    for hh in (10, 12):
        at(clock, MON, hh)
        s = ok(session(client, librarian, beta["id"], m3["id"]), 201)
        ok(post(client, librarian, f"digital-sessions/{s['id']}/close"))
    at(clock, TUE, 10)
    ok(post(client, librarian, f"digital-loans/{l1['id']}/return"))
    ok(borrow(client, librarian, alfa["id"], m2["id"]), 201)
    p = {"from": "2026-11-01", "to": "2026-11-20"}
    keys = ("title", "kind", "loans", "renewals", "holds_placed", "holds_expired", "sessions", "license_cost")
    rows = items(get(client, librarian, "reports/digital-usage", **p))
    assert [tuple(r[k] for k in keys) for r in rows] == [("Alfa", "ebook", 2, 1, 1, 0, 0, "300.00"), ("Beta", "database", 0, 0, 0, 0, 2, "50.00"), ("Gamma", "ebook", 0, 0, 0, 0, 0, "0.00")]
    assert [r["title"] for r in items(get(client, librarian, "reports/digital-usage", kind="database", **p))] == ["Beta"]
