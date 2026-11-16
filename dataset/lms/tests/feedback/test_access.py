"""Feedback tests: module 28 (Member cards and building access). Generated from cases/access.md."""
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


def test_t_acc_01_a(client, librarian, branch_a):
    """T-ACC-01-a (LIB-ACC-01): 201 LC00000001, active, issued_on Mon, expires_on 2027-11-01, no fee; one card_issued notification with the number"""
    m = member(client, librarian, branch_a)
    c = card(client, librarian, m)
    assert (c["card_no"], c["member_id"], c["status"], c["issued_on"], c["expires_on"], c["replaces_id"], c["fee_id"]) == ("LC00000001", m["id"], "active", MON, "2027-11-01", None, None)
    ns = notes(client, librarian, m["id"], "card_issued")
    assert len(ns) == 1 and "LC00000001" in ns[0]["message"] and ns[0]["card_id"] == c["id"]


def test_t_acc_03_a(client, librarian, branch_a):
    """T-ACC-03-a (LIB-ACC-03): New card with replaces_id of the old one and fee_id of an open card_replacement fee of 25.00 with card_id"""
    m, old = holder(client, librarian, branch_a)
    ok(report(client, librarian, old))
    new = card(client, librarian, m)
    assert new["replaces_id"] == old["id"] and new["fee_id"] is not None
    f = fee_of(client, librarian, m, new["fee_id"])
    assert (f["kind"], f["amount"], f["status"], f["card_id"]) == ("card_replacement", "25.00", "open", new["id"])


def test_t_acc_04_a(client, librarian, branch_a):
    """T-ACC-04-a (LIB-ACC-04): Fees none, 25.00, 10.00, 50.00"""
    m, c = holder(client, librarian, branch_a)
    amounts = [c["fee_id"]]
    for reason in ("lost", "damaged", "lost"):
        ok(report(client, librarian, c, reason))
        c = card(client, librarian, m)
        amounts.append(fee_of(client, librarian, m, c["fee_id"])["amount"])
    assert amounts == [None, "25.00", "10.00", "50.00"]


def test_t_acc_05_a(client, librarian, branch_a):
    """T-ACC-05-a (LIB-ACC-05): 200 damaged with ended_on Mon; 409 CARD_NOT_ACTIVE with details.status damaged; 403"""
    m, c = holder(client, librarian, branch_a)
    _, other = holder(client, librarian, branch_a)
    h = mh(client, m)
    out = ok(report(client, h, c, "damaged"))
    assert (out["status"], out["ended_on"]) == ("damaged", MON)
    assert err(report(client, h, c), 409, "CARD_NOT_ACTIVE")["details"]["status"] == "damaged"
    assert report(client, h, other).status_code == 403


def test_t_acc_07_a(client, librarian, branch_a):
    """T-ACC-07-a (LIB-ACC-07): The active card's expires_on becomes 2028-10-31"""
    m, c = holder(client, librarian, branch_a)
    out = ok(post(client, librarian, f"members/{m['id']}/renew-membership"))
    assert cards_of(client, librarian, m)[0]["expires_on"] == out["valid_until"] == "2028-10-31"


def test_t_acc_09_a(client, clock, librarian, branch_a):
    """T-ACC-09-a (LIB-ACC-09): cards_expired 0 then 1"""
    holder(client, librarian, branch_a)
    at(clock, "2027-11-01", 23, 59)
    assert process(client, librarian)["cards_expired"] == 0
    at(clock, "2027-11-02", 0, 0)
    assert process(client, librarian)["cards_expired"] == 1


def test_t_acc_11_a(client, admin, librarian, branch_a):
    """T-ACC-11-a (LIB-ACC-11): 409 CAPACITY_BELOW_OCCUPANCY with details.occupancy 2; 200"""
    for _ in range(2):
        enter(client, librarian, branch_a, holder(client, librarian, branch_a)[1])
    assert err(settings(client, admin, branch_a, capacity=1), 409, "CAPACITY_BELOW_OCCUPANCY")["details"]["occupancy"] == 2
    ok(settings(client, admin, branch_a, capacity=2))


def test_t_acc_13_a(client, clock, librarian, branch_a):
    """T-ACC-13-a (LIB-ACC-13): Two rows in order (member with name, pass with code); 403"""
    m, c = holder(client, librarian, branch_a)
    v1 = enter(client, librarian, branch_a, c)
    at(clock, MON, 9, 30)
    p = ok(sell(client, librarian, branch_a), 201)
    v2 = ok(scan(client, librarian, branch_a, pass_=p))
    rows = items(get(client, librarian, f"branches/{branch_a['id']}/inside"))
    assert [(r["visit_id"], r["member_id"], r["full_name"], r["day_pass_code"]) for r in rows] == [(v1["visit_id"], m["id"], m["full_name"], None), (v2["visit_id"], None, None, p["code"])]
    assert client.get(f"/api/v1/branches/{branch_a['id']}/inside", headers=mh(client, m)).status_code == 403


def test_t_acc_15_a(client, clock, admin, librarian, branch_a):
    """T-ACC-15-a (LIB-ACC-15): CARD_NOT_ACTIVE with details.status lost; MEMBERSHIP_EXPIRED; BRANCH_INACTIVE; BRANCH_NOT_OPEN"""
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


def test_t_acc_17_a(client, librarian, branch_a, branch_b):
    """T-ACC-17-a (LIB-ACC-17): NOT_INSIDE; WRONG_BRANCH with details.branch_id A; 200 left"""
    _, c = holder(client, librarian, branch_a)
    err(scan(client, librarian, branch_a, "out", c), 409, "NOT_INSIDE")
    enter(client, librarian, branch_a, c)
    assert err(scan(client, librarian, branch_b, "out", c), 409, "WRONG_BRANCH")["details"]["branch_id"] == branch_a["id"]
    ok(report(client, librarian, c))
    assert leave(client, librarian, branch_a, c)["result"] == "left"


def test_t_acc_19_a(client, clock, librarian, branch_a, branch_b):
    """T-ACC-19-a (LIB-ACC-19): WRONG_BRANCH; entered (pass used); PASS_NOT_USABLE with details.status used; left; PASS_NOT_VALID_TODAY"""
    p = ok(sell(client, librarian, branch_a), 201)
    q = ok(sell(client, librarian, branch_a), 201)
    err(scan(client, librarian, branch_b, pass_=p), 409, "WRONG_BRANCH")
    out = ok(scan(client, librarian, branch_a, pass_=p))
    assert (out["result"], out["day_pass_id"], out["member_id"]) == ("entered", p["id"], None)
    assert err(scan(client, librarian, branch_a, pass_=p), 409, "PASS_NOT_USABLE")["details"]["status"] == "used"
    assert ok(scan(client, librarian, branch_a, "out", pass_=p))["result"] == "left"
    at(clock, TUE)
    err(scan(client, librarian, branch_a, pass_=q), 409, "PASS_NOT_VALID_TODAY")


def test_t_acc_21_a(client, clock, librarian, branch_a):
    """T-ACC-21-a (LIB-ACC-21): One alert {card_no, branch_id} at 10:00; one lost_card_used notification"""
    m, c = holder(client, librarian, branch_a)
    ok(report(client, librarian, c))
    at(clock, MON, 10)
    err(scan(client, librarian, branch_a, "in", c), 409, "CARD_NOT_ACTIVE")
    rows = items(get(client, librarian, "access/alerts"))
    assert [(r["card_no"], r["branch_id"]) for r in rows] == [(c["card_no"], branch_a["id"])] and same(rows[0]["at"], MON, 10)
    assert len(notes(client, librarian, m["id"], "lost_card_used")) == 1


def test_t_acc_23_a(client, clock, librarian, branch_a):
    """T-ACC-23-a (LIB-ACC-23): visits_closed 0; then 1 with left_at 20:00 (minutes 30)"""
    m, c = holder(client, librarian, branch_a)
    at(clock, MON, 19, 30)
    enter(client, librarian, branch_a, c)
    at(clock, MON, 19, 59)
    assert process(client, librarian)["visits_closed"] == 0
    at(clock, MON, 20, 30)
    assert process(client, librarian)["visits_closed"] == 1
    v = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
    assert same(v["left_at"], MON, 20) and v["minutes"] == 30


def test_t_acc_25_a(client, admin, librarian, branch_a, branch_b):
    """T-ACC-25-a (LIB-ACC-25): 201 unused for today at 7.50; DAY_PASSES_DISABLED; BRANCH_INACTIVE"""
    ok(settings(client, admin, branch_a, day_pass_price="7.50"))
    p = ok(sell(client, librarian, branch_a, "Deniz Kaya"), 201)
    assert (p["branch_id"], p["visitor_name"], p["valid_on"], p["price"], p["status"]) == (branch_a["id"], "Deniz Kaya", MON, "7.50", "unused")
    ok(settings(client, admin, branch_b, day_passes=False))
    err(sell(client, librarian, branch_b), 409, "DAY_PASSES_DISABLED")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(sell(client, librarian, qq), 409, "BRANCH_INACTIVE")


def test_t_acc_27_a(client, librarian, branch_a):
    """T-ACC-27-a (LIB-ACC-27): 200 cancelled; 409 PASS_NOT_USABLE twice"""
    p = ok(sell(client, librarian, branch_a), 201)
    assert ok(post(client, librarian, f"day-passes/{p['id']}/cancel"))["status"] == "cancelled"
    err(post(client, librarian, f"day-passes/{p['id']}/cancel"), 409, "PASS_NOT_USABLE")
    u = ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=u))
    err(post(client, librarian, f"day-passes/{u['id']}/cancel"), 409, "PASS_NOT_USABLE")


def test_t_acc_29_a(client, librarian, branch_a):
    """T-ACC-29-a (LIB-ACC-29): 201; the visit ended (inside 0); one access_banned notification naming 2026-11-10; 422 twice"""
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


def test_t_acc_31_a(client, librarian, branch_a):
    """T-ACC-31-a (LIB-ACC-31): [future (in_force false), current (in_force false)]"""
    m, _ = holder(client, librarian, branch_a)
    cur = ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    ok(post(client, librarian, f"access-bans/{cur['id']}/lift"))
    fut = ok(ban(client, librarian, m, starts_on="2026-11-20", ends_on="2026-11-25"), 201)
    rows = items(get(client, mh(client, m), f"members/{m['id']}/access-bans"))
    assert [(r["id"], r["in_force"]) for r in rows] == [(fut["id"], False), (cur["id"], False)]


def test_t_acc_33_a(client, librarian, branch_a):
    """T-ACC-33-a (LIB-ACC-33): 409 BAN_OVERLAPS with details.ban_id; 201"""
    m, _ = holder(client, librarian, branch_a)
    b = ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    assert err(ban(client, librarian, m, starts_on="2026-11-05", ends_on="2026-11-08"), 409, "BAN_OVERLAPS")["details"]["ban_id"] == b["id"]
    ok(post(client, librarian, f"access-bans/{b['id']}/lift"))
    ok(ban(client, librarian, m, starts_on="2026-11-05", ends_on="2026-11-08"), 201)


def test_t_acc_35_a(client, librarian, branch_a):
    """T-ACC-35-a (LIB-ACC-35): 201 for the card's member; 409 CARD_NOT_ACTIVE; 404; 422"""
    m, c = holder(client, librarian, branch_a)
    cps = [add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"]) for _ in range(4)]
    assert ok(post(client, librarian, "loans", {"card_no": c["card_no"], "copy_id": cps[0]["id"]}), 201)["member_id"] == m["id"]
    _, lost = holder(client, librarian, branch_a)
    ok(report(client, librarian, lost))
    err(post(client, librarian, "loans", {"card_no": lost["card_no"], "copy_id": cps[1]["id"]}), 409, "CARD_NOT_ACTIVE")
    assert post(client, librarian, "loans", {"card_no": "LC99999999", "copy_id": cps[2]["id"]}).status_code == 404
    assert post(client, librarian, "loans", {"card_no": c["card_no"], "member_id": m["id"], "copy_id": cps[3]["id"]}).status_code == 422


def test_t_acc_37_a(client, librarian, branch_a):
    """T-ACC-37-a (LIB-ACC-37): No card after activation; the new card has no fee"""
    m, _ = holder(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    ok(post(client, librarian, f"members/{m['id']}/activate"))
    assert [c["status"] for c in cards_of(client, librarian, m)] == ["revoked"]
    assert card(client, librarian, m)["fee_id"] is None


def test_t_acc_39_a(client, librarian, branch_a):
    """T-ACC-39-a (LIB-ACC-39): outstanding_fees 25.00; after the payment the fee paid"""
    m, c = holder(client, librarian, branch_a)
    ok(report(client, librarian, c))
    new = card(client, librarian, m)
    assert get(client, librarian, f"members/{m['id']}/balance")["outstanding_fees"] == "25.00"
    ok(post(client, librarian, f"members/{m['id']}/payments", {"amount": "25.00", "method": "cash"}), 201)
    assert fee_of(client, librarian, m, new["fee_id"])["status"] == "paid"


def test_t_acc_41_a(client, clock, admin, librarian, branch_a):
    """T-ACC-41-a (LIB-ACC-41): 200 checked_in"""
    r = ok(post(client, admin, "rooms", {"branch_id": branch_a["id"], "code": "ACC1", "name": "Sessiz Oda", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}), 201)
    m, _ = holder(client, librarian, branch_a)
    b = ok(post(client, librarian, "room-bookings", {"room_id": r["id"], "date": TUE, "start_time": "10:00", "end_time": "11:00", "member_id": m["id"]}), 201)
    at(clock, TUE, 10)
    assert ok(post(client, librarian, f"room-bookings/{b['id']}/check-in"))["status"] == "checked_in"


def test_t_acc_43_a(client, admin, librarian, branch_a):
    """T-ACC-43-a (LIB-ACC-43): One entry per event (2 card_issued, 3 access_scanned, 2 day_pass_sold)"""
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


def test_t_acc_44_a(client, clock, librarian, branch_a):
    """T-ACC-44-a (LIB-ACC-44): Row A {visits 4, member_visits 3, unique_members 2, pass_visits 1, average_minutes 52.5, peak_occupancy 2, pass_revenue 10.00, denied 1}"""
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


def test_t_acc_45_a(client, admin, librarian, branch_a):
    """T-ACC-45-a (LIB-ACC-45): No audit entries; report denied 2"""
    _, lost = holder(client, librarian, branch_a)
    ok(report(client, librarian, lost))
    err(scan(client, librarian, branch_a, "in", lost), 409, "CARD_NOT_ACTIVE")
    ok(settings(client, admin, branch_a, capacity=1))
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    err(scan(client, librarian, branch_a, "in", holder(client, librarian, branch_a)[1]), 409, "BRANCH_FULL")
    assert len(items(get(client, admin, "audit-log", event="access_scanned"))) == 1
    rows = items(get(client, librarian, "reports/visits", **{"from": MON, "to": MON}))
    assert [r["denied"] for r in rows] == [2]


def test_t_acc_47_a(client, admin, librarian, branch_a):
    """T-ACC-47-a (LIB-ACC-47): The export has exactly the keys of 22.1"""
    _, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(sell(client, librarian, branch_a), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}


def test_t_acc_49_a(client, admin, librarian, branch_a):
    """T-ACC-49-a (LIB-ACC-49): 409 BRANCH_FULL"""
    ok(settings(client, admin, branch_a, capacity=1))
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    err(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)), 409, "BRANCH_FULL")


def test_t_acc_51_a(client, admin, librarian, branch_a):
    """T-ACC-51-a (LIB-ACC-51): BRANCH_FULL with details.capacity 2; entered"""
    ok(settings(client, admin, branch_a, capacity=2))
    _, c1 = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c1)
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    _, c2 = holder(client, librarian, branch_a)
    assert err(scan(client, librarian, branch_a, "in", c2), 409, "BRANCH_FULL")["details"]["capacity"] == 2
    leave(client, librarian, branch_a, c1)
    enter(client, librarian, branch_a, c2)
