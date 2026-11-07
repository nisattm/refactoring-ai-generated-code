MODULE = "rooms"
TITLE = "module 15 (Study rooms)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- rooms
    dict(id="T-ROOM-01-a", req="LIB-ROOM-01", type="Normal", input="Admin creates an individual room without `capacity`, `min_participants`, `features`; code `ra1`", expected="201; capacity 1, min_participants 1, features `[]`, code `RA1`, active", code='''
def TEST(client, admin, branch_a):
    body = {"branch_id": branch_a["id"], "code": "ra1", "name": "Quiet room", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    r = ok(client.post("/api/v1/rooms", headers=admin, json=body), 201)
    assert (r["capacity"], r["min_participants"], r["features"], r["code"], r["is_active"]) == (1, 1, [], "RA1", True)
'''),
    dict(id="T-ROOM-01-b", req="LIB-ROOM-01", type="Error", input="Code `G1` twice in branch A; then `G1` in branch B", expected="`409 CONFLICT` with `details.field` `code`; 201 in branch B", code='''
def TEST(client, admin, branch_a, branch_b):
    room(client, admin, branch_a, code="G1")
    body = {"branch_id": branch_a["id"], "code": "G1", "name": "Other", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    e = err(client.post("/api/v1/rooms", headers=admin, json=body), 409, "CONFLICT")
    assert e["details"]["field"] == "code"
    room(client, admin, branch_b, code="G1")
'''),
    dict(id="T-ROOM-01-c", req="LIB-ROOM-01", type="Error", input="Group capacity 2; group min 1; individual capacity 2; opens 07:15; closes 23:30; opens = closes; feature `sofa`; duplicate feature", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, admin, branch_a):
    bad = [dict(kind="group", capacity=2, min_participants=2), dict(kind="group", capacity=6, min_participants=1),
           dict(capacity=2), dict(opens_at="07:15"), dict(closes_at="23:30"), dict(opens_at="10:00", closes_at="10:00"),
           dict(features=["sofa"]), dict(features=["projector", "projector"])]
    for fields in bad:
        room(client, admin, branch_a, expect=422, **fields)
'''),
    dict(id="T-ROOM-01-d", req="LIB-ROOM-01", type="Error", input="Librarian creates a room", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian, branch_a):
    room(client, librarian, branch_a, expect=403)
'''),
    dict(id="T-ROOM-02-a", req="LIB-ROOM-02", type="Error", input="Room in an inactive branch", expected="`409 BRANCH_INACTIVE`", code='''
def TEST(client, admin):
    br = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, br["id"])
    body = {"branch_id": br["id"], "code": "X1", "name": "X", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}
    err(client.post("/api/v1/rooms", headers=admin, json=body), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-ROOM-02-b", req="LIB-ROOM-02", type="Error", input="`PATCH` with `branch_id`", expected="`422 VALIDATION_ERROR`; branch unchanged", code='''
def TEST(client, admin, branch_a, branch_b):
    r1 = room(client, admin, branch_a)
    assert client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"branch_id": branch_b["id"]}).status_code == 422
    assert ok(client.get(f"/api/v1/rooms/{r1['id']}", headers=admin))["branch_id"] == branch_a["id"]
'''),
    dict(id="T-ROOM-03-a", req="LIB-ROOM-03", type="Normal", input="Rooms `BB` and `AB` in branch A, `AA` in branch B; list; filter `branch_id` B", expected="Order AB, BB, AA (branch, then code); filter gives AA", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    room(client, admin, branch_a, code="BB"); room(client, admin, branch_a, code="AB"); room(client, admin, branch_b, code="AA")
    assert [x["code"] for x in items(ok(client.get("/api/v1/rooms", headers=librarian)))] == ["AB", "BB", "AA"]
    r = ok(client.get("/api/v1/rooms", headers=librarian, params={"branch_id": branch_b["id"]}))
    assert [x["code"] for x in items(r)] == ["AA"]
'''),
    dict(id="T-ROOM-03-b", req="LIB-ROOM-03", type="Normal", input="Filters `kind=group`, `min_capacity=5`, `feature=whiteboard&feature=projector`", expected="Only the rooms matching every filter", code='''
def TEST(client, admin, librarian, branch_a):
    g6 = room(client, admin, branch_a, kind="group", features=["whiteboard", "projector"])
    room(client, admin, branch_a, kind="group", capacity=4, features=["whiteboard", "projector"])
    room(client, admin, branch_a, kind="group", features=["whiteboard"])
    room(client, admin, branch_a, features=["whiteboard", "projector"])
    params = [("kind", "group"), ("min_capacity", "5"), ("feature", "whiteboard"), ("feature", "projector")]
    assert [x["id"] for x in items(ok(client.get("/api/v1/rooms", headers=librarian, params=params)))] == [g6["id"]]
'''),
    dict(id="T-ROOM-04-a", req="LIB-ROOM-04", type="Normal", input="`PATCH` name and `closes_at` `21:00`", expected="200 with the new values", code='''
def TEST(client, admin, branch_a):
    r1 = room(client, admin, branch_a)
    r = ok(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"name": "Renamed", "closes_at": "21:00"}))
    assert (r["name"], r["closes_at"]) == ("Renamed", "21:00")
'''),
    dict(id="T-ROOM-04-b", req="LIB-ROOM-04", type="Error", input="Group room capacity 6: `min_participants` 7; `kind` change", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, admin, branch_a):
    g = room(client, admin, branch_a, kind="group")
    assert client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"min_participants": 7}).status_code == 422
    assert client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"kind": "individual"}).status_code == 422
'''),
    dict(id="T-ROOM-05-a", req="LIB-ROOM-05", type="Error", input="Booking Tue 18:00-19:00; `PATCH closes_at` `18:00`", expected="`409 ROOM_HAS_BOOKINGS`, `details.booking_ids` [id]; hours unchanged", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "18:00", "19:00", member_id=m["id"])
    e = err(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"closes_at": "18:00"}), 409, "ROOM_HAS_BOOKINGS")
    assert e["details"]["booking_ids"] == [b["id"]]
    assert ok(client.get(f"/api/v1/rooms/{r1['id']}", headers=admin))["closes_at"] == "20:00"
'''),
    dict(id="T-ROOM-05-b", req="LIB-ROOM-05", type="Error", input="Group booking with 4 persons; `capacity` 3; `min_participants` 5", expected="`409 ROOM_HAS_BOOKINGS` both", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2, p3 = (member(client, librarian, branch_a) for _ in range(4))
    book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"], p2["id"], p3["id"]])
    for fields in ({"capacity": 3}, {"min_participants": 5}):
        err(client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json=fields), 409, "ROOM_HAS_BOOKINGS")
'''),
    dict(id="T-ROOM-06-a", req="LIB-ROOM-06", type="Normal", input="Booking for Tuesday; room deactivated", expected="Room inactive; booking `cancelled` with `room_closed`, `late_cancellation` false", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    assert ok(client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False}))["is_active"] is False
    g = get_booking(client, librarian, b["id"])
    assert (g["status"], g["cancel_reason"], g["late_cancellation"]) == ("cancelled", "room_closed", False)
'''),
    dict(id="T-ROOM-06-b", req="LIB-ROOM-06", type="Error", input="Booking an inactive room", expected="`409 ROOM_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False})
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "ROOM_INACTIVE")
'''),
    dict(id="T-ROOM-07-a", req="LIB-ROOM-07", type="Normal", input="Room 09:00-11:00; availability on Tuesday", expected="Slots 09:00, 09:30, 10:00, 10:30, each 30 minutes, all free", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a, opens_at="09:00", closes_at="11:00")
    a = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))
    assert a["open"] is True
    assert [(s["start"], s["end"], s["free"]) for s in a["slots"]] == [("09:00", "09:30", True), ("09:30", "10:00", True), ("10:00", "10:30", True), ("10:30", "11:00", True)]
'''),
    dict(id="T-ROOM-08-a", req="LIB-ROOM-08", type="Normal", input="Room 09:00-11:00 with a booking 09:30-10:30; librarian reads availability", expected="09:30 and 10:00 not free with the booking id; 09:00 and 10:30 free", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a, opens_at="09:00", closes_at="11:00")
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "09:30", "10:30", member_id=m["id"])
    slots = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))["slots"]
    assert [(s["free"], s["booking_id"]) for s in slots] == [(True, None), (False, b["id"]), (False, b["id"]), (True, None)]
'''),
    dict(id="T-ROOM-08-b", req="LIB-ROOM-08", type="Boundary", input="Availability on Saturday 2026-11-07; without `date`", expected="`open` false and `slots` []; `422 VALIDATION_ERROR`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    a = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": "2026-11-07"}))
    assert a["open"] is False and a["slots"] == []
    assert client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian).status_code == 422
'''),
    dict(id="T-ROOM-08-c", req="LIB-ROOM-08", type="Normal", input="Booking of member A; availability read by member A and by member B", expected="A sees the booking id; B sees `booking_id` null and `free` false", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a, opens_at="10:00", closes_at="11:00")
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    bk = book(client, member_headers(client, a), r1["id"], TUE, "10:00", "10:30")
    sa = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=member_headers(client, a), params={"date": TUE}))["slots"][0]
    sb = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=member_headers(client, b), params={"date": TUE}))["slots"][0]
    assert sa["booking_id"] == bk["id"] and sb["booking_id"] is None and sb["free"] is False
'''),
    dict(id="T-ROOM-09-a", req="LIB-ROOM-09", type="Normal", input="Free rooms Tue 10:30-11:30: R1 free, R2 booked 10:00-11:00, R3 open from 12:00, R4 inactive", expected="Only R1", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a); r2 = room(client, admin, branch_a)
    room(client, admin, branch_a, opens_at="12:00"); r4 = room(client, admin, branch_a)
    client.patch(f"/api/v1/rooms/{r4['id']}", headers=admin, json={"is_active": False})
    m = member(client, librarian, branch_a)
    book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=m["id"])
    r = ok(client.get("/api/v1/rooms/free", headers=librarian, params={"date": TUE, "start_time": "10:30", "end_time": "11:30"}))
    assert [x["id"] for x in items(r)] == [r1["id"]]
'''),
    dict(id="T-ROOM-09-b", req="LIB-ROOM-09", type="Error", input="`start_time` `10:15`; `end_time` before `start_time`", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, admin, librarian, branch_a):
    room(client, admin, branch_a)
    for s, e in (("10:15", "11:00"), ("11:00", "10:00")):
        assert client.get("/api/v1/rooms/free", headers=librarian, params={"date": TUE, "start_time": s, "end_time": e}).status_code == 422
'''),
    # ---------------------------------------------------------------- booking
    dict(id="T-ROOM-10-a", req="LIB-ROOM-10", type="Normal", input="Member books Tue 10:00-11:00 without participants and purpose", expected="201; own `member_id`, `booked`, `participant_ids` [], `purpose` \"\", `duration_minutes` 60, `room_code`, `branch_id`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a, code="QA")
    m = member(client, librarian, branch_a)
    b = book(client, member_headers(client, m), r1["id"], TUE, "10:00", "11:00")
    assert (b["member_id"], b["status"], b["participant_ids"], b["purpose"], b["duration_minutes"]) == (m["id"], "booked", [], "", 60)
    assert (b["room_code"], b["branch_id"], b["date"], b["start_time"], b["end_time"]) == ("QA", branch_a["id"], TUE, "10:00", "11:00")
'''),
    dict(id="T-ROOM-10-b", req="LIB-ROOM-10", type="Error", input="Librarian without `member_id`; member with own `member_id`", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    assert try_book(client, librarian, r1["id"], TUE, "10:00", "11:00").status_code == 422
    assert try_book(client, member_headers(client, m), r1["id"], TUE, "10:00", "11:00", member_id=m["id"]).status_code == 422
'''),
    dict(id="T-ROOM-11-a", req="LIB-ROOM-11", type="Error", input="Start `10:15`; start = end; end `11:45`", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for s, e in (("10:15", "11:00"), ("10:00", "10:00"), ("10:00", "11:45")):
        assert try_book(client, librarian, r1["id"], TUE, s, e, member_id=m["id"]).status_code == 422
'''),
    dict(id="T-ROOM-11-b", req="LIB-ROOM-11", type="Boundary", input="Academic member: 30 minutes; 4 hours; 4.5 hours", expected="201; 201; `422 VALIDATION_ERROR`", code='''
def TEST(client, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    book(client, librarian, r1["id"], TUE, "08:00", "08:30", member_id=m["id"])
    book(client, librarian, r2["id"], "2026-11-04", "10:00", "14:00", member_id=m["id"])
    assert try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "14:30", member_id=m["id"]).status_code == 422
'''),
    dict(id="T-ROOM-11-c", req="LIB-ROOM-11", type="Error", input="Group room: a participant listed twice; the organizer as participant", expected="`422 VALIDATION_ERROR` both", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    for parts in ([p["id"], p["id"]], [o["id"], p["id"]]):
        assert try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=parts).status_code == 422
'''),
    dict(id="T-ROOM-12-a", req="LIB-ROOM-12", type="Error", input="Booking for a passive member", expected="`409 MEMBER_PASSIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    deactivate_member(client, librarian, m["id"])
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_PASSIVE")
'''),
    dict(id="T-ROOM-12-b", req="LIB-ROOM-12", type="Boundary", input="Student registered 2026-11-02 (valid until 2027-11-01); on 2027-10-28 books 2027-11-01 and 2027-11-02", expected="201; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2027-10-28")
    book(client, librarian, r1["id"], "2027-11-01", "10:00", "11:00", member_id=m["id"])
    err(try_book(client, librarian, r1["id"], "2027-11-02", "10:00", "11:00", member_id=m["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-ROOM-12-c", req="LIB-ROOM-12", type="Error", input="Guest member books", expected="`409 ROOM_NOT_ALLOWED_FOR_TYPE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_book(client, member_headers(client, g), r1["id"], TUE, "10:00", "11:00"), 409, "ROOM_NOT_ALLOWED_FOR_TYPE")
'''),
    dict(id="T-ROOM-12-d", req="LIB-ROOM-12", type="Error", input="Staff ban 2026-11-02 to 2026-11-05; booking for 2026-11-09", expected="`409 MEMBER_BANNED_FROM_ROOMS` with `details.ends_on` 2026-11-05 (in force today)", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-05"), 201)
    e = err(try_book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_BANNED_FROM_ROOMS")
    assert e["details"]["ends_on"] == "2026-11-05"
'''),
    dict(id="T-ROOM-12-e", req="LIB-ROOM-12", type="Boundary", input="Member with a damage fee of 50.00", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    copy = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], copy["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="50.00")
    e = err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"
'''),
    dict(id="T-ROOM-12-f", req="LIB-ROOM-12", type="Error", input="Booking on Saturday 2026-11-07", expected="`409 ROOM_CLOSED`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], "2026-11-07", "10:00", "11:00", member_id=m["id"]), 409, "ROOM_CLOSED")
'''),
    dict(id="T-ROOM-12-g", req="LIB-ROOM-12", type="Boundary", input="Room 08:00-20:00: 07:30-08:30; 19:30-20:30; 19:00-20:00", expected="`409 OUTSIDE_ROOM_HOURS` twice; 201", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for s, e in (("07:30", "08:30"), ("19:30", "20:30")):
        err(try_book(client, librarian, r1["id"], TUE, s, e, member_id=m["id"]), 409, "OUTSIDE_ROOM_HOURS")
    book(client, librarian, r1["id"], TUE, "19:00", "20:00", member_id=m["id"])
'''),
    dict(id="T-ROOM-12-h", req="LIB-ROOM-12", type="Boundary", input="Now Mon 09:00: booking today 09:00-09:30; today 09:30-10:00", expected="`409 BOOKING_IN_PAST`; 201", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], "2026-11-02", "09:00", "09:30", member_id=m["id"]), 409, "BOOKING_IN_PAST")
    book(client, librarian, r1["id"], "2026-11-02", "09:30", "10:00", member_id=m["id"])
'''),
    dict(id="T-ROOM-12-i", req="LIB-ROOM-12", type="Boundary", input="Student on Mon 2026-11-02 books 2026-11-09 and 2026-11-10", expected="201; `409 BOOKING_TOO_FAR_AHEAD` with `details.latest_date` 2026-11-09", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], "2026-11-10", "10:00", "11:00", member_id=m["id"]), 409, "BOOKING_TOO_FAR_AHEAD")
    assert e["details"]["latest_date"] == "2026-11-09"
'''),
    dict(id="T-ROOM-12-j", req="LIB-ROOM-12", type="Boundary", input="Academic on Mon 2026-11-02 books 2026-11-16 and 2026-11-17", expected="201; `409 BOOKING_TOO_FAR_AHEAD`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    book(client, librarian, r1["id"], "2026-11-16", "10:00", "11:00", member_id=m["id"])
    err(try_book(client, librarian, r1["id"], "2026-11-17", "10:00", "11:00", member_id=m["id"]), 409, "BOOKING_TOO_FAR_AHEAD")
'''),
    dict(id="T-ROOM-12-k", req="LIB-ROOM-12", type="Error", input="Order: guest books on Saturday; room and branch both inactive", expected="`ROOM_NOT_ALLOWED_FOR_TYPE` (step 5 before 8); `BRANCH_INACTIVE` (step 1 before 2)", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_book(client, librarian, r1["id"], "2026-11-07", "10:00", "11:00", member_id=g["id"]), 409, "ROOM_NOT_ALLOWED_FOR_TYPE")
    br = create_branch(client, admin, "YY")
    r2 = room(client, admin, br)
    client.patch(f"/api/v1/rooms/{r2['id']}", headers=admin, json={"is_active": False})
    deactivate_branch(client, admin, br["id"])
    m = member(client, librarian, branch_a)
    err(try_book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=m["id"]), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-ROOM-12-l", req="LIB-ROOM-12", type="Error", input="Member B books 10:30-11:30 where A has 10:00-11:00", expected="`409 ROOM_ALREADY_BOOKED`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    err(try_book(client, librarian, r1["id"], TUE, "10:30", "11:30", member_id=b["id"]), 409, "ROOM_ALREADY_BOOKED")
'''),
    dict(id="T-ROOM-12-m", req="LIB-ROOM-12", type="Error", input="Member books another room overlapping their own booking", expected="`409 MEMBER_DOUBLE_BOOKED` with `details.member_id`", code='''
def TEST(client, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r2["id"], TUE, "10:30", "11:00", member_id=m["id"]), 409, "MEMBER_DOUBLE_BOOKED")
    assert e["details"]["member_id"] == m["id"]
'''),
    dict(id="T-ROOM-13-a", req="LIB-ROOM-13", type="Error", input="Individual room with a participant", expected="`409 PARTICIPANTS_NOT_ALLOWED`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    err(try_book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "PARTICIPANTS_NOT_ALLOWED")
'''),
    dict(id="T-ROOM-13-b", req="LIB-ROOM-13", type="Error", input="Participant id that does not exist", expected="`404 NOT_FOUND`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o = member(client, librarian, branch_a)
    err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[999999]), 404, "NOT_FOUND")
'''),
    dict(id="T-ROOM-13-c", req="LIB-ROOM-13", type="Error", input="Group room min 3; organizer + 1 participant", expected="`409 NOT_ENOUGH_PARTICIPANTS` with `details.min_participants` 3", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group", min_participants=3)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "NOT_ENOUGH_PARTICIPANTS")
    assert e["details"]["min_participants"] == 3
'''),
    dict(id="T-ROOM-13-d", req="LIB-ROOM-13", type="Error", input="Group room capacity 3; organizer + 3 participants", expected="`409 ROOM_CAPACITY_EXCEEDED` with `details.capacity` 3", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group", capacity=3, min_participants=2)
    o, *ps = (member(client, librarian, branch_a) for _ in range(4))
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"] for p in ps]), 409, "ROOM_CAPACITY_EXCEEDED")
    assert e["details"]["capacity"] == 3
'''),
    dict(id="T-ROOM-13-e", req="LIB-ROOM-13", type="Error", input="Participants: P1 passive (smaller id), P2 guest", expected="`409 PARTICIPANT_NOT_ELIGIBLE`, `member_id` P1, `reason` `MEMBER_PASSIVE`; with P2 only: `reason` `ROOM_NOT_ALLOWED_FOR_TYPE`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o = member(client, librarian, branch_a)
    p1 = member(client, librarian, branch_a)
    p2 = member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, p1["id"])
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"], p1["id"]]), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert (e["details"]["member_id"], e["details"]["reason"]) == (p1["id"], "MEMBER_PASSIVE")
    e = err(try_book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"]]), 409, "PARTICIPANT_NOT_ELIGIBLE")
    assert e["details"]["reason"] == "ROOM_NOT_ALLOWED_FOR_TYPE"
'''),
    dict(id="T-ROOM-13-f", req="LIB-ROOM-13", type="Normal", input="Group booking with participants given in descending id order", expected="201; `participant_ids` ascending", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p2["id"], p1["id"]])
    assert b["participant_ids"] == [p1["id"], p2["id"]]
'''),
    dict(id="T-ROOM-14-a", req="LIB-ROOM-14", type="Boundary", input="A books 09:00-10:00, B books 10:00-11:00 in the same room; A books another room 10:00-10:30", expected="All 201 (touching intervals do not overlap)", code='''
def TEST(client, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "09:00", "10:00", member_id=a["id"])
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=b["id"])
    book(client, librarian, r2["id"], TUE, "10:00", "10:30", member_id=a["id"])
'''),
    dict(id="T-ROOM-15-a", req="LIB-ROOM-15", type="Error", input="Student with 2 hours on Tuesday books 30 more minutes", expected="`409 DAILY_ROOM_QUOTA_EXCEEDED` with `member_id`, `used` \"2.5\"", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], TUE, "14:00", "14:30", member_id=m["id"]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert (e["details"]["member_id"], e["details"]["used"]) == (m["id"], "2.5")
'''),
    dict(id="T-ROOM-15-b", req="LIB-ROOM-15", type="Error", input="Student is participant in 2-hour group bookings Mon, Tue, Wed; books Thu 30 minutes", expected="`409 WEEKLY_ROOM_QUOTA_EXCEEDED`, `used` \"6.5\"", code='''
def TEST(client, admin, librarian, branch_a):
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o = member(client, librarian, branch_a, membership_type="academic")
    s = member(client, librarian, branch_a)
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        book(client, librarian, g["id"], day, "14:00", "16:00", member_id=o["id"], participant_ids=[s["id"]])
    e = err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "10:30", member_id=s["id"]), 409, "WEEKLY_ROOM_QUOTA_EXCEEDED")
    assert (e["details"]["member_id"], e["details"]["used"]) == (s["id"], "6.5")
'''),
    dict(id="T-ROOM-15-c", req="LIB-ROOM-15", type="Error", input="Student with 2 future bookings books a third", expected="`409 ROOM_BOOKING_LIMIT_REACHED` with `details.limit` 2", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=m["id"]), 409, "ROOM_BOOKING_LIMIT_REACHED")
    assert e["details"]["limit"] == 2
'''),
    dict(id="T-ROOM-15-d", req="LIB-ROOM-15", type="Error", input="Participant P has 2 hours on Tuesday; group booking with P on Tuesday", expected="`409 DAILY_ROOM_QUOTA_EXCEEDED` with `details.member_id` P", code='''
def TEST(client, admin, librarian, branch_a):
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=p["id"])
    e = err(try_book(client, librarian, g["id"], TUE, "14:00", "15:00", member_id=o["id"], participant_ids=[p["id"]]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"]["member_id"] == p["id"]
'''),
    dict(id="T-ROOM-16-a", req="LIB-ROOM-16", type="Boundary", input="Student with 1.5 hours on Tuesday: books 1 hour; books 30 minutes", expected="`409 DAILY_ROOM_QUOTA_EXCEEDED` with `used` \"2.5\"; 201", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:30", member_id=m["id"])
    e = err(try_book(client, librarian, r1["id"], TUE, "12:00", "13:00", member_id=m["id"]), 409, "DAILY_ROOM_QUOTA_EXCEEDED")
    assert e["details"]["used"] == "2.5"
    book(client, librarian, r1["id"], TUE, "12:00", "12:30", member_id=m["id"])
'''),
    dict(id="T-ROOM-16-b", req="LIB-ROOM-16", type="Boundary", input="Student with 6 hours in the week (as participant); books Thursday; books Monday of the next week", expected="`409 WEEKLY_ROOM_QUOTA_EXCEEDED`; 201", code='''
def TEST(client, admin, librarian, branch_a):
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o = member(client, librarian, branch_a, membership_type="academic")
    s = member(client, librarian, branch_a)
    for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
        book(client, librarian, g["id"], day, "14:00", "16:00", member_id=o["id"], participant_ids=[s["id"]])
    err(try_book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=s["id"]), 409, "WEEKLY_ROOM_QUOTA_EXCEEDED")
    book(client, librarian, r1["id"], "2026-11-09", "10:00", "11:00", member_id=s["id"])
'''),
    dict(id="T-ROOM-17-a", req="LIB-ROOM-17", type="Normal", input="Librarian books for a member", expected="`created_by` = the librarian's user id; `member_id` = the member", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    me = ok(client.get("/api/v1/auth/me", headers=librarian))
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    assert (b["created_by"], b["member_id"]) == (me["id"], m["id"])
'''),
    dict(id="T-ROOM-18-a", req="LIB-ROOM-18", type="Normal", input="Bookings on Wed 10:00, Tue 14:00, Tue 10:00; P is participant of a group booking; member list of P", expected="All-bookings list ordered by date, start; P's list contains the group booking", code='''
def TEST(client, admin, librarian, branch_a):
    r1, g = room(client, admin, branch_a), room(client, admin, branch_a, kind="group")
    a, b, c = (member(client, librarian, branch_a) for _ in range(3))
    w = book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=a["id"])
    t2 = book(client, librarian, r1["id"], TUE, "14:00", "15:00", member_id=b["id"])
    t1 = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=a["id"], participant_ids=[c["id"]])
    assert [x["id"] for x in items(ok(client.get("/api/v1/room-bookings", headers=librarian)))] == [t1["id"], t2["id"], w["id"]]
    assert [x["id"] for x in items(ok(client.get(f"/api/v1/members/{c['id']}/room-bookings", headers=librarian)))] == [t1["id"]]
'''),
    dict(id="T-ROOM-18-b", req="LIB-ROOM-18", type="Normal", input="Filters `status=cancelled`, `from`/`to` = Wednesday, `member_id` of a participant", expected="Only the matching bookings", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-ROOM-19-a", req="LIB-ROOM-19", type="Error", input="Group booking: an unrelated member reads it; a participant reads it", expected="`403 FORBIDDEN`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert client.get(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, x)).status_code == 403
    assert client.get(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, p)).status_code == 200
'''),
    # ---------------------------------------------------------------- changes, cancellation, check-in
    dict(id="T-ROOM-20-a", req="LIB-ROOM-20", type="Normal", input="Organizer adds a participant and changes the purpose", expected="200; participants ascending; purpose changed", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"]])
    r = ok(client.patch(f"/api/v1/room-bookings/{b['id']}", headers=member_headers(client, o), json={"participant_ids": [p2["id"], p1["id"]], "purpose": "Project"}))
    assert (r["participant_ids"], r["purpose"]) == ([p1["id"], p2["id"]], "Project")
'''),
    dict(id="T-ROOM-20-b", req="LIB-ROOM-20", type="Error", input="`PATCH` after the start; `PATCH` of a cancelled booking", expected="`409 BOOKING_NOT_CHANGEABLE` both", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    started = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    cancelled = book(client, librarian, r2["id"], TUE, "14:00", "15:00", member_id=b["id"])
    ok(act(client, librarian, cancelled["id"], "cancel"))
    at(clock, TUE, 10, 5)
    for bk in (started, cancelled):
        err(client.patch(f"/api/v1/room-bookings/{bk['id']}", headers=librarian, json={"purpose": "x"}), 409, "BOOKING_NOT_CHANGEABLE")
'''),
    dict(id="T-ROOM-21-a", req="LIB-ROOM-21", type="Normal", input="Group min 2 with organizer + P1 + P2; P1 leaves", expected="200; participants [P2]; still `booked`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p1, p2 = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p1["id"], p2["id"]])
    r = ok(act(client, member_headers(client, p1), b["id"], "leave"))
    assert (r["participant_ids"], r["status"]) == ([p2["id"]], "booked")
'''),
    dict(id="T-ROOM-21-b", req="LIB-ROOM-21", type="Normal", input="Group min 2 with organizer + P; P leaves", expected="Booking `cancelled` with `not_enough_participants`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ok(act(client, member_headers(client, p), b["id"], "leave"))
    g2 = get_booking(client, librarian, b["id"])
    assert (g2["status"], g2["cancel_reason"]) == ("cancelled", "not_enough_participants")
'''),
    dict(id="T-ROOM-21-c", req="LIB-ROOM-21", type="Error", input="A member who is not a participant calls `leave`", expected="`403 FORBIDDEN`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert act(client, member_headers(client, x), b["id"], "leave").status_code == 403
'''),
    dict(id="T-ROOM-22-a", req="LIB-ROOM-22", type="Normal", input="Organizer cancels a day ahead; cancels again", expected="`cancelled`, `member_request`, not late; second `409 BOOKING_NOT_ACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    h = member_headers(client, m)
    b = book(client, h, r1["id"], TUE, "10:00", "11:00")
    r = ok(act(client, h, b["id"], "cancel"))
    assert (r["status"], r["cancel_reason"], r["late_cancellation"]) == ("cancelled", "member_request", False) and r["closed_at"]
    err(act(client, h, b["id"], "cancel"), 409, "BOOKING_NOT_ACTIVE")
'''),
    dict(id="T-ROOM-22-b", req="LIB-ROOM-22", type="Normal", input="Librarian cancels 30 minutes before the start", expected="`staff_request`, `late_cancellation` false", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 9, 30)
    r = ok(act(client, librarian, b["id"], "cancel"))
    assert (r["cancel_reason"], r["late_cancellation"]) == ("staff_request", False)
'''),
    dict(id="T-ROOM-22-c", req="LIB-ROOM-22", type="Error", input="A participant (not organizer) cancels", expected="`403 FORBIDDEN`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    assert act(client, member_headers(client, p), b["id"], "cancel").status_code == 403
'''),
    dict(id="T-ROOM-23-a", req="LIB-ROOM-23", type="Boundary", input="Start 10:00: organizer A cancels at 10:15; organizer B cancels at 10:16", expected="A: 200, late; B: `409 BOOKING_NOT_ACTIVE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    ha, hb = member_headers(client, a), member_headers(client, b)
    at(clock, TUE, 10, 15)
    assert ok(act(client, ha, ba["id"], "cancel"))["late_cancellation"] is True
    at(clock, TUE, 10, 16)
    err(act(client, hb, bb["id"], "cancel"), 409, "BOOKING_NOT_ACTIVE")
'''),
    dict(id="T-ROOM-24-a", req="LIB-ROOM-24", type="Boundary", input="Start 14:00: organizer A cancels at 12:00; organizer B cancels at 12:01", expected="A not late; B late", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-ROOM-25-a", req="LIB-ROOM-25", type="Normal", input="Student books Tue 10:00-12:00, cancels, books Tue 13:00-15:00", expected="201 (the cancelled booking does not count)", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    ok(act(client, librarian, b["id"], "cancel"))
    book(client, librarian, r1["id"], TUE, "13:00", "15:00", member_id=m["id"])
'''),
    dict(id="T-ROOM-26-a", req="LIB-ROOM-26", type="Normal", input="Group booking (organizer + P); room deactivated", expected="Organizer and P each get a `room_booking_cancelled` notification", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    client.patch(f"/api/v1/rooms/{g['id']}", headers=admin, json={"is_active": False})
    for m in (o, p):
        ns = notes(client, librarian, m["id"], "room_booking_cancelled")
        assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]
'''),
    dict(id="T-ROOM-27-a", req="LIB-ROOM-27", type="Boundary", input="Start 10:00: check-in at 09:49; at 09:50", expected="`409 CHECK_IN_TOO_EARLY` with `details.earliest` 09:50; then 200 `checked_in`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 9, 49)
    e = err(act(client, librarian, b["id"], "check-in"), 409, "CHECK_IN_TOO_EARLY")
    assert e["details"]["earliest"] == "2026-11-03T09:50:00+03:00"
    at(clock, TUE, 9, 50)
    r = ok(act(client, librarian, b["id"], "check-in"))
    assert r["status"] == "checked_in" and r["checked_in_at"] == "2026-11-03T09:50:00+03:00"
'''),
    dict(id="T-ROOM-27-b", req="LIB-ROOM-27", type="Boundary", input="Start 10:00: A checks in at 10:15; B checks in at 10:16", expected="A 200; B `409 CHECK_IN_TOO_LATE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1, r2 = room(client, admin, branch_a), room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ba = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    bb = book(client, librarian, r2["id"], TUE, "10:00", "11:00", member_id=b["id"])
    at(clock, TUE, 10, 15)
    ok(act(client, librarian, ba["id"], "check-in"))
    at(clock, TUE, 10, 16)
    err(act(client, librarian, bb["id"], "check-in"), 409, "CHECK_IN_TOO_LATE")
'''),
    dict(id="T-ROOM-27-c", req="LIB-ROOM-27", type="Error", input="Check-in of a cancelled booking", expected="`409 BOOKING_NOT_ACTIVE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    ok(act(client, librarian, b["id"], "cancel"))
    at(clock, TUE, 10, 0)
    err(act(client, librarian, b["id"], "check-in"), 409, "BOOKING_NOT_ACTIVE")
'''),
    dict(id="T-ROOM-28-a", req="LIB-ROOM-28", type="Normal", input="Tue: booking 08:00-09:00 checked in at 08:00; booking 10:00-11:00 never checked in; process at 10:16", expected="`{no_shows: 1, completed: 1, bans: 0}`; statuses `completed` and `no_show`", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-ROOM-28-b", req="LIB-ROOM-28", type="Boundary", input="Start 10:00: process at 10:15; again at 10:16", expected="0 no-shows; then 1", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 10, 15)
    assert process(client, librarian)["no_shows"] == 0
    at(clock, TUE, 10, 16)
    assert process(client, librarian)["no_shows"] == 1
'''),
    dict(id="T-ROOM-28-c", req="LIB-ROOM-28", type="Normal", input="Booking 10:00-11:00 due as a no-show, not processed; at 10:20 another member books the room 10:30-11:00", expected="201 (the due no-show does not block the room); the first booking is still `booked`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    a, b = member(client, librarian, branch_a), member(client, librarian, branch_a)
    first = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=a["id"])
    at(clock, TUE, 10, 20)
    book(client, librarian, r1["id"], TUE, "10:30", "11:00", member_id=b["id"])
    assert get_booking(client, librarian, first["id"])["status"] == "booked"
'''),
    dict(id="T-ROOM-29-a", req="LIB-ROOM-29", type="Normal", input="Academic booking 10:00-12:00 checked in at 10:00, checked out at 10:41", expected="`completed`, `end_time` 11:00, `duration_minutes` 60; 11:00-12:00 free again", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a, membership_type="academic")
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    at(clock, TUE, 10, 41)
    r = ok(act(client, librarian, b["id"], "check-out"))
    assert (r["status"], r["end_time"], r["duration_minutes"]) == ("completed", "11:00", 60)
    slots = ok(client.get(f"/api/v1/rooms/{r1['id']}/availability", headers=librarian, params={"date": TUE}))["slots"]
    assert all(s["free"] for s in slots if s["start"] in ("11:00", "11:30"))
'''),
    dict(id="T-ROOM-29-b", req="LIB-ROOM-29", type="Boundary", input="Booking A 10:00-11:00 checked out at 10:05; booking B 10:00-11:00 checked out at 11:10", expected="A `end_time` 10:30 (minimum 30 minutes); B `end_time` 11:00 (not later than before)", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-ROOM-29-c", req="LIB-ROOM-29", type="Error", input="Check-out of a `booked` booking", expected="`409 BOOKING_NOT_ACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    err(act(client, librarian, b["id"], "check-out"), 409, "BOOKING_NOT_ACTIVE")
'''),
    # ---------------------------------------------------------------- fees and bans
    dict(id="T-ROOM-30-a", req="LIB-ROOM-30", type="Normal", input="Group booking (organizer + P) is processed as a no-show", expected="Organizer: one `no_show_fee` of 10.00 with `room_booking_id`, `loan_id` null; P: no fee", code='''
def TEST(client, clock, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    at(clock, TUE, 10, 16); process(client, librarian)
    fees = items(member_fees(client, librarian, o["id"]))
    assert [(f["kind"], f["amount"], f["room_booking_id"], f["loan_id"]) for f in fees] == [("no_show_fee", "10.00", b["id"], None)]
    assert member_fees(client, librarian, p["id"])["total"] == 0
'''),
    dict(id="T-ROOM-30-b", req="LIB-ROOM-30", type="Normal", input="After one no-show, the member's balance", expected="`outstanding_fees` \"10.00\", `total_debt` \"10.00\"", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, TUE)
    bal = balance(client, librarian, m["id"])
    assert (bal["outstanding_fees"], bal["total_debt"]) == ("10.00", "10.00")
'''),
    dict(id="T-ROOM-31-a", req="LIB-ROOM-31", type="Normal", input="No-shows on Tue, Wed and Thu (2026-11-03 to 11-05)", expected="Third processing reports `bans` 1; ban `no_shows` from 2026-11-05 to 2026-11-18", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for day in ("2026-11-03", "2026-11-04"):
        no_show(client, clock, librarian, r1["id"], m, day)
    book(client, librarian, r1["id"], "2026-11-05", "10:00", "11:00", member_id=m["id"])
    at(clock, "2026-11-05", 10, 16)
    assert process(client, librarian)["bans"] == 1
    bs = bans(client, librarian, m["id"])
    assert [(x["reason"], x["starts_on"], x["ends_on"]) for x in bs] == [("no_shows", "2026-11-05", "2026-11-18")]
'''),
    dict(id="T-ROOM-31-b", req="LIB-ROOM-31", type="Normal", input="Three no-shows lead to a ban; after it ends, one more no-show", expected="No second ban (earlier incidents do not count again)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    for day in ("2026-11-03", "2026-11-04", "2026-11-05"):
        no_show(client, clock, librarian, r1["id"], m, day)
    at(clock, "2026-11-19")
    book(client, librarian, r1["id"], "2026-11-20", "10:00", "11:00", member_id=m["id"])
    at(clock, "2026-11-20", 10, 16)
    assert process(client, librarian)["bans"] == 0
    assert len(bans(client, librarian, m["id"])) == 1
'''),
    dict(id="T-ROOM-32-a", req="LIB-ROOM-32", type="Boundary", input="No-shows on 2026-11-03 and 2026-11-10; late cancellation on 2026-11-20", expected="Ban from 2026-11-20 to 2026-12-03", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, "2026-11-03")
    at(clock, "2026-11-09"); no_show(client, clock, librarian, r1["id"], m, "2026-11-10")
    at(clock, "2026-11-19")
    b = book(client, member_headers(client, m), r1["id"], "2026-11-20", "14:00", "15:00")
    at(clock, "2026-11-20", 12, 30)
    assert ok(act(client, member_headers(client, m), b["id"], "cancel"))["late_cancellation"] is True
    assert [(x["starts_on"], x["ends_on"]) for x in bans(client, librarian, m["id"])] == [("2026-11-20", "2026-12-03")]
'''),
    dict(id="T-ROOM-32-b", req="LIB-ROOM-32", type="Boundary", input="No-shows on 2026-11-03, 2026-12-03 and 2026-12-04", expected="No ban", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    no_show(client, clock, librarian, r1["id"], m, "2026-11-03")
    at(clock, "2026-12-02"); no_show(client, clock, librarian, r1["id"], m, "2026-12-03")
    no_show(client, clock, librarian, r1["id"], m, "2026-12-04")
    assert bans(client, librarian, m["id"]) == []
'''),
    dict(id="T-ROOM-33-a", req="LIB-ROOM-33", type="Normal", input="Member has bookings Tue and Wed; staff ban for Tuesday only", expected="Tuesday `cancelled` with `member_banned`; Wednesday still `booked`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    t = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    w = book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=m["id"])
    ok(staff_ban(client, admin, m["id"], TUE, TUE), 201)
    gt, gw = get_booking(client, librarian, t["id"]), get_booking(client, librarian, w["id"])
    assert (gt["status"], gt["cancel_reason"], gw["status"]) == ("cancelled", "member_banned", "booked")
'''),
    dict(id="T-ROOM-33-b", req="LIB-ROOM-33", type="Normal", input="Banned member is the only participant of a group booking (min 2)", expected="Member removed; booking `cancelled` with `not_enough_participants`", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ok(staff_ban(client, admin, p["id"], TUE, "2026-11-10"), 201)
    r = get_booking(client, librarian, b["id"])
    assert (r["participant_ids"], r["status"], r["cancel_reason"]) == ([], "cancelled", "not_enough_participants")
'''),
    dict(id="T-ROOM-34-a", req="LIB-ROOM-34", type="Error", input="Ban starting yesterday; `ends_on` before `starts_on`; librarian creates a ban", expected="`422`; `422`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    assert staff_ban(client, admin, m["id"], "2026-11-01", "2026-11-05").status_code == 422
    assert staff_ban(client, admin, m["id"], "2026-11-05", "2026-11-04").status_code == 422
    assert staff_ban(client, librarian, m["id"], "2026-11-02", "2026-11-05").status_code == 403
'''),
    dict(id="T-ROOM-35-a", req="LIB-ROOM-35", type="Normal", input="Admin lifts a ban in force; member books; admin lifts it again", expected="200 with `lifted_at`; booking 201; `409 BAN_NOT_ACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ban = ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-20"), 201)
    assert ok(client.post(f"/api/v1/room-bans/{ban['id']}/lift", headers=admin))["lifted_at"]
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    err(client.post(f"/api/v1/room-bans/{ban['id']}/lift", headers=admin), 409, "BAN_NOT_ACTIVE")
'''),
    dict(id="T-ROOM-36-a", req="LIB-ROOM-36", type="Normal", input="Bans 2026-11-02 to 11-03 and 2026-11-10 to 11-12; list on 2026-11-02", expected="Order: the 11-10 ban first; `in_force` false and true", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    ok(staff_ban(client, admin, m["id"], "2026-11-02", "2026-11-03"), 201)
    ok(staff_ban(client, admin, m["id"], "2026-11-10", "2026-11-12"), 201)
    assert [(x["starts_on"], x["in_force"]) for x in bans(client, librarian, m["id"])] == [("2026-11-10", False), ("2026-11-02", True)]
'''),
    # ---------------------------------------------------------------- other modules
    dict(id="T-ROOM-37-a", req="LIB-ROOM-37", type="Normal", input="Member organizes a booking and is the participant of another group booking (organizer + member + P); member deactivated", expected="Own booking `cancelled` with `member_deactivated`; removed from the group booking, which stays `booked`", code='''
def TEST(client, admin, librarian, branch_a):
    r1, g = room(client, admin, branch_a), room(client, admin, branch_a, kind="group")
    m, o, p = (member(client, librarian, branch_a) for _ in range(3))
    own = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    grp = book(client, librarian, g["id"], "2026-11-04", "10:00", "11:00", member_id=o["id"], participant_ids=[m["id"], p["id"]])
    deactivate_member(client, librarian, m["id"])
    a, b = get_booking(client, librarian, own["id"]), get_booking(client, librarian, grp["id"])
    assert (a["status"], a["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert (b["status"], b["participant_ids"]) == ("booked", [p["id"]])
'''),
    dict(id="T-ROOM-37-b", req="LIB-ROOM-37", type="Error", input="Member checked in to a room; deactivation", expected="`409 MEMBER_IN_ROOM`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    err(client.post(f"/api/v1/members/{m['id']}/deactivate", headers=librarian), 409, "MEMBER_IN_ROOM")
'''),
    dict(id="T-ROOM-38-a", req="LIB-ROOM-38", type="Normal", input="Student with a future booking becomes `guest`", expected="Booking `cancelled` with `staff_request`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    update_member(client, librarian, m["id"], membership_type="guest", phone="905551234567")
    g = get_booking(client, librarian, b["id"])
    assert (g["status"], g["cancel_reason"]) == ("cancelled", "staff_request")
'''),
    dict(id="T-ROOM-39-a", req="LIB-ROOM-39", type="Error", input="Branch with an active room is deactivated; after the room is deactivated", expected="`409 BRANCH_IN_USE`; then 200", code='''
def TEST(client, admin):
    br = create_branch(client, admin, "QQ")
    r1 = room(client, admin, br)
    err(client.patch(f"/api/v1/branches/{br['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"/api/v1/rooms/{r1['id']}", headers=admin, json={"is_active": False})
    deactivate_branch(client, admin, br["id"])
'''),
    dict(id="T-ROOM-40-a", req="LIB-ROOM-40", type="Normal", input="Member with one booking Tue 10:00-11:00 and no ban; summary", expected="`rooms` = `{upcoming_bookings: 1, banned_until: null, hours_this_week: \"1.0\"}`", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    s = ok(client.get(f"/api/v1/members/{m['id']}/summary", headers=librarian))
    assert s["rooms"] == {"upcoming_bookings": 1, "banned_until": None, "hours_this_week": "1.0"}
'''),
    dict(id="T-ROOM-41-a", req="LIB-ROOM-41", type="Normal", input="No-show is processed", expected="Organizer gets one `room_no_show` notification with `room_booking_id`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = no_show(client, clock, librarian, r1["id"], m, TUE)
    ns = notes(client, librarian, m["id"], "room_no_show")
    assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]
'''),
    dict(id="T-ROOM-41-b", req="LIB-ROOM-41", type="Normal", input="Group booking created with participant P; organizer's own notifications", expected="P gets one `room_participant_added`; the organizer gets none", code='''
def TEST(client, admin, librarian, branch_a):
    g = room(client, admin, branch_a, kind="group")
    o, p = member(client, librarian, branch_a), member(client, librarian, branch_a)
    b = book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    ns = notes(client, librarian, p["id"], "room_participant_added")
    assert len(ns) == 1 and ns[0]["room_booking_id"] == b["id"]
    assert notes(client, librarian, o["id"], "room_participant_added") == []
'''),
    dict(id="T-ROOM-42-a", req="LIB-ROOM-42", type="Normal", input="Mon: group booking for Tue (organizer + P), individual booking for Wed; room reminders run twice; loan reminders run", expected="`{room_reminders: 2}`, then 0; loan reminders unchanged `{due_reminders: 0, overdue_notices: 0}`", code='''
def TEST(client, admin, librarian, branch_a):
    g, r1 = room(client, admin, branch_a, kind="group"), room(client, admin, branch_a)
    o, p, x = (member(client, librarian, branch_a) for _ in range(3))
    book(client, librarian, g["id"], TUE, "10:00", "11:00", member_id=o["id"], participant_ids=[p["id"]])
    book(client, librarian, r1["id"], "2026-11-04", "10:00", "11:00", member_id=x["id"])
    assert ok(client.post("/api/v1/room-bookings/run-reminders", headers=librarian)) == {"room_reminders": 2}
    assert ok(client.post("/api/v1/room-bookings/run-reminders", headers=librarian)) == {"room_reminders": 0}
    assert ok(client.post("/api/v1/notifications/run-reminders", headers=librarian)) == {"due_reminders": 0, "overdue_notices": 0}
'''),
    dict(id="T-ROOM-43-a", req="LIB-ROOM-43", type="Normal", input="Room created and booked; audit log filtered by event", expected="One `room_created` and one `room_booking_created` entry", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    for event in ("room_created", "room_booking_created"):
        assert len(items(ok(client.get("/api/v1/audit-log", headers=admin, params={"event": event})))) == 1
'''),
    dict(id="T-ROOM-44-a", req="LIB-ROOM-44", type="Normal", input="Room 08:00-20:00; 2-hour booking on Tue checked in and completed; report 2026-11-02 to 2026-11-06", expected="`open_hours` \"60.0\", `booked_hours` \"2.0\", `used_hours` \"2.0\", `no_shows` 0, `utilization` \"3.3\"", code='''
def TEST(client, clock, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    b = book(client, librarian, r1["id"], TUE, "10:00", "12:00", member_id=m["id"])
    at(clock, TUE, 10, 0); ok(act(client, librarian, b["id"], "check-in"))
    at(clock, TUE, 12, 0); process(client, librarian)
    rows = items(ok(client.get("/api/v1/reports/room-usage", headers=librarian, params={"from": "2026-11-02", "to": "2026-11-06"})))
    row = rows[0]
    assert (row["room_id"], row["open_hours"], row["booked_hours"], row["used_hours"], row["no_shows"], row["utilization"]) == (r1["id"], "60.0", "2.0", "2.0", 0, "3.3")
'''),
    dict(id="T-ROOM-44-b", req="LIB-ROOM-44", type="Error", input="`from` after `to`; range of 367 days; member", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/room-usage"
    assert client.get(url, headers=librarian, params={"from": "2026-11-06", "to": "2026-11-02"}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    assert client.get(url, headers=member_headers(client, m), params={"from": "2026-11-02", "to": "2026-11-06"}).status_code == 403
'''),
    dict(id="T-ROOM-45-a", req="LIB-ROOM-45", type="Normal", input="Rooms and a booking exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1 (no rooms or bookings)", code='''
def TEST(client, admin, librarian, branch_a):
    r1 = room(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    book(client, librarian, r1["id"], TUE, "10:00", "11:00", member_id=m["id"])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
