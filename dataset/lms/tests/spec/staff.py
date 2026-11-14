MODULE = "staff"
TITLE = "module 19 (Staff and shifts)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, deactivate_branch, error_code, items, lend, member_headers, register_member,
    return_loan, session,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, THU, FRI, SAT = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"
NMON, NTUE, NWED, NTHU, NFRI = "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"
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


def new_user(client, admin, role="librarian"):
    """A staff user and its (renewed) Authorization header."""
    _seq[0] += 1
    email, password = f"staff{_seq[0]}@library.local", "Staff12345"
    u = ok(client.post("/api/v1/users", headers=admin, json={"email": email, "full_name": f"Staff {_seq[0]:03d}",
                                                            "role": role, "password": password}), 201)
    return u, session(client, email, password)


def profile(client, admin, user_id, branch, *, employment="full_time", started_on="2020-01-01", expect=201, **fields):
    body = {"user_id": user_id, "home_branch_id": branch["id"], "employment": employment, "started_on": started_on}
    if employment == "part_time" and "weekly_hours" not in fields:
        body["weekly_hours"] = 20
    body.update(fields)
    r = client.post("/api/v1/staff", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def staff(client, admin, branch, **kw):
    """(profile, headers) of a new librarian with a staff profile."""
    u, h = new_user(client, admin)
    return profile(client, admin, u["id"], branch, **kw), h


def try_shift(client, admin, staff_id, branch, day, start, end):
    return client.post("/api/v1/shifts", headers=admin, json={"staff_id": staff_id, "branch_id": branch["id"],
                                                            "date": day, "start_time": start, "end_time": end})


def shift(client, admin, staff_id, branch, day, start, end):
    return ok(try_shift(client, admin, staff_id, branch, day, start, end), 201)


def post(client, headers, path, body=None):
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def get_shift(client, admin, shift_id):
    return [s for s in items(get(client, admin, "shifts")) if s["id"] == shift_id][0]


def closure(client, admin, branch, day, reason="Sayım"):
    return post(client, admin, f"branches/{branch['id']}/closures", {"date": day, "reason": reason})


def set_hours(client, admin, branch, opens, closes, min_staff=1):
    return client.put(f"/api/v1/branches/{branch['id']}/hours", headers=admin,
                      json={"opens_at": opens, "closes_at": closes, "min_staff": min_staff})


def leave(client, headers, kind, from_date, to_date, note=None):
    body = {"kind": kind, "from_date": from_date, "to_date": to_date}
    if note is not None:
        body["note"] = note
    return post(client, headers, "leave-requests", body)


def leave_of(client, admin, leave_id):
    return [x for x in items(get(client, admin, "leave-requests")) if x["id"] == leave_id][0]


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def room(client, admin, branch):
    _seq[0] += 1
    return ok(client.post("/api/v1/rooms", headers=admin, json={"branch_id": branch["id"], "code": f"R{_seq[0]}",
              "name": f"Room {_seq[0]}", "kind": "individual", "opens_at": "08:00", "closes_at": "20:00"}), 201)


def room_booking(client, lib, room_, member_, day, start="10:00", end="11:00"):
    return client.post("/api/v1/room-bookings", headers=lib, json={"room_id": room_["id"], "date": day,
                       "start_time": start, "end_time": end, "member_id": member_["id"]})


def equipment(client, admin, branch):
    """An equipment type (4 hours) with one item at ``branch``."""
    _seq[0] += 1
    t = ok(client.post("/api/v1/equipment-types", headers=admin, json={"code": f"T{_seq[0]}", "name": f"Type {_seq[0]}",
           "period_unit": "hours", "period": 4, "hourly_late_fee": "5.00", "requires_training": False,
           "max_open_per_member": 3}), 201)
    it = ok(client.post("/api/v1/equipment-items", headers=admin, json={"type_id": t["id"], "asset_tag": f"EQ-{_seq[0]:04d}",
            "serial_no": f"SN{_seq[0]}", "branch_id": branch["id"], "value": "1000.00", "acquired_on": "2025-01-01"}), 201)
    return t, it


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))
'''


CASES = [
    # ---------------------------------------------------------------- staff profiles
    dict(id="T-STF-01-a", req="LIB-STF-01", type="Normal", input="Admin creates a full-time profile without `weekly_hours` and `annual_leave_days`", expected="201; `weekly_hours` 40, `annual_leave_days` 14, active", code='''
def TEST(client, admin, branch_a):
    u, _ = new_user(client, admin)
    p = profile(client, admin, u["id"], branch_a)
    assert (p["user_id"], p["home_branch_id"], p["employment"], p["weekly_hours"], p["annual_leave_days"], p["is_active"]) == (u["id"], branch_a["id"], "full_time", 40, 14, True)
'''),
    dict(id="T-STF-01-b", req="LIB-STF-01", type="Error", input="Part-time without `weekly_hours`; full-time with 30; part-time 31 and 9; leave days 31; `started_on` tomorrow; librarian creates", expected="`422` six times; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    u, _ = new_user(client, admin)
    r = client.post("/api/v1/staff", headers=admin, json={"user_id": u["id"], "home_branch_id": branch_a["id"], "employment": "part_time", "started_on": "2020-01-01"})
    assert r.status_code == 422
    for fields in (dict(weekly_hours=30), dict(employment="part_time", weekly_hours=31), dict(employment="part_time", weekly_hours=9),
                   dict(annual_leave_days=31), dict(started_on=TUE)):
        profile(client, admin, u["id"], branch_a, expect=422, **fields)
    profile(client, librarian, u["id"], branch_a, expect=403)
'''),
    dict(id="T-STF-01-c", req="LIB-STF-01", type="Normal", input="Part-time profile with 20 weekly hours", expected="201; `annual_leave_days` 7", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a, employment="part_time", weekly_hours=20)
    assert (p["employment"], p["weekly_hours"], p["annual_leave_days"]) == ("part_time", 20, 7)
'''),
    dict(id="T-STF-02-a", req="LIB-STF-02", type="Error", input="Unknown user; a member's user; an inactive user; a user with a profile; an inactive home branch", expected="`404`; `409 NOT_STAFF_ROLE`; `409 USER_INACTIVE`; `409 CONFLICT` with `details.field` `user_id`; `409 BRANCH_INACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    assert profile(client, admin, 999999, branch_a, expect=404)
    m_user = get(client, member_headers(client, member(client, librarian, branch_a)), "auth/me")
    assert error_code(profile(client, admin, m_user["id"], branch_a, expect=409)) == "NOT_STAFF_ROLE"
    off, _ = new_user(client, admin)
    ok(client.patch(f"/api/v1/users/{off['id']}", headers=admin, json={"is_active": False}))
    assert error_code(profile(client, admin, off["id"], branch_a, expect=409)) == "USER_INACTIVE"
    p, _ = staff(client, admin, branch_a)
    assert profile(client, admin, p["user_id"], branch_a, expect=409)["error"]["details"]["field"] == "user_id"
    zz = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, zz["id"])
    u, _ = new_user(client, admin)
    assert error_code(profile(client, admin, u["id"], zz, expect=409)) == "BRANCH_INACTIVE"
'''),
    dict(id="T-STF-02-b", req="LIB-STF-02", type="Normal", input="Profile for the bootstrap admin user", expected="201", code='''
def TEST(client, admin, branch_a):
    me = get(client, admin, "auth/me")
    assert profile(client, admin, me["id"], branch_a)["user_id"] == me["id"]
'''),
    dict(id="T-STF-03-a", req="LIB-STF-03", type="Normal", input="PATCH employment `part_time` with 25 hours; PATCH employment `part_time` alone on a full-time profile (40 hours)", expected="200 with the new values; `422`", code='''
def TEST(client, admin, branch_a):
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    out = ok(client.patch(f"/api/v1/staff/{p1['id']}", headers=admin, json={"employment": "part_time", "weekly_hours": 25}))
    assert (out["employment"], out["weekly_hours"]) == ("part_time", 25)
    assert client.patch(f"/api/v1/staff/{p2['id']}", headers=admin, json={"employment": "part_time"}).status_code == 422
'''),
    dict(id="T-STF-04-a", req="LIB-STF-04", type="Normal", input="Profile with a planned shift Tue and a pending leave; profile deactivated; a new shift planned", expected="Shift `cancelled` with `staff_deactivated`; leave `cancelled`; `409 STAFF_INACTIVE`", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    lv = ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(client.patch(f"/api/v1/staff/{p['id']}", headers=admin, json={"is_active": False}))
    out = get_shift(client, admin, s["id"])
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_deactivated")
    assert leave_of(client, admin, lv["id"])["status"] == "cancelled"
    err(try_shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00"), 409, "STAFF_INACTIVE")
'''),
    dict(id="T-STF-05-a", req="LIB-STF-05", type="Normal", input="Profiles P1 (A, full-time) and P2 (B, part-time); list, filters; P2 reads `staff/me`", expected="Order P1, P2 with `full_name` and `email`; `home_branch_id` B → P2; `employment=full_time` → P1; `me` → P2", code='''
def TEST(client, admin, branch_a, branch_b):
    p1, _ = staff(client, admin, branch_a)
    p2, h2 = staff(client, admin, branch_b, employment="part_time")
    rows = items(get(client, admin, "staff"))
    assert [x["id"] for x in rows] == [p1["id"], p2["id"]] and rows[0]["email"].endswith("@library.local") and rows[0]["full_name"].startswith("Staff")
    assert [x["id"] for x in items(get(client, admin, "staff", home_branch_id=branch_b["id"]))] == [p2["id"]]
    assert [x["id"] for x in items(get(client, admin, "staff", employment="full_time"))] == [p1["id"]]
    assert get(client, h2, "staff/me")["id"] == p2["id"]
'''),
    dict(id="T-STF-05-b", req="LIB-STF-05", type="Error", input="Librarian without a profile reads `staff/me`; staff member reads another profile and the list; member reads the list", expected="`409 NOT_STAFF`; `403`; `403`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    err(client.get("/api/v1/staff/me", headers=librarian), 409, "NOT_STAFF")
    p1, h1 = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    assert client.get(f"/api/v1/staff/{p2['id']}", headers=h1).status_code == 403
    assert client.get(f"/api/v1/staff/{p1['id']}", headers=h1).status_code == 200
    assert client.get("/api/v1/staff", headers=h1).status_code == 403
    assert client.get("/api/v1/staff", headers=member_headers(client, member(client, librarian, branch_a))).status_code == 403
'''),
    dict(id="T-STF-06-a", req="LIB-STF-06", type="Normal", input="Staff user with a planned shift Tue is deactivated (`PATCH /users`)", expected="Profile inactive; shift `cancelled` with `staff_deactivated`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(client.patch(f"/api/v1/users/{p['user_id']}", headers=admin, json={"is_active": False}))
    assert get(client, admin, f"staff/{p['id']}")["is_active"] is False
    assert get_shift(client, admin, s["id"])["cancel_reason"] == "staff_deactivated"
'''),
    # ---------------------------------------------------------------- hours and closures
    dict(id="T-STF-07-a", req="LIB-STF-07", type="Normal", input="Member reads the hours of a branch never set; unknown branch", expected="`{opens_at 08:00, closes_at 20:00, min_staff 1}`; `404`", code='''
def TEST(client, librarian, branch_a):
    mh = member_headers(client, member(client, librarian, branch_a))
    assert get(client, mh, f"branches/{branch_a['id']}/hours") == {"branch_id": branch_a["id"], "opens_at": "08:00", "closes_at": "20:00", "min_staff": 1}
    assert client.get("/api/v1/branches/999999/hours", headers=mh).status_code == 404
'''),
    dict(id="T-STF-08-a", req="LIB-STF-08", type="Error", input="Set 09:00–18:00, min 2; then 18:00–09:00; 09:00–12:30 (under 4 h); min 11; 09:15; librarian sets", expected="200 with the values; `422` four times; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    assert ok(set_hours(client, admin, branch_a, "09:00", "18:00", 2)) == {"branch_id": branch_a["id"], "opens_at": "09:00", "closes_at": "18:00", "min_staff": 2}
    for args in (("18:00", "09:00", 1), ("09:00", "12:30", 1), ("09:00", "18:00", 11), ("09:15", "18:00", 1)):
        assert set_hours(client, admin, branch_a, *args).status_code == 422
    assert set_hours(client, librarian, branch_a, "09:00", "18:00").status_code == 403
'''),
    dict(id="T-STF-08-b", req="LIB-STF-08", type="Error", input="Planned shift Tue 08:00–12:00; hours changed to 09:00–20:00", expected="`409 SHIFTS_OUTSIDE_HOURS` with `details.shift_ids`; hours unchanged", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "08:00", "12:00")
    assert err(set_hours(client, admin, branch_a, "09:00", "20:00"), 409, "SHIFTS_OUTSIDE_HOURS")["details"]["shift_ids"] == [s["id"]]
    assert get(client, admin, f"branches/{branch_a['id']}/hours")["opens_at"] == "08:00"
'''),
    dict(id="T-STF-09-a", req="LIB-STF-09", type="Boundary", input="Branch hours 10:00–18:00; equipment lent Mon 09:30, then 10:00", expected="`409 DESK_CLOSED` with `opens_at` Mon 10:00; then 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(set_hours(client, admin, branch_a, "10:00", "18:00"))
    _, it = equipment(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, MON, 9, 30)
    e = err(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], MON, 10)
    at(clock, MON, 10)
    ok(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 201)
'''),
    dict(id="T-STF-09-b", req="LIB-STF-09", type="Normal", input="Closure of branch A on Tue; equipment lent Tue 10:00", expected="`409 DESK_CLOSED` with `opens_at` Wed 08:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    _, it = equipment(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ok(closure(client, admin, branch_a, TUE), 201)
    at(clock, TUE, 10)
    e = err(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], WED, 8)
'''),
    dict(id="T-STF-10-a", req="LIB-STF-10", type="Normal", input="Admin adds a closure for Wed with reason Sayım", expected="201 with `date`, `reason`, `created_by` and zero counts", code='''
def TEST(client, admin, branch_a):
    c = ok(closure(client, admin, branch_a, WED, "Sayım"), 201)
    assert (c["branch_id"], c["date"], c["reason"], c["cancelled_shifts"], c["cancelled_room_bookings"], c["cancelled_equipment_reservations"]) == (branch_a["id"], WED, "Sayım", 0, 0, 0)
    assert c["created_by"] is not None
'''),
    dict(id="T-STF-10-b", req="LIB-STF-10", type="Error", input="Closure today; on Saturday; twice on Wed; for an inactive branch; empty reason", expected="`422`; `409 NOT_A_WORKING_DAY`; `409 CONFLICT`; `409 BRANCH_INACTIVE`; `422`", code='''
def TEST(client, admin, branch_a):
    assert closure(client, admin, branch_a, MON).status_code == 422
    err(closure(client, admin, branch_a, SAT), 409, "NOT_A_WORKING_DAY")
    ok(closure(client, admin, branch_a, WED), 201)
    err(closure(client, admin, branch_a, WED), 409, "CONFLICT")
    zz = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, zz["id"])
    err(closure(client, admin, zz, WED), 409, "BRANCH_INACTIVE")
    assert closure(client, admin, branch_a, THU, "").status_code == 422
'''),
    dict(id="T-STF-11-a", req="LIB-STF-11", type="Normal", input="Branch A on Wed: a planned shift, a room booking 10:00–11:00 and an equipment reservation 10:00; closure added for Wed", expected="Counts 1, 1, 1; all three cancelled with `branch_closed`; the member gets `room_booking_cancelled` and `equipment_reservation_cancelled`", code='''
def TEST(client, admin, librarian, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    m = member(client, librarian, branch_a)
    b = ok(room_booking(client, librarian, room(client, admin, branch_a), m, WED), 201)
    t, _ = equipment(client, admin, branch_a)
    res = ok(post(client, librarian, "equipment-reservations", {"type_id": t["id"], "branch_id": branch_a["id"], "starts_at": f"{WED}T10:00:00+03:00", "member_id": m["id"]}), 201)
    c = ok(closure(client, admin, branch_a, WED), 201)
    assert (c["cancelled_shifts"], c["cancelled_room_bookings"], c["cancelled_equipment_reservations"]) == (1, 1, 1)
    assert get_shift(client, admin, s["id"])["cancel_reason"] == "branch_closed"
    assert (get(client, librarian, f"room-bookings/{b['id']}")["cancel_reason"], get(client, librarian, f"equipment-reservations/{res['id']}")["cancel_reason"]) == ("branch_closed", "branch_closed")
    assert len(notes(client, librarian, m["id"], "room_booking_cancelled")) == 1
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1
'''),
    dict(id="T-STF-11-b", req="LIB-STF-11", type="Normal", input="Shift at branch B on Wed and a shift at branch A on Thu; closure of A on Wed", expected="`cancelled_shifts` 0; both shifts stay `planned`", code='''
def TEST(client, admin, branch_a, branch_b):
    p, _ = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_b, WED, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    assert ok(closure(client, admin, branch_a, WED), 201)["cancelled_shifts"] == 0
    assert [get_shift(client, admin, x["id"])["status"] for x in (s1, s2)] == ["planned", "planned"]
'''),
    dict(id="T-STF-12-a", req="LIB-STF-12", type="Normal", input="Closure Wed cancels a shift; the closure is removed on Mon; another closure Thu removed on Thu", expected="`204`, the shift stays `cancelled`; `409 CLOSURE_IN_PAST`", code='''
def TEST(client, clock, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    c1, c2 = ok(closure(client, admin, branch_a, WED), 201), ok(closure(client, admin, branch_a, THU), 201)
    assert client.delete(f"/api/v1/closures/{c1['id']}", headers=admin).status_code == 204
    assert get_shift(client, admin, s["id"])["status"] == "cancelled"
    at(clock, THU, 9)
    err(client.delete(f"/api/v1/closures/{c2['id']}", headers=admin), 409, "CLOSURE_IN_PAST")
'''),
    dict(id="T-STF-13-a", req="LIB-STF-13", type="Normal", input="Closures B Wed, A Thu, A Wed; list; `branch_id` A; `from`=`to`=Thu", expected="A Wed, B Wed, A Thu; A Wed, A Thu; A Thu", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    bw, at_, aw = ok(closure(client, admin, branch_b, WED), 201), ok(closure(client, admin, branch_a, THU), 201), ok(closure(client, admin, branch_a, WED), 201)
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "closures", **p))]
    assert ids() == [aw["id"], bw["id"], at_["id"]]
    assert ids(branch_id=branch_a["id"]) == [aw["id"], at_["id"]]
    assert ids(**{"from": THU, "to": THU}) == [at_["id"]]
'''),
    dict(id="T-STF-14-a", req="LIB-STF-14", type="Normal", input="Closure of A on Wed 2026-11-11 (Sayım); open days 2026-11-09 – 2026-11-15", expected="Mon, Tue, Thu, Fri open 08:00–20:00; Wed `closure: Sayım`; Sat, Sun `weekend`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(closure(client, admin, branch_a, NWED, "Sayım"), 201)
    out = get(client, librarian, f"branches/{branch_a['id']}/open-days", **{"from": NMON, "to": "2026-11-15"})
    got = [(d["date"], d["open"], d["reason"], d["opens_at"]) for d in out["days"]]
    assert got == [(NMON, True, None, "08:00"), (NTUE, True, None, "08:00"), (NWED, False, "closure: Sayım", None), (NTHU, True, None, "08:00"),
                   (NFRI, True, None, "08:00"), ("2026-11-14", False, "weekend", None), ("2026-11-15", False, "weekend", None)]
'''),
    dict(id="T-STF-14-b", req="LIB-STF-14", type="Error", input="Open days 2026-10-28 – 2026-10-30; a range of 63 days", expected="10-29 `holiday`, 10-28 and 10-30 open; `422`", code='''
def TEST(client, librarian, branch_a):
    out = get(client, librarian, f"branches/{branch_a['id']}/open-days", **{"from": "2026-10-28", "to": "2026-10-30"})
    assert [(d["open"], d["reason"]) for d in out["days"]] == [(True, None), (False, "holiday"), (True, None)]
    assert client.get(f"/api/v1/branches/{branch_a['id']}/open-days", headers=librarian, params={"from": NMON, "to": "2027-01-10"}).status_code == 422
'''),
    dict(id="T-STF-15-a", req="LIB-STF-15", type="Error", input="Closure of A on Wed; availability of a room of A on Wed; booking it", expected="`open` false, `slots` empty; `409 ROOM_CLOSED`", code='''
def TEST(client, admin, librarian, branch_a):
    r = room(client, admin, branch_a)
    ok(closure(client, admin, branch_a, WED), 201)
    out = get(client, librarian, f"rooms/{r['id']}/availability", date=WED)
    assert (out["open"], out["slots"]) == (False, [])
    err(room_booking(client, librarian, r, member(client, librarian, branch_a), WED), 409, "ROOM_CLOSED")
'''),
    dict(id="T-STF-16-a", req="LIB-STF-16", type="Error", input="Book lent Mon; closure of A on Wed; on Wed returned at A, then at B", expected="`409 BRANCH_CLOSED_TODAY`; 200", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
    copy = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"])
    ok(closure(client, admin, branch_a, WED), 201)
    at(clock, WED, 10)
    assert error_code(return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], expect=409)) == "BRANCH_CLOSED_TODAY"
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])
'''),
    dict(id="T-STF-17-a", req="LIB-STF-17", type="Normal", input="Student loan of a member of A due 2026-11-16; closure of A on 2026-11-16; on 2026-11-17 the member borrows another book", expected="`due_date` stays 2026-11-16; `409 MEMBER_HAS_OVERDUE` (closures do not move due dates)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    c1 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], c1["id"])
    ok(closure(client, admin, branch_a, "2026-11-16"), 201)
    assert get(client, librarian, f"loans/{loan['id']}")["due_date"] == "2026-11-16"
    at(clock, "2026-11-17", 10)
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"
'''),
    # ---------------------------------------------------------------- shifts
    dict(id="T-STF-18-a", req="LIB-STF-18", type="Normal", input="Admin plans a shift Tue 10:00–14:30", expected="201: `planned`, `hours` 4.5, `staff_name`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:30")
    assert (s["staff_id"], s["branch_id"], s["date"], s["start_time"], s["end_time"], s["status"], s["hours"]) == (p["id"], branch_a["id"], TUE, "10:00", "14:30", "planned", 4.5)
    assert s["staff_name"].startswith("Staff")
'''),
    dict(id="T-STF-18-b", req="LIB-STF-18", type="Error", input="Start 10:15; 1.5 hours; 10.5 hours; librarian plans", expected="`422` three times; `403`", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    for start, end in (("10:15", "14:00"), ("10:00", "11:30"), ("08:00", "18:30")):
        assert try_shift(client, admin, p["id"], branch_a, TUE, start, end).status_code == 422
    assert try_shift(client, h, p["id"], branch_a, TUE, "10:00", "14:00").status_code == 403
'''),
    dict(id="T-STF-19-a", req="LIB-STF-19", type="Error", input="Shift at an inactive branch; shift yesterday", expected="`409 BRANCH_INACTIVE`; `409 SHIFT_IN_PAST`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    qq = create_branch(client, admin, "QQ")
    deactivate_branch(client, admin, qq["id"])
    err(try_shift(client, admin, p["id"], qq, TUE, "10:00", "14:00"), 409, "BRANCH_INACTIVE")
    err(try_shift(client, admin, p["id"], branch_a, "2026-10-30", "10:00", "14:00"), 409, "SHIFT_IN_PAST")
'''),
    dict(id="T-STF-19-b", req="LIB-STF-19", type="Error", input="Shifts on Saturday, on the holiday 2027-01-01 and on a closure day", expected="`409 BRANCH_NOT_OPEN` with `details.reason` `weekend`, `holiday`, `closure`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    ok(closure(client, admin, branch_a, WED), 201)
    for day, reason in ((SAT, "weekend"), ("2027-01-01", "holiday"), (WED, "closure")):
        assert err(try_shift(client, admin, p["id"], branch_a, day, "10:00", "14:00"), 409, "BRANCH_NOT_OPEN")["details"]["reason"] == reason
'''),
    dict(id="T-STF-19-c", req="LIB-STF-19", type="Boundary", input="Default hours 08:00–20:00: shifts 07:30–11:30, 16:30–20:30, then 16:00–20:00", expected="`409 OUTSIDE_BRANCH_HOURS` twice; 201", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    err(try_shift(client, admin, p["id"], branch_a, TUE, "07:30", "11:30"), 409, "OUTSIDE_BRANCH_HOURS")
    err(try_shift(client, admin, p["id"], branch_a, TUE, "16:30", "20:30"), 409, "OUTSIDE_BRANCH_HOURS")
    shift(client, admin, p["id"], branch_a, TUE, "16:00", "20:00")
'''),
    dict(id="T-STF-19-d", req="LIB-STF-19", type="Error", input="Approved annual leave 2026-11-09 – 2026-11-13; shift on 2026-11-10", expected="`409 STAFF_ON_LEAVE` with `details.leave_id`", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    assert err(try_shift(client, admin, p["id"], branch_a, NTUE, "10:00", "14:00"), 409, "STAFF_ON_LEAVE")["details"]["leave_id"] == lv["id"]
'''),
    dict(id="T-STF-19-e", req="LIB-STF-19", type="Boundary", input="Shift Tue 10:00–14:00; same staff Tue 13:00–17:00, then 14:00–18:00", expected="`409 SHIFT_OVERLAP` with `details.shift_id`; 201 (touching is not overlapping)", code='''
def TEST(client, admin, branch_a, branch_b):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    assert err(try_shift(client, admin, p["id"], branch_b, TUE, "13:00", "17:00"), 409, "SHIFT_OVERLAP")["details"]["shift_id"] == s["id"]
    shift(client, admin, p["id"], branch_a, TUE, "14:00", "18:00")
'''),
    dict(id="T-STF-19-f", req="LIB-STF-19", type="Error", input="Inactive profile plans a shift on Saturday; active profile plans a shift yesterday on a Saturday (2026-10-31)", expected="`STAFF_INACTIVE`; `SHIFT_IN_PAST` (order of the checks)", code='''
def TEST(client, admin, branch_a):
    off, _ = staff(client, admin, branch_a)
    ok(client.patch(f"/api/v1/staff/{off['id']}", headers=admin, json={"is_active": False}))
    p, _ = staff(client, admin, branch_a)
    err(try_shift(client, admin, off["id"], branch_a, SAT, "10:00", "14:00"), 409, "STAFF_INACTIVE")
    err(try_shift(client, admin, p["id"], branch_a, "2026-10-31", "10:00", "14:00"), 409, "SHIFT_IN_PAST")
'''),
    dict(id="T-STF-20-a", req="LIB-STF-20", type="Boundary", input="Branch hours 07:00–22:00; shift Mon 2026-11-09 14:00–22:00; Tue 08:00–12:00, then Tue 09:00–13:00", expected="`409 REST_PERIOD_TOO_SHORT`; 201", code='''
def TEST(client, admin, branch_a):
    ok(set_hours(client, admin, branch_a, "07:00", "22:00"))
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NMON, "14:00", "22:00")
    err(try_shift(client, admin, p["id"], branch_a, NTUE, "08:00", "12:00"), 409, "REST_PERIOD_TOO_SHORT")
    shift(client, admin, p["id"], branch_a, NTUE, "09:00", "13:00")
'''),
    dict(id="T-STF-20-b", req="LIB-STF-20", type="Normal", input="Branch hours 07:00–22:00; shift Wed 2026-11-11 07:00–15:00; then Tue 2026-11-10 14:00–22:00 (rest to the next day)", expected="`409 REST_PERIOD_TOO_SHORT` (9 hours)", code='''
def TEST(client, admin, branch_a):
    ok(set_hours(client, admin, branch_a, "07:00", "22:00"))
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NWED, "07:00", "15:00")
    err(try_shift(client, admin, p["id"], branch_a, NTUE, "14:00", "22:00"), 409, "REST_PERIOD_TOO_SHORT")
'''),
    dict(id="T-STF-21-a", req="LIB-STF-21", type="Boundary", input="Part-time 20 h: shifts Mon 4 h, Tue 8 h, Wed 8 h (week of 2026-11-09); Thu 2 h; Mon cancelled; Thu 4 h; next Mon 4 h", expected="`409 WEEKLY_HOURS_EXCEEDED` with `planned_hours` 20 and `limit` 20; then 201 twice", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a, employment="part_time", weekly_hours=20)
    mon = shift(client, admin, p["id"], branch_a, NMON, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, NTUE, "09:00", "17:00")
    shift(client, admin, p["id"], branch_a, NWED, "09:00", "17:00")
    e = err(try_shift(client, admin, p["id"], branch_a, NTHU, "10:00", "12:00"), 409, "WEEKLY_HOURS_EXCEEDED")
    assert (e["details"]["planned_hours"], e["details"]["limit"]) == (20, 20)
    ok(post(client, admin, f"shifts/{mon['id']}/cancel"))
    shift(client, admin, p["id"], branch_a, NTHU, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, "2026-11-16", "10:00", "14:00")
'''),
    dict(id="T-STF-22-a", req="LIB-STF-22", type="Error", input="Shifts Tue 10:00–14:00 (S1) and 15:00–19:00; S1 changed to end 16:00, then 15:00; at Mon 10:30 a shift of Mon 10:00 is changed", expected="`409 SHIFT_OVERLAP`; 200; `409 SHIFT_NOT_CHANGEABLE`", code='''
def TEST(client, clock, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, TUE, "15:00", "19:00")
    now = shift(client, admin, p["id"], branch_a, MON, "10:00", "14:00")
    err(client.patch(f"/api/v1/shifts/{s1['id']}", headers=admin, json={"end_time": "16:00"}), 409, "SHIFT_OVERLAP")
    assert ok(client.patch(f"/api/v1/shifts/{s1['id']}", headers=admin, json={"end_time": "15:00"}))["end_time"] == "15:00"
    at(clock, MON, 10, 30)
    err(client.patch(f"/api/v1/shifts/{now['id']}", headers=admin, json={"end_time": "13:00"}), 409, "SHIFT_NOT_CHANGEABLE")
'''),
    dict(id="T-STF-22-b", req="LIB-STF-22", type="Normal", input="Shift of P1 Tue 10:00–14:00 moved to P2", expected="200 with `staff_id` P2", code='''
def TEST(client, admin, branch_a):
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p1["id"], branch_a, TUE, "10:00", "14:00")
    assert ok(client.patch(f"/api/v1/shifts/{s['id']}", headers=admin, json={"staff_id": p2["id"]}))["staff_id"] == p2["id"]
'''),
    dict(id="T-STF-23-a", req="LIB-STF-23", type="Normal", input="Cancel a planned shift; cancel it again", expected="200 `cancelled` with `staff_request`; `409 SHIFT_NOT_CHANGEABLE`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    out = ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    err(post(client, admin, f"shifts/{s['id']}/cancel"), 409, "SHIFT_NOT_CHANGEABLE")
'''),
    dict(id="T-STF-24-a", req="LIB-STF-24", type="Normal", input="Shifts S3 (P2, Wed 10:00), S1 (P1, Tue 14:00), S2 (P1, Tue 08:00 at B); list; filters; P1 reads the list and P2's shifts", expected="Order S2, S1, S3; `branch_id` B → S2; `from`=`to`=Wed → S3; P1 sees S2, S1; P1 with `staff_id` P2 → `403`", code='''
def TEST(client, admin, branch_a, branch_b):
    p1, h1 = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    s3 = shift(client, admin, p2["id"], branch_a, WED, "10:00", "14:00")
    s1 = shift(client, admin, p1["id"], branch_a, TUE, "14:00", "18:00")
    s2 = shift(client, admin, p1["id"], branch_b, TUE, "08:00", "12:00")
    ids = lambda h, **p: [x["id"] for x in items(get(client, h, "shifts", **p))]
    assert ids(admin) == [s2["id"], s1["id"], s3["id"]]
    assert ids(admin, branch_id=branch_b["id"]) == [s2["id"]]
    assert ids(admin, **{"from": WED, "to": WED}) == [s3["id"]]
    assert ids(h1) == [s2["id"], s1["id"]]
    assert client.get("/api/v1/shifts", headers=h1, params={"staff_id": p2["id"]}).status_code == 403
'''),
    dict(id="T-STF-25-a", req="LIB-STF-25", type="Normal", input="Shifts of branch A (Tue 2026-11-03 and Thu 11-05) and of branch B (Wed); copy week 2026-11-02 of A to 2026-11-16", expected="`created` 2, `skipped` empty; shifts of A on 11-17 and 11-19 with the same times; nothing for B", code='''
def TEST(client, admin, branch_a, branch_b):
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, TUE, "09:00", "13:00")
    shift(client, admin, p["id"], branch_a, THU, "14:00", "18:00")
    shift(client, admin, p["id"], branch_b, WED, "10:00", "14:00")
    assert ok(post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": "2026-11-16"})) == {"created": 2, "skipped": []}
    rows = items(get(client, admin, "shifts", **{"from": "2026-11-16", "to": "2026-11-22"}))
    assert [(x["date"], x["start_time"], x["end_time"], x["branch_id"]) for x in rows] == [("2026-11-17", "09:00", "13:00", branch_a["id"]), ("2026-11-19", "14:00", "18:00", branch_a["id"])]
'''),
    dict(id="T-STF-26-a", req="LIB-STF-26", type="Normal", input="Shifts of branch A on Mon 2026-11-02, Tue 11-03, Wed 11-04; closure on Tue 2026-11-10; copy week 2026-11-02 to 2026-11-09", expected="`created` 2; `skipped` [Tue shift, `BRANCH_NOT_OPEN`]; new shifts on 11-09 and 11-11", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, MON, "10:00", "14:00")
    tue = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    ok(closure(client, admin, branch_a, NTUE), 201)
    out = ok(post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": NMON}))
    assert out["created"] == 2 and out["skipped"] == [{"source_shift_id": tue["id"], "error_code": "BRANCH_NOT_OPEN"}]
    assert [x["date"] for x in items(get(client, admin, "shifts", **{"from": NMON, "to": "2026-11-15"}))] == [NMON, NWED]
'''),
    dict(id="T-STF-25-b", req="LIB-STF-25", type="Error", input="Copy to a Tuesday; copy to the week before `from_week`", expected="`422` both", code='''
def TEST(client, admin, branch_a):
    assert post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": NTUE}).status_code == 422
    assert post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": NMON, "to_week": MON}).status_code == 422
'''),
    dict(id="T-STF-27-a", req="LIB-STF-27", type="Normal", input="Shift Tue 10:00–12:00 of a staff member; read in the shift list", expected="`hours` 2.0 and `staff_name` equal to the user's `full_name`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "12:00")
    row = get_shift(client, admin, s["id"])
    assert row["hours"] == 2.0 and row["staff_name"] == get(client, admin, f"users/{p['user_id']}")["full_name"]
'''),
    # ---------------------------------------------------------------- attendance
    dict(id="T-STF-28-a", req="LIB-STF-28", type="Error", input="Admin checks in a librarian's shift; another librarian checks it in", expected="`403` both", code='''
def TEST(client, clock, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    _, other = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    assert post(client, admin, f"shifts/{s['id']}/check-in").status_code == 403
    assert post(client, other, f"shifts/{s['id']}/check-in").status_code == 403
'''),
    dict(id="T-STF-29-a", req="LIB-STF-29", type="Boundary", input="Shift Tue 10:00–14:00: check-in at 09:29, at 09:30, again", expected="`409 CHECK_IN_TOO_EARLY` with `opens_at` 09:30; 200; `409 SHIFT_NOT_CHANGEABLE`", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 9, 29)
    assert same(err(post(client, h, f"shifts/{s['id']}/check-in"), 409, "CHECK_IN_TOO_EARLY")["details"]["opens_at"], TUE, 9, 30)
    at(clock, TUE, 9, 30)
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    err(post(client, h, f"shifts/{s['id']}/check-in"), 409, "SHIFT_NOT_CHANGEABLE")
'''),
    dict(id="T-STF-29-b", req="LIB-STF-29", type="Boundary", input="Shift Wed 10:00–14:00: check-in at 14:00; another shift Thu 10:00–14:00 checked in at 13:59", expected="`409 SHIFT_OVER`; 200", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    at(clock, WED, 14)
    err(post(client, h, f"shifts/{s1['id']}/check-in"), 409, "SHIFT_OVER")
    at(clock, THU, 13, 59)
    ok(post(client, h, f"shifts/{s2['id']}/check-in"))
'''),
    dict(id="T-STF-30-a", req="LIB-STF-30", type="Boundary", input="Shifts 09:00–13:00 on Tue, Wed, Thu; check-ins at 09:05, 09:06 and 08:40", expected="`late_minutes` 0, 6, 0; `checked_in_at` set", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    got = []
    for day, hh, mm in ((TUE, 9, 5), (WED, 9, 6), (THU, 8, 40)):
        s = shift(client, admin, p["id"], branch_a, day, "09:00", "13:00")
        at(clock, day, hh, mm)
        out = ok(post(client, h, f"shifts/{s['id']}/check-in"))
        assert same(out["checked_in_at"], day, hh, mm)
        got.append(out["late_minutes"])
    assert got == [0, 6, 0]
'''),
    dict(id="T-STF-31-a", req="LIB-STF-31", type="Normal", input="Shift Tue 09:00–17:00 in 08:50, out 17:20; shift Wed 09:00–17:00 in 09:30, out 16:00", expected="`completed` with `worked_minutes` 480 and 390", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    got = []
    for day, cin, cout in ((TUE, (8, 50), (17, 20)), (WED, (9, 30), (16, 0))):
        s = shift(client, admin, p["id"], branch_a, day, "09:00", "17:00")
        at(clock, day, *cin)
        ok(post(client, h, f"shifts/{s['id']}/check-in"))
        at(clock, day, *cout)
        out = ok(post(client, h, f"shifts/{s['id']}/check-out"))
        got.append((out["status"], out["worked_minutes"]))
    assert got == [("completed", 480), ("completed", 390)]
'''),
    dict(id="T-STF-31-b", req="LIB-STF-31", type="Error", input="Check-out without check-in; check-out twice", expected="`409 NOT_CHECKED_IN`; `409 SHIFT_NOT_CHANGEABLE`", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    err(post(client, h, f"shifts/{s['id']}/check-out"), 409, "NOT_CHECKED_IN")
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    at(clock, TUE, 14)
    ok(post(client, h, f"shifts/{s['id']}/check-out"))
    err(post(client, h, f"shifts/{s['id']}/check-out"), 409, "SHIFT_NOT_CHANGEABLE")
'''),
    dict(id="T-STF-32-a", req="LIB-STF-32", type="Boundary", input="Shift S1 Tue 09:00–17:00 checked in at 09:00 and never checked out; process at 18:00, then 18:00:01", expected="`auto_checked_out` 0, then 1; S1 `completed`, `checked_out_at` 18:00, `worked_minutes` 480", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "09:00", "17:00")
    at(clock, TUE, 9)
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    at(clock, TUE, 18)
    assert ok(post(client, admin, "staff/process"))["auto_checked_out"] == 0
    at(clock, TUE, 18, 0, 1)
    assert ok(post(client, admin, "staff/process")) == {"missed": 0, "auto_checked_out": 1}
    out = get_shift(client, admin, s["id"])
    assert out["status"] == "completed" and same(out["checked_out_at"], TUE, 18) and out["worked_minutes"] == 480
'''),
    dict(id="T-STF-33-a", req="LIB-STF-33", type="Boundary", input="Shift Tue 09:00–17:00 without check-in; process at Tue 16:59 and at 17:00:01", expected="`missed` 0, then 1; status `missed`", code='''
def TEST(client, clock, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "09:00", "17:00")
    at(clock, TUE, 16, 59)
    assert ok(post(client, admin, "staff/process"))["missed"] == 0
    at(clock, TUE, 17, 0, 1)
    assert ok(post(client, admin, "staff/process"))["missed"] == 1
    assert get_shift(client, admin, s["id"])["status"] == "missed"
'''),
    # ---------------------------------------------------------------- leave
    dict(id="T-STF-34-a", req="LIB-STF-34", type="Normal", input="Staff member requests annual leave Mon 2026-11-09 – Fri 2026-11-13 with a note", expected="201: own `staff_id`, `pending`, `days` 5", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI, "Tatil"), 201)
    assert (lv["staff_id"], lv["kind"], lv["status"], lv["days"], lv["note"]) == (p["id"], "annual", "pending", 5, "Tatil")
'''),
    dict(id="T-STF-34-b", req="LIB-STF-34", type="Error", input="`from_date` after `to_date`; 31 calendar days; note of 501 characters; kind `paid`; librarian without profile", expected="`422` four times; `409 NOT_STAFF`", code='''
def TEST(client, admin, librarian, branch_a):
    _, h = staff(client, admin, branch_a)
    assert leave(client, h, "annual", NFRI, NMON).status_code == 422
    assert leave(client, h, "unpaid", NMON, "2026-12-09").status_code == 422
    assert leave(client, h, "annual", NMON, NTUE, "x" * 501).status_code == 422
    assert leave(client, h, "paid", NMON, NTUE).status_code == 422
    err(leave(client, librarian, "annual", NMON, NTUE), 409, "NOT_STAFF")
'''),
    dict(id="T-STF-35-a", req="LIB-STF-35", type="Boundary", input="Today Mon 2026-11-02: annual from 11-01; sick 2026-10-26 – 10-27 (7 days before); sick from 2026-10-25", expected="`409 LEAVE_IN_PAST`; 201; `409 LEAVE_IN_PAST`", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    err(leave(client, h, "annual", "2026-11-01", TUE), 409, "LEAVE_IN_PAST")
    ok(leave(client, h, "sick", "2026-10-26", "2026-10-27"), 201)
    err(leave(client, h, "sick", "2026-10-25", "2026-10-25"), 409, "LEAVE_IN_PAST")
'''),
    dict(id="T-STF-35-b", req="LIB-STF-35", type="Error", input="Leave Sat–Sun; annual 11-09 – 11-13 then unpaid 11-12 – 11-16", expected="`409 NO_WORKING_DAYS`; `409 LEAVE_OVERLAP` with `details.leave_id`", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    err(leave(client, h, "unpaid", SAT, "2026-11-08"), 409, "NO_WORKING_DAYS")
    first = ok(leave(client, h, "annual", NMON, NFRI), 201)
    assert err(leave(client, h, "unpaid", NTHU, "2026-11-16"), 409, "LEAVE_OVERLAP")["details"]["leave_id"] == first["id"]
'''),
    dict(id="T-STF-35-c", req="LIB-STF-35", type="Boundary", input="Part-time profile (7 days): annual 2026-11-09 – 2026-11-18 (8 days); then 2026-11-09 – 2026-11-17 (7 days)", expected="`409 LEAVE_BALANCE_EXCEEDED` with `details.remaining` 7; 201", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a, employment="part_time")
    assert err(leave(client, h, "annual", NMON, "2026-11-18"), 409, "LEAVE_BALANCE_EXCEEDED")["details"]["remaining"] == 7
    assert ok(leave(client, h, "annual", NMON, "2026-11-17"), 201)["days"] == 7
'''),
    dict(id="T-STF-36-a", req="LIB-STF-36", type="Normal", input="On 2026-10-20 annual leave Fri 2026-10-23 – Tue 2026-11-03 is requested", expected="`days` 7 (29 Oct holiday, 28 Oct arife counts, weekends not counted)", code='''
def TEST(client, clock, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    at(clock, "2026-10-20")
    assert ok(leave(client, h, "annual", "2026-10-23", TUE), 201)["days"] == 7
'''),
    dict(id="T-STF-37-a", req="LIB-STF-37", type="Normal", input="P1: annual 11-16 (L2), unpaid 11-09 (L1); P2: annual 11-10 (L3); list; filters; P1 reads the list and P2's", expected="Order L1, L3, L2; `kind=annual` → L3, L2; `staff_id` P1 → L1, L2; P1 sees L1, L2; P1 with `staff_id` P2 → `403`", code='''
def TEST(client, admin, branch_a):
    p1, h1 = staff(client, admin, branch_a)
    p2, h2 = staff(client, admin, branch_a)
    l2 = ok(leave(client, h1, "annual", "2026-11-16", "2026-11-17"), 201)
    l1 = ok(leave(client, h1, "unpaid", NMON, NTUE), 201)
    l3 = ok(leave(client, h2, "annual", NTUE, NWED), 201)
    ids = lambda h, **p: [x["id"] for x in items(get(client, h, "leave-requests", **p))]
    assert ids(admin) == [l1["id"], l3["id"], l2["id"]]
    assert ids(admin, kind="annual") == [l3["id"], l2["id"]]
    assert ids(admin, staff_id=p1["id"]) == [l1["id"], l2["id"]]
    assert ids(h1) == [l1["id"], l2["id"]]
    assert client.get("/api/v1/leave-requests", headers=h1, params={"staff_id": p2["id"]}).status_code == 403
'''),
    dict(id="T-STF-38-a", req="LIB-STF-38", type="Normal", input="Admin approves L1 with a note; approves it again; rejects L2", expected="L1 `approved`, `decided_by` and `decision_note` set; `409 LEAVE_NOT_PENDING`; L2 `rejected`", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    l1 = ok(leave(client, h, "annual", NMON, NTUE), 201)
    l2 = ok(leave(client, h, "unpaid", "2026-11-16", "2026-11-17"), 201)
    out = ok(post(client, admin, f"leave-requests/{l1['id']}/approve", {"note": "Uygun"}))
    assert (out["status"], out["decision_note"]) == ("approved", "Uygun") and out["decided_by"] is not None and out["decided_at"] is not None
    err(post(client, admin, f"leave-requests/{l1['id']}/approve", {}), 409, "LEAVE_NOT_PENDING")
    assert ok(post(client, admin, f"leave-requests/{l2['id']}/reject", {}))["status"] == "rejected"
'''),
    dict(id="T-STF-38-b", req="LIB-STF-38", type="Error", input="Admin with a profile approves own leave; a librarian approves a leave", expected="`409 OWN_LEAVE`; `403`", code='''
def TEST(client, admin, branch_a):
    profile(client, admin, get(client, admin, "auth/me")["id"], branch_a)
    own = ok(leave(client, admin, "annual", NMON, NTUE), 201)
    err(post(client, admin, f"leave-requests/{own['id']}/approve", {}), 409, "OWN_LEAVE")
    _, h = staff(client, admin, branch_a)
    assert post(client, h, f"leave-requests/{own['id']}/approve", {}).status_code == 403
'''),
    dict(id="T-STF-39-a", req="LIB-STF-39", type="Normal", input="Shifts on 11-10 and 11-16; annual leave 11-09 – 11-13 approved", expected="`cancelled_shift_ids` [11-10 shift]; it is `cancelled` with `leave`; the 11-16 shift stays `planned`", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, NTUE, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, "2026-11-16", "10:00", "14:00")
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    assert ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))["cancelled_shift_ids"] == [s1["id"]]
    assert get_shift(client, admin, s1["id"])["cancel_reason"] == "leave"
    assert get_shift(client, admin, s2["id"])["status"] == "planned"
'''),
    dict(id="T-STF-40-a", req="LIB-STF-40", type="Normal", input="Full-time (14 days): approved annual 11-09 – 11-13 (5), pending annual 11-16 – 11-18 (3); balance 2026 and 2027", expected="2026 `{entitled 14, used 5, pending 3, remaining 6}`; 2027 `{14, 0, 0, 14}`", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    ok(leave(client, h, "annual", "2026-11-16", "2026-11-18"), 201)
    keys = ("entitled", "used", "pending", "remaining")
    b = get(client, h, f"staff/{p['id']}/leave-balance")
    assert (b["year"], *(b[k] for k in keys)) == (2026, 14, 5, 3, 6)
    assert tuple(get(client, admin, f"staff/{p['id']}/leave-balance", year=2027)[k] for k in keys) == (14, 0, 0, 14)
'''),
    dict(id="T-STF-40-b", req="LIB-STF-40", type="Normal", input="Profile with 14 days started on 2026-07-01; balance 2026; another staff member reads it", expected="`entitled` 7; `403`", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a, started_on="2026-07-01")
    _, other = staff(client, admin, branch_a)
    assert get(client, admin, f"staff/{p['id']}/leave-balance", year=2026)["entitled"] == 7
    assert client.get(f"/api/v1/staff/{p['id']}/leave-balance", headers=other).status_code == 403
'''),
    dict(id="T-STF-41-a", req="LIB-STF-41", type="Normal", input="Owner cancels a pending leave; owner cancels an approved leave; admin cancels it", expected="`cancelled`; `409 LEAVE_NOT_CANCELLABLE`; `cancelled`", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    l1 = ok(leave(client, h, "annual", NMON, NTUE), 201)
    l2 = ok(leave(client, h, "unpaid", "2026-11-16", "2026-11-17"), 201)
    assert ok(post(client, h, f"leave-requests/{l1['id']}/cancel"))["status"] == "cancelled"
    ok(post(client, admin, f"leave-requests/{l2['id']}/approve", {}))
    err(post(client, h, f"leave-requests/{l2['id']}/cancel"), 409, "LEAVE_NOT_CANCELLABLE")
    assert ok(post(client, admin, f"leave-requests/{l2['id']}/cancel"))["status"] == "cancelled"
'''),
    dict(id="T-STF-42-a", req="LIB-STF-42", type="Normal", input="Shift Wed; sick leave Tue–Wed (2 days); sick leave 11-09 – 11-11 (3 days); balance", expected="First `approved` with `decided_by` null, the Wed shift cancelled with `leave`; second `pending`; `used` 0", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    l1 = ok(leave(client, h, "sick", TUE, WED), 201)
    assert (l1["status"], l1["decided_by"]) == ("approved", None)
    assert get_shift(client, admin, s["id"])["cancel_reason"] == "leave"
    assert ok(leave(client, h, "sick", NMON, NWED), 201)["status"] == "pending"
    assert get(client, admin, f"staff/{p['id']}/leave-balance")["used"] == 0
'''),
    # ---------------------------------------------------------------- reports and effects
    dict(id="T-STF-43-a", req="LIB-STF-43", type="Normal", input="Tue 09:00–17:00 in 09:10, out 17:00; Wed 09:00–13:00 missed; sick Thu–Fri; report 2026-11-02 – 2026-11-08", expected="`{planned_hours 8, worked_hours 7.8, missed_shifts 1, late_minutes 10, leave_days 2}`", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, TUE, "09:00", "17:00")
    shift(client, admin, p["id"], branch_a, WED, "09:00", "13:00")
    ok(leave(client, h, "sick", THU, FRI), 201)
    at(clock, TUE, 9, 10)
    ok(post(client, h, f"shifts/{s1['id']}/check-in"))
    at(clock, TUE, 17)
    ok(post(client, h, f"shifts/{s1['id']}/check-out"))
    at(clock, WED, 13, 0, 1)
    ok(post(client, admin, "staff/process"))
    row = [r for r in items(get(client, admin, "reports/staff-hours", **{"from": MON, "to": "2026-11-08"})) if r["staff_id"] == p["id"]][0]
    assert (row["planned_hours"], row["worked_hours"], row["missed_shifts"], row["late_minutes"], row["leave_days"]) == (8, 7.8, 1, 10, 2)
'''),
    dict(id="T-STF-43-b", req="LIB-STF-43", type="Error", input="Range of 93 days; librarian reads the report", expected="`422`; `403`", code='''
def TEST(client, admin, branch_a):
    _, h = staff(client, admin, branch_a)
    assert client.get("/api/v1/reports/staff-hours", headers=admin, params={"from": MON, "to": "2027-02-02"}).status_code == 422
    assert client.get("/api/v1/reports/staff-hours", headers=h, params={"from": MON, "to": TUE}).status_code == 403
'''),
    dict(id="T-STF-44-a", req="LIB-STF-44", type="Normal", input="`min_staff` 2; shifts 08:00–14:00 and 13:00–19:00 on 2026-11-09; coverage", expected="24 slots; 08:00 staff 1 not ok; 13:00 and 13:30 staff 2 ok; 19:30 staff 0", code='''
def TEST(client, admin, branch_a):
    ok(set_hours(client, admin, branch_a, "08:00", "20:00", 2))
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    shift(client, admin, p1["id"], branch_a, NMON, "08:00", "14:00")
    shift(client, admin, p2["id"], branch_a, NMON, "13:00", "19:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], date=NMON)
    slots = {s["start"]: (s["staff"], s["ok"]) for s in out["slots"]}
    assert (out["open"], out["min_staff"], len(out["slots"])) == (True, 2, 24)
    assert (slots["08:00"], slots["13:00"], slots["13:30"], slots["19:30"]) == ((1, False), (2, True), (2, True), (0, False))
'''),
    dict(id="T-STF-44-b", req="LIB-STF-44", type="Normal", input="Coverage on Saturday", expected="`open` false, `slots` empty", code='''
def TEST(client, admin, branch_a):
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], date=SAT)
    assert (out["open"], out["slots"]) == (False, [])
'''),
    dict(id="T-STF-45-a", req="LIB-STF-45", type="Normal", input="Closure Wed 2026-11-11; shift Mon 11-09 08:00–18:00 only; understaffed days 11-09 – 11-15; a range of 32 days", expected="Mon 4, Tue 24, Thu 24, Fri 24 (Wed and the weekend not listed); `422`", code='''
def TEST(client, admin, branch_a):
    ok(closure(client, admin, branch_a, NWED), 201)
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NMON, "08:00", "18:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], **{"from": NMON, "to": "2026-11-15"})
    assert [(d["date"], d["missing_slots"]) for d in out["days"]] == [(NMON, 4), (NTUE, 24), (NTHU, 24), (NFRI, 24)]
    assert client.get("/api/v1/reports/branch-coverage", headers=admin, params={"branch_id": branch_a["id"], "from": NMON, "to": "2026-12-10"}).status_code == 422
'''),
    dict(id="T-STF-46-a", req="LIB-STF-46", type="Normal", input="Hours 08:00–20:00, `min_staff` 1; shifts 08:00–14:00 and 13:00–19:00 on 2026-11-09", expected="`missing_slots` 2 (19:00 and 19:30)", code='''
def TEST(client, admin, branch_a):
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    shift(client, admin, p1["id"], branch_a, NMON, "08:00", "14:00")
    shift(client, admin, p2["id"], branch_a, NMON, "13:00", "19:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], **{"from": NMON, "to": NMON})
    assert out["days"] == [{"date": NMON, "missing_slots": 2}]
'''),
    dict(id="T-STF-47-a", req="LIB-STF-47", type="Error", input="Branch QQ is the home branch of a staff profile; QQ deactivated", expected="`409 BRANCH_IN_USE`", code='''
def TEST(client, admin):
    qq = create_branch(client, admin, "QQ")
    staff(client, admin, qq)
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
'''),
    dict(id="T-STF-48-a", req="LIB-STF-48", type="Error", input="Staff member checked in on Tue 10:00; admin deactivates the user at 11:00", expected="`409 SHIFT_IN_PROGRESS`; the user stays active", code='''
def TEST(client, clock, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    at(clock, TUE, 11)
    err(client.patch(f"/api/v1/users/{p['user_id']}", headers=admin, json={"is_active": False}), 409, "SHIFT_IN_PROGRESS")
    assert get(client, admin, f"users/{p['user_id']}")["is_active"] is True
'''),
    dict(id="T-STF-49-a", req="LIB-STF-49", type="Normal", input="Member with a room booking on Wed at branch A; closure of A on Wed", expected="The member's booking notification has type `room_booking_cancelled`; staff actions create no notifications", code='''
def TEST(client, admin, librarian, branch_a):
    m = member(client, librarian, branch_a)
    ok(room_booking(client, librarian, room(client, admin, branch_a), m, WED), 201)
    before = get(client, librarian, f"members/{m['id']}/notifications")["total"]
    p, h = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(closure(client, admin, branch_a, WED), 201)
    after = items(get(client, librarian, f"members/{m['id']}/notifications"))
    assert len(after) == before + 1 and [n["type"] for n in after].count("room_booking_cancelled") == 1
'''),
    dict(id="T-STF-50-a", req="LIB-STF-50", type="Normal", input="Profile created, hours set, closure added, shift planned and cancelled, leave requested and approved; audit log filtered by event", expected="One entry each", code='''
def TEST(client, admin, branch_a):
    p, h = staff(client, admin, branch_a)
    ok(set_hours(client, admin, branch_a, "08:00", "19:00"))
    ok(closure(client, admin, branch_a, WED), 201)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    lv = ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    for event in ("staff_created", "branch_hours_updated", "branch_closure_added", "shift_planned", "shift_cancelled", "leave_requested", "leave_approved"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-STF-51-a", req="LIB-STF-51", type="Normal", input="Staff profile, shift and closure exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, branch_a):
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(closure(client, admin, branch_a, WED), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
