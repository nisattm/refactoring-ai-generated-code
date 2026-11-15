MODULE = "preservation"
TITLE = "module 23 (Preservation)"

HEADER = '''
from datetime import datetime, timedelta, timezone

from support.api import (
    add_copy, create_book, create_branch, error_code, items, lend, member_headers, register_member, report_lost, reserve,
    return_loan,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON = "2026-11-02"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py)


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


def post(client, headers, path, body=None):
    return client.post(f"/api/v1/{path}", headers=headers, json=body)


def get(client, headers, path, **params):
    return ok(client.get(f"/api/v1/{path}", headers=headers, params=params or None))


def member(client, lib, branch, **kw):
    return register_member(client, lib, home_branch_id=branch["id"], **kw)


def copy(client, lib, branch, price="100.00", book=None):
    b = book or create_book(client, lib, title="Eski Kitap")
    return add_copy(client, lib, b["id"], home_branch_id=branch["id"], price=price)


def damaged(client, lib, branch, fee="30.00", price="100.00"):
    """A copy returned damaged at ``branch``: (copy, loan, member)."""
    cp = copy(client, lib, branch, price)
    m = member(client, lib, branch)
    loan = lend(client, lib, m["id"], cp["id"])
    return_loan(client, lib, loan["id"], branch_id=branch["id"], condition="damaged", damage_fee=fee)
    return cp, loan, m


def set_budget(client, admin, branch, amount="10000.00", year=2026):
    return client.put(f"/api/v1/preservation-budgets/{branch['id']}/{year}", headers=admin, json={"amount": amount})


def budget(client, headers, branch, year=2026):
    return get(client, headers, f"preservation-budgets/{branch['id']}/{year}")


def supplier(client, lib):
    _seq[0] += 1
    return ok(post(client, lib, "suppliers", {"name": f"Mücellit {_seq[0]}", "email": None, "phone": None}), 201)


def try_job(client, headers, copy_, kind="repair", provider="in_house", supplier_=None, cost="25.00", **fields):
    body = {"copy_id": copy_["id"], "kind": kind, "provider": provider, "supplier_id": supplier_["id"] if supplier_ else None, "estimated_cost": cost}
    body.update(fields)
    return post(client, headers, "repair-jobs", body)


def job(client, headers, copy_, **kw):
    return ok(try_job(client, headers, copy_, **kw), 201)


def step(client, headers, job_, name, body=None):
    return post(client, headers, f"repair-jobs/{job_['id']}/{name}", body)


def approved(client, headers, copy_, **kw):
    j = job(client, headers, copy_, **kw)
    return ok(step(client, headers, j, "approve"))


def sent(client, headers, copy_, **kw):
    return ok(step(client, headers, approved(client, headers, copy_, **kw), "send"))


def ship(client, headers, supplier_, *jobs):
    return post(client, headers, "repair-shipments", {"supplier_id": supplier_["id"], "job_ids": [j["id"] for j in jobs]})


def give_back(client, headers, job_, outcome="repaired", cost="25.00", note=""):
    return step(client, headers, job_, "return", {"outcome": outcome, "actual_cost": cost, "cost_note": note})


def copy_of(client, lib, copy_id):
    return get(client, lib, f"copies/{copy_id}")


def job_of(client, lib, job_id):
    return get(client, lib, f"repair-jobs/{job_id}")


def inspect(client, lib, copy_, condition, note=""):
    return post(client, lib, f"copies/{copy_['id']}/inspections", {"condition": condition, "note": note})
'''


CASES = [
    # ---------------------------------------------------------------- budgets
    dict(id="T-PRE-01-a", req="LIB-PRE-01", type="Normal", input="Admin sets 5000.00 for branch A in 2026, then 6000.00", expected="200 `{amount 5000.00, committed 0.00, spent 0.00, available 5000.00}`; then `amount` and `available` 6000.00", code='''
def TEST(client, admin, branch_a):
    out = ok(set_budget(client, admin, branch_a, "5000.00"))
    assert (out["branch_id"], out["year"], out["amount"], out["committed"], out["spent"], out["available"]) == (branch_a["id"], 2026, "5000.00", "0.00", "0.00", "5000.00")
    out = ok(set_budget(client, admin, branch_a, "6000.00"))
    assert (out["amount"], out["available"]) == ("6000.00", "6000.00")
'''),
    dict(id="T-PRE-01-b", req="LIB-PRE-01", type="Error", input="Librarian sets a budget; unknown branch; year 1999; amount -1.00; a member reads it", expected="`403`; `404`; `422`; `422`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    assert set_budget(client, librarian, branch_a).status_code == 403
    assert set_budget(client, admin, {"id": 999999}).status_code == 404
    assert set_budget(client, admin, branch_a, year=1999).status_code == 422
    assert set_budget(client, admin, branch_a, "-1.00").status_code == 422
    ok(set_budget(client, admin, branch_a))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/preservation-budgets/{branch_a['id']}/2026", headers=mh).status_code == 403
'''),
    dict(id="T-PRE-02-a", req="LIB-PRE-02", type="Normal", input="Budget 1000.00: jobs approved 100.00, sent 50.00, returned with actual 30.00 (estimated 40.00), lost 20.00, cancelled 70.00; budget of 2027", expected="`committed` 150.00, `spent` 50.00, `available` 800.00; 2027 `404`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a, "1000.00"))
    approved(client, librarian, copy(client, librarian, branch_a), cost="100.00")
    sent(client, librarian, copy(client, librarian, branch_a), cost="50.00")
    ok(give_back(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="40.00"), cost="30.00"))
    ok(step(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="20.00"), "lost"))
    ok(step(client, librarian, approved(client, librarian, copy(client, librarian, branch_a), cost="70.00"), "cancel"))
    b = budget(client, librarian, branch_a)
    assert (b["committed"], b["spent"], b["available"]) == ("150.00", "50.00", "800.00")
    assert client.get(f"/api/v1/preservation-budgets/{branch_a['id']}/2027", headers=librarian).status_code == 404
'''),
    dict(id="T-PRE-03-a", req="LIB-PRE-03", type="Boundary", input="Budget 1000.00 with 150.00 committed and 50.00 spent; set to 199.99; to 200.00", expected="`409 BUDGET_BELOW_USED` with `details.used` 200.00; 200 with `available` 0.00", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a, "1000.00"))
    approved(client, librarian, copy(client, librarian, branch_a), cost="150.00")
    ok(give_back(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="50.00"), cost="50.00"))
    assert err(set_budget(client, admin, branch_a, "199.99"), 409, "BUDGET_BELOW_USED")["details"]["used"] == "200.00"
    assert ok(set_budget(client, admin, branch_a, "200.00"))["available"] == "0.00"
'''),
    # ---------------------------------------------------------------- inspections
    dict(id="T-PRE-04-a", req="LIB-PRE-04", type="Normal", input="Copy inspected `worn` with a note; a lost copy inspected; a member inspects", expected="201; copy `condition` `worn`; `409 INVALID_COPY_STATUS`; `403`", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    out = ok(inspect(client, librarian, cp, "worn", "Sırt yıpranmış"), 201)
    assert (out["copy_id"], out["condition"], out["note"]) == (cp["id"], "worn", "Sırt yıpranmış") and same(out["inspected_at"], MON, 9)
    assert copy_of(client, librarian, cp["id"])["condition"] == "worn"
    gone = copy(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], gone["id"])["id"])
    err(inspect(client, librarian, gone, "good"), 409, "INVALID_COPY_STATUS")
    assert inspect(client, member_headers(client, m), cp, "good").status_code == 403
'''),
    dict(id="T-PRE-05-a", req="LIB-PRE-05", type="Normal", input="Inspections `worn` on Mon and `fragile` on Tue; history", expected="[fragile, worn]; copy `fragile`", code='''
def TEST(client, clock, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, cp, "worn"), 201)
    at(clock, "2026-11-03")
    ok(inspect(client, librarian, cp, "fragile"), 201)
    rows = items(get(client, librarian, f"copies/{cp['id']}/inspections"))
    assert [r["condition"] for r in rows] == ["fragile", "worn"]
    assert copy_of(client, librarian, cp["id"])["condition"] == "fragile"
'''),
    dict(id="T-PRE-06-a", req="LIB-PRE-06", type="Error", input="A `fragile` copy lent; inspected `good` and lent", expected="`409 COPY_FRAGILE`; 201", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, cp, "fragile"), 201)
    m = member(client, librarian, branch_a)
    err(post(client, librarian, "loans", {"member_id": m["id"], "copy_id": cp["id"]}), 409, "COPY_FRAGILE")
    ok(inspect(client, librarian, cp, "good"), 201)
    lend(client, librarian, m["id"], cp["id"])
'''),
    dict(id="T-PRE-07-a", req="LIB-PRE-07", type="Normal", input="Only copy of a book on loan; another member reserves it at A; the copy is inspected `fragile` and returned in good condition", expected="Copy `available`; the reservation stays `waiting`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    ok(inspect(client, librarian, cp, "fragile"), 201)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert copy_of(client, librarian, cp["id"])["status"] == "available"
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "waiting"
'''),
    # ---------------------------------------------------------------- jobs
    dict(id="T-PRE-08-a", req="LIB-PRE-08", type="Normal", input="Librarian creates an in-house `repair` job of 25.00 for a damaged copy at A", expected="201 `requested`, `requested_at`, `branch_id` A, `priority` `normal`, `supplier_id` null", code='''
def TEST(client, librarian, branch_a):
    cp, _, _ = damaged(client, librarian, branch_a)
    j = job(client, librarian, cp, note="Sayfa yırtık")
    assert (j["copy_id"], j["branch_id"], j["kind"], j["provider"], j["supplier_id"], j["priority"], j["estimated_cost"], j["status"], j["note"]) == (cp["id"], branch_a["id"], "repair", "in_house", None, "normal", "25.00", "requested", "Sayfa yırtık")
    assert same(j["requested_at"], MON, 9) and (j["approved_at"], j["due_back"], j["outcome"]) == (None, None, None)
'''),
    dict(id="T-PRE-08-b", req="LIB-PRE-08", type="Error", input="`supplier` without `supplier_id`; `in_house` with one; kind `gluing`; cost -0.01; unknown copy; a member creates a job", expected="`422` five times; `403`", code='''
def TEST(client, librarian, branch_a):
    cp = copy(client, librarian, branch_a)
    sup = supplier(client, librarian)
    assert try_job(client, librarian, cp, provider="supplier").status_code == 422
    assert try_job(client, librarian, cp, supplier_=sup).status_code == 422
    assert try_job(client, librarian, cp, kind="gluing").status_code == 422
    assert try_job(client, librarian, cp, cost="-0.01").status_code == 422
    assert try_job(client, librarian, {"id": 999999}).status_code == 422
    assert try_job(client, member_headers(client, member(client, librarian, branch_a)), cp).status_code == 403
'''),
    dict(id="T-PRE-09-a", req="LIB-PRE-09", type="Error", input="Job for a copy on loan; a second job for a copy with an open job; a job with an inactive supplier", expected="`INVALID_COPY_STATUS` with `details.status` `on_loan`; `COPY_HAS_REPAIR_JOB` with `details.job_id`; `SUPPLIER_INACTIVE`", code='''
def TEST(client, librarian, branch_a):
    out = copy(client, librarian, branch_a)
    lend(client, librarian, member(client, librarian, branch_a)["id"], out["id"])
    assert err(try_job(client, librarian, out), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_loan"
    cp = copy(client, librarian, branch_a)
    j = job(client, librarian, cp)
    assert err(try_job(client, librarian, cp), 409, "COPY_HAS_REPAIR_JOB")["details"]["job_id"] == j["id"]
    sup = supplier(client, librarian)
    ok(client.patch(f"/api/v1/suppliers/{sup['id']}", headers=librarian, json={"is_active": False}))
    err(try_job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup), 409, "SUPPLIER_INACTIVE")
'''),
    dict(id="T-PRE-10-a", req="LIB-PRE-10", type="Error", input="PATCH kind and cost of a requested job; PATCH after approval", expected="200; `409 INVALID_JOB_STATUS` with `details.status` `approved`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    j = job(client, librarian, copy(client, librarian, branch_a))
    url = f"/api/v1/repair-jobs/{j['id']}"
    out = ok(client.patch(url, headers=librarian, json={"kind": "rebinding", "estimated_cost": "80.00"}))
    assert (out["kind"], out["estimated_cost"]) == ("rebinding", "80.00")
    ok(step(client, librarian, j, "approve"))
    assert err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "INVALID_JOB_STATUS")["details"]["status"] == "approved"
'''),
    dict(id="T-PRE-11-a", req="LIB-PRE-11", type="Normal", input="Job for a copy returned damaged; job for an available copy", expected="`loan_id` of that loan; null", code='''
def TEST(client, librarian, branch_a):
    cp, loan, _ = damaged(client, librarian, branch_a)
    assert job(client, librarian, cp)["loan_id"] == loan["id"]
    assert job(client, librarian, copy(client, librarian, branch_a))["loan_id"] is None
'''),
    dict(id="T-PRE-12-a", req="LIB-PRE-12", type="Error", input="Approve without a budget for 2026 (only 2027 set); with a budget; approve again", expected="`409 NO_PRESERVATION_BUDGET`; 200 `approved` with `approved_at`; `409 INVALID_JOB_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    j = job(client, librarian, copy(client, librarian, branch_a))
    ok(set_budget(client, admin, branch_a, year=2027))
    err(step(client, librarian, j, "approve"), 409, "NO_PRESERVATION_BUDGET")
    ok(set_budget(client, admin, branch_a))
    out = ok(step(client, librarian, j, "approve"))
    assert out["status"] == "approved" and same(out["approved_at"], MON, 9)
    err(step(client, librarian, j, "approve"), 409, "INVALID_JOB_STATUS")
'''),
    dict(id="T-PRE-13-a", req="LIB-PRE-13", type="Boundary", input="Librarian approves jobs of 500.00 and 500.01; admin approves the 500.01 job", expected="200; `403`; 200", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a), cost="500.00"), "approve"))
    big = job(client, librarian, copy(client, librarian, branch_a), cost="500.01")
    assert step(client, librarian, big, "approve").status_code == 403
    ok(step(client, admin, big, "approve"))
'''),
    dict(id="T-PRE-14-a", req="LIB-PRE-14", type="Boundary", input="Branches A and B with budgets 1000.00 and 700.00 committed; A: normal jobs of 300.01 and 300.00; B: urgent jobs of 400.01 and 400.00", expected="A: `BUDGET_EXCEEDED` with `details.available` 300.00, then 200; B: `BUDGET_EXCEEDED`, then 200", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    for br in (branch_a, branch_b):
        ok(set_budget(client, admin, br, "1000.00"))
        ok(step(client, admin, job(client, librarian, copy(client, librarian, br), cost="700.00"), "approve"))
    a1 = job(client, librarian, copy(client, librarian, branch_a), cost="300.01")
    assert err(step(client, librarian, a1, "approve"), 409, "BUDGET_EXCEEDED")["details"]["available"] == "300.00"
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a), cost="300.00"), "approve"))
    b1 = job(client, librarian, copy(client, librarian, branch_b), cost="400.01", priority="urgent")
    err(step(client, librarian, b1, "approve"), 409, "BUDGET_EXCEEDED")
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_b), cost="400.00", priority="urgent"), "approve"))
'''),
    dict(id="T-PRE-15-a", req="LIB-PRE-15", type="Normal", input="Cancel a requested job of a damaged copy; cancel an approved job; cancel a sent job", expected="200 `cancelled` with `staff_request`, the copy stays `damaged`; 200; `409 INVALID_JOB_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp, _, _ = damaged(client, librarian, branch_a)
    out = ok(step(client, librarian, job(client, librarian, cp), "cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    assert copy_of(client, librarian, cp["id"])["status"] == "damaged"
    ok(step(client, librarian, approved(client, librarian, copy(client, librarian, branch_a)), "cancel"))
    err(step(client, librarian, sent(client, librarian, copy(client, librarian, branch_a)), "cancel"), 409, "INVALID_JOB_STATUS")
'''),
    dict(id="T-PRE-16-a", req="LIB-PRE-16", type="Normal", input="Approved in-house `repair` job of a damaged copy returned at branch B (home A) is sent", expected="200 `sent`, `sent_at`, `due_back` 2026-11-09; the copy `in_repair` with current branch B", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    ok(set_budget(client, admin, branch_b))
    cp = copy(client, librarian, branch_a)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_b["id"], condition="damaged", damage_fee="10.00")
    j = approved(client, librarian, cp)
    assert j["branch_id"] == branch_b["id"]
    out = ok(step(client, librarian, j, "send"))
    assert (out["status"], out["due_back"]) == ("sent", "2026-11-09") and same(out["sent_at"], MON, 9)
    c = copy_of(client, librarian, cp["id"])
    assert (c["status"], c["current_branch_id"]) == ("in_repair", branch_b["id"])
'''),
    dict(id="T-PRE-16-b", req="LIB-PRE-16", type="Error", input="Send a requested job; an approved supplier job; an approved job whose available copy was lent meanwhile", expected="`INVALID_JOB_STATUS`; `SHIPMENT_REQUIRED`; `INVALID_COPY_STATUS` with `details.status` `on_loan`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    err(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a)), "send"), 409, "INVALID_JOB_STATUS")
    sj = approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=supplier(client, librarian))
    err(step(client, librarian, sj, "send"), 409, "SHIPMENT_REQUIRED")
    cp = copy(client, librarian, branch_a)
    j = approved(client, librarian, cp)
    lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    assert err(step(client, librarian, j, "send"), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_loan"
'''),
    dict(id="T-PRE-17-a", req="LIB-PRE-17", type="Boundary", input="Sent on 2026-11-02: in-house rebinding; in-house conservation; urgent in-house repair; supplier repair; urgent supplier rebinding", expected="`due_back` 2026-11-23; 2026-12-14; 2026-11-06; 2026-11-16; 2026-11-16", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    dues = [sent(client, librarian, copy(client, librarian, branch_a), kind=k, **kw)["due_back"]
            for k, kw in (("rebinding", {}), ("conservation", {}), ("repair", {"priority": "urgent"}))]
    assert dues == ["2026-11-23", "2026-12-14", "2026-11-06"]
    sup = supplier(client, librarian)
    j1 = approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    j2 = approved(client, librarian, copy(client, librarian, branch_a), kind="rebinding", provider="supplier", supplier_=sup, priority="urgent")
    ok(ship(client, librarian, sup, j1, j2), 201)
    assert [job_of(client, librarian, j["id"])["due_back"] for j in (j1, j2)] == ["2026-11-16", "2026-11-16"]
'''),
    dict(id="T-PRE-18-a", req="LIB-PRE-18", type="Normal", input="Copy with home branch A sent for repair at A; returned repaired", expected="While in repair `current_branch_id` A; after the return `available` at A", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp = copy(client, librarian, branch_a)
    j = sent(client, librarian, cp)
    assert copy_of(client, librarian, cp["id"])["current_branch_id"] == branch_a["id"]
    ok(give_back(client, librarian, j))
    c = copy_of(client, librarian, cp["id"])
    assert (c["status"], c["current_branch_id"]) == ("available", branch_a["id"])
'''),
    dict(id="T-PRE-19-a", req="LIB-PRE-19", type="Normal", input="Two approved supplier jobs at branch AA shipped; a third shipped later", expected="201 code `SH-AA-1` with both jobs `sent` with `shipment_id`, copies `in_repair`; then `SH-AA-2`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    sup = supplier(client, librarian)
    c1, c2, c3 = (copy(client, librarian, branch_a) for _ in range(3))
    j1, j2, j3 = (approved(client, librarian, c, provider="supplier", supplier_=sup) for c in (c1, c2, c3))
    sh = ok(ship(client, librarian, sup, j1, j2), 201)
    assert (sh["code"], sh["supplier_id"], sh["branch_id"], sh["job_ids"]) == ("SH-AA-1", sup["id"], branch_a["id"], [j1["id"], j2["id"]])
    assert [(job_of(client, librarian, j["id"])["status"], job_of(client, librarian, j["id"])["shipment_id"]) for j in (j1, j2)] == [("sent", sh["id"])] * 2
    assert [copy_of(client, librarian, c["id"])["status"] for c in (c1, c2)] == ["in_repair", "in_repair"]
    assert ok(ship(client, librarian, sup, j3), 201)["code"] == "SH-AA-2"
'''),
    dict(id="T-PRE-19-b", req="LIB-PRE-19", type="Error", input="Shipment of a good job with: a job of another supplier; an in-house job; a requested job; a job of branch B; empty list; the same job twice", expected="`409 SHIPMENT_MISMATCH` with `details.job_id` four times (the good job stays `approved`); `422`; `422`", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    for br in (branch_a, branch_b):
        ok(set_budget(client, admin, br))
    sup, other = supplier(client, librarian), supplier(client, librarian)
    good = approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    bad = [approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=other),
           approved(client, librarian, copy(client, librarian, branch_a)),
           job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup),
           approved(client, librarian, copy(client, librarian, branch_b), provider="supplier", supplier_=sup)]
    for b in bad:
        assert err(ship(client, librarian, sup, good, b), 409, "SHIPMENT_MISMATCH")["details"]["job_id"] == b["id"]
    assert job_of(client, librarian, good["id"])["status"] == "approved"
    assert ship(client, librarian, sup).status_code == 422
    assert ship(client, librarian, sup, good, good).status_code == 422
'''),
    dict(id="T-PRE-20-a", req="LIB-PRE-20", type="Normal", input="Shipments S1 (2 jobs, one returned) and S2 (1 job) of supplier P; list; filter by another supplier", expected="[S2, S1] with `open_jobs` 1 and 1; empty", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    sup = supplier(client, librarian)
    j1, j2, j3 = (approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup) for _ in range(3))
    s1 = ok(ship(client, librarian, sup, j1, j2), 201)
    s2 = ok(ship(client, librarian, sup, j3), 201)
    ok(give_back(client, librarian, j1))
    rows = items(get(client, librarian, "repair-shipments"))
    assert [(r["id"], r["open_jobs"]) for r in rows] == [(s2["id"], 1), (s1["id"], 1)]
    assert get(client, librarian, "repair-shipments", supplier_id=supplier(client, librarian)["id"])["total"] == 0
'''),
    dict(id="T-PRE-21-a", req="LIB-PRE-21", type="Normal", input="A `worn` copy's job returned `repaired` (actual 20.00); a damaged copy's job returned `unrepairable`; the first returned again", expected="Job `returned` with outcome and cost, copy `available` and `good`; copy `damaged`; `409 INVALID_JOB_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, cp, "worn"), 201)
    j = sent(client, librarian, cp)
    out = ok(give_back(client, librarian, j, cost="20.00"))
    assert (out["status"], out["outcome"], out["actual_cost"]) == ("returned", "repaired", "20.00") and same(out["returned_at"], MON, 9)
    c = copy_of(client, librarian, cp["id"])
    assert (c["status"], c["condition"]) == ("available", "good")
    bad, _, _ = damaged(client, librarian, branch_a)
    ok(give_back(client, librarian, sent(client, librarian, bad), outcome="unrepairable"))
    assert copy_of(client, librarian, bad["id"])["status"] == "damaged"
    err(give_back(client, librarian, j), 409, "INVALID_JOB_STATUS")
'''),
    dict(id="T-PRE-22-a", req="LIB-PRE-22", type="Boundary", input="Jobs estimated 100.00 returned with 120.00 without note; 120.01 without note; 120.01 with a note", expected="200 `cost_overrun` false; `422`; 200 `cost_overrun` true", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    j1, j2 = (sent(client, librarian, copy(client, librarian, branch_a), cost="100.00") for _ in range(2))
    assert ok(give_back(client, librarian, j1, cost="120.00"))["cost_overrun"] is False
    assert give_back(client, librarian, j2, cost="120.01").status_code == 422
    out = ok(give_back(client, librarian, j2, cost="120.01", note="Ek cilt bezi gerekti"))
    assert (out["cost_overrun"], out["cost_note"]) == (True, "Ek cilt bezi gerekti")
'''),
    dict(id="T-PRE-23-a", req="LIB-PRE-23", type="Normal", input="Sent in-house job lost; shipped supplier job of a copy priced 80.00 lost; a requested job reported lost", expected="Job `lost`, copy `lost` with branch null, `claim_amount` null; `claim_amount` 80.00; `409 INVALID_JOB_STATUS`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp = copy(client, librarian, branch_a)
    out = ok(step(client, librarian, sent(client, librarian, cp), "lost"))
    assert (out["status"], out["claim_amount"]) == ("lost", None)
    c = copy_of(client, librarian, cp["id"])
    assert (c["status"], c["current_branch_id"]) == ("lost", None)
    sup = supplier(client, librarian)
    sj = approved(client, librarian, copy(client, librarian, branch_a, price="80.00"), provider="supplier", supplier_=sup)
    ok(ship(client, librarian, sup, sj), 201)
    assert ok(step(client, librarian, sj, "lost"))["claim_amount"] == "80.00"
    err(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a)), "lost"), 409, "INVALID_JOB_STATUS")
'''),
    dict(id="T-PRE-24-a", req="LIB-PRE-24", type="Normal", input="Jobs J1 (sent, due 2026-11-09), J2 (requested, supplier), J3 (sent rebinding); on 2026-11-10 list; `overdue=true`; `provider=supplier`; `status=sent`", expected="[J3, J2, J1]; [J1] with `is_overdue` true, `barcode`, `book_title`; [J2]; [J3, J1]", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp = copy(client, librarian, branch_a)
    j1 = sent(client, librarian, cp)
    j2 = job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=supplier(client, librarian))
    j3 = sent(client, librarian, copy(client, librarian, branch_a), kind="rebinding")
    at(clock, "2026-11-10")
    ids = lambda **p: [x["id"] for x in items(get(client, librarian, "repair-jobs", **p))]
    assert ids() == [j3["id"], j2["id"], j1["id"]]
    rows = items(get(client, librarian, "repair-jobs", overdue="true"))
    assert [(r["id"], r["is_overdue"], r["barcode"], r["book_title"]) for r in rows] == [(j1["id"], True, cp["barcode"], "Eski Kitap")]
    assert ids(provider="supplier") == [j2["id"]]
    assert ids(status="sent") == [j3["id"], j1["id"]]
'''),
    dict(id="T-PRE-25-a", req="LIB-PRE-25", type="Boundary", input="Job sent Mon (due 2026-11-09); process on 2026-11-09, 2026-11-10 and again", expected="`{overdue 0, newly_overdue 0}`; `{1, 1}`; `{1, 0}`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    sent(client, librarian, copy(client, librarian, branch_a))
    out = []
    for day in ("2026-11-09", "2026-11-10", "2026-11-10"):
        at(clock, day)
        r = ok(post(client, librarian, "preservation/process"))
        out.append((r["overdue"], r["newly_overdue"]))
    assert out == [(0, 0), (1, 1), (1, 0)]
'''),
    dict(id="T-PRE-25-b", req="LIB-PRE-25", type="Boundary", input="Job requested on Mon 2026-11-02 09:00; process on 2027-01-01 09:00 and 09:00:01", expected="`expired_requests` 0; 1 and the job `cancelled` with `expired`", code='''
def TEST(client, clock, librarian, branch_a):
    j = job(client, librarian, copy(client, librarian, branch_a))
    at(clock, "2027-01-01", 9, 0, 0)
    assert ok(post(client, librarian, "preservation/process"))["expired_requests"] == 0
    at(clock, "2027-01-01", 9, 0, 1)
    assert ok(post(client, librarian, "preservation/process"))["expired_requests"] == 1
    out = job_of(client, librarian, j["id"])
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "expired")
'''),
    dict(id="T-PRE-26-a", req="LIB-PRE-26", type="Normal", input="At branch A: a damaged copy; a fragile copy; a worn copy lent 30 times; a worn copy lent 29 times; a damaged copy with an open job; a copy at branch B", expected="Damaged (`damaged`), fragile (`fragile`) and the 30-loan copy (`worn_and_used`), by copy id", code='''
def TEST(client, librarian, branch_a, branch_b):
    dmg, _, m = damaged(client, librarian, branch_a)
    frag = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, frag, "fragile"), 201)
    used, less = copy(client, librarian, branch_a), copy(client, librarian, branch_a)
    for cp, n in ((used, 30), (less, 29)):
        for _ in range(n):
            return_loan(client, librarian, lend(client, librarian, m["id"], cp["id"])["id"], branch_id=branch_a["id"])
        ok(inspect(client, librarian, cp, "worn"), 201)
    busy, _, _ = damaged(client, librarian, branch_a)
    job(client, librarian, busy)
    damaged(client, librarian, branch_b)
    rows = get(client, librarian, "preservation/suggestions", branch_id=branch_a["id"])["items"]
    assert [(r["copy_id"], r["reason"]) for r in rows] == [(dmg["id"], "damaged"), (frag["id"], "fragile"), (used["id"], "worn_and_used")]
'''),
    # ---------------------------------------------------------------- effects
    dict(id="T-PRE-27-a", req="LIB-PRE-27", type="Error", input="The only copy of a book is `in_repair`: lent; relocated; book availability", expected="`409 COPY_NOT_AVAILABLE` with `details.status` `in_repair`; `409 INVALID_COPY_STATUS`; `available` 0, `total` 1", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    sent(client, librarian, cp)
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "in_repair"
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    row = get(client, librarian, f"books/{b['id']}")["availability"][0]
    assert (row["available"], row["total"]) == (0, 1)
'''),
    dict(id="T-PRE-28-a", req="LIB-PRE-28", type="Error", input="Damaged copy with a requested job: direct repair; withdrawal; after cancelling the job, direct repair", expected="`409 COPY_HAS_REPAIR_JOB` with `details.job_id` twice; 200", code='''
def TEST(client, librarian, branch_a):
    cp, _, _ = damaged(client, librarian, branch_a)
    j = job(client, librarian, cp)
    assert err(post(client, librarian, f"copies/{cp['id']}/repair"), 409, "COPY_HAS_REPAIR_JOB")["details"]["job_id"] == j["id"]
    err(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Onarılamaz"}), 409, "COPY_HAS_REPAIR_JOB")
    ok(step(client, librarian, j, "cancel"))
    ok(post(client, librarian, f"copies/{cp['id']}/repair"))
'''),
    dict(id="T-PRE-29-a", req="LIB-PRE-29", type="Normal", input="Book with a copy in repair, a worn copy and a good copy; copies with `status=in_repair`; with `condition=worn`", expected="The repaired copy with `open_job_id`; the worn copy; the good copy has `open_job_id` null", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    rep, worn, fine = (copy(client, librarian, branch_a, book=b) for _ in range(3))
    j = sent(client, librarian, rep)
    ok(inspect(client, librarian, worn, "worn"), 201)
    rows = items(get(client, librarian, f"books/{b['id']}/copies", status="in_repair"))
    assert [(r["id"], r["open_job_id"]) for r in rows] == [(rep["id"], j["id"])]
    assert [r["id"] for r in items(get(client, librarian, f"books/{b['id']}/copies", condition="worn"))] == [worn["id"]]
    assert copy_of(client, librarian, fine["id"])["open_job_id"] is None
'''),
    dict(id="T-PRE-30-a", req="LIB-PRE-30", type="Normal", input="The only copy of a book at A is `available` but `fragile`; a member reserves it for pickup at A", expected="201 `waiting`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    ok(inspect(client, librarian, cp, "fragile"), 201)
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    assert (res["status"], res["copy_id"]) == ("waiting", None)
'''),
    dict(id="T-PRE-31-a", req="LIB-PRE-31", type="Error", input="Admin sets a budget for an inactive branch", expected="`409 BRANCH_INACTIVE`", code='''
def TEST(client, admin):
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(set_budget(client, admin, qq), 409, "BRANCH_INACTIVE")
'''),
    dict(id="T-PRE-32-a", req="LIB-PRE-32", type="Error", input="Supplier with a requested job is deactivated; after the job is cancelled", expected="`409 SUPPLIER_HAS_JOBS` with `details.job_ids`; 200", code='''
def TEST(client, librarian, branch_a):
    sup = supplier(client, librarian)
    j = job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    url = f"/api/v1/suppliers/{sup['id']}"
    assert err(client.patch(url, headers=librarian, json={"is_active": False}), 409, "SUPPLIER_HAS_JOBS")["details"]["job_ids"] == [j["id"]]
    ok(step(client, librarian, j, "cancel"))
    ok(client.patch(url, headers=librarian, json={"is_active": False}))
'''),
    dict(id="T-PRE-33-a", req="LIB-PRE-33", type="Normal", input="Book with copies at A (one in repair, due back 2026-11-09; one rebinding due 2026-11-23) and at B; a member reads the book", expected="Row A `expected_back` 2026-11-23, `available` 0; row B `expected_back` null", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    sent(client, librarian, copy(client, librarian, branch_a, book=b))
    sent(client, librarian, copy(client, librarian, branch_a, book=b), kind="rebinding")
    copy(client, librarian, branch_b, book=b)
    mh = member_headers(client, member(client, librarian, branch_a))
    rows = {r["branch_id"]: r for r in get(client, mh, f"books/{b['id']}")["availability"]}
    assert (rows[branch_a["id"]]["expected_back"], rows[branch_a["id"]]["available"]) == ("2026-11-23", 0)
    assert rows[branch_b["id"]]["expected_back"] is None
'''),
    dict(id="T-PRE-34-a", req="LIB-PRE-34", type="Error", input="Copy placed on reserve for a course; a repair job for it", expected="`409 INVALID_COPY_STATUS` with `details.status` `on_reserve`", code='''
def TEST(client, librarian, branch_a):
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    ins = member(client, librarian, branch_a, membership_type="academic")
    c = ok(post(client, librarian, "courses", {"code": "CENG401", "title": "Kurs", "term": "2026-fall", "instructor_id": ins["id"], "branch_id": branch_a["id"], "starts_on": "2026-10-01", "ends_on": "2027-01-15"}), 201)
    ok(post(client, librarian, f"courses/{c['id']}/reading-list", {"book_id": b["id"]}), 201)
    assert copy_of(client, librarian, cp["id"])["status"] == "on_reserve"
    assert err(try_job(client, librarian, cp), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_reserve"
'''),
    dict(id="T-PRE-35-a", req="LIB-PRE-35", type="Normal", input="Budget set; copy inspected; jobs created, changed, approved, sent, returned; a shipment; a job lost; one cancelled; process; audit log", expected="One entry of each event", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    ok(inspect(client, librarian, copy(client, librarian, branch_a), "worn"), 201)
    j = job(client, librarian, copy(client, librarian, branch_a))
    ok(client.patch(f"/api/v1/repair-jobs/{j['id']}", headers=librarian, json={"note": "Not"}))
    ok(step(client, librarian, j, "approve"))
    ok(step(client, librarian, j, "send"))
    ok(give_back(client, librarian, j))
    sup = supplier(client, librarian)
    s = job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    ok(step(client, librarian, s, "approve"))
    ok(ship(client, librarian, sup, s), 201)
    ok(step(client, librarian, s, "lost"))
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a)), "cancel"))
    ok(post(client, librarian, "preservation/process"))
    counts = {"preservation_budget_set": 1, "copy_inspected": 1, "repair_job_created": 3, "repair_job_updated": 1, "repair_job_approved": 2,
              "repair_job_sent": 1, "repair_shipment_sent": 1, "repair_job_returned": 1, "repair_job_lost": 1, "repair_job_cancelled": 1, "preservation_processed": 1}
    for name, n in counts.items():
        got = len(items(get(client, admin, "audit-log", event=name)))
        assert (got >= n if name == "repair_job_sent" else got == n), name
'''),
    dict(id="T-PRE-36-a", req="LIB-PRE-36", type="Normal", input="The member who returned a copy damaged; the copy's job is created, approved, sent and returned", expected="The member's notifications do not change", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    cp, _, m = damaged(client, librarian, branch_a)
    before = get(client, librarian, f"members/{m['id']}/notifications")["total"]
    ok(give_back(client, librarian, sent(client, librarian, cp)))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == before
'''),
    dict(id="T-PRE-37-a", req="LIB-PRE-37", type="Normal", input="Branch A budget 1000.00: job sent Mon returned Fri (repaired, 30.00), job sent Mon returned unrepairable on Wed 2026-11-11 (20.00), job lost, job sent and still out; branch B without budget or jobs; report 2026", expected="Only A: `{budget 1000.00, jobs_returned 2, repaired 1, unrepairable 1, lost 1, average_days 6.5, overdue_now 0}`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a, "1000.00"))
    j1, j2, j3, j4 = (sent(client, librarian, copy(client, librarian, branch_a), kind="conservation") for _ in range(4))
    ok(step(client, librarian, j3, "lost"))
    at(clock, "2026-11-06")
    ok(give_back(client, librarian, j1, cost="30.00"))
    at(clock, "2026-11-11")
    ok(give_back(client, librarian, j2, outcome="unrepairable", cost="20.00"))
    rows = items(get(client, librarian, "reports/preservation", year=2026))
    keys = ("branch_id", "budget", "jobs_returned", "repaired", "unrepairable", "lost", "average_days", "overdue_now")
    assert [tuple(r[k] for k in keys) for r in rows] == [(branch_a["id"], "1000.00", 2, 1, 1, 1, "6.5", 0)]
'''),
    dict(id="T-PRE-38-a", req="LIB-PRE-38", type="Normal", input="Copy returned damaged (fee 30.00) repaired for 20.00; another (fee 10.00) repaired for 25.00; a job without loan; report 2026-11-02 – 2026-11-08", expected="Two rows with differences 10.00 and -15.00; totals `{damage_fees 40.00, costs 45.00, difference -5.00}`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    c1, l1, m1 = damaged(client, librarian, branch_a, "30.00")
    c2, l2, m2 = damaged(client, librarian, branch_a, "10.00")
    j1, j2 = sent(client, librarian, c1), sent(client, librarian, c2)
    ok(give_back(client, librarian, j1, cost="20.00"))
    ok(give_back(client, librarian, j2, cost="25.00"))
    ok(give_back(client, librarian, sent(client, librarian, copy(client, librarian, branch_a)), cost="5.00"))
    out = get(client, librarian, "reports/damage-recovery", **{"from": MON, "to": "2026-11-08"})
    keys = ("job_id", "copy_id", "loan_id", "member_id", "damage_fee", "actual_cost", "difference")
    assert [tuple(r[k] for k in keys) for r in items(out)] == [(j1["id"], c1["id"], l1["id"], m1["id"], "30.00", "20.00", "10.00"), (j2["id"], c2["id"], l2["id"], m2["id"], "10.00", "25.00", "-15.00")]
    assert out["totals"] == {"damage_fees": "40.00", "costs": "45.00", "difference": "-5.00"}
'''),
    dict(id="T-PRE-38-b", req="LIB-PRE-38", type="Error", input="`from` > `to`; 367 days; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/damage-recovery"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-PRE-39-a", req="LIB-PRE-39", type="Normal", input="A copy `in_repair` and a `worn` copy; `GET /api/v1/export`", expected="The keys of 22.1; the copy in repair has status `damaged`; no copy has `condition`", code='''
def TEST(client, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    rep = copy(client, librarian, branch_a)
    sent(client, librarian, rep)
    ok(inspect(client, librarian, copy(client, librarian, branch_a), "worn"), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == rep["id"]] == ["damaged"]
    assert all("condition" not in c for c in out["copies"])
'''),
    dict(id="T-PRE-40-a", req="LIB-PRE-40", type="Normal", input="Copy returned damaged at A (fee 30.00) while another member waits for the book at A; in-house repair 25.00 approved and sent Mon; returned repaired with 20.00 on Fri 2026-11-06", expected="`due_back` 2026-11-09; after the return the copy `on_hold` and the reservation `ready`; damage recovery difference 10.00", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"], condition="damaged", damage_fee="30.00")
    j = sent(client, librarian, cp)
    assert j["due_back"] == "2026-11-09"
    at(clock, "2026-11-06")
    ok(give_back(client, librarian, j, cost="20.00"))
    assert copy_of(client, librarian, cp["id"])["status"] == "on_hold"
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "ready"
    rows = items(get(client, librarian, "reports/damage-recovery", **{"from": MON, "to": "2026-11-08"}))
    assert [r["difference"] for r in rows] == ["10.00"]
'''),
]
