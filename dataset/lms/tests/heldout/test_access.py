"""Heldout tests: module 28 (Member cards and building access). Generated from cases/access.md."""
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


def test_t_acc_02_a(client, clock, librarian, branch_a):
    """T-ACC-02-a (LIB-ACC-02): MEMBER_PASSIVE; MEMBERSHIP_EXPIRED; CARD_ALREADY_ACTIVE with details.card_no; 403"""
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(issue(client, librarian, p), 409, "MEMBER_PASSIVE")
    m, c = holder(client, librarian, branch_a)
    assert err(issue(client, librarian, m), 409, "CARD_ALREADY_ACTIVE")["details"]["card_no"] == c["card_no"]
    assert issue(client, mh(client, m), member(client, librarian, branch_a)).status_code == 403
    late = member(client, librarian, branch_a)
    at(clock, "2027-11-02")
    err(issue(client, librarian, late), 409, "MEMBERSHIP_EXPIRED")


def test_t_acc_04_b(client, clock, librarian, branch_a):
    """T-ACC-04-b (LIB-ACC-04): No fee"""
    m, old = holder(client, librarian, branch_a)
    at(clock, "2027-11-02")
    process(client, librarian)
    ok(post(client, librarian, f"members/{m['id']}/renew-membership"))
    assert card(client, librarian, m)["fee_id"] is None


def test_t_acc_06_a(client, librarian, branch_a):
    """T-ACC-06-a (LIB-ACC-06): [new, old]; card with member {id, member_no, full_name, membership_type, status}; 404"""
    m, old = holder(client, librarian, branch_a)
    ok(report(client, librarian, old))
    new = card(client, librarian, m)
    assert [c["id"] for c in cards_of(client, mh(client, m), m)] == [new["id"], old["id"]]
    out = get(client, librarian, f"cards/{new['card_no']}")
    assert out["member"] == {"id": m["id"], "member_no": m["member_no"], "full_name": m["full_name"], "membership_type": "student", "status": "active"}
    assert client.get("/api/v1/cards/LC99999999", headers=librarian).status_code == 404


def test_t_acc_08_a(client, clock, librarian, branch_a):
    """T-ACC-08-a (LIB-ACC-08): cards_expired 2; both expired with ended_on 2027-11-02"""
    m1, _ = holder(client, librarian, branch_a)
    m2, _ = holder(client, librarian, branch_a)
    at(clock, "2027-11-02")
    assert process(client, librarian)["cards_expired"] == 2
    assert [(c["status"], c["ended_on"]) for m in (m1, m2) for c in cards_of(client, librarian, m)] == [("expired", "2027-11-02")] * 2


def test_t_acc_10_a(client, admin, librarian, branch_a):
    """T-ACC-10-a (LIB-ACC-10): {capacity null, guest_entry true, day_passes true, day_pass_price 5.00}; 200 with the new values; 422; 422; 404; 403"""
    d = get(client, librarian, f"access-settings/{branch_a['id']}")
    assert (d["capacity"], d["guest_entry"], d["day_passes"], d["day_pass_price"]) == (None, True, True, "5.00")
    out = ok(settings(client, admin, branch_a, capacity=100, day_pass_price="7.50"))
    assert (out["capacity"], out["day_pass_price"], out["guest_entry"]) == (100, "7.50", True)
    assert settings(client, admin, branch_a, capacity=0).status_code == 422
    assert settings(client, admin, branch_a, day_pass_price="100.01").status_code == 422
    assert settings(client, admin, {"id": 999999}, capacity=5).status_code == 404
    assert settings(client, librarian, branch_a, capacity=5).status_code == 403


def test_t_acc_12_a(client, admin, librarian, branch_a):
    """T-ACC-12-a (LIB-ACC-12): {inside 2, members 1, visitors 1, capacity 10, free 8}"""
    ok(settings(client, admin, branch_a, capacity=10))
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(scan(client, librarian, branch_a, pass_=ok(sell(client, librarian, branch_a), 201)))
    out = occupancy(client, mh(client, m), branch_a)
    assert {k: out[k] for k in ("branch_id", "inside", "members", "visitors", "capacity", "free")} == {"branch_id": branch_a["id"], "inside": 2, "members": 1, "visitors": 1, "capacity": 10, "free": 8}


def test_t_acc_14_a(client, librarian, branch_a):
    """T-ACC-14-a (LIB-ACC-14): 200 {result entered, visit_id, member_id}; 422 three times; 404; 403"""
    m, c = holder(client, librarian, branch_a)
    out = enter(client, librarian, branch_a, c)
    assert (out["result"], out["member_id"], out["day_pass_id"]) == ("entered", m["id"], None) and out["visit_id"] is not None
    p = ok(sell(client, librarian, branch_a), 201)
    assert scan(client, librarian, branch_a, "in", c, p).status_code == 422
    assert scan(client, librarian, branch_a, "in").status_code == 422
    assert post(client, librarian, "access/scan", {"branch_id": branch_a["id"], "direction": "sideways", "card_no": c["card_no"]}).status_code == 422
    assert scan(client, librarian, branch_a, "in", {"card_no": "LC99999999"}).status_code == 404
    assert scan(client, mh(client, m), branch_a, "out", c).status_code == 403


def test_t_acc_15_b(client, admin, librarian, branch_a, branch_b):
    """T-ACC-15-b (LIB-ACC-15): ACCESS_BANNED with details.ends_on; GUEST_ENTRY_NOT_ALLOWED; ALREADY_INSIDE with details.branch_id B; BRANCH_FULL with details.capacity 1"""
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


def test_t_acc_16_a(client, librarian, branch_a):
    """T-ACC-16-a (LIB-ACC-16): The visit history shows the visit with entered_at 09:00, left_at null, minutes null"""
    m, c = holder(client, librarian, branch_a)
    v = enter(client, librarian, branch_a, c)
    rows = items(get(client, librarian, f"members/{m['id']}/visits"))
    assert [(r["id"], r["branch_id"], r["left_at"], r["minutes"]) for r in rows] == [(v["visit_id"], branch_a["id"], None, None)] and same(rows[0]["entered_at"], MON, 9)


def test_t_acc_18_a(client, clock, librarian, branch_a):
    """T-ACC-18-a (LIB-ACC-18): BRANCH_NOT_OPEN; entered; ALREADY_INSIDE; left with minutes 60"""
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


def test_t_acc_20_a(client, librarian, branch_a):
    """T-ACC-20-a (LIB-ACC-20): 200 (closed_by staff; the member is no longer inside); 409 VISIT_NOT_OPEN"""
    m, c = holder(client, librarian, branch_a)
    v = enter(client, librarian, branch_a, c)
    ok(post(client, librarian, f"visits/{v['visit_id']}/close"))
    assert occupancy(client, librarian, branch_a)["inside"] == 0
    row = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
    assert (row["id"], row["closed_by"]) == (v["visit_id"], "staff") and same(row["left_at"], MON, 9)
    err(post(client, librarian, f"visits/{v['visit_id']}/close"), 409, "VISIT_NOT_OPEN")


def test_t_acc_22_a(client, clock, librarian, branch_a):
    """T-ACC-22-a (LIB-ACC-22): visits_closed 2 with left_at Mon 20:00 and closed_by closing"""
    m1, c1 = holder(client, librarian, branch_a)
    m2, c2 = holder(client, librarian, branch_a)
    at(clock, MON, 10); enter(client, librarian, branch_a, c1)
    at(clock, MON, 15); enter(client, librarian, branch_a, c2)
    at(clock, MON, 21)
    assert process(client, librarian)["visits_closed"] == 2
    for m in (m1, m2):
        v = items(get(client, librarian, f"members/{m['id']}/visits"))[0]
        assert same(v["left_at"], MON, 20)


def test_t_acc_24_a(client, clock, librarian, branch_a):
    """T-ACC-24-a (LIB-ACC-24): {visits_closed 1, cards_expired 0, passes_expired 1}; the unused pass cancelled"""
    unused = ok(sell(client, librarian, branch_a), 201)
    used = ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=used))
    at(clock, TUE, 7)
    out = process(client, librarian)
    assert (out["visits_closed"], out["cards_expired"], out["passes_expired"]) == (1, 0, 1)
    rows = {p["id"]: p["status"] for p in items(get(client, librarian, "day-passes"))}
    assert (rows[unused["id"]], rows[used["id"]]) == ("cancelled", "used")


def test_t_acc_25_b(client, librarian, branch_a, branch_b):
    """T-ACC-25-b (LIB-ACC-25): DAY_PASS_LIMIT_REACHED with details.limit 50; B 201"""
    first = ok(sell(client, librarian, branch_a), 201)
    for _ in range(49):
        ok(sell(client, librarian, branch_a), 201)
    ok(post(client, librarian, f"day-passes/{first['id']}/cancel"))
    assert err(sell(client, librarian, branch_a), 409, "DAY_PASS_LIMIT_REACHED")["details"]["limit"] == 50
    ok(sell(client, librarian, branch_b), 201)


def test_t_acc_26_a(client, librarian, branch_a, branch_b):
    """T-ACC-26-a (LIB-ACC-26): Codes DP-AA-20261102-1 … -3; DP-BB-20261102-1"""
    codes = [ok(sell(client, librarian, branch_a), 201)["code"] for _ in range(3)]
    assert codes == ["DP-AA-20261102-1", "DP-AA-20261102-2", "DP-AA-20261102-3"]
    assert ok(sell(client, librarian, branch_b), 201)["code"] == "DP-BB-20261102-1"


def test_t_acc_28_a(client, librarian, branch_a, branch_b):
    """T-ACC-28-a (LIB-ACC-28): [P3, P2, P1]; [P3, P1]; [P3]"""
    p1, p2, p3 = ok(sell(client, librarian, branch_a), 201), ok(sell(client, librarian, branch_b), 201), ok(sell(client, librarian, branch_a), 201)
    ok(scan(client, librarian, branch_a, pass_=p3))
    ids = lambda **f: [p["id"] for p in items(get(client, librarian, "day-passes", **f))]
    assert ids() == [p3["id"], p2["id"], p1["id"]]
    assert ids(branch_id=branch_a["id"]) == [p3["id"], p1["id"]]
    assert ids(status="used") == [p3["id"]]


def test_t_acc_30_a(client, librarian, branch_a):
    """T-ACC-30-a (LIB-ACC-30): 200 with lifted_at; 409 BAN_ALREADY_LIFTED; entered"""
    m, c = holder(client, librarian, branch_a)
    b = ok(ban(client, librarian, m, ends_on="2026-11-10"), 201)
    out = ok(post(client, librarian, f"access-bans/{b['id']}/lift"))
    assert same(out["lifted_at"], MON, 9)
    err(post(client, librarian, f"access-bans/{b['id']}/lift"), 409, "BAN_ALREADY_LIFTED")
    enter(client, librarian, branch_a, c)


def test_t_acc_32_a(client, clock, librarian, branch_a):
    """T-ACC-32-a (LIB-ACC-32): ACCESS_BANNED with ends_on 2026-11-05; entered"""
    m, c = holder(client, librarian, branch_a)
    ok(ban(client, librarian, m, ends_on="2026-11-05"), 201)
    at(clock, "2026-11-05", 10)
    assert err(scan(client, librarian, branch_a, "in", c), 409, "ACCESS_BANNED")["details"]["ends_on"] == "2026-11-05"
    at(clock, "2026-11-06", 10)
    enter(client, librarian, branch_a, c)


def test_t_acc_34_a(client, clock, librarian, branch_a, branch_b):
    """T-ACC-34-a (LIB-ACC-34): [B (90), A (45)]; [B]; [B]; 403"""
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


def test_t_acc_36_a(client, librarian, branch_a):
    """T-ACC-36-a (LIB-ACC-36): Card revoked with ended_on today; not inside any more"""
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    deactivate_member(client, librarian, m["id"])
    out = cards_of(client, librarian, m)[0]
    assert (out["status"], out["ended_on"]) == ("revoked", MON)
    assert occupancy(client, librarian, branch_a)["inside"] == 0


def test_t_acc_38_a(client, clock, librarian, branch_a):
    """T-ACC-38-a (LIB-ACC-38): {card_no, card_status active, inside_branch_id A, visits_this_month 2}; {null, null, null, 0}"""
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    at(clock, MON, 10); leave(client, librarian, branch_a, c)
    at(clock, MON, 11); enter(client, librarian, branch_a, c)
    assert get(client, librarian, f"members/{m['id']}/summary")["access"] == {"card_no": c["card_no"], "card_status": "active", "inside_branch_id": branch_a["id"], "visits_this_month": 2}
    other = member(client, librarian, branch_a)
    assert get(client, librarian, f"members/{other['id']}/summary")["access"] == {"card_no": None, "card_status": None, "inside_branch_id": None, "visits_this_month": 0}


def test_t_acc_40_a(client, admin, librarian, branch_a):
    """T-ACC-40-a (LIB-ACC-40): BRANCH_IN_USE twice; then 200"""
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


def test_t_acc_42_a(client, clock, librarian, branch_a):
    """T-ACC-42-a (LIB-ACC-42): No new notifications after the card was issued"""
    m, c = holder(client, librarian, branch_a)
    before = len(items(get(client, librarian, f"members/{m['id']}/notifications")))
    for hh in (10, 12):
        at(clock, MON, hh); enter(client, librarian, branch_a, c)
        at(clock, MON, hh, 30); leave(client, librarian, branch_a, c)
    assert len(items(get(client, librarian, f"members/{m['id']}/notifications"))) == before


def test_t_acc_44_b(client, librarian, branch_a):
    """T-ACC-44-b (LIB-ACC-44): 422; 422; 403"""
    url = "/api/v1/reports/visits"
    assert client.get(url, headers=librarian, params={"from": TUE, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-10"}).status_code == 422
    assert client.get(url, headers=mh(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_acc_46_a(client, clock, librarian, branch_a):
    """T-ACC-46-a (LIB-ACC-46): peak_occupancy 2"""
    cs = [holder(client, librarian, branch_a)[1] for _ in range(3)]
    enter(client, librarian, branch_a, cs[0])
    at(clock, MON, 9, 30); enter(client, librarian, branch_a, cs[1])
    at(clock, MON, 10); leave(client, librarian, branch_a, cs[0]); enter(client, librarian, branch_a, cs[2])
    at(clock, MON, 10, 30); leave(client, librarian, branch_a, cs[2])
    at(clock, MON, 11); leave(client, librarian, branch_a, cs[1])
    assert items(get(client, librarian, "reports/visits", **{"from": MON, "to": MON}))[0]["peak_occupancy"] == 2


def test_t_acc_48_a(client, librarian, branch_a):
    """T-ACC-48-a (LIB-ACC-48): card_no the number; then null"""
    m, c = holder(client, librarian, branch_a)
    h = mh(client, m)
    assert get(client, h, "members/me")["card_no"] == c["card_no"]
    ok(report(client, h, c))
    assert get(client, h, "members/me")["card_no"] is None


def test_t_acc_50_a(client, admin, librarian, branch_a):
    """T-ACC-50-a (LIB-ACC-50): Still inside after the change; leaving 200; entry GUEST_ENTRY_NOT_ALLOWED"""
    ok(settings(client, admin, branch_a, guest_entry=False))
    m, c = holder(client, librarian, branch_a)
    enter(client, librarian, branch_a, c)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "+905551112233", "university_id": None}))
    assert occupancy(client, librarian, branch_a)["inside"] == 1
    leave(client, librarian, branch_a, c)
    err(scan(client, librarian, branch_a, "in", c), 409, "GUEST_ENTRY_NOT_ALLOWED")


def test_t_acc_52_a(client, clock, admin, librarian, branch_a):
    """T-ACC-52-a (LIB-ACC-52): Entry BRANCH_NOT_OPEN; the Monday visit is closed with left_at Mon 20:00"""
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    m, c = holder(client, librarian, branch_a)
    _, c2 = holder(client, librarian, branch_a)
    at(clock, MON, 19); enter(client, librarian, branch_a, c)
    at(clock, TUE, 10)
    err(scan(client, librarian, branch_a, "in", c2), 409, "BRANCH_NOT_OPEN")
    assert process(client, librarian)["visits_closed"] == 1
    assert same(items(get(client, librarian, f"members/{m['id']}/visits"))[0]["left_at"], MON, 20)
