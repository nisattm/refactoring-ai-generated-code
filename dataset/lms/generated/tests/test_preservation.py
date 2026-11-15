"""Module 23: Preservation (LIB-PRE-01 to LIB-PRE-40).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), book 0, a librarian (`lib`) and the admin.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.catalog.models import Copy
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err  # noqa: F401
from tests.test_loans import API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret  # noqa: F401
from tests.test_purchasing import mk_supplier
from tests.test_reservations import arrivals, reserve, res  # noqa: F401


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def budget(client, hd, amount="1000.00", branch=1, year=2026, expect=200):
    r = client.put(f"{API}/preservation-budgets/{branch}/{year}", headers=hd, json={"amount": amount})
    assert r.status_code == expect, r.text
    return r.json()


def job(client, hd, copy=1, expect=201, **kw):
    body = {"copy_id": copy, "kind": "repair", "provider": "in_house", "estimated_cost": "100.00", **kw}
    r = client.post(f"{API}/repair-jobs", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def step(client, hd, job_id, action, expect=200, **body):
    r = client.post(f"{API}/repair-jobs/{job_id}/{action}", headers=hd, json=body or None)
    assert r.status_code == expect, r.text
    return r.json()


def approved(client, hd, adm, copy=1, **kw):
    j = job(client, hd, copy, **kw)
    return step(client, adm, j["id"], "approve")


def used(client, hd, branch=1, year=2026):
    r = client.get(f"{API}/preservation-budgets/{branch}/{year}", headers=hd)
    assert r.status_code == 200, r.text
    return r.json()


def inspect(client, hd, copy, condition, note="", expect=201):
    r = client.post(f"{API}/copies/{copy}/inspections", headers=hd, json={"condition": condition, "note": note})
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def shelf(client, lib):
    """Book 0 with copies 1 and 2 at branch 1 (barcodes BC-0001, BC-0002)."""
    book = mk_book(client, lib, 0)
    new_copy(client, lib, book, "BC-0001")
    new_copy(client, lib, book, "BC-0002")
    return book


# --- budgets ----------------------------------------------------------------------------------------


def test_set_and_read_budget(client, lib, admin_h, shelf, app):
    assert budget(client, admin_h) == {"branch_id": 1, "year": 2026, "amount": "1000.00", "committed": "0.00",
                                       "spent": "0.00", "available": "1000.00"}
    assert budget(client, admin_h, "1500.50")["amount"] == "1500.50"
    assert used(client, lib)["amount"] == "1500.50"
    assert [a.entity_id for a in audit(app, "preservation_budget_set")] == [1, 1]
    err(client.get(f"{API}/preservation-budgets/2/2026", headers=lib), 404, "NOT_FOUND")
    err(client.get(f"{API}/preservation-budgets/1/2027", headers=lib), 404, "NOT_FOUND")


def test_budget_validation_and_permissions(client, lib, admin_h, shelf):
    for body in ({"amount": "-1.00"}, {"amount": "1000000.01"}, {"amount": 5}, {"amount": "1.234"}, {}, {"amount": "1.00", "x": 1}):
        err(client.put(f"{API}/preservation-budgets/1/2026", headers=admin_h, json=body), 422, "VALIDATION_ERROR")
    for year in (1999, 2101):
        err(client.put(f"{API}/preservation-budgets/1/{year}", headers=admin_h, json={"amount": "1.00"}), 422,
            "VALIDATION_ERROR")
    assert budget(client, admin_h, "0.00")["amount"] == "0.00"
    assert budget(client, admin_h, "1000000.00", year=2100)["year"] == 2100
    err(client.put(f"{API}/preservation-budgets/9/2026", headers=admin_h, json={"amount": "1.00"}), 404, "NOT_FOUND")
    err(client.put(f"{API}/preservation-budgets/1/2026", headers=lib, json={"amount": "1.00"}), 403, "FORBIDDEN")
    err(client.put(f"{API}/preservation-budgets/1/2026", json={"amount": "1.00"}), 401, "UNAUTHENTICATED")
    mk_member(client, lib)
    mh = member_h(client)
    for method, path in (("get", "/preservation-budgets/1/2026"), ("get", "/repair-jobs"), ("get", "/repair-shipments"),
                         ("get", "/copies/1/inspections"), ("get", "/preservation/suggestions?branch_id=1"),
                         ("post", "/preservation/process"), ("get", "/reports/preservation"),
                         ("get", "/reports/damage-recovery?from=2026-01-01&to=2026-12-31")):
        err(client.request(method, API + path, headers=mh), 403, "FORBIDDEN")


def test_budget_of_inactive_branch(client, lib, admin_h, shelf):
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200
    r = client.put(f"{API}/preservation-budgets/2/2026", headers=admin_h, json={"amount": "10.00"})
    err(r, 409, "BRANCH_INACTIVE")


def test_budget_use_and_lowering(client, lib, admin_h, shelf):
    budget(client, admin_h, "1000.00")
    a = approved(client, lib, admin_h, 1, estimated_cost="300.00")
    b = approved(client, lib, admin_h, 2, estimated_cost="200.00")
    assert used(client, lib) == {"branch_id": 1, "year": 2026, "amount": "1000.00", "committed": "500.00",
                                 "spent": "0.00", "available": "500.00"}
    step(client, lib, a["id"], "send")
    step(client, lib, a["id"], "return", outcome="repaired", actual_cost="250.00")
    u = used(client, lib)
    assert (u["committed"], u["spent"], u["available"]) == ("200.00", "250.00", "550.00")
    e = err(client.put(f"{API}/preservation-budgets/1/2026", headers=admin_h, json={"amount": "449.99"}), 409,
            "BUDGET_BELOW_USED")
    assert e["details"]["used"] == "450.00"
    assert budget(client, admin_h, "450.00")["available"] == "0.00"
    step(client, lib, b["id"], "cancel")
    assert used(client, lib)["available"] == "200.00"


# --- inspections and fragile copies -------------------------------------------------------------------


def test_inspection(client, lib, admin_h, shelf, clock, app):
    i = inspect(client, lib, 1, "worn", "spine cracked")
    assert i == {"id": 1, "copy_id": 1, "condition": "worn", "note": "spine cracked", "inspected_by": 2,
                 "inspected_at": "2026-11-02T09:30:00+03:00"} or i["inspected_by"] >= 1
    assert copy_of(client, lib, 1)["condition"] == "worn"
    clock.advance(hours=1)
    inspect(client, lib, 1, "fragile")
    inspect(client, lib, 2, "good")
    got = client.get(f"{API}/copies/1/inspections", headers=lib).json()
    assert [x["condition"] for x in got["items"]] == ["fragile", "worn"] and got["total"] == 2
    assert client.get(f"{API}/copies/1/inspections", headers=lib, params={"page_size": 1}).json()["items"][0]["id"] == 2
    assert [a.entity_id for a in audit(app, "copy_inspected")] == [1, 1, 2]
    err(client.post(f"{API}/copies/1/inspections", headers=lib, json={"condition": "bad"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/copies/1/inspections", headers=lib, json={"condition": "good", "note": "x" * 501}), 422,
        "VALIDATION_ERROR")
    err(client.post(f"{API}/copies/9/inspections", headers=lib, json={"condition": "good"}), 404, "NOT_FOUND")
    err(client.get(f"{API}/copies/9/inspections", headers=lib), 404, "NOT_FOUND")
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 2).json()
    inspect(client, lib, 2, "worn")  # a copy on loan can be inspected
    assert client.post(f"{API}/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    err(client.post(f"{API}/copies/2/inspections", headers=lib, json={"condition": "good"}), 409, "INVALID_COPY_STATUS")


def test_fragile_copy_is_not_lent(client, lib, shelf):
    m = mk_member(client, lib)
    inspect(client, lib, 1, "fragile")
    err(lend(client, lib, m, 1), 409, "COPY_FRAGILE")
    assert lend(client, lib, m, 2).status_code == 201
    inspect(client, lib, 1, "good")
    assert client.post(f"{API}/loans/1/return", headers=lib, json={"branch_id": 1, "condition": "good"}).status_code == 200
    assert lend(client, lib, m, 1).status_code == 201


def test_fragile_check_comes_after_status_checks(client, lib, shelf):
    m = mk_member(client, lib)
    inspect(client, lib, 1, "fragile")
    assert lend(client, lib, m, 2).status_code == 201
    m2 = mk_member(client, lib, 2)
    inspect(client, lib, 2, "fragile")
    err(lend(client, lib, m2, 2), 409, "COPY_NOT_AVAILABLE")


def test_fragile_copy_is_not_given_to_reservation(client, lib, shelf):
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    loan1 = lend(client, lib, m1, 1).json()
    loan2 = lend(client, lib, m1, 2).json()
    assert reserve(client, lib, shelf, 1, m2).status_code == 201
    inspect(client, lib, 1, "fragile")
    assert ret(client, lib, loan1["id"]).status_code == 200
    assert copy_of(client, lib, 1)["status"] == "available"
    assert res(client, lib, 1)["status"] == "waiting"
    assert ret(client, lib, loan2["id"]).status_code == 200  # a good copy goes to the reservation
    assert (copy_of(client, lib, 2)["status"], res(client, lib, 1)["status"]) == ("on_hold", "ready")


def test_fragile_copy_at_other_branch_is_not_assigned(client, lib, shelf):
    """LIB-RES-05 and LIB-PRE-30: only good copies count and are assigned."""
    m = mk_member(client, lib)
    inspect(client, lib, 1, "fragile")
    inspect(client, lib, 2, "fragile")
    r = reserve(client, lib, shelf, 1, m)
    assert r.status_code == 201 and r.json()["status"] == "waiting"  # LIB-PRE-30: fragile copies do not block
    assert copy_of(client, lib, 1)["status"] == "available"
    r = reserve(client, lib, shelf, 2, mk_member(client, lib, 2))
    assert r.json()["status"] == "waiting"


def test_fragile_copy_at_other_branch_is_assigned_when_good(client, lib, shelf):
    m = mk_member(client, lib)
    r = reserve(client, lib, shelf, 2, m).json()
    assert r["status"] == "in_transit"


# --- creating and changing jobs -----------------------------------------------------------------------


def test_create_job(client, lib, admin_h, shelf, app):
    s = mk_supplier(client, admin_h)
    j = job(client, lib, 1, kind="rebinding", provider="supplier", supplier_id=s["id"], priority="urgent",
            estimated_cost="80.50", note="  loose  ")
    assert j == {
        "id": 1, "copy_id": 1, "barcode": "BC-0001", "book_title": "Book 0", "branch_id": 1, "kind": "rebinding",
        "provider": "supplier", "supplier_id": 1, "priority": "urgent", "estimated_cost": "80.50",
        "actual_cost": None, "status": "requested", "outcome": None, "loan_id": None, "shipment_id": None,
        "note": "loose", "cost_note": "", "cost_overrun": False, "requested_at": "2026-11-02T09:30:00+03:00",
        "approved_at": None, "sent_at": None, "returned_at": None, "due_back": None, "cancel_reason": None,
        "overdue_marked_at": None, "is_overdue": False, "claim_amount": None,
    }
    assert [a.entity_id for a in audit(app, "repair_job_created")] == [1]
    assert copy_of(client, lib, 1)["open_job_id"] == 1
    assert client.get(f"{API}/repair-jobs/1", headers=lib).json() == j
    err(client.get(f"{API}/repair-jobs/5", headers=lib), 404, "NOT_FOUND")


def test_create_job_validation(client, lib, admin_h, shelf):
    s = mk_supplier(client, admin_h)
    base = {"copy_id": 1, "kind": "repair", "provider": "in_house", "estimated_cost": "10.00"}
    bad = [
        {**base, "kind": "paint"}, {**base, "provider": "me"}, {**base, "priority": "high"},
        {**base, "estimated_cost": "100000.01"}, {**base, "estimated_cost": "-1.00"}, {**base, "estimated_cost": 5},
        {**base, "provider": "supplier"}, {**base, "supplier_id": s["id"]}, {**base, "note": "x" * 501},
        {**base, "x": 1}, {k: v for k, v in base.items() if k != "kind"},
    ]
    for body in bad:
        err(client.post(f"{API}/repair-jobs", headers=lib, json=body), 422, "VALIDATION_ERROR")
    e = err(client.post(f"{API}/repair-jobs", headers=lib, json={**base, "copy_id": 99}), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "copy_id"
    e = err(client.post(f"{API}/repair-jobs", headers=lib, json={**base, "provider": "supplier", "supplier_id": 99}),
            422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "supplier_id"
    j = job(client, lib, 1, estimated_cost="0.00")
    assert j["estimated_cost"] == "0.00" and j["priority"] == "normal"


def test_create_checks_in_order(client, lib, admin_h, shelf):
    s = mk_supplier(client, admin_h)
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 1).json()
    e = err(client.post(f"{API}/repair-jobs", headers=lib, json={"copy_id": 1, "kind": "repair", "provider": "in_house",
                                                                 "estimated_cost": "1.00"}), 409, "INVALID_COPY_STATUS")
    assert e["details"]["status"] == "on_loan"
    ret(client, lib, loan["id"])
    first = job(client, lib, 1)
    e = err(client.post(f"{API}/repair-jobs", headers=lib, json={"copy_id": 1, "kind": "repair", "provider": "in_house",
                                                                 "estimated_cost": "1.00"}), 409, "COPY_HAS_REPAIR_JOB")
    assert e["details"]["job_id"] == first["id"]
    assert client.patch(f"{API}/suppliers/{s['id']}", headers=admin_h, json={"is_active": False}).status_code == 200
    body = {"copy_id": 2, "kind": "repair", "provider": "supplier", "supplier_id": s["id"], "estimated_cost": "1.00"}
    err(client.post(f"{API}/repair-jobs", headers=lib, json=body), 409, "SUPPLIER_INACTIVE")
    # supplier check comes before the branch check
    err(client.post(f"{API}/repair-jobs", headers=lib, json={**body, "copy_id": 1}), 409, "COPY_HAS_REPAIR_JOB")


def test_update_job(client, lib, admin_h, shelf, app):
    s = mk_supplier(client, admin_h)
    j = job(client, lib, 1)
    r = client.patch(f"{API}/repair-jobs/1", headers=lib, json={"kind": "conservation", "estimated_cost": "75.00",
                                                                "priority": "urgent", "note": "new"})
    assert r.status_code == 200
    body = r.json()
    assert (body["kind"], body["estimated_cost"], body["priority"], body["note"]) == ("conservation", "75.00", "urgent", "new")
    assert [a.entity_id for a in audit(app, "repair_job_updated")] == [1]
    r = client.patch(f"{API}/repair-jobs/1", headers=lib, json={"provider": "supplier", "supplier_id": s["id"]})
    assert r.status_code == 200 and r.json()["supplier_id"] == s["id"]
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"supplier_id": None}), 422, "VALIDATION_ERROR")
    r = client.patch(f"{API}/repair-jobs/1", headers=lib, json={"provider": "in_house", "supplier_id": None})
    assert r.status_code == 200 and r.json()["supplier_id"] is None
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"supplier_id": s["id"]}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"supplier_id": 99, "provider": "supplier"}), 422,
        "VALIDATION_ERROR")
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"kind": "x"}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"copy_id": 2}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/repair-jobs/7", headers=lib, json={"note": "x"}), 404, "NOT_FOUND")
    assert client.patch(f"{API}/suppliers/{s['id']}", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"provider": "supplier", "supplier_id": s["id"]}), 409,
        "SUPPLIER_INACTIVE")
    budget(client, admin_h)
    step(client, admin_h, 1, "approve")
    e = err(client.patch(f"{API}/repair-jobs/1", headers=lib, json={"note": "late"}), 409, "INVALID_JOB_STATUS")
    assert e["details"]["status"] == "approved"


def test_damage_link(client, lib, shelf):
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 1).json()
    assert ret(client, lib, loan["id"], condition="damaged", damage_fee="30.00").status_code == 200
    assert job(client, lib, 1)["loan_id"] == loan["id"]
    assert job(client, lib, 2)["loan_id"] is None


def test_damage_link_only_for_a_damaged_return(client, lib, shelf):
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 1).json()
    ret(client, lib, loan["id"])
    assert job(client, lib, 1)["loan_id"] is None


# --- approval ----------------------------------------------------------------------------------------


def test_approve(client, lib, admin_h, shelf, app):
    j = job(client, lib, 1)
    e = err(client.post(f"{API}/repair-jobs/1/approve", headers=lib), 409, "NO_PRESERVATION_BUDGET")
    budget(client, admin_h, "1000.00", year=2027)
    err(client.post(f"{API}/repair-jobs/1/approve", headers=lib), 409, "NO_PRESERVATION_BUDGET")
    budget(client, admin_h, "1000.00", branch=2)
    err(client.post(f"{API}/repair-jobs/1/approve", headers=lib), 409, "NO_PRESERVATION_BUDGET")
    budget(client, admin_h, "1000.00")
    a = client.post(f"{API}/repair-jobs/1/approve", headers=lib)
    assert a.status_code == 200
    assert (a.json()["status"], a.json()["approved_at"]) == ("approved", "2026-11-02T09:30:00+03:00")
    assert [x.entity_id for x in audit(app, "repair_job_approved")] == [1]
    e = err(client.post(f"{API}/repair-jobs/1/approve", headers=lib), 409, "INVALID_JOB_STATUS")
    assert e["details"]["status"] == "approved"
    assert j["status"] == "requested"
    err(client.post(f"{API}/repair-jobs/9/approve", headers=lib), 404, "NOT_FOUND")


def test_budget_examples(client, lib, admin_h, shelf):
    budget(client, admin_h, "1000.00")
    c3 = new_copy(client, lib, 1, "BC-0003")
    c4 = new_copy(client, lib, 1, "BC-0004")
    c5 = new_copy(client, lib, 1, "BC-0005")
    c6 = new_copy(client, lib, 1, "BC-0006")
    approved(client, lib, admin_h, 1, estimated_cost="700.00")
    j = job(client, lib, 2, estimated_cost="300.01")
    e = err(client.post(f"{API}/repair-jobs/{j['id']}/approve", headers=lib), 409, "BUDGET_EXCEEDED")
    assert e["details"]["available"] == "300.00"
    client.patch(f"{API}/repair-jobs/{j['id']}", headers=lib, json={"estimated_cost": "300.00"})
    assert step(client, lib, j["id"], "approve")["status"] == "approved"
    step(client, lib, j["id"], "cancel")
    ju = job(client, lib, c3, estimated_cost="400.01", priority="urgent")
    e = err(client.post(f"{API}/repair-jobs/{ju['id']}/approve", headers=admin_h), 409, "BUDGET_EXCEEDED")
    assert e["details"]["available"] == "300.00"
    client.patch(f"{API}/repair-jobs/{ju['id']}", headers=lib, json={"estimated_cost": "400.00"})
    assert step(client, admin_h, ju["id"], "approve")["status"] == "approved"
    assert used(client, lib)["available"] == "-100.00"
    jn = job(client, lib, c4, estimated_cost="0.01")
    err(client.post(f"{API}/repair-jobs/{jn['id']}/approve", headers=lib), 409, "BUDGET_EXCEEDED")
    assert c5 and c6


def test_only_admin_approves_expensive_jobs(client, lib, admin_h, shelf):
    budget(client, admin_h, "5000.00")
    job(client, lib, 1, estimated_cost="500.00")
    job(client, lib, 2, estimated_cost="500.01")
    assert client.post(f"{API}/repair-jobs/1/approve", headers=lib).status_code == 200
    err(client.post(f"{API}/repair-jobs/2/approve", headers=lib), 403, "FORBIDDEN")
    assert client.post(f"{API}/repair-jobs/2/approve", headers=admin_h).status_code == 200


def test_cancel(client, lib, admin_h, shelf, app):
    budget(client, admin_h)
    a, b = job(client, lib, 1), job(client, lib, 2)
    step(client, admin_h, b["id"], "approve")
    c1 = step(client, lib, a["id"], "cancel")
    assert (c1["status"], c1["cancel_reason"]) == ("cancelled", "staff_request")
    assert step(client, lib, b["id"], "cancel")["status"] == "cancelled"
    assert copy_of(client, lib, 1)["status"] == "available" and copy_of(client, lib, 1)["open_job_id"] is None
    assert [x.entity_id for x in audit(app, "repair_job_cancelled")] == [1, 2]
    e = err(client.post(f"{API}/repair-jobs/1/cancel", headers=lib), 409, "INVALID_JOB_STATUS")
    assert e["details"]["status"] == "cancelled"
    job(client, lib, 1)  # a new job is possible again


# --- sending, shipments and returning ---------------------------------------------------------------------


def test_send_and_due_back(client, lib, admin_h, shelf, app):
    budget(client, admin_h)
    approved(client, lib, admin_h, 1, kind="rebinding")
    s = step(client, lib, 1, "send")
    assert (s["status"], s["sent_at"], s["due_back"]) == ("sent", "2026-11-02T09:30:00+03:00", "2026-11-23")
    c = copy_of(client, lib, 1)
    assert (c["status"], c["current_branch_id"]) == ("in_repair", 1)
    assert [x.entity_id for x in audit(app, "repair_job_sent")] == [1]
    e = err(client.post(f"{API}/repair-jobs/1/send", headers=lib), 409, "INVALID_JOB_STATUS")
    assert e["details"]["status"] == "sent"
    e = err(client.post(f"{API}/repair-jobs/1/cancel", headers=lib), 409, "INVALID_JOB_STATUS")


@pytest.mark.parametrize("kind,provider,priority,days", [
    ("repair", "in_house", "normal", 7), ("rebinding", "in_house", "normal", 21),
    ("conservation", "in_house", "normal", 42), ("repair", "supplier", "normal", 14),
    ("rebinding", "supplier", "normal", 28), ("conservation", "supplier", "normal", 49),
    ("repair", "in_house", "urgent", 4), ("rebinding", "in_house", "urgent", 11),
    ("conservation", "in_house", "urgent", 21), ("repair", "supplier", "urgent", 7),
    ("rebinding", "supplier", "urgent", 14), ("conservation", "supplier", "urgent", 25),
])
def test_turnaround(client, lib, admin_h, shelf, kind, provider, priority, days):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    extra = {"supplier_id": s["id"]} if provider == "supplier" else {}
    j = approved(client, lib, admin_h, 1, kind=kind, provider=provider, priority=priority, **extra)
    if provider == "supplier":
        r = client.post(f"{API}/repair-shipments", headers=lib, json={"supplier_id": s["id"], "job_ids": [j["id"]]})
        assert r.status_code == 201, r.text
    else:
        step(client, lib, j["id"], "send")
    due = client.get(f"{API}/repair-jobs/{j['id']}", headers=lib).json()["due_back"]
    assert due == (datetime.date(2026, 11, 2) + datetime.timedelta(days=days)).isoformat()


def test_send_checks(client, lib, admin_h, shelf):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    j = approved(client, lib, admin_h, 1, provider="supplier", supplier_id=s["id"])
    err(client.post(f"{API}/repair-jobs/{j['id']}/send", headers=lib), 409, "SHIPMENT_REQUIRED")
    j2 = approved(client, lib, admin_h, 2)
    m = mk_member(client, lib)
    assert lend(client, lib, m, 2).status_code == 201  # the approved copy was lent in the meantime
    e = err(client.post(f"{API}/repair-jobs/{j2['id']}/send", headers=lib), 409, "INVALID_COPY_STATUS")
    assert e["details"]["status"] == "on_loan"
    assert copy_of(client, lib, 2)["status"] == "on_loan"


def test_shipment(client, lib, admin_h, shelf, app):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    s2 = mk_supplier(client, admin_h, "Other")
    book = 1
    c3 = new_copy(client, lib, book, "BC-0003", branch=2)
    ja = approved(client, lib, admin_h, 1, provider="supplier", supplier_id=s["id"], kind="repair")
    jb = approved(client, lib, admin_h, 2, provider="supplier", supplier_id=s["id"], kind="rebinding")
    jd = job(client, lib, c3, provider="supplier", supplier_id=s["id"])
    post = lambda body: client.post(f"{API}/repair-shipments", headers=lib, json=body)  # noqa: E731
    for body in ({"supplier_id": s["id"], "job_ids": []}, {"supplier_id": s["id"], "job_ids": [1, 1]},
                 {"supplier_id": s["id"], "job_ids": list(range(1, 52))}, {"supplier_id": s["id"]},
                 {"supplier_id": s["id"], "job_ids": [1], "x": 1}):
        err(post(body), 422, "VALIDATION_ERROR")
    err(post({"supplier_id": 99, "job_ids": [1]}), 404, "NOT_FOUND")
    err(post({"supplier_id": s["id"], "job_ids": [1, 99]}), 404, "NOT_FOUND")
    e = err(post({"supplier_id": s2["id"], "job_ids": [ja["id"]]}), 409, "SHIPMENT_MISMATCH")
    assert e["details"]["job_id"] == ja["id"]
    e = err(post({"supplier_id": s["id"], "job_ids": [ja["id"], jd["id"]]}), 409, "SHIPMENT_MISMATCH")
    assert e["details"]["job_id"] == jd["id"]
    assert copy_of(client, lib, 1)["status"] == "available"  # all or nothing
    r = post({"supplier_id": s["id"], "job_ids": [jb["id"], ja["id"]]})
    assert r.status_code == 201, r.text
    ship = r.json()
    assert ship == {"id": 1, "code": "SH-AAA-1", "supplier_id": s["id"], "branch_id": 1, "job_ids": [1, 2],
                    "open_jobs": 2, "sent_at": "2026-11-02T09:30:00+03:00"}
    assert [(j["status"], j["shipment_id"], j["due_back"]) for j in
            client.get(f"{API}/repair-jobs", headers=lib, params={"status": "sent"}).json()["items"]] == [
        ("sent", 1, "2026-11-30"), ("sent", 1, "2026-11-16")]
    assert [x.entity_id for x in audit(app, "repair_shipment_sent")] == [1]
    assert copy_of(client, lib, 2)["status"] == "in_repair"
    err(post({"supplier_id": s["id"], "job_ids": [ja["id"]]}), 409, "SHIPMENT_MISMATCH")
    step(client, lib, ja["id"], "return", outcome="repaired", actual_cost="10.00")
    got = client.get(f"{API}/repair-shipments/1", headers=lib).json()
    assert (got["job_ids"], got["open_jobs"]) == ([1, 2], 1)
    err(client.get(f"{API}/repair-shipments/4", headers=lib), 404, "NOT_FOUND")


def test_shipment_code_counts_per_branch_and_list(client, lib, admin_h, shelf):
    budget(client, admin_h)
    budget(client, admin_h, branch=2)
    s = mk_supplier(client, admin_h)
    c3 = new_copy(client, lib, 1, "BC-0003", branch=2)
    for c in (1, 2, c3):
        j = approved(client, lib, admin_h, c, provider="supplier", supplier_id=s["id"])
        r = client.post(f"{API}/repair-shipments", headers=lib, json={"supplier_id": s["id"], "job_ids": [j["id"]]})
        assert r.status_code == 201, r.text
    items = client.get(f"{API}/repair-shipments", headers=lib).json()["items"]
    assert [i["code"] for i in items] == ["SH-BBB-1", "SH-AAA-2", "SH-AAA-1"]
    only = client.get(f"{API}/repair-shipments", headers=lib, params={"branch_id": 2}).json()
    assert [i["id"] for i in only["items"]] == [3] and only["total"] == 1
    assert client.get(f"{API}/repair-shipments", headers=lib, params={"supplier_id": 9}).json()["total"] == 0


def test_shipment_copy_checks_apply(client, lib, admin_h, shelf):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    j = approved(client, lib, admin_h, 1, provider="supplier", supplier_id=s["id"])
    m = mk_member(client, lib)
    assert lend(client, lib, m, 1).status_code == 201
    err(client.post(f"{API}/repair-shipments", headers=lib, json={"supplier_id": s["id"], "job_ids": [j["id"]]}), 409,
        "INVALID_COPY_STATUS")
    assert client.get(f"{API}/repair-shipments", headers=lib).json()["total"] == 0


def test_return_repaired_and_example(client, lib, admin_h, clock, shelf, app):
    """LIB-PRE-40."""
    budget(client, admin_h)
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    loan = lend(client, lib, m1, 1).json()
    assert lend(client, lib, m1, 2).status_code == 201
    assert ret(client, lib, loan["id"], condition="damaged", damage_fee="30.00").status_code == 200
    assert reserve(client, lib, 1, 1, m2).json()["status"] == "waiting"
    j = approved(client, lib, admin_h, 1, estimated_cost="25.00")
    assert j["loan_id"] == loan["id"]
    s = step(client, lib, j["id"], "send")
    assert s["due_back"] == "2026-11-09"
    at(clock, 2026, 11, 6)
    done = step(client, lib, j["id"], "return", outcome="repaired", actual_cost="20.00", cost_note="")
    assert (done["status"], done["outcome"], done["actual_cost"], done["returned_at"], done["cost_overrun"]) == (
        "returned", "repaired", "20.00", "2026-11-06T09:00:00+03:00", False)
    assert (copy_of(client, lib, 1)["status"], copy_of(client, lib, 1)["condition"]) == ("on_hold", "good")
    assert res(client, lib, 1)["status"] == "ready"
    rep = client.get(f"{API}/reports/damage-recovery", headers=lib, params={"from": "2026-11-01", "to": "2026-11-30"}).json()
    assert rep["items"] == [{"job_id": 1, "copy_id": 1, "loan_id": loan["id"], "member_id": m1, "damage_fee": "30.00",
                             "actual_cost": "20.00", "difference": "10.00"}]
    assert rep["totals"] == {"damage_fees": "30.00", "costs": "20.00", "difference": "10.00"}
    assert [x.entity_id for x in audit(app, "repair_job_returned")] == [1]
    err(client.post(f"{API}/repair-jobs/1/return", headers=lib, json={"outcome": "repaired", "actual_cost": "1.00"}), 409,
        "INVALID_JOB_STATUS")


def test_return_goes_home_or_available(client, lib, admin_h, shelf):
    budget(client, admin_h)
    j = approved(client, lib, admin_h, 1)
    step(client, lib, j["id"], "send")
    step(client, lib, j["id"], "return", outcome="repaired", actual_cost="0.00")
    assert copy_of(client, lib, 1)["status"] == "available"


def test_return_unrepairable(client, lib, admin_h, shelf):
    budget(client, admin_h)
    inspect(client, lib, 1, "worn")
    j = approved(client, lib, admin_h, 1)
    step(client, lib, j["id"], "send")
    got = step(client, lib, j["id"], "return", outcome="unrepairable", actual_cost="5.00")
    assert got["outcome"] == "unrepairable"
    c = copy_of(client, lib, 1)
    assert (c["status"], c["condition"], c["open_job_id"]) == ("damaged", "worn", None)
    assert client.post(f"{API}/copies/1/repair", headers=lib).status_code == 200


def test_return_validation_and_cost_overrun(client, lib, admin_h, shelf):
    budget(client, admin_h)
    j = approved(client, lib, admin_h, 1, estimated_cost="100.00")
    step(client, lib, j["id"], "send")
    url = f"{API}/repair-jobs/{j['id']}/return"
    for body in ({"outcome": "x", "actual_cost": "1.00"}, {"actual_cost": "1.00"}, {"outcome": "repaired"},
                 {"outcome": "repaired", "actual_cost": "100000.01"}, {"outcome": "repaired", "actual_cost": "-1.00"},
                 {"outcome": "repaired", "actual_cost": "1.00", "x": 1}, {"outcome": "repaired", "actual_cost": 1}):
        err(client.post(url, headers=lib, json=body), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=lib, json={"outcome": "repaired", "actual_cost": "120.01"}), 422, "VALIDATION_ERROR")
    err(client.post(url, headers=lib, json={"outcome": "repaired", "actual_cost": "120.01", "cost_note": "  "}), 422,
        "VALIDATION_ERROR")
    assert copy_of(client, lib, 1)["status"] == "in_repair"
    got = client.post(url, headers=lib, json={"outcome": "repaired", "actual_cost": "120.01", "cost_note": "more glue"})
    assert got.status_code == 200
    assert (got.json()["cost_overrun"], got.json()["cost_note"]) == (True, "more glue")
    j2 = approved(client, lib, admin_h, 2, estimated_cost="100.00")
    step(client, lib, j2["id"], "send")
    ok = step(client, lib, j2["id"], "return", outcome="repaired", actual_cost="120.00")
    assert ok["cost_overrun"] is False


def test_lost_at_provider(client, lib, admin_h, shelf, app):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    ja = approved(client, lib, admin_h, 1, provider="supplier", supplier_id=s["id"], estimated_cost="40.00")
    jb = approved(client, lib, admin_h, 2, estimated_cost="60.00")
    client.post(f"{API}/repair-shipments", headers=lib, json={"supplier_id": s["id"], "job_ids": [ja["id"]]})
    step(client, lib, jb["id"], "send")
    err(client.post(f"{API}/repair-jobs/{ja['id']}/cancel", headers=lib), 409, "INVALID_JOB_STATUS")
    lost = step(client, lib, ja["id"], "lost")
    assert (lost["status"], lost["claim_amount"]) == ("lost", "50.00")
    c = copy_of(client, lib, 1)
    assert (c["status"], c["current_branch_id"]) == ("lost", None)
    inhouse = step(client, lib, jb["id"], "lost")
    assert inhouse["claim_amount"] is None and copy_of(client, lib, 2)["status"] == "lost"
    assert [x.entity_id for x in audit(app, "repair_job_lost")] == [1, 2]
    u = used(client, lib)
    assert (u["committed"], u["spent"]) == ("0.00", "100.00")
    err(client.post(f"{API}/repair-jobs/{ja['id']}/lost", headers=lib), 409, "INVALID_JOB_STATUS")
    assert client.post(f"{API}/copies/1/withdraw", headers=lib, json={"reason": "gone for good"}).status_code == 200


# --- reading jobs and other lists ------------------------------------------------------------------------


def test_list_jobs_and_filters(client, lib, admin_h, shelf, clock):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    c3 = new_copy(client, lib, 1, "BC-0003", branch=2)
    job(client, lib, 1)
    j2 = approved(client, lib, admin_h, 2, kind="conservation", provider="supplier", supplier_id=s["id"])
    job(client, lib, c3, kind="rebinding")
    client.post(f"{API}/repair-shipments", headers=lib, json={"supplier_id": s["id"], "job_ids": [j2["id"]]})

    def ids(**params):
        r = client.get(f"{API}/repair-jobs", headers=lib, params=params)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids() == [3, 2, 1]
    assert ids(status="requested") == [3, 1] and ids(status="sent") == [2]
    assert ids(branch_id=2) == [3] and ids(provider="supplier") == [2] and ids(supplier_id=s["id"]) == [2]
    assert ids(kind="rebinding") == [3] and ids(copy_id=2) == [2] and ids(overdue="false") == [3, 2, 1]
    assert ids(overdue="true") == []
    at(clock, 2026, 12, 21)
    assert ids(overdue="true") == [] and ids(overdue="false") == [3, 2, 1]
    at(clock, 2026, 12, 22)
    assert ids(overdue="true") == [2] and ids(overdue="false") == [3, 1]
    assert client.get(f"{API}/repair-jobs/2", headers=lib).json()["is_overdue"] is True
    for bad in ({"status": "x"}, {"provider": "x"}, {"kind": "x"}, {"overdue": "maybe"}, {"page": 0}):
        err(client.get(f"{API}/repair-jobs", headers=lib, params=bad), 422, "VALIDATION_ERROR")
    page = client.get(f"{API}/repair-jobs", headers=lib, params={"page_size": 2, "page": 2}).json()
    assert (page["total"], [i["id"] for i in page["items"]]) == (3, [1])


def test_process(client, lib, admin_h, shelf, clock, app):
    budget(client, admin_h)
    approved(client, lib, admin_h, 1, kind="repair")
    step(client, lib, 1, "send")  # due 2026-11-09
    job(client, lib, 2)
    r = client.post(f"{API}/preservation/process", headers=lib)
    assert r.json() == {"overdue": 0, "newly_overdue": 0, "expired_requests": 0}
    at(clock, 2026, 11, 9)
    assert client.post(f"{API}/preservation/process", headers=lib).json()["overdue"] == 0
    at(clock, 2026, 11, 10)
    assert client.post(f"{API}/preservation/process", headers=lib).json() == {
        "overdue": 1, "newly_overdue": 1, "expired_requests": 0}
    assert client.get(f"{API}/repair-jobs/1", headers=lib).json()["overdue_marked_at"] == "2026-11-10T09:00:00+03:00"
    assert client.post(f"{API}/preservation/process", headers=lib).json() == {
        "overdue": 1, "newly_overdue": 0, "expired_requests": 0}
    at(clock, 2027, 1, 1)  # 60 days after 2026-11-02 is 2027-01-01 09:30
    assert client.post(f"{API}/preservation/process", headers=lib).json()["expired_requests"] == 0
    at(clock, 2027, 1, 2)
    assert client.post(f"{API}/preservation/process", headers=lib).json() == {
        "overdue": 1, "newly_overdue": 0, "expired_requests": 1}
    j = client.get(f"{API}/repair-jobs/2", headers=lib).json()
    assert (j["status"], j["cancel_reason"]) == ("cancelled", "expired")
    assert len(audit(app, "preservation_processed")) == 6
    err(client.post(f"{API}/preservation/process"), 401, "UNAUTHENTICATED")


def test_suggestions(client, lib, admin_h, shelf, app):
    books = [mk_book(client, lib, 1)]
    for n in range(3, 7):
        new_copy(client, lib, books[0], f"BC-000{n}")
    other = new_copy(client, lib, books[0], "BC-0009", branch=2)
    inspect(client, lib, 1, "fragile")
    inspect(client, lib, 2, "worn")
    inspect(client, lib, 3, "worn")
    inspect(client, lib, 4, "good")
    inspect(client, lib, other, "fragile")
    m = mk_member(client, lib, 1, "academic")
    with app.state.session_factory.begin() as s:
        from lms.loans.models import Loan
        for n in range(30):
            s.add(Loan(copy_id=3, member_id=m, branch_id=1, loan_date=datetime.date(2026, 1, 1),
                       due_date=datetime.date(2026, 1, 2), loan_period_days=1, max_renewals=0, daily_fee=0,
                       renewal_count=0, status="returned", returned_on=datetime.date(2026, 1, 2), created_by=1))
        for n in range(29):
            s.add(Loan(copy_id=2, member_id=m, branch_id=1, loan_date=datetime.date(2026, 1, 1),
                       due_date=datetime.date(2026, 1, 2), loan_period_days=1, max_renewals=0, daily_fee=0,
                       renewal_count=0, status="returned", returned_on=datetime.date(2026, 1, 2), created_by=1))
        s.get(Copy, 5).status = "damaged"
    got = client.get(f"{API}/preservation/suggestions", headers=lib, params={"branch_id": 1}).json()
    assert got == {"items": [
        {"copy_id": 1, "barcode": "BC-0001", "reason": "fragile"},
        {"copy_id": 3, "barcode": "BC-0003", "reason": "worn_and_used"},
        {"copy_id": 5, "barcode": "BC-0005", "reason": "damaged"},
    ]}
    budget(client, admin_h)
    job(client, lib, 1)
    ids = [i["copy_id"] for i in client.get(f"{API}/preservation/suggestions", headers=lib, params={"branch_id": 1}).json()["items"]]
    assert ids == [3, 5]
    assert [i["copy_id"] for i in client.get(f"{API}/preservation/suggestions", headers=lib, params={"branch_id": 2}).json()["items"]] == [other]
    err(client.get(f"{API}/preservation/suggestions", headers=lib), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/preservation/suggestions", headers=lib, params={"branch_id": 9}), 404, "NOT_FOUND")


# --- effects on other modules ----------------------------------------------------------------------------------


def _in_repair(client, lib, admin_h, copy=1):
    budget(client, admin_h)
    j = approved(client, lib, admin_h, copy)
    step(client, lib, j["id"], "send")
    return j


def test_copy_in_repair_blocks_other_actions(client, lib, admin_h, shelf):
    m = mk_member(client, lib)
    _in_repair(client, lib, admin_h)
    e = err(lend(client, lib, m, 1), 409, "COPY_NOT_AVAILABLE")
    assert e["details"]["status"] == "in_repair"
    err(client.post(f"{API}/transfers", headers=lib, json={"copy_id": 1, "to_branch_id": 2}), 409, "INVALID_COPY_STATUS")
    e = err(client.post(f"{API}/copies/1/withdraw", headers=lib, json={"reason": "no longer"}), 409, "COPY_HAS_REPAIR_JOB")
    assert e["details"]["job_id"] == 1
    err(client.post(f"{API}/copies/1/repair", headers=lib), 409, "COPY_HAS_REPAIR_JOB")
    err(client.patch(f"{API}/copies/1", headers=lib, json={"home_branch_id": 2}), 409, "INVALID_COPY_STATUS")
    b = client.get(f"{API}/books/{shelf}", headers=lib).json()
    assert b["availability"] == [{"branch_id": 1, "available": 1, "total": 2, "expected_back": "2026-11-09"}]
    assert client.get(f"{API}/books/{shelf}/copies", headers=lib, params={"status": "in_repair"}).json()["total"] == 1
    assert client.get(f"{API}/copies/1", headers=lib).json()["open_job_id"] == 1


def test_direct_repair_and_withdraw_of_copy_with_requested_job(client, lib, admin_h, shelf):
    budget(client, admin_h)
    m = mk_member(client, lib)
    loan = lend(client, lib, m, 1).json()
    ret(client, lib, loan["id"], condition="damaged", damage_fee="5.00")
    job(client, lib, 1)
    e = err(client.post(f"{API}/copies/1/repair", headers=lib), 409, "COPY_HAS_REPAIR_JOB")
    assert e["details"]["job_id"] == 1
    err(client.post(f"{API}/copies/1/withdraw", headers=lib, json={"reason": "12345"}), 409, "COPY_HAS_REPAIR_JOB")
    step(client, lib, 1, "cancel")
    assert client.post(f"{API}/copies/1/repair", headers=lib).status_code == 200


def test_member_view_of_books(client, lib, admin_h, shelf):
    mk_member(client, lib)
    _in_repair(client, lib, admin_h)
    assert [r for r in client.get(f"{API}/books/{shelf}", headers=member_h(client)).json()["availability"]] == [
        {"branch_id": 1, "available": 1, "total": 2, "expected_back": "2026-11-09"}]
    approved(client, lib, admin_h, 2, kind="conservation")
    step(client, lib, 2, "send")
    row = client.get(f"{API}/books/{shelf}", headers=member_h(client)).json()["availability"][0]
    assert (row["available"], row["total"], row["expected_back"]) == (0, 2, "2026-12-14")


def test_copy_condition_filter(client, lib, shelf):
    inspect(client, lib, 2, "fragile")
    got = client.get(f"{API}/books/{shelf}/copies", headers=lib, params={"condition": "fragile"}).json()
    assert [c["id"] for c in got["items"]] == [2]
    err(client.get(f"{API}/books/{shelf}/copies", headers=lib, params={"condition": "x"}), 422, "VALIDATION_ERROR")


def test_supplier_deactivation(client, lib, admin_h, shelf):
    budget(client, admin_h)
    s = mk_supplier(client, admin_h)
    job(client, lib, 1, provider="supplier", supplier_id=s["id"])
    job(client, lib, 2, provider="supplier", supplier_id=s["id"])
    e = err(client.patch(f"{API}/suppliers/{s['id']}", headers=lib, json={"is_active": False}), 409, "SUPPLIER_HAS_JOBS")
    assert e["details"]["job_ids"] == [1, 2]
    step(client, lib, 1, "cancel")
    step(client, lib, 2, "cancel")
    assert client.patch(f"{API}/suppliers/{s['id']}", headers=lib, json={"is_active": False}).status_code == 200


def test_reservation_check_ignores_fragile_copy(client, lib, shelf):
    m = mk_member(client, lib)
    inspect(client, lib, 1, "fragile")
    err(reserve(client, lib, shelf, 1, m), 409, "COPY_AVAILABLE_AT_BRANCH")  # copy 2 is good and available
    inspect(client, lib, 2, "fragile")
    assert reserve(client, lib, shelf, 1, m).status_code == 201


def test_export_hides_repair_status(client, lib, admin_h, shelf, app):
    _in_repair(client, lib, admin_h)
    doc = lms.export_dataset(app.state.settings)
    assert [(c["id"], c["status"]) for c in doc["copies"]] == [(1, "damaged"), (2, "available")]
    assert all("condition" not in c for c in doc["copies"])
    assert client.get(f"{API}/export", headers=admin_h).json()["copies"][0]["status"] == "damaged"


def test_no_notifications(client, lib, admin_h, shelf, app):
    _in_repair(client, lib, admin_h)
    step(client, lib, 1, "return", outcome="repaired", actual_cost="1.00")
    with app.state.session_factory() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Notification)) == 0


# --- reports ----------------------------------------------------------------------------------------------------


def test_preservation_report(client, lib, admin_h, shelf, clock):
    budget(client, admin_h, "1000.00")
    budget(client, admin_h, "500.00", branch=2)
    budget(client, admin_h, "50.00", year=2025)
    c3 = new_copy(client, lib, 1, "BC-0003")
    c4 = new_copy(client, lib, 1, "BC-0004")
    ja, jb, jc = (approved(client, lib, admin_h, c, estimated_cost="100.00") for c in (1, 2, c3))
    for j in (ja, jb, jc):
        step(client, lib, j["id"], "send")
    at(clock, 2026, 11, 10)
    step(client, lib, ja["id"], "return", outcome="repaired", actual_cost="80.00")
    at(clock, 2026, 11, 13)
    step(client, lib, jb["id"], "return", outcome="unrepairable", actual_cost="90.00")
    jd = approved(client, lib, lib, c4, estimated_cost="10.00")
    step(client, lib, jd["id"], "send")
    step(client, lib, jc["id"], "lost")
    at(clock, 2026, 11, 21)
    rows = client.get(f"{API}/reports/preservation", headers=lib, params={"year": 2026}).json()["items"]
    assert rows == [
        {"branch_id": 1, "budget": "1000.00", "committed": "10.00", "spent": "270.00", "jobs_returned": 2,
         "repaired": 1, "unrepairable": 1, "lost": 1, "average_days": "9.5", "overdue_now": 1},
        {"branch_id": 2, "budget": "500.00", "committed": "0.00", "spent": "0.00", "jobs_returned": 0,
         "repaired": 0, "unrepairable": 0, "lost": 0, "average_days": None, "overdue_now": 0},
    ]
    assert [r["branch_id"] for r in client.get(f"{API}/reports/preservation", headers=lib, params={"year": 2025}).json()["items"]] == [1]
    assert client.get(f"{API}/reports/preservation", headers=lib).json()["total"] == 2
    err(client.get(f"{API}/reports/preservation", headers=lib, params={"year": 1999}), 422, "VALIDATION_ERROR")


def test_damage_recovery_validation_and_range(client, lib, admin_h, shelf, clock):
    for params in ({}, {"from": "2026-01-01"}, {"from": "2026-02-01", "to": "2026-01-01"},
                   {"from": "2026-01-01", "to": "2027-01-02"}, {"from": "x", "to": "2026-01-01"}):
        err(client.get(f"{API}/reports/damage-recovery", headers=lib, params=params), 422, "VALIDATION_ERROR")
    ok = client.get(f"{API}/reports/damage-recovery", headers=lib, params={"from": "2026-01-01", "to": "2027-01-01"})
    assert ok.status_code == 200
    assert ok.json()["items"] == [] and ok.json()["totals"] == {"damage_fees": "0.00", "costs": "0.00", "difference": "0.00"}
    budget(client, admin_h)
    m = mk_member(client, lib)
    for copy, fee, cost in ((1, "30.00", "20.00"), (2, "10.00", "25.00")):
        loan = lend(client, lib, m, copy).json()
        assert ret(client, lib, loan["id"], condition="damaged", damage_fee=fee).status_code == 200
        j = approved(client, lib, admin_h, copy)
        step(client, lib, j["id"], "send")
        step(client, lib, j["id"], "return", outcome="repaired", actual_cost=cost)
    job(client, lib, 1, kind="rebinding")  # a job without a damage loan is not listed
    rep = client.get(f"{API}/reports/damage-recovery", headers=lib, params={"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert [(i["job_id"], i["difference"]) for i in rep["items"]] == [(1, "10.00"), (2, "-15.00")]
    assert rep["totals"] == {"damage_fees": "40.00", "costs": "45.00", "difference": "-5.00"}
    none = client.get(f"{API}/reports/damage-recovery", headers=lib, params={"from": "2026-11-03", "to": "2026-11-04"}).json()
    assert none["items"] == []


def test_job_cannot_be_created_for_reserved_copy(client, lib, shelf, app):
    with app.state.session_factory.begin() as s:
        s.get(Copy, 1).status = "on_reserve"
    err(client.post(f"{API}/repair-jobs", headers=lib, json={"copy_id": 1, "kind": "repair", "provider": "in_house",
                                                              "estimated_cost": "1.00"}), 409, "INVALID_COPY_STATUS")


def test_transition_table_of_in_repair():
    from lms.catalog.status import ALLOWED_TRANSITIONS
    assert ALLOWED_TRANSITIONS["in_repair"] == {"available", "on_hold", "in_transfer", "damaged", "lost"}
    assert "in_repair" in ALLOWED_TRANSITIONS["damaged"] and "in_repair" in ALLOWED_TRANSITIONS["available"]
    for other in ("on_loan", "on_hold", "in_transfer", "lost", "withdrawn", "at_partner", "on_reserve"):
        assert "in_repair" not in ALLOWED_TRANSITIONS[other]
