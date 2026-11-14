"""Heldout tests: module 19 (Staff and shifts). Generated from cases/staff.md."""
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


def test_t_stf_01_b(client, admin, librarian, branch_a):
    """T-STF-01-b (LIB-STF-01): 422 six times; 403"""
    u, _ = new_user(client, admin)
    r = client.post("/api/v1/staff", headers=admin, json={"user_id": u["id"], "home_branch_id": branch_a["id"], "employment": "part_time", "started_on": "2020-01-01"})
    assert r.status_code == 422
    for fields in (dict(weekly_hours=30), dict(employment="part_time", weekly_hours=31), dict(employment="part_time", weekly_hours=9),
                   dict(annual_leave_days=31), dict(started_on=TUE)):
        profile(client, admin, u["id"], branch_a, expect=422, **fields)
    profile(client, librarian, u["id"], branch_a, expect=403)


def test_t_stf_02_b(client, admin, branch_a):
    """T-STF-02-b (LIB-STF-02): 201"""
    me = get(client, admin, "auth/me")
    assert profile(client, admin, me["id"], branch_a)["user_id"] == me["id"]


def test_t_stf_04_a(client, admin, branch_a):
    """T-STF-04-a (LIB-STF-04): Shift cancelled with staff_deactivated; leave cancelled; 409 STAFF_INACTIVE"""
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    lv = ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(client.patch(f"/api/v1/staff/{p['id']}", headers=admin, json={"is_active": False}))
    out = get_shift(client, admin, s["id"])
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_deactivated")
    assert leave_of(client, admin, lv["id"])["status"] == "cancelled"
    err(try_shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00"), 409, "STAFF_INACTIVE")


def test_t_stf_05_b(client, admin, librarian, branch_a):
    """T-STF-05-b (LIB-STF-05): 409 NOT_STAFF; 403; 403; 403"""
    err(client.get("/api/v1/staff/me", headers=librarian), 409, "NOT_STAFF")
    p1, h1 = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    assert client.get(f"/api/v1/staff/{p2['id']}", headers=h1).status_code == 403
    assert client.get(f"/api/v1/staff/{p1['id']}", headers=h1).status_code == 200
    assert client.get("/api/v1/staff", headers=h1).status_code == 403
    assert client.get("/api/v1/staff", headers=member_headers(client, member(client, librarian, branch_a))).status_code == 403


def test_t_stf_06_a(client, admin, branch_a):
    """T-STF-06-a (LIB-STF-06): Profile inactive; shift cancelled with staff_deactivated"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(client.patch(f"/api/v1/users/{p['user_id']}", headers=admin, json={"is_active": False}))
    assert get(client, admin, f"staff/{p['id']}")["is_active"] is False
    assert get_shift(client, admin, s["id"])["cancel_reason"] == "staff_deactivated"


def test_t_stf_08_b(client, admin, branch_a):
    """T-STF-08-b (LIB-STF-08): 409 SHIFTS_OUTSIDE_HOURS with details.shift_ids; hours unchanged"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "08:00", "12:00")
    assert err(set_hours(client, admin, branch_a, "09:00", "20:00"), 409, "SHIFTS_OUTSIDE_HOURS")["details"]["shift_ids"] == [s["id"]]
    assert get(client, admin, f"branches/{branch_a['id']}/hours")["opens_at"] == "08:00"


def test_t_stf_09_b(client, clock, admin, librarian, branch_a):
    """T-STF-09-b (LIB-STF-09): 409 DESK_CLOSED with opens_at Wed 08:00"""
    _, it = equipment(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    ok(closure(client, admin, branch_a, TUE), 201)
    at(clock, TUE, 10)
    e = err(post(client, librarian, "equipment-loans", {"member_id": m["id"], "item_id": it["id"]}), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], WED, 8)


def test_t_stf_10_b(client, admin, branch_a):
    """T-STF-10-b (LIB-STF-10): 422; 409 NOT_A_WORKING_DAY; 409 CONFLICT; 409 BRANCH_INACTIVE; 422"""
    assert closure(client, admin, branch_a, MON).status_code == 422
    err(closure(client, admin, branch_a, SAT), 409, "NOT_A_WORKING_DAY")
    ok(closure(client, admin, branch_a, WED), 201)
    err(closure(client, admin, branch_a, WED), 409, "CONFLICT")
    zz = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, zz["id"])
    err(closure(client, admin, zz, WED), 409, "BRANCH_INACTIVE")
    assert closure(client, admin, branch_a, THU, "").status_code == 422


def test_t_stf_11_b(client, admin, branch_a, branch_b):
    """T-STF-11-b (LIB-STF-11): cancelled_shifts 0; both shifts stay planned"""
    p, _ = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_b, WED, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    assert ok(closure(client, admin, branch_a, WED), 201)["cancelled_shifts"] == 0
    assert [get_shift(client, admin, x["id"])["status"] for x in (s1, s2)] == ["planned", "planned"]


def test_t_stf_12_a(client, clock, admin, branch_a):
    """T-STF-12-a (LIB-STF-12): 204, the shift stays cancelled; 409 CLOSURE_IN_PAST"""
    p, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    c1, c2 = ok(closure(client, admin, branch_a, WED), 201), ok(closure(client, admin, branch_a, THU), 201)
    assert client.delete(f"/api/v1/closures/{c1['id']}", headers=admin).status_code == 204
    assert get_shift(client, admin, s["id"])["status"] == "cancelled"
    at(clock, THU, 9)
    err(client.delete(f"/api/v1/closures/{c2['id']}", headers=admin), 409, "CLOSURE_IN_PAST")


def test_t_stf_14_b(client, librarian, branch_a):
    """T-STF-14-b (LIB-STF-14): 10-29 holiday, 10-28 and 10-30 open; 422"""
    out = get(client, librarian, f"branches/{branch_a['id']}/open-days", **{"from": "2026-10-28", "to": "2026-10-30"})
    assert [(d["open"], d["reason"]) for d in out["days"]] == [(True, None), (False, "holiday"), (True, None)]
    assert client.get(f"/api/v1/branches/{branch_a['id']}/open-days", headers=librarian, params={"from": NMON, "to": "2027-01-10"}).status_code == 422


def test_t_stf_16_a(client, clock, admin, librarian, branch_a, branch_b):
    """T-STF-16-a (LIB-STF-16): 409 BRANCH_CLOSED_TODAY; 200"""
    copy = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], copy["id"])
    ok(closure(client, admin, branch_a, WED), 201)
    at(clock, WED, 10)
    assert error_code(return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], expect=409)) == "BRANCH_CLOSED_TODAY"
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"])


def test_t_stf_18_b(client, admin, branch_a):
    """T-STF-18-b (LIB-STF-18): 422 three times; 403"""
    p, h = staff(client, admin, branch_a)
    for start, end in (("10:15", "14:00"), ("10:00", "11:30"), ("08:00", "18:30")):
        assert try_shift(client, admin, p["id"], branch_a, TUE, start, end).status_code == 422
    assert try_shift(client, h, p["id"], branch_a, TUE, "10:00", "14:00").status_code == 403


def test_t_stf_19_b(client, admin, branch_a):
    """T-STF-19-b (LIB-STF-19): 409 BRANCH_NOT_OPEN with details.reason weekend, holiday, closure"""
    p, _ = staff(client, admin, branch_a)
    ok(closure(client, admin, branch_a, WED), 201)
    for day, reason in ((SAT, "weekend"), ("2027-01-01", "holiday"), (WED, "closure")):
        assert err(try_shift(client, admin, p["id"], branch_a, day, "10:00", "14:00"), 409, "BRANCH_NOT_OPEN")["details"]["reason"] == reason


def test_t_stf_19_d(client, admin, branch_a):
    """T-STF-19-d (LIB-STF-19): 409 STAFF_ON_LEAVE with details.leave_id"""
    p, h = staff(client, admin, branch_a)
    lv = ok(leave(client, h, "annual", NMON, NFRI), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    assert err(try_shift(client, admin, p["id"], branch_a, NTUE, "10:00", "14:00"), 409, "STAFF_ON_LEAVE")["details"]["leave_id"] == lv["id"]


def test_t_stf_19_f(client, admin, branch_a):
    """T-STF-19-f (LIB-STF-19): STAFF_INACTIVE; SHIFT_IN_PAST (order of the checks)"""
    off, _ = staff(client, admin, branch_a)
    ok(client.patch(f"/api/v1/staff/{off['id']}", headers=admin, json={"is_active": False}))
    p, _ = staff(client, admin, branch_a)
    err(try_shift(client, admin, off["id"], branch_a, SAT, "10:00", "14:00"), 409, "STAFF_INACTIVE")
    err(try_shift(client, admin, p["id"], branch_a, "2026-10-31", "10:00", "14:00"), 409, "SHIFT_IN_PAST")


def test_t_stf_20_b(client, admin, branch_a):
    """T-STF-20-b (LIB-STF-20): 409 REST_PERIOD_TOO_SHORT (9 hours)"""
    ok(set_hours(client, admin, branch_a, "07:00", "22:00"))
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, NWED, "07:00", "15:00")
    err(try_shift(client, admin, p["id"], branch_a, NTUE, "14:00", "22:00"), 409, "REST_PERIOD_TOO_SHORT")


def test_t_stf_22_b(client, admin, branch_a):
    """T-STF-22-b (LIB-STF-22): 200 with staff_id P2"""
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    s = shift(client, admin, p1["id"], branch_a, TUE, "10:00", "14:00")
    assert ok(client.patch(f"/api/v1/shifts/{s['id']}", headers=admin, json={"staff_id": p2["id"]}))["staff_id"] == p2["id"]


def test_t_stf_24_a(client, admin, branch_a, branch_b):
    """T-STF-24-a (LIB-STF-24): Order S2, S1, S3; branch_id B → S2; from=to=Wed → S3; P1 sees S2, S1; P1 with staff_id P2 → 403"""
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


def test_t_stf_26_a(client, admin, branch_a):
    """T-STF-26-a (LIB-STF-26): created 2; skipped [Tue shift, BRANCH_NOT_OPEN]; new shifts on 11-09 and 11-11"""
    p, _ = staff(client, admin, branch_a)
    shift(client, admin, p["id"], branch_a, MON, "10:00", "14:00")
    tue = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    ok(closure(client, admin, branch_a, NTUE), 201)
    out = ok(post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": NMON}))
    assert out["created"] == 2 and out["skipped"] == [{"source_shift_id": tue["id"], "error_code": "BRANCH_NOT_OPEN"}]
    assert [x["date"] for x in items(get(client, admin, "shifts", **{"from": NMON, "to": "2026-11-15"}))] == [NMON, NWED]


def test_t_stf_25_b(client, admin, branch_a):
    """T-STF-25-b (LIB-STF-25): 422 both"""
    assert post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": MON, "to_week": NTUE}).status_code == 422
    assert post(client, admin, "shifts/copy-week", {"branch_id": branch_a["id"], "from_week": NMON, "to_week": MON}).status_code == 422


def test_t_stf_28_a(client, clock, admin, branch_a):
    """T-STF-28-a (LIB-STF-28): 403 both"""
    p, _ = staff(client, admin, branch_a)
    _, other = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    assert post(client, admin, f"shifts/{s['id']}/check-in").status_code == 403
    assert post(client, other, f"shifts/{s['id']}/check-in").status_code == 403


def test_t_stf_29_b(client, clock, admin, branch_a):
    """T-STF-29-b (LIB-STF-29): 409 SHIFT_OVER; 200"""
    p, h = staff(client, admin, branch_a)
    s1 = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    s2 = shift(client, admin, p["id"], branch_a, THU, "10:00", "14:00")
    at(clock, WED, 14)
    err(post(client, h, f"shifts/{s1['id']}/check-in"), 409, "SHIFT_OVER")
    at(clock, THU, 13, 59)
    ok(post(client, h, f"shifts/{s2['id']}/check-in"))


def test_t_stf_30_a(client, clock, admin, branch_a):
    """T-STF-30-a (LIB-STF-30): late_minutes 0, 6, 0; checked_in_at set"""
    p, h = staff(client, admin, branch_a)
    got = []
    for day, hh, mm in ((TUE, 9, 5), (WED, 9, 6), (THU, 8, 40)):
        s = shift(client, admin, p["id"], branch_a, day, "09:00", "13:00")
        at(clock, day, hh, mm)
        out = ok(post(client, h, f"shifts/{s['id']}/check-in"))
        assert same(out["checked_in_at"], day, hh, mm)
        got.append(out["late_minutes"])
    assert got == [0, 6, 0]


def test_t_stf_31_b(client, clock, admin, branch_a):
    """T-STF-31-b (LIB-STF-31): 409 NOT_CHECKED_IN; 409 SHIFT_NOT_CHANGEABLE"""
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    err(post(client, h, f"shifts/{s['id']}/check-out"), 409, "NOT_CHECKED_IN")
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    at(clock, TUE, 14)
    ok(post(client, h, f"shifts/{s['id']}/check-out"))
    err(post(client, h, f"shifts/{s['id']}/check-out"), 409, "SHIFT_NOT_CHANGEABLE")


def test_t_stf_32_a(client, clock, admin, branch_a):
    """T-STF-32-a (LIB-STF-32): auto_checked_out 0, then 1; S1 completed, checked_out_at 18:00, worked_minutes 480"""
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


def test_t_stf_34_b(client, admin, librarian, branch_a):
    """T-STF-34-b (LIB-STF-34): 422 four times; 409 NOT_STAFF"""
    _, h = staff(client, admin, branch_a)
    assert leave(client, h, "annual", NFRI, NMON).status_code == 422
    assert leave(client, h, "unpaid", NMON, "2026-12-09").status_code == 422
    assert leave(client, h, "annual", NMON, NTUE, "x" * 501).status_code == 422
    assert leave(client, h, "paid", NMON, NTUE).status_code == 422
    err(leave(client, librarian, "annual", NMON, NTUE), 409, "NOT_STAFF")


def test_t_stf_35_b(client, admin, branch_a):
    """T-STF-35-b (LIB-STF-35): 409 NO_WORKING_DAYS; 409 LEAVE_OVERLAP with details.leave_id"""
    _, h = staff(client, admin, branch_a)
    err(leave(client, h, "unpaid", SAT, "2026-11-08"), 409, "NO_WORKING_DAYS")
    first = ok(leave(client, h, "annual", NMON, NFRI), 201)
    assert err(leave(client, h, "unpaid", NTHU, "2026-11-16"), 409, "LEAVE_OVERLAP")["details"]["leave_id"] == first["id"]


def test_t_stf_36_a(client, clock, admin, branch_a):
    """T-STF-36-a (LIB-STF-36): days 7 (29 Oct holiday, 28 Oct arife counts, weekends not counted)"""
    _, h = staff(client, admin, branch_a)
    at(clock, "2026-10-20")
    assert ok(leave(client, h, "annual", "2026-10-23", TUE), 201)["days"] == 7


def test_t_stf_38_b(client, admin, branch_a):
    """T-STF-38-b (LIB-STF-38): 409 OWN_LEAVE; 403"""
    profile(client, admin, get(client, admin, "auth/me")["id"], branch_a)
    own = ok(leave(client, admin, "annual", NMON, NTUE), 201)
    err(post(client, admin, f"leave-requests/{own['id']}/approve", {}), 409, "OWN_LEAVE")
    _, h = staff(client, admin, branch_a)
    assert post(client, h, f"leave-requests/{own['id']}/approve", {}).status_code == 403


def test_t_stf_40_b(client, admin, branch_a):
    """T-STF-40-b (LIB-STF-40): entitled 7; 403"""
    p, _ = staff(client, admin, branch_a, started_on="2026-07-01")
    _, other = staff(client, admin, branch_a)
    assert get(client, admin, f"staff/{p['id']}/leave-balance", year=2026)["entitled"] == 7
    assert client.get(f"/api/v1/staff/{p['id']}/leave-balance", headers=other).status_code == 403


def test_t_stf_42_a(client, admin, branch_a):
    """T-STF-42-a (LIB-STF-42): First approved with decided_by null, the Wed shift cancelled with leave; second pending; used 0"""
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, WED, "10:00", "14:00")
    l1 = ok(leave(client, h, "sick", TUE, WED), 201)
    assert (l1["status"], l1["decided_by"]) == ("approved", None)
    assert get_shift(client, admin, s["id"])["cancel_reason"] == "leave"
    assert ok(leave(client, h, "sick", NMON, NWED), 201)["status"] == "pending"
    assert get(client, admin, f"staff/{p['id']}/leave-balance")["used"] == 0


def test_t_stf_43_b(client, admin, branch_a):
    """T-STF-43-b (LIB-STF-43): 422; 403"""
    _, h = staff(client, admin, branch_a)
    assert client.get("/api/v1/reports/staff-hours", headers=admin, params={"from": MON, "to": "2027-02-02"}).status_code == 422
    assert client.get("/api/v1/reports/staff-hours", headers=h, params={"from": MON, "to": TUE}).status_code == 403


def test_t_stf_44_b(client, admin, branch_a):
    """T-STF-44-b (LIB-STF-44): open false, slots empty"""
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], date=SAT)
    assert (out["open"], out["slots"]) == (False, [])


def test_t_stf_46_a(client, admin, branch_a):
    """T-STF-46-a (LIB-STF-46): missing_slots 2 (19:00 and 19:30)"""
    p1, _ = staff(client, admin, branch_a)
    p2, _ = staff(client, admin, branch_a)
    shift(client, admin, p1["id"], branch_a, NMON, "08:00", "14:00")
    shift(client, admin, p2["id"], branch_a, NMON, "13:00", "19:00")
    out = get(client, admin, "reports/branch-coverage", branch_id=branch_a["id"], **{"from": NMON, "to": NMON})
    assert out["days"] == [{"date": NMON, "missing_slots": 2}]


def test_t_stf_48_a(client, clock, admin, branch_a):
    """T-STF-48-a (LIB-STF-48): 409 SHIFT_IN_PROGRESS; the user stays active"""
    p, h = staff(client, admin, branch_a)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    at(clock, TUE, 10)
    ok(post(client, h, f"shifts/{s['id']}/check-in"))
    at(clock, TUE, 11)
    err(client.patch(f"/api/v1/users/{p['user_id']}", headers=admin, json={"is_active": False}), 409, "SHIFT_IN_PROGRESS")
    assert get(client, admin, f"users/{p['user_id']}")["is_active"] is True


def test_t_stf_50_a(client, admin, branch_a):
    """T-STF-50-a (LIB-STF-50): One entry each"""
    p, h = staff(client, admin, branch_a)
    ok(set_hours(client, admin, branch_a, "08:00", "19:00"))
    ok(closure(client, admin, branch_a, WED), 201)
    s = shift(client, admin, p["id"], branch_a, TUE, "10:00", "14:00")
    ok(post(client, admin, f"shifts/{s['id']}/cancel"))
    lv = ok(leave(client, h, "annual", NMON, NTUE), 201)
    ok(post(client, admin, f"leave-requests/{lv['id']}/approve", {}))
    for event in ("staff_created", "branch_hours_updated", "branch_closure_added", "shift_planned", "shift_cancelled", "leave_requested", "leave_approved"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
