"""Feedback tests: module 19 (Staff and shifts). Generated from cases/staff.md."""
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


def test_t_stf_01_a(client, admin, branch_a):
    """T-STF-01-a (LIB-STF-01): 201; weekly_hours 40, annual_leave_days 14, active"""
    u, _ = new_user(client, admin)
    p = profile(client, admin, u["id"], branch_a)
    assert (p["user_id"], p["home_branch_id"], p["employment"], p["weekly_hours"], p["annual_leave_days"], p["is_active"]) == (u["id"], branch_a["id"], "full_time", 40, 14, True)


def test_t_stf_01_c(client, admin, branch_a):
    """T-STF-01-c (LIB-STF-01): 201; annual_leave_days 7"""
    p, _ = staff(client, admin, branch_a, employment="part_time", weekly_hours=20)
    assert (p["employment"], p["weekly_hours"], p["annual_leave_days"]) == ("part_time", 20, 7)


def test_t_stf_02_a(client, admin, librarian, branch_a):
    """T-STF-02-a (LIB-STF-02): 404; 409 NOT_STAFF_ROLE; 409 USER_INACTIVE; 409 CONFLICT with details.field user_id; 409 BRANCH_INACTIVE"""
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


def test_t_stf_03_a(client, admin, branch_a):
    """T-STF-03-a (LIB-STF-03): 200 with the new values; 422"""
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    out = ok(client.patch(f"/api/v1/staff/{p1['id']}", headers=admin, json={"employment": "part_time", "weekly_hours": 25}))
    assert (out["employment"], out["weekly_hours"]) == ("part_time", 25)
    assert client.patch(f"/api/v1/staff/{p2['id']}", headers=admin, json={"employment": "part_time"}).status_code == 422


def test_t_stf_05_a(client, admin, branch_a, branch_b):
    """T-STF-05-a (LIB-STF-05): Order P1, P2 with full_name and email; home_branch_id B → P2; employment=full_time → P1; me → P2"""
    p1, _ = staff(client, admin, branch_a)
    p2, h2 = staff(client, admin, branch_b, employment="part_time")
    rows = items(get(client, admin, "staff"))
    assert [x["id"] for x in rows] == [p1["id"], p2["id"]] and rows[0]["email"].endswith("@library.local") and rows[0]["full_name"].startswith("Staff")
    assert [x["id"] for x in items(get(client, admin, "staff", home_branch_id=branch_b["id"]))] == [p2["id"]]
    assert [x["id"] for x in items(get(client, admin, "staff", employment="full_time"))] == [p1["id"]]
    assert get(client, h2, "staff/me")["id"] == p2["id"]


def test_t_stf_07_a(client, librarian, branch_a):
    """T-STF-07-a (LIB-STF-07): {opens_at 08:00, closes_at 20:00, min_staff 1}; 404"""
    mh = member_headers(client, member(client, librarian, branch_a))
    assert get(client, mh, f"branches/{branch_a['id']}/hours") == {"branch_id": branch_a["id"], "opens_at": "08:00", "closes_at": "20:00", "min_staff": 1}
    assert client.get("/api/v1/branches/999999/hours", headers=mh).status_code == 404


def test_t_stf_08_a(client, admin, librarian, branch_a):
    """T-STF-08-a (LIB-STF-08): 200 with the values; 422 four times; 403"""
    assert ok(set_hours(client, admin, branch_a, "09:00", "18:00", 2)) == {"branch_id": branch_a["id"], "opens_at": "09:00", "closes_at": "18:00", "min_staff": 2}
    for args in (("18:00", "09:00", 1), ("09:00", "12:30", 1), ("09:00", "18:00", 11), ("09:15", "18:00", 1)):
        assert set_hours(client, admin, branch_a, *args).status_code == 422
    assert set_hours(client, librarian, branch_a, "09:00", "18:00").status_code == 403


def test_t_stf_09_a(client, clock, admin, librarian, branch_a):
    """T-STF-09-a (LIB-STF-09): 409 DESK_CLOSED with opens_at Mon 10:00; then 201"""
    ok(set_hours(client, admin, branch_a, "10:00", "18:00"))
    _, it = equipment(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, MON, 9, 30)
    e = err(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], MON, 10)
    at(clock, MON, 10)
    ok(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 201)


def test_t_stf_10_a(client, admin, branch_a):
    """T-STF-10-a (LIB-STF-10): 201 with date, reason, created_by and zero counts"""
    c = ok(closure(client, admin, branch_a, WED, "Sayım"), 201)
    assert (c["branch_id"], c["date"], c["reason"], c["cancelled_shifts"], c["cancelled_room_bookings"], c["cancelled_equipment_reservations"]) == (branch_a["id"], WED, "Sayım", 0, 0, 0)
    assert c["created_by"] is not None


def test_t_stf_11_a(client, admin, librarian, branch_a):
    """T-STF-11-a (LIB-STF-11): Counts 1, 1, 1; all three cancelled with branch_closed; the member gets room_booking_cancelled and equipment_reservation_cancelled"""
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


def test_t_stf_13_a(client, admin, librarian, branch_a, branch_b):
    """T-STF-13-a (LIB-STF-13): A Wed, B Wed, A Thu; A Wed, A Thu; A Thu"""
    bw, at_, aw = ok(closure(client, admin, branch_b, WED), 201), ok(closure(client, admin, branch_a, THU), 201), ok(closure(client, admin, branch_a, WED), 201)
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "closures", **p))]
    assert ids() == [aw["id"], bw["id"], at_["id"]]
    assert ids(branch_id=branch_a["id"]) == [aw["id"], at_["id"]]
    assert ids(**{"from": THU, "to": THU}) == [at_["id"]]


def test_t_stf_14_a(client, admin, librarian, branch_a):
    """T-STF-14-a (LIB-STF-14): Mon, Tue, Thu, Fri open 08:00–20:00; Wed closure: Sayım; Sat, Sun weekend"""
    ok(closure(client, admin, branch_a, NWED, "Sayım"), 201)
    out = get(client, librarian, f"branches/{branch_a['id']}/open-days", **{"from": NMON, "to": "2026-11-15"})
    got = [(d["date"], d["open"], d["reason"], d["opens_at"]) for d in out["days"]]
    assert got == [(NMON, True, None, "08:00"), (NTUE, True, None, "08:00"), (NWED, False, "closure: Sayım", None), (NTHU, True, None, "08:00"),
                   (NFRI, True, None, "08:00"), ("2026-11-14", False, "weekend", None), ("2026-11-15", False, "weekend", None)]


def test_t_stf_15_a(client, admin, librarian, branch_a):
    """T-STF-15-a (LIB-STF-15): open false, slots empty; 409 ROOM_CLOSED"""
    r = room(client, admin, branch_a)
    ok(closure(client, admin, branch_a, WED), 201)
    out = get(client, librarian, f"rooms/{r['id']}/availability", date=WED)
    assert (out["open"], out["slots"]) == (False, [])
    err(room_booking(client, librarian, r, member(client, librarian, branch_a), WED), 409, "ROOM_CLOSED")


def test_t_stf_17_a(client, clock, admin, librarian, branch_a):
    """T-STF-17-a (LIB-STF-17): due_date stays 2026-11-16; 409 MEMBER_HAS_OVERDUE (closures do not move due dates)"""
    m = member(client, librarian, branch_a)
    c1 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    c2 = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, m["id"], c1["id"])
    ok(closure(client, admin, branch_a, "2026-11-16"), 201)
    assert get(client, librarian, f"loans/{loan['id']}")["due_date"] == "2026-11-16"
    at(clock, "2026-11-17", 10)
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"


def test_t_stf_18_a(client, admin, branch_a):
    """T-STF-18-a (LIB-STF-18): 201: planned, hours 4.5, staff_name"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:30")
    assert (s["staff_id"], s["branch_id"], s["date"], s["start_time"], s["end_time"], s["status"], s["hours"]) == (p["id"], branch_a["id"], TUE, "10:00", "14:30", "planned", 4.5)
    assert s["staff_name"].startswith("Staff")


def test_t_stf_19_a(client, admin, branch_a):
    """T-STF-19-a (LIB-STF-19): 409 BRANCH_INACTIVE; 409 SHIFT_IN_PAST"""
    p, _ = staff(client, admin, branch_a)
    qq = create_branch(client, admin, "QQ")
    deactivate_branch(client, admin, qq["id"])
    err(try_shift(client, admin, p["id"], qq, TUE, "10:00", "14:00"), 409, "BRANCH_INACTIVE")
    err(try_shift(client, admin, p["id"], branch_a, "2026-10-30", "10:00", "14:00"), 409, "SHIFT_IN_PAST")


def test_t_stf_19_c(client, admin, branch_a):
    """T-STF-19-c (LIB-STF-19): 409 OUTSIDE_BRANCH_HOURS twice; 201"""
    p, _ = staff(client, admin, branch_a)
    err(try_shift(client, admin, p["id"], branch_a, TUE, "07:30", "11:30"), 409, "OUTSIDE_BRANCH_HOURS")
    err(try_shift(client, admin, p["id"], branch_a, TUE, "16:30", "20:30"), 409, "OUTSIDE_BRANCH_HOURS")
    shift(client, admin, p["id"], branch_a, TUE, "16:00", "20:00")


def test_t_stf_19_e(client, admin, branch_a, branch_b):
    """T-STF-19-e (LIB-STF-19): 409 SHIFT_OVERLAP with details.shift_id; 201 (touching is not overlapping)"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    assert err(try_shift(client, admin, p["id"], branch_b, TUE, "13:00", "17:00"), 409, "SHIFT_OVERLAP")["details"]["shift_id"] == s["id"]
    shift(client, admin, p["id"], branch_a, TUE, "14:00", "18:00")


def test_t_stf_20_a(client, admin, branch_a):
    """T-STF-20-a (LIB-STF-20): 409 REST_PERIOD_TOO_SHORT; 201"""
    ok(set_hours(client, admin, branch_a, "07:00", "22:00"))
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NMON, "14:00", "22:00")
    err(try_shift(client, admin, p["id"], branch_a, NTUE, "08:00", "12:00"), 409, "REST_PERIOD_TOO_SHORT")
    shift(client, admin, p["id"], branch_a, NTUE, "09:00", "13:00")


def test_t_stf_21_a(client, admin, branch_a):
    """T-STF-21-a (LIB-STF-21): 409 WEEKLY_HOURS_EXCEEDED with planned_hours 20 and limit 20; then 201 twice"""
    p, _ = staff(client, admin, branch_a, employment="part_time", weekly_hours=20)
    mon = shift(client, admin, p["id"], branch_a, NMON, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, NTUE, "09:00", "17:00")
    shift(client, admin, p["id"], branch_a, NWED, "09:00", "17:00")
    e = err(try_shift(client, admin, p["id"], branch_a, NTHU, "10:00", "12:00"), 409, "WEEKLY_HOURS_EXCEEDED")
    assert (e["details"]["planned_hours"], e["details"]["limit"]) == (20, 20)
    ok(post(client, admin, f"shifts/{mon['id']}/cancel"))
    shift(client, admin, p["id"], branch_a, NTHU, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, "2026-11-16", "10:00", "14:00")


def test_t_stf_22_a(client, clock, admin, branch_a):
    """T-STF-22-a (LIB-STF-22): 409 SHIFT_OVERLAP; 200; 409 SHIFT_NOT_CHANGEABLE"""
    p, _ = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, TUE, "15:00", "19:00")
    now = shift(client, admin, p["id"], branch_a, MON, "10:00", "14:00")
    err(client.patch(f"/api/v1/shifts/{s1['id']}", headers=admin, json={"end_time": "16:00"}), 409, "SHIFT_OVERLAP")
    assert ok(client.patch(f"/api/v1/shifts/{s1['id']}", headers=admin, json={"end_time": "15:00"}))["end_time"] == "15:00"
    at(clock, MON, 10, 30)
    err(client.patch(f"/api/v1/shifts/{now['id']}", headers=admin, json={"end_time": "13:00"}), 409, "SHIFT_NOT_CHANGEABLE")


def test_t_stf_23_a(client, admin, branch_a):
    """T-STF-23-a (LIB-STF-23): 200 cancelled with staff_request; 409 SHIFT_NOT_CHANGEABLE"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    out = ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    err(post(client, admin, f"shifts/{s['id']}/cancel"), 409, "SHIFT_NOT_CHANGEABLE")


def test_t_stf_25_a(client, admin, branch_a, branch_b):
    """T-STF-25-a (LIB-STF-25): created 2, skipped empty; shifts of A on 11-17 and 11-19 with the same times; nothing for B"""
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, TUE, "09:00", "13:00")
    shift(client, admin, p["id"], branch_a, THU, "14:00", "18:00")
    shift(client, admin, p["id"], branch_b, WED, "10:00", "14:00")
    assert ok(post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": "2026-11-16"})) == {"created": 2, "skipped": []}
    rows = items(get(client, admin, "shifts", **{"from": "2026-11-16", "to": "2026-11-22"}))
    assert [(x["date"], x["start_time"], x["end_time"], x["branch_id"]) for x in rows] == [("2026-11-17", "09:00", "13:00", branch_a["id"]), ("2026-11-19", "14:00", "18:00", branch_a["id"])]


def test_t_stf_27_a(client, admin, branch_a):
    """T-STF-27-a (LIB-STF-27): hours 2.0 and staff_name equal to the user's full_name"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "12:00")
    row = get_shift(client, admin, s["id"])
    assert row["hours"] == 2.0 and row["staff_name"] == get(client, admin, f"users/{p['user_id']}")["full_name"]


def test_t_stf_29_a(client, clock, admin, branch_a):
    """T-STF-29-a (LIB-STF-29): 409 CHECK_IN_TOO_EARLY with opens_at 09:30; 200; 409 SHIFT_NOT_CHANGEABLE"""
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 9, 29)
    assert same(err(post(client, h, f"shifts/{s['id']}/check-in"), 409, "CHECK_IN_TOO_EARLY")["details"]["opens_at"], TUE, 9, 30)
    at(clock, TUE, 9, 30)
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    err(post(client, h, f"shifts/{s['id']}/check-in"), 409, "SHIFT_NOT_CHANGEABLE")


def test_t_stf_31_a(client, clock, admin, branch_a):
    """T-STF-31-a (LIB-STF-31): completed with worked_minutes 480 and 390"""
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


def test_t_stf_33_a(client, clock, admin, branch_a):
    """T-STF-33-a (LIB-STF-33): missed 0, then 1; status missed"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "09:00", "17:00")
    at(clock, TUE, 16, 59)
    assert ok(post(client, admin, "staff/process"))["missed"] == 0
    at(clock, TUE, 17, 0, 1)
    assert ok(post(client, admin, "staff/process"))["missed"] == 1
    assert get_shift(client, admin, s["id"])["status"] == "missed"


def test_t_stf_34_a(client, admin, branch_a):
    """T-STF-34-a (LIB-STF-34): 201: own staff_id, pending, days 5"""
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI, "Tatil"), 201)
    assert (lv["staff_id"], lv["kind"], lv["status"], lv["days"], lv["note"]) == (p["id"], "annual", "pending", 5, "Tatil")


def test_t_stf_35_a(client, admin, branch_a):
    """T-STF-35-a (LIB-STF-35): 409 LEAVE_IN_PAST; 201; 409 LEAVE_IN_PAST"""
    _, h = staff(client, admin, branch_a)
    err(leave(client, h, "annual", "2026-11-01", TUE), 409, "LEAVE_IN_PAST")
    ok(leave(client, h, "sick", "2026-10-26", "2026-10-27"), 201)
    err(leave(client, h, "sick", "2026-10-25", "2026-10-25"), 409, "LEAVE_IN_PAST")


def test_t_stf_35_c(client, admin, branch_a):
    """T-STF-35-c (LIB-STF-35): 409 LEAVE_BALANCE_EXCEEDED with details.remaining 7; 201"""
    _, h = staff(client, admin, branch_a, employment="part_time")
    assert err(leave(client, h, "annual", NMON, "2026-11-18"), 409, "LEAVE_BALANCE_EXCEEDED")["details"]["remaining"] == 7
    assert ok(leave(client, h, "annual", NMON, "2026-11-17"), 201)["days"] == 7


def test_t_stf_37_a(client, admin, branch_a):
    """T-STF-37-a (LIB-STF-37): Order L1, L3, L2; kind=annual → L3, L2; staff_id P1 → L1, L2; P1 sees L1, L2; P1 with staff_id P2 → 403"""
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


def test_t_stf_38_a(client, admin, branch_a):
    """T-STF-38-a (LIB-STF-38): L1 approved, decided_by and decision_note set; 409 LEAVE_NOT_PENDING; L2 rejected"""
    _, h = staff(client, admin, branch_a)
    l1 = ok(leave(client, h, "annual", NMON, NTUE), 201)
    l2 = ok(leave(client, h, "unpaid", "2026-11-16", "2026-11-17"), 201)
    out = ok(post(client, admin, f"leave-requests/{l1['id']}/approve", {"note": "Uygun"}))
    assert (out["status"], out["decision_note"]) == ("approved", "Uygun") and out["decided_by"] is not None and out["decided_at"] is not None
    err(post(client, admin, f"leave-requests/{l1['id']}/approve", {}), 409, "LEAVE_NOT_PENDING")
    assert ok(post(client, admin, f"leave-requests/{l2['id']}/reject", {}))["status"] == "rejected"


def test_t_stf_39_a(client, admin, branch_a):
    """T-STF-39-a (LIB-STF-39): cancelled_shift_ids [11-10 shift]; it is cancelled with leave; the 11-16 shift stays planned"""
    p, h = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, NTUE, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, "2026-11-16", "10:00", "14:00")
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    assert ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))["cancelled_shift_ids"] == [s1["id"]]
    assert get_shift(client, admin, s1["id"])["cancel_reason"] == "leave"
    assert get_shift(client, admin, s2["id"])["status"] == "planned"


def test_t_stf_40_a(client, admin, branch_a):
    """T-STF-40-a (LIB-STF-40): 2026 {entitled 14, used 5, pending 3, remaining 6}; 2027 {14, 0, 0, 14}"""
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    ok(leave(client, h, "annual", "2026-11-16", "2026-11-18"), 201)
    keys = ("entitled", "used", "pending", "remaining")
    b = get(client, h, f"staff/{p['id']}/leave-balance")
    assert (b["year"], *(b[k] for k in keys)) == (2026, 14, 5, 3, 6)
    assert tuple(get(client, admin, f"staff/{p['id']}/leave-balance", year=2027)[k] for k in keys) == (14, 0, 0, 14)


def test_t_stf_41_a(client, admin, branch_a):
    """T-STF-41-a (LIB-STF-41): cancelled; 409 LEAVE_NOT_CANCELLABLE; cancelled"""
    _, h = staff(client, admin, branch_a)
    l1 = ok(leave(client, h, "annual", NMON, NTUE), 201)
    l2 = ok(leave(client, h, "unpaid", "2026-11-16", "2026-11-17"), 201)
    assert ok(post(client, h, f"leave-requests/{l1['id']}/cancel"))["status"] == "cancelled"
    ok(post(client, admin, f"leave-requests/{l2['id']}/approve", {}))
    err(post(client, h, f"leave-requests/{l2['id']}/cancel"), 409, "LEAVE_NOT_CANCELLABLE")
    assert ok(post(client, admin, f"leave-requests/{l2['id']}/cancel"))["status"] == "cancelled"


def test_t_stf_43_a(client, clock, admin, branch_a):
    """T-STF-43-a (LIB-STF-43): {planned_hours 8, worked_hours 7.8, missed_shifts 1, late_minutes 10, leave_days 2}"""
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


def test_t_stf_44_a(client, admin, branch_a):
    """T-STF-44-a (LIB-STF-44): 24 slots; 08:00 staff 1 not ok; 13:00 and 13:30 staff 2 ok; 19:30 staff 0"""
    ok(set_hours(client, admin, branch_a, "08:00", "20:00", 2))
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    shift(client, admin, p1["id"], branch_a, NMON, "08:00", "14:00")
    shift(client, admin, p2["id"], branch_a, NMON, "13:00", "19:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], date=NMON)
    slots = {s["start"]: (s["staff"], s["ok"]) for s in out["slots"]}
    assert (out["open"], out["min_staff"], len(out["slots"])) == (True, 2, 24)
    assert (slots["08:00"], slots["13:00"], slots["13:30"], slots["19:30"]) == ((1, False), (2, True), (2, True), (0, False))


def test_t_stf_45_a(client, admin, branch_a):
    """T-STF-45-a (LIB-STF-45): Mon 4, Tue 24, Thu 24, Fri 24 (Wed and the weekend not listed); 422"""
    ok(closure(client, admin, branch_a, NWED), 201)
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NMON, "08:00", "18:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], **{"from": NMON, "to": "2026-11-15"})
    assert [(d["date"], d["missing_slots"]) for d in out["days"]] == [(NMON, 4), (NTUE, 24), (NTHU, 24), (NFRI, 24)]
    assert client.get("/api/v1/reports/branch-coverage", headers=admin, params={"branch_id": branch_a["id"], "from": NMON, "to": "2026-12-10"}).status_code == 422


def test_t_stf_47_a(client, admin):
    """T-STF-47-a (LIB-STF-47): 409 BRANCH_IN_USE"""
    qq = create_branch(client, admin, "QQ")
    staff(client, admin, qq)
    err(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_t_stf_49_a(client, admin, librarian, branch_a):
    """T-STF-49-a (LIB-STF-49): The member's booking notification has type room_booking_cancelled; staff actions create no notifications"""
    m = member(client, librarian, branch_a)
    ok(room_booking(client, librarian, room(client, admin, branch_a), m, WED), 201)
    before = get(client, librarian, f"members/{m['id']}/notifications")["total"]
    p, h = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(closure(client, admin, branch_a, WED), 201)
    after = items(get(client, librarian, f"members/{m['id']}/notifications"))
    assert len(after) == before + 1 and [n["type"] for n in after].count("room_booking_cancelled") == 1


def test_t_stf_51_a(client, admin, branch_a):
    """T-STF-51-a (LIB-STF-51): The export has exactly the keys of 22.1"""
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(closure(client, admin, branch_a, WED), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
