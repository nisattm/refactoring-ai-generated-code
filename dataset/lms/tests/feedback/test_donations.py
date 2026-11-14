"""Feedback tests: module 22 (Donations). Generated from cases/donations.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_member, error_code, items, lend, member_fees, member_headers,
    register_member, report_lost,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); expected_by of a review on MON is 2026-11-16


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


def try_donor(client, headers, **fields):
    _seq[0] += 1
    body = {"kind": "person", "name": f"Donor {_seq[0]:03d}"}
    body.update(fields)
    return post(client, headers, "donors", body)


def donor(client, headers, **fields):
    return ok(try_donor(client, headers, **fields), 201)


def it(title="Bağış Kitabı", isbn=None, year=2020, condition="good", quantity=1, author_text=""):
    return {"title": title, "author_text": author_text, "isbn": isbn, "publication_year": year, "condition": condition, "quantity": quantity}


def try_offer(client, headers, branch, donor_=None, items_=None, note=""):
    body = {"branch_id": branch["id"], "note": note, "items": items_ or [it()]}
    if donor_ is not None:
        body["donor_id"] = donor_["id"]
    return post(client, headers, "donations", body)


def offer(client, headers, branch, donor_=None, items_=None, **kw):
    return ok(try_offer(client, headers, branch, donor_, items_, **kw), 201)


def acc(item, book_, qty=1, value="40.00"):
    return {"item_id": item["id"], "decision": "accepted", "book_id": book_["id"], "accepted_quantity": qty, "estimated_value": value}


def dec(item, reason="out_of_scope"):
    return {"item_id": item["id"], "decision": "declined", "decline_reason": reason}


def try_review(client, lib, donation, decisions):
    return post(client, lib, f"donations/{donation['id']}/review", {"items": decisions})


def review(client, lib, donation, decisions):
    return ok(try_review(client, lib, donation, decisions))


def barcodes(n):
    out = []
    for _ in range(n):
        _seq[0] += 1
        out.append(f"DN{_seq[0]:06d}")
    return out


def try_receive(client, lib, donation, counts):
    body = {"items": [{"item_id": item_id, "barcodes": barcodes(n)} for item_id, n in counts]}
    return post(client, lib, f"donations/{donation['id']}/receive", body)


def receive(client, lib, donation, counts):
    return ok(try_receive(client, lib, donation, counts))


def book(client, lib):
    return create_book(client, lib)


def accepted(client, lib, branch, donor_, value="40.00", qty=1, book_=None):
    """An accepted donation with one item of ``book_`` (new book when None): (donation, item, book)."""
    b = book_ or book(client, lib)
    d = offer(client, lib, branch, donor_, [it(isbn=b["isbn"], quantity=qty)])
    item = d["items"][0]
    return review(client, lib, d, [acc(item, b, qty, value)]), item, b


def given(client, lib, branch, donor_, value="40.00", qty=1):
    """A fully received donation of ``qty`` copies worth ``value`` each."""
    d, item, b = accepted(client, lib, branch, donor_, value, qty)
    return receive(client, lib, d, [(item["id"], qty)]), item, b


def donor_row(client, lib, donor_id):
    return [x for x in items(get(client, lib, "donors")) if x["id"] == donor_id][0]


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def copies_of(client, lib, book_id, **params):
    return items(get(client, lib, f"books/{book_id}/copies", **params))


def test_t_don_01_a(client, librarian):
    """T-DON-01-a (LIB-DON-01): 201 each; defaults anonymous false, is_active true, member_id null"""
    p = donor(client, librarian, name="Ayşe Yılmaz")
    assert (p["kind"], p["name"], p["email"], p["anonymous"], p["is_active"], p["member_id"], p["merged_into_id"]) == ("person", "Ayşe Yılmaz", None, False, True, None, None)
    o = donor(client, librarian, kind="organization", name="Kitap Dostları Derneği", email="info@kitapdostlari.org", phone="+905551112233")
    assert (o["kind"], o["email"]) == ("organization", "info@kitapdostlari.org")


def test_t_don_02_a(client, librarian, branch_a):
    """T-DON-02-a (LIB-DON-02): 422"""
    m = member(client, librarian, branch_a)
    assert try_donor(client, librarian, kind="organization", member_id=m["id"]).status_code == 422


def test_t_don_03_a(client, librarian):
    """T-DON-03-a (LIB-DON-03): Order Ahmet, Mavi Vakfı, zeynep with level none and value_this_year 0.00; q → Mavi Vakfı; kind → Ahmet, zeynep"""
    z = donor(client, librarian, name="zeynep")
    a = donor(client, librarian, name="Ahmet")
    v = donor(client, librarian, kind="organization", name="Mavi Vakfı")
    rows = items(get(client, librarian, "donors"))
    assert [(r["id"], r["level"], r["value_this_year"]) for r in rows] == [(a["id"], "none", "0.00"), (v["id"], "none", "0.00"), (z["id"], "none", "0.00")]
    assert [r["id"] for r in items(get(client, librarian, "donors", q="vak"))] == [v["id"]]
    assert [r["id"] for r in items(get(client, librarian, "donors", kind="person"))] == [a["id"], z["id"]]


def test_t_don_05_a(client, librarian, branch_a):
    """T-DON-05-a (LIB-DON-05): 409 DONOR_HAS_OPEN_DONATIONS with details.donation_ids; 200; 409 DONOR_INACTIVE"""
    d = donor(client, librarian)
    dn = offer(client, librarian, branch_a, d)
    url = f"/api/v1/donors/{d['id']}"
    assert err(client.patch(url, headers=librarian, json={"is_active": False}), 409, "DONOR_HAS_OPEN_DONATIONS")["details"]["donation_ids"] == [dn["id"]]
    ok(post(client, librarian, f"donations/{dn['id']}/cancel"))
    ok(client.patch(url, headers=librarian, json={"is_active": False}))
    err(try_offer(client, librarian, branch_a, d), 409, "DONOR_INACTIVE")


def test_t_don_06_a(client, admin, librarian, branch_a):
    """T-DON-06-a (LIB-DON-06): 200 with T; both donations have donor_id T; S inactive with merged_into_id T"""
    s, t = donor(client, librarian), donor(client, librarian)
    d1, d2 = offer(client, librarian, branch_a, s), offer(client, librarian, branch_a, s)
    out = ok(post(client, admin, f"donors/{s['id']}/merge", {"into_donor_id": t["id"]}))
    assert out["id"] == t["id"]
    assert [get(client, librarian, f"donations/{x['id']}")["donor_id"] for x in (d1, d2)] == [t["id"], t["id"]]
    src = get(client, librarian, f"donors/{s['id']}")
    assert (src["is_active"], src["merged_into_id"]) == (False, t["id"])


def test_t_don_06_c(client, admin, librarian, branch_a):
    """T-DON-06-c (LIB-DON-06): T gets S's member_id and email"""
    m = member(client, librarian, branch_a)
    s = donor(client, librarian, member_id=m["id"], email="kaynak@example.org")
    t = donor(client, librarian)
    out = ok(post(client, admin, f"donors/{s['id']}/merge", {"into_donor_id": t["id"]}))
    assert (out["member_id"], out["email"]) == (m["id"], "kaynak@example.org")


def test_t_don_07_a(client, librarian, branch_a):
    """T-DON-07-a (LIB-DON-07): {donations 3, open_donations 1, copies_received 2, value_received 80.00, first/last_received_on 2026-11-02}; years [{2026, 80.00, none}]"""
    d = donor(client, librarian)
    given(client, librarian, branch_a, d, "40.00", 2)
    accepted(client, librarian, branch_a, d)
    r = offer(client, librarian, branch_a, d)
    review(client, librarian, r, [dec(r["items"][0])])
    h = get(client, librarian, f"donors/{d['id']}/history")
    keys = ("donor_id", "donations", "open_donations", "copies_received", "value_received", "first_received_on", "last_received_on")
    assert tuple(h[k] for k in keys) == (d["id"], 3, 1, 2, "80.00", MON, MON)
    assert h["years"] == [{"year": 2026, "value": "80.00", "level": "none"}]


def test_t_don_08_a(client, librarian, branch_a):
    """T-DON-08-a (LIB-DON-08): 201 offered with offered_at; items pending, received_quantity 0; items_count 2, copies_offered 4"""
    d = donor(client, librarian)
    out = offer(client, librarian, branch_a, d, [it("Sefiller", quantity=3, author_text="Victor Hugo"), it("Nutuk", condition="new")], note="Kutu halinde")
    assert (out["status"], out["donor_id"], out["branch_id"], out["note"], out["items_count"], out["copies_offered"]) == ("offered", d["id"], branch_a["id"], "Kutu halinde", 2, 4)
    assert same(out["offered_at"], MON, 9) and (out["reviewed_at"], out["expected_by"], out["receipt_no"]) == (None, None, None)
    assert [(i["title"], i["decision"], i["received_quantity"], i["book_id"]) for i in out["items"]] == [("Sefiller", "pending", 0, None), ("Nutuk", "pending", 0, None)]


def test_t_don_08_c(client, librarian, branch_a):
    """T-DON-08-c (LIB-DON-08): 201 each"""
    d = donor(client, librarian)
    offer(client, librarian, branch_a, d, [it() for _ in range(30)])
    offer(client, librarian, branch_a, d, [it(quantity=20) for _ in range(5)])
    offer(client, librarian, branch_a, d, [it(year=2026), it(year=1450)])


def test_t_don_09_a(client, librarian, branch_a):
    """T-DON-09-a (LIB-DON-09): 422"""
    m = member(client, librarian, branch_a)
    assert try_offer(client, member_headers(client, m), branch_a, donor(client, librarian)).status_code == 422


def test_t_don_10_a(client, admin, librarian, branch_a):
    """T-DON-10-a (LIB-DON-10): 409 BRANCH_INACTIVE; 409 MEMBER_PASSIVE"""
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_offer(client, librarian, qq, donor(client, librarian)), 409, "BRANCH_INACTIVE")
    m = member(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    err(try_offer(client, member_headers(client, m), branch_a), 409, "MEMBER_PASSIVE")


def test_t_don_11_a(client, librarian, branch_a):
    """T-DON-11-a (LIB-DON-11): 200 with the new items; 409 INVALID_DONATION_STATUS with details.status accepted"""
    d = donor(client, librarian)
    dn = offer(client, librarian, branch_a, d)
    url = f"/api/v1/donations/{dn['id']}"
    out = ok(client.patch(url, headers=librarian, json={"note": "Güncel", "items": [it("Kuyucaklı Yusuf"), it("Tutunamayanlar")]}))
    assert (out["note"], [i["title"] for i in out["items"]]) == ("Güncel", ["Kuyucaklı Yusuf", "Tutunamayanlar"])
    b = book(client, librarian)
    review(client, librarian, out, [acc(out["items"][0], b), dec(out["items"][1])])
    assert err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "INVALID_DONATION_STATUS")["details"]["status"] == "accepted"


def test_t_don_13_a(client, librarian, branch_a):
    """T-DON-13-a (LIB-DON-13): [D3, D2, D1]; [D2, D1]; [D3, D1]; [D2]; 404"""
    a = donor(client, librarian)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d1, d2, d3 = offer(client, librarian, branch_a, a), offer(client, mh, branch_a), offer(client, librarian, branch_a, a)
    ok(post(client, librarian, f"donations/{d3['id']}/cancel"))
    ids = lambda page: [x["id"] for x in items(page)]
    assert ids(get(client, librarian, "donations")) == [d3["id"], d2["id"], d1["id"]]
    assert ids(get(client, librarian, "donations", status="offered")) == [d2["id"], d1["id"]]
    assert ids(get(client, librarian, "donations", donor_id=a["id"])) == [d3["id"], d1["id"]]
    assert ids(get(client, mh, f"members/{m['id']}/donations")) == [d2["id"]]
    assert client.get(f"/api/v1/donations/{d1['id']}", headers=mh).status_code == 404


def test_t_don_15_a(client, librarian, branch_a, branch_b):
    """T-DON-15-a (LIB-DON-15): A: duplicate; B: accepted; poor 1990: poor_condition (first rule)"""
    b = book(client, librarian)
    for _ in range(3):
        add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    d = donor(client, librarian)
    da = offer(client, librarian, branch_a, d, [it(isbn=b["isbn"]), it(condition="poor", year=1990)])
    db = offer(client, librarian, branch_b, d, [it(isbn=b["isbn"])])
    sa = get(client, librarian, f"donations/{da['id']}/suggestions")["items"]
    sb = get(client, librarian, f"donations/{db['id']}/suggestions")["items"]
    assert [(x["decision"], x["decline_reason"]) for x in sa] == [("declined", "duplicate"), ("declined", "poor_condition")]
    assert (sb[0]["decision"], sb[0]["book_id"]) == ("accepted", b["id"])


def test_t_don_16_a(client, librarian, branch_a):
    """T-DON-16-a (LIB-DON-16): 200 accepted, reviewed_at, expected_by 2026-11-16; items with decisions, book_id, accepted_quantity, estimated_value"""
    b1, b2 = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(quantity=3), it(year=1980), it()])
    i1, i2, i3 = d["items"]
    out = review(client, librarian, d, [acc(i1, b1, 2, "40.00"), dec(i2, "too_old"), acc(i3, b2, 1, "150.00")])
    assert (out["status"], out["expected_by"]) == ("accepted", "2026-11-16") and same(out["reviewed_at"], MON, 9)
    keys = ("decision", "decline_reason", "book_id", "accepted_quantity", "estimated_value")
    assert [tuple(x[k] for k in keys) for x in out["items"]] == [("accepted", None, b1["id"], 2, "40.00"), ("declined", "too_old", None, None, None), ("accepted", None, b2["id"], 1, "150.00")]


def test_t_don_17_a(client, librarian, branch_a):
    """T-DON-17-a (LIB-DON-17): 409 ISBN_MISMATCH with details.item_id; 200; 409 INVALID_DONATION_STATUS"""
    x, y = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(isbn=x["isbn"])])
    item = d["items"][0]
    assert err(try_review(client, librarian, d, [acc(item, y)]), 409, "ISBN_MISMATCH")["details"]["item_id"] == item["id"]
    review(client, librarian, d, [acc(item, x)])
    err(try_review(client, librarian, d, [acc(item, x)]), 409, "INVALID_DONATION_STATUS")


def test_t_don_19_a(client, librarian, branch_a):
    """T-DON-19-a (LIB-DON-19): 200 partially_received; X has 2 new available copies at A with price 40.00, acquired_on today and donation_id"""
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian), "40.00", 3)
    out = receive(client, librarian, d, [(item["id"], 2)])
    assert out["status"] == "partially_received" and out["items"][0]["received_quantity"] == 2 and same(out["received_at"], MON, 9)
    cs = copies_of(client, librarian, b["id"])
    assert [(c["status"], c["home_branch_id"], c["price"], c["acquired_on"], c["donation_id"]) for c in cs] == [("available", branch_a["id"], "40.00", MON, d["id"])] * 2


def test_t_don_21_a(client, librarian, branch_a):
    """T-DON-21-a (LIB-DON-21): INVALID_DONATION_STATUS; ITEM_NOT_ACCEPTED with details.item_id; RECEIVE_EXCEEDS_ACCEPTED with details.item_id; CONFLICT; no copy created"""
    dn = donor(client, librarian)
    off = offer(client, librarian, branch_a, dn)
    err(try_receive(client, librarian, off, [(off["items"][0]["id"], 1)]), 409, "INVALID_DONATION_STATUS")
    b = book(client, librarian)
    d = offer(client, librarian, branch_a, dn, [it(quantity=2), it()])
    i1, i2 = d["items"]
    review(client, librarian, d, [acc(i1, b, 2), dec(i2)])
    assert err(try_receive(client, librarian, d, [(i2["id"], 1)]), 409, "ITEM_NOT_ACCEPTED")["details"]["item_id"] == i2["id"]
    assert err(try_receive(client, librarian, d, [(i1["id"], 3)]), 409, "RECEIVE_EXCEEDS_ACCEPTED")["details"]["item_id"] == i1["id"]
    other = add_copy(client, librarian, book(client, librarian)["id"], home_branch_id=branch_a["id"])
    body = {"items": [{"item_id": i1["id"], "barcodes": [barcodes(1)[0], other["barcode"]]}]}
    err(post(client, librarian, f"donations/{d['id']}/receive", body), 409, "CONFLICT")
    assert copies_of(client, librarian, b["id"]) == []


def test_t_don_23_a(client, librarian, branch_a):
    """T-DON-23-a (LIB-DON-23): partially_received; received; receipt total_copies 4, total_value 270.00, lines for I1 (3, 120.00) and I2 (1, 150.00)"""
    b1, b2 = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(quantity=3), it(), it()])
    i1, i2, i3 = d["items"]
    review(client, librarian, d, [acc(i1, b1, 3, "40.00"), acc(i2, b2, 1, "150.00"), dec(i3)])
    assert receive(client, librarian, d, [(i1["id"], 2)])["status"] == "partially_received"
    assert receive(client, librarian, d, [(i1["id"], 1), (i2["id"], 1)])["status"] == "received"
    r = get(client, librarian, f"donations/{d['id']}/receipt")
    assert (r["total_copies"], r["total_value"]) == (4, "270.00")
    assert [(x["item_id"], x["copies"], x["value_per_copy"], x["value"]) for x in r["lines"]] == [(i1["id"], 3, "40.00", "120.00"), (i2["id"], 1, "150.00", "150.00")]


def test_t_don_25_a(client, librarian, branch_a):
    """T-DON-25-a (LIB-DON-25): 200 (the keep period does not apply to lost copies)"""
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    report_lost(client, librarian, loan["id"])
    assert ok(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Kayıp kopya"}))["status"] == "withdrawn"


def test_t_don_27_a(client, clock, librarian, branch_a):
    """T-DON-27-a (LIB-DON-27): expired 0, then 2; both expired; the received copy stays; one donation_expired notification for the member"""
    m = member(client, librarian, branch_a)
    d1 = offer(client, member_headers(client, m), branch_a)
    review(client, librarian, d1, [acc(d1["items"][0], book(client, librarian))])
    d2, item, b = accepted(client, librarian, branch_a, donor(client, librarian), qty=2)
    receive(client, librarian, d2, [(item["id"], 1)])
    at(clock, "2026-11-16")
    assert ok(post(client, librarian, "donations/process")) == {"expired": 0}
    at(clock, "2026-11-17")
    assert ok(post(client, librarian, "donations/process")) == {"expired": 2}
    assert [get(client, librarian, f"donations/{x['id']}")["status"] for x in (d1, d2)] == ["expired", "expired"]
    assert len(copies_of(client, librarian, b["id"])) == 1
    assert len(notes(client, librarian, m["id"], "donation_expired")) == 1


def test_t_don_29_a(client, librarian, branch_a):
    """T-DON-29-a (LIB-DON-29): 409 RECEIPT_NOT_AVAILABLE; 200 with donor, branch and dates; 404"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d = offer(client, mh, branch_a)
    item = d["items"][0]
    review(client, librarian, d, [acc(item, book(client, librarian), 1, "75.50")])
    err(client.get(f"/api/v1/donations/{d['id']}/receipt", headers=librarian), 409, "RECEIPT_NOT_AVAILABLE")
    receive(client, librarian, d, [(item["id"], 1)])
    r = get(client, mh, f"donations/{d['id']}/receipt")
    assert (r["receipt_no"], r["donor"]["id"], r["donor"]["name"], r["branch_id"], r["first_received_on"], r["last_received_on"], r["total_value"]) == ("DN-2026-0001", d["donor_id"], m["full_name"], branch_a["id"], MON, MON, "75.50")
    other = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/donations/{d['id']}/receipt", headers=other).status_code == 404


def test_t_don_31_a(client, librarian, branch_a):
    """T-DON-31-a (LIB-DON-31): none, bronze, bronze, silver, silver, gold"""
    levels = []
    for value, qty in (("499.99", 1), ("500.00", 1), ("1999.99", 1), ("2000.00", 1), ("3333.33", 3), ("5000.00", 2)):
        dn = donor(client, librarian)
        given(client, librarian, branch_a, dn, value, qty)
        levels.append(donor_row(client, librarian, dn["id"])["level"])
    assert levels == ["none", "bronze", "bronze", "silver", "silver", "gold"]


def test_t_don_33_a(client, librarian, branch_a):
    """T-DON-33-a (LIB-DON-33): Two donor_level_reached notifications"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    for value in ("300.00", "300.00", "100.00", "1500.00"):
        d = offer(client, mh, branch_a)
        review(client, librarian, d, [acc(d["items"][0], book(client, librarian), 1, value)])
        receive(client, librarian, d, [(d["items"][0]["id"], 1)])
    assert len(notes(client, librarian, m["id"], "donor_level_reached")) == 2


def test_t_don_35_a(client, librarian, branch_a, branch_b):
    """T-DON-35-a (LIB-DON-35): A: 409 DONATION_PENDING with details.book_ids [X]; B: 200; then 200"""
    d, item, x = accepted(client, librarian, branch_a, donor(client, librarian))
    sup = ok(post(client, librarian, "suppliers", {"name": "Kitap Deposu", "email": None, "phone": None}), 201)
    def order(branch):
        return ok(post(client, librarian, "purchase-orders", {"supplier_id": sup["id"], "branch_id": branch["id"], "lines": [{"book_id": x["id"], "quantity": 1, "unit_price": "50.00"}]}), 201)
    oa, ob = order(branch_a), order(branch_b)
    assert err(post(client, librarian, f"purchase-orders/{oa['id']}/submit"), 409, "DONATION_PENDING")["details"]["book_ids"] == [x["id"]]
    ok(post(client, librarian, f"purchase-orders/{ob['id']}/submit"))
    receive(client, librarian, d, [(item["id"], 1)])
    ok(post(client, librarian, f"purchase-orders/{oa['id']}/submit"))


def test_t_don_37_a(client, librarian, branch_a):
    """T-DON-37-a (LIB-DON-37): Offered → cancelled with member_deactivated; accepted unchanged"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d1, d2 = offer(client, mh, branch_a), offer(client, mh, branch_a)
    review(client, librarian, d2, [acc(d2["items"][0], book(client, librarian))])
    deactivate_member(client, librarian, m["id"])
    o1 = get(client, librarian, f"donations/{d1['id']}")
    assert (o1["status"], o1["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert get(client, librarian, f"donations/{d2['id']}")["status"] == "accepted"


def test_t_don_39_a(client, librarian, branch_a):
    """T-DON-39-a (LIB-DON-39): 409 IN_USE; 204"""
    _, _, b = accepted(client, librarian, branch_a, donor(client, librarian))
    err(client.delete(f"/api/v1/books/{b['id']}", headers=librarian), 409, "IN_USE")
    assert client.delete(f"/api/v1/books/{book(client, librarian)['id']}", headers=librarian).status_code == 204


def test_t_don_41_a(client, librarian, branch_a):
    """T-DON-41-a (LIB-DON-41): No notification"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d = offer(client, mh, branch_a)
    ok(client.patch(f"/api/v1/donations/{d['id']}", headers=mh, json={"note": "Değişti"}))
    ok(post(client, mh, f"donations/{d['id']}/cancel"))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0


def test_t_don_43_a(client, librarian, branch_a, branch_b):
    """T-DON-43-a (LIB-DON-43): A {donations 2, copies_offered 6, copies_accepted 2, copies_received 1, value_received 40.00, declined duplicate 1, too_old 1}; B {1, 1, 0, 0, 0.00}"""
    dn = donor(client, librarian)
    d1 = offer(client, librarian, branch_a, dn, [it(quantity=2), it(quantity=3)])
    review(client, librarian, d1, [acc(d1["items"][0], book(client, librarian), 2, "40.00"), dec(d1["items"][1], "duplicate")])
    receive(client, librarian, d1, [(d1["items"][0]["id"], 1)])
    d2 = offer(client, librarian, branch_a, dn)
    review(client, librarian, d2, [dec(d2["items"][0], "too_old")])
    offer(client, librarian, branch_b, dn)
    rows = items(get(client, librarian, "reports/donations", **{"from": MON, "to": "2026-11-08"}))
    keys = ("branch_id", "donations", "copies_offered", "copies_accepted", "copies_received", "value_received")
    assert [tuple(r[k] for k in keys) for r in rows] == [(branch_a["id"], 2, 6, 2, 1, "40.00"), (branch_b["id"], 1, 1, 0, 0, "0.00")]
    assert rows[0]["declined"] == {"duplicate": 1, "poor_condition": 0, "out_of_scope": 0, "too_old": 1, "other": 0}


def test_t_don_45_a(client, librarian, branch_a):
    """T-DON-45-a (LIB-DON-45): 409 INVALID_DONATION_STATUS each"""
    d = offer(client, librarian, branch_a, donor(client, librarian))
    item = d["items"][0]
    review(client, librarian, d, [dec(item)])
    err(client.patch(f"/api/v1/donations/{d['id']}", headers=librarian, json={"note": "X"}), 409, "INVALID_DONATION_STATUS")
    err(post(client, librarian, f"donations/{d['id']}/cancel"), 409, "INVALID_DONATION_STATUS")
    err(try_review(client, librarian, d, [dec(item)]), 409, "INVALID_DONATION_STATUS")
    err(try_receive(client, librarian, d, [(item["id"], 1)]), 409, "INVALID_DONATION_STATUS")


def test_t_don_47_a(client, admin, librarian, branch_a):
    """T-DON-47-a (LIB-DON-47): The keys of 22.1; the exported copy has no donation_id"""
    given(client, librarian, branch_a, donor(client, librarian))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert out["copies"] and all("donation_id" not in c for c in out["copies"])
