"""Heldout tests: module 23 (Preservation). Generated from cases/preservation.md."""
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


def test_t_pre_01_b(client, admin, librarian, branch_a):
    """T-PRE-01-b (LIB-PRE-01): 403; 404; 422; 422; 403"""
    assert set_budget(client, librarian, branch_a).status_code == 403
    assert set_budget(client, admin, {"id": 999999}).status_code == 404
    assert set_budget(client, admin, branch_a, year=1999).status_code == 422
    assert set_budget(client, admin, branch_a, "-1.00").status_code == 422
    ok(set_budget(client, admin, branch_a))
    mh = member_headers(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/preservation-budgets/{branch_a['id']}/2026", headers=mh).status_code == 403


def test_t_pre_02_a(client, admin, librarian, branch_a):
    """T-PRE-02-a (LIB-PRE-02): committed 150.00, spent 50.00, available 800.00; 2027 404"""
    ok(set_budget(client, admin, branch_a, "1000.00"))
    approved(client, librarian, copy(client, librarian, branch_a), cost="100.00")
    sent(client, librarian, copy(client, librarian, branch_a), cost="50.00")
    ok(give_back(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="40.00"), cost="30.00"))
    ok(step(client, librarian, sent(client, librarian, copy(client, librarian, branch_a), cost="20.00"), "lost"))
    ok(step(client, librarian, approved(client, librarian, copy(client, librarian, branch_a), cost="70.00"), "cancel"))
    b = budget(client, librarian, branch_a)
    assert (b["committed"], b["spent"], b["available"]) == ("150.00", "50.00", "800.00")
    assert client.get(f"/api/v1/preservation-budgets/{branch_a['id']}/2027", headers=librarian).status_code == 404


def test_t_pre_04_a(client, librarian, branch_a):
    """T-PRE-04-a (LIB-PRE-04): 201; copy condition worn; 409 INVALID_COPY_STATUS; 403"""
    cp = copy(client, librarian, branch_a)
    out = ok(inspect(client, librarian, cp, "worn", "Sırt yıpranmış"), 201)
    assert (out["copy_id"], out["condition"], out["note"]) == (cp["id"], "worn", "Sırt yıpranmış") and same(out["inspected_at"], MON, 9)
    assert copy_of(client, librarian, cp["id"])["condition"] == "worn"
    gone = copy(client, librarian, branch_a)
    m = member(client, librarian, branch_a)
    report_lost(client, librarian, lend(client, librarian, m["id"], gone["id"])["id"])
    err(inspect(client, librarian, gone, "good"), 409, "INVALID_COPY_STATUS")
    assert inspect(client, member_headers(client, m), cp, "good").status_code == 403


def test_t_pre_06_a(client, librarian, branch_a):
    """T-PRE-06-a (LIB-PRE-06): 409 COPY_FRAGILE; 201"""
    cp = copy(client, librarian, branch_a)
    ok(inspect(client, librarian, cp, "fragile"), 201)
    m = member(client, librarian, branch_a)
    err(post(client, librarian, "loans", {"member_id": m["id"], "copy_id": cp["id"]}), 409, "COPY_FRAGILE")
    ok(inspect(client, librarian, cp, "good"), 201)
    lend(client, librarian, m["id"], cp["id"])


def test_t_pre_08_b(client, librarian, branch_a):
    """T-PRE-08-b (LIB-PRE-08): 422 five times; 403"""
    cp = copy(client, librarian, branch_a)
    sup = supplier(client, librarian)
    assert try_job(client, librarian, cp, provider="supplier").status_code == 422
    assert try_job(client, librarian, cp, supplier_=sup).status_code == 422
    assert try_job(client, librarian, cp, kind="gluing").status_code == 422
    assert try_job(client, librarian, cp, cost="-0.01").status_code == 422
    assert try_job(client, librarian, {"id": 999999}).status_code == 422
    assert try_job(client, member_headers(client, member(client, librarian, branch_a)), cp).status_code == 403


def test_t_pre_10_a(client, admin, librarian, branch_a):
    """T-PRE-10-a (LIB-PRE-10): 200; 409 INVALID_JOB_STATUS with details.status approved"""
    ok(set_budget(client, admin, branch_a))
    j = job(client, librarian, copy(client, librarian, branch_a))
    url = f"/api/v1/repair-jobs/{j['id']}"
    out = ok(client.patch(url, headers=librarian, json={"kind": "rebinding", "estimated_cost": "80.00"}))
    assert (out["kind"], out["estimated_cost"]) == ("rebinding", "80.00")
    ok(step(client, librarian, j, "approve"))
    assert err(client.patch(url, headers=librarian, json={"note": "X"}), 409, "INVALID_JOB_STATUS")["details"]["status"] == "approved"


def test_t_pre_12_a(client, admin, librarian, branch_a):
    """T-PRE-12-a (LIB-PRE-12): 409 NO_PRESERVATION_BUDGET; 200 approved with approved_at; 409 INVALID_JOB_STATUS"""
    j = job(client, librarian, copy(client, librarian, branch_a))
    ok(set_budget(client, admin, branch_a, year=2027))
    err(step(client, librarian, j, "approve"), 409, "NO_PRESERVATION_BUDGET")
    ok(set_budget(client, admin, branch_a))
    out = ok(step(client, librarian, j, "approve"))
    assert out["status"] == "approved" and same(out["approved_at"], MON, 9)
    err(step(client, librarian, j, "approve"), 409, "INVALID_JOB_STATUS")


def test_t_pre_14_a(client, admin, librarian, branch_a, branch_b):
    """T-PRE-14-a (LIB-PRE-14): A: BUDGET_EXCEEDED with details.available 300.00, then 200; B: BUDGET_EXCEEDED, then 200"""
    for br in (branch_a, branch_b):
        ok(set_budget(client, admin, br, "1000.00"))
        ok(step(client, admin, job(client, librarian, copy(client, librarian, br), cost="700.00"), "approve"))
    a1 = job(client, librarian, copy(client, librarian, branch_a), cost="300.01")
    assert err(step(client, librarian, a1, "approve"), 409, "BUDGET_EXCEEDED")["details"]["available"] == "300.00"
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a), cost="300.00"), "approve"))
    b1 = job(client, librarian, copy(client, librarian, branch_b), cost="400.01", priority="urgent")
    err(step(client, librarian, b1, "approve"), 409, "BUDGET_EXCEEDED")
    ok(step(client, librarian, job(client, librarian, copy(client, librarian, branch_b), cost="400.00", priority="urgent"), "approve"))


def test_t_pre_16_b(client, admin, librarian, branch_a):
    """T-PRE-16-b (LIB-PRE-16): INVALID_JOB_STATUS; SHIPMENT_REQUIRED; INVALID_COPY_STATUS with details.status on_loan"""
    ok(set_budget(client, admin, branch_a))
    err(step(client, librarian, job(client, librarian, copy(client, librarian, branch_a)), "send"), 409, "INVALID_JOB_STATUS")
    sj = approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=supplier(client, librarian))
    err(step(client, librarian, sj, "send"), 409, "SHIPMENT_REQUIRED")
    cp = copy(client, librarian, branch_a)
    j = approved(client, librarian, cp)
    lend(client, librarian, member(client, librarian, branch_a)["id"], cp["id"])
    assert err(step(client, librarian, j, "send"), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_loan"


def test_t_pre_18_a(client, admin, librarian, branch_a):
    """T-PRE-18-a (LIB-PRE-18): While in repair current_branch_id A; after the return available at A"""
    ok(set_budget(client, admin, branch_a))
    cp = copy(client, librarian, branch_a)
    j = sent(client, librarian, cp)
    assert copy_of(client, librarian, cp["id"])["current_branch_id"] == branch_a["id"]
    ok(give_back(client, librarian, j))
    c = copy_of(client, librarian, cp["id"])
    assert (c["status"], c["current_branch_id"]) == ("available", branch_a["id"])


def test_t_pre_19_b(client, admin, librarian, branch_a, branch_b):
    """T-PRE-19-b (LIB-PRE-19): 409 SHIPMENT_MISMATCH with details.job_id four times (the good job stays approved); 422; 422"""
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


def test_t_pre_20_a(client, admin, librarian, branch_a):
    """T-PRE-20-a (LIB-PRE-20): [S2, S1] with open_jobs 1 and 1; empty"""
    ok(set_budget(client, admin, branch_a))
    sup = supplier(client, librarian)
    j1, j2, j3 = (approved(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup) for _ in range(3))
    s1 = ok(ship(client, librarian, sup, j1, j2), 201)
    s2 = ok(ship(client, librarian, sup, j3), 201)
    ok(give_back(client, librarian, j1))
    rows = items(get(client, librarian, "repair-shipments"))
    assert [(r["id"], r["open_jobs"]) for r in rows] == [(s2["id"], 1), (s1["id"], 1)]
    assert get(client, librarian, "repair-shipments", supplier_id=supplier(client, librarian)["id"])["total"] == 0


def test_t_pre_22_a(client, admin, librarian, branch_a):
    """T-PRE-22-a (LIB-PRE-22): 200 cost_overrun false; 422; 200 cost_overrun true"""
    ok(set_budget(client, admin, branch_a))
    j1, j2 = (sent(client, librarian, copy(client, librarian, branch_a), cost="100.00") for _ in range(2))
    assert ok(give_back(client, librarian, j1, cost="120.00"))["cost_overrun"] is False
    assert give_back(client, librarian, j2, cost="120.01").status_code == 422
    out = ok(give_back(client, librarian, j2, cost="120.01", note="Ek cilt bezi gerekti"))
    assert (out["cost_overrun"], out["cost_note"]) == (True, "Ek cilt bezi gerekti")


def test_t_pre_24_a(client, clock, admin, librarian, branch_a):
    """T-PRE-24-a (LIB-PRE-24): [J3, J2, J1]; [J1] with is_overdue true, barcode, book_title; [J2]; [J3, J1]"""
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


def test_t_pre_25_b(client, clock, librarian, branch_a):
    """T-PRE-25-b (LIB-PRE-25): expired_requests 0; 1 and the job cancelled with expired"""
    j = job(client, librarian, copy(client, librarian, branch_a))
    at(clock, "2027-01-01", 9, 0, 0)
    assert ok(post(client, librarian, "preservation/process"))["expired_requests"] == 0
    at(clock, "2027-01-01", 9, 0, 1)
    assert ok(post(client, librarian, "preservation/process"))["expired_requests"] == 1
    out = job_of(client, librarian, j["id"])
    assert (out["status"], out["cancel_reason"]) == ("cancelled", "expired")


def test_t_pre_26_a(client, librarian, branch_a, branch_b):
    """T-PRE-26-a (LIB-PRE-26): Damaged (damaged), fragile (fragile) and the 30-loan copy (worn_and_used), by copy id"""
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


def test_t_pre_28_a(client, librarian, branch_a):
    """T-PRE-28-a (LIB-PRE-28): 409 COPY_HAS_REPAIR_JOB with details.job_id twice; 200"""
    cp, _, _ = damaged(client, librarian, branch_a)
    j = job(client, librarian, cp)
    assert err(post(client, librarian, f"copies/{cp['id']}/repair"), 409, "COPY_HAS_REPAIR_JOB")["details"]["job_id"] == j["id"]
    err(post(client, librarian, f"copies/{cp['id']}/withdraw", {"reason": "Onarılamaz"}), 409, "COPY_HAS_REPAIR_JOB")
    ok(step(client, librarian, j, "cancel"))
    ok(post(client, librarian, f"copies/{cp['id']}/repair"))


def test_t_pre_30_a(client, librarian, branch_a):
    """T-PRE-30-a (LIB-PRE-30): 201 waiting"""
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    ok(inspect(client, librarian, cp, "fragile"), 201)
    res = reserve(client, librarian, book_id=b["id"], pickup_branch_id=branch_a["id"], member_id=member(client, librarian, branch_a)["id"])
    assert (res["status"], res["copy_id"]) == ("waiting", None)


def test_t_pre_32_a(client, librarian, branch_a):
    """T-PRE-32-a (LIB-PRE-32): 409 SUPPLIER_HAS_JOBS with details.job_ids; 200"""
    sup = supplier(client, librarian)
    j = job(client, librarian, copy(client, librarian, branch_a), provider="supplier", supplier_=sup)
    url = f"/api/v1/suppliers/{sup['id']}"
    assert err(client.patch(url, headers=librarian, json={"is_active": False}), 409, "SUPPLIER_HAS_JOBS")["details"]["job_ids"] == [j["id"]]
    ok(step(client, librarian, j, "cancel"))
    ok(client.patch(url, headers=librarian, json={"is_active": False}))


def test_t_pre_34_a(client, librarian, branch_a):
    """T-PRE-34-a (LIB-PRE-34): 409 INVALID_COPY_STATUS with details.status on_reserve"""
    b = create_book(client, librarian)
    cp = copy(client, librarian, branch_a, book=b)
    ins = member(client, librarian, branch_a, membership_type="academic")
    c = ok(post(client, librarian, "courses", {"code": "CENG401", "title": "Kurs", "term": "2026-fall", "instructor_id": ins["id"], "branch_id": branch_a["id"], "starts_on": "2026-10-01", "ends_on": "2027-01-15"}), 201)
    ok(post(client, librarian, f"courses/{c['id']}/reading-list", {"book_id": b["id"]}), 201)
    assert copy_of(client, librarian, cp["id"])["status"] == "on_reserve"
    assert err(try_job(client, librarian, cp), 409, "INVALID_COPY_STATUS")["details"]["status"] == "on_reserve"


def test_t_pre_36_a(client, admin, librarian, branch_a):
    """T-PRE-36-a (LIB-PRE-36): The member's notifications do not change"""
    ok(set_budget(client, admin, branch_a))
    cp, _, m = damaged(client, librarian, branch_a)
    before = get(client, librarian, f"members/{m['id']}/notifications")["total"]
    ok(give_back(client, librarian, sent(client, librarian, cp)))
    assert get(client, librarian, f"members/{m['id']}/notifications")["total"] == before


def test_t_pre_38_b(client, librarian, branch_a):
    """T-PRE-38-b (LIB-PRE-38): 422; 422; 403"""
    url = "/api/v1/reports/damage-recovery"
    assert client.get(url, headers=librarian, params={"from": "2026-11-05", "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-02"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_pre_40_a(client, clock, admin, librarian, branch_a):
    """T-PRE-40-a (LIB-PRE-40): due_back 2026-11-09; after the return the copy on_hold and the reservation ready; damage recovery difference 10.00"""
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
