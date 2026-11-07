"""Feedback tests: module 15 (Study rooms). Generated from cases/rooms.md."""
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


def test_t_room_01_a(client, admin, branch_a):
    """T-ROOM-01-a (LIB-ROOM-01): 201; capacity 1, min_participants 1, features [], code RA1, active"""
    body = {"branch_id": branch_a["id"], "code": "ra1", "name": "Quiet room", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    r = ok(client.post("/api/v1/rooms", headers=admin, json=body), 201)
    assert (r["capacity"], r["min_participants"], r["features"], r["code"], r["is_active"]) == (1, 1, [], "RA1", True)


def test_t_room_01_c(client, admin, branch_a):
    """T-ROOM-01-c (LIB-ROOM-01): 422 VALIDATION_ERROR each"""
    bad = [dict(kind="group", capacity=2, min_participants=2), dict(kind="group", capacity=6, min_participants=1),
           dict(capacity=2), dict(opens_at="07:15"), dict(closes_at="23:30"), dict(opens_at="10:00", closes_at="10:00"),
           dict(features=["sofa"]), dict(features=["projector", "projector"])]
    for fields in bad:
        room(client, admin, branch_a, expect=422, **fields)


def test_t_room_02_a(client, admin):
    """T-ROOM-02-a (LIB-ROOM-02): 409 BRANCH_INACTIVE"""
    br = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, br["id"])
    body = {"branch_id": br["id"], "code": "X1", "name": "X", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    err(client.post("/api/v1/rooms", headers=admin, json=body), 409, "BRANCH_INACTIVE")


def test_t_room_03_a(client, admin, librarian, branch_a, branch_b):
    """T-ROOM-03-a (LIB-ROOM-03): Order AB, BB, AA (branch, then code); filter gives AA"""
    room(client, admin, branch_a, code="BB"); room(client, admin, branch_a, code="AB"); room(client, admin, branch_b, code="AA")
    assert [x["code"] for x in items(ok(client.get("/api/v1/rooms", headers=librarian)))] == ["AB", "BB", "AA"]
    r = ok(client.get("/api/v1/rooms", headers=librarian, params={"branch_id": branch_b["id"]}))
    assert [x["code"] for x in items(r)] == ["AA"]


def test_t_room_04_a(client, admin, branch_a):
    """T-ROOM-04-a (LIB-ROOM-04): 200 with the new values"""
    r1 = room(client, admin, branch_a)
    r = ok(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"name": "Renamed", "closes_at": "21:00"}))
    assert (r["name"], r["closes_at"]) == ("Renamed", "21:00")


def test_t_room_05_a(client, admin, librarian, branch_a):
    """T-ROOM-05-a (LIB-ROOM-05): 409 ROOM_HAS_BOOKINGS, details.booking_ids [id]; hours unchanged"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "18:00", "19:00", member_id=m["id"])
    e = err(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"closes_at": "18:00"}), 409, "ROOM_HAS_BOOKINGS")
    assert e["details"]["booking_ids"] == [b["id"]]
    assert ok(client.get(f"/api/v1/rooms/{r1['id']}", headers=admin))["closes_at"] == "20:00"


def test_t_room_06_a(client, admin, librarian, branch_a):
    """T-ROOM-06-a (LIB-ROOM-06): Room inactive; booking cancelled with room_closed, late_cancellation false"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    assert ok(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False}))["is_active"] is False
    g = get_booking(client, librarian, b["id"])
    assert (g["status"], g["cancel_reason"], g["late_cancellation"]) == ("cancelled", "room_closed", False)


def test_t_room_07_a(client, admin, librarian, branch_a):
    """T-ROOM-07-a (LIB-ROOM-07): Slots 09:00, 09:30, 10:00, 10:30, each 30 minutes, all free"""
    r1 = room(client, admin, branch_a, opens_at="09:00", closes_at="11:00")
    a = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))
    assert a["open"] is True
    assert [(s["start"], s["end"], s["free"]) for s in a["slots"]] == [("09:00", "09:30", True), ("09:30", "10:00", True), ("10:00", "10:30", True), ("10:30", "11:00", True)]


def test_t_room_08_a(client, admin, librarian, branch_a):
    """T-ROOM-08-a (LIB-ROOM-08): 09:30 and 10:00 not free with the booking id; 09:00 and 10:30 free"""
    r1 = room(client, admin, branch_a, opens_at="09:00", closes_at="11:00")
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "09:30", "10:30", member_id=m["id"])
    slots = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))["slots"]
    assert [(s["free"], s["booking_id"]) for s in slots] == [(True, None), (False, b["id"]), (False, b["id"]), (True, None)]


def test_t_room_08_c(client, admin, librarian, branch_a):
    """T-ROOM-08-c (LIB-ROOM-08): A sees the booking id; B sees booking_id null and free false"""
    r1 = room(client, admin, branch_a, opens_at="10:00", closes_at="11:00")
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    bk = book(client, member_headers(client, a), r1["id"], TUE, "10:00", "10:30")
    sa = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=member_headers(client, a), params={"date": TUE}))["slots"][0]
    sb = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=member_headers(client, b), params={"date": TUE}))["slots"][0]
    assert sa["booking_id"] == bk["id"] and sb["booking_id"] is None and sb["free"] is False


def test_t_room_09_a(client, admin, librarian, branch_a):
    """T-ROOM-09-a (LIB-ROOM-09): Only R1"""
    r1 = room(client, admin, branch_a); r2 = room(client, admin, branch_a)
    room(client, admin, branch_a, opens_at="12:00"); r4 = room(client, admin, branch_a)
    client.patch(f"/api/v1/rooms/{r4['id']}", headers=admin, json={"is_active": False})
    m = member(client, librarian, branch_a)
    book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=m["id"])
    r = ok(client.get("/api/v1/rooms/free", headers=librarian, params={"date": TUE, "start_time": "10:30", "end_time": "11:30"}))
    assert [x["id"] for x in items(r)] == [r1["id"]]


def test_t_room_10_a(client, admin, librarian, branch_a):
    """T-ROOM-10-a (LIB-ROOM-10): 201; own member_id, booked, participant_ids [], purpose '', duration_minutes 60, room_code, branch_id"""
    r1 = room(client, admin, branch_a, code="QA")
    m = member(client, librarian, branch_a)
    b = book(client, member_headers(client, m), r1["id"], TUE, "10:00", "11:00")
    assert (b["member_id"], b["status"], b["participant_ids"], b["purpose"], b["duration_minutes"]) == (m["id"], "booked", [], "", 60)
    assert (b["room_code"], b["branch_id"], b["date"], b["start_time"], b["end_time"]) == ("QA", branch_a["id"], TUE, "10:00", "11:00")


def test_t_room_11_a(client, admin, librarian, branch_a):
    """T-ROOM-11-a (LIB-ROOM-11): 422 VALIDATION_ERROR each"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for s, e in (("10:15", "11:00"), ("10:00", "10:00"), ("10:00", "11:45")):
        assert try_book(client, librarian, r1["id"], TUE, s, e, member_id=m["id"]).status_code == 422


def test_t_room_11_c(client, admin, librarian, branch_a):
    """T-ROOM-11-c (LIB-ROOM-11): 422 VALIDATION_ERROR both"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    for parts in ([p["id"], p["id"]], [o["id"], p["id"]]):
        assert try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=parts).status_code == 422


def test_t_room_12_a(client, admin, librarian, branch_a):
    """T-ROOM-12-a (LIB-ROOM-12): 409 MEMBER_PASSIVE"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_PASSIVE")


def test_t_room_12_c(client, admin, librarian, branch_a):
    """T-ROOM-12-c (LIB-ROOM-12): 409 ROOM_NOT_ALLOWED_FOR_TYPE"""
    r1 = room(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_book(client, member_headers(client, g), r1["id"], TUE, "10:00", "11:00"), 409, "ROOM_NOT_ALLOWED_FOR_TYPE")


def test_t_room_12_e(client, admin, librarian, branch_a):
    """T-ROOM-12-e (LIB-ROOM-12): 409 MEMBER_BLOCKED_BY_DEBT with details.total_debt '50.00'"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    copy = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], copy["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="50.00")
    e = err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"


def test_t_room_12_g(client, admin, librarian, branch_a):
    """T-ROOM-12-g (LIB-ROOM-12): 409 OUTSIDE_ROOM_HOURS twice; 201"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for s, e in (("07:30", "08:30"), ("19:30", "20:30")):
        err(try_book(client, librarian, r1["id"], TUE, s, e, member_id=m["id"]), 409, "OUTSIDE_ROOM_HOURS")
    book(client, librarian, r1["id"], TUE, "19:00", "20:00", member_id=m["id"])


def test_t_room_12_i(client, admin, librarian, branch_a):
    """T-ROOM-12-i (LIB-ROOM-12): 201; 409 BOOKING_TOO_FAR_AHEAD with details.latest_date 2026-11-09"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], "2026-11-10", "10:00", "11:00", member_id=m["id"]), 409, "BOOKING_TOO_FAR_AHEAD")
    assert e["details"]["latest_date"] == "2026-11-09"


def test_t_room_12_k(client, admin, librarian, branch_a):
    """T-ROOM-12-k (LIB-ROOM-12): ROOM_NOT_ALLOWED_FOR_TYPE (step 5 before 8); BRANCH_INACTIVE (step 1 before 2)"""
    r1 = room(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_book(client, librarian, r1["id"], "2026-11-07", "10:00", "11:00", member_id=g["id"]), 409, "ROOM_NOT_ALLOWED_FOR_TYPE")
    br = create_branch(client, admin, "YY")
    r2 = room(client, admin, br)
    client.patch(f"/api/v1/rooms/{r2['id']}", headers=admin, json={"is_active": False})
    deactivate_branch(client, admin, br["id"])
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "BRANCH_INACTIVE")


def test_t_room_12_m(client, admin, librarian, branch_a):
    """T-ROOM-12-m (LIB-ROOM-12): 409 MEMBER_DOUBLE_BOOKED with details.member_id"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r2["id"], TUE, "10:30", "11:00", member_id=m["id"]), 409, "MEMBER_DOUBLE_BOOKED")
    assert e["details"]["member_id"] == m["id"]


def test_t_room_13_a(client, admin, librarian, branch_a):
    """T-ROOM-13-a (LIB-ROOM-13): 409 PARTICIPANTS_NOT_ALLOWED"""
    r1 = room(client, admin, branch_a)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "PARTICIPANTS_NOT_ALLOWED")


def test_t_room_13_c(client, admin, librarian, branch_a):
    """T-ROOM-13-c (LIB-ROOM-13): 409 NOT_ENOUGH_PARTICIPANTS with details.min_participants 3"""
    g = room(client, admin, branch_a, kind="group", min_participants=3)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "NOT_ENOUGH_PARTICIPANTS")
    assert e["details"]["min_participants"] == 3


def test_t_room_13_e(client, admin, librarian, branch_a):
    """T-ROOM-13-e (LIB-ROOM-13): 409 PARTICIPANT_NOT_ELIGIBLE, member_id P1, reason MEMBER_PASSIVE; with P2 only: reason ROOM_NOT_ALLOWED_FOR_TYPE"""
    g = room(client, admin, branch_a, kind="group")
    o = member(client, librarian, branch_a)
    p1 = member(client, librarian, branch_a)
    p2 = member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, p1["id"])
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"], p1["id"]]), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert (e["details"]["member_id"], e["details"]["reason"]) == (p1["id"], "MEMBER_PASSIVE")
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"]]), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert e["details"]["reason"] == "ROOM_NOT_ALLOWED_FOR_TYPE"


def test_t_room_15_a(client, admin, librarian, branch_a):
    """T-ROOM-15-a (LIB-ROOM-15): 409 DAILY_ROOM_QUOTA_EXCEEDED with member_id, used '2.5'"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], TUE, "14:00", "14:30", member_id=m["id"]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert (e["details"]["member_id"], e["details"]["used"]) == (m["id"], "2.5")


def test_t_room_15_c(client, admin, librarian, branch_a):
    """T-ROOM-15-c (LIB-ROOM-15): 409 ROOM_BOOKING_LIMIT_REACHED with details.limit 2"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=m["id"]), 409, "ROOM_BOOKING_LIMIT_REACHED")
    assert e["details"]["limit"] == 2


def test_t_room_16_a(client, admin, librarian, branch_a):
    """T-ROOM-16-a (LIB-ROOM-16): 409 DAILY_ROOM_QUOTA_EXCEEDED with used '2.5'; 201"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:30", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], TUE, "12:00", "13:00", member_id=m["id"]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"]["used"] == "2.5"
    book(client, librarian, r1["id"], TUE, "12:00", "12:30", member_id=m["id"])


def test_t_room_17_a(client, admin, librarian, branch_a):
    """T-ROOM-17-a (LIB-ROOM-17): created_by = the librarian's user id; member_id = the member"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    me = ok(client.get("/api/v1/auth/me", headers=librarian))
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    assert (b["created_by"], b["member_id"]) == (me["id"], m["id"])


def test_t_room_18_a(client, admin, librarian, branch_a):
    """T-ROOM-18-a (LIB-ROOM-18): All-bookings list ordered by date, start; P's list contains the group booking"""
    r1, g = room(client, admin, branch_a), room(client, admin, branch_a, kind="group")
    a, b, c = (member(client, librarian, branch_a) for _ in range(3))
    w = book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=a["id"])
    t2 = book(client, librarian, r1["id"], TUE, "14:00", "15:00", member_id=b["id"])
    t1 = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=a["id"], participant_ids=[c["id"]])
    assert [x["id"] for x in items(ok(client.get("/api/v1/room-bookings", headers=librarian)))] == [t1["id"], t2["id"], w["id"]]
    assert [x["id"] for x in items(ok(client.get(f"/api/v1/members/{c['id']}/room-bookings", headers=librarian)))] == [t1["id"]]


def test_t_room_19_a(client, admin, librarian, branch_a):
    """T-ROOM-19-a (LIB-ROOM-19): 403 FORBIDDEN; 200"""
    g = room(client, admin, branch_a, kind="group")
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert client.get(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, x)).status_code == 403
    assert client.get(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, p)).status_code == 200


def test_t_room_20_a(client, admin, librarian, branch_a):
    """T-ROOM-20-a (LIB-ROOM-20): 200; participants ascending; purpose changed"""
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"]])
    r = ok(client.patch(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, o), json={"participant_ids": [p2["id"], p1["id"]], "purpose": "Project"}))
    assert (r["participant_ids"], r["purpose"]) == ([p1["id"], p2["id"]], "Project")


def test_t_room_21_a(client, admin, librarian, branch_a):
    """T-ROOM-21-a (LIB-ROOM-21): 200; participants [P2]; still booked"""
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"], p2["id"]])
    r = ok(act(client, member_headers(client, p1), b["id"], "leave"))
    assert (r["participant_ids"], r["status"]) == ([p2["id"]], "booked")


def test_t_room_21_c(client, admin, librarian, branch_a):
    """T-ROOM-21-c (LIB-ROOM-21): 403 FORBIDDEN"""
    g = room(client, admin, branch_a, kind="group")
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert act(client, member_headers(client, x), b["id"], "leave").status_code == 403


def test_t_room_22_a(client, admin, librarian, branch_a):
    """T-ROOM-22-a (LIB-ROOM-22): cancelled, member_request, not late; second 409 BOOKING_NOT_ACTIVE"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    h = member_headers(client, m)
    b = book(client, h, r1["id"], TUE, "10:00", "11:00")
    r = ok(act(client, h, b["id"], "cancel"))
    assert (r["status"], r["cancel_reason"], r["late_cancellation"]) == ("cancelled", "member_request", False) and r["closed_at"]
    err(act(client, h, b["id"], "cancel"), 409, "BOOKING_NOT_ACTIVE")


def test_t_room_22_c(client, admin, librarian, branch_a):
    """T-ROOM-22-c (LIB-ROOM-22): 403 FORBIDDEN"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert act(client, member_headers(client, p), b["id"], "cancel").status_code == 403


def test_t_room_23_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-23-a (LIB-ROOM-23): A: 200, late; B: 409 BOOKING_NOT_ACTIVE"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    ha, hb = member_headers(client, a), member_headers(client, b)
    at(clock, TUE, 10, 15)
    assert ok(act(client, ha, ba["id"], "cancel"))["late_cancellation"] is True
    at(clock, TUE, 10, 16)
    err(act(client, hb, bb["id"], "cancel"), 409, "BOOKING_NOT_ACTIVE")


def test_t_room_25_a(client, admin, librarian, branch_a):
    """T-ROOM-25-a (LIB-ROOM-25): 201 (the cancelled booking does not count)"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    ok(act(client, librarian, b["id"], "cancel"))
    book(client, librarian, r1["id"], TUE, "13:00", "15:00", member_id=m["id"])


def test_t_room_27_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-27-a (LIB-ROOM-27): 409 CHECK_IN_TOO_EARLY with details.earliest 09:50; then 200 checked_in"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 9, 49)
    e = err(act(client, librarian, b["id"], "check-in"), 409, "CHECK_IN_TOO_EARLY")
    assert e["details"]["earliest"] == "2026-11-03T09:50:00+03:00"
    at(clock, TUE, 9, 50)
    r = ok(act(client, librarian, b["id"], "check-in"))
    assert r["status"] == "checked_in" and r["checked_in_at"] == "2026-11-03T09:50:00+03:00"


def test_t_room_27_c(client, clock, admin, librarian, branch_a):
    """T-ROOM-27-c (LIB-ROOM-27): 409 BOOKING_NOT_ACTIVE"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    ok(act(client, librarian, b["id"], "cancel"))
    at(clock, TUE, 10, 0)
    err(act(client, librarian, b["id"], "check-in"), 409, "BOOKING_NOT_ACTIVE")


def test_t_room_28_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-28-a (LIB-ROOM-28): {no_shows: 1, completed: 1, bans: 0}; statuses completed and no_show"""
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    early = book(client, librarian, r1["id"], TUE, "08:00", "09:00", member_id=a["id"])
    late = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    at(clock, TUE, 8, 0)
    ok(act(client, librarian, early["id"], "check-in"))
    at(clock, TUE, 10, 16)
    assert process(client, librarian) == {"no_shows": 1, "completed": 1, "bans": 0}
    assert get_booking(client, librarian, early["id"])["status"] == "completed"
    assert get_booking(client, librarian, late["id"])["status"] == "no_show"


def test_t_room_28_c(client, clock, admin, librarian, branch_a):
    """T-ROOM-28-c (LIB-ROOM-28): 201 (the due no-show does not block the room); the first booking is still booked"""
    r1 = room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    first = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    at(clock, TUE, 10, 20)
    book(client, librarian, r1["id"], TUE, "10:30", "11:00", member_id=b["id"])
    assert get_booking(client, librarian, first["id"])["status"] == "booked"


def test_t_room_29_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-29-a (LIB-ROOM-29): completed, end_time 11:00, duration_minutes 60; 11:00-12:00 free again"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    at(clock, TUE, 10, 41)
    r = ok(act(client, librarian, b["id"], "check-out"))
    assert (r["status"], r["end_time"], r["duration_minutes"]) == ("completed", "11:00", 60)
    slots = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))["slots"]
    assert all(s["free"] for s in slots if s["start"] in ("11:00", "11:30"))


def test_t_room_29_c(client, admin, librarian, branch_a):
    """T-ROOM-29-c (LIB-ROOM-29): 409 BOOKING_NOT_ACTIVE"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    err(act(client, librarian, b["id"], "check-out"), 409, "BOOKING_NOT_ACTIVE")


def test_t_room_30_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-30-a (LIB-ROOM-30): Organizer: one no_show_fee of 10.00 with room_booking_id, loan_id null; P: no fee"""
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    at(clock, TUE, 10, 16); process(client, librarian)
    fees = items(member_fees(client, librarian, o["id"]))
    assert [(f["kind"], f["amount"], f["room_booking_id"], f["loan_id"]) for f in fees] == [("no_show_fee", "10.00", b["id"], None)]
    assert member_fees(client, librarian, p["id"])["total"] == 0


def test_t_room_31_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-31-a (LIB-ROOM-31): Third processing reports bans 1; ban no_shows from 2026-11-05 to 2026-11-18"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for day in ("2026-11-03", "2026-11-04"):
        no_show(client, clock, librarian, r1["id"], m, day)
    book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=m["id"])
    at(clock, "2026-11-05", 10, 16)
    assert process(client, librarian)["bans"] == 1
    bs = bans(client, librarian, m["id"])
    assert [(x["reason"], x["starts_on"], x["ends_on"]) for x in bs] == [("no_shows", "2026-11-05", "2026-11-18")]


def test_t_room_32_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-32-a (LIB-ROOM-32): Ban from 2026-11-20 to 2026-12-03"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, "2026-11-03")
    at(clock, "2026-11-09"); no_show(client, clock, librarian, r1["id"], m, "2026-11-10")
    at(clock, "2026-11-19")
    b = book(client, member_headers(client, m), r1["id"], "2026-11-20", "14:00", "15:00")
    at(clock, "2026-11-20", 12, 30)
    assert ok(act(client, member_headers(client, m), b["id"], "cancel"))["late_cancellation"] is True
    assert [(x["starts_on"], x["ends_on"]) for x in bans(client, librarian, m["id"])] == [("2026-11-20", "2026-12-03")]


def test_t_room_33_a(client, admin, librarian, branch_a):
    """T-ROOM-33-a (LIB-ROOM-33): Tuesday cancelled with member_banned; Wednesday still booked"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    t = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    w = book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=m["id"])
    ok(staff_ban(client, admin, m["id"], TUE, TUE), 201)
    gt, gw = get_booking(client, librarian, t["id"]), get_booking(client, librarian, w["id"])
    assert (gt["status"], gt["cancel_reason"], gw["status"]) == ("cancelled", "member_banned", "booked")


def test_t_room_35_a(client, admin, librarian, branch_a):
    """T-ROOM-35-a (LIB-ROOM-35): 200 with lifted_at; booking 201; 409 BAN_NOT_ACTIVE"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ban = ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-20"), 201)
    assert ok(client.post(f"/api/v1/room-bans/{ban['id']}/lift", headers=admin))["lifted_at"]
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    err(client.post(f"/api/v1/room-bans/{ban['id']}/lift", headers=admin), 409, "BAN_NOT_ACTIVE")


def test_t_room_37_a(client, admin, librarian, branch_a):
    """T-ROOM-37-a (LIB-ROOM-37): Own booking cancelled with member_deactivated; removed from the group booking, which stays booked"""
    r1, g = room(client, admin, branch_a), room(client, admin, branch_a, kind="group")
    m, o, p = (member(client, librarian, branch_a) for _ in range(3))
    own = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    grp = book(client, librarian, g["id"], "2026-11-04", "10:00", "11:00", member_id=o["id"], participant_ids=[m["id"], p["id"]])
    deactivate_member(client, librarian, m["id"])
    a, b = get_booking(client, librarian, own["id"]), get_booking(client, librarian, grp["id"])
    assert (a["status"], a["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert (b["status"], b["participant_ids"]) == ("booked", [p["id"]])


def test_t_room_39_a(client, admin):
    """T-ROOM-39-a (LIB-ROOM-39): 409 BRANCH_IN_USE; then 200"""
    br = create_branch(client, admin, "QQ")
    r1 = room(client, admin, br)
    err(client.patch(f"/api/v1/branches/{br['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False})
    deactivate_branch(client, admin, br["id"])


def test_t_room_41_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-41-a (LIB-ROOM-41): Organizer gets one room_no_show notification with room_booking_id"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = no_show(client, clock, librarian, r1["id"], m, TUE)
    ns = notes(client, librarian, m["id"], "room_no_show")
    assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]


def test_t_room_43_a(client, admin, librarian, branch_a):
    """T-ROOM-43-a (LIB-ROOM-43): One room_created and one room_booking_created entry"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    for event in ("room_created", "room_booking_created"):
        assert len(items(ok(client.get("/api/v1/audit-log", headers=admin, params={"event": event})))) == 1


def test_t_room_44_a(client, clock, admin, librarian, branch_a):
    """T-ROOM-44-a (LIB-ROOM-44): open_hours '60.0', booked_hours '2.0', used_hours '2.0', no_shows 0, utilization '3.3'"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    at(clock, TUE, 12, 0); process(client, librarian)
    rows = items(ok(client.get("/api/v1/reports/room-usage", headers=librarian, params={"from": "2026-11-02", "to": "2026-11-06"})))
    row = rows[0]
    assert (row["room_id"], row["open_hours"], row["booked_hours"], row["used_hours"], row["no_shows"], row["utilization"]) == (r1["id"], "60.0", "2.0", "2.0", 0, "3.3")


def test_t_room_45_a(client, admin, librarian, branch_a):
    """T-ROOM-45-a (LIB-ROOM-45): The export has exactly the keys of 22.1 (no rooms or bookings)"""
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
