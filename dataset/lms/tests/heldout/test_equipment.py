"""Heldout tests: module 16 (Equipment loans). Generated from cases/equipment.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, balance, create_book, create_branch, deactivate_branch, deactivate_member, error_code, items, lend,
    member_fees, member_headers, pay, register_member, return_loan, waive,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, WED, FRI, SAT = "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-06", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); the desk is open 08:00-20:00 on working days


def at(clock, day, hh=9, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    clock.set(datetime(y, m, d, hh, mm, ss, tzinfo=TR))


def ts(day, hh, mm=0, ss=0):
    return f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+03:00"


def same(value, day, hh, mm=0, ss=0):
    y, m, d = (int(x) for x in day.split("-"))
    return datetime.fromisoformat(value) == datetime(y, m, d, hh, mm, ss, tzinfo=TR)


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def err(r, status, code):
    assert r.status_code == status and error_code(r) == code, r.text
    return r.json()["error"]


def etype(client, admin, *, code=None, unit="hours", period=4, fee="5.00", training=False, max_open=3, expect=201, **fields):
    """Equipment type; default: 4 hours, 5.00 per hour, no training, 3 open loans per member."""
    _seq[0] += 1
    body = {"code": code or f"T{_seq[0]}", "name": f"Type {_seq[0]}", "period_unit": unit, "period": period,
            "hourly_late_fee": fee, "requires_training": training, "max_open_per_member": max_open}
    body.update(fields)
    r = client.post("/api/v1/equipment-types", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def item(client, admin, type_, branch, *, tag=None, value="1000.00", expect=201, **fields):
    _seq[0] += 1
    body = {"type_id": type_["id"], "asset_tag": tag or f"EQ-{_seq[0]:04d}", "serial_no": f"SN{_seq[0]}",
            "branch_id": branch["id"], "value": value, "acquired_on": "2025-01-01"}
    body.update(fields)
    r = client.post("/api/v1/equipment-items", headers=admin, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def try_lend(client, headers, member_id, item_id=None, reservation_id=None):
    body = {"member_id": member_id}
    if item_id is not None:
        body["item_id"] = item_id
    if reservation_id is not None:
        body["reservation_id"] = reservation_id
    return client.post("/api/v1/equipment-loans", headers=headers, json=body)


def elend(client, headers, member_id, item_id):
    return ok(try_lend(client, headers, member_id, item_id), 201)


def ret(client, headers, loan_id, condition="good", damage_fee=None):
    body = {"condition": condition}
    if damage_fee is not None:
        body["damage_fee"] = damage_fee
    return client.post(f"/api/v1/equipment-loans/{loan_id}/return", headers=headers, json=body)


def act(client, headers, path):
    return client.post(f"/api/v1/{path}", headers=headers)


def try_reserve(client, headers, type_id, branch_id, starts_at, member_id=None):
    body = {"type_id": type_id, "branch_id": branch_id, "starts_at": starts_at}
    if member_id is not None:
        body["member_id"] = member_id
    return client.post("/api/v1/equipment-reservations", headers=headers, json=body)


def reserve(client, lib, type_, branch, member_, day, hh, mm=0):
    """Staff reservation for ``member_``."""
    return ok(try_reserve(client, lib, type_["id"], branch["id"], ts(day, hh, mm), member_id=member_["id"]), 201)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def process(client, lib):
    return ok(client.post("/api/v1/equipment/process", headers=lib))


def train(client, headers, member_id, type_id, completed_on):
    return client.post(f"/api/v1/members/{member_id}/equipment-trainings", headers=headers,
                       json={"type_id": type_id, "completed_on": completed_on})


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fees_of(client, lib, member_id):
    return sorted((f["kind"], f["amount"]) for f in items(member_fees(client, lib, member_id)))


def debt(client, lib, branch, member_, amount="50.00"):
    """A book damage fee of ``amount`` for ``member_``."""
    copy = add_copy(client, lib, create_book(client, lib)["id"], home_branch_id=branch["id"])
    loan = lend(client, lib, member_["id"], copy["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=amount)


def test_t_eq_01_b(client, clock, admin, librarian, branch_a):
    """T-EQ-01-b (LIB-EQ-01): 201 with due_at 20:00; then 409 DESK_CLOSED"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 19, 59)
    assert same(elend(client, librarian, m1["id"], i1["id"])["due_at"], TUE, 20, 0)
    at(clock, TUE, 20, 0)
    err(try_lend(client, librarian, m2["id"], i2["id"]), 409, "DESK_CLOSED")


def test_t_eq_02_b(client, clock, admin, librarian, branch_a):
    """T-EQ-02-b (LIB-EQ-02): opens_at Tue 08:00; Fri 2026-10-30 08:00"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 7, 0)
    e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], TUE, 8, 0)
    at(clock, "2026-10-29", 10, 0)
    e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], "2026-10-30", 8, 0)


def test_t_eq_03_b(client, admin):
    """T-EQ-03-b (LIB-EQ-03): 409 CONFLICT with details.field code"""
    etype(client, admin, code="LAP")
    r = client.post("/api/v1/equipment-types", headers=admin, json={"code": "lap", "name": "Laptop", "period_unit": "working_days",
                    "period": 3, "hourly_late_fee": "25.00", "requires_training": True, "max_open_per_member": 1})
    assert err(r, 409, "CONFLICT")["details"]["field"] == "code"


def test_t_eq_03_d(client, librarian):
    """T-EQ-03-d (LIB-EQ-03): 403 FORBIDDEN"""
    etype(client, librarian, expect=403)


def test_t_eq_04_b(client, clock, admin, librarian, branch_a):
    """T-EQ-04-b (LIB-EQ-04): Old loan due 13:00, late_hours 2, late fee 10.00 (old rate); new loan due 16:30"""
    t = etype(client, admin, period=4, fee="5.00")
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    l1 = elend(client, librarian, m1["id"], i1["id"])
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"period": 2, "hourly_late_fee": "10.00"}))
    at(clock, TUE, 14, 30)
    r = ok(ret(client, librarian, l1["id"]))
    assert same(r["due_at"], TUE, 13, 0) and r["late_hours"] == 2
    assert fees_of(client, librarian, m1["id"]) == [("equipment_late_fee", "10.00")]
    assert same(elend(client, librarian, m2["id"], i2["id"])["due_at"], TUE, 16, 30)


def test_t_eq_05_b(client, admin, librarian, branch_a):
    """T-EQ-05-b (LIB-EQ-05): 409 TYPE_INACTIVE twice; the return gives 200"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = elend(client, librarian, m1["id"], i1["id"])
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    err(try_lend(client, librarian, m2["id"], i2["id"]), 409, "TYPE_INACTIVE")
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "TYPE_INACTIVE")
    assert ok(ret(client, librarian, loan["id"]))["status"] == "returned"


def test_t_eq_06_b(client, admin, librarian, branch_a):
    """T-EQ-06-b (LIB-EQ-06): 200; only BB"""
    etype(client, admin, code="AA")
    bb = etype(client, admin, code="BB")
    ok(client.patch(f"/api/v1/equipment-types/{bb['id']}", headers=admin, json={"is_active": False}))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert [x["code"] for x in items(get(client, mh, "equipment-types", is_active="false"))] == ["BB"]


def test_t_eq_07_b(client, admin, librarian, branch_a):
    """T-EQ-07-b (LIB-EQ-07): 409 CONFLICT; 409 BRANCH_INACTIVE; 422 three times; 403"""
    t = etype(client, admin)
    item(client, admin, t, branch_a, tag="EQ-0100")
    assert error_code(item(client, admin, t, branch_a, tag="EQ-0100", expect=409)) == "CONFLICT"
    zz = create_branch(client, admin, "ZZ")
    deactivate_branch(client, admin, zz["id"])
    assert error_code(item(client, admin, t, zz, expect=409)) == "BRANCH_INACTIVE"
    item(client, admin, t, branch_a, tag="AB1", expect=422)
    item(client, admin, t, branch_a, value="0.99", expect=422)
    item(client, admin, t, branch_a, acquired_on="2026-11-03", expect=422)
    item(client, librarian, t, branch_a, expect=403)


def test_t_eq_08_b(client, admin, librarian, branch_a, branch_b):
    """T-EQ-08-b (LIB-EQ-08): 409 INVALID_ITEM_STATUS; value change 200"""
    it = item(client, admin, etype(client, admin), branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], it["id"])
    url = f"/api/v1/equipment-items/{it['id']}"
    err(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}), 409, "INVALID_ITEM_STATUS")
    assert ok(client.patch(url, headers=admin, json={"value": "900.00"}))["value"] == "900.00"


def test_t_eq_09_b(client, admin, librarian, branch_a):
    """T-EQ-09-b (LIB-EQ-09): 403 FORBIDDEN both"""
    it = item(client, admin, etype(client, admin), branch_a)
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get("/api/v1/equipment-items", headers=mh).status_code == 403
    assert client.get(f"/api/v1/equipment-items/{it['id']}", headers=mh).status_code == 403


def test_t_eq_10_b(client, admin, librarian, branch_a):
    """T-EQ-10-b (LIB-EQ-10): 403; available; retired"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    for it in (i1, i2):
        ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"], "damaged", "10.00"))
    assert act(client, librarian, f"equipment-items/{i1['id']}/retire").status_code == 403
    assert ok(act(client, librarian, f"equipment-items/{i1['id']}/repair-done"))["status"] == "available"
    assert ok(act(client, admin, f"equipment-items/{i2['id']}/retire"))["status"] == "retired"


def test_t_eq_11_b(client, admin, librarian, branch_a):
    """T-EQ-11-b (LIB-EQ-11): 422; 409 TRAINING_NOT_REQUIRED; 201 twice"""
    t, plain = etype(client, admin, training=True), etype(client, admin)
    m = member(client, librarian, branch_a)
    assert train(client, librarian, m["id"], t["id"], "2026-11-03").status_code == 422
    err(train(client, librarian, m["id"], plain["id"], "2026-11-02"), 409, "TRAINING_NOT_REQUIRED")
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)


def test_t_eq_11_d(client, admin, librarian, branch_a):
    """T-EQ-11-d (LIB-EQ-11): 200 with one record; 403 FORBIDDEN"""
    t = etype(client, admin, training=True)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    mh = member_headers(client, m)
    assert len(items(get(client, mh, f"members/{m['id']}/equipment-trainings"))) == 1
    assert client.get(f"/api/v1/members/{other['id']}/equipment-trainings", headers=mh).status_code == 403


def test_t_eq_12_b(client, admin, librarian, branch_a):
    """T-EQ-12-b (LIB-EQ-12): 422, 422, 403"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    assert try_lend(client, librarian, m["id"], it["id"], reservation_id=1).status_code == 422
    assert try_lend(client, librarian, m["id"]).status_code == 422
    assert try_lend(client, member_headers(client, m), m["id"], it["id"]).status_code == 403


def test_t_eq_13_b(client, admin, librarian, branch_a):
    """T-EQ-13-b (LIB-EQ-13): 409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE"""
    it = item(client, admin, etype(client, admin), branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_lend(client, librarian, g["id"], it["id"]), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")


def test_t_eq_13_d(client, admin, librarian, branch_a):
    """T-EQ-13-d (LIB-EQ-13): 409 TRAINING_REQUIRED; 201; 201"""
    t = etype(client, admin, training=True)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    err(try_lend(client, librarian, s["id"], i1["id"]), 409, "TRAINING_REQUIRED")
    ok(try_lend(client, librarian, a["id"], i1["id"]), 201)
    ok(train(client, librarian, s["id"], t["id"], "2026-11-02"), 201)
    ok(try_lend(client, librarian, s["id"], i2["id"]), 201)


def test_t_eq_13_f(client, admin, librarian, branch_a):
    """T-EQ-13-f (LIB-EQ-13): 409 TYPE_LIMIT_REACHED with details.limit 1"""
    t = etype(client, admin, max_open=1)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    elend(client, librarian, m["id"], i1["id"])
    assert err(try_lend(client, librarian, m["id"], i2["id"]), 409, "TYPE_LIMIT_REACHED")["details"]["limit"] == 1


def test_t_eq_13_h(client, clock, admin, librarian, branch_a):
    """T-EQ-13-h (LIB-EQ-13): DESK_CLOSED; then TYPE_INACTIVE (desk before type before member)"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    at(clock, SAT, 10, 0)
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "DESK_CLOSED")
    at(clock, "2026-11-09", 10, 0)
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "TYPE_INACTIVE")


def test_t_eq_14_b(client, clock, admin, librarian, branch_a):
    """T-EQ-14-b (LIB-EQ-14): Loan: overdue, accrued 50.00; balance accrued_late_fees and total_debt 50.00, blocked true"""
    it = item(client, admin, etype(client, admin, fee="10.00"), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 18, 0)
    r = get(client, librarian, f"equipment-loans/{loan['id']}")
    assert (r["overdue"], r["accrued_late_fee"]) == (True, "50.00")
    b = balance(client, librarian, m["id"])
    assert (b["outstanding_fees"], b["accrued_late_fees"], b["total_debt"], b["blocked"]) == ("0.00", "50.00", "50.00", True)


def test_t_eq_15_b(client, clock, admin, librarian, branch_a):
    """T-EQ-15-b (LIB-EQ-15): Due Tue 2026-11-03 17:00"""
    it = item(client, admin, etype(client, admin, unit="working_days", period=3), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2026-10-28", 15, 0)
    assert same(elend(client, librarian, m["id"], it["id"])["due_at"], TUE, 17, 0)


def test_t_eq_16_a(client, clock, admin, librarian, branch_a):
    """T-EQ-16-a (LIB-EQ-16): Not overdue, accrued 0.00; then overdue, accrued 5.00"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 14, 35, 0)
    r = get(client, librarian, f"equipment-loans/{loan['id']}")
    assert (r["overdue"], r["accrued_late_fee"]) == (False, "0.00")
    at(clock, TUE, 14, 35, 1)
    r = get(client, librarian, f"equipment-loans/{loan['id']}")
    assert (r["overdue"], r["accrued_late_fee"]) == (True, "5.00")


def test_t_eq_17_b(client, admin, librarian, branch_a):
    """T-EQ-17-b (LIB-EQ-17): 200; 403; 403; 200 with 1 item; 403"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = elend(client, librarian, m["id"], i1["id"]), elend(client, librarian, other["id"], i2["id"])
    mh = member_headers(client, m)
    assert client.get(f"/api/v1/equipment-loans/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/equipment-loans/{foreign['id']}", headers=mh).status_code == 403
    assert client.get("/api/v1/equipment-loans", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/equipment-loans")["total"] == 1
    assert client.get(f"/api/v1/members/{other['id']}/equipment-loans", headers=mh).status_code == 403


def test_t_eq_18_b(client, clock, admin, librarian, branch_a):
    """T-EQ-18-b (LIB-EQ-18): 201 with reservation_id null; reservation stays booked"""
    t = etype(client, admin)
    i1, _ = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 40)
    assert elend(client, librarian, m["id"], i1["id"])["reservation_id"] is None
    assert get(client, librarian, f"equipment-reservations/{res['id']}")["status"] == "booked"


def test_t_eq_19_b(client, clock, admin, librarian, branch_a):
    """T-EQ-19-b (LIB-EQ-19): Due 20:00; 409 EXTENSION_NOT_POSSIBLE"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 13, 30)
    l1 = elend(client, librarian, m1["id"], i1["id"])
    at(clock, TUE, 14, 0)
    assert same(ok(act(client, librarian, f"equipment-loans/{l1['id']}/extend"))["due_at"], TUE, 20, 0)
    at(clock, TUE, 16, 0)
    l2 = elend(client, librarian, m2["id"], i2["id"])
    err(act(client, librarian, f"equipment-loans/{l2['id']}/extend"), 409, "EXTENSION_NOT_POSSIBLE")


def test_t_eq_19_d(client, clock, admin, librarian, branch_a):
    """T-EQ-19-d (LIB-EQ-19): 409 ITEM_NEEDED_FOR_RESERVATION; due stays 14:20"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m2, TUE, 16)
    at(clock, TUE, 10, 20)
    loan = elend(client, librarian, m1["id"], it["id"])
    at(clock, TUE, 13, 0)
    err(act(client, librarian, f"equipment-loans/{loan['id']}/extend"), 409, "ITEM_NEEDED_FOR_RESERVATION")
    assert same(get(client, librarian, f"equipment-loans/{loan['id']}")["due_at"], TUE, 14, 20)


def test_t_eq_20_b(client, clock, admin, librarian, branch_a):
    """T-EQ-20-b (LIB-EQ-20): 200; late_hours 14; late fee 70.00"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, FRI, 16, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, SAT, 10, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 14
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "70.00")]


def test_t_eq_21_b(client, admin, librarian, branch_a):
    """T-EQ-21-b (LIB-EQ-21): 422; 422; 409 DAMAGE_FEE_EXCEEDS_VALUE; 200 without fee, item in_repair"""
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    assert ret(client, librarian, loan["id"], "damaged").status_code == 422
    assert ret(client, librarian, loan["id"], "good", "1.00").status_code == 422
    err(ret(client, librarian, loan["id"], "damaged", "1000.01"), 409, "DAMAGE_FEE_EXCEEDS_VALUE")
    ok(ret(client, librarian, loan["id"], "damaged", "0.00"))
    assert member_fees(client, librarian, m["id"])["total"] == 0
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "in_repair"


def test_t_eq_22_b(client, clock, admin, librarian, branch_a):
    """T-EQ-22-b (LIB-EQ-22): late_hours 1 and 2"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 15, 20)
    assert ok(ret(client, librarian, l1["id"]))["late_hours"] == 1
    at(clock, TUE, 15, 21)
    assert ok(ret(client, librarian, l2["id"]))["late_hours"] == 2


def test_t_eq_23_b(client, clock, admin, librarian, branch_a):
    """T-EQ-23-b (LIB-EQ-23): 6000.00 (20 % cap); 66.67 (cap 66.666 rounded half up)"""
    big = item(client, admin, etype(client, admin, period=2, fee="25.00"), branch_a, value="30000.00")
    small = item(client, admin, etype(client, admin, period=2, fee="5.00"), branch_a, value="333.33")
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    l1, l2 = elend(client, librarian, m1["id"], big["id"]), elend(client, librarian, m2["id"], small["id"])
    at(clock, WED, 7, 0)
    assert ok(ret(client, librarian, l2["id"]))["late_hours"] == 20
    at(clock, "2026-11-15", 23, 0)
    assert ok(ret(client, librarian, l1["id"]))["late_hours"] == 300
    assert fees_of(client, librarian, m1["id"]) == [("equipment_late_fee", "6000.00")]
    assert fees_of(client, librarian, m2["id"]) == [("equipment_late_fee", "66.67")]


def test_t_eq_24_b(client, admin, librarian, branch_a):
    """T-EQ-24-b (LIB-EQ-24): Only equipment_lost; 409 LOAN_NOT_OPEN twice"""
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a, value="800.00"), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    l1, l2 = elend(client, librarian, m["id"], i1["id"]), elend(client, librarian, m["id"], i2["id"])
    ok(act(client, librarian, f"equipment-loans/{l1['id']}/report-lost"))
    assert fees_of(client, librarian, m["id"]) == [("equipment_lost", "800.00")]
    err(act(client, librarian, f"equipment-loans/{l1['id']}/report-lost"), 409, "LOAN_NOT_OPEN")
    ok(ret(client, librarian, l2["id"]))
    err(act(client, librarian, f"equipment-loans/{l2['id']}/report-lost"), 409, "LOAN_NOT_OPEN")


def test_t_eq_25_b(client, admin, librarian, branch_a):
    """T-EQ-25-b (LIB-EQ-25): Only the equipment fee"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m, "5.00")
    loan = elend(client, librarian, m["id"], it["id"])
    ok(ret(client, librarian, loan["id"], "damaged", "7.00"))
    rows = items(get(client, librarian, "fees", kind="equipment_damage_fee"))
    assert [(f["amount"], f["equipment_loan_id"]) for f in rows] == [("7.00", loan["id"])]


def test_t_eq_26_b(client, admin, librarian, branch_a):
    """T-EQ-26-b (LIB-EQ-26): 422 VALIDATION_ERROR each"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10), member_id=m["id"]).status_code == 422
    assert try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10)).status_code == 422
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10, 15)).status_code == 422
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10, 0, 30)).status_code == 422


def test_t_eq_27_b(client, admin, librarian, branch_a):
    """T-EQ-27-b (LIB-EQ-27): M1, M2 201; M3 13:00 409 NO_EQUIPMENT_AVAILABLE; M3 14:30 201"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    reserve(client, librarian, t, branch_a, m2, TUE, 12)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 13), member_id=m3["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    reserve(client, librarian, t, branch_a, m3, TUE, 14, 30)


def test_t_eq_27_d(client, admin, librarian, branch_a):
    """T-EQ-27-d (LIB-EQ-27): M1 201; M2 409 NO_EQUIPMENT_AVAILABLE"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    broken = item(client, admin, t, branch_a)
    m0, m1, m2 = (member(client, librarian, branch_a) for _ in range(3))
    ok(ret(client, librarian, elend(client, librarian, m0["id"], broken["id"])["id"], "damaged", "0.00"))
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")


def test_t_eq_28_b(client, clock, admin, librarian, branch_a):
    """T-EQ-28-b (LIB-EQ-28): 409 MEMBERSHIP_EXPIRED; 201"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2027-10-25", 9, 0)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2027-11-02", 10), member_id=m["id"]), 409, "MEMBERSHIP_EXPIRED")
    reserve(client, librarian, t, branch_a, m, "2027-11-01", 10)


def test_t_eq_28_d(client, admin, librarian, branch_a):
    """T-EQ-28-d (LIB-EQ-28): 201; 409 TRAINING_REQUIRED"""
    t = etype(client, admin, training=True)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2025-11-05"), 201)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-05", 10), member_id=m["id"]), 409, "TRAINING_REQUIRED")


def test_t_eq_28_f(client, clock, admin, librarian, branch_a):
    """T-EQ-28-f (LIB-EQ-28): 201; 409 RESERVATION_TOO_SOON"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 9, 0)
    reserve(client, librarian, t, branch_a, m1, MON, 9, 30)
    at(clock, MON, 9, 1)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(MON, 9, 30), member_id=m2["id"]), 409, "RESERVATION_TOO_SOON")


def test_t_eq_28_h(client, admin, librarian, branch_a):
    """T-EQ-28-h (LIB-EQ-28): 409 EQUIPMENT_RESERVATION_LIMIT_REACHED"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, TUE, 10)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-05", 10), member_id=m["id"]), 409, "EQUIPMENT_RESERVATION_LIMIT_REACHED")


def test_t_eq_28_j(client, admin, librarian, branch_a):
    """T-EQ-28-j (LIB-EQ-28): 409 NO_EQUIPMENT_AVAILABLE with details.next_free_at Tue 14:30"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 12), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    assert same(e["details"]["next_free_at"], TUE, 14, 30)


def test_t_eq_29_b(client, clock, admin, librarian, branch_a):
    """T-EQ-29-b (LIB-EQ-29): 409 RESERVATION_NOT_READY; 409 RESERVATION_EXPIRED; 201"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 44)
    err(try_lend(client, librarian, m["id"], reservation_id=res["id"]), 409, "RESERVATION_NOT_READY")
    at(clock, TUE, 10, 30, 1)
    err(try_lend(client, librarian, m["id"], reservation_id=res["id"]), 409, "RESERVATION_EXPIRED")
    at(clock, TUE, 10, 30)
    ok(try_lend(client, librarian, m["id"], reservation_id=res["id"]), 201)


def test_t_eq_29_d(client, clock, admin, librarian, branch_a):
    """T-EQ-29-d (LIB-EQ-29): 409 ITEM_NOT_AVAILABLE; reservation stays booked"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m0, m1 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m0["id"], it["id"])
    res = reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 9, 50)
    err(try_lend(client, librarian, m1["id"], reservation_id=res["id"]), 409, "ITEM_NOT_AVAILABLE")
    assert get(client, librarian, f"equipment-reservations/{res['id']}")["status"] == "booked"


def test_t_eq_30_b(client, admin, librarian, branch_a):
    """T-EQ-30-b (LIB-EQ-30): 403 FORBIDDEN; then staff_request and one equipment_reservation_cancelled notification for M"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    assert act(client, member_headers(client, other), f"equipment-reservations/{res['id']}/cancel").status_code == 403
    assert ok(act(client, librarian, f"equipment-reservations/{res['id']}/cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1


def test_t_eq_31_b(client, clock, admin, librarian, branch_a):
    """T-EQ-31-b (LIB-EQ-31): 201 for M2; then 1 expired and one equipment_reservation_expired notification for M1"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 10, 31)
    ok(try_lend(client, librarian, m2["id"], it["id"]), 201)
    at(clock, TUE, 10, 40)
    assert process(client, librarian)["expired_reservations"] == 1
    assert len(notes(client, librarian, m1["id"], "equipment_reservation_expired")) == 1


def test_t_eq_32_a(client, clock, admin, librarian, branch_a):
    """T-EQ-32-a (LIB-EQ-32): {expired_reservations: 0, overdue_notices: 1}, then 0 notices; Wed 1; member has 2 equipment_overdue notifications"""
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 14, 0)
    assert process(client, librarian) == {"expired_reservations": 0, "overdue_notices": 1}
    assert process(client, librarian)["overdue_notices"] == 0
    at(clock, WED, 9, 0)
    assert process(client, librarian)["overdue_notices"] == 1
    assert len(notes(client, librarian, m["id"], "equipment_overdue")) == 2


def test_t_eq_33_b(client, admin, librarian, branch_a):
    """T-EQ-33-b (LIB-EQ-33): 200; capacity 1; slots empty"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    mh = member_headers(client, member(client, librarian, branch_a))
    r = get(client, mh, f"equipment-types/{t['id']}/availability", branch_id=branch_a["id"], date=SAT)
    assert (r["capacity"], r["slots"]) == (1, [])


def test_t_eq_34_b(client, admin, librarian, branch_a):
    """T-EQ-34-b (LIB-EQ-34): 403; 200 with 1 item; 200; 403"""
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = reserve(client, librarian, t, branch_a, m, TUE, 10), reserve(client, librarian, t, branch_a, other, TUE, 10)
    mh = member_headers(client, m)
    assert client.get("/api/v1/equipment-reservations", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/equipment-reservations")["total"] == 1
    assert client.get(f"/api/v1/equipment-reservations/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/equipment-reservations/{foreign['id']}", headers=mh).status_code == 403


def test_t_eq_35_b(client, admin, librarian, branch_a):
    """T-EQ-35-b (LIB-EQ-35): Reservation cancelled with member_deactivated; one equipment_reservation_cancelled notification"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    deactivate_member(client, librarian, m["id"])
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1


def test_t_eq_36_a(client, admin):
    """T-EQ-36-a (LIB-EQ-36): 409 BRANCH_IN_USE; then 200"""
    br = create_branch(client, admin, "QQ")
    it = item(client, admin, etype(client, admin), br)
    err(client.patch(f"/api/v1/branches/{br['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(act(client, admin, f"equipment-items/{it['id']}/retire"))
    deactivate_branch(client, admin, br["id"])


def test_t_eq_38_b(client, admin, librarian, branch_a):
    """T-EQ-38-b (LIB-EQ-38): The member's notifications: only equipment_loan_created"""
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    res = ok(try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10)), 201)
    ok(act(client, mh, f"equipment-reservations/{res['id']}/cancel"))
    loan = elend(client, librarian, m["id"], it["id"])
    ok(act(client, mh, f"equipment-loans/{loan['id']}/extend"))
    assert [n["type"] for n in items(get(client, librarian, f"members/{m['id']}/notifications"))] == ["equipment_loan_created"]


def test_t_eq_39_b(client, admin, librarian, branch_a):
    """T-EQ-39-b (LIB-EQ-39): One entry each for equipment_reservation_created, equipment_reservation_cancelled, equipment_processed"""
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    res = reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    ok(act(client, librarian, f"equipment-reservations/{res['id']}/cancel"))
    process(client, librarian)
    for event in ("equipment_reservation_created", "equipment_reservation_cancelled", "equipment_processed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event


def test_t_eq_40_b(client, admin, librarian, branch_a):
    """T-EQ-40-b (LIB-EQ-40): 422; 422; 403; 200"""
    url = "/api/v1/reports/equipment-usage"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": WED}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200
