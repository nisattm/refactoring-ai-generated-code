"""Heldout tests: module 15 (Study rooms). Generated from cases/rooms.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, items, lend,
    member_fees, member_headers, register_member, return_loan, update_member,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
TUE = "2026-11-03"  # the clock starts on Monday 2026-11-02 09:00 (conftest.py)


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def room(client, admin, branch, *, kind="individual", code=None, expect=201, **fields):
    """Room open 08:00-20:00; group rooms have capacity 6 and min_participants 2 unless given."""
    _seq[0] += 1
    body = {"branch_id": branch["id"], "code": code or f"R{_seq[0]}", "name": f"Room {_seq[0]}", "kind": kind,
            "opens_at": "08:00", "closes_at": "20:00"}
    if kind == "group":
        body.update(capacity=6, min_participants=2)
    body.update(fields)
    r = client.post("/api/v1/rooms", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def try_book(client, headers, room_id, date, start, end, **kw):
    body = {"room_id": room_id, "date": date, "start_time": start, "end_time": end, **kw}
    return client.post("/api/v1/room-bookings", headers=headers, json=body)


def book(client, headers, room_id, date, start, end, **kw):
    r = try_book(client, headers, room_id, date, start, end, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def act(client, headers, booking_id, action, json=None):
    return client.post(f"/api/v1/room-bookings/{booking_id}/{action}", headers=headers, json=json)


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def get_booking(client, headers, booking_id):
    return ok(client.get(f"/api/v1/room-bookings/{booking_id}", headers=headers))


def process(client, lib):
    return ok(client.post("/api/v1/room-bookings/process", headers=lib))


def notes(client, lib, member_id, type_):
    r = client.get(f"/api/v1/members/{member_id}/notifications", headers=lib, params={"type": type_})
    return items(ok(r))


def bans(client, lib, member_id):
    return items(ok(client.get(f"/api/v1/members/{member_id}/room-bans", headers=lib)))


def staff_ban(client, admin, member_id, starts_on, ends_on, note=""):
    r = client.post(f"/api/v1/members/{member_id}/room-bans", headers=admin,
                    json={"starts_on": starts_on, "ends_on": ends_on, "note": note})
    return r


def no_show(client, clock, lib, room_id, organizer, day):
    """Book `day` 10:00-11:00 the day before at 09:00 (or `day` itself if it is today) and process at 10:16."""
    b = book(client, lib, room_id, day, "10:00", "11:00", member_id=organizer["id"])
    at(clock, day, 10, 16)
    assert process(client, lib)["no_shows"] >= 1
    return b


def test_t_room_01_b(client, admin, branch_a, branch_b):
    """T-ROOM-01-b (LIB-ROOM-01): 409 CONFLICT with details.field code; 201 in branch B"""
    room(client, admin, branch_a, code="G1")
    body = {"branch_id": branch_a["id"], "code": "G1", "name": "Other", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    e = err(client.post("/api/v1/rooms", headers=admin, json=body), 409, "CONFLICT")
    assert e["details"]["field"] == "code"
    room(client, admin, branch_b, code="G1")


def test_t_room_01_d(client, librarian, branch_a):
    """T-ROOM-01-d (LIB-ROOM-01): 403 FORBIDDEN"""
    room(client, librarian, branch_a, expect=403)


def test_t_room_02_b(client, admin, branch_a, branch_b):
    """T-ROOM-02-b (LIB-ROOM-02): 422 VALIDATION_ERROR; branch unchanged"""
    r1 = room(client, admin, branch_a)
    assert client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"branch_id": branch_b["id"]}).status_code == 422
    assert ok(client.get(f"/api/v1/rooms/{r1['id']}", headers=admin))["branch_id"] == branch_a["id"]


def test_t_room_03_b(client, admin, librarian, branch_a):
    """T-ROOM-03-b (LIB-ROOM-03): Only the rooms matching every filter"""
    g6 = room(client, admin, branch_a, kind="group", features=["whiteboard", "projector"])
    room(client, admin, branch_a, kind="group", capacity=4, features=["whiteboard", "projector"])
    room(client, admin, branch_a, kind="group", features=["whiteboard"])
    room(client, admin, branch_a, features=["whiteboard", "projector"])
    params = [("kind", "group"), ("min_capacity", "5"), ("feature", "whiteboard"), ("feature", "projector")]
    assert [x["id"] for x in items(ok(client.get("/api/v1/rooms", headers=librarian, params=params)))] == [g6["id"]]


def test_t_room_04_b(client, admin, branch_a):
    """T-ROOM-04-b (LIB-ROOM-04): 422 VALIDATION_ERROR both"""
    g = room(client, admin, branch_a, kind="group")
    assert client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"min_participants": 7}).status_code == 422
    assert client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"kind": "individual"}).status_code == 422


def test_t_room_05_b(client, admin, librarian, branch_a):
    """T-ROOM-05-b (LIB-ROOM-05): 409 ROOM_HAS_BOOKINGS both"""
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2, p3 = (member(client, librarian, branch_a) for _ in range(4))
    book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"], p2["id"], p3["id"]])
    for fields in ({"capacity": 3}, {"min_participants": 5}):
        err(client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json=fields), 409, "ROOM_HAS_BOOKINGS")


def test_t_room_06_b(client, admin, librarian, branch_a):
    """T-ROOM-06-b (LIB-ROOM-06): 409 ROOM_INACTIVE"""
    r1 = room(client, admin, branch_a)
    client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False})
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "ROOM_INACTIVE")


def test_t_room_08_b(client, admin, librarian, branch_a):
    """T-ROOM-08-b (LIB-ROOM-08): open false and slots []; 422 VALIDATION_ERROR"""
    r1 = room(client, admin, branch_a)
    a = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": "2026-11-07"}))
    assert a["open"] is False and a["slots"] == []
    assert client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian).status_code == 422


def test_t_room_09_b(client, admin, librarian, branch_a):
    """T-ROOM-09-b (LIB-ROOM-09): 422 VALIDATION_ERROR both"""
    room(client, admin, branch_a)
    for s, e in (("10:15", "11:00"), ("11:00", "10:00")):
        assert client.get("/api/v1/rooms/free", headers=librarian, params={"date": TUE, "start_time": s, "end_time": e}).status_code == 422


def test_t_room_10_b(client, admin, librarian, branch_a):
    """T-ROOM-10-b (LIB-ROOM-10): 422 VALIDATION_ERROR both"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    assert try_book(client, librarian, r1["id"], TUE, "10:00", "11:00").status_code == 422
    assert try_book(client, member_headers(client, m), r1["id"], TUE, "10:00", "11:00", member_id=m["id"]).status_code == 422


def test_t_room_11_b(client, admin, librarian, branch_a):
    """T-ROOM-11-b (LIB-ROOM-11): 201; 201; 422 VALIDATION_ERROR"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    book(client, librarian, r1["id"], TUE, "08:00", "08:30", member_id=m["id"])
    book(client, librarian, r2["id"], "2026-11-04", "10:00", "14:00", member_id=m["id"])
    assert try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "14:30", member_id=m["id"]).status_code == 422


def test_t_room_12_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-12-b (LIB-ROOM-12): 201; 409 MEMBERSHIP_EXPIRED"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2027-10-28")
    book(client, librarian, r1["id"], "2027-11-01", "10:00", "11:00", member_id=m["id"])
    err(try_book(client, librarian, r1["id"], "2027-11-02", "10:00", "11:00", member_id=m["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_room_12_d(client, admin, librarian, branch_a):
    """T-ROOM-12-d (LIB-ROOM-12): 409 MEMBER_BANNED_FROM_ROOMS with details.ends_on 2026-11-05 (in force today)"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-05"), 201)
    e = err(try_book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_BANNED_FROM_ROOMS")
    assert e["details"]["ends_on"] == "2026-11-05"


def test_t_room_12_f(client, admin, librarian, branch_a):
    """T-ROOM-12-f (LIB-ROOM-12): 409 ROOM_CLOSED"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], "2026-11-07", "10:00", "11:00", member_id=m["id"]), 409, "ROOM_CLOSED")


def test_t_room_12_h(client, admin, librarian, branch_a):
    """T-ROOM-12-h (LIB-ROOM-12): 409 BOOKING_IN_PAST; 201"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], "2026-11-02", "09:00", "09:30", member_id=m["id"]), 409, "BOOKING_IN_PAST")
    book(client, librarian, r1["id"], "2026-11-02", "09:30", "10:00", member_id=m["id"])


def test_t_room_12_j(client, admin, librarian, branch_a):
    """T-ROOM-12-j (LIB-ROOM-12): 201; 409 BOOKING_TOO_FAR_AHEAD"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    book(client, librarian, r1["id"], "2026-11-16", "10:00", "11:00", member_id=m["id"])
    err(try_book(client, librarian, r1["id"], "2026-11-17", "10:00", "11:00", member_id=m["id"]), 409, "BOOKING_TOO_FAR_AHEAD")


def test_t_room_12_l(client, admin, librarian, branch_a):
    """T-ROOM-12-l (LIB-ROOM-12): 409 ROOM_ALREADY_BOOKED"""
    r1 = room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    err(try_book(client, librarian, r1["id"], TUE, "10:30", "11:30", member_id=b["id"]), 409, "ROOM_ALREADY_BOOKED")


def test_t_room_13_b(client, admin, librarian, branch_a):
    """T-ROOM-13-b (LIB-ROOM-13): 404 NOT_FOUND"""
    g = room(client, admin, branch_a, kind="group")
    o = member(client, librarian, branch_a)
    err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[999999]), 404, "NOT_FOUND")


def test_t_room_13_d(client, admin, librarian, branch_a):
    """T-ROOM-13-d (LIB-ROOM-13): 409 ROOM_CAPACITY_EXCEEDED with details.capacity 3"""
    g = room(client, admin, branch_a, kind="group", capacity=3, min_participants=2)
    o, *ps = (member(client, librarian, branch_a) for _ in range(4))
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"] for p in ps]), 409, "ROOM_CAPACITY_EXCEEDED")
    assert e["details"]["capacity"] == 3


def test_t_room_13_f(client, admin, librarian, branch_a):
    """T-ROOM-13-f (LIB-ROOM-13): 201; participant_ids ascending"""
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"], p1["id"]])
    assert b["participant_ids"] == [p1["id"], p2["id"]]


def test_t_room_14_a(client, admin, librarian, branch_a):
    """T-ROOM-14-a (LIB-ROOM-14): All 201 (touching intervals do not overlap)"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "09:00", "10:00", member_id=a["id"])
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=b["id"])
    book(client, librarian, r2["id"], TUE, "10:00", "10:30", member_id=a["id"])


def test_t_room_15_b(client, admin, librarian, branch_a):
    """T-ROOM-15-b (LIB-ROOM-15): 409 WEEKLY_ROOM_QUOTA_EXCEEDED, used '6.5'"""
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o = member(client, librarian, branch_a, membership_type="academic")
    s = member(client, librarian, branch_a)
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        book(client, librarian, g["id"], day, "14:00", "16:00", member_id=o["id"], participant_ids=[s["id"]])
    e = err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "10:30", member_id=s["id"]), 409, "WEEKLY_ROOM_QUOTA_EXCEEDED")
    assert (e["details"]["member_id"], e["details"]["used"]) == (s["id"], "6.5")


def test_t_room_15_d(client, admin, librarian, branch_a):
    """T-ROOM-15-d (LIB-ROOM-15): 409 DAILY_ROOM_QUOTA_EXCEEDED with details.member_id P"""
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=p["id"])
    e = err(try_book(client, librarian, g["id"], TUE, "14:00", "15:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"]["member_id"] == p["id"]


def test_t_room_16_b(client, admin, librarian, branch_a):
    """T-ROOM-16-b (LIB-ROOM-16): 409 WEEKLY_ROOM_QUOTA_EXCEEDED; 201"""
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o = member(client, librarian, branch_a, membership_type="academic")
    s = member(client, librarian, branch_a)
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        book(client, librarian, g["id"], day, "14:00", "16:00", member_id=o["id"], participant_ids=[s["id"]])
    err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=s["id"]), 409, "WEEKLY_ROOM_QUOTA_EXCEEDED")
    book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=s["id"])


def test_t_room_18_b(client, admin, librarian, branch_a):
    """T-ROOM-18-b (LIB-ROOM-18): Only the matching bookings"""
    r1, g = room(client, admin, branch_a), room(client, admin, branch_a, kind="group")
    a, b, p = (member(client, librarian, branch_a) for _ in range(3))
    t = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    w = book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=b["id"])
    gb = book(client, librarian, g["id"], "2026-11-05", "10:00", "11:00", member_id=a["id"], participant_ids=[p["id"]])
    ok(act(client, librarian, t["id"], "cancel"))
    get = lambda **q: [x["id"] for x in items(ok(client.get("/api/v1/room-bookings", headers=librarian, params=q)))]
    assert get(status="cancelled") == [t["id"]]
    assert get(**{"from": "2026-11-04", "to": "2026-11-04"}) == [w["id"]]
    assert get(member_id=p["id"]) == [gb["id"]]


def test_t_room_20_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-20-b (LIB-ROOM-20): 409 BOOKING_NOT_CHANGEABLE both"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    started = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    cancelled = book(client, librarian, r2["id"], TUE, "14:00", "15:00", member_id=b["id"])
    ok(act(client, librarian, cancelled["id"], "cancel"))
    at(clock, TUE, 10, 5)
    for bk in (started, cancelled):
        err(client.patch(f"/api/v1/room-bookings/{bk['id']}", headers=librarian, json={"purpose": "x"}), 409, "BOOKING_NOT_CHANGEABLE")


def test_t_room_21_b(client, admin, librarian, branch_a):
    """T-ROOM-21-b (LIB-ROOM-21): Booking cancelled with not_enough_participants"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ok(act(client, member_headers(client, p), b["id"], "leave"))
    g2 = get_booking(client, librarian, b["id"])
    assert (g2["status"], g2["cancel_reason"]) == ("cancelled", "not_enough_participants")


def test_t_room_22_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-22-b (LIB-ROOM-22): staff_request, late_cancellation false"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 9, 30)
    r = ok(act(client, librarian, b["id"], "cancel"))
    assert (r["cancel_reason"], r["late_cancellation"]) == ("staff_request", False)


def test_t_room_24_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-24-a (LIB-ROOM-24): A not late; B late"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "14:00", "15:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "14:00", "15:00", member_id=b["id"])
    ha, hb = member_headers(client, a), member_headers(client, b)
    at(clock, TUE, 12, 0)
    assert ok(act(client, ha, ba["id"], "cancel"))["late_cancellation"] is False
    at(clock, TUE, 12, 1)
    assert ok(act(client, hb, bb["id"], "cancel"))["late_cancellation"] is True
    assert member_fees(client, librarian, b["id"])["total"] == 0


def test_t_room_26_a(client, admin, librarian, branch_a):
    """T-ROOM-26-a (LIB-ROOM-26): Organizer and P each get a room_booking_cancelled notification"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"is_active": False})
    for m in (o, p):
        ns = notes(client, librarian, m["id"], "room_booking_cancelled")
        assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]


def test_t_room_27_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-27-b (LIB-ROOM-27): A 200; B 409 CHECK_IN_TOO_LATE"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    at(clock, TUE, 10, 15)
    ok(act(client, librarian, ba["id"], "check-in"))
    at(clock, TUE, 10, 16)
    err(act(client, librarian, bb["id"], "check-in"), 409, "CHECK_IN_TOO_LATE")


def test_t_room_28_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-28-b (LIB-ROOM-28): 0 no-shows; then 1"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 10, 15)
    assert process(client, librarian)["no_shows"] == 0
    at(clock, TUE, 10, 16)
    assert process(client, librarian)["no_shows"] == 1


def test_t_room_29_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-29-b (LIB-ROOM-29): A end_time 10:30 (minimum 30 minutes); B end_time 11:00 (not later than before)"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    at(clock, TUE, 10, 0)
    ok(act(client, librarian, ba["id"], "check-in")); ok(act(client, librarian, bb["id"], "check-in"))
    at(clock, TUE, 10, 5)
    assert ok(act(client, librarian, ba["id"], "check-out"))["end_time"] == "10:30"
    at(clock, TUE, 11, 10)
    assert ok(act(client, librarian, bb["id"], "check-out"))["end_time"] == "11:00"


def test_t_room_30_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-30-b (LIB-ROOM-30): outstanding_fees '10.00', total_debt '10.00'"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, TUE)
    bal = balance(client, librarian, m["id"])
    assert (bal["outstanding_fees"], bal["total_debt"]) == ("10.00", "10.00")


def test_t_room_31_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-31-b (LIB-ROOM-31): No second ban (earlier incidents do not count again)"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for day in ("2026-11-03", "2026-11-04", "2026-11-05"):
        no_show(client, clock, librarian, r1["id"], m, day)
    at(clock, "2026-11-19")
    book(client, librarian, r1["id"], "2026-11-20", "10:00", "11:00", member_id=m["id"])
    at(clock, "2026-11-20", 10, 16)
    assert process(client, librarian)["bans"] == 0
    assert len(bans(client, librarian, m["id"])) == 1


def test_t_room_32_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-32-b (LIB-ROOM-32): No ban"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, "2026-11-03")
    at(clock, "2026-12-02"); no_show(client, clock, librarian, r1["id"], m, "2026-12-03")
    no_show(client, clock, librarian, r1["id"], m, "2026-12-04")
    assert bans(client, librarian, m["id"]) == []


def test_t_room_33_b(client, admin, librarian, branch_a):
    """T-ROOM-33-b (LIB-ROOM-33): Member removed; booking cancelled with not_enough_participants"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ok(staff_ban(client, admin, p["id"], TUE, "2026-11-10"), 201)
    r = get_booking(client, librarian, b["id"])
    assert (r["participant_ids"], r["status"], r["cancel_reason"]) == ([], "cancelled", "not_enough_participants")


def test_t_room_34_a(client, admin, librarian, branch_a):
    """T-ROOM-34-a (LIB-ROOM-34): 422; 422; 403"""
    m = member(client, librarian, branch_a)
    assert staff_ban(client, admin, m["id"], "2026-11-01", "2026-11-05").status_code == 422
    assert staff_ban(client, admin, m["id"], "2026-11-05", "2026-11-04").status_code == 422
    assert staff_ban(client, librarian, m["id"], "2026-11-02", "2026-11-05").status_code == 403


def test_t_room_36_a(client, admin, librarian, branch_a):
    """T-ROOM-36-a (LIB-ROOM-36): Order: the 11-10 ban first; in_force false and true"""
    m = member(client, librarian, branch_a)
    ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-03"), 201)
    ok(staff_ban(client, admin, m["id"], "2026-11-10", "2026-11-12"), 201)
    assert [(x["starts_on"], x["in_force"]) for x in bans(client, librarian, m["id"])] == [("2026-11-10", False), ("2026-11-02", True)]


def test_t_room_37_b(client, clock, admin, librarian, branch_a):
    """T-ROOM-37-b (LIB-ROOM-37): 409 MEMBER_IN_ROOM"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    err(client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian), 409, "MEMBER_IN_ROOM")


def test_t_room_38_a(client, admin, librarian, branch_a):
    """T-ROOM-38-a (LIB-ROOM-38): Booking cancelled with staff_request"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    update_member(client, librarian, m["id"], membership_type="guest", phone="905551234567")
    g = get_booking(client, librarian, b["id"])
    assert (g["status"], g["cancel_reason"]) == ("cancelled", "staff_request")


def test_t_room_40_a(client, admin, librarian, branch_a):
    """T-ROOM-40-a (LIB-ROOM-40): rooms = {upcoming_bookings: 1, banned_until: null, hours_this_week: '1.0'}"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    s = ok(client.get(f"/api/v1/members/{m['id']}/summary", headers=librarian))
    assert s["rooms"] == {"upcoming_bookings": 1, "banned_until": None, "hours_this_week": "1.0"}


def test_t_room_41_b(client, admin, librarian, branch_a):
    """T-ROOM-41-b (LIB-ROOM-41): P gets one room_participant_added; the organizer gets none"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ns = notes(client, librarian, p["id"], "room_participant_added")
    assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]
    assert notes(client, librarian, o["id"], "room_participant_added") == []


def test_t_room_42_a(client, admin, librarian, branch_a):
    """T-ROOM-42-a (LIB-ROOM-42): {room_reminders: 2}, then 0; loan reminders unchanged {due_reminders: 0, overdue_notices: 0}"""
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=x["id"])
    assert ok(client.post("/api/v1/room-bookings/run-reminders", headers=librarian)) == {"room_reminders": 2}
    assert ok(client.post("/api/v1/room-bookings/run-reminders", headers=librarian)) == {"room_reminders": 0}
    assert ok(client.post("/api/v1/notifications/run-reminders", headers=librarian)) == {"due_reminders": 0, "overdue_notices": 0}


def test_t_room_44_b(client, librarian, branch_a):
    """T-ROOM-44-b (LIB-ROOM-44): 422; 422; 403"""
    url = "/api/v1/reports/room-usage"
    assert client.get(url, headers=librarian, params={"from": "2026-11-06", "to": "2026-11-02"}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    assert client.get(url, headers=member_headers(client, m), params={"from": "2026-11-02", "to": "2026-11-06"}).status_code == 403
