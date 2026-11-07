MODULE = "digital"
TITLE = "module 17 (Digital resources)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- resources and licenses
    dict(id="T-DIG-01-a", req="LIB-DIG-01", type="Normal", input="Librarian creates an e-book of a book without `loan_days`", expected="201; `loan_days` 14, active, `book_id` set", code='''
def TEST(client, librarian):
    book = create_book(client, librarian)
    r = resource(client, librarian, title="Dijital Kitap", book_id=book["id"])
    assert (r["kind"], r["title"], r["book_id"], r["loan_days"], r["is_active"]) == ("ebook", "Dijital Kitap", book["id"], 14, True)
'''),
    dict(id="T-DIG-01-b", req="LIB-DIG-01", type="Error", input="Database with `loan_days`; database with `book_id`; e-book `loan_days` 22 and 0; unknown `book_id`; kind `audio`; empty title; member creates", expected="`422` seven times; `403`", code='''
def TEST(client, librarian, branch_a):
    book = create_book(client, librarian)
    for fields in (dict(kind="database", loan_days=7), dict(kind="database", book_id=book["id"]), dict(loan_days=22),
                   dict(loan_days=0), dict(book_id=999999), dict(kind="audio"), dict(title="")):
        resource(client, librarian, expect=422, **fields)
    resource(client, member_headers(client, member(client, librarian, branch_a)), expect=403)
'''),
    dict(id="T-DIG-02-a", req="LIB-DIG-02", type="Normal", input="PATCH `title` and `loan_days` 7; PATCH `kind`", expected="200 with the new values; `422`", code='''
def TEST(client, librarian):
    r = resource(client, librarian)
    url = f"/api/v1/digital-resources/{r['id']}"
    out = ok(client.patch(url, headers=librarian, json={"title": "Yeni Ad", "loan_days": 7}))
    assert (out["title"], out["loan_days"]) == ("Yeni Ad", 7)
    assert client.patch(url, headers=librarian, json={"kind": "database"}).status_code == 422
'''),
    dict(id="T-DIG-02-b", req="LIB-DIG-02", type="Normal", input="E-book (14 days, 2 copies): M1 borrows Mon 09:00; `loan_days` changed to 7; M2 borrows", expected="M1 due 2026-11-16 09:00 (unchanged); M2 due 2026-11-09 09:00", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"loan_days": 7}))
    l2 = ok(borrow(client, librarian, r["id"], m2["id"]), 201)
    assert same(get(client, librarian, f"digital-loans/{l1['id']}")["due_at"], "2026-11-16", 9) and same(l2["due_at"], "2026-11-09", 9)
'''),
    dict(id="T-DIG-03-a", req="LIB-DIG-03", type="Normal", input="E-book with 1 copy: M1 borrowed, M2 waiting; resource deactivated; M3 borrows and holds", expected="M2's hold `cancelled` with `resource_inactive` and one `digital_hold_cancelled` notification; M1's loan still `open`; `409 RESOURCE_INACTIVE` twice", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-03-b", req="LIB-DIG-03", type="Normal", input="Database with an open session; resource deactivated; another member opens a session", expected="The session has `closed_at` and `open` false; `409 RESOURCE_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r = database(client, admin, seats=3)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(session(client, librarian, r["id"], m1["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    s = items(get(client, librarian, f"members/{m1['id']}/digital-sessions"))[0]
    assert s["closed_at"] is not None and s["open"] is False
    err(session(client, librarian, r["id"], m2["id"]), 409, "RESOURCE_INACTIVE")
'''),
    dict(id="T-DIG-04-a", req="LIB-DIG-04", type="Normal", input="Resources Beta, Alfa (e-books) and Delta (database, provider Springer Nature); Beta deactivated; list and filters", expected="Order Alfa, Beta, Delta; `q=springer` → Delta; `kind=database` → Delta; `is_active=false` → Beta", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-04-b", req="LIB-DIG-04", type="Normal", input="E-book with 2 copies: M1 and M2 borrow, M3 waits; database with 3 seats and one open session", expected="E-book capacity 2, in_use 2, available 0, waiting_holds 1; database 3, 1, 2, 0", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-05-a", req="LIB-DIG-05", type="Normal", input="Admin adds a subscription 2026-11-01 – 2026-11-30 (3 copies, 1200.00) and one from 2026-11-10", expected="201 `active` with the values; 201 `pending`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30", cost="1200.00")
    assert (lic["resource_id"], lic["model"], lic["copies"], lic["starts_on"], lic["ends_on"], lic["cost"], lic["status"]) == (r["id"], "subscription", 3, "2026-11-01", "2026-11-30", "1200.00", "active")
    assert license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")["status"] == "pending"
'''),
    dict(id="T-DIG-05-b", req="LIB-DIG-05", type="Error", input="Perpetual with `ends_on`; subscription without `ends_on`; `ends_on` before `starts_on`; copies 0; e-book 101 copies; database 501 seats; cost -1.00; librarian adds", expected="`422` seven times (database 500 seats: 201); `403`", code='''
def TEST(client, admin, librarian):
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
'''),
    dict(id="T-DIG-05-c", req="LIB-DIG-05", type="Normal", input="License added to an inactive resource", expected="201", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    assert license_(client, admin, r["id"])["status"] == "active"
'''),
    dict(id="T-DIG-06-a", req="LIB-DIG-06", type="Error", input="License with an `ordered` purchase order; with a draft order; with an unknown order; then the referenced order is cancelled", expected="201 with `order_id`; `409 INVALID_ORDER_STATUS`; `422`; cancel `409 ORDER_HAS_LICENSE`", code='''
def TEST(client, admin, librarian, branch_a):
    r = resource(client, librarian)
    o, draft = order(client, librarian, branch_a), order(client, librarian, branch_a, submit=False)
    assert license_(client, admin, r["id"], order_id=o["id"])["order_id"] == o["id"]
    assert error_code(license_(client, admin, r["id"], order_id=draft["id"], expect=409)) == "INVALID_ORDER_STATUS"
    license_(client, admin, r["id"], order_id=999999, expect=422)
    err(post(client, librarian, f"purchase-orders/{o['id']}/cancel"), 409, "ORDER_HAS_LICENSE")
'''),
    dict(id="T-DIG-06-b", req="LIB-DIG-06", type="Error", input="License with a cancelled purchase order", expected="`409 INVALID_ORDER_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    r = resource(client, librarian)
    o = order(client, librarian, branch_a, submit=False)
    ok(post(client, librarian, f"purchase-orders/{o['id']}/cancel"))
    assert error_code(license_(client, admin, r["id"], order_id=o["id"], expect=409)) == "INVALID_ORDER_STATUS"
'''),
    dict(id="T-DIG-07-a", req="LIB-DIG-07", type="Normal", input="E-book with one license; M1 borrowed; license cancelled; cancelled again; M2 borrows", expected="200, `cancelled_on` 2026-11-02, `cancelled`; `409 INVALID_LICENSE_STATUS`; M2 `409 NO_ACTIVE_LICENSE`; M1's loan stays `open`", code='''
def TEST(client, admin, librarian, branch_a):
    r = resource(client, librarian, loan_days=14)
    lic = license_(client, admin, r["id"], copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    out = ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    assert (out["cancelled_on"], out["status"]) == (MON, "cancelled")
    err(post(client, admin, f"digital-licenses/{lic['id']}/cancel"), 409, "INVALID_LICENSE_STATUS")
    err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_ACTIVE_LICENSE")
    assert get(client, librarian, f"digital-loans/{loan['id']}")["status"] == "open"
'''),
    dict(id="T-DIG-07-b", req="LIB-DIG-07", type="Error", input="Subscription 2026-10-01 – 2026-11-01 (ended); cancel", expected="`409 INVALID_LICENSE_STATUS`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"], model="subscription", starts_on="2026-10-01", ends_on="2026-11-01")
    assert lic["status"] == "ended"
    err(post(client, admin, f"digital-licenses/{lic['id']}/cancel"), 409, "INVALID_LICENSE_STATUS")
'''),
    dict(id="T-DIG-08-a", req="LIB-DIG-08", type="Normal", input="Licenses starting 2026-11-10 (pending) and 2026-10-01; librarian lists, with `status=pending`; member lists", expected="Order 2026-10-01, 2026-11-10; filter → the pending one; member `403`", code='''
def TEST(client, admin, librarian, branch_a):
    r = resource(client, librarian)
    later = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    first = license_(client, admin, r["id"], starts_on="2026-10-01")
    url = f"digital-resources/{r['id']}/licenses"
    assert [x["id"] for x in items(get(client, librarian, url))] == [first["id"], later["id"]]
    assert [x["id"] for x in items(get(client, librarian, url, status="pending"))] == [later["id"]]
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/{url}", headers=mh).status_code == 403
'''),
    dict(id="T-DIG-09-a", req="LIB-DIG-09", type="Normal", input="Book with an active e-book (1 copy, borrowed) and an inactive e-book; unknown book", expected="Only the active e-book with `available` 0; `404 NOT_FOUND`", code='''
def TEST(client, admin, librarian, branch_a):
    book = create_book(client, librarian)
    active = ebook(client, admin, book_id=book["id"])
    gone = ebook(client, admin, book_id=book["id"])
    ok(client.patch(f"/api/v1/digital-resources/{gone['id']}", headers=librarian, json={"is_active": False}))
    ok(borrow(client, librarian, active["id"], member(client, librarian, branch_a)["id"]), 201)
    out = get(client, librarian, f"books/{book['id']}/digital-resources")
    rows = out if isinstance(out, list) else out["items"]
    assert [(x["id"], x["available"]) for x in rows] == [(active["id"], 0)]
    assert client.get("/api/v1/books/999999/digital-resources", headers=librarian).status_code == 404
'''),
    dict(id="T-DIG-10-a", req="LIB-DIG-10", type="Normal", input="Pending license: copies 5, cost 50.00; active subscription: copies 4, then `ends_on` 2026-12-15; perpetual: `ends_on`; subscription `ends_on` 2026-11-01 (before today)", expected="200; `409 INVALID_LICENSE_STATUS`, then 200; `422`; `422`", code='''
def TEST(client, admin, librarian):
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
'''),
    dict(id="T-DIG-10-b", req="LIB-DIG-10", type="Error", input="Ended subscription: change `ends_on`; librarian changes a pending license", expected="`409 INVALID_LICENSE_STATUS`; `403`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    ended = license_(client, admin, r["id"], model="subscription", starts_on="2026-10-01", ends_on="2026-10-31")
    pend = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    err(client.patch(f"/api/v1/digital-licenses/{ended['id']}", headers=admin, json={"ends_on": "2026-12-31"}), 409, "INVALID_LICENSE_STATUS")
    assert client.patch(f"/api/v1/digital-licenses/{pend['id']}", headers=librarian, json={"copies": 2}).status_code == 403
'''),
    dict(id="T-DIG-11-a", req="LIB-DIG-11", type="Normal", input="Subscription 2026-11-01 – 2026-11-30 (3 copies) renewed to 2026-12-31 (900.00); renewed again", expected="201: new subscription 2026-12-01 – 2026-12-31, 3 copies, 900.00, `pending`; then `409 ALREADY_RENEWED`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    sub = license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    new = ok(post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2026-12-31", "cost": "900.00"}), 201)
    assert (new["resource_id"], new["model"], new["copies"], new["starts_on"], new["ends_on"], new["cost"], new["status"]) == (r["id"], "subscription", 3, "2026-12-01", "2026-12-31", "900.00", "pending")
    err(post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2027-01-31", "cost": "900.00"}), 409, "ALREADY_RENEWED")
'''),
    dict(id="T-DIG-11-b", req="LIB-DIG-11", type="Error", input="Renew a perpetual license; a pending subscription; an active subscription (ends 2026-11-30) to 2026-11-30", expected="`409 NOT_A_SUBSCRIPTION`; `409 INVALID_LICENSE_STATUS`; `422`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    perp = license_(client, admin, r["id"])
    pend = license_(client, admin, r["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    sub = license_(client, admin, r["id"], model="subscription", ends_on="2026-11-30")
    body = {"ends_on": "2027-03-31", "cost": "10.00"}
    err(post(client, admin, f"digital-licenses/{perp['id']}/renew", body), 409, "NOT_A_SUBSCRIPTION")
    err(post(client, admin, f"digital-licenses/{pend['id']}/renew", body), 409, "INVALID_LICENSE_STATUS")
    assert post(client, admin, f"digital-licenses/{sub['id']}/renew", {"ends_on": "2026-11-30", "cost": "10.00"}).status_code == 422
'''),
    dict(id="T-DIG-12-a", req="LIB-DIG-12", type="Normal", input="Active subscriptions ending 2026-11-20 (A), 2026-12-31 (B), 2026-11-10 renewed (C), 2026-11-05 (D); list; with `ending_within_days=3`", expected="D, A (with `resource_title`); then only D", code='''
def TEST(client, admin, librarian):
    ids = {}
    for name, ends in (("A", "2026-11-20"), ("B", "2026-12-31"), ("C", "2026-11-10"), ("D", "2026-11-05")):
        r = resource(client, librarian, title=f"Abonelik {name}")
        ids[name] = license_(client, admin, r["id"], model="subscription", ends_on=ends)["id"]
    ok(post(client, admin, f"digital-licenses/{ids['C']}/renew", {"ends_on": "2026-12-31", "cost": "10.00"}), 201)
    rows = items(get(client, librarian, "digital-licenses"))
    assert [(x["id"], x["resource_title"]) for x in rows] == [(ids["D"], "Abonelik D"), (ids["A"], "Abonelik A")]
    assert [x["id"] for x in items(get(client, librarian, "digital-licenses", ending_within_days=3))] == [ids["D"]]
'''),
    dict(id="T-DIG-12-b", req="LIB-DIG-12", type="Error", input="`ending_within_days` 0 and 366; member reads the list", expected="`422` twice; `403`", code='''
def TEST(client, librarian, branch_a):
    for n in (0, 366):
        assert client.get("/api/v1/digital-licenses", headers=librarian, params={"ending_within_days": n}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get("/api/v1/digital-licenses", headers=mh).status_code == 403
'''),
    dict(id="T-DIG-13-a", req="LIB-DIG-13", type="Normal", input="Perpetual 2 copies and subscription 3 copies until 2026-11-30; calendar 2026-11-28 – 2026-12-02", expected="Capacities 5, 5, 5, 2, 2", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    license_(client, admin, r["id"], copies=2)
    license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    out = get(client, librarian, f"digital-resources/{r['id']}/calendar", **{"from": "2026-11-28", "to": "2026-12-02"})
    assert out["resource_id"] == r["id"]
    assert [(d["date"], d["capacity"]) for d in out["days"]] == [("2026-11-28", 5), ("2026-11-29", 5), ("2026-11-30", 5), ("2026-12-01", 2), ("2026-12-02", 2)]
'''),
    dict(id="T-DIG-13-b", req="LIB-DIG-13", type="Error", input="Calendar 2026-11-01 – 2027-02-15 (more than 92 days); `from` after `to`", expected="`422` both", code='''
def TEST(client, librarian):
    r = resource(client, librarian)
    url = f"/api/v1/digital-resources/{r['id']}/calendar"
    assert client.get(url, headers=librarian, params={"from": "2026-11-01", "to": "2027-02-15"}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": "2026-11-04"}).status_code == 422
'''),
    dict(id="T-DIG-14-a", req="LIB-DIG-14", type="Boundary", input="Perpetual 2 copies and subscription 3 copies until 2026-11-30; resource read on 2026-11-30 and 2026-12-01", expected="`capacity` 5, then 2", code='''
def TEST(client, clock, admin, librarian):
    r = resource(client, librarian)
    license_(client, admin, r["id"], copies=2)
    license_(client, admin, r["id"], model="subscription", copies=3, ends_on="2026-11-30")
    at(clock, "2026-11-30", 23, 59, 59)
    assert get(client, librarian, f"digital-resources/{r['id']}")["capacity"] == 5
    at(clock, "2026-12-01", 0, 0)
    assert get(client, librarian, f"digital-resources/{r['id']}")["capacity"] == 2
'''),
    dict(id="T-DIG-14-b", req="LIB-DIG-14", type="Boundary", input="Perpetual 1 copy cancelled on 2026-11-04; subscription 2 copies from 2026-11-10; calendar 2026-11-03 – 2026-11-04 and 2026-11-09 – 2026-11-10", expected="1, 0; 0, 2", code='''
def TEST(client, clock, admin, librarian):
    r = resource(client, librarian)
    perp = license_(client, admin, r["id"])
    license_(client, admin, r["id"], model="subscription", copies=2, starts_on="2026-11-10", ends_on="2026-12-31")
    at(clock, WED, 10)
    ok(post(client, admin, f"digital-licenses/{perp['id']}/cancel"))
    cal = lambda a, b: [d["capacity"] for d in get(client, librarian, f"digital-resources/{r['id']}/calendar", **{"from": a, "to": b})["days"]]
    assert cal("2026-11-03", "2026-11-04") == [1, 0]
    assert cal("2026-11-09", "2026-11-10") == [0, 2]
'''),
    # ---------------------------------------------------------------- e-book loans
    dict(id="T-DIG-15-a", req="LIB-DIG-15", type="Normal", input="Member borrows an e-book (14 days) on Mon 09:00", expected="201: own `member_id`, `open`, `hold_id` null, `renewed` false, `ended_at` null", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    loan = ok(borrow(client, member_headers(client, m), r["id"]), 201)
    assert (loan["resource_id"], loan["member_id"], loan["status"], loan["hold_id"], loan["renewed"], loan["ended_at"]) == (r["id"], m["id"], "open", None, False, None)
    assert same(loan["borrowed_at"], MON, 9)
'''),
    dict(id="T-DIG-15-b", req="LIB-DIG-15", type="Error", input="Librarian borrows without `member_id`; member sends `member_id`", expected="`422` both", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    assert borrow(client, librarian, r["id"]).status_code == 422
    assert borrow(client, member_headers(client, m), r["id"], m["id"]).status_code == 422
'''),
    dict(id="T-DIG-15-c", req="LIB-DIG-15", type="Normal", input="1 copy: M1 borrowed, M2 waits; M1 returns; M2 borrows", expected="Loan with `hold_id` of M2's hold; the hold `fulfilled` with `closed_at`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{l1['id']}/return"))
    loan = ok(borrow(client, member_headers(client, m2), r["id"]), 201)
    assert loan["hold_id"] == h["id"]
    out = holds_of(client, librarian, m2["id"])[0]
    assert out["status"] == "fulfilled" and out["closed_at"] is not None
'''),
    dict(id="T-DIG-16-a", req="LIB-DIG-16", type="Error", input="Borrow a database; borrow an inactive e-book", expected="`409 WRONG_RESOURCE_KIND`; `409 RESOURCE_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    d, e = database(client, admin), ebook(client, admin)
    ok(client.patch(f"/api/v1/digital-resources/{e['id']}", headers=librarian, json={"is_active": False}))
    m = member(client, librarian, branch_a)
    err(borrow(client, librarian, d["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")
    err(borrow(client, librarian, e["id"], m["id"]), 409, "RESOURCE_INACTIVE")
'''),
    dict(id="T-DIG-16-b", req="LIB-DIG-16", type="Error", input="Passive member; guest; member on Tue 2027-11-02 (membership ended 2027-11-01)", expected="`409 MEMBER_PASSIVE`; `409 DIGITAL_NOT_ALLOWED_FOR_TYPE`; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin, copies=3)
    p, g, m = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(borrow(client, librarian, r["id"], p["id"]), 409, "MEMBER_PASSIVE")
    err(borrow(client, librarian, r["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    at(clock, "2027-11-02", 10)
    err(borrow(client, librarian, r["id"], m["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-DIG-16-c", req="LIB-DIG-16", type="Boundary", input="Member with debt 50.00; member with debt 49.99", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"; 201", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, copies=2)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(borrow(client, librarian, r["id"], m1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(borrow(client, librarian, r["id"], m2["id"]), 201)
'''),
    dict(id="T-DIG-16-d", req="LIB-DIG-16", type="Error", input="Member borrows the same e-book (2 copies) twice", expected="`409 ALREADY_BORROWED`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, copies=2)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    err(borrow(client, librarian, r["id"], m["id"]), 409, "ALREADY_BORROWED")
'''),
    dict(id="T-DIG-16-e", req="LIB-DIG-16", type="Boundary", input="Student with 5 active digital loans borrows a sixth e-book", expected="`409 DIGITAL_LOAN_LIMIT_REACHED` with `details.limit` 5", code='''
def TEST(client, admin, librarian, branch_a):
    books = [ebook(client, admin) for _ in range(6)]
    m = member(client, librarian, branch_a)
    for r in books[:5]:
        ok(borrow(client, librarian, r["id"], m["id"]), 201)
    assert err(borrow(client, librarian, books[5]["id"], m["id"]), 409, "DIGITAL_LOAN_LIMIT_REACHED")["details"]["limit"] == 5
'''),
    dict(id="T-DIG-16-f", req="LIB-DIG-16", type="Error", input="E-book without license; e-book with only a pending license (from 2026-11-10)", expected="`409 NO_ACTIVE_LICENSE` both", code='''
def TEST(client, admin, librarian, branch_a):
    bare, later = resource(client, librarian), resource(client, librarian)
    license_(client, admin, later["id"], model="subscription", starts_on="2026-11-10", ends_on="2026-12-31")
    m = member(client, librarian, branch_a)
    err(borrow(client, librarian, bare["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")
    err(borrow(client, librarian, later["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")
'''),
    dict(id="T-DIG-16-g", req="LIB-DIG-16", type="Error", input="1 copy borrowed by M1; M2 borrows; M2 places a hold; M3 borrows", expected="`409 NO_COPY_AVAILABLE` with `details.waiting` 0, then 1", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    assert err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 0
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    assert err(borrow(client, librarian, r["id"], m3["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 1
'''),
    dict(id="T-DIG-16-h", req="LIB-DIG-16", type="Error", input="Passive member borrows an inactive database; and an inactive e-book", expected="`WRONG_RESOURCE_KIND`; `RESOURCE_INACTIVE` (resource checks before member checks)", code='''
def TEST(client, admin, librarian, branch_a):
    d, e = database(client, admin), ebook(client, admin)
    for r in (d, e):
        ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"is_active": False}))
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(borrow(client, librarian, d["id"], p["id"]), 409, "WRONG_RESOURCE_KIND")
    err(borrow(client, librarian, e["id"], p["id"]), 409, "RESOURCE_INACTIVE")
'''),
    dict(id="T-DIG-17-a", req="LIB-DIG-17", type="Normal", input="E-book of 14 days borrowed Mon 09:00; e-book of 3 days borrowed Mon 09:00:30", expected="Due Mon 2026-11-16 09:00; due Thu 2026-11-05 09:00:30", code='''
def TEST(client, clock, admin, librarian, branch_a):
    a, b = ebook(client, admin, loan_days=14), ebook(client, admin, loan_days=3)
    m = member(client, librarian, branch_a)
    assert same(ok(borrow(client, librarian, a["id"], m["id"]), 201)["due_at"], "2026-11-16", 9)
    at(clock, MON, 9, 0, 30)
    assert same(ok(borrow(client, librarian, b["id"], m["id"]), 201)["due_at"], THU, 9, 0, 30)
'''),
    dict(id="T-DIG-18-a", req="LIB-DIG-18", type="Boundary", input="1 copy, 1 day: M1 borrows Mon 09:00; M2 borrows Tue 08:59:59, then Tue 09:00", expected="`409 NO_COPY_AVAILABLE`; then 201; M1's loan shown `expired` with `ended_at` Tue 09:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1 = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    at(clock, TUE, 8, 59, 59)
    err(borrow(client, librarian, r["id"], m2["id"]), 409, "NO_COPY_AVAILABLE")
    at(clock, TUE, 9, 0)
    ok(borrow(client, librarian, r["id"], m2["id"]), 201)
    out = get(client, librarian, f"digital-loans/{l1['id']}")
    assert out["status"] == "expired" and same(out["ended_at"], TUE, 9)
'''),
    dict(id="T-DIG-18-b", req="LIB-DIG-18", type="Normal", input="1-day e-book borrowed Mon 09:00; the same member borrows it again on Tue 09:00", expected="201 (a finished loan is not `ALREADY_BORROWED`)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=1)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    at(clock, TUE, 9, 0)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
'''),
    dict(id="T-DIG-19-a", req="LIB-DIG-19", type="Normal", input="Member returns an active loan at Mon 12:00; returns it again", expected="200 `returned`, `ended_at` 12:00; then `409 LOAN_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    loan = ok(borrow(client, mh, r["id"]), 201)
    at(clock, MON, 12)
    out = ok(post(client, mh, f"digital-loans/{loan['id']}/return"))
    assert out["status"] == "returned" and same(out["ended_at"], MON, 12)
    err(post(client, mh, f"digital-loans/{loan['id']}/return"), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-DIG-19-b", req="LIB-DIG-19", type="Error", input="Return a finished loan (1 day, on Tue 09:00); another member returns a loan", expected="`409 LOAN_NOT_OPEN`; `403`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    a, b = ebook(client, admin, loan_days=1), ebook(client, admin)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    l1, l2 = ok(borrow(client, librarian, a["id"], m["id"]), 201), ok(borrow(client, librarian, b["id"], m["id"]), 201)
    assert post(client, member_headers(client, other), f"digital-loans/{l2['id']}/return").status_code == 403
    at(clock, TUE, 9)
    err(post(client, librarian, f"digital-loans/{l1['id']}/return"), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-DIG-20-a", req="LIB-DIG-20", type="Normal", input="L2 (M2, R2) Mon 10:00; L1 (M1, R1 of 1 day) Mon 09:00; L3 (M1, R2) Mon 11:00, returned; list on Tue 10:00", expected="Order L1, L2, L3; `status=expired` → L1; `returned` → L3; `open` → L2; `resource_id` R2 → L2, L3; `member_id` M1 → L1, L3", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-20-b", req="LIB-DIG-20", type="Error", input="Member reads own loan, a loan of another member, the general list, own list", expected="200; 403; 403; 200 with 1 item", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, copies=2)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = ok(borrow(client, librarian, r["id"], m["id"]), 201), ok(borrow(client, librarian, r["id"], other["id"]), 201)
    mh = member_headers(client, m)
    assert client.get(f"/api/v1/digital-loans/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/digital-loans/{foreign['id']}", headers=mh).status_code == 403
    assert client.get("/api/v1/digital-loans", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/digital-loans")["total"] == 1
'''),
    dict(id="T-DIG-21-a", req="LIB-DIG-21", type="Boundary", input="Loan due Mon 2026-11-16 09:00; renew on Fri 2026-11-13 08:59:59, at 09:00, again", expected="`409 RENEWAL_TOO_EARLY` with `renewable_from` 2026-11-13 09:00; 200 due 2026-11-30 09:00, `renewed` true, `renewed_at` set; `409 RENEWAL_LIMIT_REACHED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-21-b", req="LIB-DIG-21", type="Error", input="1 copy (3 days) borrowed by M1, M2 waiting; M1 renews", expected="`409 RESOURCE_HAS_HOLDS`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=3)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "RESOURCE_HAS_HOLDS")
'''),
    dict(id="T-DIG-21-c", req="LIB-DIG-21", type="Error", input="3-day loan; license cancelled; renew; renew on Thu 09:00 (finished)", expected="`409 NO_ACTIVE_LICENSE`; `409 LOAN_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = resource(client, librarian, loan_days=3)
    lic = license_(client, admin, r["id"])
    loan = ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "NO_ACTIVE_LICENSE")
    at(clock, THU, 9)
    err(post(client, librarian, f"digital-loans/{loan['id']}/renew"), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-DIG-21-d", req="LIB-DIG-21", type="Normal", input="3-day loan due Thu 09:00; `loan_days` changed to 7; renewed", expected="Due Thu 2026-11-12 09:00 (current `loan_days`)", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=3)
    loan = ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    ok(client.patch(f"/api/v1/digital-resources/{r['id']}", headers=librarian, json={"loan_days": 7}))
    assert same(ok(post(client, librarian, f"digital-loans/{loan['id']}/renew"))["due_at"], "2026-11-12", 9)
'''),
    # ---------------------------------------------------------------- holds
    dict(id="T-DIG-22-a", req="LIB-DIG-22", type="Normal", input="1 copy borrowed; M2 places a hold herself; librarian places one for M3", expected="201 `waiting` with `position` 1; 201 with `position` 2", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h2 = ok(hold(client, member_headers(client, m2), r["id"]), 201)
    assert (h2["status"], h2["member_id"], h2["position"], h2["ready_until"]) == ("waiting", m2["id"], 1, None)
    assert ok(hold(client, librarian, r["id"], m3["id"]), 201)["position"] == 2
'''),
    dict(id="T-DIG-23-a", req="LIB-DIG-23", type="Error", input="M2 holds twice; M1 (borrower) holds", expected="`409 DUPLICATE_HOLD`; `409 ALREADY_BORROWED`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    err(hold(client, librarian, r["id"], m2["id"]), 409, "DUPLICATE_HOLD")
    err(hold(client, librarian, r["id"], m1["id"]), 409, "ALREADY_BORROWED")
'''),
    dict(id="T-DIG-23-b", req="LIB-DIG-23", type="Error", input="Hold on an e-book with a free copy; on an e-book without license", expected="`409 HOLD_NOT_NEEDED`; `409 NO_ACTIVE_LICENSE`", code='''
def TEST(client, admin, librarian, branch_a):
    free, bare = ebook(client, admin), resource(client, librarian)
    m = member(client, librarian, branch_a)
    err(hold(client, librarian, free["id"], m["id"]), 409, "HOLD_NOT_NEEDED")
    err(hold(client, librarian, bare["id"], m["id"]), 409, "NO_ACTIVE_LICENSE")
'''),
    dict(id="T-DIG-23-c", req="LIB-DIG-23", type="Boundary", input="Six e-books borrowed by an academic; a student holds five, then the sixth", expected="`409 DIGITAL_HOLD_LIMIT_REACHED` with `details.limit` 5", code='''
def TEST(client, admin, librarian, branch_a):
    books = [ebook(client, admin) for _ in range(6)]
    a, s = member(client, librarian, branch_a, membership_type="academic"), member(client, librarian, branch_a)
    for r in books:
        ok(borrow(client, librarian, r["id"], a["id"]), 201)
    for r in books[:5]:
        ok(hold(client, librarian, r["id"], s["id"]), 201)
    assert err(hold(client, librarian, books[5]["id"], s["id"]), 409, "DIGITAL_HOLD_LIMIT_REACHED")["details"]["limit"] == 5
'''),
    dict(id="T-DIG-23-d", req="LIB-DIG-23", type="Error", input="Guest holds a borrowed e-book; member holds a database", expected="`409 DIGITAL_NOT_ALLOWED_FOR_TYPE`; `409 WRONG_RESOURCE_KIND`", code='''
def TEST(client, admin, librarian, branch_a):
    r, d = ebook(client, admin), database(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    g, m = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a)
    err(hold(client, librarian, r["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    err(hold(client, librarian, d["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")
'''),
    dict(id="T-DIG-24-a", req="LIB-DIG-24", type="Normal", input="1 copy borrowed; M2 holds at Mon 10:00, M3 at Mon 09:30 (clock moved back); queue; the copy is returned; queue with `status=ready`", expected="Queue M3 (position 1), M2 (2); after the return: waiting M2 (position 1), ready M3", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-25-a", req="LIB-DIG-25", type="Normal", input="Member cancels own waiting hold; cancels again", expected="`cancelled`, `member_request`, `closed_at` set, no notification; then `409 HOLD_NOT_ACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    h = ok(hold(client, mh, r["id"]), 201)
    out = ok(post(client, mh, f"digital-holds/{h['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "member_request") and out["closed_at"] is not None
    assert notes(client, librarian, m["id"], "digital_hold_cancelled") == []
    err(post(client, mh, f"digital-holds/{h['id']}/cancel"), 409, "HOLD_NOT_ACTIVE")
'''),
    dict(id="T-DIG-25-b", req="LIB-DIG-25", type="Normal", input="1 copy: M1 borrowed, M2 and M3 wait; M1 returns (M2 ready); librarian cancels M2's hold", expected="`staff_request` and one `digital_hold_cancelled` notification for M2; M3's hold becomes `ready`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h2 = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    assert ok(post(client, librarian, f"digital-holds/{h2['id']}/cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m2["id"], "digital_hold_cancelled")) == 1
    assert holds_of(client, librarian, m3["id"])[0]["status"] == "ready"
'''),
    dict(id="T-DIG-25-c", req="LIB-DIG-25", type="Error", input="Hold ready at Mon 10:00 (lapsed after Wed 10:00); cancelled on Wed 10:00:01; another member cancels a hold", expected="`409 HOLD_NOT_ACTIVE`; `403`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, MON, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    assert post(client, member_headers(client, m3), f"digital-holds/{h['id']}/cancel").status_code == 403
    at(clock, WED, 10, 0, 1)
    err(post(client, librarian, f"digital-holds/{h['id']}/cancel"), 409, "HOLD_NOT_ACTIVE")
'''),
    dict(id="T-DIG-26-a", req="LIB-DIG-26", type="Normal", input="E-book \"Kayıp Şehir\" with 1 copy: M1 borrowed, M2 and M3 wait; M1 returns on Tue 10:00", expected="M2 `ready`, `ready_until` Thu 10:00, one `digital_hold_ready` notification containing the title; M3 `waiting` with position 1", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-26-b", req="LIB-DIG-26", type="Normal", input="1 copy borrowed by M1; M2 and M3 wait; admin adds a license of 2 copies", expected="Both holds `ready`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(hold(client, librarian, r["id"], m3["id"]), 201)
    license_(client, admin, r["id"], copies=2)
    assert [holds_of(client, librarian, m["id"])[0]["status"] for m in (m2, m3)] == ["ready", "ready"]
'''),
    dict(id="T-DIG-26-c", req="LIB-DIG-26", type="Normal", input="1 copy, 1 day: M1 borrowed Mon 09:00, M2 waits; on Tue 09:00 M3 borrows; process", expected="M2 still `waiting`; `409 NO_COPY_AVAILABLE` with `waiting` 1; process gives `holds_ready` 1 and M2 `ready`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=1)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, TUE, 9)
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "waiting"
    assert err(borrow(client, librarian, r["id"], m3["id"]), 409, "NO_COPY_AVAILABLE")["details"]["waiting"] == 1
    assert process(client, librarian)["holds_ready"] == 1
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "ready"
'''),
    dict(id="T-DIG-27-a", req="LIB-DIG-27", type="Boundary", input="M2's hold ready at Tue 10:00 (until Thu 10:00); M3 borrows on Tue 11:00, on Thu 10:00 and on Thu 10:00:01", expected="`409 NO_COPY_AVAILABLE` twice; then 201 (lapsed hold keeps no copy)", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-27-b", req="LIB-DIG-27", type="Boundary", input="M2's hold ready at Tue 10:00; M2 borrows on Thu 10:00", expected="201 with `hold_id`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    at(clock, THU, 10)
    assert ok(borrow(client, librarian, r["id"], m2["id"]), 201)["hold_id"] == h["id"]
'''),
    # ---------------------------------------------------------------- database sessions
    dict(id="T-DIG-28-a", req="LIB-DIG-28", type="Normal", input="Member opens a database session on Mon 10:00", expected="201: `expires_at` 11:00, `open` true, `closed_at` null", code='''
def TEST(client, clock, admin, librarian, branch_a):
    d = database(client, admin)
    m = member(client, librarian, branch_a)
    at(clock, MON, 10)
    s = ok(session(client, member_headers(client, m), d["id"]), 201)
    assert (s["resource_id"], s["member_id"], s["open"], s["closed_at"]) == (d["id"], m["id"], True, None)
    assert same(s["started_at"], MON, 10) and same(s["expires_at"], MON, 11)
'''),
    dict(id="T-DIG-28-b", req="LIB-DIG-28", type="Error", input="Session on an e-book; second session on the same database; student opens a session on a second database", expected="`409 WRONG_RESOURCE_KIND`; `409 SESSION_ALREADY_OPEN` with `details.session_id`; `409 SESSION_LIMIT_REACHED` with `details.limit` 1", code='''
def TEST(client, admin, librarian, branch_a):
    e, d1, d2 = ebook(client, admin), database(client, admin, seats=5), database(client, admin, seats=5)
    m = member(client, librarian, branch_a)
    err(session(client, librarian, e["id"], m["id"]), 409, "WRONG_RESOURCE_KIND")
    s = ok(session(client, librarian, d1["id"], m["id"]), 201)
    assert err(session(client, librarian, d1["id"], m["id"]), 409, "SESSION_ALREADY_OPEN")["details"]["session_id"] == s["id"]
    assert err(session(client, librarian, d2["id"], m["id"]), 409, "SESSION_LIMIT_REACHED")["details"]["limit"] == 1
'''),
    dict(id="T-DIG-28-c", req="LIB-DIG-28", type="Error", input="Database with 1 seat used by M1 since 10:00; M2 opens; database without license", expected="`409 NO_SEAT_AVAILABLE` with `next_free_at` 11:00; `409 NO_ACTIVE_LICENSE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    d, bare = database(client, admin), resource(client, librarian, kind="database")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    ok(session(client, librarian, d["id"], m1["id"]), 201)
    at(clock, MON, 10, 20)
    e = err(session(client, librarian, d["id"], m2["id"]), 409, "NO_SEAT_AVAILABLE")
    assert same(e["details"]["next_free_at"], MON, 11)
    err(session(client, librarian, bare["id"], m2["id"]), 409, "NO_ACTIVE_LICENSE")
'''),
    dict(id="T-DIG-28-d", req="LIB-DIG-28", type="Error", input="Guest; member with debt 50.00; academic opens sessions on three databases", expected="`DIGITAL_NOT_ALLOWED_FOR_TYPE`; `MEMBER_BLOCKED_BY_DEBT`; third `SESSION_LIMIT_REACHED` with `details.limit` 2", code='''
def TEST(client, admin, librarian, branch_a):
    dbs = [database(client, admin, seats=5) for _ in range(3)]
    g, m, a = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    debt(client, librarian, branch_a, m, "50.00")
    err(session(client, librarian, dbs[0]["id"], g["id"]), 409, "DIGITAL_NOT_ALLOWED_FOR_TYPE")
    err(session(client, librarian, dbs[0]["id"], m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    ok(session(client, librarian, dbs[0]["id"], a["id"]), 201)
    ok(session(client, librarian, dbs[1]["id"], a["id"]), 201)
    assert err(session(client, librarian, dbs[2]["id"], a["id"]), 409, "SESSION_LIMIT_REACHED")["details"]["limit"] == 2
'''),
    dict(id="T-DIG-29-a", req="LIB-DIG-29", type="Normal", input="1 seat: M1's session closed at 10:15; closed again; M2 opens", expected="200 with `closed_at` 10:15, `open` false; `409 SESSION_NOT_OPEN`; M2 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-29-b", req="LIB-DIG-29", type="Error", input="Another member closes M1's session; M1 closes it at 11:00 (expired)", expected="`403`; `409 SESSION_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    d = database(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 10)
    s = ok(session(client, librarian, d["id"], m1["id"]), 201)
    assert post(client, member_headers(client, m2), f"digital-sessions/{s['id']}/close").status_code == 403
    at(clock, MON, 11)
    err(post(client, member_headers(client, m1), f"digital-sessions/{s['id']}/close"), 409, "SESSION_NOT_OPEN")
'''),
    dict(id="T-DIG-30-a", req="LIB-DIG-30", type="Boundary", input="Member opens and closes 6 sessions of one database on Monday; opens a seventh; opens one on Tuesday", expected="7th `409 DAILY_SESSION_LIMIT_REACHED`; Tuesday 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-31-a", req="LIB-DIG-31", type="Boundary", input="1 seat: M1 opens at 10:00; M2 opens at 10:59:59 and at 11:00; M1's session read", expected="`409 NO_SEAT_AVAILABLE`; 201; M1's session `open` false, `closed_at` null", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-32-a", req="LIB-DIG-32", type="Normal", input="Sessions S1 (10:00, closed), S2 (12:00, open); list; `open=true`", expected="S2, S1; then only S2", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- processing and effects
    dict(id="T-DIG-33-a", req="LIB-DIG-33", type="Normal", input="Hold of M2 becomes ready after a return", expected="One `digital_hold_ready` notification for M2 with `digital_hold_id`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    h = ok(hold(client, librarian, r["id"], m2["id"]), 201)
    ok(post(client, librarian, f"digital-loans/{loan['id']}/return"))
    n = notes(client, librarian, m2["id"], "digital_hold_ready")
    assert [x["digital_hold_id"] for x in n] == [h["id"]]
'''),
    dict(id="T-DIG-33-b", req="LIB-DIG-33", type="Normal", input="Member borrows, renews and returns e-books and opens a session", expected="The member has no notifications", code='''
def TEST(client, admin, librarian, branch_a):
    a, b, d = ebook(client, admin), ebook(client, admin, loan_days=3), database(client, admin)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    la, lb = ok(borrow(client, mh, a["id"]), 201), ok(borrow(client, mh, b["id"]), 201)
    ok(post(client, mh, f"digital-loans/{lb['id']}/renew"))
    ok(post(client, mh, f"digital-loans/{la['id']}/return"))
    ok(session(client, mh, d["id"]), 201)
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0
'''),
    dict(id="T-DIG-34-a", req="LIB-DIG-34", type="Boundary", input="Loans of 1 day (due Tue 09:00) and 2 days (due Wed 09:00) borrowed Mon 09:00; process Mon 09:00 twice; process Tue 09:00", expected="`due_soon_notices` 1, 0; Tue 1 (and `expired_loans` 1); 2 `digital_loan_due_soon` notifications", code='''
def TEST(client, clock, admin, librarian, branch_a):
    a, b = ebook(client, admin, loan_days=1), ebook(client, admin, loan_days=2)
    m = member(client, librarian, branch_a)
    la, lb = ok(borrow(client, librarian, a["id"], m["id"]), 201), ok(borrow(client, librarian, b["id"], m["id"]), 201)
    assert process(client, librarian)["due_soon_notices"] == 1
    assert process(client, librarian)["due_soon_notices"] == 0
    at(clock, TUE, 9)
    out = process(client, librarian)
    assert (out["due_soon_notices"], out["expired_loans"]) == (1, 1)
    assert sorted(x["digital_loan_id"] for x in notes(client, librarian, m["id"], "digital_loan_due_soon")) == sorted([la["id"], lb["id"]])
'''),
    dict(id="T-DIG-35-a", req="LIB-DIG-35", type="Normal", input="R1 (1 day): M1 borrowed Mon 09:00, M2 waits. R2: M3 borrowed and returned Mon 09:00, M4's hold ready until Wed 09:00. Process Wed 09:00:01", expected="`{expired_loans: 1, expired_holds: 1, holds_ready: 1, due_soon_notices: 0}`; M1's loan stored `expired`; M4's hold `expired`; M2 `ready`; notifications `digital_loan_expired` (M1) and `digital_hold_expired` (M4)", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-35-b", req="LIB-DIG-35", type="Normal", input="Process twice at the same time after a loan finished; member reads process", expected="Second call all counts 0; member `403`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ebook(client, admin, loan_days=1)
    m = member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m["id"]), 201)
    at(clock, WED, 9)
    assert process(client, librarian)["expired_loans"] == 1
    assert process(client, librarian) == {"expired_loans": 0, "expired_holds": 0, "holds_ready": 0, "due_soon_notices": 0}
    assert post(client, member_headers(client, m), "digital/process").status_code == 403
'''),
    dict(id="T-DIG-36-a", req="LIB-DIG-36", type="Normal", input="Member with one active loan, one waiting hold and one ready hold", expected="`digital` = `{open_loans: 1, waiting_holds: 1, ready_holds: 1}`; `borrowing.eligible` true", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-37-a", req="LIB-DIG-37", type="Normal", input="Member with an active loan, a waiting hold and an open session is deactivated", expected="200; loan `returned`; hold `cancelled` with `member_deactivated` and one `digital_hold_cancelled` notification; session closed", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-37-b", req="LIB-DIG-37", type="Normal", input="1 copy borrowed by M1, M2 waits; M1 deactivated", expected="M2's hold `ready`", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(borrow(client, librarian, r["id"], m1["id"]), 201)
    ok(hold(client, librarian, r["id"], m2["id"]), 201)
    deactivate_member(client, librarian, m1["id"])
    assert holds_of(client, librarian, m2["id"])[0]["status"] == "ready"
'''),
    dict(id="T-DIG-38-a", req="LIB-DIG-38", type="Normal", input="Resource created, license added, e-book borrowed and returned, hold placed, session opened; audit log filtered by event", expected="One entry each for `digital_resource_created` (2), `digital_license_added` (2), `digital_loan_created`, `digital_loan_returned`, `digital_hold_created`, `digital_session_opened`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-38-b", req="LIB-DIG-38", type="Normal", input="License cancelled; process run", expected="One entry each for `digital_license_cancelled` and `digital_processed`", code='''
def TEST(client, admin, librarian):
    r = resource(client, librarian)
    lic = license_(client, admin, r["id"])
    ok(post(client, admin, f"digital-licenses/{lic['id']}/cancel"))
    process(client, librarian)
    for event in ("digital_license_cancelled", "digital_processed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-DIG-39-a", req="LIB-DIG-39", type="Normal", input="Alfa (e-book, license 300.00 from 2026-11-01): M1 borrows and renews Mon, M2 holds, M1 returns Tue, M2 borrows. Beta (database, 50.00): M3 opens two sessions. Gamma (inactive e-book, no license). Report 2026-11-01 – 2026-11-20; with `kind=database`", expected="Alfa `{loans 2, renewals 1, holds_placed 1, holds_expired 0, sessions 0, license_cost \"300.00\"}`; Beta sessions 2, cost \"50.00\"; Gamma all 0 and \"0.00\"; `kind=database` → Beta", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-DIG-39-b", req="LIB-DIG-39", type="Error", input="`from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31", expected="`422`; `422`; `403`; 200", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/digital-usage"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": WED}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200
'''),
    dict(id="T-DIG-40-a", req="LIB-DIG-40", type="Normal", input="A digital resource, license and loan exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1 (no digital data)", code='''
def TEST(client, admin, librarian, branch_a):
    r = ebook(client, admin)
    ok(borrow(client, librarian, r["id"], member(client, librarian, branch_a)["id"]), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
