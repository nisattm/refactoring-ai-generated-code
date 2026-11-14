MODULE = "donations"
TITLE = "module 22 (Donations)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- donors
    dict(id="T-DON-01-a", req="LIB-DON-01", type="Normal", input="A person with only `kind` and `name`; an organization with e-mail and phone", expected="201 each; defaults `anonymous` false, `is_active` true, `member_id` null", code='''
def TEST(client, librarian):
    p = donor(client, librarian, name="Ayşe Yılmaz")
    assert (p["kind"], p["name"], p["email"], p["anonymous"], p["is_active"], p["member_id"], p["merged_into_id"]) == ("person", "Ayşe Yılmaz", None, False, True, None, None)
    o = donor(client, librarian, kind="organization", name="Kitap Dostları Derneği", email="info@kitapdostlari.org", phone="+905551112233")
    assert (o["kind"], o["email"]) == ("organization", "info@kitapdostlari.org")
'''),
    dict(id="T-DON-01-b", req="LIB-DON-01", type="Error", input="Kind `company`; empty name; unknown member; e-mail used by another donor (other case); a member that already has a donor; a member creates a donor", expected="`422` three times; `409 CONFLICT` with `details.field` `email`, then `member_id`; `403`", code='''
def TEST(client, librarian, branch_a):
    assert try_donor(client, librarian, kind="company").status_code == 422
    assert try_donor(client, librarian, name="").status_code == 422
    assert try_donor(client, librarian, member_id=999999).status_code == 422
    donor(client, librarian, email="bagis@example.org")
    assert err(try_donor(client, librarian, email="BAGIS@example.org"), 409, "CONFLICT")["details"]["field"] == "email"
    m = member(client, librarian, branch_a)
    donor(client, librarian, member_id=m["id"])
    assert err(try_donor(client, librarian, member_id=m["id"]), 409, "CONFLICT")["details"]["field"] == "member_id"
    assert try_donor(client, member_headers(client, m)).status_code == 403
'''),
    dict(id="T-DON-02-a", req="LIB-DON-02", type="Error", input="An organization donor with `member_id`", expected="`422`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    assert try_donor(client, librarian, kind="organization", member_id=m["id"]).status_code == 422
'''),
    dict(id="T-DON-02-b", req="LIB-DON-02", type="Normal", input="Member M (no donor) offers twice; member N offers while a donor already has N's e-mail", expected="One donor for M with M's name, e-mail and `member_id`, used by both offers; N's new donor has `email` null", code='''
def TEST(client, librarian, branch_a):
    m, n = member(client, librarian, branch_a), member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d1, d2 = offer(client, mh, branch_a), offer(client, mh, branch_a)
    assert d1["donor_id"] == d2["donor_id"]
    dn = get(client, librarian, f"donors/{d1['donor_id']}")
    assert (dn["kind"], dn["name"], dn["email"], dn["member_id"]) == ("person", m["full_name"], m["email"], m["id"])
    donor(client, librarian, email=n["email"])
    d3 = offer(client, member_headers(client, n), branch_a)
    dn3 = get(client, librarian, f"donors/{d3['donor_id']}")
    assert (dn3["member_id"], dn3["email"]) == (n["id"], None)
'''),
    dict(id="T-DON-03-a", req="LIB-DON-03", type="Normal", input="Donors `zeynep`, `Ahmet`, organization `Mavi Vakfı`; list; `q=vak`; `kind=person`", expected="Order Ahmet, Mavi Vakfı, zeynep with `level` `none` and `value_this_year` 0.00; `q` → Mavi Vakfı; `kind` → Ahmet, zeynep", code='''
def TEST(client, librarian):
    z = donor(client, librarian, name="zeynep")
    a = donor(client, librarian, name="Ahmet")
    v = donor(client, librarian, kind="organization", name="Mavi Vakfı")
    rows = items(get(client, librarian, "donors"))
    assert [(r["id"], r["level"], r["value_this_year"]) for r in rows] == [(a["id"], "none", "0.00"), (v["id"], "none", "0.00"), (z["id"], "none", "0.00")]
    assert [r["id"] for r in items(get(client, librarian, "donors", q="vak"))] == [v["id"]]
    assert [r["id"] for r in items(get(client, librarian, "donors", kind="person"))] == [a["id"], z["id"]]
'''),
    dict(id="T-DON-04-a", req="LIB-DON-04", type="Error", input="PATCH name and `anonymous`; PATCH `kind`; PATCH a merged donor", expected="200; `422`; `409 DONOR_MERGED`", code='''
def TEST(client, admin, librarian):
    d = donor(client, librarian)
    url = f"/api/v1/donors/{d['id']}"
    out = ok(client.patch(url, headers=librarian, json={"name": "Yeni Ad", "anonymous": True}))
    assert (out["name"], out["anonymous"]) == ("Yeni Ad", True)
    assert client.patch(url, headers=librarian, json={"kind": "organization"}).status_code == 422
    ok(post(client, admin, f"donors/{d['id']}/merge", {"into_donor_id": donor(client, librarian)["id"]}))
    err(client.patch(url, headers=librarian, json={"name": "X Y"}), 409, "DONOR_MERGED")
'''),
    dict(id="T-DON-05-a", req="LIB-DON-05", type="Error", input="Deactivate a donor with an offered donation; after its cancellation deactivate; offer for the inactive donor", expected="`409 DONOR_HAS_OPEN_DONATIONS` with `details.donation_ids`; 200; `409 DONOR_INACTIVE`", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    dn = offer(client, librarian, branch_a, d)
    url = f"/api/v1/donors/{d['id']}"
    assert err(client.patch(url, headers=librarian, json={"is_active": False}), 409, "DONOR_HAS_OPEN_DONATIONS")["details"]["donation_ids"] == [dn["id"]]
    ok(post(client, librarian, f"donations/{dn['id']}/cancel"))
    ok(client.patch(url, headers=librarian, json={"is_active": False}))
    err(try_offer(client, librarian, branch_a, d), 409, "DONOR_INACTIVE")
'''),
    dict(id="T-DON-06-a", req="LIB-DON-06", type="Normal", input="Donor S with two donations merged into T", expected="200 with T; both donations have `donor_id` T; S inactive with `merged_into_id` T", code='''
def TEST(client, admin, librarian, branch_a):
    s, t = donor(client, librarian), donor(client, librarian)
    d1, d2 = offer(client, librarian, branch_a, s), offer(client, librarian, branch_a, s)
    out = ok(post(client, admin, f"donors/{s['id']}/merge", {"into_donor_id": t["id"]}))
    assert out["id"] == t["id"]
    assert [get(client, librarian, f"donations/{x['id']}")["donor_id"] for x in (d1, d2)] == [t["id"], t["id"]]
    src = get(client, librarian, f"donors/{s['id']}")
    assert (src["is_active"], src["merged_into_id"]) == (False, t["id"])
'''),
    dict(id="T-DON-06-b", req="LIB-DON-06", type="Error", input="Merge into itself; into an unknown donor; two member donors; an already merged donor; librarian merges", expected="`422`; `404`; `409 DONOR_MERGE_CONFLICT`; `409 DONOR_MERGED`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    a, b = donor(client, librarian), donor(client, librarian)
    assert post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": a["id"]}).status_code == 422
    assert post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": 999999}).status_code == 404
    m1 = donor(client, librarian, member_id=member(client, librarian, branch_a)["id"])
    m2 = donor(client, librarian, member_id=member(client, librarian, branch_a)["id"])
    err(post(client, admin, f"donors/{m1['id']}/merge", {"into_donor_id": m2["id"]}), 409, "DONOR_MERGE_CONFLICT")
    assert post(client, librarian, f"donors/{a['id']}/merge", {"into_donor_id": b["id"]}).status_code == 403
    ok(post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": b["id"]}))
    err(post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": m1["id"]}), 409, "DONOR_MERGED")
'''),
    dict(id="T-DON-06-c", req="LIB-DON-06", type="Normal", input="Member donor S (with e-mail) merged into T without member and e-mail", expected="T gets S's `member_id` and `email`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    s = donor(client, librarian, member_id=m["id"], email="kaynak@example.org")
    t = donor(client, librarian)
    out = ok(post(client, admin, f"donors/{s['id']}/merge", {"into_donor_id": t["id"]}))
    assert (out["member_id"], out["email"]) == (m["id"], "kaynak@example.org")
'''),
    dict(id="T-DON-07-a", req="LIB-DON-07", type="Normal", input="Donor with a received donation (2 × 40.00), an accepted one and a rejected one", expected="`{donations 3, open_donations 1, copies_received 2, value_received 80.00, first/last_received_on 2026-11-02}`; years `[{2026, 80.00, none}]`", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    given(client, librarian, branch_a, d, "40.00", 2)
    accepted(client, librarian, branch_a, d)
    r = offer(client, librarian, branch_a, d)
    review(client, librarian, r, [dec(r["items"][0])])
    h = get(client, librarian, f"donors/{d['id']}/history")
    keys = ("donor_id", "donations", "open_donations", "copies_received", "value_received", "first_received_on", "last_received_on")
    assert tuple(h[k] for k in keys) == (d["id"], 3, 1, 2, "80.00", MON, MON)
    assert h["years"] == [{"year": 2026, "value": "80.00", "level": "none"}]
'''),
    # ---------------------------------------------------------------- offers
    dict(id="T-DON-08-a", req="LIB-DON-08", type="Normal", input="Librarian offers 2 items (quantities 3 and 1) for a donor", expected="201 `offered` with `offered_at`; items `pending`, `received_quantity` 0; `items_count` 2, `copies_offered` 4", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    out = offer(client, librarian, branch_a, d, [it("Sefiller", quantity=3, author_text="Victor Hugo"), it("Nutuk", condition="new")], note="Kutu halinde")
    assert (out["status"], out["donor_id"], out["branch_id"], out["note"], out["items_count"], out["copies_offered"]) == ("offered", d["id"], branch_a["id"], "Kutu halinde", 2, 4)
    assert same(out["offered_at"], MON, 9) and (out["reviewed_at"], out["expected_by"], out["receipt_no"]) == (None, None, None)
    assert [(i["title"], i["decision"], i["received_quantity"], i["book_id"]) for i in out["items"]] == [("Sefiller", "pending", 0, None), ("Nutuk", "pending", 0, None)]
'''),
    dict(id="T-DON-08-b", req="LIB-DON-08", type="Error", input="No items; 31 items; total quantity 101; the same ISBN twice; invalid ISBN; years 1449 and 2027; quantity 21; condition `bad`", expected="`422` each", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    isbn = book(client, librarian)["isbn"]
    bad = [[], [it() for _ in range(31)], [it(quantity=20) for _ in range(5)] + [it()], [it(isbn=isbn), it(isbn=isbn)],
           [it(isbn="9780000000000")], [it(year=1449)], [it(year=2027)], [it(quantity=21)], [it(condition="bad")]]
    for items_ in bad:
        body = {"donor_id": d["id"], "branch_id": branch_a["id"], "note": "", "items": items_}
        assert post(client, librarian, "donations", body).status_code == 422, len(items_)
'''),
    dict(id="T-DON-08-c", req="LIB-DON-08", type="Boundary", input="30 items; total quantity 100; year 2026 and 1450", expected="201 each", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    offer(client, librarian, branch_a, d, [it() for _ in range(30)])
    offer(client, librarian, branch_a, d, [it(quantity=20) for _ in range(5)])
    offer(client, librarian, branch_a, d, [it(year=2026), it(year=1450)])
'''),
    dict(id="T-DON-09-a", req="LIB-DON-09", type="Error", input="A member offers with a `donor_id`", expected="`422`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    assert try_offer(client, member_headers(client, m), branch_a, donor(client, librarian)).status_code == 422
'''),
    dict(id="T-DON-10-a", req="LIB-DON-10", type="Error", input="Offer to an inactive branch; a passive member offers", expected="`409 BRANCH_INACTIVE`; `409 MEMBER_PASSIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_offer(client, librarian, qq, donor(client, librarian)), 409, "BRANCH_INACTIVE")
    m = member(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    err(try_offer(client, member_headers(client, m), branch_a), 409, "MEMBER_PASSIVE")
'''),
    dict(id="T-DON-10-b", req="LIB-DON-10", type="Boundary", input="Donor with 3 open donations (offered, accepted, partially received) offers a fourth; after one is received fully, again", expected="`409 DONOR_OFFER_LIMIT` with `details.limit` 3; 201", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    offer(client, librarian, branch_a, d)
    accepted(client, librarian, branch_a, d)
    part, item, _ = accepted(client, librarian, branch_a, d, qty=2)
    receive(client, librarian, part, [(item["id"], 1)])
    assert err(try_offer(client, librarian, branch_a, d), 409, "DONOR_OFFER_LIMIT")["details"]["limit"] == 3
    receive(client, librarian, part, [(item["id"], 1)])
    offer(client, librarian, branch_a, d)
'''),
    dict(id="T-DON-11-a", req="LIB-DON-11", type="Error", input="PATCH note and items of an offer; PATCH after the review", expected="200 with the new items; `409 INVALID_DONATION_STATUS` with `details.status` `accepted`", code='''
def TEST(client, librarian, branch_a):
    d = donor(client, librarian)
    dn = offer(client, librarian, branch_a, d)
    url = f"/api/v1/donations/{dn['id']}"
    out = ok(client.patch(url, headers=librarian, json={"note": "Güncel", "items": [it("Kuyucaklı Yusuf"), it("Tutunamayanlar")]}))
    assert (out["note"], [i["title"] for i in out["items"]]) == ("Güncel", ["Kuyucaklı Yusuf", "Tutunamayanlar"])
    b = book(client, librarian)
    review(client, librarian, out, [acc(out["items"][0], b), dec(out["items"][1])])
    assert err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "INVALID_DONATION_STATUS")["details"]["status"] == "accepted"
'''),
    dict(id="T-DON-12-a", req="LIB-DON-12", type="Normal", input="Member cancels own offer; member cancels own accepted donation; staff cancels it; staff cancels again", expected="200 `cancelled` with `donor_request`; `409 INVALID_DONATION_STATUS`; 200 with `staff_request`; `409 INVALID_DONATION_STATUS`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d1 = offer(client, mh, branch_a)
    out = ok(post(client, mh, f"donations/{d1['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "donor_request")
    d2 = offer(client, mh, branch_a)
    review(client, librarian, d2, [acc(d2["items"][0], book(client, librarian))])
    err(post(client, mh, f"donations/{d2['id']}/cancel"), 409, "INVALID_DONATION_STATUS")
    assert ok(post(client, librarian, f"donations/{d2['id']}/cancel"))["cancel_reason"] == "staff_request"
    err(post(client, librarian, f"donations/{d2['id']}/cancel"), 409, "INVALID_DONATION_STATUS")
'''),
    dict(id="T-DON-13-a", req="LIB-DON-13", type="Normal", input="Donations D1 (donor A), D2 (member M), D3 (A, cancelled); list; `status=offered`; `donor_id` A; M's own list; M reads D1", expected="[D3, D2, D1]; [D2, D1]; [D3, D1]; [D2]; `404`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- review
    dict(id="T-DON-14-a", req="LIB-DON-14", type="Normal", input="Items: poor 2020; good 1995; good 1996 with the ISBN of a book with 3 copies at A (one lost); new 2010 with the ISBN of a book with 4 copies at A; good 2015 without ISBN", expected="`poor_condition`; `too_old`; `accepted` with `book_id`; `duplicate` with `book_id`; decision null", code='''
def TEST(client, librarian, branch_a):
    b3, b4 = book(client, librarian), book(client, librarian)
    c3 = [add_copy(client, librarian, b3["id"], home_branch_id=branch_a["id"]) for _ in range(3)]
    for _ in range(4):
        add_copy(client, librarian, b4["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], c3[0]["id"])
    report_lost(client, librarian, loan["id"])
    d = offer(client, librarian, branch_a, donor(client, librarian),
              [it(condition="poor"), it(year=1995), it(year=1996, isbn=b3["isbn"]), it(year=2010, condition="new", isbn=b4["isbn"]), it(year=2015)])
    out = get(client, librarian, f"donations/{d['id']}/suggestions")["items"]
    assert [(x["item_id"], x["decision"], x["decline_reason"], x["book_id"]) for x in out] == [
        (d["items"][0]["id"], "declined", "poor_condition", None), (d["items"][1]["id"], "declined", "too_old", None),
        (d["items"][2]["id"], "accepted", None, b3["id"]), (d["items"][3]["id"], "declined", "duplicate", b4["id"]),
        (d["items"][4]["id"], None, None, None)]
'''),
    dict(id="T-DON-15-a", req="LIB-DON-15", type="Boundary", input="A book with 3 copies at branch A and none at B; good 2020 items with its ISBN offered to A and to B; a poor item from 1990", expected="A: `duplicate`; B: `accepted`; poor 1990: `poor_condition` (first rule)", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-DON-16-a", req="LIB-DON-16", type="Normal", input="Offer with 3 items: accept 2 of 3 copies at 40.00, decline one `too_old`, accept one at 150.00", expected="200 `accepted`, `reviewed_at`, `expected_by` 2026-11-16; items with decisions, `book_id`, `accepted_quantity`, `estimated_value`", code='''
def TEST(client, librarian, branch_a):
    b1, b2 = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(quantity=3), it(year=1980), it()])
    i1, i2, i3 = d["items"]
    out = review(client, librarian, d, [acc(i1, b1, 2, "40.00"), dec(i2, "too_old"), acc(i3, b2, 1, "150.00")])
    assert (out["status"], out["expected_by"]) == ("accepted", "2026-11-16") and same(out["reviewed_at"], MON, 9)
    keys = ("decision", "decline_reason", "book_id", "accepted_quantity", "estimated_value")
    assert [tuple(x[k] for k in keys) for x in out["items"]] == [("accepted", None, b1["id"], 2, "40.00"), ("declined", "too_old", None, None, None), ("accepted", None, b2["id"], 1, "150.00")]
'''),
    dict(id="T-DON-16-b", req="LIB-DON-16", type="Error", input="Review missing one item; an item twice; accepted without `estimated_value`; accepted 4 of 3; declined with `book_id`; unknown `book_id`; a member reviews", expected="`422` six times; `403`", code='''
def TEST(client, librarian, branch_a):
    b = book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(quantity=3), it()])
    i1, i2 = d["items"]
    no_value = {k: v for k, v in acc(i1, b).items() if k != "estimated_value"}
    bad = [[acc(i1, b)], [acc(i1, b), acc(i1, b), dec(i2)], [no_value, dec(i2)], [acc(i1, b, 4), dec(i2)],
           [acc(i1, b), {**dec(i2), "book_id": b["id"]}], [acc(i1, {"id": 999999}), dec(i2)]]
    for decisions in bad:
        assert try_review(client, librarian, d, decisions).status_code == 422, decisions
    m = member(client, librarian, branch_a)
    assert try_review(client, member_headers(client, m), d, [acc(i1, b), dec(i2)]).status_code == 403
'''),
    dict(id="T-DON-17-a", req="LIB-DON-17", type="Error", input="Item with the ISBN of book X accepted for book Y; reviewed correctly; reviewed again", expected="`409 ISBN_MISMATCH` with `details.item_id`; 200; `409 INVALID_DONATION_STATUS`", code='''
def TEST(client, librarian, branch_a):
    x, y = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(isbn=x["isbn"])])
    item = d["items"][0]
    assert err(try_review(client, librarian, d, [acc(item, y)]), 409, "ISBN_MISMATCH")["details"]["item_id"] == item["id"]
    review(client, librarian, d, [acc(item, x)])
    err(try_review(client, librarian, d, [acc(item, x)]), 409, "INVALID_DONATION_STATUS")
'''),
    dict(id="T-DON-18-a", req="LIB-DON-18", type="Normal", input="A member's offer with 2 items, both declined", expected="`rejected`, `expected_by` null; one `donation_reviewed` notification with `donation_id`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    d = offer(client, member_headers(client, m), branch_a, items_=[it(), it()])
    out = review(client, librarian, d, [dec(d["items"][0], "duplicate"), dec(d["items"][1], "other")])
    assert (out["status"], out["expected_by"]) == ("rejected", None)
    ns = notes(client, librarian, m["id"], "donation_reviewed")
    assert len(ns) == 1 and ns[0]["donation_id"] == d["id"]
'''),
    # ---------------------------------------------------------------- receiving
    dict(id="T-DON-19-a", req="LIB-DON-19", type="Normal", input="Item accepted 3 × 40.00 for book X at branch A; 2 copies received", expected="200 `partially_received`; X has 2 new `available` copies at A with price 40.00, `acquired_on` today and `donation_id`", code='''
def TEST(client, librarian, branch_a):
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian), "40.00", 3)
    out = receive(client, librarian, d, [(item["id"], 2)])
    assert out["status"] == "partially_received" and out["items"][0]["received_quantity"] == 2 and same(out["received_at"], MON, 9)
    cs = copies_of(client, librarian, b["id"])
    assert [(c["status"], c["home_branch_id"], c["price"], c["acquired_on"], c["donation_id"]) for c in cs] == [("available", branch_a["id"], "40.00", MON, d["id"])] * 2
'''),
    dict(id="T-DON-20-a", req="LIB-DON-20", type="Error", input="Empty `items`; empty `barcodes`; an item twice; an item of another donation", expected="`422` three times; `404`", code='''
def TEST(client, librarian, branch_a):
    d, item, _ = accepted(client, librarian, branch_a, donor(client, librarian), qty=3)
    _, other, _ = accepted(client, librarian, branch_a, donor(client, librarian))
    url = f"donations/{d['id']}/receive"
    assert post(client, librarian, url, {"items": []}).status_code == 422
    assert post(client, librarian, url, {"items": [{"item_id": item["id"], "barcodes": []}]}).status_code == 422
    assert try_receive(client, librarian, d, [(item["id"], 1), (item["id"], 1)]).status_code == 422
    assert try_receive(client, librarian, d, [(other["id"], 1)]).status_code == 404
'''),
    dict(id="T-DON-21-a", req="LIB-DON-21", type="Error", input="Receive for an offered donation; a declined item; 3 copies of an item accepted 2; an existing barcode together with a good item", expected="`INVALID_DONATION_STATUS`; `ITEM_NOT_ACCEPTED` with `details.item_id`; `RECEIVE_EXCEEDS_ACCEPTED` with `details.item_id`; `CONFLICT`; no copy created", code='''
def TEST(client, librarian, branch_a):
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
'''),
    dict(id="T-DON-22-a", req="LIB-DON-22", type="Normal", input="A member's donation with I1 accepted 2 and I2 accepted 1: receive 1 of I1; receive 1 of I1 and 1 of I2", expected="`partially_received`, then `received`; two `donation_received` notifications", code='''
def TEST(client, clock, librarian, branch_a):
    m = member(client, librarian, branch_a)
    b1, b2 = book(client, librarian), book(client, librarian)
    d = offer(client, member_headers(client, m), branch_a, items_=[it(quantity=2), it()])
    i1, i2 = d["items"]
    review(client, librarian, d, [acc(i1, b1, 2), acc(i2, b2, 1)])
    assert receive(client, librarian, d, [(i1["id"], 1)])["status"] == "partially_received"
    at(clock, "2026-11-03", 10)
    out = receive(client, librarian, d, [(i1["id"], 1), (i2["id"], 1)])
    assert out["status"] == "received" and same(out["received_at"], "2026-11-03", 10)
    assert len(notes(client, librarian, m["id"], "donation_received")) == 2
'''),
    dict(id="T-DON-23-a", req="LIB-DON-23", type="Normal", input="I1 accepted 3 × 40.00, I2 1 × 150.00, I3 declined; receive 2 of I1; then 1 of I1 and 1 of I2; receipt", expected="`partially_received`; `received`; receipt `total_copies` 4, `total_value` 270.00, lines for I1 (3, 120.00) and I2 (1, 150.00)", code='''
def TEST(client, librarian, branch_a):
    b1, b2 = book(client, librarian), book(client, librarian)
    d = offer(client, librarian, branch_a, donor(client, librarian), [it(quantity=3), it(), it()])
    i1, i2, i3 = d["items"]
    review(client, librarian, d, [acc(i1, b1, 3, "40.00"), acc(i2, b2, 1, "150.00"), dec(i3)])
    assert receive(client, librarian, d, [(i1["id"], 2)])["status"] == "partially_received"
    assert receive(client, librarian, d, [(i1["id"], 1), (i2["id"], 1)])["status"] == "received"
    r = get(client, librarian, f"donations/{d['id']}/receipt")
    assert (r["total_copies"], r["total_value"]) == (4, "270.00")
    assert [(x["item_id"], x["copies"], x["value_per_copy"], x["value"]) for x in r["lines"]] == [(i1["id"], 3, "40.00", "120.00"), (i2["id"], 1, "150.00", "150.00")]
'''),
    dict(id="T-DON-24-a", req="LIB-DON-24", type="Normal", input="Book with a donated copy and a bought copy; copies with `donated=true` and `donated=false`", expected="One copy each; the bought copy has `donation_id` null", code='''
def TEST(client, librarian, branch_a):
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    bought = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    yes = copies_of(client, librarian, b["id"], donated="true")
    no = copies_of(client, librarian, b["id"], donated="false")
    assert [c["donation_id"] for c in yes] == [d["id"]]
    assert [(c["id"], c["donation_id"]) for c in no] == [(bought["id"], None)]
'''),
    dict(id="T-DON-25-a", req="LIB-DON-25", type="Normal", input="Donated copy lent and reported lost on the day it arrived; withdrawn", expected="200 (the keep period does not apply to `lost` copies)", code='''
def TEST(client, librarian, branch_a):
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    report_lost(client, librarian, loan["id"])
    assert ok(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Kayıp kopya"}))["status"] == "withdrawn"
'''),
    dict(id="T-DON-26-a", req="LIB-DON-26", type="Boundary", input="Copy received on 2026-11-02 withdrawn on 2027-04-30 and on 2027-05-01", expected="`409 DONATION_KEEP_PERIOD` with `details.keep_until` 2027-05-01; 200", code='''
def TEST(client, clock, librarian, branch_a):
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    url = f"copies/{cp['id']}/withdraw"
    at(clock, "2027-04-30")
    assert err(post(client, librarian, url, {"reason": "Eskidi artık"}), 409, "DONATION_KEEP_PERIOD")["details"]["keep_until"] == "2027-05-01"
    at(clock, "2027-05-01")
    ok(post(client, librarian, url, {"reason": "Eskidi artık"}))
'''),
    dict(id="T-DON-27-a", req="LIB-DON-27", type="Boundary", input="Member donation accepted on Mon (`expected_by` 2026-11-16) and another partially received; process on 2026-11-16 and on 2026-11-17", expected="`expired` 0, then 2; both `expired`; the received copy stays; one `donation_expired` notification for the member", code='''
def TEST(client, clock, librarian, branch_a):
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
'''),
    dict(id="T-DON-28-a", req="LIB-DON-28", type="Normal", input="D1 received in two parts in 2026, D2 received in 2026, D3 received on 2027-01-04", expected="`DN-2026-0001` (kept at the second part), `DN-2026-0002`, `DN-2027-0001`", code='''
def TEST(client, clock, librarian, branch_a):
    dn = donor(client, librarian)
    d1, i1, _ = accepted(client, librarian, branch_a, dn, qty=2)
    assert receive(client, librarian, d1, [(i1["id"], 1)])["receipt_no"] == "DN-2026-0001"
    d2, i2, _ = accepted(client, librarian, branch_a, dn)
    assert receive(client, librarian, d2, [(i2["id"], 1)])["receipt_no"] == "DN-2026-0002"
    assert receive(client, librarian, d1, [(i1["id"], 1)])["receipt_no"] == "DN-2026-0001"
    at(clock, "2027-01-04")
    d3, i3, _ = accepted(client, librarian, branch_a, dn)
    assert receive(client, librarian, d3, [(i3["id"], 1)])["receipt_no"] == "DN-2027-0001"
'''),
    dict(id="T-DON-29-a", req="LIB-DON-29", type="Error", input="Receipt of a member's accepted donation before receiving; after receiving read by the member and by another member", expected="`409 RECEIPT_NOT_AVAILABLE`; 200 with donor, branch and dates; `404`", code='''
def TEST(client, librarian, branch_a):
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
'''),
    # ---------------------------------------------------------------- recognition
    dict(id="T-DON-30-a", req="LIB-DON-30", type="Normal", input="Donor receives 2 × 300.00 on Mon and 1 × 100.00 on Tue", expected="`value_this_year` 700.00, `level` `bronze`", code='''
def TEST(client, clock, librarian, branch_a):
    dn = donor(client, librarian)
    given(client, librarian, branch_a, dn, "300.00", 2)
    at(clock, "2026-11-03")
    given(client, librarian, branch_a, dn, "100.00", 1)
    row = donor_row(client, librarian, dn["id"])
    assert (row["value_this_year"], row["level"]) == ("700.00", "bronze")
'''),
    dict(id="T-DON-31-a", req="LIB-DON-31", type="Boundary", input="Donors with values 499.99, 500.00, 1999.99, 2000.00, 9999.99, 10000.00", expected="`none`, `bronze`, `bronze`, `silver`, `silver`, `gold`", code='''
def TEST(client, librarian, branch_a):
    levels = []
    for value, qty in (("499.99", 1), ("500.00", 1), ("1999.99", 1), ("2000.00", 1), ("3333.33", 3), ("5000.00", 2)):
        dn = donor(client, librarian)
        given(client, librarian, branch_a, dn, value, qty)
        levels.append(donor_row(client, librarian, dn["id"])["level"])
    assert levels == ["none", "bronze", "bronze", "silver", "silver", "gold"]
'''),
    dict(id="T-DON-32-a", req="LIB-DON-32", type="Boundary", input="Donor receives 600.00 on 2026-12-31 and 700.00 on 2027-01-04; history", expected="years `[{2026, 600.00, bronze}, {2027, 700.00, bronze}]`", code='''
def TEST(client, clock, librarian, branch_a):
    dn = donor(client, librarian)
    at(clock, "2026-12-28")
    d1, i1, _ = accepted(client, librarian, branch_a, dn, "600.00")
    at(clock, "2026-12-31", 15)
    receive(client, librarian, d1, [(i1["id"], 1)])
    d2, i2, _ = accepted(client, librarian, branch_a, dn, "700.00")
    at(clock, "2027-01-04")
    receive(client, librarian, d2, [(i2["id"], 1)])
    assert get(client, librarian, f"donors/{dn['id']}/history")["years"] == [{"year": 2026, "value": "600.00", "level": "bronze"}, {"year": 2027, "value": "700.00", "level": "bronze"}]
'''),
    dict(id="T-DON-33-a", req="LIB-DON-33", type="Normal", input="Member donor receives 300.00 (none), 300.00 (bronze), 100.00 (bronze) and 1500.00 (silver)", expected="Two `donor_level_reached` notifications", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    for value in ("300.00", "300.00", "100.00", "1500.00"):
        d = offer(client, mh, branch_a)
        review(client, librarian, d, [acc(d["items"][0], book(client, librarian), 1, value)])
        receive(client, librarian, d, [(d["items"][0]["id"], 1)])
    assert len(notes(client, librarian, m["id"], "donor_level_reached")) == 2
'''),
    dict(id="T-DON-34-a", req="LIB-DON-34", type="Normal", input="Donors Zehra (silver), Ali (bronze), Can (gold), anonymous (bronze), Ece (none); a member reads the wall; year 2025; year 1999", expected="Can gold, Zehra silver, Ali bronze; `anonymous_count` 1; 2025 empty; `422`", code='''
def TEST(client, librarian, branch_a):
    for name, value, qty, anon in (("Zehra", "2500.00", 1, False), ("Ali", "600.00", 1, False), ("Can", "5000.00", 2, False), ("Gizli", "700.00", 1, True), ("Ece", "10.00", 1, False)):
        given(client, librarian, branch_a, donor(client, librarian, name=name, anonymous=anon), value, qty)
    mh = member_headers(client, member(client, librarian, branch_a))
    wall = get(client, mh, "donor-wall")
    assert (wall["year"], wall["anonymous_count"]) == (2026, 1)
    assert wall["donors"] == [{"name": "Can", "level": "gold"}, {"name": "Zehra", "level": "silver"}, {"name": "Ali", "level": "bronze"}]
    assert get(client, mh, "donor-wall", year=2025)["donors"] == []
    assert client.get("/api/v1/donor-wall", headers=mh, params={"year": 1999}).status_code == 422
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-DON-35-a", req="LIB-DON-35", type="Error", input="Book X accepted (not received) in a donation for branch A; orders with X for A and for B submitted; after receiving, the order for A again", expected="A: `409 DONATION_PENDING` with `details.book_ids` [X]; B: 200; then 200", code='''
def TEST(client, librarian, branch_a, branch_b):
    d, item, x = accepted(client, librarian, branch_a, donor(client, librarian))
    sup = ok(post(client, librarian, "suppliers", {"name": "Kitap Deposu", "email": None, "phone": None}), 201)
    def order(branch):
        return ok(post(client, librarian, "purchase-orders", {"supplier_id": sup["id"], "branch_id": branch["id"], "lines": [{"book_id": x["id"], "quantity": 1, "unit_price": "50.00"}]}), 201)
    oa, ob = order(branch_a), order(branch_b)
    assert err(post(client, librarian, f"purchase-orders/{oa['id']}/submit"), 409, "DONATION_PENDING")["details"]["book_ids"] == [x["id"]]
    ok(post(client, librarian, f"purchase-orders/{ob['id']}/submit"))
    receive(client, librarian, d, [(item["id"], 1)])
    ok(post(client, librarian, f"purchase-orders/{oa['id']}/submit"))
'''),
    dict(id="T-DON-36-a", req="LIB-DON-36", type="Error", input="Branch QQ (no copies, no members) with an offered donation is deactivated; after the cancellation", expected="`409 BRANCH_IN_USE`; 200", code='''
def TEST(client, admin, librarian):
    qq = create_branch(client, admin, "QQ")
    d = offer(client, librarian, qq, donor(client, librarian))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"donations/{d['id']}/cancel"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
    dict(id="T-DON-37-a", req="LIB-DON-37", type="Normal", input="Member with an offered and an accepted donation is deactivated", expected="Offered → `cancelled` with `member_deactivated`; accepted unchanged", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d1, d2 = offer(client, mh, branch_a), offer(client, mh, branch_a)
    review(client, librarian, d2, [acc(d2["items"][0], book(client, librarian))])
    deactivate_member(client, librarian, m["id"])
    o1 = get(client, librarian, f"donations/{d1['id']}")
    assert (o1["status"], o1["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert get(client, librarian, f"donations/{d2['id']}")["status"] == "accepted"
'''),
    dict(id="T-DON-38-a", req="LIB-DON-38", type="Normal", input="Member donor with one received donation (2 × 300.00) and one offer; a member without a donor", expected="`{open 1, copies_received 2, value_this_year 600.00, level bronze}`; `{0, 0, 0.00, none}`", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d = offer(client, mh, branch_a, items_=[it(quantity=2)])
    review(client, librarian, d, [acc(d["items"][0], book(client, librarian), 2, "300.00")])
    receive(client, librarian, d, [(d["items"][0]["id"], 2)])
    offer(client, mh, branch_a)
    assert get(client, librarian, f"members/{m['id']}/summary")["donations"] == {"open": 1, "copies_received": 2, "value_this_year": "600.00", "level": "bronze"}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["donations"] == {"open": 0, "copies_received": 0, "value_this_year": "0.00", "level": "none"}
'''),
    dict(id="T-DON-39-a", req="LIB-DON-39", type="Error", input="Book without copies that is the `book_id` of an accepted item is deleted; a book without copies and donations", expected="`409 IN_USE`; `204`", code='''
def TEST(client, librarian, branch_a):
    _, _, b = accepted(client, librarian, branch_a, donor(client, librarian))
    err(client.delete(f"/api/v1/books/{b['id']}", headers=librarian), 409, "IN_USE")
    assert client.delete(f"/api/v1/books/{book(client, librarian)['id']}", headers=librarian).status_code == 204
'''),
    dict(id="T-DON-40-a", req="LIB-DON-40", type="Normal", input="Anonymous donor with a bronze level; staff reads donors; the wall", expected="Staff see the real name; the wall has no name and `anonymous_count` 1", code='''
def TEST(client, librarian, branch_a):
    dn = donor(client, librarian, name="Gizli Bağışçı", anonymous=True)
    given(client, librarian, branch_a, dn, "800.00")
    assert donor_row(client, librarian, dn["id"])["name"] == "Gizli Bağışçı"
    wall = get(client, librarian, "donor-wall")
    assert (wall["donors"], wall["anonymous_count"]) == ([], 1)
'''),
    dict(id="T-DON-41-a", req="LIB-DON-41", type="Normal", input="A member offers, changes and cancels an offer", expected="No notification", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d = offer(client, mh, branch_a)
    ok(client.patch(f"/api/v1/donations/{d['id']}", headers=mh, json={"note": "Değişti"}))
    ok(post(client, mh, f"donations/{d['id']}/cancel"))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == 0
'''),
    dict(id="T-DON-42-a", req="LIB-DON-42", type="Normal", input="Donor created, changed, merged; donation offered, changed, reviewed, received, another cancelled; process; audit log", expected="One entry of each event", code='''
def TEST(client, admin, librarian, branch_a):
    a, t = donor(client, librarian), donor(client, librarian)
    ok(client.patch(f"/api/v1/donors/{a['id']}", headers=librarian, json={"name": "Değişen Ad"}))
    d = offer(client, librarian, branch_a, a)
    ok(client.patch(f"/api/v1/donations/{d['id']}", headers=librarian, json={"note": "Not"}))
    review(client, librarian, d, [acc(d["items"][0], book(client, librarian))])
    receive(client, librarian, d, [(d["items"][0]["id"], 1)])
    c = offer(client, librarian, branch_a, a)
    ok(post(client, librarian, f"donations/{c['id']}/cancel"))
    ok(post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": t["id"]}))
    ok(post(client, librarian, "donations/process"))
    counts = {"donor_created": 2, "donor_updated": 1, "donors_merged": 1, "donation_offered": 2, "donation_updated": 1, "donation_reviewed": 1,
              "donation_received": 1, "donation_cancelled": 1, "donations_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name
'''),
    dict(id="T-DON-43-a", req="LIB-DON-43", type="Normal", input="Branch A: donation with items accepted 2 (received 1) and declined `duplicate` (quantity 3); donation declined `too_old`; branch B: an offer; report 2026-11-02 – 2026-11-08", expected="A `{donations 2, copies_offered 6, copies_accepted 2, copies_received 1, value_received 40.00, declined duplicate 1, too_old 1}`; B `{1, 1, 0, 0, 0.00}`", code='''
def TEST(client, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-DON-43-b", req="LIB-DON-43", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/donations"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-DON-44-a", req="LIB-DON-44", type="Normal", input="Anonymous donor A 700.00 (1 copy), organization B 2 × 1500.00, donor C without receivings; donors report 2026", expected="B (3000.00, silver, 2 copies), A with its real name (700.00, bronze, 1); C not listed", code='''
def TEST(client, librarian, branch_a):
    a = donor(client, librarian, name="Anonim Kişi", anonymous=True)
    b = donor(client, librarian, kind="organization", name="Vakıf")
    donor(client, librarian)
    given(client, librarian, branch_a, a, "700.00")
    given(client, librarian, branch_a, b, "1500.00", 2)
    rows = items(get(client, librarian, "reports/donors", year=2026))
    keys = ("donor_id", "name", "kind", "value", "level", "copies")
    assert [tuple(r[k] for k in keys) for r in rows] == [(b["id"], "Vakıf", "organization", "3000.00", "silver", 2), (a["id"], "Anonim Kişi", "person", "700.00", "bronze", 1)]
'''),
    dict(id="T-DON-45-a", req="LIB-DON-45", type="Error", input="A rejected donation is changed, cancelled, reviewed and received", expected="`409 INVALID_DONATION_STATUS` each", code='''
def TEST(client, librarian, branch_a):
    d = offer(client, librarian, branch_a, donor(client, librarian))
    item = d["items"][0]
    review(client, librarian, d, [dec(item)])
    err(client.patch(f"/api/v1/donations/{d['id']}", headers=librarian, json={"note": "X"}), 409, "INVALID_DONATION_STATUS")
    err(post(client, librarian, f"donations/{d['id']}/cancel"), 409, "INVALID_DONATION_STATUS")
    err(try_review(client, librarian, d, [dec(item)]), 409, "INVALID_DONATION_STATUS")
    err(try_receive(client, librarian, d, [(item["id"], 1)]), 409, "INVALID_DONATION_STATUS")
'''),
    dict(id="T-DON-46-a", req="LIB-DON-46", type="Normal", input="Donated copy valued 65.00 lent and reported lost", expected="A `lost_book` fee of 65.00", code='''
def TEST(client, librarian, branch_a):
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian), "65.00")
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    m = member(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"])
    assert [f["amount"] for f in items(member_fees(client, librarian, m["id"])) if f["kind"] == "lost_book"] == ["65.00"]
'''),
    dict(id="T-DON-47-a", req="LIB-DON-47", type="Normal", input="A donated copy exists; `GET /api/v1/export`", expected="The keys of 22.1; the exported copy has no `donation_id`", code='''
def TEST(client, admin, librarian, branch_a):
    given(client, librarian, branch_a, donor(client, librarian))
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert out["copies"] and all("donation_id" not in c for c in out["copies"])
'''),
]
