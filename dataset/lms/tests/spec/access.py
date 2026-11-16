MODULE = "access"
TITLE = "module 28 (Member cards and building access)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_member, error_code, items, member_fees, member_headers, register_member,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, SAT = "2026-11-02", "2026-11-03", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); branches are open 08:00-20:00 on working days


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


def issue(client, lib, m):
    return post(client, lib, f"members/{m['id']}/cards")


def card(client, lib, m):
    return ok(issue(client, lib, m), 201)


def holder(client, lib, branch, **kw):
    """A member of ``branch`` with an active card: (member, card)."""
    m = member(client, lib, branch, **kw)
    return m, card(client, lib, m)


def report(client, headers, c, reason="lost"):
    return post(client, headers, f"cards/{c['card_no']}/report", {"reason": reason})


def scan(client, lib, branch, direction="in", card_=None, pass_=None):
    body = {"branch_id": branch["id"], "direction": direction}
    if card_ is not None:
        body["card_no"] = card_["card_no"]
    if pass_ is not None:
        body["pass_code"] = pass_["code"]
    return post(client, lib, "access/scan", body)


def enter(client, lib, branch, card_):
    return ok(scan(client, lib, branch, "in", card_))


def leave(client, lib, branch, card_):
    return ok(scan(client, lib, branch, "out", card_))


def settings(client, admin, branch, **fields):
    return client.put(f"/api/v1/access-settings/{branch['id']}", headers=admin, json=fields)


def sell(client, lib, branch, name="Ziyaretçi Kişi"):
    return post(client, lib, "day-passes", {"branch_id": branch["id"], "visitor_name": name})


def ban(client, lib, m, **fields):
    body = {"reason": "Kurallara uymadı"}
    body.update(fields)
    return post(client, lib, f"members/{m['id']}/access-bans", body)


def occupancy(client, headers, branch):
    return get(client, headers, f"branches/{branch['id']}/occupancy")


def process(client, lib):
    return ok(post(client, lib, "access/process"))


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def cards_of(client, headers, m):
    return items(get(client, headers, f"members/{m['id']}/cards"))


def fee_of(client, lib, m, fee_id):
    return [f for f in items(member_fees(client, lib, m["id"])) if f["id"] == fee_id][0]
'''


CASES = [
    # ---------------------------------------------------------------- cards
    dict(id="T-ACC-01-a", req="LIB-ACC-01", type="Normal", input="Librarian issues the first card of a student registered on Mon", expected="201 `LC00000001`, `active`, `issued_on` Mon, `expires_on` 2027-11-01, no fee; one `card_issued` notification with the number", code='''
def TEST(client, librarian, branch_a):
    m = member(client, librarian, branch_a)
    c = card(client, librarian, m)
    assert (c["card_no"], c["member_id"], c["status"], c["issued_on"], c["expires_on"], c["replaces_id"], c["fee_id"]) == ("LC00000001", m["id"], "active", MON, "2027-11-01", None, None)
    ns = notes(client, librarian, m["id"], "card_issued")
    assert len(ns) == 1 and "LC00000001" in ns[0]["message"] and ns[0]["card_id"] == c["id"]
'''),
    dict(id="T-ACC-02-a", req="LIB-ACC-02", type="Error", input="Card for a passive member; for a member whose membership ended (on 2027-11-02); a second card while one is active; a member issues", expected="`MEMBER_PASSIVE`; `MEMBERSHIP_EXPIRED`; `CARD_ALREADY_ACTIVE` with `details.card_no`; `403`", code='''
def TEST(client, clock, librarian, branch_a):
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(issue(client, librarian, p), 409, "MEMBER_PASSIVE")
    m, c = holder(client, librarian, branch_a)
    assert err(issue(client, librarian, m), 409, "CARD_ALREADY_ACTIVE")["details"]["card_no"] == c["card_no"]
    assert issue(client, mh(client, m), member(client, librarian, branch_a)).status_code == 403
    late = member(client, librarian, branch_a)
    at(clock, "2027-11-02")
    err(issue(client, librarian, late), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-ACC-03-a", req="LIB-ACC-03", type="Normal", input="Card reported lost; a new card issued", expected="New card with `replaces_id` of the old one and `fee_id` of an open `card_replacement` fee of 25.00 with `card_id`", code='''
def TEST(client, librarian, branch_a):
    m, old = holder(client, librarian, branch_a)
    ok(report(client, librarian, old))
    new = card(client, librarian, m)
    assert new["replaces_id"] == old["id"] and new["fee_id"] is not None
    f = fee_of(client, librarian, m, new["fee_id"])
    assert (f["kind"], f["amount"], f["status"], f["card_id"]) == ("card_replacement", "25.00", "open", new["id"])
'''),
    dict(id="T-ACC-04-a", req="LIB-ACC-04", type="Boundary", input="First card; lost → second; damaged → third; lost → fourth (third replacement within 365 days)", expected="Fees none, 25.00, 10.00, 50.00", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    amounts = [c["fee_id"]]
    for reason in ("lost", "damaged", "lost"):
        ok(report(client, librarian, c, reason))
        c = card(client, librarian, m)
        amounts.append(fee_of(client, librarian, m, c["fee_id"])["amount"])
    assert amounts == [None, "25.00", "10.00", "50.00"]
'''),
    dict(id="T-ACC-04-b", req="LIB-ACC-04", type="Normal", input="Card expires (process on 2027-11-02); membership renewed; a new card issued", expected="No fee", code='''
def TEST(client, clock, librarian, branch_a):
    m, old = holder(client, librarian, branch_a)
    at(clock, "2027-11-02")
    process(client, librarian)
    ok(post(client, librarian, f"members/{m['id']}/renew-membership"))
    assert card(client, librarian, m)["fee_id"] is None
'''),
    dict(id="T-ACC-05-a", req="LIB-ACC-05", type="Error", input="Member reports own card damaged; reports it again; reports another member's card", expected="200 `damaged` with `ended_on` Mon; `409 CARD_NOT_ACTIVE` with `details.status` `damaged`; `403`", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    _, other = holder(client, librarian, branch_a)
    h = mh(client, m)
    out = ok(report(client, h, c, "damaged"))
    assert (out["status"], out["ended_on"]) == ("damaged", MON)
    assert err(report(client, h, c), 409, "CARD_NOT_ACTIVE")["details"]["status"] == "damaged"
    assert report(client, h, other).status_code == 403
'''),
    dict(id="T-ACC-06-a", req="LIB-ACC-06", type="Normal", input="Member with an old lost card and a new one; list; look up the new number; an unknown number", expected="[new, old]; card with `member` `{id, member_no, full_name, membership_type, status}`; `404`", code='''
def TEST(client, librarian, branch_a):
    m, old = holder(client, librarian, branch_a)
    ok(report(client, librarian, old))
    new = card(client, librarian, m)
    assert [c["id"] for c in cards_of(client, mh(client, m), m)] == [new["id"], old["id"]]
    out = get(client, librarian, f"cards/{new['card_no']}")
    assert out["member"] == {"id": m["id"], "member_no": m["member_no"], "full_name": m["full_name"], "membership_type": "student", "status": "active"}
    assert client.get("/api/v1/cards/LC99999999", headers=librarian).status_code == 404
'''),
    dict(id="T-ACC-07-a", req="LIB-ACC-07", type="Normal", input="Membership renewed on Mon (valid until 2027-11-01)", expected="The active card's `expires_on` becomes 2028-10-31", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    out = ok(post(client, librarian, f"members/{m['id']}/renew-membership"))
    assert cards_of(client, librarian, m)[0]["expires_on"] == out["valid_until"] == "2028-10-31"
'''),
    dict(id="T-ACC-08-a", req="LIB-ACC-08", type="Normal", input="Two cards expiring 2027-11-01; process on 2027-11-02", expected="`cards_expired` 2; both `expired` with `ended_on` 2027-11-02", code='''
def TEST(client, clock, librarian, branch_a):
    m1, _ = holder(client, librarian, branch_a)
    m2, _ = holder(client, librarian, branch_a)
    at(clock, "2027-11-02")
    assert process(client, librarian)["cards_expired"] == 2
    assert [(c["status"], c["ended_on"]) for m in (m1, m2) for c in cards_of(client, librarian, m)] == [("expired", "2027-11-02")] * 2
'''),
    dict(id="T-ACC-09-a", req="LIB-ACC-09", type="Boundary", input="Card expiring 2027-11-01; process on 2027-11-01 and 2027-11-02", expected="`cards_expired` 0 then 1", code='''
def TEST(client, clock, librarian, branch_a):
    holder(client, librarian, branch_a)
    at(clock, "2027-11-01", 23, 59)
    assert process(client, librarian)["cards_expired"] == 0
    at(clock, "2027-11-02", 0, 0)
    assert process(client, librarian)["cards_expired"] == 1
'''),
    # ---------------------------------------------------------------- settings and occupancy
    dict(id="T-ACC-10-a", req="LIB-ACC-10", type="Error", input="Defaults of branch A; admin sets capacity 100 and price 7.50; capacity 0; price 100.01; unknown branch; a librarian sets", expected="`{capacity null, guest_entry true, day_passes true, day_pass_price 5.00}`; 200 with the new values; `422`; `422`; `404`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    d = get(client, librarian, f"access-settings/{branch_a['id']}")
    assert (d["capacity"], d["guest_entry"], d["day_passes"], d["day_pass_price"]) == (None, True, True, "5.00")
    out = ok(settings(client, admin, branch_a, capacity=100, day_pass_price="7.50"))
    assert (out["capacity"], out["day_pass_price"], out["guest_entry"]) == (100, "7.50", True)
    assert settings(client, admin, branch_a, capacity=0).status_code == 422
    assert settings(client, admin, branch_a, day_pass_price="100.01").status_code == 422
    assert settings(client, admin, {"id": 999999}, capacity=5).status_code == 404
    assert settings(client, librarian, branch_a, capacity=5).status_code == 403
'''),
    dict(id="T-ACC-11-a", req="LIB-ACC-11", type="Error", input="Two people inside branch A; capacity 1; capacity 2", expected="`409 CAPACITY_BELOW_OCCUPANCY` with `details.occupancy` 2; 200", code='''
def TEST(client, admin, librarian, branch_a):
    for _ in range(2):
        enter(client, librarian, branch_a, holder(client, librarian, branch_a)[1])
    assert err(settings(client, admin, branch_a, capacity=1), 409, "CAPACITY_BELOW_OCCUPANCY")["details"]["occupancy"] == 2
    ok(settings(client, admin, branch_a, capacity=2))
'''),
    dict(id="T-ACC-12-a", req="LIB-ACC-12", type="Normal", input="Capacity 10; a member and a day pass visitor inside; a member reads the occupancy", expected="`{inside 2, members 1, visitors 1, capacity 10, free 8}`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(settings(client, admin, branch_a, capacity=10))
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    out = occupancy(client, mh(client, m), branch_a)
    assert {k: out[k] for k in ("branch_id", "inside", "members", "visitors", "capacity", "free")} == {"branch_id": branch_a["id"], "inside": 2, "members": 1, "visitors": 1, "capacity": 10, "free": 8}
'''),
    dict(id="T-ACC-13-a", req="LIB-ACC-13", type="Normal", input="Member enters at 09:00, a day pass visitor at 09:30; inside list; a member reads it", expected="Two rows in order (member with name, pass with code); `403`", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    v1 = enter(client, librarian, branch_a, c)
    at(clock, MON, 9, 30)
    p = ok(sell(client, librarian, branch_a), 201)
    v2 = ok(scan(client, librarian, branch_a, pass_=p))
    rows = items(get(client, librarian, f"branches/{branch_a['id']}/inside"))
    assert [(r["visit_id"], r["member_id"], r["full_name"], r["day_pass_code"]) for r in rows] == [(v1["visit_id"], m["id"], m["full_name"], None), (v2["visit_id"], None, None, p["code"])]
    assert client.get(f"/api/v1/branches/{branch_a['id']}/inside", headers=mh(client, m)).status_code == 403
'''),
    # ---------------------------------------------------------------- gate
    dict(id="T-ACC-14-a", req="LIB-ACC-14", type="Error", input="Scan with a card; with both a card and a pass code; with neither; with an unknown card; direction `sideways`; a member scans", expected="200 `{result entered, visit_id, member_id}`; `422` three times; `404`; `403`", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    out = enter(client, librarian, branch_a, c)
    assert (out["result"], out["member_id"], out["day_pass_id"]) == ("entered", m["id"], None) and out["visit_id"] is not None
    p = ok(sell(client, librarian, branch_a), 201)
    assert scan(client, librarian, branch_a, "in", c, p).status_code == 422
    assert scan(client, librarian, branch_a, "in").status_code == 422
    assert post(client, librarian, "access/scan", {"branch_id": branch_a["id"], "direction": "sideways", "card_no": c["card_no"]}).status_code == 422
    assert scan(client, librarian, branch_a, "in", {"card_no": "LC99999999"}).status_code == 404
    assert scan(client, mh(client, m), branch_a, "out", c).status_code == 403
'''),
    dict(id="T-ACC-15-a", req="LIB-ACC-15", type="Error", input="Lost card; a member whose membership ended (card still active, 2027-11-02 09:00); an inactive branch; Saturday", expected="`CARD_NOT_ACTIVE` with `details.status` `lost`; `MEMBERSHIP_EXPIRED`; `BRANCH_INACTIVE`; `BRANCH_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    _, lost = holder(client, librarian, branch_a)
    ok(report(client, librarian, lost))
    assert err(scan(client, librarian, branch_a, "in", lost), 409, "CARD_NOT_ACTIVE")["details"]["status"] == "lost"
    _, c = holder(client, librarian, branch_a)
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(scan(client, librarian, qq, "in", c), 409, "BRANCH_INACTIVE")
    at(clock, SAT, 10)
    err(scan(client, librarian, branch_a, "in", c), 409, "BRANCH_NOT_OPEN")
    at(clock, "2027-11-02", 9)
    err(scan(client, librarian, branch_a, "in", c), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-ACC-15-b", req="LIB-ACC-15", type="Error", input="A banned member; a guest where `guest_entry` is false; a member inside branch B enters A; capacity 1 with one person inside", expected="`ACCESS_BANNED` with `details.ends_on`; `GUEST_ENTRY_NOT_ALLOWED`; `ALREADY_INSIDE` with `details.branch_id` B; `BRANCH_FULL` with `details.capacity` 1", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    b, bc = holder(client, librarian, branch_a)
    ok(ban(client, librarian, b, ends_on="2026-11-10"), 201)
    assert err(scan(client, librarian, branch_a, "in", bc), 409, "ACCESS_BANNED")["details"]["ends_on"] == "2026-11-10"
    ok(settings(client, admin, branch_a, guest_entry=False, capacity=1))
    _, gc = holder(client, librarian, branch_a, membership_type="guest")
    err(scan(client, librarian, branch_a, "in", gc), 409, "GUEST_ENTRY_NOT_ALLOWED")
    _, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_b, c)
    assert err(scan(client, librarian, branch_a, "in", c), 409, "ALREADY_INSIDE")["details"]["branch_id"] == branch_b["id"]
    enter(client, librarian, branch_a, holder(client, librarian, branch_a)[1])
    assert err(scan(client, librarian, branch_a, "in", holder(client, librarian, branch_a)[1]), 409, "BRANCH_FULL")["details"]["capacity"] == 1
'''),
    dict(id="T-ACC-16-a", req="LIB-ACC-16", type="Normal", input="A member enters at 09:00", expected="The visit history shows the visit with `entered_at` 09:00, `left_at` null, `minutes` null", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    v = enter(client, librarian, branch_a, c)
    rows = items(get(client, librarian, f"members/{m['id']}/visits"))
    assert [(r["id"], r["branch_id"], r["left_at"], r["minutes"]) for r in rows] == [(v["visit_id"], branch_a["id"], None, None)] and same(rows[0]["entered_at"], MON, 9)
'''),
    dict(id="T-ACC-17-a", req="LIB-ACC-17", type="Error", input="Exit without being inside; inside A, exit at B; exit at A with the card reported lost meanwhile", expected="`NOT_INSIDE`; `WRONG_BRANCH` with `details.branch_id` A; 200 `left`", code='''
def TEST(client, librarian, branch_a, branch_b):
    _, c = holder(client, librarian, branch_a)
    err(scan(client, librarian, branch_a, "out", c), 409, "NOT_INSIDE")
    enter(client, librarian, branch_a, c)
    assert err(scan(client, librarian, branch_b, "out", c), 409, "WRONG_BRANCH")["details"]["branch_id"] == branch_a["id"]
    ok(report(client, librarian, c))
    assert leave(client, librarian, branch_a, c)["result"] == "left"
'''),
    dict(id="T-ACC-18-a", req="LIB-ACC-18", type="Boundary", input="Entry at 07:59; at 08:00; again at 08:05; exit at 09:00", expected="`BRANCH_NOT_OPEN`; entered; `ALREADY_INSIDE`; left with `minutes` 60", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    at(clock, TUE, 7, 59)
    err(scan(client, librarian, branch_a, "in", c), 409, "BRANCH_NOT_OPEN")
    at(clock, TUE, 8, 0)
    enter(client, librarian, branch_a, c)
    at(clock, TUE, 8, 5)
    err(scan(client, librarian, branch_a, "in", c), 409, "ALREADY_INSIDE")
    at(clock, TUE, 9, 0)
    leave(client, librarian, branch_a, c)
    assert items(get(client, librarian, f"members/{m['id']}/visits"))[0]["minutes"] == 60
'''),
    dict(id="T-ACC-19-a", req="LIB-ACC-19", type="Error", input="Day pass of A: entry at B; entry at A; entry again; exit; Monday's other pass used on Tuesday", expected="`WRONG_BRANCH`; entered (pass `used`); `PASS_NOT_USABLE` with `details.status` `used`; left; `PASS_NOT_VALID_TODAY`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    p = ok(sell(client, librarian, branch_a), 201)
    q = ok(sell(client, librarian, branch_a), 201)
    err(scan(client, librarian, branch_b, pass_=p), 409, "WRONG_BRANCH")
    out = ok(scan(client, librarian, branch_a, pass_=p))
    assert (out["result"], out["day_pass_id"], out["member_id"]) == ("entered", p["id"], None)
    assert err(scan(client, librarian, branch_a, pass_=p), 409, "PASS_NOT_USABLE")["details"]["status"] == "used"
    assert ok(scan(client, librarian, branch_a, "out", pass_=p))["result"] == "left"
    at(clock, TUE)
    err(scan(client, librarian, branch_a, pass_=q), 409, "PASS_NOT_VALID_TODAY")
'''),
    dict(id="T-ACC-20-a", req="LIB-ACC-20", type="Error", input="Staff end an open visit; end it again", expected="200 (`closed_by` `staff`; the member is no longer inside); `409 VISIT_NOT_OPEN`", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    v = enter(client, librarian, branch_a, c)
    ok(post(client, librarian, f"visits/{v['visit_id']}/close"))
    assert occupancy(client, librarian, branch_a)["inside"] == 0
    row = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
    assert (row["id"], row["closed_by"]) == (v["visit_id"], "staff") and same(row["left_at"], MON, 9)
    err(post(client, librarian, f"visits/{v['visit_id']}/close"), 409, "VISIT_NOT_OPEN")
'''),
    dict(id="T-ACC-21-a", req="LIB-ACC-21", type="Normal", input="A lost card is scanned at A at 10:00; alerts; the member's notifications", expected="One alert `{card_no, branch_id}` at 10:00; one `lost_card_used` notification", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    ok(report(client, librarian, c))
    at(clock, MON, 10)
    err(scan(client, librarian, branch_a, "in", c), 409, "CARD_NOT_ACTIVE")
    rows = items(get(client, librarian, "access/alerts"))
    assert [(r["card_no"], r["branch_id"]) for r in rows] == [(c["card_no"], branch_a["id"])] and same(rows[0]["at"], MON, 10)
    assert len(notes(client, librarian, m["id"], "lost_card_used")) == 1
'''),
    dict(id="T-ACC-22-a", req="LIB-ACC-22", type="Normal", input="Two members enter Mon at 10:00 and 15:00; process on Mon 21:00", expected="`visits_closed` 2 with `left_at` Mon 20:00 and `closed_by` `closing`", code='''
def TEST(client, clock, librarian, branch_a):
    m1, c1 = holder(client, librarian, branch_a)
    m2, c2 = holder(client, librarian, branch_a)
    at(clock, MON, 10); enter(client, librarian, branch_a, c1)
    at(clock, MON, 15); enter(client, librarian, branch_a, c2)
    at(clock, MON, 21)
    assert process(client, librarian)["visits_closed"] == 2
    for m in (m1, m2):
        v = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
        assert same(v["left_at"], MON, 20)
'''),
    dict(id="T-ACC-23-a", req="LIB-ACC-23", type="Boundary", input="Member enters at 19:30; process at 19:59 and at 20:30", expected="`visits_closed` 0; then 1 with `left_at` 20:00 (`minutes` 30)", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    at(clock, MON, 19, 30)
    enter(client, librarian, branch_a, c)
    at(clock, MON, 19, 59)
    assert process(client, librarian)["visits_closed"] == 0
    at(clock, MON, 20, 30)
    assert process(client, librarian)["visits_closed"] == 1
    v = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
    assert same(v["left_at"], MON, 20) and v["minutes"] == 30
'''),
    dict(id="T-ACC-24-a", req="LIB-ACC-24", type="Normal", input="An unused day pass of Mon and a used one (visitor still inside); process on Tue 07:00", expected="`{visits_closed 1, cards_expired 0, passes_expired 1}`; the unused pass `cancelled`", code='''
def TEST(client, clock, librarian, branch_a):
    unused = ok(sell(client, librarian, branch_a), 201)
    used = ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=used))
    at(clock, TUE, 7)
    out = process(client, librarian)
    assert (out["visits_closed"], out["cards_expired"], out["passes_expired"]) == (1, 0, 1)
    rows = {p["id"]: p["status"] for p in items(get(client, librarian, "day-passes"))}
    assert (rows[unused["id"]], rows[used["id"]]) == ("cancelled", "used")
'''),
    # ---------------------------------------------------------------- day passes and bans
    dict(id="T-ACC-25-a", req="LIB-ACC-25", type="Error", input="Sell a pass at A (price 7.50); with day passes disabled at B; at an inactive branch", expected="201 `unused` for today at 7.50; `DAY_PASSES_DISABLED`; `BRANCH_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    ok(settings(client, admin, branch_a, day_pass_price="7.50"))
    p = ok(sell(client, librarian, branch_a, "Deniz Kaya"), 201)
    assert (p["branch_id"], p["visitor_name"], p["valid_on"], p["price"], p["status"]) == (branch_a["id"], "Deniz Kaya", MON, "7.50", "unused")
    ok(settings(client, admin, branch_b, day_passes=False))
    err(sell(client, librarian, branch_b), 409, "DAY_PASSES_DISABLED")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(sell(client, librarian, qq), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-ACC-25-b", req="LIB-ACC-25", type="Boundary", input="50 passes sold at A today (one cancelled); a 51st; one at B", expected="`DAY_PASS_LIMIT_REACHED` with `details.limit` 50; B 201", code='''
def TEST(client, librarian, branch_a, branch_b):
    first = ok(sell(client, librarian, branch_a), 201)
    for _ in range(49):
        ok(sell(client, librarian, branch_a), 201)
    ok(post(client, librarian, f"day-passes/{first['id']}/cancel"))
    assert err(sell(client, librarian, branch_a), 409, "DAY_PASS_LIMIT_REACHED")["details"]["limit"] == 50
    ok(sell(client, librarian, branch_b), 201)
'''),
    dict(id="T-ACC-26-a", req="LIB-ACC-26", type="Normal", input="Three passes sold at branch AA on 2026-11-02; one at BB", expected="Codes `DP-AA-20261102-1` … `-3`; `DP-BB-20261102-1`", code='''
def TEST(client, librarian, branch_a, branch_b):
    codes = [ok(sell(client, librarian, branch_a), 201)["code"] for _ in range(3)]
    assert codes == ["DP-AA-20261102-1", "DP-AA-20261102-2", "DP-AA-20261102-3"]
    assert ok(sell(client, librarian, branch_b), 201)["code"] == "DP-BB-20261102-1"
'''),
    dict(id="T-ACC-27-a", req="LIB-ACC-27", type="Error", input="Cancel an unused pass; cancel it again; cancel a used pass", expected="200 `cancelled`; `409 PASS_NOT_USABLE` twice", code='''
def TEST(client, librarian, branch_a):
    p = ok(sell(client, librarian, branch_a), 201)
    assert ok(post(client, librarian, f"day-passes/{p['id']}/cancel"))["status"] == "cancelled"
    err(post(client, librarian, f"day-passes/{p['id']}/cancel"), 409, "PASS_NOT_USABLE")
    u = ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=u))
    err(post(client, librarian, f"day-passes/{u['id']}/cancel"), 409, "PASS_NOT_USABLE")
'''),
    dict(id="T-ACC-28-a", req="LIB-ACC-28", type="Normal", input="Passes P1 (A), P2 (B), P3 (A, used); list; `branch_id` A; `status=used`", expected="[P3, P2, P1]; [P3, P1]; [P3]", code='''
def TEST(client, librarian, branch_a, branch_b):
    p1, p2, p3 = ok(sell(client, librarian, branch_a), 201), ok(sell(client, librarian, branch_b), 201), ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=p3))
    ids = lambda **f: [p["id"] for p in items(get(client, librarian, "day-passes", **f))]
    assert ids() == [p3["id"], p2["id"], p1["id"]]
    assert ids(branch_id=branch_a["id"]) == [p3["id"], p1["id"]]
    assert ids(status="used") == [p3["id"]]
'''),
    dict(id="T-ACC-29-a", req="LIB-ACC-29", type="Normal", input="A member inside A is banned from today until 2026-11-10; bans starting yesterday or longer than 365 days", expected="201; the visit ended (`inside` 0); one `access_banned` notification naming 2026-11-10; `422` twice", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    b = ok(ban(client, librarian, m, ends_on="2026-11-10"), 201)
    assert (b["starts_on"], b["ends_on"], b["lifted_at"]) == (MON, "2026-11-10", None)
    assert occupancy(client, librarian, branch_a)["inside"] == 0
    ns = notes(client, librarian, m["id"], "access_banned")
    assert len(ns) == 1 and "2026-11-10" in ns[0]["message"]
    other = member(client, librarian, branch_a)
    assert ban(client, librarian, other, starts_on="2026-11-01", ends_on="2026-11-10").status_code == 422
    assert ban(client, librarian, other, starts_on=MON, ends_on="2027-11-03").status_code == 422
'''),
    dict(id="T-ACC-30-a", req="LIB-ACC-30", type="Error", input="Lift a ban; lift again; the member enters", expected="200 with `lifted_at`; `409 BAN_ALREADY_LIFTED`; entered", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    b = ok(ban(client, librarian, m, ends_on="2026-11-10"), 201)
    out = ok(post(client, librarian, f"access-bans/{b['id']}/lift"))
    assert same(out["lifted_at"], MON, 9)
    err(post(client, librarian, f"access-bans/{b['id']}/lift"), 409, "BAN_ALREADY_LIFTED")
    enter(client, librarian, branch_a, c)
'''),
    dict(id="T-ACC-31-a", req="LIB-ACC-31", type="Normal", input="A future ban (2026-11-20 – 2026-11-25) and a current lifted one; the member reads own bans", expected="[future (in_force false), current (in_force false)]", code='''
def TEST(client, librarian, branch_a):
    m, _ = holder(client, librarian, branch_a)
    cur = ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    ok(post(client, librarian, f"access-bans/{cur['id']}/lift"))
    fut = ok(ban(client, librarian, m, starts_on="2026-11-20", ends_on="2026-11-25"), 201)
    rows = items(get(client, mh(client, m), f"members/{m['id']}/access-bans"))
    assert [(r["id"], r["in_force"]) for r in rows] == [(fut["id"], False), (cur["id"], False)]
'''),
    dict(id="T-ACC-32-a", req="LIB-ACC-32", type="Boundary", input="Ban 2026-11-02 – 2026-11-05; entry on 2026-11-05 and on 2026-11-06", expected="`ACCESS_BANNED` with `ends_on` 2026-11-05; entered", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    at(clock, "2026-11-05", 10)
    assert err(scan(client, librarian, branch_a, "in", c), 409, "ACCESS_BANNED")["details"]["ends_on"] == "2026-11-05"
    at(clock, "2026-11-06", 10)
    enter(client, librarian, branch_a, c)
'''),
    dict(id="T-ACC-33-a", req="LIB-ACC-33", type="Error", input="Ban 2026-11-02 – 2026-11-05; a new ban 2026-11-05 – 2026-11-08; after lifting the first, again", expected="`409 BAN_OVERLAPS` with `details.ban_id`; 201", code='''
def TEST(client, librarian, branch_a):
    m, _ = holder(client, librarian, branch_a)
    b = ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    assert err(ban(client, librarian, m, starts_on="2026-11-05", ends_on="2026-11-08"), 409, "BAN_OVERLAPS")["details"]["ban_id"] == b["id"]
    ok(post(client, librarian, f"access-bans/{b['id']}/lift"))
    ok(ban(client, librarian, m, starts_on="2026-11-05", ends_on="2026-11-08"), 201)
'''),
    # ---------------------------------------------------------------- visits and effects
    dict(id="T-ACC-34-a", req="LIB-ACC-34", type="Normal", input="Visits: A Mon 09:00–09:45, B Tue 10:00–11:30; history; `branch_id` B; `from` Tue; another member reads it", expected="[B (90), A (45)]; [B]; [B]; `403`", code='''
def TEST(client, clock, librarian, branch_a, branch_b):
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    at(clock, MON, 9, 45); leave(client, librarian, branch_a, c)
    at(clock, TUE, 10); enter(client, librarian, branch_b, c)
    at(clock, TUE, 11, 30); leave(client, librarian, branch_b, c)
    h = mh(client, m)
    rows = items(get(client, h, f"members/{m['id']}/visits"))
    assert [(r["branch_id"], r["minutes"]) for r in rows] == [(branch_b["id"], 90), (branch_a["id"], 45)]
    assert [r["branch_id"] for r in items(get(client, h, f"members/{m['id']}/visits", branch_id=branch_b["id"]))] == [branch_b["id"]]
    assert [r["branch_id"] for r in items(get(client, h, f"members/{m['id']}/visits", **{"from": TUE}))] == [branch_b["id"]]
    assert client.get(f"/api/v1/members/{m['id']}/visits", headers=mh(client, member(client, librarian, branch_a))).status_code == 403
'''),
    dict(id="T-ACC-35-a", req="LIB-ACC-35", type="Error", input="Loan by card number; by a lost card; by an unknown card; with both `member_id` and `card_no`", expected="201 for the card's member; `409 CARD_NOT_ACTIVE`; `404`; `422`", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    cps = [add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"]) for _ in range(4)]
    assert ok(post(client, librarian, "loans", {"card_no": c["card_no"], "copy_id": cps[0]["id"]}), 201)["member_id"] == m["id"]
    _, lost = holder(client, librarian, branch_a)
    ok(report(client, librarian, lost))
    err(post(client, librarian, "loans", {"card_no": lost["card_no"], "copy_id": cps[1]["id"]}), 409, "CARD_NOT_ACTIVE")
    assert post(client, librarian, "loans", {"card_no": "LC99999999", "copy_id": cps[2]["id"]}).status_code == 404
    assert post(client, librarian, "loans", {"card_no": c["card_no"], "member_id": m["id"], "copy_id": cps[3]["id"]}).status_code == 422
'''),
    dict(id="T-ACC-36-a", req="LIB-ACC-36", type="Normal", input="A member inside A is deactivated", expected="Card `revoked` with `ended_on` today; not inside any more", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    deactivate_member(client, librarian, m["id"])
    out = cards_of(client, librarian, m)[0]
    assert (out["status"], out["ended_on"]) == ("revoked", MON)
    assert occupancy(client, librarian, branch_a)["inside"] == 0
'''),
    dict(id="T-ACC-37-a", req="LIB-ACC-37", type="Normal", input="A member with a card is deactivated and activated again; a new card issued", expected="No card after activation; the new card has no fee", code='''
def TEST(client, librarian, branch_a):
    m, _ = holder(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    ok(post(client, librarian, f"members/{m['id']}/activate"))
    assert [c["status"] for c in cards_of(client, librarian, m)] == ["revoked"]
    assert card(client, librarian, m)["fee_id"] is None
'''),
    dict(id="T-ACC-38-a", req="LIB-ACC-38", type="Normal", input="Member with a card inside A after one earlier visit this month; a member without a card", expected="`{card_no, card_status active, inside_branch_id A, visits_this_month 2}`; `{null, null, null, 0}`", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    at(clock, MON, 10); leave(client, librarian, branch_a, c)
    at(clock, MON, 11); enter(client, librarian, branch_a, c)
    assert get(client, librarian, f"members/{m['id']}/summary")["access"] == {"card_no": c["card_no"], "card_status": "active", "inside_branch_id": branch_a["id"], "visits_this_month": 2}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["access"] == {"card_no": None, "card_status": None, "inside_branch_id": None, "visits_this_month": 0}
'''),
    dict(id="T-ACC-39-a", req="LIB-ACC-39", type="Normal", input="A replacement fee of 25.00; balance; payment of 25.00", expected="`outstanding_fees` 25.00; after the payment the fee `paid`", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    ok(report(client, librarian, c))
    new = card(client, librarian, m)
    assert get(client, librarian, f"members/{m['id']}/balance")["outstanding_fees"] == "25.00"
    ok(post(client, librarian, f"members/{m['id']}/payments", {"amount": "25.00", "method": "cash"}), 201)
    assert fee_of(client, librarian, m, new["fee_id"])["status"] == "paid"
'''),
    dict(id="T-ACC-40-a", req="LIB-ACC-40", type="Error", input="Branch QQ (no copies, no members): a member of A inside QQ; after the exit an unused day pass of QQ; after cancelling it", expected="`BRANCH_IN_USE` twice; then 200", code='''
def TEST(client, admin, librarian, branch_a):
    qq = create_branch(client, admin, "QQ")
    _, c = holder(client, librarian, branch_a)
    enter(client, librarian, qq, c)
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    leave(client, librarian, qq, c)
    p = ok(sell(client, librarian, qq), 201)
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(post(client, librarian, f"day-passes/{p['id']}/cancel"))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
    dict(id="T-ACC-41-a", req="LIB-ACC-41", type="Normal", input="A member who is not inside the branch checks in to a room booking at A on Tue 10:00", expected="200 `checked_in`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r = ok(post(client, admin, "rooms", {"branch_id": branch_a["id"], "code": "ACC1", "name": "Sessiz Oda", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}), 201)
    m, _ = holder(client, librarian, branch_a)
    b = ok(post(client, librarian, "room-bookings", {"room_id": r["id"], "date": TUE, "start_time": "10:00", "end_time": "11:00", "member_id": m["id"]}), 201)
    at(clock, TUE, 10)
    assert ok(post(client, librarian, f"room-bookings/{b['id']}/check-in"))["status"] == "checked_in"
'''),
    dict(id="T-ACC-42-a", req="LIB-ACC-42", type="Normal", input="A member with a card enters and leaves twice", expected="No new notifications after the card was issued", code='''
def TEST(client, clock, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    before = len(items(get(client, librarian, f"members/{m['id']}/notifications")))
    for hh in (10, 12):
        at(clock, MON, hh); enter(client, librarian, branch_a, c)
        at(clock, MON, hh, 30); leave(client, librarian, branch_a, c)
    assert len(items(get(client, librarian, f"members/{m['id']}/notifications"))) == before
'''),
    dict(id="T-ACC-43-a", req="LIB-ACC-43", type="Normal", input="Card issued and reported; settings changed; entry and exit; a visit closed by hand; passes sold and cancelled; a ban created and lifted; process; a refused scan; audit log", expected="One entry per event (2 `card_issued`, 3 `access_scanned`, 2 `day_pass_sold`)", code='''
def TEST(client, admin, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    ok(report(client, librarian, c, "damaged"))
    c2 = card(client, librarian, m)
    ok(settings(client, admin, branch_a, capacity=50))
    enter(client, librarian, branch_a, c2)
    leave(client, librarian, branch_a, c2)
    v = enter(client, librarian, branch_a, c2)
    ok(post(client, librarian, f"visits/{v['visit_id']}/close"))
    ok(sell(client, librarian, branch_a), 201)
    p = ok(sell(client, librarian, branch_a), 201)
    ok(post(client, librarian, f"day-passes/{p['id']}/cancel"))
    b = ok(ban(client, librarian, m, starts_on="2026-11-20", ends_on="2026-11-22"), 201)
    ok(post(client, librarian, f"access-bans/{b['id']}/lift"))
    err(scan(client, librarian, branch_a, "in", c), 409, "CARD_NOT_ACTIVE")
    process(client, librarian)
    counts = {"card_issued": 2, "card_reported": 1, "access_settings_changed": 1, "access_scanned": 3, "visit_closed": 1, "day_pass_sold": 2,
              "day_pass_cancelled": 1, "access_ban_created": 1, "access_ban_lifted": 1, "access_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name
'''),
    dict(id="T-ACC-44-a", req="LIB-ACC-44", type="Normal", input="Branch A on Mon: M1 09:00–10:00, M2 09:30–11:00, M1 again 10:00–10:30, a day pass 12:00–12:30 (price 5.00) and an unused pass; one refused scan; report 2026-11-02 – 2026-11-08", expected="Row A `{visits 4, member_visits 3, unique_members 2, pass_visits 1, average_minutes 52.5, peak_occupancy 2, pass_revenue 10.00, denied 1}`", code='''
def TEST(client, clock, librarian, branch_a):
    _, c1 = holder(client, librarian, branch_a)
    _, c2 = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c1)
    at(clock, MON, 9, 30); enter(client, librarian, branch_a, c2)
    at(clock, MON, 10); leave(client, librarian, branch_a, c1); enter(client, librarian, branch_a, c1)
    err(scan(client, librarian, branch_a, "in", c1), 409, "ALREADY_INSIDE")
    at(clock, MON, 10, 30); leave(client, librarian, branch_a, c1)
    at(clock, MON, 11); leave(client, librarian, branch_a, c2)
    at(clock, MON, 12)
    p = ok(sell(client, librarian, branch_a), 201)
    ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=p))
    at(clock, MON, 12, 30); ok(scan(client, librarian, branch_a, "out", pass_=p))
    rows = items(get(client, librarian, "reports/visits", **{"from": MON, "to": "2026-11-08"}))
    keys = ("branch_id", "visits", "member_visits", "unique_members", "pass_visits", "average_minutes", "peak_occupancy", "pass_revenue", "denied")
    assert [tuple(r[k] for k in keys) for r in rows] == [(branch_a["id"], 4, 3, 2, 1, "52.5", 2, "10.00", 1)]
'''),
    dict(id="T-ACC-44-b", req="LIB-ACC-44", type="Error", input="`from` > `to`; 2026-01-01 – 2027-01-10; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/visits"
    assert client.get(url, headers=librarian, params={"from": TUE, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-10"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-ACC-45-a", req="LIB-ACC-45", type="Normal", input="Refused entry scans: a lost card and a full branch; audit log of `access_scanned`; report", expected="No audit entries; report `denied` 2", code='''
def TEST(client, admin, librarian, branch_a):
    _, lost = holder(client, librarian, branch_a)
    ok(report(client, librarian, lost))
    err(scan(client, librarian, branch_a, "in", lost), 409, "CARD_NOT_ACTIVE")
    ok(settings(client, admin, branch_a, capacity=1))
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    err(scan(client, librarian, branch_a, "in", holder(client, librarian, branch_a)[1]), 409, "BRANCH_FULL")
    assert len(items(get(client, admin, "audit-log", event="access_scanned"))) == 1
    rows = items(get(client, librarian, "reports/visits", **{"from": MON, "to": MON}))
    assert [r["denied"] for r in rows] == [2]
'''),
    dict(id="T-ACC-46-a", req="LIB-ACC-46", type="Boundary", input="Visits 09:00–10:00, 09:30–11:00 and 10:00–10:30 at A", expected="`peak_occupancy` 2", code='''
def TEST(client, clock, librarian, branch_a):
    cs = [holder(client, librarian, branch_a)[1] for _ in range(3)]
    enter(client, librarian, branch_a, cs[0])
    at(clock, MON, 9, 30); enter(client, librarian, branch_a, cs[1])
    at(clock, MON, 10); leave(client, librarian, branch_a, cs[0]); enter(client, librarian, branch_a, cs[2])
    at(clock, MON, 10, 30); leave(client, librarian, branch_a, cs[2])
    at(clock, MON, 11); leave(client, librarian, branch_a, cs[1])
    assert items(get(client, librarian, "reports/visits", **{"from": MON, "to": MON}))[0]["peak_occupancy"] == 2
'''),
    dict(id="T-ACC-47-a", req="LIB-ACC-47", type="Normal", input="Cards, a visit and a pass exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    _, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(sell(client, librarian, branch_a), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
    dict(id="T-ACC-48-a", req="LIB-ACC-48", type="Normal", input="A member reads `members/me` with an active card; after reporting it lost", expected="`card_no` the number; then null", code='''
def TEST(client, librarian, branch_a):
    m, c = holder(client, librarian, branch_a)
    h = mh(client, m)
    assert get(client, h, "members/me")["card_no"] == c["card_no"]
    ok(report(client, h, c))
    assert get(client, h, "members/me")["card_no"] is None
'''),
    dict(id="T-ACC-49-a", req="LIB-ACC-49", type="Boundary", input="Capacity 1 with a day pass visitor inside; another pass is used", expected="`409 BRANCH_FULL`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(settings(client, admin, branch_a, capacity=1))
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    err(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)), 409, "BRANCH_FULL")
'''),
    dict(id="T-ACC-50-a", req="LIB-ACC-50", type="Normal", input="`guest_entry` false at A; a student inside A becomes a guest; leaves; enters again", expected="Still inside after the change; leaving 200; entry `GUEST_ENTRY_NOT_ALLOWED`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(settings(client, admin, branch_a, guest_entry=False))
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "+905551112233", "university_id": None}))
    assert occupancy(client, librarian, branch_a)["inside"] == 1
    leave(client, librarian, branch_a, c)
    err(scan(client, librarian, branch_a, "in", c), 409, "GUEST_ENTRY_NOT_ALLOWED")
'''),
    dict(id="T-ACC-51-a", req="LIB-ACC-51", type="Normal", input="Capacity 2 with a member and a day pass visitor inside; a member enters; after one exit, again", expected="`BRANCH_FULL` with `details.capacity` 2; entered", code='''
def TEST(client, admin, librarian, branch_a):
    ok(settings(client, admin, branch_a, capacity=2))
    _, c1 = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c1)
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    _, c2 = holder(client, librarian, branch_a)
    assert err(scan(client, librarian, branch_a, "in", c2), 409, "BRANCH_FULL")["details"]["capacity"] == 2
    leave(client, librarian, branch_a, c1)
    enter(client, librarian, branch_a, c2)
'''),
    dict(id="T-ACC-52-a", req="LIB-ACC-52", type="Normal", input="Closure of A on Tue (created Mon); a member inside since Mon 19:00; entry on Tue 10:00; process on Tue 10:00", expected="Entry `BRANCH_NOT_OPEN`; the Monday visit is closed with `left_at` Mon 20:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    m, c = holder(client, librarian, branch_a)
    _, c2 = holder(client, librarian, branch_a)
    at(clock, MON, 19); enter(client, librarian, branch_a, c)
    at(clock, TUE, 10)
    err(scan(client, librarian, branch_a, "in", c2), 409, "BRANCH_NOT_OPEN")
    assert process(client, librarian)["visits_closed"] == 1
    assert same(items(get(client, librarian, f"members/{m['id']}/visits"))[0]["left_at"], MON, 20)
'''),
]
