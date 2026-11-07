"""Module 16: Equipment loans (LIB-EQ-01 to LIB-EQ-41)."""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.equipment.rules import desk_open, due_at_from, late_hours_between, next_desk_opening
from lms.fines.models import Fee
from lms.core.holidays import DEFAULT_HOLIDAYS
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import lib_h, mk_branch
from tests.test_members import guest_body, reg

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def dt(day, hhmm="10:00", month=11, sec=0):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, month, day, hour, minute, sec, tzinfo=TZ)


def iso(day, hhmm="10:00", month=11, sec=0):
    return dt(day, hhmm, month, sec).isoformat()


def mk_type(client, admin_h, code="CHARGER", **kw):
    body = {"code": code, "name": f"Type {code}", "period_unit": "hours", "period": 4, "hourly_late_fee": "2.00",
            "max_open_per_member": 2}
    body.update(kw)
    r = client.post(f"{API}/equipment-types", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def mk_item(client, admin_h, type_id=1, tag="CH-0001", **kw):
    body = {"type_id": type_id, "asset_tag": tag, "serial_no": f"SN-{tag}", "branch_id": 1, "value": "100.00",
            "acquired_on": "2026-10-01"}
    body.update(kw)
    r = client.post(f"{API}/equipment-items", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def lend(client, headers, member_id=1, expect=201, **kw):
    r = client.post(f"{API}/equipment-loans", headers=headers, json={"member_id": member_id, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def reserve(client, headers, starts_at, expect=201, type_id=1, **kw):
    body = {"type_id": type_id, "branch_id": 1, "starts_at": starts_at, **kw}
    r = client.post(f"{API}/equipment-reservations", headers=headers, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def ret(client, headers, loan_id=1, expect=200, **kw):
    r = client.post(f"{API}/equipment-loans/{loan_id}/return", headers=headers, json={"condition": "good", **kw})
    assert r.status_code == expect, r.text
    return r.json()


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


@pytest.fixture
def world(client, admin_h, clock):
    """Tuesday 2026-11-03 10:00; one branch, a librarian, a student member and one charger."""
    clock.set(dt(3))
    mk_branch(client, admin_h)
    lh = lib_h(client, admin_h)
    m1 = reg(client, admin_h)
    mk_type(client, admin_h)
    mk_item(client, admin_h)
    return {"lh": lh, "m1": m1, "mh": h(token_of(client, "ayse@example.edu.tr", "Passw0rd1"))}


# --- desk hours ------------------------------------------------------------------------------


def test_desk_hours_and_next_opening():
    hol = DEFAULT_HOLIDAYS
    assert desk_open(dt(3, "08:00"), hol) and desk_open(dt(3, "19:59", sec=59), hol)
    assert not desk_open(dt(3, "07:59"), hol) and not desk_open(dt(3, "20:00"), hol)
    assert not desk_open(dt(7, "10:00"), hol)  # Saturday
    assert next_desk_opening(dt(6, "20:30"), hol) == dt(9, "08:00")
    assert next_desk_opening(dt(3, "07:00"), hol) == dt(3, "08:00")
    assert next_desk_opening(datetime.datetime(2026, 10, 29, 10, tzinfo=TZ), hol) == datetime.datetime(2026, 10, 30, 8, tzinfo=TZ)


def test_due_time_rules():
    hol = DEFAULT_HOLIDAYS
    assert due_at_from(dt(3, "10:20"), "hours", 4, hol) == dt(3, "14:20")
    assert due_at_from(dt(3, "17:30"), "hours", 4, hol) == dt(3, "20:00")
    start = datetime.datetime(2026, 10, 28, 15, tzinfo=TZ)
    assert due_at_from(start, "working_days", 3, hol) == dt(3, "17:00")
    assert late_hours_between(dt(3, "14:20"), dt(3, "14:35")) == 0
    assert late_hours_between(dt(3, "14:20"), dt(3, "14:36")) == 1
    assert late_hours_between(dt(3, "14:20"), dt(3, "15:20")) == 1
    assert late_hours_between(dt(3, "14:20"), dt(3, "15:21")) == 2


# --- types and items -------------------------------------------------------------------------


def test_create_type(client, admin_h, world):
    r = client.post(
        f"{API}/equipment-types", headers=admin_h,
        json={"code": "lap_1", "name": " Laptop ", "period_unit": "working_days", "period": 3,
              "hourly_late_fee": "25.00", "requires_training": True, "max_open_per_member": 1},
    )
    assert r.status_code == 201
    assert r.json() == {"id": 2, "code": "LAP_1", "name": "Laptop", "period_unit": "working_days", "period": 3,
                        "hourly_late_fee": "25.00", "requires_training": True, "max_open_per_member": 1,
                        "is_active": True, "items_total": 0, "items_available": 0}
    e = err(client.post(f"{API}/equipment-types", headers=admin_h, json={"code": "LAP_1", "name": "x", "period_unit": "hours",
            "period": 1, "hourly_late_fee": "1.00", "max_open_per_member": 1}), 409, "CONFLICT")
    assert e["details"]["field"] == "code"
    for bad in ({"period": 9}, {"period": 0}, {"hourly_late_fee": "0.49"}, {"hourly_late_fee": "50.01"},
                {"max_open_per_member": 4}, {"code": "a"}, {"code": "a-b"}, {"hourly_late_fee": 2.0}):
        body = {"code": "NEW1", "name": "x", "period_unit": "hours", "period": 1, "hourly_late_fee": "1.00",
                "max_open_per_member": 1, **bad}
        err(client.post(f"{API}/equipment-types", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    body = {"code": "NEW1", "name": "x", "period_unit": "working_days", "period": 11, "hourly_late_fee": "1.00", "max_open_per_member": 1}
    err(client.post(f"{API}/equipment-types", headers=admin_h, json=body), 422, "VALIDATION_ERROR")


def test_type_permissions(client, admin_h, world):
    body = {"code": "NEW1", "name": "x", "period_unit": "hours", "period": 1, "hourly_late_fee": "1.00", "max_open_per_member": 1}
    err(client.post(f"{API}/equipment-types", json=body), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/equipment-types", headers=world["lh"], json=body), 403, "FORBIDDEN")
    err(client.post(f"{API}/equipment-types", headers=world["mh"], json=body), 403, "FORBIDDEN")
    assert client.get(f"{API}/equipment-types", headers=world["mh"]).status_code == 200
    assert client.get(f"{API}/equipment-types/1", headers=world["mh"]).status_code == 200
    err(client.get(f"{API}/equipment-types/99", headers=world["mh"]), 404, "NOT_FOUND")
    err(client.get(f"{API}/equipment-items", headers=world["mh"]), 403, "FORBIDDEN")
    err(client.patch(f"{API}/equipment-items/1", headers=world["lh"], json={"value": "5.00"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/equipment-items/1/retire", headers=world["lh"]), 403, "FORBIDDEN")


def test_patch_type(client, admin_h, world, app):
    err(client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"code": "X1"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"period_unit": "hours"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"period": 9}), 422, "VALIDATION_ERROR")
    r = client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"period": 8, "hourly_late_fee": "3.50"})
    assert r.status_code == 200 and r.json()["period"] == 8 and r.json()["items_total"] == 1
    assert [a.entity_id for a in audit(app, "equipment_type_updated")] == [1]
    err(client.patch(f"{API}/equipment-types/99", headers=admin_h, json={"period": 2}), 404, "NOT_FOUND")


def test_type_list_counts(client, admin_h, world):
    mk_item(client, admin_h, tag="CH-0002")
    lend(client, world["lh"], item_id=1)
    t = client.get(f"{API}/equipment-types", headers=admin_h).json()
    assert t["items"][0]["items_total"] == 2 and t["items"][0]["items_available"] == 1
    mk_type(client, admin_h, code="AAA")
    assert [i["code"] for i in client.get(f"{API}/equipment-types", headers=admin_h).json()["items"]] == ["AAA", "CHARGER"]
    assert client.get(f"{API}/equipment-types?is_active=false", headers=admin_h).json()["total"] == 0


def test_create_item(client, admin_h, world):
    r = client.post(f"{API}/equipment-items", headers=admin_h,
                    json={"type_id": 1, "asset_tag": "ab-12", "serial_no": " S1 ", "branch_id": 1, "value": "1.00",
                          "acquired_on": "2026-11-03"})
    assert r.status_code == 201
    j = r.json()
    assert j["asset_tag"] == "AB-12" and j["serial_no"] == "S1" and j["status"] == "available" and j["id"] == 2
    err(client.post(f"{API}/equipment-items", headers=admin_h,
                    json={"type_id": 1, "asset_tag": "AB-12", "serial_no": "S", "branch_id": 1, "value": "5.00",
                          "acquired_on": "2026-11-03"}), 409, "CONFLICT")
    for bad in ({"acquired_on": "2026-11-04"}, {"value": "0.99"}, {"value": "100000.01"}, {"asset_tag": "AB1"},
                {"asset_tag": "AB_12"}, {"serial_no": ""}):
        body = {"type_id": 1, "asset_tag": "ZZ-99", "serial_no": "S", "branch_id": 1, "value": "5.00", "acquired_on": "2026-11-03", **bad}
        err(client.post(f"{API}/equipment-items", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    body = {"type_id": 7, "asset_tag": "ZZ-99", "serial_no": "S", "branch_id": 1, "value": "5.00", "acquired_on": "2026-11-03"}
    e = err(client.post(f"{API}/equipment-items", headers=admin_h, json=body), 404, "NOT_FOUND")
    assert e["details"] == {"field": "type_id", "id": 7}
    mk_branch(client, admin_h, code="B2")
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200
    body.update(type_id=1, branch_id=2)
    err(client.post(f"{API}/equipment-items", headers=admin_h, json=body), 409, "BRANCH_INACTIVE")


def test_item_list_and_get(client, admin_h, world):
    mk_item(client, admin_h, tag="AA-0001", serial_no="Işık-9")
    r = client.get(f"{API}/equipment-items", headers=world["lh"]).json()
    assert [i["asset_tag"] for i in r["items"]] == ["AA-0001", "CH-0001"]
    assert client.get(f"{API}/equipment-items?q=ışık", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/equipment-items?q=ch-00", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/equipment-items?status=lost", headers=world["lh"]).json()["total"] == 0
    assert client.get(f"{API}/equipment-items/1", headers=world["lh"]).json()["asset_tag"] == "CH-0001"


def test_item_patch_retire_repair(client, admin_h, world, app):
    r = client.patch(f"{API}/equipment-items/1", headers=admin_h, json={"serial_no": "NEW", "value": "250.00"})
    assert r.status_code == 200 and r.json()["serial_no"] == "NEW" and r.json()["value"] == "250.00"
    for bad in ({"status": "lost"}, {"type_id": 1}, {"asset_tag": "XXXX"}):
        err(client.patch(f"{API}/equipment-items/1", headers=admin_h, json=bad), 422, "VALIDATION_ERROR")
    mk_branch(client, admin_h, code="B2")
    assert client.patch(f"{API}/equipment-items/1", headers=admin_h, json={"branch_id": 2}).json()["branch_id"] == 2
    err(client.post(f"{API}/equipment-items/1/repair-done", headers=world["lh"]), 409, "INVALID_ITEM_STATUS")
    assert client.post(f"{API}/equipment-items/1/retire", headers=admin_h).json()["status"] == "retired"
    err(client.post(f"{API}/equipment-items/1/retire", headers=admin_h), 409, "INVALID_ITEM_STATUS")
    assert [a.entity_id for a in audit(app, "equipment_item_retired")] == [1]


def test_item_branch_change_needs_available(client, admin_h, world):
    mk_branch(client, admin_h, code="B2")
    lend(client, world["lh"], item_id=1)
    err(client.patch(f"{API}/equipment-items/1", headers=admin_h, json={"branch_id": 2}), 409, "INVALID_ITEM_STATUS")


def test_item_needed_for_reservation(client, admin_h, world):
    mk_branch(client, admin_h, code="B2")
    reserve(client, world["mh"], iso(3, "12:00"))
    err(client.patch(f"{API}/equipment-items/1", headers=admin_h, json={"branch_id": 2}), 409, "ITEM_NEEDED_FOR_RESERVATION")
    err(client.post(f"{API}/equipment-items/1/retire", headers=admin_h), 409, "ITEM_NEEDED_FOR_RESERVATION")


# --- training --------------------------------------------------------------------------------


def test_training(client, admin_h, world, app):
    mk_type(client, admin_h, code="LAPTOP", requires_training=True)
    r = client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2026-11-02"})
    assert r.status_code == 201
    j = r.json()
    assert j["valid_until"] == "2027-11-01" and j["recorded_by"] == 2 and j["member_id"] == 1 and j["type_id"] == 2
    err(client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2026-11-04"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 1, "completed_on": "2026-11-02"}), 409, "TRAINING_NOT_REQUIRED")
    err(client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 9, "completed_on": "2026-11-02"}), 404, "NOT_FOUND")
    err(client.post(f"{API}/members/9/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2026-11-02"}), 404, "NOT_FOUND")
    err(client.post(f"{API}/members/1/equipment-trainings", headers=world["mh"], json={"type_id": 2, "completed_on": "2026-11-02"}), 403, "FORBIDDEN")
    assert client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2026-11-01"}).status_code == 201
    assert client.get(f"{API}/members/1/equipment-trainings", headers=world["mh"]).json()["total"] == 2
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    err(client.get(f"{API}/members/2/equipment-trainings", headers=world["mh"]), 403, "FORBIDDEN")


def test_training_required_for_students(client, admin_h, world, clock):
    mk_type(client, admin_h, code="LAPTOP", requires_training=True)
    mk_item(client, admin_h, type_id=2, tag="LP-0001")
    reg(client, admin_h, email="ac@example.com", university_id="20230002", membership_type="academic")
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 2}), 409, "TRAINING_REQUIRED")
    lend(client, world["lh"], member_id=2, item_id=2)  # academics need no training
    client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2025-11-03"})
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 2}), 409, "TRAINING_REQUIRED")  # valid until 2026-11-02: expired
    client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2025-11-04"})
    # valid until 2026-11-03 inclusive: the training is accepted, the item is taken
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 2}), 409, "ITEM_NOT_AVAILABLE")


# --- lending ---------------------------------------------------------------------------------


def test_lend_and_due(client, admin_h, world, app, clock):
    clock.set(dt(3, "10:20", sec=7))
    loan = lend(client, world["lh"], item_id=1)
    assert loan["due_at"] == dt(3, "14:20", sec=7).isoformat()
    assert loan["status"] == "open" and loan["lent_by"] == 2 and loan["received_by"] is None
    assert loan["asset_tag"] == "CH-0001" and loan["type_code"] == "CHARGER" and loan["type_id"] == 1
    assert loan["overdue"] is False and loan["accrued_late_fee"] == "0.00" and loan["extended"] is False
    assert loan["reservation_id"] is None and loan["branch_id"] == 1 and "hourly_late_fee" not in loan
    assert client.get(f"{API}/equipment-items/1", headers=admin_h).json()["status"] == "on_loan"
    assert [a.entity_id for a in audit(app, "equipment_loan_created")] == [1]
    n = sel(app, sa.select(Notification).where(Notification.type == "equipment_loan_created"))
    assert len(n) == 1 and "CH-0001" in n[0].message and "Type CHARGER" in n[0].message and n[0].equipment_loan_id == 1


def test_lend_late_in_day_caps_due(client, admin_h, world, clock):
    clock.set(dt(3, "17:30"))
    assert lend(client, world["lh"], item_id=1)["due_at"] == iso(3, "20:00")


def test_lend_working_days_type(client, admin_h, world, clock):
    mk_type(client, admin_h, code="LAPTOP", period_unit="working_days", period=3)
    mk_item(client, admin_h, type_id=2, tag="LP-0001")
    clock.set(datetime.datetime(2026, 10, 28, 15, tzinfo=TZ))
    assert lend(client, world["lh"], item_id=2)["due_at"] == iso(3, "17:00")


def test_lend_validation_and_permissions(client, admin_h, world):
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1, "reservation_id": 1}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/equipment-loans", headers=world["mh"], json={"member_id": 1, "item_id": 1}), 403, "FORBIDDEN")
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 9, "item_id": 1}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "member_id", "id": 9}
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 9}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "item_id", "id": 9}
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 9}), 404, "NOT_FOUND")
    assert e["details"] == {"field": "reservation_id", "id": 9}


def test_lend_desk_closed(client, admin_h, world, clock):
    clock.set(dt(6, "20:30"))
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1}), 409, "DESK_CLOSED")
    assert e["details"]["opens_at"] == iso(9, "08:00")
    clock.set(dt(7, "10:00"))
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1}), 409, "DESK_CLOSED")
    assert e["details"]["opens_at"] == iso(9, "08:00")
    clock.set(dt(3, "07:00"))
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1}), 409, "DESK_CLOSED")
    assert e["details"]["opens_at"] == iso(3, "08:00")


def test_lend_check_order(client, admin_h, world, app, clock):
    def attempt(headers=None):
        return client.post(f"{API}/equipment-loans", headers=headers or world["lh"], json={"member_id": 1, "item_id": 1})

    # type inactive
    client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"is_active": False})
    err(attempt(), 409, "TYPE_INACTIVE")
    client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"is_active": True})
    # passive
    client.post(f"{API}/members/1/deactivate", headers=world["lh"])
    err(attempt(), 409, "MEMBER_PASSIVE")
    client.post(f"{API}/members/1/activate", headers=world["lh"])
    # expired membership
    clock.set(dt(3) + datetime.timedelta(days=366))
    err(attempt(relogin(client)), 409, "MEMBERSHIP_EXPIRED")


def relogin(client):
    return h(token_of(client, "lib@example.com", "Passw0rd1"))


def test_branch_inactive_beats_other_checks(client, admin_h, world):
    mk_branch(client, admin_h, code="B2")
    assert client.patch(f"{API}/equipment-items/1", headers=admin_h, json={"branch_id": 2}).status_code == 200
    mk_item(client, admin_h, tag="CH-0002", branch_id=2)
    client.post(f"{API}/equipment-items/1/retire", headers=admin_h)
    client.post(f"{API}/equipment-items/2/retire", headers=admin_h)
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200
    client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 2}), 409, "BRANCH_INACTIVE")


def test_guest_cannot_borrow(client, admin_h, world):
    r = client.post(f"{API}/members", headers=admin_h, json=guest_body())
    assert r.status_code == 201
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 2, "item_id": 1}), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")


def test_limits(client, admin_h, world):
    mk_item(client, admin_h, tag="CH-0002")
    mk_item(client, admin_h, tag="CH-0003")
    mk_type(client, admin_h, code="TABLET", max_open_per_member=3)
    mk_item(client, admin_h, type_id=2, tag="TB-0001")
    lend(client, world["lh"], item_id=1)
    lend(client, world["lh"], item_id=2)
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 3}), 409, "EQUIPMENT_LIMIT_REACHED")
    assert e["details"]["limit"] == 2
    # type limit: academic has 3 in total, charger allows 2
    reg(client, admin_h, email="ac@example.com", university_id="20230002", membership_type="academic")
    lend(client, world["lh"], member_id=2, item_id=3)
    mk_item(client, admin_h, tag="CH-0004")
    mk_item(client, admin_h, tag="CH-0005")
    lend(client, world["lh"], member_id=2, item_id=5)
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 2, "item_id": 6}), 409, "TYPE_LIMIT_REACHED")
    assert e["details"]["limit"] == 2
    lend(client, world["lh"], member_id=2, item_id=4)


def test_item_not_available(client, admin_h, world):
    lend(client, world["lh"], item_id=1)
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 2, "item_id": 1}), 409, "ITEM_NOT_AVAILABLE")


def test_capacity_boundary_with_reservation(client, admin_h, world, clock):
    """One charger (4 hours); another member's reservation for 14:30 holds it from 14:15."""
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    reserve(client, mb, iso(3, "14:30"))
    clock.set(dt(3, "10:00"))
    loan = lend(client, world["lh"], item_id=1)
    assert loan["due_at"] == iso(3, "14:00")
    ret(client, world["lh"], loan_id=1)
    clock.set(dt(3, "10:01"))
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1}), 409, "ITEM_NEEDED_FOR_RESERVATION")


def test_debt_blocks_and_overdue_blocks(client, admin_h, world, clock):
    loan = lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "14:36"))
    mk_item(client, admin_h, tag="CH-0002")
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 2}), 409, "MEMBER_HAS_OVERDUE")
    # boundary: exactly 15 minutes after the due time is not overdue
    clock.set(dt(3, "14:15"))
    assert client.get(f"{API}/equipment-loans/1", headers=world["lh"]).json()["overdue"] is False
    clock.set(dt(3, "14:15", sec=1))
    j = client.get(f"{API}/equipment-loans/1", headers=world["lh"]).json()
    assert loan["due_at"] == iso(3, "14:00") and j["overdue"] is True and j["accrued_late_fee"] == "2.00"


def test_overdue_equipment_blocks_book_loans_and_counts_as_debt(client, admin_h, world, clock):
    mk_type(client, admin_h, code="LAPTOP", hourly_late_fee="25.00")
    mk_item(client, admin_h, type_id=2, tag="LP-0001", value="30000.00")
    lend(client, world["lh"], item_id=2)
    clock.set(dt(3, "14:20") + datetime.timedelta(hours=1))
    bal = client.get(f"{API}/members/1/balance", headers=world["mh"]).json()
    assert bal["accrued_late_fees"] == "50.00" and bal["total_debt"] == "50.00" and bal["blocked"] is True
    summary = client.get(f"{API}/members/1/summary", headers=world["mh"]).json()
    assert summary["borrowing"]["reasons"] == ["MEMBER_HAS_OVERDUE", "MEMBER_BLOCKED_BY_DEBT"]
    assert summary["equipment"] == {"open_loans": 1, "overdue_loans": 1, "booked_reservations": 0}
    assert summary["overdue_loans"] == 0 and summary["open_loans"] == 0


def test_book_overdue_blocks_equipment(client, admin_h, world, clock):
    b = client.post(f"{API}/authors", headers=admin_h, json={"name": "A"}).json()
    p = client.post(f"{API}/publishers", headers=admin_h, json={"name": "P"}).json()
    book = client.post(f"{API}/books", headers=admin_h, json={"isbn": "9780306406157", "title": "T", "author_ids": [b["id"]],
        "publisher_id": p["id"], "publication_year": 2000, "language": "en", "classification": "005"}).json()
    client.post(f"{API}/books/{book['id']}/copies", headers=admin_h, json={"barcode": "BC-000001", "home_branch_id": 1, "price": "10.00", "acquired_on": "2026-01-01"})
    assert client.post(f"{API}/loans", headers=world["lh"], json={"member_id": 1, "copy_id": 1}).status_code == 201
    clock.set(dt(3) + datetime.timedelta(days=15))  # the book was due on 2026-11-16
    err(client.post(f"{API}/equipment-loans", headers=relogin(client), json={"member_id": 1, "item_id": 1}), 409, "MEMBER_HAS_OVERDUE")


def test_debt_blocks_lending_with_details(client, admin_h, world, clock):
    mk_type(client, admin_h, code="LAPTOP", hourly_late_fee="25.00")
    mk_item(client, admin_h, type_id=2, tag="LP-0001", value="30000.00")
    lend(client, world["lh"], item_id=2)
    clock.set(dt(3, "14:20") + datetime.timedelta(hours=1))
    ret(client, world["lh"], loan_id=1)
    e = err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "item_id": 1}), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"


# --- extension -------------------------------------------------------------------------------


def test_extend(client, admin_h, world, clock, app):
    clock.set(dt(3, "10:20"))
    lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "13:00"))
    r = client.post(f"{API}/equipment-loans/1/extend", headers=world["mh"])
    assert r.status_code == 200 and r.json()["due_at"] == iso(3, "18:20") and r.json()["extended"] is True
    err(client.post(f"{API}/equipment-loans/1/extend", headers=world["mh"]), 409, "EXTENSION_LIMIT_REACHED")
    assert [a.entity_id for a in audit(app, "equipment_loan_extended")] == [1]
    err(client.post(f"{API}/equipment-loans/9/extend", headers=world["mh"]), 404, "NOT_FOUND")


def test_extend_caps_and_not_possible(client, admin_h, world, clock):
    clock.set(dt(3, "13:30"))
    lend(client, world["lh"], item_id=1)  # due 17:30
    r = client.post(f"{API}/equipment-loans/1/extend", headers=world["lh"])
    assert r.json()["due_at"] == iso(3, "20:00")
    ret(client, world["lh"], loan_id=1)
    clock.set(dt(3, "16:30"))
    lend(client, world["lh"], item_id=1)  # due 20:00 (capped)
    err(client.post(f"{API}/equipment-loans/2/extend", headers=world["lh"]), 409, "EXTENSION_NOT_POSSIBLE")


def test_extend_errors(client, admin_h, world, clock):
    lend(client, world["lh"], item_id=1)
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    err(client.post(f"{API}/equipment-loans/1/extend", headers=mb), 403, "FORBIDDEN")
    clock.set(dt(3, "14:16"))
    err(client.post(f"{API}/equipment-loans/1/extend", headers=world["mh"]), 409, "LOAN_OVERDUE")
    ret(client, world["lh"], loan_id=1)
    err(client.post(f"{API}/equipment-loans/1/extend", headers=world["mh"]), 409, "LOAN_NOT_OPEN")


def test_extend_needs_capacity(client, admin_h, world, clock):
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    lend(client, world["lh"], item_id=1)  # due 14:00, needed until 14:15
    reserve(client, mb, iso(3, "15:00"))  # holds from 14:45
    r = client.post(f"{API}/equipment-loans/1/extend", headers=world["lh"])
    assert r.status_code == 409, r.text  # 18:00 + 15 min overlaps the hold
    assert r.json()["error"]["code"] == "ITEM_NEEDED_FOR_RESERVATION"


# --- return, loss, fees ----------------------------------------------------------------------


def test_return_good_on_time(client, admin_h, world, app):
    lend(client, world["lh"], item_id=1)
    j = ret(client, world["lh"])
    assert j["status"] == "returned" and j["returned_at"] == iso(3) and j["received_by"] == 2
    assert j["return_condition"] == "good" and j["late_hours"] == 0
    assert client.get(f"{API}/equipment-items/1", headers=admin_h).json()["status"] == "available"
    assert sel(app, sa.select(Fee)) == []
    err(client.post(f"{API}/equipment-loans/1/return", headers=world["lh"], json={"condition": "good"}), 409, "LOAN_NOT_OPEN")
    assert [a.entity_id for a in audit(app, "equipment_loan_returned")] == [1]
    assert len(sel(app, sa.select(Notification).where(Notification.type == "equipment_loan_returned"))) == 1


def test_return_validation(client, admin_h, world):
    lend(client, world["lh"], item_id=1)
    url = f"{API}/equipment-loans/1/return"
    err(client.post(url, headers=world["lh"], json={"condition": "damaged"}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=world["lh"], json={"condition": "good", "damage_fee": "1.00"}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=world["lh"], json={"condition": "damaged", "damage_fee": "-1.00"}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=world["lh"], json={"condition": "bad"}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=world["lh"], json={"condition": "damaged", "damage_fee": "100.01"}), 409, "DAMAGE_FEE_EXCEEDS_VALUE")
    err(client.post(url, headers=world["mh"], json={"condition": "good"}), 403, "FORBIDDEN")


def test_return_damaged(client, admin_h, world, app):
    lend(client, world["lh"], item_id=1)
    j = client.post(f"{API}/equipment-loans/1/return", headers=world["lh"], json={"condition": "damaged", "damage_fee": "40.00"}).json()
    assert j["return_condition"] == "damaged"
    assert client.get(f"{API}/equipment-items/1", headers=admin_h).json()["status"] == "in_repair"
    fee = sel(app, sa.select(Fee))
    assert [(f.kind, str(f.amount), f.loan_id, f.equipment_loan_id) for f in fee] == [("equipment_damage_fee", "40.00", None, 1)]
    fees = client.get(f"{API}/members/1/fees", headers=world["mh"]).json()["items"]
    assert fees[0]["equipment_loan_id"] == 1 and fees[0]["loan_id"] is None and fees[0]["kind"] == "equipment_damage_fee"
    assert client.get(f"{API}/members/1/balance", headers=world["mh"]).json()["outstanding_fees"] == "40.00"
    assert len(sel(app, sa.select(Notification).where(Notification.type == "fee_created"))) == 1
    assert client.post(f"{API}/equipment-items/1/repair-done", headers=world["lh"]).json()["status"] == "available"


def test_return_damaged_zero_fee_creates_no_fee(client, admin_h, world, app):
    lend(client, world["lh"], item_id=1)
    r = client.post(f"{API}/equipment-loans/1/return", headers=world["lh"], json={"condition": "damaged", "damage_fee": "0.00"})
    assert r.status_code == 200
    assert sel(app, sa.select(Fee)) == []


def test_late_return_fee(client, admin_h, world, clock, app):
    mk_type(client, admin_h, code="LAPTOP", hourly_late_fee="25.00")
    mk_item(client, admin_h, type_id=2, tag="LP-0001", value="30000.00")
    lend(client, world["lh"], item_id=2)
    clock.set(dt(3, "14:20") + datetime.timedelta(hours=29, minutes=30))  # 30 started hours late
    j = ret(client, world["lh"])
    assert j["late_hours"] == 30
    assert [str(f.amount) for f in sel(app, sa.select(Fee))] == ["750.00"]
    assert sel(app, sa.select(Fee))[0].kind == "equipment_late_fee"


def test_late_fee_cap(client, admin_h, world, clock, app):
    mk_type(client, admin_h, code="LAPTOP", hourly_late_fee="25.00")
    mk_item(client, admin_h, type_id=2, tag="LP-0001", value="30000.00")
    lend(client, world["lh"], item_id=2)
    clock.set(dt(3, "14:20") + datetime.timedelta(hours=299, minutes=30))
    lh = relogin(client)
    assert client.get(f"{API}/equipment-loans/1", headers=lh).json()["accrued_late_fee"] == "6000.00"
    ret(client, lh)
    assert [str(f.amount) for f in sel(app, sa.select(Fee))] == ["6000.00"]


def test_late_fee_uses_loan_rate(client, admin_h, world, clock, app):
    lend(client, world["lh"], item_id=1)
    client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"hourly_late_fee": "10.00"})
    clock.set(dt(3, "16:00"))  # due 14:00 -> 2 hours late
    ret(client, world["lh"])
    assert [str(f.amount) for f in sel(app, sa.select(Fee))] == ["4.00"]


def test_late_fee_rounding_and_value_cap(client, admin_h, world, clock, app):
    mk_item(client, admin_h, tag="CH-0002", value="1.00")
    lend(client, world["lh"], item_id=2)
    clock.set(dt(3, "16:00"))
    ret(client, world["lh"])
    assert [str(f.amount) for f in sel(app, sa.select(Fee))] == ["0.20"]


def test_report_lost(client, admin_h, world, clock, app):
    lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "16:00"))
    j = client.post(f"{API}/equipment-loans/1/report-lost", headers=world["lh"]).json()
    assert j["status"] == "lost" and j["returned_at"] is None and j["late_hours"] == 2
    fees = sel(app, sa.select(Fee))
    assert [(f.kind, str(f.amount)) for f in fees] == [("equipment_late_fee", "4.00"), ("equipment_lost", "100.00")]
    assert client.get(f"{API}/equipment-items/1", headers=admin_h).json()["status"] == "lost"
    err(client.post(f"{API}/equipment-loans/1/report-lost", headers=world["lh"]), 409, "LOAN_NOT_OPEN")
    assert client.get(f"{API}/members/1/balance", headers=world["mh"]).json()["outstanding_fees"] == "104.00"
    assert [a.entity_id for a in audit(app, "equipment_loan_lost")] == [1]
    assert len(sel(app, sa.select(Notification).where(Notification.type == "equipment_loan_lost"))) == 1
    err(client.post(f"{API}/equipment-loans/1/report-lost", headers=world["mh"]), 403, "FORBIDDEN")


def test_return_when_desk_closed(client, admin_h, world, clock):
    clock.set(dt(3, "17:00"))
    lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "23:00"))
    ret(client, world["lh"])


def test_pay_equipment_fee(client, admin_h, world, clock):
    lend(client, world["lh"], item_id=1)
    client.post(f"{API}/equipment-loans/1/return", headers=world["lh"], json={"condition": "damaged", "damage_fee": "40.00"})
    r = client.post(f"{API}/members/1/payments", headers=world["lh"], json={"amount": "40.00", "method": "cash"})
    assert r.status_code == 201 and r.json()["allocations"] == [{"fee_id": 1, "amount": "40.00"}]


# --- lists and reads -------------------------------------------------------------------------


def test_loan_reads_and_lists(client, admin_h, world, clock):
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    mk_item(client, admin_h, tag="CH-0002")
    lend(client, world["lh"], item_id=1)
    clock.advance(minutes=5)
    lend(client, world["lh"], member_id=2, item_id=2)
    assert client.get(f"{API}/equipment-loans/1", headers=world["mh"]).status_code == 200
    err(client.get(f"{API}/equipment-loans/2", headers=world["mh"]), 403, "FORBIDDEN")
    err(client.get(f"{API}/equipment-loans", headers=world["mh"]), 403, "FORBIDDEN")
    err(client.get(f"{API}/equipment-loans/99", headers=world["lh"]), 404, "NOT_FOUND")
    r = client.get(f"{API}/equipment-loans", headers=world["lh"]).json()
    assert [i["id"] for i in r["items"]] == [1, 2] and r["total"] == 2
    assert client.get(f"{API}/equipment-loans?member_id=2", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/equipment-loans?overdue=true", headers=world["lh"]).json()["total"] == 0
    assert client.get(f"{API}/equipment-loans?overdue=false", headers=world["lh"]).json()["total"] == 2
    assert client.get(f"{API}/equipment-loans?type_id=1&branch_id=1&status=open", headers=world["lh"]).json()["total"] == 2
    assert client.get(f"{API}/members/1/equipment-loans", headers=world["mh"]).json()["total"] == 1
    err(client.get(f"{API}/members/2/equipment-loans", headers=world["mh"]), 403, "FORBIDDEN")
    clock.advance(hours=5)
    assert client.get(f"{API}/equipment-loans?overdue=true", headers=world["lh"]).json()["total"] == 2
    assert client.get(f"{API}/equipment-loans?overdue=false", headers=world["lh"]).json()["total"] == 0


# --- reservations ----------------------------------------------------------------------------


def test_reserve(client, admin_h, world, app):
    r = reserve(client, world["mh"], iso(4, "10:00"))
    assert r["status"] == "booked" and r["ends_at"] == iso(4, "14:00") and r["member_id"] == 1
    assert r["loan_id"] is None and r["closed_at"] is None and r["cancel_reason"] is None
    assert [a.entity_id for a in audit(app, "equipment_reservation_created")] == [1]
    j = reserve(client, world["lh"], iso(5, "10:00"), member_id=1)
    assert j["member_id"] == 1
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 1, "member_id": 1, "starts_at": iso(5, "10:00")}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/equipment-reservations", headers=world["lh"], json={"type_id": 1, "branch_id": 1, "starts_at": iso(5, "10:00")}), 422, "VALIDATION_ERROR")


def test_reserve_validation(client, admin_h, world):
    for bad in (iso(4, "10:15"), iso(4, "10:00", sec=5), "2026-11-04T10:00:00", "garbage"):
        err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 1, "starts_at": bad}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 9, "branch_id": 1, "starts_at": iso(4)}), 404, "NOT_FOUND")
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 9, "starts_at": iso(4)}), 404, "NOT_FOUND")
    err(client.post(f"{API}/equipment-reservations", json={"type_id": 1, "branch_id": 1, "starts_at": iso(4)}), 401, "UNAUTHENTICATED")


def test_reserve_checks(client, admin_h, world, clock):
    def attempt(starts, **kw):
        return client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 1, "starts_at": starts, **kw})

    err(attempt(iso(3, "10:00")), 409, "RESERVATION_TOO_SOON")  # now = 10:00
    assert attempt(iso(3, "10:30")).status_code == 201  # exactly now + 30 minutes
    err(attempt(iso(7, "10:00")), 409, "DESK_CLOSED")
    err(attempt(iso(4, "20:00")), 409, "DESK_CLOSED")
    err(attempt(iso(4, "07:30")), 409, "DESK_CLOSED")
    e = err(attempt(iso(18, "10:00")), 409, "RESERVATION_TOO_FAR_AHEAD")
    assert e["details"]["latest_date"] == "2026-11-17"
    assert attempt(iso(17, "10:00")).status_code in (201, 409)


def test_reserve_limits_and_duplicates(client, admin_h, world):
    mk_item(client, admin_h, tag="CH-0002")
    mk_item(client, admin_h, tag="CH-0003")
    mk_type(client, admin_h, code="TABLET")
    mk_item(client, admin_h, type_id=2, tag="TB-0001")

    def attempt(starts, type_id=1):
        return client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": type_id, "branch_id": 1, "starts_at": starts})

    assert attempt(iso(4, "10:00")).status_code == 201
    err(attempt(iso(4, "13:30")), 409, "DUPLICATE_EQUIPMENT_RESERVATION")  # overlaps [10:00, 14:00)
    assert attempt(iso(4, "14:00")).status_code == 201  # touching intervals do not overlap
    err(attempt(iso(5, "10:00"), type_id=2), 409, "EQUIPMENT_RESERVATION_LIMIT_REACHED")
    cancel = client.post(f"{API}/equipment-reservations/1/cancel", headers=world["mh"])
    assert cancel.status_code == 200 and cancel.json()["cancel_reason"] == "member_request"
    assert attempt(iso(5, "10:00"), type_id=2).status_code == 201


def test_reserve_membership_debt_training_states(client, admin_h, world, clock):
    mk_type(client, admin_h, code="LAPTOP", requires_training=True)
    mk_item(client, admin_h, type_id=2, tag="LP-0001")
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 2, "branch_id": 1, "starts_at": iso(4, "10:00")}), 409, "TRAINING_REQUIRED")
    client.post(f"{API}/members/1/equipment-trainings", headers=world["lh"], json={"type_id": 2, "completed_on": "2026-11-03"})
    assert client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 2, "branch_id": 1, "starts_at": iso(4, "10:00")}).status_code == 201
    client.post(f"{API}/members", headers=admin_h, json=guest_body())
    gh = h(token_of(client, "guest@example.com", "Passw0rd1"))
    err(client.post(f"{API}/equipment-reservations", headers=gh, json={"type_id": 1, "branch_id": 1, "starts_at": iso(4, "10:00")}), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")
    client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 1, "starts_at": iso(4, "10:00")}), 409, "TYPE_INACTIVE")


def test_no_equipment_available_next_free(client, admin_h, world, clock):
    reserve(client, world["lh"], iso(4, "10:00"), member_id=1)  # holds 09:45-14:00 on Wednesday
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    r = client.post(f"{API}/equipment-reservations", headers=mb, json={"type_id": 1, "branch_id": 1, "starts_at": iso(4, "11:00")})
    e = err(r, 409, "NO_EQUIPMENT_AVAILABLE")
    # a reservation starting 14:00 would hold from 13:45 which overlaps; 14:15 is not a half hour; so 14:30
    assert e["details"]["next_free_at"] == iso(4, "14:30")


def test_no_equipment_without_items(client, admin_h, world):
    mk_type(client, admin_h, code="EMPTY")
    r = client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 2, "branch_id": 1, "starts_at": iso(4, "10:00")})
    e = err(r, 409, "NO_EQUIPMENT_AVAILABLE")
    assert e["details"]["next_free_at"] is None


def test_availability(client, admin_h, world, clock):
    mk_item(client, admin_h, tag="CH-0002")
    reserve(client, world["mh"], iso(4, "10:00"))
    r = client.get(f"{API}/equipment-types/1/availability?branch_id=1&date=2026-11-04", headers=world["mh"])
    assert r.status_code == 200
    j = r.json()
    assert j["capacity"] == 2 and j["type_id"] == 1 and j["branch_id"] == 1 and j["date"] == "2026-11-04"
    slots = {s["start"]: s["free"] for s in j["slots"]}
    assert list(slots)[0] == "08:00" and list(slots)[-1] == "19:30" and len(slots) == 24
    assert slots["09:00"] == 2 and slots["09:30"] == 1
    assert slots["10:00"] == 1 and slots["13:30"] == 1 and slots["14:00"] == 2
    j = client.get(f"{API}/equipment-types/1/availability?branch_id=1&date=2026-11-07", headers=world["mh"]).json()
    assert j["slots"] == []
    err(client.get(f"{API}/equipment-types/1/availability?date=2026-11-07", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/equipment-types/1/availability?branch_id=1", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/equipment-types/1/availability?branch_id=1&date=x", headers=world["mh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/equipment-types/9/availability?branch_id=1&date=2026-11-07", headers=world["mh"]), 404, "NOT_FOUND")
    err(client.get(f"{API}/equipment-types/1/availability?branch_id=9&date=2026-11-07", headers=world["mh"]), 404, "NOT_FOUND")


def test_availability_slot_before_hold(client, admin_h, world):
    reserve(client, world["mh"], iso(4, "10:00"))  # holds from 09:45: the 09:30 slot already sees it
    slots = {s["start"]: s["free"] for s in client.get(f"{API}/equipment-types/1/availability?branch_id=1&date=2026-11-04", headers=world["mh"]).json()["slots"]}
    assert slots["09:30"] == 0 and slots["09:00"] == 1 and slots["13:30"] == 0 and slots["14:00"] == 1


def test_cancel_reservation(client, admin_h, world, app):
    reserve(client, world["mh"], iso(4, "10:00"))
    reserve(client, world["lh"], iso(5, "10:00"), member_id=1)
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    err(client.post(f"{API}/equipment-reservations/1/cancel", headers=mb), 403, "FORBIDDEN")
    err(client.post(f"{API}/equipment-reservations/9/cancel", headers=mb), 404, "NOT_FOUND")
    j = client.post(f"{API}/equipment-reservations/2/cancel", headers=world["lh"]).json()
    assert j["status"] == "cancelled" and j["cancel_reason"] == "staff_request" and j["closed_at"] == iso(3)
    err(client.post(f"{API}/equipment-reservations/2/cancel", headers=world["lh"]), 409, "RESERVATION_NOT_ACTIVE")
    n = sel(app, sa.select(Notification).where(Notification.type == "equipment_reservation_cancelled"))
    assert len(n) == 1 and n[0].equipment_reservation_id == 2
    client.post(f"{API}/equipment-reservations/1/cancel", headers=world["mh"])
    assert len(sel(app, sa.select(Notification).where(Notification.type == "equipment_reservation_cancelled"))) == 1  # member_request: none
    assert [a.entity_id for a in audit(app, "equipment_reservation_cancelled")] == [2, 1]


def test_reservation_reads(client, admin_h, world):
    reserve(client, world["mh"], iso(5, "10:00"))
    reserve(client, world["mh"], iso(4, "10:00"))
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    mb = h(token_of(client, "b@example.com", "Passw0rd1"))
    assert [i["id"] for i in client.get(f"{API}/equipment-reservations", headers=world["lh"]).json()["items"]] == [2, 1]
    err(client.get(f"{API}/equipment-reservations", headers=world["mh"]), 403, "FORBIDDEN")
    assert client.get(f"{API}/equipment-reservations/1", headers=world["mh"]).status_code == 200
    err(client.get(f"{API}/equipment-reservations/1", headers=mb), 403, "FORBIDDEN")
    err(client.get(f"{API}/equipment-reservations/9", headers=mb), 404, "NOT_FOUND")
    assert client.get(f"{API}/members/1/equipment-reservations", headers=world["mh"]).json()["total"] == 2
    err(client.get(f"{API}/members/1/equipment-reservations", headers=mb), 403, "FORBIDDEN")
    assert client.get(f"{API}/equipment-reservations?from=2026-11-05&to=2026-11-05", headers=world["lh"]).json()["total"] == 1
    assert client.get(f"{API}/equipment-reservations?status=cancelled", headers=world["lh"]).json()["total"] == 0
    assert client.get(f"{API}/equipment-reservations?member_id=2", headers=world["lh"]).json()["total"] == 0


def test_collect_reservation(client, admin_h, world, clock, app):
    mk_item(client, admin_h, tag="AA-0001")
    reserve(client, world["mh"], iso(3, "11:00"))
    clock.set(dt(3, "10:44"))
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 1}), 409, "RESERVATION_NOT_READY")
    clock.set(dt(3, "10:45"))
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 2, "reservation_id": 1}), 409, "RESERVATION_OF_OTHER_MEMBER")
    loan = lend(client, world["lh"], reservation_id=1)
    assert loan["asset_tag"] == "AA-0001" and loan["reservation_id"] == 1 and loan["due_at"] == iso(3, "14:45")
    res = client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()
    assert res["status"] == "collected" and res["loan_id"] == 1 and res["closed_at"] == iso(3, "10:45")
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 1}), 409, "RESERVATION_NOT_ACTIVE")


def test_collect_late_boundary(client, admin_h, world, clock):
    reserve(client, world["mh"], iso(3, "11:00"))
    clock.set(dt(3, "11:30"))
    lend(client, world["lh"], reservation_id=1)
    ret(client, world["lh"])
    reserve(client, world["mh"], iso(3, "12:30"))
    clock.set(dt(3, "13:00", sec=1))
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 2}), 409, "RESERVATION_EXPIRED")


def test_collect_without_available_item(client, admin_h, world, clock):
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    lend(client, world["lh"], member_id=2, item_id=1)  # due 14:00, needed until 14:15
    reserve(client, world["mh"], iso(3, "14:30"))
    clock.set(dt(3, "14:30"))  # the first loan is overdue and still holds the only item
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 1}), 409, "ITEM_NOT_AVAILABLE")
    assert client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()["status"] == "booked"
    ret(client, world["lh"], loan_id=1)
    loan = lend(client, world["lh"], reservation_id=1)
    assert loan["reservation_id"] == 1


def test_lend_item_with_own_reservation(client, admin_h, world, clock):
    """LIB-EQ-18: the given item collects the member's own reservation."""
    reserve(client, world["mh"], iso(3, "10:30"))
    clock.set(dt(3, "10:15"))
    loan = lend(client, world["lh"], item_id=1)
    assert loan["reservation_id"] == 1
    assert client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()["status"] == "collected"


def test_lend_item_with_reservation_too_early_still_counts(client, admin_h, world, clock):
    reserve(client, world["mh"], iso(3, "14:30"))  # holds from 14:15; loan until 14:15 is fine
    loan = lend(client, world["lh"], item_id=1)
    assert loan["reservation_id"] is None
    ret(client, world["lh"])


def test_process_expires_and_notifies(client, admin_h, world, clock, app):
    reserve(client, world["mh"], iso(3, "11:00"))
    reserve(client, world["mh"], iso(4, "11:00"))
    clock.set(dt(3, "11:30"))
    r = client.post(f"{API}/equipment/process", headers=world["lh"])
    assert r.json() == {"expired_reservations": 0, "overdue_notices": 0}
    clock.set(dt(3, "11:30", sec=1))
    # an expired but unprocessed reservation no longer holds its item
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    assert client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()["status"] == "booked"
    r = client.post(f"{API}/equipment/process", headers=world["lh"])
    assert r.json() == {"expired_reservations": 1, "overdue_notices": 0}
    res = client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()
    assert res["status"] == "expired" and res["closed_at"] == dt(3, "11:30", sec=1).isoformat()
    n = sel(app, sa.select(Notification).where(Notification.type == "equipment_reservation_expired"))
    assert len(n) == 1 and n[0].equipment_reservation_id == 1
    assert [a.entity_id for a in audit(app, "equipment_reservation_expired")] == [1]
    assert audit(app, "equipment_processed")[-1].details == {"expired_reservations": 1, "overdue_notices": 0}
    err(client.post(f"{API}/equipment/process", headers=world["mh"]), 403, "FORBIDDEN")
    err(client.post(f"{API}/equipment-reservations/1/cancel", headers=world["mh"]), 409, "RESERVATION_NOT_ACTIVE")


def test_expired_reservation_does_not_hold_or_collect(client, admin_h, world, clock):
    reserve(client, world["mh"], iso(3, "11:00"))
    clock.set(dt(3, "11:31"))
    err(client.post(f"{API}/equipment-loans", headers=world["lh"], json={"member_id": 1, "reservation_id": 1}), 409, "RESERVATION_EXPIRED")
    reg(client, admin_h, email="b@example.com", university_id="20230002")
    lend(client, world["lh"], member_id=2, item_id=1)  # not held any more


def test_overdue_notices_once_per_day(client, admin_h, world, clock, app):
    lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "14:15"))
    assert client.post(f"{API}/equipment/process", headers=world["lh"]).json()["overdue_notices"] == 0
    clock.set(dt(3, "15:00"))
    assert client.post(f"{API}/equipment/process", headers=world["lh"]).json()["overdue_notices"] == 1
    assert client.post(f"{API}/equipment/process", headers=world["lh"]).json()["overdue_notices"] == 0
    clock.set(dt(4, "09:00"))
    assert client.post(f"{API}/equipment/process", headers=world["lh"]).json()["overdue_notices"] == 1
    n = sel(app, sa.select(Notification).where(Notification.type == "equipment_overdue"))
    assert len(n) == 2 and n[0].equipment_loan_id == 1 and "CH-0001" in n[0].message


def test_notifications_api_lists_equipment_types(client, admin_h, world):
    lend(client, world["lh"], item_id=1)
    r = client.get(f"{API}/members/1/notifications?type=equipment_loan_created", headers=world["mh"]).json()
    assert r["total"] == 1 and r["items"][0]["equipment_loan_id"] == 1 and r["items"][0]["equipment_reservation_id"] is None


# --- effects on other modules ----------------------------------------------------------------


def test_deactivation(client, admin_h, world, app):
    reserve(client, world["mh"], iso(4, "10:00"))
    lend(client, world["lh"], item_id=1)
    err(client.post(f"{API}/members/1/deactivate", headers=world["lh"]), 409, "MEMBER_HAS_OPEN_LOANS")
    ret(client, world["lh"])
    assert client.post(f"{API}/members/1/deactivate", headers=world["lh"]).status_code == 200
    res = client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()
    assert res["status"] == "cancelled" and res["cancel_reason"] == "member_deactivated"
    assert len(sel(app, sa.select(Notification).where(Notification.type == "equipment_reservation_cancelled"))) == 1


def test_deactivate_type_cancels_reservations(client, admin_h, world, app):
    reserve(client, world["mh"], iso(4, "10:00"))
    lend(client, world["lh"], item_id=1)
    assert client.patch(f"{API}/equipment-types/1", headers=admin_h, json={"is_active": False}).status_code == 200
    res = client.get(f"{API}/equipment-reservations/1", headers=world["lh"]).json()
    assert res["cancel_reason"] == "type_inactive" and res["status"] == "cancelled"
    assert client.get(f"{API}/equipment-loans/1", headers=world["lh"]).json()["status"] == "open"
    err(client.post(f"{API}/equipment-reservations", headers=world["mh"], json={"type_id": 1, "branch_id": 1, "starts_at": iso(5, "10:00")}), 409, "TYPE_INACTIVE")


def test_branch_deactivation(client, admin_h, world):
    mk_branch(client, admin_h, code="B2")
    client.patch(f"{API}/members/1", headers=admin_h, json={"home_branch_id": 2})
    err(client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/equipment-items/1/retire", headers=admin_h)
    assert client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}).status_code == 200


def test_branch_deactivation_lost_item_is_fine(client, admin_h, world):
    mk_branch(client, admin_h, code="B2")
    client.patch(f"{API}/members/1", headers=admin_h, json={"home_branch_id": 2})
    lend(client, world["lh"], item_id=1)
    client.post(f"{API}/equipment-loans/1/report-lost", headers=world["lh"])
    assert client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}).status_code == 200


def test_member_summary(client, admin_h, world, clock):
    reserve(client, world["mh"], iso(4, "10:00"))
    lend(client, world["lh"], item_id=1)
    s = client.get(f"{API}/members/1/summary", headers=world["mh"]).json()
    assert s["equipment"] == {"open_loans": 1, "overdue_loans": 0, "booked_reservations": 1}


# --- report ----------------------------------------------------------------------------------


def test_usage_report(client, admin_h, world, clock, app):
    mk_type(client, admin_h, code="AAA")
    lend(client, world["lh"], item_id=1)
    clock.set(dt(3, "16:00"))
    ret(client, world["lh"])  # 2 hours late: 4.00
    lend(client, world["lh"], item_id=1)
    client.post(f"{API}/equipment-loans/2/report-lost", headers=world["lh"])  # lost: 100.00 (+0)
    r = client.get(f"{API}/reports/equipment-usage?from=2026-11-01&to=2026-11-30", headers=world["lh"])
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["type_code"] for i in items] == ["AAA", "CHARGER"]
    assert items[0] == {"type_id": 2, "type_code": "AAA", "loans": 0, "late_returns": 0, "late_hours": 0,
                        "damaged_returns": 0, "lost": 0, "reservations": 0, "expired_reservations": 0, "fees_created": "0.00"}
    c = items[1]
    assert (c["loans"], c["late_returns"], c["late_hours"], c["lost"], c["fees_created"]) == (2, 1, 2, 1, "104.00")
    assert client.get(f"{API}/reports/equipment-usage?from=2026-11-04&to=2026-11-30", headers=world["lh"]).json()["items"][1]["loans"] == 0
    assert client.get(f"{API}/reports/equipment-usage?from=2026-11-01&to=2026-11-30&branch_id=2", headers=world["lh"]).json()["items"][1]["loans"] == 0
    err(client.get(f"{API}/reports/equipment-usage?from=2026-11-05&to=2026-11-01", headers=world["lh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/equipment-usage?from=2025-11-01&to=2026-11-30", headers=world["lh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/equipment-usage?from=2026-11-01", headers=world["lh"]), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/equipment-usage?from=2026-11-01&to=2026-11-30", headers=world["mh"]), 403, "FORBIDDEN")


def test_usage_report_reservations(client, admin_h, world, clock):
    reserve(client, world["mh"], iso(3, "11:00"))
    reserve(client, world["mh"], iso(5, "11:00"))
    clock.set(dt(3, "12:00"))
    client.post(f"{API}/equipment/process", headers=world["lh"])
    c = client.get(f"{API}/reports/equipment-usage?from=2026-11-03&to=2026-11-03", headers=world["lh"]).json()["items"][0]
    assert c["reservations"] == 1 and c["expired_reservations"] == 1


def test_exports_unaffected(client, admin_h, world):
    r = client.get(f"{API}/export", headers=admin_h)
    assert r.status_code == 200
    assert "equipment" not in r.text.lower()
