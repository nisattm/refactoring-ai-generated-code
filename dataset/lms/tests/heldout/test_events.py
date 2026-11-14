"""Heldout tests: module 20 (Events). Generated from cases/events.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, items, lend,
    member_fees, member_headers, pay, register_member, return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, THU, FRI, SAT = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); default branch hours 08:00-20:00


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


def staff(client, admin, branch):
    """Id of a new active staff profile (module 19) with home ``branch``."""
    _seq[0] += 1
    email = f"evstaff{_seq[0]}@library.local"
    u = ok(post(client, admin, "users", {"email": email, "full_name": f"Staff {_seq[0]}", "role": "librarian", "password": "Staff12345"}), 201)
    p = ok(post(client, admin, "staff", {"user_id": u["id"], "home_branch_id": branch["id"], "employment": "full_time", "started_on": "2020-01-01"}), 201)
    return p["id"]


def shift(client, admin, staff_id, branch, day, start="08:00", end="18:00"):
    return ok(post(client, admin, "shifts", {"staff_id": staff_id, "branch_id": branch["id"], "date": day, "start_time": start, "end_time": end}), 201)


def on_shift(client, admin, branch, *days, start="08:00", end="18:00"):
    """A staff profile with a shift on each of ``days`` at ``branch``."""
    sid = staff(client, admin, branch)
    for day in days:
        shift(client, admin, sid, branch, day, start, end)
    return sid


def try_event(client, headers, branch, staff_id, *, day=WED, start="14:00", end="16:00", capacity=10, title=None, **fields):
    _seq[0] += 1
    body = {"title": title or f"Event {_seq[0]:03d}", "kind": "talk", "branch_id": branch["id"], "date": day,
            "start_time": start, "end_time": end, "capacity": capacity, "staff_id": staff_id}
    body.update(fields)
    return client.post("/api/v1/events", headers=headers, json=body)


def event(client, headers, branch, staff_id, **kw):
    return ok(try_event(client, headers, branch, staff_id, **kw), 201)


def publish(client, headers, event_id):
    return post(client, headers, f"events/{event_id}/publish")


def published(client, lib, branch, staff_id, **kw):
    ev = event(client, lib, branch, staff_id, **kw)
    return ok(publish(client, lib, ev["id"]))


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def reg(client, headers, event_id, member_id=None):
    return post(client, headers, f"events/{event_id}/registrations", {} if member_id is None else {"member_id": member_id})


def register(client, lib, event_id, member_):
    return ok(reg(client, lib, event_id, member_["id"]), 201)


def cancel_reg(client, headers, registration_id):
    return post(client, headers, f"event-registrations/{registration_id}/cancel")


def regs_of(client, lib, event_id, **params):
    return items(get(client, lib, f"events/{event_id}/registrations", **params))


def reg_of(client, lib, event_id, member_id):
    return [x for x in regs_of(client, lib, event_id) if x["member_id"] == member_id][0]


def group_room(client, admin, branch, capacity=6):
    _seq[0] += 1
    return ok(post(client, admin, "rooms", {"branch_id": branch["id"], "code": f"G{_seq[0]}", "name": f"Group {_seq[0]}", "kind": "group",
              "opens_at": "08:00", "closes_at": "20:00", "capacity": capacity, "min_participants": 2}), 201)


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fees_of(client, lib, member_id):
    return [(f["kind"], f["amount"], f["status"]) for f in items(member_fees(client, lib, member_id))]


def process(client, lib):
    return ok(post(client, lib, "events/process"))


def debt(client, lib, branch, member_, amount="50.00"):
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def test_t_evt_01_b(client, admin, librarian, branch_a, branch_b):
    """T-EVT-01-b (LIB-EVT-01): 422 ten times; 403"""
    sid = staff(client, admin, branch_a)
    indiv = ok(post(client, admin, "rooms", {"branch_id": branch_a["id"], "code": "IND1", "name": "Single", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}), 201)
    small, other = group_room(client, admin, branch_a, 6), group_room(client, admin, branch_b)
    bad = [dict(end="14:30"), dict(end="18:30"), dict(capacity=0), dict(capacity=201), dict(fee="200.01"), dict(kind="concert"),
           dict(room_id=indiv["id"]), dict(room_id=other["id"]), dict(room_id=small["id"], capacity=7)]
    for fields in bad:
        assert try_event(client, librarian, branch_a, sid, **fields).status_code == 422, fields
    assert try_event(client, librarian, branch_a, 999999).status_code == 422
    assert try_event(client, member_headers(client, member(client, librarian, branch_a)), branch_a, sid).status_code == 403


def test_t_evt_02_b(client, admin, librarian, branch_a):
    """T-EVT-02-b (LIB-EVT-02): ROOM_NOT_AVAILABLE with details.booking_id; 201; ROOM_NOT_AVAILABLE with details.event_id"""
    sid = staff(client, admin, branch_a)
    r = group_room(client, admin, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = ok(post(client, librarian, "room-bookings", {"room_id": r["id"], "date": WED, "start_time": "14:00", "end_time": "15:00", "member_id": m1["id"], "participant_ids": [m2["id"]]}), 201)
    assert err(try_event(client, librarian, branch_a, sid, room_id=r["id"]), 409, "ROOM_NOT_AVAILABLE")["details"]["booking_id"] == b["id"]
    e = event(client, librarian, branch_a, sid, room_id=r["id"], start="15:00", end="17:00")
    assert err(try_event(client, librarian, branch_a, sid, room_id=r["id"], start="16:00", end="17:00"), 409, "ROOM_NOT_AVAILABLE")["details"]["event_id"] == e["id"]


def test_t_evt_03_b(client, admin, librarian, branch_a, branch_b):
    """T-EVT-03-b (LIB-EVT-03): 409 STAFF_NOT_ON_SHIFT each"""
    for sid in (staff(client, admin, branch_a), on_shift(client, admin, branch_a, WED, start="10:00", end="15:00"), on_shift(client, admin, branch_b, WED)):
        e = event(client, librarian, branch_a, sid)
        err(publish(client, librarian, e["id"]), 409, "STAFF_NOT_ON_SHIFT")


def test_t_evt_04_b(client, admin, librarian, branch_a):
    """T-EVT-04-b (LIB-EVT-04): 409 STAFF_NOT_ON_SHIFT; the event keeps its times"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    err(client.patch(f"/api/v1/events/{e['id']}", headers=librarian, json={"start_time": "17:00", "end_time": "19:00"}), 409, "STAFF_NOT_ON_SHIFT")
    assert get(client, librarian, f"events/{e['id']}")["start_time"] == "14:00"


def test_t_evt_06_a(client, admin, librarian, branch_a):
    """T-EVT-06-a (LIB-EVT-06): 409 CAPACITY_BELOW_REGISTERED with details.registered 2; then 200 and M3 registered"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    for m in (m1, m2, m3):
        register(client, librarian, e["id"], m)
    url = f"/api/v1/events/{e['id']}"
    assert err(client.patch(url, headers=librarian, json={"capacity": 1}), 409, "CAPACITY_BELOW_REGISTERED")["details"]["registered"] == 2
    ok(client.patch(url, headers=librarian, json={"capacity": 3}))
    assert reg_of(client, librarian, e["id"], m3["id"])["status"] == "registered"


def test_t_evt_08_b(client, admin, librarian, branch_a):
    """T-EVT-08-b (LIB-EVT-08): 404 NOT_FOUND"""
    d = event(client, librarian, branch_a, staff(client, admin, branch_a))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/events/{d['id']}", headers=mh).status_code == 404


def test_t_evt_10_b(client, admin, librarian, branch_a):
    """T-EVT-10-b (LIB-EVT-10): 409 INVALID_EVENT_STATUS; 403"""
    e = event(client, librarian, branch_a, staff(client, admin, branch_a))
    assert post(client, member_headers(client, member(client, librarian, branch_a)), f"events/{e['id']}/cancel").status_code == 403
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    err(post(client, librarian, f"events/{e['id']}/cancel"), 409, "INVALID_EVENT_STATUS")


def test_t_evt_12_a(client, admin, librarian, branch_a):
    """T-EVT-12-a (LIB-EVT-12): cancelled_events 2; events cancelled with branch_closed; M's registration cancelled (event_cancelled) and one event_cancelled notification"""
    sid = on_shift(client, admin, branch_a, WED)
    e = published(client, librarian, branch_a, sid)
    d = event(client, librarian, branch_a, sid, start="10:00", end="11:00")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    c = ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": WED, "reason": "Sayım"}), 201)
    assert c["cancelled_events"] == 2
    assert [get(client, librarian, f"events/{x['id']}")["cancel_reason"] for x in (e, d)] == ["branch_closed", "branch_closed"]
    assert reg_of(client, librarian, e["id"], m["id"])["cancel_reason"] == "event_cancelled"
    assert len(notes(client, librarian, m["id"], "event_cancelled")) == 1


def test_t_evt_13_b(client, admin, librarian, branch_a):
    """T-EVT-13-b (LIB-EVT-13): 422 both"""
    sid = staff(client, admin, branch_a)
    for weeks in (1, 13):
        body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "18:00", "end_time": "19:00", "capacity": 5, "staff_id": sid, "weeks": weeks}
        assert post(client, librarian, "event-series", body).status_code == 422


def test_t_evt_14_a(client, admin, librarian, branch_a):
    """T-EVT-14-a (LIB-EVT-14): 409 SERIES_EMPTY; no event is created"""
    sid = staff(client, admin, branch_a)
    body = {"title": "Hafta sonu", "kind": "talk", "branch_id": branch_a["id"], "first_date": SAT, "start_time": "10:00", "end_time": "11:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    err(post(client, librarian, "event-series", body), 409, "SERIES_EMPTY")
    assert get(client, librarian, "events")["total"] == 0


def test_t_evt_16_a(client, admin, librarian, branch_a):
    """T-EVT-16-a (LIB-EVT-16): First published, second still draft"""
    sid = on_shift(client, admin, branch_a, "2026-11-10", "2026-11-17")
    body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "15:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    first, second = ok(post(client, librarian, "event-series", body), 201)["created"]
    ok(publish(client, librarian, first))
    assert [get(client, librarian, f"events/{i}")["status"] for i in (first, second)] == ["published", "draft"]


def test_t_evt_18_a(client, admin, librarian, branch_a):
    """T-EVT-18-a (LIB-EVT-18): The member has one registration"""
    sid = on_shift(client, admin, branch_a, "2026-11-10", "2026-11-17")
    body = {"title": "Seri", "kind": "talk", "branch_id": branch_a["id"], "first_date": "2026-11-10", "start_time": "14:00", "end_time": "15:00", "capacity": 5, "staff_id": sid, "weeks": 2}
    ids = ok(post(client, librarian, "event-series", body), 201)["created"]
    for i in ids:
        ok(publish(client, librarian, i))
    m = member(client, librarian, branch_a)
    register(client, librarian, ids[0], m)
    assert get(client, librarian, f"members/{m['id']}/event-registrations")["total"] == 1


def test_t_evt_19_b(client, admin, librarian, branch_a):
    """T-EVT-19-b (LIB-EVT-19): 422 both"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    m = member(client, librarian, branch_a)
    assert reg(client, librarian, e["id"]).status_code == 422
    assert reg(client, member_headers(client, m), e["id"], m["id"]).status_code == 422


def test_t_evt_20_b(client, admin, librarian, branch_a):
    """T-EVT-20-b (LIB-EVT-20): 409 MEMBER_PASSIVE; 409 MEMBERSHIP_EXPIRED"""
    sid = on_shift(client, admin, branch_a, WED, "2027-11-02")
    e = published(client, librarian, branch_a, sid)
    late = published(client, librarian, branch_a, sid, day="2027-11-02")
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(reg(client, librarian, e["id"], p["id"]), 409, "MEMBER_PASSIVE")
    err(reg(client, librarian, late["id"], m["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_evt_20_d(client, admin, librarian, branch_a):
    """T-EVT-20-d (LIB-EVT-20): 409 ALREADY_REGISTERED both"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    err(reg(client, librarian, e["id"], m1["id"]), 409, "ALREADY_REGISTERED")
    err(reg(client, librarian, e["id"], m2["id"]), 409, "ALREADY_REGISTERED")


def test_t_evt_20_f(client, admin, librarian, branch_a):
    """T-EVT-20-f (LIB-EVT-20): 409 WAITLIST_FULL"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    err(reg(client, librarian, e["id"], m3["id"]), 409, "WAITLIST_FULL")


def test_t_evt_22_a(client, admin, librarian, branch_a):
    """T-EVT-22-a (LIB-EVT-22): Order M2 (registered), M3 (waitlisted), M1 (cancelled); status=waitlisted → M3; M3's list has event_title"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, title="Şiir Akşamı")
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    r1 = register(client, librarian, e["id"], m1)
    ok(cancel_reg(client, librarian, r1["id"]))
    register(client, librarian, e["id"], m2); register(client, librarian, e["id"], m3)
    assert [x["member_id"] for x in regs_of(client, librarian, e["id"])] == [m2["id"], m3["id"], m1["id"]]
    assert [x["member_id"] for x in regs_of(client, librarian, e["id"], status="waitlisted")] == [m3["id"]]
    own = items(get(client, member_headers(client, m3), f"members/{m3['id']}/event-registrations"))
    assert [(x["event_title"], x["event_date"], x["start_time"]) for x in own] == [("Şiir Akşamı", WED, "14:00")]


def test_t_evt_24_a(client, admin, librarian, branch_a):
    """T-EVT-24-a (LIB-EVT-24): 201; 409 EVENT_NOT_FOR_TYPE; 201; 409 EVENT_NOT_FOR_TYPE"""
    sid = on_shift(client, admin, branch_a, WED)
    stu = published(client, librarian, branch_a, sid, audience="students", start="10:00", end="11:00")
    allx = published(client, librarian, branch_a, sid, start="12:00", end="13:00")
    aca = published(client, librarian, branch_a, sid, audience="academics", start="14:00", end="15:00")
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    g, st = member(client, librarian, branch_a, membership_type="guest"), member(client, librarian, branch_a, membership_type="staff")
    ok(reg(client, librarian, stu["id"], s["id"]), 201)
    err(reg(client, librarian, stu["id"], a["id"]), 409, "EVENT_NOT_FOR_TYPE")
    ok(reg(client, librarian, allx["id"], g["id"]), 201)
    err(reg(client, librarian, aca["id"], st["id"]), 409, "EVENT_NOT_FOR_TYPE")


def test_t_evt_26_a(client, clock, admin, librarian, branch_a):
    """T-EVT-26-a (LIB-EVT-26): 201; 409 REGISTRATION_CLOSED"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, TUE, start="10:00", end="20:00"), day=TUE, start="18:00", end="19:00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 16, 59)
    ok(reg(client, librarian, e["id"], m1["id"]), 201)
    at(clock, TUE, 17, 0)
    err(reg(client, librarian, e["id"], m2["id"]), 409, "REGISTRATION_CLOSED")


def test_t_evt_27_b(client, clock, admin, librarian, branch_a):
    """T-EVT-27-b (LIB-EVT-27): 409 EVENT_STARTED"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED))
    r = register(client, librarian, e["id"], member(client, librarian, branch_a))
    at(clock, WED, 14)
    err(cancel_reg(client, librarian, r["id"]), 409, "EVENT_STARTED")


def test_t_evt_28_a(client, admin, librarian, branch_a):
    """T-EVT-28-a (LIB-EVT-28): Fee waived; late_cancellation false"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="30.00")
    m = member(client, librarian, branch_a)
    r = register(client, librarian, e["id"], m)
    assert ok(cancel_reg(client, member_headers(client, m), r["id"]))["late_cancellation"] is False
    assert fees_of(client, librarian, m["id"]) == [("event_fee", "30.00", "waived")]


def test_t_evt_30_a(client, clock, admin, librarian, branch_a):
    """T-EVT-30-a (LIB-EVT-30): M1 in time (fee waived); M2 late (fee open)"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, THU, start="10:00", end="20:00"), day=THU, start="18:00", end="19:00", fee="10.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1, r2 = register(client, librarian, e["id"], m1), register(client, librarian, e["id"], m2)
    at(clock, WED, 18, 0, 0)
    assert ok(cancel_reg(client, librarian, r1["id"]))["late_cancellation"] is False
    at(clock, WED, 18, 0, 1)
    assert ok(cancel_reg(client, librarian, r2["id"]))["late_cancellation"] is True
    assert (fees_of(client, librarian, m1["id"])[0][2], fees_of(client, librarian, m2["id"])[0][2]) == ("waived", "open")


def test_t_evt_32_a(client, clock, admin, librarian, branch_a):
    """T-EVT-32-a (LIB-EVT-32): 409 CHECK_IN_NOT_OPEN; 200 attended; 409 EVENT_OVER; 409 REGISTRATION_NOT_ACTIVE"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=2)
    ms = [member(client, librarian, branch_a) for _ in range(3)]
    r1, r2, r3 = (register(client, librarian, e["id"], m) for m in ms)
    at(clock, WED, 13, 29)
    err(post(client, librarian, f"event-registrations/{r1['id']}/check-in"), 409, "CHECK_IN_NOT_OPEN")
    at(clock, WED, 13, 30)
    out = ok(post(client, librarian, f"event-registrations/{r1['id']}/check-in"))
    assert out["status"] == "attended" and same(out["attended_at"], WED, 13, 30)
    err(post(client, librarian, f"event-registrations/{r3['id']}/check-in"), 409, "REGISTRATION_NOT_ACTIVE")
    at(clock, WED, 16)
    err(post(client, librarian, f"event-registrations/{r2['id']}/check-in"), 409, "EVENT_OVER")


def test_t_evt_33_b(client, clock, admin, librarian, branch_a):
    """T-EVT-33-b (LIB-EVT-33): reminders 0, 1, 0; M1 has one event_reminder, M2 none"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, THU), day=THU, start="10:00", end="11:00", capacity=1)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    at(clock, WED, 9, 59)
    assert process(client, librarian)["reminders"] == 0
    at(clock, WED, 10)
    assert process(client, librarian)["reminders"] == 1
    assert process(client, librarian)["reminders"] == 0
    assert [len(notes(client, librarian, m["id"], "event_reminder")) for m in (m1, m2)] == [1, 0]


def test_t_evt_34_a(client, clock, admin, librarian, branch_a):
    """T-EVT-34-a (LIB-EVT-34): No ban after two no-shows (bans 0); the member can still register"""
    sid = on_shift(client, admin, branch_a, WED, "2026-11-11", "2026-11-18")
    evs = [published(client, librarian, branch_a, sid, day=d) for d in (WED, "2026-11-11", "2026-11-18")]
    m = member(client, librarian, branch_a)
    for e in evs[:2]:
        register(client, librarian, e["id"], m)
    for d in (WED, "2026-11-11"):
        at(clock, d, 17)
        assert process(client, librarian)["bans"] == 0
    ok(reg(client, librarian, evs[2]["id"], m["id"]), 201)


def test_t_evt_36_a(client, clock, admin, librarian, branch_a):
    """T-EVT-36-a (LIB-EVT-36): Third process: bans 1; ban 2026-11-17 – 2026-12-16 with one event_ban_started notification; 409 MEMBER_BANNED_FROM_EVENTS with details.ends_on 2026-12-16"""
    days = (TUE, "2026-11-10", "2026-11-17")
    sid = on_shift(client, admin, branch_a, *days, "2026-11-25")
    evs = [published(client, librarian, branch_a, sid, day=d, start="10:00", end="11:00") for d in days]
    other = published(client, librarian, branch_a, sid, day="2026-11-25")
    m = member(client, librarian, branch_a)
    for e in evs:
        register(client, librarian, e["id"], m)
    results = []
    for d in days:
        at(clock, d, 12)
        results.append(process(client, librarian)["bans"])
    assert results == [0, 0, 1]
    bans = items(get(client, librarian, f"members/{m['id']}/event-bans"))
    assert [(b["starts_on"], b["ends_on"]) for b in bans] == [("2026-11-17", "2026-12-16")]
    assert len(notes(client, librarian, m["id"], "event_ban_started")) == 1
    assert err(reg(client, librarian, other["id"], m["id"]), 409, "MEMBER_BANNED_FROM_EVENTS")["details"]["ends_on"] == "2026-12-16"


def test_t_evt_38_a(client, admin, librarian, branch_a):
    """T-EVT-38-a (LIB-EVT-38): Fee paid 15.00, outstanding 25.00; outstanding_fees 25.00; fee list kind=event_fee has it"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), fee="40.00")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    pay(client, librarian, m["id"], "15.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["paid_amount"], fee["outstanding"]) == ("15.00", "25.00")
    assert balance(client, librarian, m["id"])["outstanding_fees"] == "25.00"
    assert [f["id"] for f in items(get(client, librarian, "fees", kind="event_fee"))] == [fee["id"]]


def test_t_evt_40_a(client, admin, librarian, branch_a):
    """T-EVT-40-a (LIB-EVT-40): 200; M1's registration cancelled with member_deactivated, fee stays open; M2 registered"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), capacity=1, fee="12.00")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    register(client, librarian, e["id"], m1); register(client, librarian, e["id"], m2)
    deactivate_member(client, librarian, m1["id"])
    assert reg_of(client, librarian, e["id"], m1["id"])["cancel_reason"] == "member_deactivated"
    assert fees_of(client, librarian, m1["id"]) == [("event_fee", "12.00", "open")]
    assert reg_of(client, librarian, e["id"], m2["id"])["status"] == "registered"


def test_t_evt_42_a(client, admin, librarian, branch_a):
    """T-EVT-42-a (LIB-EVT-42): 409 BRANCH_IN_USE"""
    qq = create_branch(client, admin, "QQ")
    event(client, librarian, qq, staff(client, admin, branch_a))
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_t_evt_44_b(client, admin, librarian, branch_a):
    """T-EVT-44-b (LIB-EVT-44): The event_cancelled notification has event_id and contains the title and the date"""
    e = published(client, librarian, branch_a, on_shift(client, admin, branch_a, WED), title="Masal Saati")
    m = member(client, librarian, branch_a)
    register(client, librarian, e["id"], m)
    ok(post(client, librarian, f"events/{e['id']}/cancel"))
    n = notes(client, librarian, m["id"], "event_cancelled")[0]
    assert n["event_id"] == e["id"] and "Masal Saati" in n["message"] and WED in n["message"]


def test_t_evt_46_b(client, librarian, branch_a):
    """T-EVT-46-b (LIB-EVT-46): 422; 422; 403"""
    url = "/api/v1/reports/event-attendance"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": WED}).status_code == 403
