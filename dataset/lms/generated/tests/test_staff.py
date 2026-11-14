"""Module 19: Staff and shifts (LIB-STF-01 to LIB-STF-51)."""

import datetime

import pytest

import lms
from lms.core.clock import local_now
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_branches import mk_branch
from tests.test_members import reg
from tests.test_rooms import book, mk_room

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def at(day, hhmm="09:00", month=11):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, month, day, hour, minute, tzinfo=TZ)


def mk_staff(client, admin_h, email="lib@example.com", role="librarian", branch=1, employment="full_time", **kw):
    u = make_user(client, admin_h, email=email, role=role)
    uid = u["id"] if isinstance(u, dict) and "id" in u else u
    body = {"user_id": uid, "home_branch_id": branch, "employment": employment, "started_on": "2025-01-01", **kw}
    r = client.post(f"{API}/staff", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def mk_shift(client, admin_h, staff_id=1, branch_id=1, date="2026-11-03", start="09:00", end="17:00", expect=201):
    body = {"staff_id": staff_id, "branch_id": branch_id, "date": date, "start_time": start, "end_time": end}
    r = client.post(f"{API}/shifts", headers=admin_h, json=body)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def world(client, admin_h):
    mk_branch(client, admin_h)
    s = mk_staff(client, admin_h)
    return {"staff": s, "lh": h(token_of(client, "lib@example.com", "Passw0rd1"))}


def test_create_staff_defaults(client, admin_h, app, world):
    s = world["staff"]
    assert s["weekly_hours"] == 40 and s["annual_leave_days"] == 14 and s["is_active"] is True
    assert s["email"] == "lib@example.com" and s["full_name"]
    assert [a.entity_id for a in audit(app, "staff_created")] == [1]
    mk_staff(client, admin_h, email="p@example.com", role="admin", employment="part_time", weekly_hours=20)
    r = client.get(f"{API}/staff/2", headers=admin_h)
    assert r.json()["annual_leave_days"] == 7


def test_create_staff_validation_and_checks(client, admin_h, world):
    u = make_user(client, admin_h, email="x@example.com")
    uid = u["id"] if isinstance(u, dict) else u
    base = {"user_id": uid, "home_branch_id": 1, "employment": "part_time", "started_on": "2025-01-01"}
    err(client.post(f"{API}/staff", headers=admin_h, json=base), 422, "VALIDATION_ERROR")  # no weekly_hours
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 31}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "employment": "full_time", "weekly_hours": 30}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 20, "annual_leave_days": 31}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 20, "started_on": "2026-11-03"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 20, "user_id": 999}), 404, "NOT_FOUND")
    dup = {**base, "weekly_hours": 20, "user_id": 2}
    e = err(client.post(f"{API}/staff", headers=admin_h, json=dup), 409, "CONFLICT")
    assert e["details"]["field"] == "user_id"
    mk_branch(client, admin_h, "B2")
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 20, "home_branch_id": 2}), 409, "BRANCH_INACTIVE")
    client.patch(f"{API}/users/{uid}", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/staff", headers=admin_h, json={**base, "weekly_hours": 20}), 409, "USER_INACTIVE")


def test_staff_permissions(client, admin_h, world):
    lh = world["lh"]
    assert client.get(f"{API}/staff/me", headers=lh).json()["id"] == 1
    assert client.get(f"{API}/staff/1", headers=lh).status_code == 200
    mk_staff(client, admin_h, email="o@example.com")
    err(client.get(f"{API}/staff/2", headers=lh), 403, "FORBIDDEN")
    err(client.get(f"{API}/staff", headers=lh), 403, "FORBIDDEN")
    err(client.get(f"{API}/staff/me", headers=admin_h), 409, "NOT_STAFF")


def test_branch_hours(client, admin_h, world):
    r = client.get(f"{API}/branches/1/hours", headers=world["lh"])
    assert r.json() == {"branch_id": 1, "opens_at": "08:00", "closes_at": "20:00", "min_staff": 1}
    err(client.get(f"{API}/branches/9/hours", headers=admin_h), 404, "NOT_FOUND")
    r = client.put(f"{API}/branches/1/hours", headers=admin_h, json={"opens_at": "07:00", "closes_at": "22:00", "min_staff": 2})
    assert r.status_code == 200 and r.json()["min_staff"] == 2
    for body in ({"opens_at": "09:00", "closes_at": "12:00", "min_staff": 1}, {"opens_at": "07:00", "closes_at": "22:00", "min_staff": 11}, {"opens_at": "07:15", "closes_at": "22:00", "min_staff": 1}):
        err(client.put(f"{API}/branches/1/hours", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    err(client.put(f"{API}/branches/1/hours", headers=world["lh"], json={"opens_at": "07:00", "closes_at": "22:00", "min_staff": 2}), 403, "FORBIDDEN")


def test_hours_vs_shifts(client, admin_h, world):
    s = mk_shift(client, admin_h, start="08:00", end="16:00")
    e = err(client.put(f"{API}/branches/1/hours", headers=admin_h, json={"opens_at": "09:00", "closes_at": "20:00", "min_staff": 1}), 409, "SHIFTS_OUTSIDE_HOURS")
    assert e["details"]["shift_ids"] == [s["id"]]
    assert client.get(f"{API}/branches/1/hours", headers=admin_h).json()["opens_at"] == "08:00"


def test_shift_checks(client, admin_h, world):
    client.put(f"{API}/branches/1/hours", headers=admin_h, json={"opens_at": "07:00", "closes_at": "22:00", "min_staff": 1})
    s = mk_shift(client, admin_h, date="2026-11-02", start="14:00", end="22:00")
    assert s["status"] == "planned" and s["hours"] == 8.0 and s["staff_name"]
    e = err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-03", "start_time": "08:00", "end_time": "12:00"}), 409, "REST_PERIOD_TOO_SHORT")
    mk_shift(client, admin_h, date="2026-11-03", start="09:00", end="13:00")
    e = err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-03", "start_time": "12:00", "end_time": "15:00"}), 409, "SHIFT_OVERLAP")
    err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-01", "start_time": "12:00", "end_time": "15:00"}), 409, "SHIFT_IN_PAST")
    e = err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-07", "start_time": "12:00", "end_time": "15:00"}), 409, "BRANCH_NOT_OPEN")
    assert e["details"]["reason"] == "weekend"
    e = err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-10-29", "start_time": "12:00", "end_time": "15:00"}), 409, "SHIFT_IN_PAST")
    err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-04", "start_time": "06:00", "end_time": "12:00"}), 409, "OUTSIDE_BRANCH_HOURS")
    for body in ({"start_time": "12:00", "end_time": "13:00"}, {"start_time": "08:00", "end_time": "19:00"}, {"start_time": "12:10", "end_time": "15:00"}, {"start_time": "15:00", "end_time": "12:00"}):
        err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-04", **body}), 422, "VALIDATION_ERROR")


def test_weekly_hours(client, admin_h):
    mk_branch(client, admin_h)
    mk_staff(client, admin_h, employment="part_time", weekly_hours=20)
    mon = mk_shift(client, admin_h, date="2026-11-09", start="09:00", end="13:00")
    mk_shift(client, admin_h, date="2026-11-10", start="09:00", end="17:00")
    mk_shift(client, admin_h, date="2026-11-11", start="09:00", end="17:00")
    e = err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-12", "start_time": "09:00", "end_time": "11:00"}), 409, "WEEKLY_HOURS_EXCEEDED")
    assert e["details"] == {"planned_hours": 20, "limit": 20}
    assert client.post(f"{API}/shifts/{mon['id']}/cancel", headers=admin_h).json()["cancel_reason"] == "staff_request"
    mk_shift(client, admin_h, date="2026-11-12", start="09:00", end="13:00")
    mk_shift(client, admin_h, date="2026-11-16", start="09:00", end="13:00")  # next week


def test_leave_balance_and_flow(client, admin_h, world, app):
    lh = world["lh"]
    r = client.post(f"{API}/leave-requests", headers=lh, json={"kind": "annual", "from_date": "2026-10-23", "to_date": "2026-11-03"})
    err(r, 409, "LEAVE_IN_PAST")
    r = client.post(f"{API}/leave-requests", headers=lh, json={"kind": "annual", "from_date": "2026-11-04", "to_date": "2026-11-13"})
    assert r.status_code == 201 and r.json()["days"] == 8 and r.json()["status"] == "pending"
    lid = r.json()["id"]
    e = err(client.post(f"{API}/leave-requests", headers=lh, json={"kind": "sick", "from_date": "2026-11-10", "to_date": "2026-11-10"}), 409, "LEAVE_OVERLAP")
    assert e["details"]["leave_id"] == lid
    bal = client.get(f"{API}/staff/1/leave-balance?year=2026", headers=lh).json()
    assert bal == {"staff_id": 1, "year": 2026, "entitled": 14, "used": 0, "pending": 8, "remaining": 6}
    e = err(client.post(f"{API}/leave-requests", headers=lh, json={"kind": "annual", "from_date": "2026-11-16", "to_date": "2026-11-24"}), 409, "LEAVE_BALANCE_EXCEEDED")
    assert e["details"]["remaining"] == 6
    shift = mk_shift(client, admin_h, date="2026-11-05")
    err(client.post(f"{API}/leave-requests/{lid}/approve", headers=lh, json={}), 403, "FORBIDDEN")
    r = client.post(f"{API}/leave-requests/{lid}/approve", headers=admin_h, json={"note": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["cancelled_shift_ids"] == [shift["id"]]
    err(client.post(f"{API}/leave-requests/{lid}/approve", headers=admin_h), 409, "LEAVE_NOT_PENDING")
    err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-06", "start_time": "09:00", "end_time": "12:00"}), 409, "STAFF_ON_LEAVE")
    err(client.post(f"{API}/leave-requests/{lid}/cancel", headers=lh), 409, "LEAVE_NOT_CANCELLABLE")
    assert client.post(f"{API}/leave-requests/{lid}/cancel", headers=admin_h).json()["status"] == "cancelled"


def test_sick_leave_auto_approved(client, admin_h, world):
    lh = world["lh"]
    r = client.post(f"{API}/leave-requests", headers=lh, json={"kind": "sick", "from_date": "2026-10-26", "to_date": "2026-10-27"})
    assert r.status_code == 201 and r.json()["status"] == "approved" and r.json()["decided_by"] is None
    err(client.post(f"{API}/leave-requests", headers=lh, json={"kind": "sick", "from_date": "2026-10-23", "to_date": "2026-10-23"}), 409, "LEAVE_IN_PAST")
    r = client.post(f"{API}/leave-requests", headers=lh, json={"kind": "sick", "from_date": "2026-11-03", "to_date": "2026-11-05"})
    assert r.json()["status"] == "pending"


def test_leave_working_days_example(client, admin_h, world, clock):
    clock.set(at(20, month=10))
    r = client.post(f"{API}/leave-requests", headers=world["lh"], json={"kind": "annual", "from_date": "2026-10-23", "to_date": "2026-11-03"})
    assert r.status_code == 201 and r.json()["days"] == 7


def test_entitlement_pro_rata(client, admin_h):
    mk_branch(client, admin_h)
    mk_staff(client, admin_h, started_on="2026-07-01")
    assert client.get(f"{API}/staff/1/leave-balance", headers=admin_h).json()["entitled"] == 7


def test_attendance(client, admin_h, world, clock):
    lh = world["lh"]
    s = mk_shift(client, admin_h, date="2026-11-03", start="09:00", end="17:00")
    sid = s["id"]
    clock.set(at(3, "08:29"))
    e = err(client.post(f"{API}/shifts/{sid}/check-in", headers=lh), 409, "CHECK_IN_TOO_EARLY")
    assert e["details"]["opens_at"] == "2026-11-03T08:30:00+03:00"
    err(client.post(f"{API}/shifts/{sid}/check-in", headers=admin_h), 403, "FORBIDDEN")
    err(client.post(f"{API}/shifts/{sid}/check-out", headers=lh), 409, "NOT_CHECKED_IN")
    clock.set(at(3, "09:06"))
    r = client.post(f"{API}/shifts/{sid}/check-in", headers=lh)
    assert r.status_code == 200 and r.json()["late_minutes"] == 6
    err(client.post(f"{API}/shifts/{sid}/check-in", headers=lh), 409, "SHIFT_NOT_CHANGEABLE")
    clock.set(at(3, "17:20"))
    r = client.post(f"{API}/shifts/{sid}/check-out", headers=lh)
    assert r.json()["status"] == "completed" and r.json()["worked_minutes"] == 474
    err(client.post(f"{API}/shifts/{sid}/check-out", headers=lh), 409, "SHIFT_NOT_CHANGEABLE")


def test_process_missed(client, admin_h, world, clock):
    s = mk_shift(client, admin_h, date="2026-11-03", start="09:00", end="17:00")
    clock.set(datetime.datetime(2026, 11, 3, 16, 59, tzinfo=TZ))
    assert client.post(f"{API}/staff/process", headers=admin_h).json() == {"missed": 0, "auto_checked_out": 0}
    clock.set(datetime.datetime(2026, 11, 3, 17, 0, 1, tzinfo=TZ))
    assert client.post(f"{API}/staff/process", headers=admin_h).json() == {"missed": 1, "auto_checked_out": 0}
    assert client.get(f"{API}/shifts", headers=admin_h).json()["items"][0]["status"] == "missed"


def test_closure_effects_and_open_days(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    mk_room(client, admin_h)
    m = reg(client, admin_h)
    book(client, admin_h, member_id=m["id"], date="2026-11-09")
    mk_shift(client, admin_h, date="2026-11-09")
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-09", "reason": "Sayım"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["cancelled_shifts"], body["cancelled_room_bookings"], body["cancelled_equipment_reservations"]) == (1, 1, 0)
    cid = body["id"]
    err(client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-09", "reason": "x"}), 409, "CONFLICT")
    err(client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-14", "reason": "x"}), 409, "NOT_A_WORKING_DAY")
    err(client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-02", "reason": "x"}), 422, "VALIDATION_ERROR")
    days = client.get(f"{API}/branches/1/open-days?from=2026-11-09&to=2026-11-15", headers=world["lh"]).json()["days"]
    assert [d["reason"] for d in days] == ["closure: Sayım", None, None, None, None, "weekend", "weekend"]
    assert days[1]["opens_at"] == "08:00" and days[0]["opens_at"] is None
    av = client.get(f"{API}/rooms/1/availability?date=2026-11-09", headers=admin_h).json()
    assert av["open"] is False
    assert book(client, admin_h, expect=409, member_id=m["id"], date="2026-11-09")["error"]["code"] == "ROOM_CLOSED"
    assert client.get(f"{API}/closures", headers=world["lh"]).json()["total"] == 1
    assert client.delete(f"{API}/closures/{cid}", headers=admin_h).status_code == 204
    assert client.delete(f"{API}/closures/{cid}", headers=admin_h).status_code == 404


def test_return_at_closed_branch(client, admin_h, clock):
    from tests import test_loans as tl

    mk_branch(client, admin_h, "AAA")
    mk_branch(client, admin_h, "BBB")
    tl.mk_author(client, admin_h)
    tl.mk_publisher(client, admin_h)
    lh = tl.lib_h(client, admin_h)
    book_id = tl.mk_book(client, lh, 0)
    member = tl.mk_member(client, lh)
    copy = tl.new_copy(client, lh, book_id, "COPY001")
    loan = tl.lend(client, lh, member, copy).json()
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-03", "reason": "Sayım"})
    assert r.status_code == 201
    clock.set(at(3))
    lh = h(token_of(client, "lib@example.com", "Passw0rd1"))
    err(tl.ret(client, lh, loan["id"], branch=1), 409, "BRANCH_CLOSED_TODAY")
    assert tl.ret(client, lh, loan["id"], branch=2).status_code == 200


def test_closure_cancels_equipment_reservation(client, admin_h, world):
    from tests.test_equipment import mk_item, mk_type, reserve

    client.put(f"{API}/branches/1/hours", headers=admin_h, json={"opens_at": "10:00", "closes_at": "16:00", "min_staff": 1})
    mk_type(client, admin_h)
    mk_item(client, admin_h)
    m = reg(client, admin_h)
    r = client.post(f"{API}/equipment-reservations", headers=admin_h, json={"type_id": 1, "branch_id": 1, "member_id": m["id"], "starts_at": "2026-11-04T09:00:00+03:00"})
    err(r, 409, "DESK_CLOSED")
    assert r.json()["error"]["details"]["opens_at"] == "2026-11-04T10:00:00+03:00"
    reserve(client, admin_h, "2026-11-04T10:00:00+03:00", member_id=m["id"])
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-04", "reason": "x"})
    assert r.json()["cancelled_equipment_reservations"] == 1


def test_deactivation_effects(client, admin_h, world, app):
    shift = mk_shift(client, admin_h, date="2026-11-05")
    lh = world["lh"]
    lid = client.post(f"{API}/leave-requests", headers=lh, json={"kind": "annual", "from_date": "2026-11-16", "to_date": "2026-11-17"}).json()["id"]
    r = client.patch(f"{API}/users/2", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/staff/1", headers=admin_h).json()["is_active"] is False
    s = client.get(f"{API}/shifts", headers=admin_h).json()["items"][0]
    assert s["status"] == "cancelled" and s["cancel_reason"] == "staff_deactivated"
    assert client.get(f"{API}/leave-requests", headers=admin_h).json()["items"][0]["status"] == "cancelled"
    err(client.post(f"{API}/shifts", headers=admin_h, json={"staff_id": 1, "branch_id": 1, "date": "2026-11-06", "start_time": "09:00", "end_time": "12:00"}), 409, "STAFF_INACTIVE")


def test_user_in_progress(client, admin_h, world, clock):
    mk_shift(client, admin_h, date="2026-11-02", start="09:00", end="17:00")
    assert client.post(f"{API}/shifts/1/check-in", headers=world["lh"]).status_code == 200
    err(client.patch(f"{API}/users/2", headers=admin_h, json={"is_active": False}), 409, "SHIFT_IN_PROGRESS")


def test_branch_in_use(client, admin_h, world):
    mk_branch(client, admin_h, "B2")
    err(client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"{API}/staff/1", headers=admin_h, json={"home_branch_id": 2})
    mk_shift(client, admin_h, date="2026-11-03")
    err(client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_copy_week(client, admin_h, world):
    mk_shift(client, admin_h, date="2026-11-02", start="09:00", end="13:00")
    mk_shift(client, admin_h, date="2026-11-03", start="09:00", end="13:00")
    mk_shift(client, admin_h, date="2026-11-04", start="09:00", end="13:00")
    client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-10", "reason": "x"})
    r = client.post(f"{API}/shifts/copy-week", headers=admin_h, json={"branch_id": 1, "from_week": "2026-11-02", "to_week": "2026-11-09"})
    assert r.status_code == 200 and r.json() == {"created": 2, "skipped": [{"source_shift_id": 2, "error_code": "BRANCH_NOT_OPEN"}]}
    err(client.post(f"{API}/shifts/copy-week", headers=admin_h, json={"branch_id": 1, "from_week": "2026-11-03", "to_week": "2026-11-09"}), 422, "VALIDATION_ERROR")


def test_coverage(client, admin_h, world):
    mk_staff(client, admin_h, email="o@example.com")
    mk_shift(client, admin_h, staff_id=1, date="2026-11-03", start="08:00", end="14:00")
    mk_shift(client, admin_h, staff_id=2, date="2026-11-03", start="13:00", end="19:00")
    r = client.get(f"{API}/reports/branch-coverage?branch_id=1&date=2026-11-03", headers=admin_h).json()
    assert r["open"] is True and len(r["slots"]) == 24
    assert [s["start"] for s in r["slots"] if not s["ok"]] == ["19:00", "19:30"]
    r = client.get(f"{API}/reports/branch-coverage?branch_id=1&from=2026-11-02&to=2026-11-08", headers=admin_h).json()
    assert [d["missing_slots"] for d in r["days"]] == [24, 2, 24, 24, 24]


def test_staff_hours_report(client, admin_h, world, clock):
    mk_shift(client, admin_h, date="2026-11-03", start="09:00", end="17:00")
    clock.set(datetime.datetime(2026, 11, 3, 9, 10, tzinfo=TZ))
    client.post(f"{API}/shifts/1/check-in", headers=h(token_of(client, "lib@example.com", "Passw0rd1")))
    r = client.get(f"{API}/reports/staff-hours?from=2026-11-01&to=2026-11-30", headers=admin_h).json()
    assert r["items"][0] == {"staff_id": 1, "full_name": r["items"][0]["full_name"], "planned_hours": 8.0, "worked_hours": 0.0, "missed_shifts": 0, "late_minutes": 10, "leave_days": 0}
    err(client.get(f"{API}/reports/staff-hours?from=2026-01-01&to=2026-12-31", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/staff-hours?from=2026-11-01&to=2026-11-30", headers=world["lh"]), 403, "FORBIDDEN")


def test_audit_events(client, admin_h, world, app):
    mk_shift(client, admin_h)
    client.put(f"{API}/branches/1/hours", headers=admin_h, json={"opens_at": "07:00", "closes_at": "22:00", "min_staff": 1})
    names = {a.event for a in audit(app)}
    assert {"staff_created", "shift_planned", "branch_hours_updated"} <= names
