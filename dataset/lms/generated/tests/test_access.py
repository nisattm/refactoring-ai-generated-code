"""Module 28: Member cards and building access (LIB-ACC-01 to LIB-ACC-52).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), students 1 to 3.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
import lms.access.models
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_loans import API, at, lend, lib, mk_book, mk_member, member_h, new_copy, ret  # noqa: F401

TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def go(clock, y, m, d, hh=9, mm=0):
    clock.set(datetime.datetime(y, m, d, hh, mm, tzinfo=TZ))


def issue(client, hd, member=1, expect=201):
    r = client.post(f"{API}/members/{member}/cards", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


def report(client, hd, card_no, reason="lost", expect=200):
    r = client.post(f"{API}/cards/{card_no}/report", headers=hd, json={"reason": reason})
    assert r.status_code == expect, r.text
    return r.json()


def scan(client, hd, direction="in", branch=1, expect=200, **who):
    r = client.post(f"{API}/access/scan", headers=hd, json={"branch_id": branch, "direction": direction, **who})
    assert r.status_code == expect, r.text
    return r.json()


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notes(app, type_):
    return sel(app, sa.select(Notification).where(Notification.type == type_).order_by(Notification.id))


def sell(client, hd, branch=1, name="Visitor", expect=201):
    r = client.post(f"{API}/day-passes", headers=hd, json={"branch_id": branch, "visitor_name": name})
    assert r.status_code == expect, r.text
    return r.json()


def put_settings(client, hd, branch=1, expect=200, **kw):
    r = client.put(f"{API}/access-settings/{branch}", headers=hd, json=kw)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def world(client, lib):
    members = [mk_member(client, lib, n) for n in range(1, 4)]
    mh = [member_h(client, n) for n in range(1, 4)]
    return {"lib": lib, "members": members, "mh": mh}


# --- cards --------------------------------------------------------------------


def test_issue_card(client, world, clock, app):
    lib = world["lib"]
    card = issue(client, lib)
    assert card["card_no"] == "LC00000001" and card["status"] == "active"
    assert card["issued_on"] == "2026-11-02" and card["expires_on"] == "2027-11-01"
    assert card["replaces_id"] is None and card["fee_id"] is None and card["ended_on"] is None
    assert issue(client, lib, 2)["card_no"] == "LC00000002"
    e = err(client.post(f"{API}/members/1/cards", headers=lib), 409, "CARD_ALREADY_ACTIVE")
    assert e["details"]["card_no"] == "LC00000001"
    assert client.post(f"{API}/members/1/cards", headers=world["mh"][0]).status_code == 403
    assert client.post(f"{API}/members/99/cards", headers=lib).status_code == 404
    assert len(audit(app, "card_issued")) == 2
    n = notes(app, "card_issued")
    assert len(n) == 2 and "LC00000001" in n[0].message and n[0].card_id == 1
    got = client.get(f"{API}/notifications", headers=lib).json()["items"]
    assert any(i["card_id"] == 1 and i["type"] == "card_issued" for i in got)


def test_issue_checks(client, world, clock):
    lib = world["lib"]
    go(clock, 2027, 11, 2)
    err(client.post(f"{API}/members/1/cards", headers=lib), 409, "MEMBERSHIP_EXPIRED")
    go(clock, 2026, 11, 2)
    assert client.post(f"{API}/members/1/deactivate", headers=lib).status_code == 200
    err(client.post(f"{API}/members/1/cards", headers=lib), 409, "MEMBER_PASSIVE")


def test_replacement_fees(client, world, clock):
    lib = world["lib"]
    c1 = issue(client, lib)
    report(client, lib, c1["card_no"], "lost")
    c2 = issue(client, lib)
    assert c2["replaces_id"] == c1["id"] and c2["fee_id"] is not None
    fees = client.get(f"{API}/members/1/fees", headers=lib).json()["items"]
    assert len(fees) == 1 and fees[0]["kind"] == "card_replacement" and fees[0]["amount"] == "25.00"
    assert fees[0]["card_id"] == c2["id"] and fees[0]["id"] == c2["fee_id"]
    report(client, lib, c2["card_no"], "damaged")
    c3 = issue(client, lib)
    fee = client.get(f"{API}/members/1/fees", headers=lib).json()["items"][1]
    assert fee["amount"] == "10.00" and fee["id"] == c3["fee_id"]
    go(clock, 2026, 12, 1)
    report(client, lib, c3["card_no"], "damaged")
    c4 = issue(client, lib)
    fee = client.get(f"{API}/members/1/fees", headers=lib).json()["items"][2]
    assert fee["amount"] == "50.00" and fee["id"] == c4["fee_id"]
    bal = client.get(f"{API}/members/1/balance", headers=lib).json()
    assert bal["outstanding_fees"] == "85.00" and bal["blocked"] is True
    r = client.get(f"{API}/members/1/fees?kind=card_replacement", headers=lib).json()
    assert r["total"] == 3


def test_replacement_after_expired_and_revoked(client, world, clock):
    lib = world["lib"]
    c1 = issue(client, lib)
    go(clock, 2027, 11, 2)
    assert client.post(f"{API}/members/1/renew-membership", headers=lib).status_code == 200
    # renewal moved the card's expiry, so it is still active
    assert client.get(f"{API}/cards/{c1['card_no']}", headers=lib).json()["expires_on"] == "2028-10-31"
    go(clock, 2028, 11, 1)
    r = client.post(f"{API}/access/process", headers=lib).json()
    assert r["cards_expired"] == 1
    assert client.post(f"{API}/members/1/renew-membership", headers=lib).status_code == 200
    c2 = issue(client, lib)
    assert c2["fee_id"] is None and c2["replaces_id"] is None
    assert client.post(f"{API}/members/1/deactivate", headers=lib).status_code == 200
    assert client.get(f"{API}/cards/{c2['card_no']}", headers=lib).json()["status"] == "revoked"
    assert client.post(f"{API}/members/1/activate", headers=lib).status_code == 200
    c3 = issue(client, lib)
    assert c3["fee_id"] is None


def test_report_card(client, world, app):
    lib, mh = world["lib"], world["mh"]
    c = issue(client, lib)
    assert client.post(f"{API}/cards/{c['card_no']}/report", headers=mh[1], json={"reason": "lost"}).status_code == 403
    assert client.post(f"{API}/cards/{c['card_no']}/report", headers=mh[0], json={"reason": "x"}).status_code == 422
    assert client.post(f"{API}/cards/LC00000099/report", headers=mh[0], json={"reason": "lost"}).status_code == 404
    r = report(client, mh[0], c["card_no"], "damaged")
    assert r["status"] == "damaged" and r["ended_on"] == "2026-11-02"
    e = err(client.post(f"{API}/cards/{c['card_no']}/report", headers=lib, json={"reason": "lost"}), 409, "CARD_NOT_ACTIVE")
    assert e["details"]["status"] == "damaged"
    assert len(audit(app, "card_reported")) == 1


def test_read_cards(client, world):
    lib, mh = world["lib"], world["mh"]
    c1 = issue(client, lib)
    report(client, lib, c1["card_no"], "lost")
    c2 = issue(client, lib)
    items = client.get(f"{API}/members/1/cards", headers=mh[0]).json()["items"]
    assert [i["id"] for i in items] == [c2["id"], c1["id"]]
    assert client.get(f"{API}/members/1/cards", headers=mh[1]).status_code == 403
    got = client.get(f"{API}/cards/{c2['card_no']}", headers=lib).json()
    assert got["member"] == {
        "id": 1, "member_no": "M000001", "full_name": got["member"]["full_name"],
        "membership_type": "student", "status": "active",
    }
    assert client.get(f"{API}/cards/{c2['card_no']}", headers=mh[0]).status_code == 403
    assert client.get(f"{API}/cards/LC00000077", headers=lib).status_code == 404
    assert client.get(f"{API}/cards/zzz", headers=lib).status_code == 404


def test_expiry(client, world, clock):
    lib = world["lib"]
    c = issue(client, lib)
    go(clock, 2027, 11, 1)
    assert client.post(f"{API}/access/process", headers=lib).json()["cards_expired"] == 0
    assert client.get(f"{API}/cards/{c['card_no']}", headers=lib).json()["status"] == "active"
    go(clock, 2027, 11, 2)
    r = client.post(f"{API}/access/process", headers=lib).json()
    assert r == {"visits_closed": 0, "cards_expired": 1, "passes_expired": 0}
    got = client.get(f"{API}/cards/{c['card_no']}", headers=lib).json()
    assert got["status"] == "expired" and got["ended_on"] == "2027-11-02"


def test_members_me_and_summary(client, world):
    lib, mh = world["lib"], world["mh"]
    assert client.get(f"{API}/members/me", headers=mh[0]).json()["card_no"] is None
    s = client.get(f"{API}/members/1/summary", headers=lib).json()["access"]
    assert s == {"card_no": None, "card_status": None, "inside_branch_id": None, "visits_this_month": 0}
    c = issue(client, lib)
    assert client.get(f"{API}/members/me", headers=mh[0]).json()["card_no"] == c["card_no"]
    assert "card_no" not in client.get(f"{API}/members/1", headers=lib).json()
    scan(client, lib, card_no=c["card_no"])
    s = client.get(f"{API}/members/1/summary", headers=lib).json()["access"]
    assert s == {"card_no": c["card_no"], "card_status": "active", "inside_branch_id": 1, "visits_this_month": 1}
    report(client, lib, c["card_no"], "lost")
    s = client.get(f"{API}/members/1/summary", headers=lib).json()["access"]
    assert s["card_status"] == "lost" and client.get(f"{API}/members/me", headers=mh[0]).json()["card_no"] is None


# --- settings and occupancy ---------------------------------------------------


def test_settings(client, world, admin_h, app):
    lib = world["lib"]
    got = client.get(f"{API}/access-settings/1", headers=lib).json()
    assert got == {"branch_id": 1, "capacity": None, "guest_entry": True, "day_passes": True, "day_pass_price": "5.00"}
    r = put_settings(client, admin_h, capacity=10, day_pass_price="7.50")
    assert r["capacity"] == 10 and r["day_pass_price"] == "7.50" and r["guest_entry"] is True
    assert put_settings(client, admin_h, capacity=None)["capacity"] is None
    assert put_settings(client, admin_h, guest_entry=False)["guest_entry"] is False
    assert len(audit(app, "access_settings_changed")) == 3
    put_settings(client, lib, expect=403)
    assert client.get(f"{API}/access-settings/1", headers=world["mh"][0]).status_code == 403
    for bad in ({"capacity": 0}, {"capacity": 5001}, {"day_pass_price": "100.01"}, {"day_pass_price": "-1.00"},
                {"day_pass_price": 5}, {"guest_entry": "yes"}, {"x": 1}):
        put_settings(client, admin_h, expect=422, **bad)
    put_settings(client, admin_h, branch=99, expect=404)
    assert client.get(f"{API}/access-settings/99", headers=lib).status_code == 404


def test_capacity_below_occupancy_and_full(client, world, admin_h):
    lib = world["lib"]
    cards = [issue(client, lib, n)["card_no"] for n in (1, 2, 3)]
    scan(client, lib, card_no=cards[0])
    p = sell(client, lib)
    scan(client, lib, pass_code=p["code"])
    e = err(client.put(f"{API}/access-settings/1", headers=admin_h, json={"capacity": 1}), 409, "CAPACITY_BELOW_OCCUPANCY")
    assert e["details"]["occupancy"] == 2
    put_settings(client, admin_h, capacity=2)
    occ = client.get(f"{API}/branches/1/occupancy", headers=world["mh"][0]).json()
    assert occ == {"branch_id": 1, "inside": 2, "members": 1, "visitors": 1, "capacity": 2, "free": 0}
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": cards[1]}), 409, "BRANCH_FULL")
    assert e["details"]["capacity"] == 2
    scan(client, lib, "out", card_no=cards[0])
    assert scan(client, lib, card_no=cards[1])["result"] == "entered"
    p2 = sell(client, lib)
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "pass_code": p2["code"]}), 409, "BRANCH_FULL")
    assert client.get(f"{API}/branches/99/occupancy", headers=lib).status_code == 404
    assert client.get(f"{API}/branches/2/occupancy", headers=lib).json()["capacity"] is None


def test_inside_list(client, world, clock):
    lib = world["lib"]
    c1, c2 = issue(client, lib, 1)["card_no"], issue(client, lib, 2)["card_no"]
    p = sell(client, lib)
    scan(client, lib, card_no=c2)
    clock.advance(minutes=5)
    scan(client, lib, pass_code=p["code"])
    clock.advance(minutes=5)
    scan(client, lib, card_no=c1)
    items = client.get(f"{API}/branches/1/inside", headers=lib).json()["items"]
    assert [i["member_id"] for i in items] == [2, None, 1]
    assert items[1]["day_pass_code"] == p["code"] and items[1]["full_name"] is None
    assert items[0]["day_pass_code"] is None and items[0]["entered_at"] == "2026-11-02T09:30:00+03:00"
    assert client.get(f"{API}/branches/1/inside", headers=world["mh"][0]).status_code == 403


# --- gate -----------------------------------------------------------------------


def test_gate_example(client, world, clock):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    go(clock, 2026, 11, 2, 7, 59)
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": c}), 409, "BRANCH_NOT_OPEN")
    go(clock, 2026, 11, 2, 8, 0)
    r = scan(client, lib, card_no=c)
    assert r["result"] == "entered" and r["member_id"] == 1 and r["day_pass_id"] is None
    go(clock, 2026, 11, 2, 8, 5)
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 2, "direction": "in", "card_no": c}), 409, "ALREADY_INSIDE")
    assert e["details"]["branch_id"] == 1
    go(clock, 2026, 11, 2, 9, 0)
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 2, "direction": "out", "card_no": c}), 409, "WRONG_BRANCH")
    assert e["details"]["branch_id"] == 1
    out = scan(client, lib, "out", card_no=c)
    assert out["result"] == "left" and out["visit_id"] == r["visit_id"]
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "out", "card_no": c}), 409, "NOT_INSIDE")
    v = client.get(f"{API}/members/1/visits", headers=lib).json()["items"][0]
    assert v["minutes"] == 60 and v["closed_by"] == "exit" and v["left_at"] == "2026-11-02T09:00:00+03:00"
    assert v["card_id"] == 1 and v["day_pass_id"] is None


def test_scan_validation(client, world):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    for body in (
        {"branch_id": 1, "direction": "in"},
        {"branch_id": 1, "direction": "in", "card_no": c, "pass_code": "x"},
        {"branch_id": 1, "direction": "sideways", "card_no": c},
        {"direction": "in", "card_no": c},
    ):
        assert client.post(f"{API}/access/scan", headers=lib, json=body).status_code == 422
    assert client.post(f"{API}/access/scan", headers=world["mh"][0], json={"branch_id": 1, "direction": "in", "card_no": c}).status_code == 403
    for body in ({"branch_id": 1, "direction": "in", "card_no": "LC00000099"},
                 {"branch_id": 1, "direction": "out", "pass_code": "DP-X"},
                 {"branch_id": 9, "direction": "in", "card_no": c}):
        assert client.post(f"{API}/access/scan", headers=lib, json=body).status_code == 404


def test_entry_check_order(client, world, clock, admin_h, app):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    g = issue(client, lib, 2)["card_no"]
    mk = lambda **kw: client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", **kw})
    # guest member
    gid = mk_member(client, lib, 9, "guest")
    gc = issue(client, lib, gid)["card_no"]
    put_settings(client, admin_h, guest_entry=False)
    err(mk(card_no=gc), 409, "GUEST_ENTRY_NOT_ALLOWED")
    put_settings(client, admin_h, guest_entry=True)
    assert mk(card_no=gc).status_code == 200
    # ban before guest
    r = client.post(f"{API}/members/2/access-bans", headers=lib, json={"reason": "noise", "ends_on": "2026-11-05"})
    assert r.status_code == 201, r.text
    e = err(mk(card_no=g), 409, "ACCESS_BANNED")
    assert e["details"]["ends_on"] == "2026-11-05"
    go(clock, 2026, 11, 7, 10)  # Saturday
    err(mk(card_no=c), 409, "BRANCH_NOT_OPEN")
    assert len(sel(app, sa.select(lms.access.models.DeniedScan))) == 3
    assert audit(app, "access_scanned") and len(audit(app, "access_scanned")) == 1


def test_ban_example(client, world, clock):
    lib, mh = world["lib"], world["mh"]
    c = issue(client, lib)["card_no"]
    r = client.post(f"{API}/members/1/access-bans", headers=lib, json={"reason": "x", "starts_on": "2026-11-02", "ends_on": "2026-11-05"})
    assert r.status_code == 201
    ban = r.json()
    assert ban["in_force"] is True and ban["lifted_at"] is None and ban["created_by"] == 2
    go(clock, 2026, 11, 5, 9)
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": c}), 409, "ACCESS_BANNED")
    assert e["details"]["ends_on"] == "2026-11-05"
    go(clock, 2026, 11, 6, 9)
    assert scan(client, lib, card_no=c)["result"] == "entered"
    n = notes(client.app, "access_banned")
    assert len(n) == 1 and "2026-11-05" in n[0].message
    items = client.get(f"{API}/members/1/access-bans", headers=mh[0]).json()["items"]
    assert items[0]["in_force"] is False
    assert client.get(f"{API}/members/1/access-bans", headers=mh[1]).status_code == 403
    assert client.post(f"{API}/members/1/access-bans", headers=mh[0], json={}).status_code == 403


def test_ban_rules(client, world, clock, app):
    lib = world["lib"]
    post = lambda **kw: client.post(f"{API}/members/1/access-bans", headers=lib, json=kw)
    assert post(reason="x", ends_on="2026-11-01").status_code == 422
    assert post(reason="x", starts_on="2026-11-01", ends_on="2026-11-05").status_code == 422
    assert post(reason="x", starts_on="2026-11-05", ends_on="2026-11-04").status_code == 422
    assert post(reason="x", starts_on="2026-11-02", ends_on="2027-11-04").status_code == 422
    assert post(reason="", ends_on="2026-11-05").status_code == 422
    assert post(reason="y" * 201, ends_on="2026-11-05").status_code == 422
    assert post(reason="x").status_code == 422
    assert post(reason="x", starts_on="2026-11-02", ends_on="2027-11-02").status_code == 201
    assert client.post(f"{API}/members/99/access-bans", headers=lib, json={"reason": "x", "ends_on": "2026-11-05"}).status_code == 404
    ban = client.get(f"{API}/members/1/access-bans", headers=lib).json()["items"][0]
    e = err(post(reason="again", starts_on="2027-11-02", ends_on="2027-11-10"), 409, "BAN_OVERLAPS")
    assert e["details"]["ban_id"] == ban["id"]
    lifted = client.post(f"{API}/access-bans/{ban['id']}/lift", headers=lib).json()
    assert lifted["lifted_at"] == "2026-11-02T09:30:00+03:00" and lifted["in_force"] is False
    err(client.post(f"{API}/access-bans/{ban['id']}/lift", headers=lib), 409, "BAN_ALREADY_LIFTED")
    assert client.post(f"{API}/access-bans/99/lift", headers=lib).status_code == 404
    assert post(reason="again", starts_on="2027-11-02", ends_on="2027-11-10").status_code == 201
    assert len(audit(app, "access_ban_created")) == 2 and len(audit(app, "access_ban_lifted")) == 1


def test_ban_ends_visit(client, world, clock):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    v = scan(client, lib, card_no=c)
    client.post(f"{API}/members/1/access-bans", headers=lib, json={"reason": "x", "starts_on": "2026-11-03", "ends_on": "2026-11-04"})
    assert client.get(f"{API}/branches/1/occupancy", headers=lib).json()["inside"] == 1
    clock.advance(minutes=30)
    client.post(f"{API}/members/1/access-bans", headers=lib, json={"reason": "x", "ends_on": "2026-11-02"})
    got = client.get(f"{API}/members/1/visits", headers=lib).json()["items"][0]
    assert got["id"] == v["visit_id"] and got["closed_by"] == "staff" and got["minutes"] == 30


def test_lost_card_alert(client, world, clock, app):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    report(client, lib, c, "lost")
    e = err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 2, "direction": "in", "card_no": c}), 409, "CARD_NOT_ACTIVE")
    assert e["details"]["status"] == "lost"
    clock.advance(minutes=10)
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": c}), 409, "CARD_NOT_ACTIVE")
    alerts = client.get(f"{API}/access/alerts", headers=lib).json()["items"]
    assert [a["branch_id"] for a in alerts] == [1, 2] and alerts[0]["card_no"] == c
    assert alerts[0]["at"] == "2026-11-02T09:40:00+03:00"
    assert len(notes(app, "lost_card_used")) == 2 and c in notes(app, "lost_card_used")[0].message
    assert client.get(f"{API}/access/alerts", headers=world["mh"][0]).status_code == 403
    # damaged cards: refused, no alert
    c2 = issue(client, lib)["card_no"]
    report(client, lib, c2, "damaged")
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": c2}), 409, "CARD_NOT_ACTIVE")
    assert client.get(f"{API}/access/alerts", headers=lib).json()["total"] == 2
    assert not audit(app, "access_scanned")


def test_exit_with_inactive_card_and_passive_member(client, world, clock):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    scan(client, lib, card_no=c)
    report(client, lib, c, "damaged")
    assert scan(client, lib, "out", card_no=c)["result"] == "left"
    c2 = issue(client, lib, 2)["card_no"]
    scan(client, lib, card_no=c2)
    client.post(f"{API}/members/2/deactivate", headers=lib)
    # deactivation ended the visit and revoked the card
    assert client.get(f"{API}/branches/1/occupancy", headers=lib).json()["inside"] == 0
    got = client.get(f"{API}/cards/{c2}", headers=lib).json()
    assert got["status"] == "revoked" and got["ended_on"] == "2026-11-02"
    v = client.get(f"{API}/members/2/visits", headers=lib).json()["items"][0]
    assert v["closed_by"] == "staff" and v["left_at"] is not None


def test_close_by_hand(client, world, app):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    v = scan(client, lib, card_no=c)
    r = client.post(f"{API}/visits/{v['visit_id']}/close", headers=lib)
    assert r.status_code == 200 and r.json()["closed_by"] == "staff" and r.json()["minutes"] == 0
    err(client.post(f"{API}/visits/{v['visit_id']}/close", headers=lib), 409, "VISIT_NOT_OPEN")
    assert client.post(f"{API}/visits/99/close", headers=lib).status_code == 404
    assert client.post(f"{API}/visits/1/close", headers=world["mh"][0]).status_code == 403
    assert len(audit(app, "visit_closed")) == 1


def test_closing_time(client, world, clock):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    go(clock, 2026, 11, 2, 19, 30)
    scan(client, lib, card_no=c)
    go(clock, 2026, 11, 2, 19, 59)
    assert client.post(f"{API}/access/process", headers=lib).json()["visits_closed"] == 0
    assert client.get(f"{API}/branches/1/occupancy", headers=lib).json()["inside"] == 1
    go(clock, 2026, 11, 2, 20, 30)
    assert client.post(f"{API}/access/process", headers=lib).json()["visits_closed"] == 1
    v = client.get(f"{API}/members/1/visits", headers=lib).json()["items"][0]
    assert v["left_at"] == "2026-11-02T20:00:00+03:00" and v["closed_by"] == "closing" and v["minutes"] == 30
    # next day: closes_at of the entry date
    go(clock, 2026, 11, 3, 9)
    scan(client, lib, card_no=c)
    go(clock, 2026, 11, 7, 12)
    assert client.post(f"{API}/access/process", headers=lib).json()["visits_closed"] == 1
    v = client.get(f"{API}/members/1/visits", headers=lib).json()["items"][0]
    assert v["left_at"] == "2026-11-03T20:00:00+03:00"


def test_closure_closes_visits(client, world, clock, admin_h):
    lib = world["lib"]
    c = issue(client, lib)["card_no"]
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-03", "reason": "Sayim"})
    assert r.status_code == 201, r.text
    go(clock, 2026, 11, 3, 9)
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "card_no": c}), 409, "BRANCH_NOT_OPEN")
    assert scan(client, lib, branch=2, card_no=c)["result"] == "entered"


def test_day_passes(client, world, clock, admin_h, app):
    lib = world["lib"]
    p = sell(client, lib, name="  Ali Veli ")
    assert p["code"] == "DP-AAA-20261102-1" and p["status"] == "unused" and p["price"] == "5.00"
    assert p["valid_on"] == "2026-11-02" and p["visitor_name"] == "Ali Veli" and p["sold_by"] == 2
    assert sell(client, lib)["code"] == "DP-AAA-20261102-2"
    assert sell(client, lib, branch=2)["code"] == "DP-BBB-20261102-1"
    for body in ({"branch_id": 1}, {"visitor_name": "x"}, {"branch_id": 1, "visitor_name": ""}):
        assert client.post(f"{API}/day-passes", headers=lib, json=body).status_code == 422
    sell(client, lib, branch=9, expect=404)
    assert client.post(f"{API}/day-passes", headers=world["mh"][0], json={"branch_id": 1, "visitor_name": "x"}).status_code == 403
    put_settings(client, admin_h, day_pass_price="12.00")
    assert sell(client, lib)["price"] == "12.00"
    put_settings(client, admin_h, day_passes=False)
    err(client.post(f"{API}/day-passes", headers=lib, json={"branch_id": 1, "visitor_name": "x"}), 409, "DAY_PASSES_DISABLED")
    put_settings(client, admin_h, day_passes=True)
    assert len(audit(app, "day_pass_sold")) == 4
    assert client.post(f"{API}/day-passes/1/cancel", headers=lib).json()["status"] == "cancelled"
    err(client.post(f"{API}/day-passes/1/cancel", headers=lib), 409, "PASS_NOT_USABLE")
    assert client.post(f"{API}/day-passes/99/cancel", headers=lib).status_code == 404
    assert len(audit(app, "day_pass_cancelled")) == 1
    items = client.get(f"{API}/day-passes", headers=lib).json()["items"]
    assert [i["id"] for i in items] == [4, 3, 2, 1]
    assert client.get(f"{API}/day-passes?branch_id=2", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/day-passes?status=cancelled", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/day-passes?valid_on=2026-11-03", headers=lib).json()["total"] == 0
    assert client.get(f"{API}/day-passes?valid_on=bad", headers=lib).status_code == 422
    assert client.get(f"{API}/day-passes?status=bad", headers=lib).status_code == 422


def test_day_pass_limit(client, world):
    lib = world["lib"]
    for _ in range(50):
        sell(client, lib)
    e = err(client.post(f"{API}/day-passes", headers=lib, json={"branch_id": 1, "visitor_name": "x"}), 409, "DAY_PASS_LIMIT_REACHED")
    assert e["details"]["limit"] == 50
    client.post(f"{API}/day-passes/50/cancel", headers=lib)
    err(client.post(f"{API}/day-passes", headers=lib, json={"branch_id": 1, "visitor_name": "x"}), 409, "DAY_PASS_LIMIT_REACHED")
    assert sell(client, lib, branch=2)["code"] == "DP-BBB-20261102-1"


def test_pass_code_example(client, world, clock):
    lib = world["lib"]
    go(clock, 2026, 11, 2, 9)
    for _ in range(3):
        p = sell(client, lib)
    assert p["code"] == "DP-AAA-20261102-3"


def test_pass_entry(client, world, clock):
    lib = world["lib"]
    p = sell(client, lib)
    code = p["code"]
    post = lambda direction="in", branch=1: client.post(
        f"{API}/access/scan", headers=lib, json={"branch_id": branch, "direction": direction, "pass_code": code}
    )
    e = err(post(branch=2), 409, "WRONG_BRANCH")
    assert e["details"]["branch_id"] == 1
    err(post("out"), 409, "NOT_INSIDE")
    go(clock, 2026, 11, 2, 7, 0)
    err(post(), 409, "BRANCH_NOT_OPEN")
    go(clock, 2026, 11, 2, 9, 0)
    r = post()
    assert r.status_code == 200 and r.json()["day_pass_id"] == 1 and r.json()["member_id"] is None
    err(post(), 409, "PASS_NOT_USABLE")
    assert post("out").json()["result"] == "left"
    e = err(post(), 409, "PASS_NOT_USABLE")
    assert e["details"]["status"] == "used"
    p2 = sell(client, lib)
    client.post(f"{API}/day-passes/{p2['id']}/cancel", headers=lib)
    code = p2["code"]
    assert err(post(), 409, "PASS_NOT_USABLE")["details"]["status"] == "cancelled"
    p3 = sell(client, lib)
    code = p3["code"]
    go(clock, 2026, 11, 3, 9)
    err(post(), 409, "PASS_NOT_VALID_TODAY")
    # process cancels the unused pass of yesterday
    r = client.post(f"{API}/access/process", headers=lib).json()
    assert r["passes_expired"] == 1
    assert client.get(f"{API}/day-passes/", headers=lib).status_code in (200, 307, 404)
    assert client.get(f"{API}/day-passes?status=cancelled", headers=lib).json()["total"] == 2


def test_branch_deactivation(client, world, admin_h, lib, clock):
    # a branch that only has an unused pass or a visitor inside is in use
    mk = client.post(f"{API}/branches", headers=admin_h, json={"code": "CCC", "name": "C", "address": ""})
    bid = mk.json()["id"]
    cards = issue(client, lib)["card_no"]
    r = client.patch(f"{API}/branches/{bid}", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200
    client.patch(f"{API}/branches/{bid}", headers=admin_h, json={"is_active": True})
    p = sell(client, lib, branch=bid)
    err(client.patch(f"{API}/branches/{bid}", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/day-passes/{p['id']}/cancel", headers=lib)
    scan(client, lib, branch=bid, card_no=cards)
    err(client.patch(f"{API}/branches/{bid}", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    scan(client, lib, "out", branch=bid, card_no=cards)
    assert client.patch(f"{API}/branches/{bid}", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/day-passes", headers=lib, json={"branch_id": bid, "visitor_name": "x"}), 409, "BRANCH_INACTIVE")
    c2 = issue(client, lib, 2)["card_no"]
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": bid, "direction": "in", "card_no": c2}), 409, "BRANCH_INACTIVE")


# --- lending, visits, reports ------------------------------------------------------


def test_lend_by_card(client, world):
    lib = world["lib"]
    book = mk_book(client, lib, 0)
    copy = new_copy(client, lib, book, "BC-0001")
    c = issue(client, lib, 2)["card_no"]
    post = lambda **kw: client.post(f"{API}/loans", headers=lib, json=kw)
    assert post(member_id=1, card_no=c, copy_id=copy).status_code == 422
    assert post(copy_id=copy).status_code == 422
    assert post(card_no="LC00000099", copy_id=copy).status_code == 404
    report(client, lib, c, "lost")
    e = err(post(card_no=c, copy_id=copy), 409, "CARD_NOT_ACTIVE")
    assert e["details"]["status"] == "lost"
    c2 = issue(client, lib, 2)["card_no"]
    r = post(card_no=c2, copy_id=copy)
    assert r.status_code == 201 and r.json()["member_id"] == 2


def test_visit_history(client, world, clock):
    lib, mh = world["lib"], world["mh"]
    c = issue(client, lib)["card_no"]
    for day in (2, 3, 4):
        go(clock, 2026, 11, day, 9)
        scan(client, lib, branch=1 if day != 3 else 2, card_no=c)
        clock.advance(minutes=45)
        scan(client, lib, "out", branch=1 if day != 3 else 2, card_no=c)
    items = client.get(f"{API}/members/1/visits", headers=mh[0]).json()["items"]
    assert [i["entered_at"][:10] for i in items] == ["2026-11-04", "2026-11-03", "2026-11-02"]
    assert all(i["minutes"] == 45 for i in items)
    assert client.get(f"{API}/members/1/visits?from=2026-11-03&to=2026-11-03", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/members/1/visits?branch_id=2", headers=lib).json()["total"] == 1
    assert client.get(f"{API}/members/1/visits?from=x", headers=lib).status_code == 422
    assert client.get(f"{API}/members/1/visits", headers=mh[1]).status_code == 403
    assert client.get(f"{API}/members/99/visits", headers=lib).status_code == 404
    go(clock, 2026, 11, 5, 9)
    scan(client, lib, card_no=c)
    assert client.get(f"{API}/members/1/visits", headers=lib).json()["items"][0]["minutes"] is None


def test_visits_report(client, world, clock, admin_h):
    lib = world["lib"]
    cs = [issue(client, lib, n)["card_no"] for n in (1, 2, 3)]
    go(clock, 2026, 11, 2, 9, 0)
    scan(client, lib, card_no=cs[0])
    go(clock, 2026, 11, 2, 9, 30)
    scan(client, lib, card_no=cs[1])
    go(clock, 2026, 11, 2, 10, 0)
    scan(client, lib, "out", card_no=cs[0])
    p = sell(client, lib)
    scan(client, lib, pass_code=p["code"])
    go(clock, 2026, 11, 2, 10, 30)
    scan(client, lib, "out", pass_code=p["code"])
    go(clock, 2026, 11, 2, 11, 0)
    scan(client, lib, "out", card_no=cs[1])
    err(client.post(f"{API}/access/scan", headers=lib, json={"branch_id": 1, "direction": "in", "pass_code": p["code"]}), 409, "PASS_NOT_USABLE")
    sell(client, lib)
    r = client.get(f"{API}/reports/visits?from=2026-11-01&to=2026-11-30", headers=lib)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [
        {"branch_id": 1, "visits": 3, "member_visits": 2, "unique_members": 2, "pass_visits": 1,
         "average_minutes": "60.0", "peak_occupancy": 2, "pass_revenue": "10.00", "denied": 1}
    ]
    assert client.get(f"{API}/reports/visits?from=2026-11-01&to=2026-11-30&branch_id=2", headers=lib).json()["items"] == []
    for q in ("from=2026-11-05&to=2026-11-01", "from=2026-01-01&to=2027-01-02", "from=2026-11-01", "to=x&from=y"):
        assert client.get(f"{API}/reports/visits?{q}", headers=lib).status_code == 422
    assert client.get(f"{API}/reports/visits?from=2026-11-01&to=2026-11-30", headers=world["mh"][0]).status_code == 403
    assert client.get(f"{API}/reports/visits?from=2026-01-01&to=2027-01-01", headers=admin_h).status_code == 200


def test_peak_example():
    from lms.access.models import Visit
    from lms.access.reports import peak_occupancy

    def v(a, b):
        t = lambda hh, mm: datetime.datetime(2026, 11, 2, hh, mm, tzinfo=TZ)
        return Visit(entered_at=t(*a), left_at=t(*b))

    assert peak_occupancy([v((9, 0), (10, 0)), v((9, 30), (11, 0)), v((10, 0), (10, 30))]) == 2


def test_permissions(client, world, admin_h):
    mh = world["mh"][0]
    for method, url in (
        ("post", "/access/process"), ("get", "/access/alerts"), ("get", "/day-passes"),
        ("get", "/branches/1/inside"), ("post", "/members/1/cards"), ("get", "/cards/LC00000001"),
    ):
        assert getattr(client, method)(f"{API}{url}", headers=mh).status_code == 403, url
        assert getattr(client, method)(f"{API}{url}").status_code == 401, url
    assert client.get(f"{API}/branches/1/occupancy", headers=mh).status_code == 200
    assert client.get(f"{API}/branches/1/occupancy").status_code == 401
    assert client.post(f"{API}/access/process", headers=admin_h).status_code == 200
