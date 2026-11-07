MODULE = "equipment"
TITLE = "module 16 (Equipment loans)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- desk hours
    dict(id="T-EQ-01-a", req="LIB-EQ-01", type="Boundary", input="Lend on Tue at 07:59:59, then at 08:00", expected="`409 DESK_CLOSED`, then 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 7, 59, 59)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    at(clock, TUE, 8, 0)
    ok(try_lend(client, librarian, m["id"], it["id"]), 201)
'''),
    dict(id="T-EQ-01-b", req="LIB-EQ-01", type="Boundary", input="Lend on Tue at 19:59, then another item at 20:00", expected="201 with `due_at` 20:00; then `409 DESK_CLOSED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 19, 59)
    assert same(elend(client, librarian, m1["id"], i1["id"])["due_at"], TUE, 20, 0)
    at(clock, TUE, 20, 0)
    err(try_lend(client, librarian, m2["id"], i2["id"]), 409, "DESK_CLOSED")
'''),
    dict(id="T-EQ-01-c", req="LIB-EQ-01", type="Error", input="Lend on Saturday 2026-11-07 10:00 and on the holiday 2026-10-29 10:00", expected="`409 DESK_CLOSED` both", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    for day in (SAT, "2026-10-29"):
        at(clock, day, 10, 0)
        err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
'''),
    dict(id="T-EQ-02-a", req="LIB-EQ-02", type="Normal", input="Lend on Fri 2026-11-06 20:30 and on Sat 10:00", expected="`DESK_CLOSED` with `details.opens_at` Mon 2026-11-09 08:00 both", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    for day, hh, mm in ((FRI, 20, 30), (SAT, 10, 0)):
        at(clock, day, hh, mm)
        e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
        assert same(e["details"]["opens_at"], "2026-11-09", 8, 0)
'''),
    dict(id="T-EQ-02-b", req="LIB-EQ-02", type="Normal", input="Lend on Tue 07:00 and on the holiday Thu 2026-10-29 10:00", expected="`opens_at` Tue 08:00; Fri 2026-10-30 08:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 7, 0)
    e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], TUE, 8, 0)
    at(clock, "2026-10-29", 10, 0)
    e = err(try_lend(client, librarian, m["id"], it["id"]), 409, "DESK_CLOSED")
    assert same(e["details"]["opens_at"], "2026-10-30", 8, 0)
'''),
    # ---------------------------------------------------------------- types
    dict(id="T-EQ-03-a", req="LIB-EQ-03", type="Normal", input="Admin creates a type `chg_4` (4 hours, 5.00) without `requires_training`", expected="201; code `CHG_4`, `requires_training` false, active", code='''
def TEST(client, admin):
    body = {"code": "chg_4", "name": "Phone charger", "period_unit": "hours", "period": 4, "hourly_late_fee": "5.00", "max_open_per_member": 1}
    r = ok(client.post("/api/v1/equipment-types", headers=admin, json=body), 201)
    assert (r["code"], r["requires_training"], r["is_active"], r["period"], r["hourly_late_fee"]) == ("CHG_4", False, True, 4, "5.00")
'''),
    dict(id="T-EQ-03-b", req="LIB-EQ-03", type="Error", input="Type `LAP`, then `lap`", expected="`409 CONFLICT` with `details.field` `code`", code='''
def TEST(client, admin):
    etype(client, admin, code="LAP")
    r = client.post("/api/v1/equipment-types", headers=admin, json={"code": "lap", "name": "Laptop", "period_unit": "working_days",
                    "period": 3, "hourly_late_fee": "25.00", "requires_training": True, "max_open_per_member": 1})
    assert err(r, 409, "CONFLICT")["details"]["field"] == "code"
'''),
    dict(id="T-EQ-03-c", req="LIB-EQ-03", type="Error", input="hours period 9; working_days period 11; period 0; fee 0.49; fee 50.01; max_open 4; max_open 0; code `A`; code `AB-1`; unit `days`", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, admin):
    bad = [dict(period=9), dict(unit="working_days", period=11), dict(period=0), dict(fee="0.49"), dict(fee="50.01"),
           dict(max_open=4), dict(max_open=0), dict(code="A"), dict(code="AB-1"), dict(unit="days")]
    for fields in bad:
        etype(client, admin, expect=422, **fields)
'''),
    dict(id="T-EQ-03-d", req="LIB-EQ-03", type="Error", input="Librarian creates a type", expected="`403 FORBIDDEN`", code='''
def TEST(client, librarian):
    etype(client, librarian, expect=403)
'''),
    dict(id="T-EQ-04-a", req="LIB-EQ-04", type="Normal", input="PATCH `name` and `period`; PATCH `code`; PATCH `period_unit`", expected="200 with the new values; `422` twice", code='''
def TEST(client, admin):
    t = etype(client, admin)
    url = f"/api/v1/equipment-types/{t['id']}"
    r = ok(client.patch(url, headers=admin, json={"name": "Charger", "period": 6}))
    assert (r["name"], r["period"]) == ("Charger", 6)
    assert client.patch(url, headers=admin, json={"code": "NEW"}).status_code == 422
    assert client.patch(url, headers=admin, json={"period_unit": "working_days"}).status_code == 422
'''),
    dict(id="T-EQ-04-b", req="LIB-EQ-04", type="Normal", input="Loan Tue 09:00 (4 hours, 5.00); type changed to 2 hours, 10.00; returned 14:30; new loan at 14:30", expected="Old loan due 13:00, `late_hours` 2, late fee 10.00 (old rate); new loan due 16:30", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-05-a", req="LIB-EQ-05", type="Normal", input="Member reserved Wed 10:00; admin deactivates the type", expected="Reservation `cancelled` with `type_inactive`; one `equipment_reservation_cancelled` notification", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = ok(try_reserve(client, member_headers(client, m), t["id"], branch_a["id"], ts(WED, 10)), 201)
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "type_inactive")
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1
'''),
    dict(id="T-EQ-05-b", req="LIB-EQ-05", type="Error", input="Open loan of a type; type deactivated; lend another item; reserve; return the open loan", expected="`409 TYPE_INACTIVE` twice; the return gives 200", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    loan = elend(client, librarian, m1["id"], i1["id"])
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    err(try_lend(client, librarian, m2["id"], i2["id"]), 409, "TYPE_INACTIVE")
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "TYPE_INACTIVE")
    assert ok(ret(client, librarian, loan["id"]))["status"] == "returned"
'''),
    dict(id="T-EQ-06-a", req="LIB-EQ-06", type="Normal", input="Types `BB` (no items) and `AA` (available item at A, item on loan at B, retired item); list", expected="Order AA, BB; AA `items_total` 2, `items_available` 1; BB 0 and 0", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    bb, aa = etype(client, admin, code="BB"), etype(client, admin, code="AA")
    item(client, admin, aa, branch_a)
    on_loan, gone = item(client, admin, aa, branch_b), item(client, admin, aa, branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], on_loan["id"])
    ok(act(client, admin, f"equipment-items/{gone['id']}/retire"))
    rows = items(get(client, librarian, "equipment-types"))
    assert [(x["code"], x["items_total"], x["items_available"]) for x in rows] == [("AA", 2, 1), ("BB", 0, 0)]
'''),
    dict(id="T-EQ-06-b", req="LIB-EQ-06", type="Normal", input="Types `AA` and `BB`, `BB` deactivated; member lists with `is_active=false`", expected="200; only BB", code='''
def TEST(client, admin, librarian, branch_a):
    etype(client, admin, code="AA")
    bb = etype(client, admin, code="BB")
    ok(client.patch(f"/api/v1/equipment-types/{bb['id']}", headers=admin, json={"is_active": False}))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert [x["code"] for x in items(get(client, mh, "equipment-types", is_active="false"))] == ["BB"]
'''),
    # ---------------------------------------------------------------- items
    dict(id="T-EQ-07-a", req="LIB-EQ-07", type="Normal", input="Admin creates an item with asset tag `eq-ab12`, value 2500.00", expected="201; `asset_tag` `EQ-AB12`, status `available`", code='''
def TEST(client, admin, branch_a):
    t = etype(client, admin)
    r = item(client, admin, t, branch_a, tag="eq-ab12", value="2500.00")
    assert (r["asset_tag"], r["status"], r["value"], r["type_id"], r["branch_id"]) == ("EQ-AB12", "available", "2500.00", t["id"], branch_a["id"])
'''),
    dict(id="T-EQ-07-b", req="LIB-EQ-07", type="Error", input="Duplicate tag; inactive branch; tag `AB1`; value 0.99; `acquired_on` tomorrow; librarian creates", expected="`409 CONFLICT`; `409 BRANCH_INACTIVE`; `422` three times; `403`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-08-a", req="LIB-EQ-08", type="Normal", input="PATCH an available item: `serial_no`, `value`, `branch_id` B; then `status`, `asset_tag`, `type_id`", expected="200 with the new values; `422` three times", code='''
def TEST(client, admin, branch_a, branch_b):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    url = f"/api/v1/equipment-items/{it['id']}"
    r = ok(client.patch(url, headers=admin, json={"serial_no": "SN-NEW", "value": "1500.00", "branch_id": branch_b["id"]}))
    assert (r["serial_no"], r["value"], r["branch_id"]) == ("SN-NEW", "1500.00", branch_b["id"])
    for body in ({"status": "lost"}, {"asset_tag": "EQ-9999"}, {"type_id": etype(client, admin)["id"]}):
        assert client.patch(url, headers=admin, json=body).status_code == 422
'''),
    dict(id="T-EQ-08-b", req="LIB-EQ-08", type="Error", input="Item on loan: PATCH `branch_id`; PATCH `value`", expected="`409 INVALID_ITEM_STATUS`; value change 200", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    it = item(client, admin, etype(client, admin), branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], it["id"])
    url = f"/api/v1/equipment-items/{it['id']}"
    err(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}), 409, "INVALID_ITEM_STATUS")
    assert ok(client.patch(url, headers=admin, json={"value": "900.00"}))["value"] == "900.00"
'''),
    dict(id="T-EQ-08-c", req="LIB-EQ-08", type="Error", input="Only item of the type at A; reservation Tue 10:00 at A; move the item to B; then with a second item at A", expected="`409 ITEM_NEEDED_FOR_RESERVATION`; then 200", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    url = f"/api/v1/equipment-items/{it['id']}"
    err(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}), 409, "ITEM_NEEDED_FOR_RESERVATION")
    item(client, admin, t, branch_a)
    assert ok(client.patch(url, headers=admin, json={"branch_id": branch_b["id"]}))["branch_id"] == branch_b["id"]
'''),
    dict(id="T-EQ-09-a", req="LIB-EQ-09", type="Normal", input="Items EQ-0003 (serial `SN-XY`), EQ-0001, EQ-0002 (branch B); EQ-0001 lent; list and filters", expected="Order by tag; `q=sn-x` → EQ-0003; `branch_id` B → EQ-0002; `status=on_loan` → EQ-0001", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    t = etype(client, admin)
    item(client, admin, t, branch_a, tag="EQ-0003", serial_no="SN-XY")
    first = item(client, admin, t, branch_a, tag="EQ-0001")
    item(client, admin, t, branch_b, tag="EQ-0002")
    elend(client, librarian, member(client, librarian, branch_a)["id"], first["id"])
    tags = lambda **p: [x["asset_tag"] for x in items(get(client, librarian, "equipment-items", **p))]
    assert tags() == ["EQ-0001", "EQ-0002", "EQ-0003"]
    assert tags(q="sn-x") == ["EQ-0003"]
    assert tags(branch_id=branch_b["id"]) == ["EQ-0002"]
    assert tags(status="on_loan") == ["EQ-0001"]
'''),
    dict(id="T-EQ-09-b", req="LIB-EQ-09", type="Error", input="Member reads the item list and one item", expected="`403 FORBIDDEN` both", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get("/api/v1/equipment-items", headers=mh).status_code == 403
    assert client.get(f"/api/v1/equipment-items/{it['id']}", headers=mh).status_code == 403
'''),
    dict(id="T-EQ-10-a", req="LIB-EQ-10", type="Normal", input="Retire an available item; retire it again; `repair-done` on another available item", expected="`retired`; `409 INVALID_ITEM_STATUS` twice", code='''
def TEST(client, admin, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    assert ok(act(client, admin, f"equipment-items/{i1['id']}/retire"))["status"] == "retired"
    err(act(client, admin, f"equipment-items/{i1['id']}/retire"), 409, "INVALID_ITEM_STATUS")
    err(act(client, admin, f"equipment-items/{i2['id']}/repair-done"), 409, "INVALID_ITEM_STATUS")
'''),
    dict(id="T-EQ-10-b", req="LIB-EQ-10", type="Normal", input="Two items returned damaged (`in_repair`); librarian retires one; librarian marks it repaired; admin retires the other", expected="`403`; `available`; `retired`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    for it in (i1, i2):
        ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"], "damaged", "10.00"))
    assert act(client, librarian, f"equipment-items/{i1['id']}/retire").status_code == 403
    assert ok(act(client, librarian, f"equipment-items/{i1['id']}/repair-done"))["status"] == "available"
    assert ok(act(client, admin, f"equipment-items/{i2['id']}/retire"))["status"] == "retired"
'''),
    dict(id="T-EQ-10-c", req="LIB-EQ-10", type="Error", input="Only item of the type at A; reservation Tue 10:00; retire", expected="`409 ITEM_NEEDED_FOR_RESERVATION`; item stays `available`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    err(act(client, admin, f"equipment-items/{it['id']}/retire"), 409, "ITEM_NEEDED_FOR_RESERVATION")
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "available"
'''),
    # ---------------------------------------------------------------- training
    dict(id="T-EQ-11-a", req="LIB-EQ-11", type="Normal", input="Training for a type that requires it, completed 2026-11-02", expected="201; `valid_until` 2027-11-01", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    m = member(client, librarian, branch_a)
    r = ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    assert (r["member_id"], r["type_id"], r["completed_on"], r["valid_until"]) == (m["id"], t["id"], "2026-11-02", "2027-11-01")
'''),
    dict(id="T-EQ-11-b", req="LIB-EQ-11", type="Error", input="`completed_on` tomorrow; a type without training; the same training twice", expected="`422`; `409 TRAINING_NOT_REQUIRED`; 201 twice", code='''
def TEST(client, admin, librarian, branch_a):
    t, plain = etype(client, admin, training=True), etype(client, admin)
    m = member(client, librarian, branch_a)
    assert train(client, librarian, m["id"], t["id"], "2026-11-03").status_code == 422
    err(train(client, librarian, m["id"], plain["id"], "2026-11-02"), 409, "TRAINING_NOT_REQUIRED")
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
'''),
    dict(id="T-EQ-11-c", req="LIB-EQ-11", type="Boundary", input="Student trained 2025-11-03 (valid until 2026-11-02); lend Mon 2026-11-02, return; lend Tue", expected="Mon 201; Tue `409 TRAINING_REQUIRED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    assert ok(train(client, librarian, m["id"], t["id"], "2025-11-03"), 201)["valid_until"] == "2026-11-02"
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"]))
    at(clock, TUE, 9, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "TRAINING_REQUIRED")
'''),
    dict(id="T-EQ-11-d", req="LIB-EQ-11", type="Error", input="Member reads own trainings and those of another member", expected="200 with one record; `403 FORBIDDEN`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    mh = member_headers(client, m)
    assert len(items(get(client, mh, f"members/{m['id']}/equipment-trainings"))) == 1
    assert client.get(f"/api/v1/members/{other['id']}/equipment-trainings", headers=mh).status_code == 403
'''),
    # ---------------------------------------------------------------- lending
    dict(id="T-EQ-12-a", req="LIB-EQ-12", type="Normal", input="Librarian lends a charger (4 hours) on Tue 10:20", expected="201 `EquipmentLoanOut`: open, due 14:20, not extended, not overdue, accrued 0.00, asset tag and type code; item `on_loan`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin, code="CHG")
    it = item(client, admin, t, branch_a, tag="EQ-0042")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    r = elend(client, librarian, m["id"], it["id"])
    assert (r["status"], r["member_id"], r["item_id"], r["branch_id"], r["asset_tag"], r["type_id"], r["type_code"]) == ("open", m["id"], it["id"], branch_a["id"], "EQ-0042", t["id"], "CHG")
    assert same(r["loaned_at"], TUE, 10, 20) and same(r["due_at"], TUE, 14, 20)
    assert (r["extended"], r["overdue"], r["accrued_late_fee"], r["reservation_id"], r["returned_at"], r["late_hours"]) == (False, False, "0.00", None, None, None)
    assert r["lent_by"] is not None
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "on_loan"
'''),
    dict(id="T-EQ-12-b", req="LIB-EQ-12", type="Error", input="Both `item_id` and `reservation_id`; neither; a member lends", expected="`422`, `422`, `403`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    assert try_lend(client, librarian, m["id"], it["id"], reservation_id=1).status_code == 422
    assert try_lend(client, librarian, m["id"]).status_code == 422
    assert try_lend(client, member_headers(client, m), m["id"], it["id"]).status_code == 403
'''),
    dict(id="T-EQ-13-a", req="LIB-EQ-13", type="Error", input="Passive member; member whose membership ended (Tue 2027-11-02)", expected="`409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    p, m = member(client, librarian, branch_a), member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "MEMBER_PASSIVE")
    at(clock, "2027-11-02", 10, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "MEMBERSHIP_EXPIRED")
'''),
    dict(id="T-EQ-13-b", req="LIB-EQ-13", type="Error", input="Guest member", expected="`409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    err(try_lend(client, librarian, g["id"], it["id"]), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")
'''),
    dict(id="T-EQ-13-c", req="LIB-EQ-13", type="Boundary", input="Member with debt 50.00; member with debt 49.99", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"; 201", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m1, "50.00")
    debt(client, librarian, branch_a, m2, "49.99")
    assert err(try_lend(client, librarian, m1["id"], i1["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["total_debt"] == "50.00"
    ok(try_lend(client, librarian, m2["id"], i2["id"]), 201)
'''),
    dict(id="T-EQ-13-d", req="LIB-EQ-13", type="Normal", input="Type requires training: student without training; academic without training; the student after a training today", expected="`409 TRAINING_REQUIRED`; 201; 201", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    err(try_lend(client, librarian, s["id"], i1["id"]), 409, "TRAINING_REQUIRED")
    ok(try_lend(client, librarian, a["id"], i1["id"]), 201)
    ok(train(client, librarian, s["id"], t["id"], "2026-11-02"), 201)
    ok(try_lend(client, librarian, s["id"], i2["id"]), 201)
'''),
    dict(id="T-EQ-13-e", req="LIB-EQ-13", type="Boundary", input="Student with 2 open equipment loans; academic with 3 (type allows 3)", expected="Next loan: `409 EQUIPMENT_LIMIT_REACHED` with `details.limit` 2 and 3", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, max_open=3)
    its = [item(client, admin, t, branch_a) for _ in range(7)]
    s, a = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="academic")
    elend(client, librarian, s["id"], its[0]["id"]); elend(client, librarian, s["id"], its[1]["id"])
    assert err(try_lend(client, librarian, s["id"], its[2]["id"]), 409, "EQUIPMENT_LIMIT_REACHED")["details"]["limit"] == 2
    for it in its[3:6]:
        elend(client, librarian, a["id"], it["id"])
    assert err(try_lend(client, librarian, a["id"], its[6]["id"]), 409, "EQUIPMENT_LIMIT_REACHED")["details"]["limit"] == 3
'''),
    dict(id="T-EQ-13-f", req="LIB-EQ-13", type="Error", input="Type with `max_open_per_member` 1; student borrows a second item of it", expected="`409 TYPE_LIMIT_REACHED` with `details.limit` 1", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, max_open=1)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    elend(client, librarian, m["id"], i1["id"])
    assert err(try_lend(client, librarian, m["id"], i2["id"]), 409, "TYPE_LIMIT_REACHED")["details"]["limit"] == 1
'''),
    dict(id="T-EQ-13-g", req="LIB-EQ-13", type="Error", input="Item on loan to another member; item `in_repair`; item `retired`", expected="`409 ITEM_NOT_AVAILABLE` each", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    lent, broken, old = (item(client, admin, t, branch_a) for _ in range(3))
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m1["id"], lent["id"])
    ok(ret(client, librarian, elend(client, librarian, m1["id"], broken["id"])["id"], "damaged", "0.00"))
    ok(act(client, admin, f"equipment-items/{old['id']}/retire"))
    for it in (lent, broken, old):
        err(try_lend(client, librarian, m2["id"], it["id"]), 409, "ITEM_NOT_AVAILABLE")
'''),
    dict(id="T-EQ-13-h", req="LIB-EQ-13", type="Error", input="Passive member, inactive type: lend on Saturday; then on Monday 2026-11-09 10:00", expected="`DESK_CLOSED`; then `TYPE_INACTIVE` (desk before type before member)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    p = member(client, librarian, branch_a)
    deactivate_member(client, librarian, p["id"])
    ok(client.patch(f"/api/v1/equipment-types/{t['id']}", headers=admin, json={"is_active": False}))
    at(clock, SAT, 10, 0)
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "DESK_CLOSED")
    at(clock, "2026-11-09", 10, 0)
    err(try_lend(client, librarian, p["id"], it["id"]), 409, "TYPE_INACTIVE")
'''),
    dict(id="T-EQ-14-a", req="LIB-EQ-14", type="Boundary", input="Charger lent Tue 09:00 (due 13:00); the member borrows a book at 13:15 and another at 13:16", expected="201; then `409 MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    c1, c2 = (add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"]) for _ in range(2))
    at(clock, TUE, 9, 0)
    elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 15)
    lend(client, librarian, m["id"], c1["id"])
    at(clock, TUE, 13, 16)
    assert error_code(lend(client, librarian, m["id"], c2["id"], expect=409)) == "MEMBER_HAS_OVERDUE"
'''),
    dict(id="T-EQ-14-b", req="LIB-EQ-14", type="Normal", input="Charger (10.00 per hour) lent Tue 09:00, due 13:00; balance at 18:00", expected="Loan: overdue, accrued 50.00; balance `accrued_late_fees` and `total_debt` 50.00, `blocked` true", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin, fee="10.00"), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 18, 0)
    r = get(client, librarian, f"equipment-loans/{loan['id']}")
    assert (r["overdue"], r["accrued_late_fee"]) == (True, "50.00")
    b = balance(client, librarian, m["id"])
    assert (b["outstanding_fees"], b["accrued_late_fees"], b["total_debt"], b["blocked"]) == ("0.00", "50.00", "50.00", True)
'''),
    dict(id="T-EQ-14-c", req="LIB-EQ-14", type="Error", input="Book lent Mon 2026-11-02 (due 2026-11-16); equipment lent on Tue 2026-11-17", expected="`409 MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    lend(client, librarian, m["id"], add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])["id"])
    at(clock, "2026-11-17", 10, 0)
    err(try_lend(client, librarian, m["id"], it["id"]), 409, "MEMBER_HAS_OVERDUE")
'''),
    dict(id="T-EQ-15-a", req="LIB-EQ-15", type="Normal", input="Charger (4 hours) lent Tue 10:20:30; another lent 17:30", expected="Due 14:20:30; due 20:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin, period=4)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20, 30)
    assert same(elend(client, librarian, m1["id"], i1["id"])["due_at"], TUE, 14, 20, 30)
    at(clock, TUE, 17, 30)
    assert same(elend(client, librarian, m2["id"], i2["id"])["due_at"], TUE, 20, 0)
'''),
    dict(id="T-EQ-15-b", req="LIB-EQ-15", type="Normal", input="Laptop (3 working days) lent Wed 2026-10-28 15:00", expected="Due Tue 2026-11-03 17:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin, unit="working_days", period=3), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2026-10-28", 15, 0)
    assert same(elend(client, librarian, m["id"], it["id"])["due_at"], TUE, 17, 0)
'''),
    dict(id="T-EQ-15-c", req="LIB-EQ-15", type="Normal", input="Type of 1 working day lent Fri 2026-11-06 19:00", expected="Due Mon 2026-11-09 17:00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin, unit="working_days", period=1), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, FRI, 19, 0)
    assert same(elend(client, librarian, m["id"], it["id"])["due_at"], "2026-11-09", 17, 0)
'''),
    dict(id="T-EQ-16-a", req="LIB-EQ-16", type="Boundary", input="Loan due Tue 14:20 (5.00 per hour); read at 14:35:00 and at 14:35:01", expected="Not overdue, accrued 0.00; then overdue, accrued 5.00", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-17-a", req="LIB-EQ-17", type="Normal", input="Loan L2 (M2) Tue 10:00, then L1 (M1) Tue 09:00 (due 13:00); at 14:00 L2 returned; list and filters", expected="Order L1, L2; `member_id` M2 → L2; `overdue=true` → L1; `status=returned` → L2", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    l2 = elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 9, 0)
    l1 = elend(client, librarian, m1["id"], i1["id"])
    at(clock, TUE, 14, 0)
    ok(ret(client, librarian, l2["id"]))
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "equipment-loans", **p))]
    assert ids() == [l1["id"], l2["id"]]
    assert ids(member_id=m2["id"]) == [l2["id"]]
    assert ids(overdue="true") == [l1["id"]]
    assert ids(status="returned") == [l2["id"]]
'''),
    dict(id="T-EQ-17-b", req="LIB-EQ-17", type="Error", input="Member reads own loan, a loan of another member, the general list, own list, list of another member", expected="200; 403; 403; 200 with 1 item; 403", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-18-a", req="LIB-EQ-18", type="Normal", input="One item; member reserved Tue 10:00; at 09:50 the librarian lends the item by `item_id`", expected="201 with `reservation_id`; reservation `collected` with this `loan_id`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 50)
    loan = elend(client, librarian, m["id"], it["id"])
    assert loan["reservation_id"] == res["id"]
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["loan_id"]) == ("collected", loan["id"])
'''),
    dict(id="T-EQ-18-b", req="LIB-EQ-18", type="Normal", input="Two items; member reserved Tue 10:00; at 09:40 the member borrows by `item_id`", expected="201 with `reservation_id` null; reservation stays `booked`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, _ = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 40)
    assert elend(client, librarian, m["id"], i1["id"])["reservation_id"] is None
    assert get(client, librarian, f"equipment-reservations/{res['id']}")["status"] == "booked"
'''),
    # ---------------------------------------------------------------- extension, return, loss
    dict(id="T-EQ-19-a", req="LIB-EQ-19", type="Normal", input="Charger lent Tue 10:20 (due 14:20); the member extends at 13:00; extends again", expected="200, due 18:20, `extended` true; then `409 EXTENSION_LIMIT_REACHED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 0)
    mh = member_headers(client, m)
    r = ok(act(client, mh, f"equipment-loans/{loan['id']}/extend"))
    assert same(r["due_at"], TUE, 18, 20) and r["extended"] is True
    err(act(client, mh, f"equipment-loans/{loan['id']}/extend"), 409, "EXTENSION_LIMIT_REACHED")
'''),
    dict(id="T-EQ-19-b", req="LIB-EQ-19", type="Boundary", input="Loan due 17:30 extended at 14:00; loan lent 16:00 (due 20:00) extended", expected="Due 20:00; `409 EXTENSION_NOT_POSSIBLE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-19-c", req="LIB-EQ-19", type="Boundary", input="Two loans due Tue 14:20; extend one at 14:35:00, the other at 14:35:01", expected="200 (due 18:20); `409 LOAN_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 14, 35, 0)
    assert same(ok(act(client, librarian, f"equipment-loans/{l1['id']}/extend"))["due_at"], TUE, 18, 20)
    at(clock, TUE, 14, 35, 1)
    err(act(client, librarian, f"equipment-loans/{l2['id']}/extend"), 409, "LOAN_OVERDUE")
'''),
    dict(id="T-EQ-19-d", req="LIB-EQ-19", type="Error", input="One charger; M2 reserved Tue 16:00; M1 borrows at 10:20 (due 14:20) and extends at 13:00", expected="`409 ITEM_NEEDED_FOR_RESERVATION`; due stays 14:20", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m2, TUE, 16)
    at(clock, TUE, 10, 20)
    loan = elend(client, librarian, m1["id"], it["id"])
    at(clock, TUE, 13, 0)
    err(act(client, librarian, f"equipment-loans/{loan['id']}/extend"), 409, "ITEM_NEEDED_FOR_RESERVATION")
    assert same(get(client, librarian, f"equipment-loans/{loan['id']}")["due_at"], TUE, 14, 20)
'''),
    dict(id="T-EQ-19-e", req="LIB-EQ-19", type="Normal", input="Laptop (3 working days) lent Tue 2026-11-03 10:00 (due Fri 17:00); extended Thu; returned; extended again", expected="Due Wed 2026-11-11 17:00; then `409 LOAN_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin, unit="working_days", period=3), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    assert same(loan["due_at"], FRI, 17, 0)
    at(clock, "2026-11-05", 10, 0)
    assert same(ok(act(client, librarian, f"equipment-loans/{loan['id']}/extend"))["due_at"], "2026-11-11", 17, 0)
    ok(ret(client, librarian, loan["id"]))
    err(act(client, librarian, f"equipment-loans/{loan['id']}/extend"), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-EQ-20-a", req="LIB-EQ-20", type="Normal", input="Loan Tue 10:00 returned `good` at 13:00; returned again", expected="200: `returned`, `returned_at` 13:00, `late_hours` 0, `received_by` set; item `available`; no fee; then `409 LOAN_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 13, 0)
    r = ok(ret(client, librarian, loan["id"]))
    assert (r["status"], r["late_hours"], r["return_condition"]) == ("returned", 0, "good")
    assert same(r["returned_at"], TUE, 13, 0) and r["received_by"] is not None
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "available"
    assert member_fees(client, librarian, m["id"])["total"] == 0
    err(ret(client, librarian, loan["id"]), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-EQ-20-b", req="LIB-EQ-20", type="Normal", input="Charger lent Fri 16:00 (due 20:00), returned Saturday 10:00 (desk closed)", expected="200; `late_hours` 14; late fee 70.00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    at(clock, FRI, 16, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, SAT, 10, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 14
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "70.00")]
'''),
    dict(id="T-EQ-21-a", req="LIB-EQ-21", type="Normal", input="Item (value 1000.00) returned `damaged` with `damage_fee` 300.00", expected="Item `in_repair`; one `equipment_damage_fee` 300.00 with `equipment_loan_id`, `loan_id` null", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    assert ok(ret(client, librarian, loan["id"], "damaged", "300.00"))["return_condition"] == "damaged"
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "in_repair"
    fees = items(member_fees(client, librarian, m["id"]))
    assert [(f["kind"], f["amount"], f["equipment_loan_id"], f["loan_id"]) for f in fees] == [("equipment_damage_fee", "300.00", loan["id"], None)]
'''),
    dict(id="T-EQ-21-b", req="LIB-EQ-21", type="Error", input="`damaged` without fee; `good` with fee 1.00; `damaged` 1000.01 (value 1000.00); `damaged` 0.00", expected="`422`; `422`; `409 DAMAGE_FEE_EXCEEDS_VALUE`; 200 without fee, item `in_repair`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    assert ret(client, librarian, loan["id"], "damaged").status_code == 422
    assert ret(client, librarian, loan["id"], "good", "1.00").status_code == 422
    err(ret(client, librarian, loan["id"], "damaged", "1000.01"), 409, "DAMAGE_FEE_EXCEEDS_VALUE")
    ok(ret(client, librarian, loan["id"], "damaged", "0.00"))
    assert member_fees(client, librarian, m["id"])["total"] == 0
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "in_repair"
'''),
    dict(id="T-EQ-22-a", req="LIB-EQ-22", type="Boundary", input="Two loans due Tue 14:20; returned at 14:35 and at 14:36", expected="`late_hours` 0 (no fee) and 1", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 14, 35)
    assert ok(ret(client, librarian, l1["id"]))["late_hours"] == 0
    at(clock, TUE, 14, 36)
    assert ok(ret(client, librarian, l2["id"]))["late_hours"] == 1
    assert member_fees(client, librarian, m1["id"])["total"] == 0
'''),
    dict(id="T-EQ-22-b", req="LIB-EQ-22", type="Boundary", input="Two loans due Tue 14:20; returned at 15:20 and at 15:21", expected="`late_hours` 1 and 2", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, TUE, 10, 20)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    at(clock, TUE, 15, 20)
    assert ok(ret(client, librarian, l1["id"]))["late_hours"] == 1
    at(clock, TUE, 15, 21)
    assert ok(ret(client, librarian, l2["id"]))["late_hours"] == 2
'''),
    dict(id="T-EQ-22-c", req="LIB-EQ-22", type="Normal", input="Charger (5.00 per hour, value 1000.00) lent Fri 16:00 (due 20:00), returned Mon 2026-11-09 09:00", expected="`late_hours` 61 (nights and weekend count); fee 200.00 (cap)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    at(clock, FRI, 16, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, "2026-11-09", 9, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 61
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "200.00")]
'''),
    dict(id="T-EQ-23-a", req="LIB-EQ-23", type="Normal", input="Type 2 hours, 25.00 per hour; item value 30,000.00; lent Tue 09:00 (due 11:00), returned Wed 17:00", expected="`late_hours` 30; `equipment_late_fee` 750.00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin, period=2, fee="25.00"), branch_a, value="30000.00")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, WED, 17, 0)
    assert ok(ret(client, librarian, loan["id"]))["late_hours"] == 30
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "750.00")]
'''),
    dict(id="T-EQ-23-b", req="LIB-EQ-23", type="Boundary", input="Same type: value 30,000.00 returned 300 hours late (Sun 2026-11-15 23:00); value 333.33 at 5.00 per hour returned 20 hours late", expected="6000.00 (20 % cap); 66.67 (cap 66.666 rounded half up)", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-24-a", req="LIB-EQ-24", type="Normal", input="Loan Tue 09:00 (due 13:00, 5.00 per hour, value 1000.00) reported lost at 15:00", expected="`lost`, `returned_at` null, `late_hours` 2; fees `equipment_late_fee` 10.00 and `equipment_lost` 1000.00; item `lost`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a, value="1000.00")
    m = member(client, librarian, branch_a)
    at(clock, TUE, 9, 0)
    loan = elend(client, librarian, m["id"], it["id"])
    at(clock, TUE, 15, 0)
    r = ok(act(client, librarian, f"equipment-loans/{loan['id']}/report-lost"))
    assert (r["status"], r["returned_at"], r["late_hours"]) == ("lost", None, 2)
    assert fees_of(client, librarian, m["id"]) == [("equipment_late_fee", "10.00"), ("equipment_lost", "1000.00")]
    assert get(client, librarian, f"equipment-items/{it['id']}")["status"] == "lost"
'''),
    dict(id="T-EQ-24-b", req="LIB-EQ-24", type="Error", input="Loan reported lost before its due time; reported lost again; a returned loan reported lost", expected="Only `equipment_lost`; `409 LOAN_NOT_OPEN` twice", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, i2 = item(client, admin, t, branch_a, value="800.00"), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    l1, l2 = elend(client, librarian, m["id"], i1["id"]), elend(client, librarian, m["id"], i2["id"])
    ok(act(client, librarian, f"equipment-loans/{l1['id']}/report-lost"))
    assert fees_of(client, librarian, m["id"]) == [("equipment_lost", "800.00")]
    err(act(client, librarian, f"equipment-loans/{l1['id']}/report-lost"), 409, "LOAN_NOT_OPEN")
    ok(ret(client, librarian, l2["id"]))
    err(act(client, librarian, f"equipment-loans/{l2['id']}/report-lost"), 409, "LOAN_NOT_OPEN")
'''),
    dict(id="T-EQ-25-a", req="LIB-EQ-25", type="Normal", input="Equipment damage fee 30.00; payment 10.00; admin waives the fee", expected="Fee paid 10.00, outstanding 20.00, balance 20.00; after waiving `waived`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"], "damaged", "30.00"))
    pay(client, librarian, m["id"], "10.00")
    fee = items(member_fees(client, librarian, m["id"]))[0]
    assert (fee["paid_amount"], fee["outstanding"], fee["status"]) == ("10.00", "20.00", "open")
    assert balance(client, librarian, m["id"])["outstanding_fees"] == "20.00"
    assert waive(client, admin, fee["id"])["status"] == "waived"
'''),
    dict(id="T-EQ-25-b", req="LIB-EQ-25", type="Normal", input="A book damage fee and an equipment damage fee; `GET /api/v1/fees?kind=equipment_damage_fee`", expected="Only the equipment fee", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m, "5.00")
    loan = elend(client, librarian, m["id"], it["id"])
    ok(ret(client, librarian, loan["id"], "damaged", "7.00"))
    rows = items(get(client, librarian, "fees", kind="equipment_damage_fee"))
    assert [(f["amount"], f["equipment_loan_id"]) for f in rows] == [("7.00", loan["id"])]
'''),
    # ---------------------------------------------------------------- reservations
    dict(id="T-EQ-26-a", req="LIB-EQ-26", type="Normal", input="Member reserves a charger (4 hours) for Tue 10:00", expected="201: `booked`, own `member_id`, `ends_at` 14:00, `loan_id` and `closed_at` null", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    r = ok(try_reserve(client, member_headers(client, m), t["id"], branch_a["id"], ts(TUE, 10)), 201)
    assert (r["status"], r["member_id"], r["type_id"], r["branch_id"], r["loan_id"], r["closed_at"]) == ("booked", m["id"], t["id"], branch_a["id"], None, None)
    assert same(r["starts_at"], TUE, 10, 0) and same(r["ends_at"], TUE, 14, 0)
'''),
    dict(id="T-EQ-26-b", req="LIB-EQ-26", type="Error", input="Member sends `member_id`; librarian without `member_id`; start 10:15; start 10:00:30", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10), member_id=m["id"]).status_code == 422
    assert try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10)).status_code == 422
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10, 15)).status_code == 422
    assert try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10, 0, 30)).status_code == 422
'''),
    dict(id="T-EQ-26-c", req="LIB-EQ-26", type="Normal", input="Librarian reserves a laptop (3 working days) for a member, Tue 10:00", expected="201 for that member; `ends_at` Fri 2026-11-06 17:00", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, unit="working_days", period=3)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    r = reserve(client, librarian, t, branch_a, m, TUE, 10)
    assert r["member_id"] == m["id"] and same(r["ends_at"], FRI, 17, 0)
'''),
    dict(id="T-EQ-27-a", req="LIB-EQ-27", type="Boundary", input="One charger; M1 reserved Tue 14:30 (holds from 14:15); M2 borrows at 10:01, then at 10:00", expected="`409 ITEM_NEEDED_FOR_RESERVATION`; then 201 (due 14:00, needed until 14:15)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 14, 30)
    at(clock, TUE, 10, 1)
    err(try_lend(client, librarian, m2["id"], it["id"]), 409, "ITEM_NEEDED_FOR_RESERVATION")
    at(clock, TUE, 10, 0)
    ok(try_lend(client, librarian, m2["id"], it["id"]), 201)
'''),
    dict(id="T-EQ-27-b", req="LIB-EQ-27", type="Normal", input="Two chargers; M1 Tue 10:00, M2 Tue 12:00; M3 Tue 13:00, then Tue 14:30", expected="M1, M2 201; M3 13:00 `409 NO_EQUIPMENT_AVAILABLE`; M3 14:30 201", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2, m3 = (member(client, librarian, branch_a) for _ in range(3))
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    reserve(client, librarian, t, branch_a, m2, TUE, 12)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 13), member_id=m3["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    reserve(client, librarian, t, branch_a, m3, TUE, 14, 30)
'''),
    dict(id="T-EQ-27-c", req="LIB-EQ-27", type="Normal", input="One charger lent Mon 09:00 (due 13:00) and not returned; at 14:00 another member reserves Tue 10:00", expected="`409 NO_EQUIPMENT_AVAILABLE` with `details.next_free_at` null (an overdue loan needs its item until returned)", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m1["id"], it["id"])
    at(clock, MON, 14, 0)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    assert e["details"]["next_free_at"] is None
'''),
    dict(id="T-EQ-27-d", req="LIB-EQ-27", type="Normal", input="Two chargers, one `in_repair`; M1 and M2 reserve Tue 10:00", expected="M1 201; M2 `409 NO_EQUIPMENT_AVAILABLE`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    broken = item(client, admin, t, branch_a)
    m0, m1, m2 = (member(client, librarian, branch_a) for _ in range(3))
    ok(ret(client, librarian, elend(client, librarian, m0["id"], broken["id"])["id"], "damaged", "0.00"))
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
'''),
    dict(id="T-EQ-28-a", req="LIB-EQ-28", type="Error", input="Reservation for a passive member; for a guest", expected="`409 MEMBER_PASSIVE`; `409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    p, g = member(client, librarian, branch_a), member(client, librarian, branch_a, membership_type="guest")
    deactivate_member(client, librarian, p["id"])
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=p["id"]), 409, "MEMBER_PASSIVE")
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=g["id"]), 409, "EQUIPMENT_NOT_ALLOWED_FOR_TYPE")
'''),
    dict(id="T-EQ-28-b", req="LIB-EQ-28", type="Boundary", input="Membership valid until 2027-11-01; on 2027-10-25 reserve for 2027-11-02 10:00 and for 2027-11-01 10:00", expected="`409 MEMBERSHIP_EXPIRED`; 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2027-10-25", 9, 0)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2027-11-02", 10), member_id=m["id"]), 409, "MEMBERSHIP_EXPIRED")
    reserve(client, librarian, t, branch_a, m, "2027-11-01", 10)
'''),
    dict(id="T-EQ-28-c", req="LIB-EQ-28", type="Error", input="Member with debt 50.00 reserves", expected="`409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` \"50.00\"", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    debt(client, librarian, branch_a, m, "50.00")
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 10), member_id=m["id"]), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"
'''),
    dict(id="T-EQ-28-d", req="LIB-EQ-28", type="Boundary", input="Student trained 2025-11-05 (valid until 2026-11-04); reserves Wed 2026-11-04 10:00 and Thu 2026-11-05 10:00", expected="201; `409 TRAINING_REQUIRED`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2025-11-05"), 201)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-05", 10), member_id=m["id"]), 409, "TRAINING_REQUIRED")
'''),
    dict(id="T-EQ-28-e", req="LIB-EQ-28", type="Boundary", input="Starts Sat 10:00; Tue 20:00; Tue 07:30; Tue 19:30", expected="`409 DESK_CLOSED` three times; Tue 19:30 201 with `ends_at` 20:00", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    for day, hh, mm in ((SAT, 10, 0), (TUE, 20, 0), (TUE, 7, 30)):
        err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(day, hh, mm), member_id=m["id"]), 409, "DESK_CLOSED")
    assert same(reserve(client, librarian, t, branch_a, m, TUE, 19, 30)["ends_at"], TUE, 20, 0)
'''),
    dict(id="T-EQ-28-f", req="LIB-EQ-28", type="Boundary", input="Now Mon 09:00: reserve Mon 09:30; at 09:01 another member reserves Mon 09:30", expected="201; `409 RESERVATION_TOO_SOON`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    at(clock, MON, 9, 0)
    reserve(client, librarian, t, branch_a, m1, MON, 9, 30)
    at(clock, MON, 9, 1)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(MON, 9, 30), member_id=m2["id"]), 409, "RESERVATION_TOO_SOON")
'''),
    dict(id="T-EQ-28-g", req="LIB-EQ-28", type="Boundary", input="Today Mon 2026-11-02: reserve Mon 2026-11-16 19:30; Tue 2026-11-17 08:00", expected="201; `409 RESERVATION_TOO_FAR_AHEAD` with `details.latest_date` 2026-11-16", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, "2026-11-16", 19, 30)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-17", 8), member_id=m["id"]), 409, "RESERVATION_TOO_FAR_AHEAD")
    assert e["details"]["latest_date"] == "2026-11-16"
'''),
    dict(id="T-EQ-28-h", req="LIB-EQ-28", type="Error", input="Student with reservations Tue 10:00 and Wed 10:00 reserves Thu 10:00", expected="`409 EQUIPMENT_RESERVATION_LIMIT_REACHED`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, TUE, 10)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts("2026-11-05", 10), member_id=m["id"]), 409, "EQUIPMENT_RESERVATION_LIMIT_REACHED")
'''),
    dict(id="T-EQ-28-i", req="LIB-EQ-28", type="Boundary", input="Two chargers; member reserved Tue 10:00 (until 14:00); reserves the same type Tue 13:30, then Tue 14:00", expected="`409 DUPLICATE_EQUIPMENT_RESERVATION`; 201", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, TUE, 10)
    err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 13, 30), member_id=m["id"]), 409, "DUPLICATE_EQUIPMENT_RESERVATION")
    reserve(client, librarian, t, branch_a, m, TUE, 14)
'''),
    dict(id="T-EQ-28-j", req="LIB-EQ-28", type="Normal", input="One charger; M1 reserved Tue 10:00 (holds 09:45–14:00); M2 reserves Tue 12:00", expected="`409 NO_EQUIPMENT_AVAILABLE` with `details.next_free_at` Tue 14:30", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    e = err(try_reserve(client, librarian, t["id"], branch_a["id"], ts(TUE, 12), member_id=m2["id"]), 409, "NO_EQUIPMENT_AVAILABLE")
    assert same(e["details"]["next_free_at"], TUE, 14, 30)
'''),
    dict(id="T-EQ-29-a", req="LIB-EQ-29", type="Boundary", input="Items EQ-0002 and EQ-0001; member reserved Tue 10:00; collected with `reservation_id` at 09:45", expected="201: item EQ-0001, `reservation_id` set, due 13:45; reservation `collected` with `loan_id`, `closed_at` 09:45", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a, tag="EQ-0002"); item(client, admin, t, branch_a, tag="EQ-0001")
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    at(clock, TUE, 9, 45)
    loan = ok(try_lend(client, librarian, m["id"], reservation_id=res["id"]), 201)
    assert (loan["asset_tag"], loan["reservation_id"]) == ("EQ-0001", res["id"]) and same(loan["due_at"], TUE, 13, 45)
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["loan_id"]) == ("collected", loan["id"]) and same(r["closed_at"], TUE, 9, 45)
'''),
    dict(id="T-EQ-29-b", req="LIB-EQ-29", type="Boundary", input="Reservation Tue 10:00 collected at 09:44, at 10:30:01, then at 10:30", expected="`409 RESERVATION_NOT_READY`; `409 RESERVATION_EXPIRED`; 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-29-c", req="LIB-EQ-29", type="Error", input="M2 collects M1's reservation; M1 cancels and then collects", expected="`409 RESERVATION_OF_OTHER_MEMBER`; `409 RESERVATION_NOT_ACTIVE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 10, 0)
    err(try_lend(client, librarian, m2["id"], reservation_id=res["id"]), 409, "RESERVATION_OF_OTHER_MEMBER")
    ok(act(client, member_headers(client, m1), f"equipment-reservations/{res['id']}/cancel"))
    err(try_lend(client, librarian, m1["id"], reservation_id=res["id"]), 409, "RESERVATION_NOT_ACTIVE")
'''),
    dict(id="T-EQ-29-d", req="LIB-EQ-29", type="Error", input="One charger lent to M0 Mon 09:00 (due 13:00, not returned); M1 reserved Tue 10:00 on Mon; M1 collects Tue 09:50", expected="`409 ITEM_NOT_AVAILABLE`; reservation stays `booked`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m0, m1 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    elend(client, librarian, m0["id"], it["id"])
    res = reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 9, 50)
    err(try_lend(client, librarian, m1["id"], reservation_id=res["id"]), 409, "ITEM_NOT_AVAILABLE")
    assert get(client, librarian, f"equipment-reservations/{res['id']}")["status"] == "booked"
'''),
    dict(id="T-EQ-30-a", req="LIB-EQ-30", type="Normal", input="Member cancels own reservation; cancels again", expected="200 `cancelled`, `member_request`, `closed_at` set, no notification; then `409 RESERVATION_NOT_ACTIVE`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    mh = member_headers(client, m)
    r = ok(act(client, mh, f"equipment-reservations/{res['id']}/cancel"))
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "member_request") and r["closed_at"] is not None
    assert notes(client, librarian, m["id"], "equipment_reservation_cancelled") == []
    err(act(client, mh, f"equipment-reservations/{res['id']}/cancel"), 409, "RESERVATION_NOT_ACTIVE")
'''),
    dict(id="T-EQ-30-b", req="LIB-EQ-30", type="Normal", input="Another member cancels M's reservation; the librarian cancels it", expected="`403 FORBIDDEN`; then `staff_request` and one `equipment_reservation_cancelled` notification for M", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    assert act(client, member_headers(client, other), f"equipment-reservations/{res['id']}/cancel").status_code == 403
    assert ok(act(client, librarian, f"equipment-reservations/{res['id']}/cancel"))["cancel_reason"] == "staff_request"
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1
'''),
    dict(id="T-EQ-31-a", req="LIB-EQ-31", type="Boundary", input="Reservation Tue 10:00; process at 10:30:00 and at 10:30:01", expected="`expired_reservations` 0, then 1; reservation `expired` with `closed_at` 10:30:01", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    res = reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    at(clock, TUE, 10, 30, 0)
    assert process(client, librarian)["expired_reservations"] == 0
    at(clock, TUE, 10, 30, 1)
    assert process(client, librarian)["expired_reservations"] == 1
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert r["status"] == "expired" and same(r["closed_at"], TUE, 10, 30, 1)
'''),
    dict(id="T-EQ-31-b", req="LIB-EQ-31", type="Normal", input="One charger; M1 reserved Tue 10:00; at 10:31 (not processed) M2 borrows it; at 10:40 process", expected="201 for M2; then 1 expired and one `equipment_reservation_expired` notification for M1", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m1, TUE, 10)
    at(clock, TUE, 10, 31)
    ok(try_lend(client, librarian, m2["id"], it["id"]), 201)
    at(clock, TUE, 10, 40)
    assert process(client, librarian)["expired_reservations"] == 1
    assert len(notes(client, librarian, m1["id"], "equipment_reservation_expired")) == 1
'''),
    dict(id="T-EQ-32-a", req="LIB-EQ-32", type="Normal", input="Loan due Tue 13:00; process at 14:00 twice; process Wed 09:00", expected="`{expired_reservations: 0, overdue_notices: 1}`, then 0 notices; Wed 1; member has 2 `equipment_overdue` notifications", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-EQ-33-a", req="LIB-EQ-33", type="Normal", input="Two chargers; reservation Tue 10:00 (holds 09:45–14:00); availability for Tue", expected="Capacity 2; 24 slots 08:00…19:30; free 2 at 09:00, 1 at 09:30 and 13:30, 2 at 14:00", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    r = get(client, librarian, f"equipment-types/{t['id']}/availability", branch_id=branch_a["id"], date=TUE)
    assert (r["type_id"], r["branch_id"], r["date"], r["capacity"]) == (t["id"], branch_a["id"], TUE, 2)
    free = {s["start"]: s["free"] for s in r["slots"]}
    assert len(r["slots"]) == 24 and r["slots"][0]["start"] == "08:00" and r["slots"][-1]["start"] == "19:30"
    assert (free["09:00"], free["09:30"], free["13:30"], free["14:00"]) == (2, 1, 1, 2)
'''),
    dict(id="T-EQ-33-b", req="LIB-EQ-33", type="Normal", input="Member reads availability for Saturday", expected="200; capacity 1; `slots` empty", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    mh = member_headers(client, member(client, librarian, branch_a))
    r = get(client, mh, f"equipment-types/{t['id']}/availability", branch_id=branch_a["id"], date=SAT)
    assert (r["capacity"], r["slots"]) == (1, [])
'''),
    dict(id="T-EQ-34-a", req="LIB-EQ-34", type="Normal", input="Reservations R1 (M1 Wed 10:00), R2 (M2 Tue 12:00), R3 (M1 Tue 08:00); R2 cancelled; list and filters", expected="Order R3, R2, R1; `from`=`to`=Wed → R1; `status=cancelled` → R2; `member_id` M1 → R3, R1", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m1, m2 = member(client, librarian, branch_a), member(client, librarian, branch_a)
    r1 = reserve(client, librarian, t, branch_a, m1, WED, 10)
    r2 = reserve(client, librarian, t, branch_a, m2, TUE, 12)
    r3 = reserve(client, librarian, t, branch_a, m1, TUE, 8)
    ok(act(client, librarian, f"equipment-reservations/{r2['id']}/cancel"))
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "equipment-reservations", **p))]
    assert ids() == [r3["id"], r2["id"], r1["id"]]
    assert ids(**{"from": WED, "to": WED}) == [r1["id"]]
    assert ids(status="cancelled") == [r2["id"]]
    assert ids(member_id=m1["id"]) == [r3["id"], r1["id"]]
'''),
    dict(id="T-EQ-34-b", req="LIB-EQ-34", type="Error", input="Member reads the general list, own list, own reservation, a reservation of another member", expected="403; 200 with 1 item; 200; 403", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a); item(client, admin, t, branch_a)
    m, other = member(client, librarian, branch_a), member(client, librarian, branch_a)
    own, foreign = reserve(client, librarian, t, branch_a, m, TUE, 10), reserve(client, librarian, t, branch_a, other, TUE, 10)
    mh = member_headers(client, m)
    assert client.get("/api/v1/equipment-reservations", headers=mh).status_code == 403
    assert get(client, mh, f"members/{m['id']}/equipment-reservations")["total"] == 1
    assert client.get(f"/api/v1/equipment-reservations/{own['id']}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/equipment-reservations/{foreign['id']}", headers=mh).status_code == 403
'''),
    # ---------------------------------------------------------------- effects on other modules
    dict(id="T-EQ-35-a", req="LIB-EQ-35", type="Error", input="Member with an open equipment loan (no book loans) is deactivated", expected="`409 MEMBER_HAS_OPEN_LOANS`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    elend(client, librarian, m["id"], it["id"])
    assert error_code(deactivate_member(client, librarian, m["id"], expect=409)) == "MEMBER_HAS_OPEN_LOANS"
'''),
    dict(id="T-EQ-35-b", req="LIB-EQ-35", type="Normal", input="Member with a booked reservation is deactivated", expected="Reservation `cancelled` with `member_deactivated`; one `equipment_reservation_cancelled` notification", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    res = reserve(client, librarian, t, branch_a, m, TUE, 10)
    deactivate_member(client, librarian, m["id"])
    r = get(client, librarian, f"equipment-reservations/{res['id']}")
    assert (r["status"], r["cancel_reason"]) == ("cancelled", "member_deactivated")
    assert len(notes(client, librarian, m["id"], "equipment_reservation_cancelled")) == 1
'''),
    dict(id="T-EQ-36-a", req="LIB-EQ-36", type="Error", input="Branch with one equipment item is deactivated; after the item is retired", expected="`409 BRANCH_IN_USE`; then 200", code='''
def TEST(client, admin):
    br = create_branch(client, admin, "QQ")
    it = item(client, admin, etype(client, admin), br)
    err(client.patch(f"/api/v1/branches/{br['id']}", headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(act(client, admin, f"equipment-items/{it['id']}/retire"))
    deactivate_branch(client, admin, br["id"])
'''),
    dict(id="T-EQ-37-a", req="LIB-EQ-37", type="Normal", input="Member reserved Wed 10:00 and borrowed Tue 09:00 (due 13:00); summary at 14:00", expected="`equipment` = `{open_loans: 1, overdue_loans: 1, booked_reservations: 1}`; `borrowing.eligible` false with `MEMBER_HAS_OVERDUE`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    t = etype(client, admin)
    i1, _ = item(client, admin, t, branch_a), item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    reserve(client, librarian, t, branch_a, m, WED, 10)
    at(clock, TUE, 9, 0)
    elend(client, librarian, m["id"], i1["id"])
    at(clock, TUE, 14, 0)
    s = get(client, librarian, f"members/{m['id']}/summary")
    assert s["equipment"] == {"open_loans": 1, "overdue_loans": 1, "booked_reservations": 1}
    assert s["borrowing"]["eligible"] is False and "MEMBER_HAS_OVERDUE" in s["borrowing"]["reasons"]
'''),
    dict(id="T-EQ-38-a", req="LIB-EQ-38", type="Normal", input="Item EQ-0777 lent and returned", expected="One `equipment_loan_created` and one `equipment_loan_returned` notification with `equipment_loan_id`; messages contain `EQ-0777`", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a, tag="EQ-0777")
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    ok(ret(client, librarian, loan["id"]))
    for type_ in ("equipment_loan_created", "equipment_loan_returned"):
        rows = notes(client, librarian, m["id"], type_)
        assert len(rows) == 1 and rows[0]["equipment_loan_id"] == loan["id"] and "EQ-0777" in rows[0]["message"]
'''),
    dict(id="T-EQ-38-b", req="LIB-EQ-38", type="Normal", input="Member reserves, cancels own reservation, borrows and extends", expected="The member's notifications: only `equipment_loan_created`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    mh = member_headers(client, m)
    res = ok(try_reserve(client, mh, t["id"], branch_a["id"], ts(TUE, 10)), 201)
    ok(act(client, mh, f"equipment-reservations/{res['id']}/cancel"))
    loan = elend(client, librarian, m["id"], it["id"])
    ok(act(client, mh, f"equipment-loans/{loan['id']}/extend"))
    assert [n["type"] for n in items(get(client, librarian, f"members/{m['id']}/notifications"))] == ["equipment_loan_created"]
'''),
    dict(id="T-EQ-38-c", req="LIB-EQ-38", type="Normal", input="Loan reported lost before its due time", expected="One `equipment_loan_lost` and one `fee_created` notification", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    m = member(client, librarian, branch_a)
    loan = elend(client, librarian, m["id"], it["id"])
    ok(act(client, librarian, f"equipment-loans/{loan['id']}/report-lost"))
    assert len(notes(client, librarian, m["id"], "equipment_loan_lost")) == 1
    assert len(notes(client, librarian, m["id"], "fee_created")) == 1
'''),
    dict(id="T-EQ-39-a", req="LIB-EQ-39", type="Normal", input="Type and item created, training recorded, item lent and returned; audit log filtered by event", expected="One entry each for `equipment_type_created`, `equipment_item_created`, `equipment_training_recorded`, `equipment_loan_created`, `equipment_loan_returned`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin, training=True)
    it = item(client, admin, t, branch_a)
    m = member(client, librarian, branch_a)
    ok(train(client, librarian, m["id"], t["id"], "2026-11-02"), 201)
    ok(ret(client, librarian, elend(client, librarian, m["id"], it["id"])["id"]))
    for event in ("equipment_type_created", "equipment_item_created", "equipment_training_recorded", "equipment_loan_created", "equipment_loan_returned"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-EQ-39-b", req="LIB-EQ-39", type="Normal", input="Reservation created and cancelled; process run", expected="One entry each for `equipment_reservation_created`, `equipment_reservation_cancelled`, `equipment_processed`", code='''
def TEST(client, admin, librarian, branch_a):
    t = etype(client, admin)
    item(client, admin, t, branch_a)
    res = reserve(client, librarian, t, branch_a, member(client, librarian, branch_a), TUE, 10)
    ok(act(client, librarian, f"equipment-reservations/{res['id']}/cancel"))
    process(client, librarian)
    for event in ("equipment_reservation_created", "equipment_reservation_cancelled", "equipment_processed"):
        assert len(items(get(client, admin, "audit-log", event=event))) == 1, event
'''),
    dict(id="T-EQ-40-a", req="LIB-EQ-40", type="Normal", input="Types AA (items at A, A, B) and BB (unused). Mon: reservation AA at A for Wed 10:00. Tue 09:00: three AA loans; 12:00 one returned damaged (40.00); 15:00 one returned 2 h late (10.00). Wed 10:31 process. Report Mon–Wed for branch A; then without branch", expected="Branch A: AA `{loans 2, late_returns 1, late_hours 2, damaged_returns 1, lost 0, reservations 1, expired_reservations 1, fees_created \"50.00\"}`, BB all 0 and \"0.00\"; without branch AA `loans` 3", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
    aa, bb = etype(client, admin, code="AA"), etype(client, admin, code="BB")
    i1, i2, i3 = item(client, admin, aa, branch_a), item(client, admin, aa, branch_a), item(client, admin, aa, branch_b)
    m1, m2, m3, m4 = (member(client, librarian, branch_a) for _ in range(4))
    reserve(client, librarian, aa, branch_a, m4, WED, 10)
    at(clock, TUE, 9, 0)
    l1, l2 = elend(client, librarian, m1["id"], i1["id"]), elend(client, librarian, m2["id"], i2["id"])
    elend(client, librarian, m3["id"], i3["id"])
    at(clock, TUE, 12, 0)
    ok(ret(client, librarian, l2["id"], "damaged", "40.00"))
    at(clock, TUE, 15, 0)
    ok(ret(client, librarian, l1["id"]))
    at(clock, WED, 10, 31)
    process(client, librarian)
    p = {"from": MON, "to": WED}
    rows = items(get(client, librarian, "reports/equipment-usage", branch_id=branch_a["id"], **p))
    keys = ("type_code", "loans", "late_returns", "late_hours", "damaged_returns", "lost", "reservations", "expired_reservations", "fees_created")
    assert [tuple(r[k] for k in keys) for r in rows] == [("AA", 2, 1, 2, 1, 0, 1, 1, "50.00"), ("BB", 0, 0, 0, 0, 0, 0, 0, "0.00")]
    assert items(get(client, librarian, "reports/equipment-usage", **p))[0]["loans"] == 3
'''),
    dict(id="T-EQ-40-b", req="LIB-EQ-40", type="Error", input="`from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31", expected="`422`; `422`; `403`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    url = "/api/v1/reports/equipment-usage"
    assert client.get(url, headers=librarian, params={"from": WED, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(url, headers=mh, params={"from": MON, "to": WED}).status_code == 403
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 200
'''),
    dict(id="T-EQ-41-a", req="LIB-EQ-41", type="Normal", input="Equipment type, item and loan exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1 (no equipment data)", code='''
def TEST(client, admin, librarian, branch_a):
    it = item(client, admin, etype(client, admin), branch_a)
    elend(client, librarian, member(client, librarian, branch_a)["id"], it["id"])
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
]
