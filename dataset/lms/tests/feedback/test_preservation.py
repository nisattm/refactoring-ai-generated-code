"""Feedback tests: module 23 (Preservation). Generated from cases/preservation.md."""
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


def test_t_pre_01_a(client, admin, branch_a):
    """T-PRE-01-a (LIB-PRE-01): 200 {amount 5000.00, committed 0.00, spent 0.00, available 5000.00}; then amount and available 6000.00"""
    out = ok(set_budget(client, admin, branch_a, "5000.00"))
    assert (out["branch_id"], out["year"], out["amount"], out["committed"], out["spent"], out["available"]) == (branch_a["id"], 2026, "5000.00", "0.00", "0.00", "5000.00")
    out = ok(set_budget(client, admin, branch_a, "6000.00"))
    assert (out["amount"], out["available"]) == ("6000.00", "6000.00")


def test_t_pre_03_a(client, admin, librarian, branch_a):
    """T-PRE-03-a (LIB-PRE-03): 409 BUDGET_BELOW_USED with details.used 200.00; 200 with available 0.00"""
    ok(set_budget(client, admin, branch_a, "1000.00"))
    approved(client, librarian, copy(client, librarian, branch_a), cost="150.00")
    ok(give_back(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="50.00"), cost="50.00"))
    assert err(set_budget(client, admin, branch_a, "199.99"), 409, "BUDGET_BELOW_USED")["details"]["used"] == "200.00"
    assert ok(set_budget(client, admin, branch_a, "200.00"))["available"] == "0.00"


def test_t_pre_05_a(client, clock, librarian, branch_a):
    """T-PRE-05-a (LIB-PRE-05): [fragile, worn]; copy fragile"""
    cp = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, cp, "worn"), 201)
    at(clock, "2026-11-03")
    ok(inspect(client, librarian, cp, "fragile"), 201)
    rows = items(get(client, librarian, f"copies/{cp['id']}/inspections"))
    assert [r["condition"] for r in rows] == ["fragile", "worn"]
    assert copy_of(client, librarian, cp["id"])["condition"] == "fragile"


def test_t_pre_07_a(client, librarian, branch_a):
    """T-PRE-07-a (LIB-PRE-07): Copy available; the reservation stays waiting"""
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    loan = lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    ok(inspect(client, librarian, cp, "fragile"), 201)
    return_loan(client, librarian, loan["id"], branch_id=branch_a["id"])
    assert copy_of(client, librarian, cp["id"])["status"] == "available"
    assert get(client, librarian, f"reservations/{res['id']}")["status"] == "waiting"


def test_t_pre_08_a(client, librarian, branch_a):
    """T-PRE-08-a (LIB-PRE-08): 201 requested, requested_at, branch_id A, priority normal, supplier_id null"""
    cp, _, _ = damaged(client, librarian, branch_a)
    j = job(client, librarian, cp, note="Sayfa yırtık")
    assert (j["copy_id"], j["branch_id"], j["kind"], j["provider"], j["supplier_id"], j["priority"], j["estimated_cost"], j["status"], j["note"]) == (cp["id"], branch_a["id"], "repair", "in_house", None, "normal", "25.00", "requested", "Sayfa yırtık")
    assert same(j["requested_at"], MON, 9) and (j["approved_at"], j["due_back"], j["outcome"]) == (None, None, None)


def test_t_pre_09_a(client, librarian, branch_a):
    """T-PRE-09-a (LIB-PRE-09): INVALID_COPY_STATUS with details.status on_loan; COPY_HAS_REPAIR_JOB with details.job_id; SUPPLIER_INACTIVE"""
    out = copy(client, librarian, branch_a)
    lend(client, librarian, member(client, librarian, branch_a)["id"], out["id"])
    assert err(try_job(client, librarian, out), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_loan"
    cp = copy(client, librarian, branch_a)
    j = job(client, librarian, cp)
    assert err(try_job(client, librarian, cp), 409, "COPY_HAS_REPAIR_JOB")["details"]["job_id"] == j["id"]
    sup = supplier(client, librarian)
    ok(client.patch(f"/api/v1/suppliers/{sup['id']}", headers=librarian, json={"is_active": False}))
    err(try_job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup), 409, "SUPPLIER_INACTIVE")


def test_t_pre_11_a(client, librarian, branch_a):
    """T-PRE-11-a (LIB-PRE-11): loan_id of that loan; null"""
    cp, loan, _ = damaged(client, librarian, branch_a)
    assert job(client, librarian, cp)["loan_id"] == loan["id"]
    assert job(client, librarian, copy(client, librarian, branch_a))["loan_id"] is None


def test_t_pre_13_a(client, admin, librarian, branch_a):
    """T-PRE-13-a (LIB-PRE-13): 200; 403; 200"""
    ok(set_budget(client, admin, branch_a))
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a), cost="500.00"), "approve"))
    big = job(client, librarian, copy(client, librarian, branch_a), cost="500.01")
    assert step(client, librarian, big, "approve").status_code == 403
    ok(step(client, admin, big, "approve"))


def test_t_pre_15_a(client, admin, librarian, branch_a):
    """T-PRE-15-a (LIB-PRE-15): 200 cancelled with staff_request, the copy stays damaged; 200; 409 INVALID_JOB_STATUS"""
    ok(set_budget(client, admin, branch_a))
    cp, _, _ = damaged(client, librarian, branch_a)
    out = ok(step(client, librarian, job(client, librarian, cp), "cancel"))
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "staff_request")
    assert copy_of(client, librarian, cp["id"])["status"] == "damaged"
    ok(step(client, librarian, approved(client, librarian, copy(client, librarian, branch_a)), "cancel"))
    err(step(client, librarian, sent(client, librarian, copy(client, librarian, branch_a)), "cancel"), 409, "INVALID_JOB_STATUS")


def test_t_pre_16_a(client, admin, librarian, branch_a, branch_b):
    """T-PRE-16-a (LIB-PRE-16): 200 sent, sent_at, due_back 2026-11-09; the copy in_repair with current branch B"""
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


def test_t_pre_17_a(client, admin, librarian, branch_a):
    """T-PRE-17-a (LIB-PRE-17): due_back 2026-11-23; 2026-12-14; 2026-11-06; 2026-11-16; 2026-11-16"""
    ok(set_budget(client, admin, branch_a))
    dues = [sent(client, librarian, copy(client, librarian, branch_a), kind=k, **kw)["due_back"]
            for k, kw in (("rebinding", {}), ("conservation", {}), ("repair", {"priority": "urgent"}))]
    assert dues == ["2026-11-23", "2026-12-14", "2026-11-06"]
    sup = supplier(client, librarian)
    j1 = approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    j2 = approved(client, librarian, copy(client, librarian, branch_a), kind="rebinding", provider="supplier", supplier_=sup, priority="urgent")
    ok(ship(client, librarian, sup, j1, j2), 201)
    assert [job_of(client, librarian, j["id"])["due_back"] for j in (j1, j2)] == ["2026-11-16", "2026-11-16"]


def test_t_pre_19_a(client, admin, librarian, branch_a):
    """T-PRE-19-a (LIB-PRE-19): 201 code SH-AA-1 with both jobs sent with shipment_id, copies in_repair; then SH-AA-2"""
    ok(set_budget(client, admin, branch_a))
    sup = supplier(client, librarian)
    c1, c2, c3 = (copy(client, librarian, branch_a) for _ in range(3))
    j1, j2, j3 = (approved(client, librarian, c, provider="supplier", supplier_=sup) for c in (c1, c2, c3))
    sh = ok(ship(client, librarian, sup, j1, j2), 201)
    assert (sh["code"], sh["supplier_id"], sh["branch_id"], sh["job_ids"]) == ("SH-AA-1", sup["id"], branch_a["id"], [j1["id"], j2["id"]])
    assert [(job_of(client, librarian, j["id"])["status"], job_of(client, librarian, j["id"])["shipment_id"]) for j in (j1, j2)] == [("sent", sh["id"])] * 2
    assert [copy_of(client, librarian, c["id"])["status"] for c in (c1, c2)] == ["in_repair", "in_repair"]
    assert ok(ship(client, librarian, sup, j3), 201)["code"] == "SH-AA-2"


def test_t_pre_21_a(client, admin, librarian, branch_a):
    """T-PRE-21-a (LIB-PRE-21): Job returned with outcome and cost, copy available and good; copy damaged; 409 INVALID_JOB_STATUS"""
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


def test_t_pre_23_a(client, admin, librarian, branch_a):
    """T-PRE-23-a (LIB-PRE-23): Job lost, copy lost with branch null, claim_amount null; claim_amount 80.00; 409 INVALID_JOB_STATUS"""
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


def test_t_pre_25_a(client, clock, admin, librarian, branch_a):
    """T-PRE-25-a (LIB-PRE-25): {overdue 0, newly_overdue 0}; {1, 1}; {1, 0}"""
    ok(set_budget(client, admin, branch_a))
    sent(client, librarian, copy(client, librarian, branch_a))
    out = []
    for day in ("2026-11-09", "2026-11-10", "2026-11-10"):
        at(clock, day)
        r = ok(post(client, librarian, "preservation/process"))
        out.append((r["overdue"], r["newly_overdue"]))
    assert out == [(0, 0), (1, 1), (1, 0)]


def test_t_pre_27_a(client, admin, librarian, branch_a, branch_b):
    """T-PRE-27-a (LIB-PRE-27): 409 COPY_NOT_AVAILABLE with details.status in_repair; 409 INVALID_COPY_STATUS; available 0, total 1"""
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    sent(client, librarian, cp)
    r = post(client, librarian, "loans", {"member_id": member(client, librarian, branch_a)["id"], "copy_id": cp["id"]})
    assert err(r, 409, "COPY_NOT_AVAILABLE")["details"]["status"] == "in_repair"
    err(post(client, librarian, "transfers", {"copy_id": cp["id"], "to_branch_id": branch_b["id"]}), 409, "INVALID_COPY_STATUS")
    row = get(client, librarian, f"books/{b['id']}")["availability"][0]
    assert (row["available"], row["total"]) == (0, 1)


def test_t_pre_29_a(client, admin, librarian, branch_a):
    """T-PRE-29-a (LIB-PRE-29): The repaired copy with open_job_id; the worn copy; the good copy has open_job_id null"""
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    rep, worn, fine = (copy(client, librarian, branch_a, book=b) for _ in range(3))
    j = sent(client, librarian, rep)
    ok(inspect(client, librarian, worn, "worn"), 201)
    rows = items(get(client, librarian, f"books/{b['id']}/copies", status="in_repair"))
    assert [(r["id"], r["open_job_id"]) for r in rows] == [(rep["id"], j["id"])]
    assert [r["id"] for r in items(get(client, librarian, f"books/{b['id']}/copies", condition="worn"))] == [worn["id"]]
    assert copy_of(client, librarian, fine["id"])["open_job_id"] is None


def test_t_pre_31_a(client, admin):
    """T-PRE-31-a (LIB-PRE-31): 409 BRANCH_INACTIVE"""
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(set_budget(client, admin, qq), 409, "BRANCH_INACTIVE")


def test_t_pre_33_a(client, admin, librarian, branch_a, branch_b):
    """T-PRE-33-a (LIB-PRE-33): Row A expected_back 2026-11-23, available 0; row B expected_back null"""
    ok(set_budget(client, admin, branch_a))
    b = create_book(client, librarian)
    sent(client, librarian, copy(client, librarian, branch_a, book=b))
    sent(client, librarian, copy(client, librarian, branch_a, book=b), kind="rebinding")
    copy(client, librarian, branch_b, book=b)
    mh = member_headers(client, member(client, librarian, branch_a))
    rows = {r["branch_id"]: r for r in get(client, mh, f"books/{b['id']}")["availability"]}
    assert (rows[branch_a["id"]]["expected_back"], rows[branch_a["id"]]["available"]) == ("2026-11-23", 0)
    assert rows[branch_b["id"]]["expected_back"] is None


def test_t_pre_35_a(client, admin, librarian, branch_a):
    """T-PRE-35-a (LIB-PRE-35): One entry of each event"""
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


def test_t_pre_37_a(client, clock, admin, librarian, branch_a):
    """T-PRE-37-a (LIB-PRE-37): Only A: {budget 1000.00, jobs_returned 2, repaired 1, unrepairable 1, lost 1, average_days 6.5, overdue_now 0}"""
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


def test_t_pre_38_a(client, admin, librarian, branch_a):
    """T-PRE-38-a (LIB-PRE-38): Two rows with differences 10.00 and -15.00; totals {damage_fees 40.00, costs 45.00, difference -5.00}"""
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


def test_t_pre_39_a(client, admin, librarian, branch_a):
    """T-PRE-39-a (LIB-PRE-39): The keys of 22.1; the copy in repair has status damaged; no copy has condition"""
    ok(set_budget(client, admin, branch_a))
    rep = copy(client, librarian, branch_a)
    sent(client, librarian, rep)
    ok(inspect(client, librarian, copy(client, librarian, branch_a), "worn"), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
    assert [c["status"] for c in out["copies"] if c["id"] == rep["id"]] == ["damaged"]
    assert all("condition" not in c for c in out["copies"])
