"""Heldout tests: module 29 (Printing and copying). Generated from cases/printing.md."""
from datetime import datetime, timedelta, timezone

from support.api import (
    create_branch, deactivate_member, error_code, items, member_fees, member_headers, register_member,
)

TR = timezone(timedelta(hours=3))
_seq = [0]
MON, TUE, SAT = "2026-11-02", "2026-11-03", "2026-11-07"
# the clock starts on Monday 2026-11-02 09:00 (conftest.py); branches are open 08:00-20:00 on working days


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


def mh(client, m):
    return member_headers(client, m)


def try_printer(client, admin, branch, **fields):
    _seq[0] += 1
    body = {"branch_id": branch["id"], "code": f"PR-{_seq[0]:03d}", "name": f"Yazıcı {_seq[0]}", "color": False, "duplex": False}
    body.update(fields)
    return post(client, admin, "printers", body)


def printer(client, admin, branch, paper=1000, **fields):
    """An active printer of ``branch`` refilled with ``paper`` sheets."""
    p = ok(try_printer(client, admin, branch, **fields), 201)
    if paper:
        p = ok(post(client, admin, f"printers/{p['id']}/refill", {"sheets": paper}))
    return p


def send(client, headers, p, pages=1, member_id=None, **fields):
    body = {"printer_id": p["id"], "title": "Ödev raporu", "pages": pages}
    if member_id is not None:
        body["member_id"] = member_id
    body.update(fields)
    return post(client, headers, "print-jobs", body)


def job(client, lib, p, m, pages=1, **fields):
    """A queued job of member ``m`` sent by staff."""
    return ok(send(client, lib, p, pages, member_id=m["id"], **fields), 201)


def release(client, headers, j):
    return post(client, headers, f"print-jobs/{j['id']}/release")


def printed(client, lib, p, m, pages=1, **fields):
    """A job of ``m`` sent and released by staff."""
    return ok(release(client, lib, job(client, lib, p, m, pages, **fields)))


def quota(client, headers, m, **params):
    return get(client, headers, f"members/{m['id']}/print-quota", **params)


def buy_pack(client, lib, m):
    return post(client, lib, f"members/{m['id']}/print-packs")


def inside(client, lib, branch, m):
    """Issue a card to ``m`` and let them enter ``branch`` (module 28)."""
    c = ok(post(client, lib, f"members/{m['id']}/cards"), 201)
    ok(post(client, lib, "access/scan", {"branch_id": branch["id"], "direction": "in", "card_no": c["card_no"]}))
    return c


def notes(client, lib, member_id, type_):
    return items(get(client, lib, f"members/{member_id}/notifications", type=type_))


def fee_of(client, lib, m, fee_id):
    return [f for f in items(member_fees(client, lib, m["id"])) if f["id"] == fee_id][0]


def get_printer(client, headers, p):
    return get(client, headers, f"printers/{p['id']}")


def test_t_prt_02_a(client, admin, librarian, branch_a, branch_b):
    """T-PRT-02-a (LIB-PRT-02): [PR-001, PR-002, PR-003]; [PR-002, PR-003]; [PR-003]"""
    printer(client, admin, branch_a, code="PR-003", color=True)
    printer(client, admin, branch_b, code="PR-001")
    printer(client, admin, branch_a, code="PR-002")
    h = mh(client, member(client, librarian, branch_a))
    codes = lambda **f: [p["code"] for p in items(get(client, h, "printers", **f))]
    assert codes() == ["PR-001", "PR-002", "PR-003"]
    assert codes(branch_id=branch_a["id"]) == ["PR-002", "PR-003"]
    assert codes(color="true") == ["PR-003"]


def test_t_prt_04_a(client, admin, librarian, branch_a):
    """T-PRT-04-a (LIB-PRT-04): The color job cancelled with one print_job_cancelled notification; then the plain job cancelled"""
    p = printer(client, admin, branch_a, color=True, duplex=True)
    m = member(client, librarian, branch_a)
    cj = job(client, librarian, p, m, 2, color=True)
    pj = job(client, librarian, p, m, 2)
    url = f"/api/v1/printers/{p['id']}"
    ok(client.patch(url, headers=admin, json={"color": False}))
    status = lambda j: get(client, librarian, f"print-jobs/{j['id']}")["status"]
    assert (status(cj), status(pj)) == ("cancelled", "queued")
    ns = notes(client, librarian, m["id"], "print_job_cancelled")
    assert len(ns) == 1 and ns[0]["print_job_id"] == cj["id"] and "Ödev raporu" in ns[0]["message"]
    ok(client.patch(url, headers=admin, json={"status": "out_of_service"}))
    assert status(pj) == "cancelled" and len(notes(client, librarian, m["id"], "print_job_cancelled")) == 2


def test_t_prt_06_a(client, admin, librarian, branch_a):
    """T-PRT-06-a (LIB-PRT-06): PAPER_CAPACITY_EXCEEDED with details.paper_left 4900; 5000"""
    p = printer(client, admin, branch_a, paper=4900)
    assert err(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 101}), 409, "PAPER_CAPACITY_EXCEEDED")["details"]["paper_left"] == 4900
    assert ok(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 100}))["paper_left"] == 5000


def test_t_prt_08_b(client, admin, librarian, branch_a):
    """T-PRT-08-b (LIB-PRT-08): 409 PRINT_QUEUE_FULL; 201"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    js = [job(client, librarian, p, m) for _ in range(3)]
    err(send(client, librarian, p, member_id=m["id"]), 409, "PRINT_QUEUE_FULL")
    ok(post(client, librarian, f"print-jobs/{js[0]['id']}/cancel"))
    job(client, librarian, p, m)


def test_t_prt_10_a(client, clock, admin, librarian, branch_a):
    """T-PRT-10-a (LIB-PRT-10): DAILY_PAGE_LIMIT with details.remaining 20; 201; Tue 201"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 150)
    q1 = job(client, librarian, p, m, 30)
    assert err(send(client, librarian, p, 21, member_id=m["id"]), 409, "DAILY_PAGE_LIMIT")["details"]["remaining"] == 20
    q2 = job(client, librarian, p, m, 20)
    at(clock, TUE)
    for q in (q1, q2):
        ok(post(client, librarian, f"print-jobs/{q['id']}/cancel"))
    job(client, librarian, p, m, 200)


def test_t_prt_12_a(client, admin, librarian, branch_a):
    """T-PRT-12-a (LIB-PRT-12): 200 cancelled; 409 PRINT_JOB_NOT_QUEUED with details.status cancelled; 403"""
    p = printer(client, admin, branch_a)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    j, oj = job(client, librarian, p, m), job(client, librarian, p, o)
    h = mh(client, m)
    assert ok(post(client, h, f"print-jobs/{j['id']}/cancel"))["status"] == "cancelled"
    assert err(post(client, h, f"print-jobs/{j['id']}/cancel"), 409, "PRINT_JOB_NOT_QUEUED")["details"]["status"] == "cancelled"
    assert post(client, h, f"print-jobs/{oj['id']}/cancel").status_code == 403


def test_t_prt_14_a(client, clock, admin, librarian, branch_a):
    """T-PRT-14-a (LIB-PRT-14): PRINT_JOB_NOT_QUEUED; BRANCH_NOT_OPEN; NOT_IN_BRANCH with details.branch_id A; OUT_OF_PAPER"""
    p = printer(client, admin, branch_a, paper=10)
    m = member(client, librarian, branch_a)
    c = job(client, librarian, p, m)
    ok(post(client, librarian, f"print-jobs/{c['id']}/cancel"))
    err(release(client, librarian, c), 409, "PRINT_JOB_NOT_QUEUED")
    j = job(client, librarian, p, m, 20)
    assert err(release(client, mh(client, m), j), 409, "NOT_IN_BRANCH")["details"]["branch_id"] == branch_a["id"]
    err(release(client, librarian, j), 409, "OUT_OF_PAPER")
    at(clock, SAT, 10)
    err(release(client, librarian, j), 409, "BRANCH_NOT_OPEN")


def test_t_prt_16_a(client, admin, librarian, branch_a):
    """T-PRT-16-a (LIB-PRT-16): OUT_OF_PAPER with details.paper_left 10; printed, paper_left 0"""
    p = printer(client, admin, branch_a, paper=10)
    m = member(client, librarian, branch_a)
    assert err(release(client, librarian, job(client, librarian, p, m, 11)), 409, "OUT_OF_PAPER")["details"]["paper_left"] == 10
    ok(release(client, librarian, job(client, librarian, p, m, 10)))
    assert get_printer(client, librarian, p)["paper_left"] == 0


def test_t_prt_18_a(client, admin, librarian, branch_a):
    """T-PRT-18-a (LIB-PRT-18): Open printing fee 2.00 with print_job_id, stored in fee_id; one fee_created notification; the student job has no fee"""
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    j = printed(client, librarian, p, g, 4)
    f = fee_of(client, librarian, g, j["fee_id"])
    assert (f["kind"], f["amount"], f["status"], f["print_job_id"]) == ("printing", "2.00", "open", j["id"])
    assert len(notes(client, librarian, g["id"], "fee_created")) == 1
    s = member(client, librarian, branch_a)
    assert printed(client, librarian, p, s, 4)["fee_id"] is None


def test_t_prt_20_a(client, admin, librarian, branch_a):
    """T-PRT-20-a (LIB-PRT-20): charged_pages 6, fee 12.00; fee 3.50"""
    p = printer(client, admin, branch_a, color=True)
    g = member(client, librarian, branch_a, membership_type="guest")
    a = printed(client, librarian, p, g, 3, copies=2, color=True)
    b = printed(client, librarian, p, g, 7)
    assert a["charged_pages"] == 6
    assert [fee_of(client, librarian, g, j["fee_id"])["amount"] for j in (a, b)] == ["12.00", "3.50"]


def test_t_prt_22_a(client, admin, librarian, branch_a):
    """T-PRT-22-a (LIB-PRT-22): MEMBER_BLOCKED_BY_DEBT with details.amount 3.50; printed; printed from the pack"""
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    printed(client, librarian, p, g, 93)
    assert get(client, librarian, f"members/{g['id']}/balance")["total_debt"] == "46.50"
    assert err(release(client, librarian, job(client, librarian, p, g, 7)), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["amount"] == "3.50"
    ok(release(client, librarian, job(client, librarian, p, g, 6)))
    ok(buy_pack(client, librarian, g), 201)
    assert printed(client, librarian, p, g, 10)["pack_pages"] == 10


def test_t_prt_24_a(client, admin, librarian, branch_a):
    """T-PRT-24-a (LIB-PRT-24): The paid fee stays paid; the student's used free pages decrease by 10; one print_job_failed notification each"""
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    gj = printed(client, librarian, p, g, 4)
    ok(post(client, librarian, f"members/{g['id']}/payments", {"amount": "2.00", "method": "cash"}), 201)
    ok(post(client, librarian, f"print-jobs/{gj['id']}/fail", {"reason": "Mürekkep bitti"}))
    assert fee_of(client, librarian, g, gj["fee_id"])["status"] == "paid"
    s = member(client, librarian, branch_a)
    sj = printed(client, librarian, p, s, 10)
    assert quota(client, librarian, s)["free_pages_used"] == 10
    ok(post(client, librarian, f"print-jobs/{sj['id']}/fail", {"reason": "Mürekkep bitti"}))
    assert quota(client, librarian, s)["free_pages_used"] == 0
    for x, j in ((g, gj), (s, sj)):
        ns = notes(client, librarian, x["id"], "print_job_failed")
        assert len(ns) == 1 and ns[0]["print_job_id"] == j["id"]


def test_t_prt_26_a(client, clock, admin, librarian, branch_a):
    """T-PRT-26-a (LIB-PRT-26): failed; FAIL_WINDOW_CLOSED"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, MON, 10)
    a, b = printed(client, librarian, p, m, 1), printed(client, librarian, p, m, 1)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"print-jobs/{a['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    at(clock, TUE, 10, 1)
    err(post(client, librarian, f"print-jobs/{b['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "FAIL_WINDOW_CLOSED")


def test_t_prt_28_a(client, admin, librarian, branch_a):
    """T-PRT-28-a (LIB-PRT-28): [first, second]; [first]"""
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    first = ok(buy_pack(client, librarian, g), 201)
    second = ok(buy_pack(client, librarian, g), 201)
    printed(client, librarian, p, g, 50)
    h = mh(client, g)
    assert [x["id"] for x in items(get(client, h, f"members/{g['id']}/print-packs"))] == [first["id"], second["id"]]
    assert [x["id"] for x in items(get(client, h, f"members/{g['id']}/print-packs", with_pages_left="false"))] == [first["id"]]


def test_t_prt_30_a(client, admin, librarian, branch_a):
    """T-PRT-30-a (LIB-PRT-30): free_pages 0, free_pages_left 0; the job is charged (1.00)"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 100)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "+905551112233", "university_id": None}))
    q = quota(client, librarian, m)
    assert (q["free_pages"], q["free_pages_left"]) == (0, 0)
    j = printed(client, librarian, p, m, 2)
    assert fee_of(client, librarian, m, j["fee_id"])["amount"] == "1.00"


def test_t_prt_32_a(client, clock, admin, librarian, branch_a):
    """T-PRT-32-a (LIB-PRT-32): jobs_expired 0; then 1"""
    p = printer(client, admin, branch_a)
    at(clock, MON, 10)
    job(client, librarian, p, member(client, librarian, branch_a))
    at(clock, TUE, 9, 59)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 0
    at(clock, TUE, 10)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 1


def test_t_prt_34_a(client, admin, librarian, branch_a):
    """T-PRT-34-a (LIB-PRT-34): outstanding_fees 22.50; both fees paid"""
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    j = printed(client, librarian, p, g, 5)
    pack = ok(buy_pack(client, librarian, g), 201)
    assert get(client, librarian, f"members/{g['id']}/balance")["outstanding_fees"] == "22.50"
    ok(post(client, librarian, f"members/{g['id']}/payments", {"amount": "22.50", "method": "cash"}), 201)
    assert [fee_of(client, librarian, g, i)["status"] for i in (j["fee_id"], pack["fee_id"])] == ["paid", "paid"]


def test_t_prt_36_a(client, admin, librarian, branch_a):
    """T-PRT-36-a (LIB-PRT-36): Summary printing {free_pages_left 60, pack_pages_left 50, queued_jobs 1}"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 40)
    ok(buy_pack(client, librarian, m), 201)
    job(client, librarian, p, m)
    assert get(client, librarian, f"members/{m['id']}/summary")["printing"] == {"free_pages_left": 60, "pack_pages_left": 50, "queued_jobs": 1}


def test_t_prt_38_a(client, clock, admin, librarian, branch_a):
    """T-PRT-38-a (LIB-PRT-38): Sent 201; release BRANCH_NOT_OPEN"""
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10)
    err(release(client, librarian, job(client, librarian, p, m)), 409, "BRANCH_NOT_OPEN")


def test_t_prt_40_a(client, admin, librarian, branch_a):
    """T-PRT-40-a (LIB-PRT-40): released the two ids, refused []; the other job stays queued; CARD_NOT_ACTIVE; 404; refused with NOT_IN_BRANCH"""
    p, other = printer(client, admin, branch_a), printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    c = inside(client, librarian, branch_a, m)
    j1, j2, j3 = job(client, librarian, p, m), job(client, librarian, p, m), job(client, librarian, other, m)
    out = ok(post(client, librarian, "print-jobs/release-by-card", {"printer_id": p["id"], "card_no": c["card_no"]}))
    assert (sorted(out["released"]), out["refused"]) == (sorted([j1["id"], j2["id"]]), [])
    assert get(client, librarian, f"print-jobs/{j3['id']}")["status"] == "queued"
    o = member(client, librarian, branch_a)
    oc = ok(post(client, librarian, f"members/{o['id']}/cards"), 201)
    oj = job(client, librarian, p, o)
    out = ok(post(client, librarian, "print-jobs/release-by-card", {"printer_id": p["id"], "card_no": oc["card_no"]}))
    assert (out["released"], out["refused"]) == ([], [{"job_id": oj["id"], "code": "NOT_IN_BRANCH"}])
    ok(post(client, librarian, f"cards/{oc['card_no']}/report", {"reason": "lost"}))
    err(post(client, librarian, "print-jobs/release-by-card", {"printer_id": p["id"], "card_no": oc["card_no"]}), 409, "CARD_NOT_ACTIVE")
    assert post(client, librarian, "print-jobs/release-by-card", {"printer_id": p["id"], "card_no": "LC99999999"}).status_code == 404


def test_t_prt_42_a(client, admin, librarian, branch_a):
    """T-PRT-42-a (LIB-PRT-42): No notifications"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    before = len(items(get(client, librarian, f"members/{m['id']}/notifications")))
    printed(client, librarian, p, m, 3)
    j = ok(send(client, mh(client, m), p, 2), 201)
    ok(post(client, mh(client, m), f"print-jobs/{j['id']}/cancel"))
    assert len(items(get(client, librarian, f"members/{m['id']}/notifications"))) == before


def test_t_prt_44_b(client, admin, librarian, branch_a, branch_b):
    """T-PRT-44-b (LIB-PRT-44): Rows [A (all 0), B {jobs_printed 1, pages 4, sheets 2, free_pages 4, packs_sold 1, revenue 0.00}]; with branch_id B only B"""
    printer(client, admin, branch_a)
    pb = printer(client, admin, branch_b, duplex=True)
    m = member(client, librarian, branch_b)
    printed(client, librarian, pb, m, 4, duplex=True)
    ok(buy_pack(client, librarian, m), 201)
    rows = items(get(client, librarian, "reports/printing", **{"from": MON, "to": "2026-11-08"}))
    assert [r["branch_id"] for r in rows] == [branch_a["id"], branch_b["id"]]
    b = rows[1]
    assert (b["jobs_printed"], b["pages"], b["sheets"], b["free_pages"], b["packs_sold"], b["revenue"]) == (1, 4, 2, 4, 1, "0.00")
    assert rows[0]["jobs_printed"] == 0
    only = items(get(client, librarian, "reports/printing", **{"from": MON, "to": "2026-11-08", "branch_id": branch_b["id"]}))
    assert [r["branch_id"] for r in only] == [branch_b["id"]]


def test_t_prt_46_a(client, admin, librarian, branch_a):
    """T-PRT-46-a (LIB-PRT-46): The export has exactly the keys of 22.1"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 2)
    ok(buy_pack(client, librarian, m), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
