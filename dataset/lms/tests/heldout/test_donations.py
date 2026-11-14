"""Heldout tests: module 22 (Donations). Generated from cases/donations.md."""
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


def test_t_don_01_b(client, librarian, branch_a):
    """T-DON-01-b (LIB-DON-01): 422 three times; 409 CONFLICT with details.field email, then member_id; 403"""
    assert try_donor(client, librarian, kind="company").status_code == 422
    assert try_donor(client, librarian, name="").status_code == 422
    assert try_donor(client, librarian, member_id=999999).status_code == 422
    donor(client, librarian, email="bagis@example.org")
    assert err(try_donor(client, librarian, email="BAGIS@example.org"), 409, "CONFLICT")["details"]["field"] == "email"
    m = member(client, librarian, branch_a)
    donor(client, librarian, member_id=m["id"])
    assert err(try_donor(client, librarian, member_id=m["id"]), 409, "CONFLICT")["details"]["field"] == "member_id"
    assert try_donor(client, member_headers(client, m)).status_code == 403


def test_t_don_02_b(client, librarian, branch_a):
    """T-DON-02-b (LIB-DON-02): One donor for M with M's name, e-mail and member_id, used by both offers; N's new donor has email null"""
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


def test_t_don_04_a(client, admin, librarian):
    """T-DON-04-a (LIB-DON-04): 200; 422; 409 DONOR_MERGED"""
    d = donor(client, librarian)
    url = f"/api/v1/donors/{d['id']}"
    out = ok(client.patch(url, headers=librarian, json={"name": "Yeni Ad", "anonymous": True}))
    assert (out["name"], out["anonymous"]) == ("Yeni Ad", True)
    assert client.patch(url, headers=librarian, json={"kind": "organization"}).status_code == 422
    ok(post(client, admin, f"donors/{d['id']}/merge", {"into_donor_id": donor(client, librarian)["id"]}))
    err(client.patch(url, headers=librarian, json={"name": "X Y"}), 409, "DONOR_MERGED")


def test_t_don_06_b(client, admin, librarian, branch_a):
    """T-DON-06-b (LIB-DON-06): 422; 404; 409 DONOR_MERGE_CONFLICT; 409 DONOR_MERGED; 403"""
    a, b = donor(client, librarian), donor(client, librarian)
    assert post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": a["id"]}).status_code == 422
    assert post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": 999999}).status_code == 404
    m1 = donor(client, librarian, member_id=member(client, librarian, branch_a)["id"])
    m2 = donor(client, librarian, member_id=member(client, librarian, branch_a)["id"])
    err(post(client, admin, f"donors/{m1['id']}/merge", {"into_donor_id": m2["id"]}), 409, "DONOR_MERGE_CONFLICT")
    assert post(client, librarian, f"donors/{a['id']}/merge", {"into_donor_id": b["id"]}).status_code == 403
    ok(post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": b["id"]}))
    err(post(client, admin, f"donors/{a['id']}/merge", {"into_donor_id": m1["id"]}), 409, "DONOR_MERGED")


def test_t_don_08_b(client, librarian, branch_a):
    """T-DON-08-b (LIB-DON-08): 422 each"""
    d = donor(client, librarian)
    isbn = book(client, librarian)["isbn"]
    bad = [[], [it() for _ in range(31)], [it(quantity=20) for _ in range(5)] + [it()], [it(isbn=isbn), it(isbn=isbn)],
           [it(isbn="9780000000000")], [it(year=1449)], [it(year=2027)], [it(quantity=21)], [it(condition="bad")]]
    for items_ in bad:
        body = {"donor_id": d["id"], "branch_id": branch_a["id"], "note": "", "items": items_}
        assert post(client, librarian, "donations", body).status_code == 422, len(items_)


def test_t_don_10_b(client, librarian, branch_a):
    """T-DON-10-b (LIB-DON-10): 409 DONOR_OFFER_LIMIT with details.limit 3; 201"""
    d = donor(client, librarian)
    offer(client, librarian, branch_a, d)
    accepted(client, librarian, branch_a, d)
    part, item, _ = accepted(client, librarian, branch_a, d, qty=2)
    receive(client, librarian, part, [(item["id"], 1)])
    assert err(try_offer(client, librarian, branch_a, d), 409, "DONOR_OFFER_LIMIT")["details"]["limit"] == 3
    receive(client, librarian, part, [(item["id"], 1)])
    offer(client, librarian, branch_a, d)


def test_t_don_12_a(client, librarian, branch_a):
    """T-DON-12-a (LIB-DON-12): 200 cancelled with donor_request; 409 INVALID_DONATION_STATUS; 200 with staff_request; 409 INVALID_DONATION_STATUS"""
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


def test_t_don_14_a(client, librarian, branch_a):
    """T-DON-14-a (LIB-DON-14): poor_condition; too_old; accepted with book_id; duplicate with book_id; decision null"""
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


def test_t_don_16_b(client, librarian, branch_a):
    """T-DON-16-b (LIB-DON-16): 422 six times; 403"""
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


def test_t_don_18_a(client, librarian, branch_a):
    """T-DON-18-a (LIB-DON-18): rejected, expected_by null; one donation_reviewed notification with donation_id"""
    m = member(client, librarian, branch_a)
    d = offer(client, member_headers(client, m), branch_a, items_=[it(), it()])
    out = review(client, librarian, d, [dec(d["items"][0], "duplicate"), dec(d["items"][1], "other")])
    assert (out["status"], out["expected_by"]) == ("rejected", None)
    ns = notes(client, librarian, m["id"], "donation_reviewed")
    assert len(ns) == 1 and ns[0]["donation_id"] == d["id"]


def test_t_don_20_a(client, librarian, branch_a):
    """T-DON-20-a (LIB-DON-20): 422 three times; 404"""
    d, item, _ = accepted(client, librarian, branch_a, donor(client, librarian), qty=3)
    _, other, _ = accepted(client, librarian, branch_a, donor(client, librarian))
    url = f"donations/{d['id']}/receive"
    assert post(client, librarian, url, {"items": []}).status_code == 422
    assert post(client, librarian, url, {"items": [{"item_id": item["id"], "barcodes": []}]}).status_code == 422
    assert try_receive(client, librarian, d, [(item["id"], 1), (item["id"], 1)]).status_code == 422
    assert try_receive(client, librarian, d, [(other["id"], 1)]).status_code == 404


def test_t_don_22_a(client, clock, librarian, branch_a):
    """T-DON-22-a (LIB-DON-22): partially_received, then received; two donation_received notifications"""
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


def test_t_don_24_a(client, librarian, branch_a):
    """T-DON-24-a (LIB-DON-24): One copy each; the bought copy has donation_id null"""
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    bought = add_copy(client, librarian, b["id"], home_branch_id=branch_a["id"])
    yes = copies_of(client, librarian, b["id"], donated="true")
    no = copies_of(client, librarian, b["id"], donated="false")
    assert [c["donation_id"] for c in yes] == [d["id"]]
    assert [(c["id"], c["donation_id"]) for c in no] == [(bought["id"], None)]


def test_t_don_26_a(client, clock, librarian, branch_a):
    """T-DON-26-a (LIB-DON-26): 409 DONATION_KEEP_PERIOD with details.keep_until 2027-05-01; 200"""
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian))
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    url = f"copies/{cp['id']}/withdraw"
    at(clock, "2027-04-30")
    assert err(post(client, librarian, url, {"reason": "Eskidi artık"}), 409, "DONATION_KEEP_PERIOD")["details"]["keep_until"] == "2027-05-01"
    at(clock, "2027-05-01")
    ok(post(client, librarian, url, {"reason": "Eskidi artık"}))


def test_t_don_28_a(client, clock, librarian, branch_a):
    """T-DON-28-a (LIB-DON-28): DN-2026-0001 (kept at the second part), DN-2026-0002, DN-2027-0001"""
    dn = donor(client, librarian)
    d1, i1, _ = accepted(client, librarian, branch_a, dn, qty=2)
    assert receive(client, librarian, d1, [(i1["id"], 1)])["receipt_no"] == "DN-2026-0001"
    d2, i2, _ = accepted(client, librarian, branch_a, dn)
    assert receive(client, librarian, d2, [(i2["id"], 1)])["receipt_no"] == "DN-2026-0002"
    assert receive(client, librarian, d1, [(i1["id"], 1)])["receipt_no"] == "DN-2026-0001"
    at(clock, "2027-01-04")
    d3, i3, _ = accepted(client, librarian, branch_a, dn)
    assert receive(client, librarian, d3, [(i3["id"], 1)])["receipt_no"] == "DN-2027-0001"


def test_t_don_30_a(client, clock, librarian, branch_a):
    """T-DON-30-a (LIB-DON-30): value_this_year 700.00, level bronze"""
    dn = donor(client, librarian)
    given(client, librarian, branch_a, dn, "300.00", 2)
    at(clock, "2026-11-03")
    given(client, librarian, branch_a, dn, "100.00", 1)
    row = donor_row(client, librarian, dn["id"])
    assert (row["value_this_year"], row["level"]) == ("700.00", "bronze")


def test_t_don_32_a(client, clock, librarian, branch_a):
    """T-DON-32-a (LIB-DON-32): years [{2026, 600.00, bronze}, {2027, 700.00, bronze}]"""
    dn = donor(client, librarian)
    at(clock, "2026-12-28")
    d1, i1, _ = accepted(client, librarian, branch_a, dn, "600.00")
    at(clock, "2026-12-31", 15)
    receive(client, librarian, d1, [(i1["id"], 1)])
    d2, i2, _ = accepted(client, librarian, branch_a, dn, "700.00")
    at(clock, "2027-01-04")
    receive(client, librarian, d2, [(i2["id"], 1)])
    assert get(client, librarian, f"donors/{dn['id']}/history")["years"] == [{"year": 2026, "value": "600.00", "level": "bronze"}, {"year": 2027, "value": "700.00", "level": "bronze"}]


def test_t_don_34_a(client, librarian, branch_a):
    """T-DON-34-a (LIB-DON-34): Can gold, Zehra silver, Ali bronze; anonymous_count 1; 2025 empty; 422"""
    for name, value, qty, anon in (("Zehra", "2500.00", 1, False), ("Ali", "600.00", 1, False), ("Can", "5000.00", 2, False), ("Gizli", "700.00", 1, True), ("Ece", "10.00", 1, False)):
        given(client, librarian, branch_a, donor(client, librarian, name=name, anonymous=anon), value, qty)
    mh = member_headers(client, member(client, librarian, branch_a))
    wall = get(client, mh, "donor-wall")
    assert (wall["year"], wall["anonymous_count"]) == (2026, 1)
    assert wall["donors"] == [{"name": "Can", "level": "gold"}, {"name": "Zehra", "level": "silver"}, {"name": "Ali", "level": "bronze"}]
    assert get(client, mh, "donor-wall", year=2025)["donors"] == []
    assert client.get("/api/v1/donor-wall", headers=mh, params={"year": 1999}).status_code == 422


def test_t_don_36_a(client, admin, librarian):
    """T-DON-36-a (LIB-DON-36): 409 BRANCH_IN_USE; 200"""
    qq = create_branch(client, admin, "QQ")
    d = offer(client, librarian, qq, donor(client, librarian))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"donations/{d['id']}/cancel"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))


def test_t_don_38_a(client, librarian, branch_a):
    """T-DON-38-a (LIB-DON-38): {open 1, copies_received 2, value_this_year 600.00, level bronze}; {0, 0, 0.00, none}"""
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    d = offer(client, mh, branch_a, items_=[it(quantity=2)])
    review(client, librarian, d, [acc(d["items"][0], book(client, librarian), 2, "300.00")])
    receive(client, librarian, d, [(d["items"][0]["id"], 2)])
    offer(client, mh, branch_a)
    assert get(client, librarian, f"members/{m['id']}/summary")["donations"] == {"open": 1, "copies_received": 2, "value_this_year": "600.00", "level": "bronze"}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["donations"] == {"open": 0, "copies_received": 0, "value_this_year": "0.00", "level": "none"}


def test_t_don_40_a(client, librarian, branch_a):
    """T-DON-40-a (LIB-DON-40): Staff see the real name; the wall has no name and anonymous_count 1"""
    dn = donor(client, librarian, name="Gizli Bağışçı", anonymous=True)
    given(client, librarian, branch_a, dn, "800.00")
    assert donor_row(client, librarian, dn["id"])["name"] == "Gizli Bağışçı"
    wall = get(client, librarian, "donor-wall")
    assert (wall["donors"], wall["anonymous_count"]) == ([], 1)


def test_t_don_42_a(client, admin, librarian, branch_a):
    """T-DON-42-a (LIB-DON-42): One entry of each event"""
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


def test_t_don_43_b(client, librarian, branch_a):
    """T-DON-43-b (LIB-DON-43): 422; 422; 403"""
    url = "/api/v1/reports/donations"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_don_44_a(client, librarian, branch_a):
    """T-DON-44-a (LIB-DON-44): B (3000.00, silver, 2 copies), A with its real name (700.00, bronze, 1); C not listed"""
    a = donor(client, librarian, name="Anonim Kişi", anonymous=True)
    b = donor(client, librarian, kind="organization", name="Vakıf")
    donor(client, librarian)
    given(client, librarian, branch_a, a, "700.00")
    given(client, librarian, branch_a, b, "1500.00", 2)
    rows = items(get(client, librarian, "reports/donors", year=2026))
    keys = ("donor_id", "name", "kind", "value", "level", "copies")
    assert [tuple(r[k] for k in keys) for r in rows] == [(b["id"], "Vakıf", "organization", "3000.00", "silver", 2), (a["id"], "Anonim Kişi", "person", "700.00", "bronze", 1)]


def test_t_don_46_a(client, librarian, branch_a):
    """T-DON-46-a (LIB-DON-46): A lost_book fee of 65.00"""
    d, item, b = accepted(client, librarian, branch_a, donor(client, librarian), "65.00")
    receive(client, librarian, d, [(item["id"], 1)])
    cp = copies_of(client, librarian, b["id"])[0]
    m = member(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"])
    assert [f["amount"] for f in items(member_fees(client, librarian, m["id"])) if f["kind"] == "lost_book"] == ["65.00"]
