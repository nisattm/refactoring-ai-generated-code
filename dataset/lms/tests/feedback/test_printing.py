"""Feedback tests: module 29 (Printing and copying). Generated from cases/printing.md."""
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


def test_t_prt_01_a(client, admin, librarian, branch_a):
    """T-PRT-01-a (LIB-PRT-01): 201 active with paper_left 0; 409 CONFLICT; 409 BRANCH_INACTIVE; 403"""
    p = ok(post(client, admin, "printers", {"branch_id": branch_a["id"], "code": "PR-001", "name": "Giriş katı", "color": True, "duplex": True}), 201)
    assert (p["branch_id"], p["code"], p["status"], p["paper_left"], p["color"], p["duplex"]) == (branch_a["id"], "PR-001", "active", 0, True, True)
    err(post(client, admin, "printers", {"branch_id": branch_a["id"], "code": "PR-001", "name": "İkinci", "color": False, "duplex": False}), 409, "CONFLICT")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_printer(client, admin, qq), 409, "BRANCH_INACTIVE")
    assert try_printer(client, librarian, branch_a).status_code == 403


def test_t_prt_03_a(client, admin, branch_a):
    """T-PRT-03-a (LIB-PRT-03): 200 each; 409 PRINTER_RETIRED"""
    p = printer(client, admin, branch_a)
    url = f"/api/v1/printers/{p['id']}"
    for status in ("out_of_service", "active", "retired"):
        assert ok(client.patch(url, headers=admin, json={"status": status}))["status"] == status
    err(client.patch(url, headers=admin, json={"name": "Yeni"}), 409, "PRINTER_RETIRED")


def test_t_prt_05_a(client, admin, librarian, branch_a):
    """T-PRT-05-a (LIB-PRT-05): 200 paper_left 500; 422; 409 PRINTER_RETIRED"""
    p = printer(client, admin, branch_a, paper=0)
    assert ok(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 500}))["paper_left"] == 500
    assert post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 0}).status_code == 422
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "retired"}))
    err(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 10}), 409, "PRINTER_RETIRED")


def test_t_prt_07_a(client, admin, librarian, branch_a):
    """T-PRT-07-a (LIB-PRT-07): 201 queued with copies 1, color and duplex false, sheets 4; 422; 422"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    j = ok(send(client, mh(client, m), p, 4), 201)
    assert (j["member_id"], j["printer_id"], j["status"], j["copies"], j["color"], j["duplex"], j["sheets"]) == (m["id"], p["id"], "queued", 1, False, False, 4)
    assert same(j["submitted_at"], MON, 9) and j["released_at"] is None
    assert send(client, librarian, p, 4).status_code == 422
    assert send(client, mh(client, m), p, 4, member_id=m["id"]).status_code == 422


def test_t_prt_08_a(client, clock, admin, librarian, branch_a):
    """T-PRT-08-a (LIB-PRT-08): MEMBER_PASSIVE; PRINTER_UNAVAILABLE with details.status; PRINTER_NO_COLOR; PRINTER_NO_DUPLEX; MEMBERSHIP_EXPIRED"""
    p = printer(client, admin, branch_a)
    off = printer(client, admin, branch_a)
    ok(client.patch(f"/api/v1/printers/{off['id']}", headers=admin, json={"status": "out_of_service"}))
    gone = member(client, librarian, branch_a)
    deactivate_member(client, librarian, gone["id"])
    err(send(client, librarian, p, member_id=gone["id"]), 409, "MEMBER_PASSIVE")
    m = member(client, librarian, branch_a)
    assert err(send(client, librarian, off, member_id=m["id"]), 409, "PRINTER_UNAVAILABLE")["details"]["status"] == "out_of_service"
    err(send(client, librarian, p, member_id=m["id"], color=True), 409, "PRINTER_NO_COLOR")
    err(send(client, librarian, p, member_id=m["id"], duplex=True), 409, "PRINTER_NO_DUPLEX")
    at(clock, "2027-11-02")
    err(send(client, librarian, p, member_id=m["id"]), 409, "MEMBERSHIP_EXPIRED")


def test_t_prt_09_a(client, admin, librarian, branch_a):
    """T-PRT-09-a (LIB-PRT-09): sheets 10, 6, 2"""
    p = printer(client, admin, branch_a, duplex=True)
    m = member(client, librarian, branch_a)
    sheets = [job(client, librarian, p, m, pages, copies=2, duplex=d)["sheets"] for pages, d in ((5, False), (5, True), (1, True))]
    assert sheets == [10, 6, 2]


def test_t_prt_11_a(client, clock, admin, librarian, branch_a, branch_b):
    """T-PRT-11-a (LIB-PRT-11): [J3, J2, J1] with printer and amount '0.00'; [J3, J1]; [J2]; 403"""
    p1, p2 = printer(client, admin, branch_a), printer(client, admin, branch_b)
    m = member(client, librarian, branch_a)
    j1 = job(client, librarian, p1, m)
    at(clock, MON, 9, 10); j2 = job(client, librarian, p2, m)
    ok(post(client, librarian, f"print-jobs/{j2['id']}/cancel"))
    at(clock, MON, 9, 20); j3 = job(client, librarian, p1, m)
    h = mh(client, m)
    rows = items(get(client, h, f"members/{m['id']}/print-jobs"))
    assert [r["id"] for r in rows] == [j3["id"], j2["id"], j1["id"]]
    assert rows[1]["printer"] == {"id": p2["id"], "code": p2["code"], "branch_id": branch_b["id"]} and rows[0]["amount"] == "0.00"
    assert [r["id"] for r in items(get(client, h, f"members/{m['id']}/print-jobs", status="queued"))] == [j3["id"], j1["id"]]
    assert [r["id"] for r in items(get(client, librarian, "print-jobs", printer_id=p2["id"]))] == [j2["id"]]
    other = mh(client, member(client, librarian, branch_a))
    assert client.get(f"/api/v1/members/{m['id']}/print-jobs", headers=other).status_code == 403


def test_t_prt_13_a(client, clock, admin, librarian, branch_a):
    """T-PRT-13-a (LIB-PRT-13): 200 printed, released_at 10:00; paper_left 94"""
    p = printer(client, admin, branch_a, paper=100)
    j = job(client, librarian, p, member(client, librarian, branch_a), 3, copies=2)
    at(clock, MON, 10)
    out = ok(release(client, librarian, j))
    assert out["status"] == "printed" and same(out["released_at"], MON, 10)
    assert get_printer(client, librarian, p)["paper_left"] == 94


def test_t_prt_15_a(client, admin, librarian, branch_a):
    """T-PRT-15-a (LIB-PRT-15): 200 both"""
    p = printer(client, admin, branch_a)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    inside(client, librarian, branch_a, m)
    j = ok(send(client, mh(client, m), p, 2), 201)
    assert ok(release(client, mh(client, m), j))["status"] == "printed"
    assert ok(release(client, librarian, job(client, librarian, p, o, 2)))["status"] == "printed"


def test_t_prt_17_a(client, admin, librarian, branch_a):
    """T-PRT-17-a (LIB-PRT-17): free_pages 100, pack_pages 20, charged_pages 0; then 0, 0, 2"""
    p = printer(client, admin, branch_a, color=True)
    m = member(client, librarian, branch_a)
    ok(buy_pack(client, librarian, m), 201)
    a = printed(client, librarian, p, m, 120)
    b = printed(client, librarian, p, m, 2, color=True)
    assert [(j["free_pages"], j["pack_pages"], j["charged_pages"]) for j in (a, b)] == [(100, 20, 0), (0, 0, 2)]


def test_t_prt_19_a(client, admin, librarian, branch_a):
    """T-PRT-19-a (LIB-PRT-19): free_pages 5, pack_pages 25, charged_pages 0, no fee; the pack has 25 pages left"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 95)
    pack = ok(buy_pack(client, librarian, m), 201)
    j = printed(client, librarian, p, m, 30)
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"], j["fee_id"]) == (5, 25, 0, None)
    packs = items(get(client, librarian, f"members/{m['id']}/print-packs"))
    assert [(x["id"], x["pages_left"]) for x in packs] == [(pack["id"], 25)]


def test_t_prt_21_a(client, clock, admin, librarian, branch_a):
    """T-PRT-21-a (LIB-PRT-21): free_pages_left 0; then 100"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2026-11-30", 10)
    printed(client, librarian, p, m, 100)
    assert quota(client, librarian, m)["free_pages_left"] == 0
    at(clock, "2026-12-01", 10)
    assert quota(client, librarian, m)["free_pages_left"] == 100


def test_t_prt_23_a(client, admin, librarian, branch_a):
    """T-PRT-23-a (LIB-PRT-23): 200 failed with failed_reason; PRINT_JOB_NOT_PRINTED twice; 422"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    j = printed(client, librarian, p, m, 2)
    assert post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Leke"}).status_code == 422
    out = ok(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    assert (out["status"], out["failed_reason"]) == ("failed", "Kâğıt sıkıştı")
    err(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "PRINT_JOB_NOT_PRINTED")
    q = job(client, librarian, p, m)
    err(post(client, librarian, f"print-jobs/{q['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "PRINT_JOB_NOT_PRINTED")


def test_t_prt_25_a(client, admin, librarian, branch_a):
    """T-PRT-25-a (LIB-PRT-25): Fee waived; free pages used 95; the pack has 50 pages left"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 95)
    ok(buy_pack(client, librarian, m), 201)
    j = printed(client, librarian, p, m, 58)
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"]) == (5, 50, 3)
    assert fee_of(client, librarian, m, j["fee_id"])["amount"] == "1.50"
    ok(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Sayfalar boş çıktı"}))
    assert fee_of(client, librarian, m, j["fee_id"])["status"] == "waived"
    q = quota(client, librarian, m)
    assert (q["free_pages_used"], q["pack_pages_left"]) == (95, 50)


def test_t_prt_27_a(client, admin, librarian, branch_a):
    """T-PRT-27-a (LIB-PRT-27): 201 with 50 pages and an open print_pack fee of 20.00; the fifth with 4 packs left → PACK_LIMIT_REACHED; MEMBER_PASSIVE; 403"""
    m = member(client, librarian, branch_a)
    pack = ok(buy_pack(client, librarian, m), 201)
    assert (pack["pages"], pack["pages_left"], pack["bought_on"]) == (50, 50, MON)
    f = fee_of(client, librarian, m, pack["fee_id"])
    assert (f["kind"], f["amount"], f["status"]) == ("print_pack", "20.00", "open")
    for _ in range(3):
        ok(buy_pack(client, librarian, m), 201)
    err(buy_pack(client, librarian, m), 409, "PACK_LIMIT_REACHED")
    gone = member(client, librarian, branch_a)
    deactivate_member(client, librarian, gone["id"])
    err(buy_pack(client, librarian, gone), 409, "MEMBER_PASSIVE")
    assert buy_pack(client, mh(client, m), m).status_code == 403


def test_t_prt_29_a(client, admin, librarian, branch_a):
    """T-PRT-29-a (LIB-PRT-29): {2026-11, student, 100, 30, 70, 0, 32, 4.00}; October with 0 used; 422"""
    p = printer(client, admin, branch_a, color=True)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 30)
    printed(client, librarian, p, m, 2, color=True)
    q = quota(client, mh(client, m), m)
    keys = ("month", "membership_type", "free_pages", "free_pages_used", "free_pages_left", "pack_pages_left", "pages_printed", "amount_charged")
    assert tuple(q[k] for k in keys) == ("2026-11", "student", 100, 30, 70, 0, 32, "4.00")
    assert quota(client, librarian, m, month="2026-10")["free_pages_used"] == 0
    assert client.get(f"/api/v1/members/{m['id']}/print-quota", headers=librarian, params={"month": "2026-12"}).status_code == 422


def test_t_prt_31_a(client, clock, admin, librarian, branch_a):
    """T-PRT-31-a (LIB-PRT-31): jobs_expired 1; the queued job expired with one print_job_expired notification"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    q = job(client, librarian, p, m)
    printed(client, librarian, p, m)
    at(clock, TUE, 9, 30)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 1
    assert get(client, librarian, f"print-jobs/{q['id']}")["status"] == "expired"
    ns = notes(client, librarian, m["id"], "print_job_expired")
    assert len(ns) == 1 and ns[0]["print_job_id"] == q["id"]


def test_t_prt_33_a(client, admin, librarian, branch_a):
    """T-PRT-33-a (LIB-PRT-33): low_paper false; true; the printer listed"""
    p = printer(client, admin, branch_a, paper=100)
    printer(client, admin, branch_a, paper=500)
    assert get_printer(client, librarian, p)["low_paper"] is False
    printed(client, librarian, p, member(client, librarian, branch_a), 1)
    assert get_printer(client, librarian, p)["low_paper"] is True
    assert [x["id"] for x in items(get(client, librarian, "printers", low_paper="true"))] == [p["id"]]


def test_t_prt_35_a(client, admin, librarian, branch_a):
    """T-PRT-35-a (LIB-PRT-35): Both jobs cancelled, no print_job_cancelled notification; the pack keeps 50 pages"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    js = [job(client, librarian, p, m) for _ in range(2)]
    ok(buy_pack(client, librarian, m), 201)
    ok(post(client, librarian, f"members/{m['id']}/payments", {"amount": "20.00", "method": "cash"}), 201)
    deactivate_member(client, librarian, m["id"])
    assert [get(client, librarian, f"print-jobs/{j['id']}")["status"] for j in js] == ["cancelled", "cancelled"]
    assert notes(client, librarian, m["id"], "print_job_cancelled") == []
    assert [x["pages_left"] for x in items(get(client, librarian, f"members/{m['id']}/print-packs"))] == [50]


def test_t_prt_37_a(client, admin, branch_a):
    """T-PRT-37-a (LIB-PRT-37): 409 BRANCH_IN_USE; 200"""
    qq = create_branch(client, admin, "QQ")
    p = printer(client, admin, qq, paper=0)
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "out_of_service"}))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "retired"}))
    ok(client.patch(url, headers=admin, json={"is_active": False}))


def test_t_prt_39_a(client, admin, librarian, branch_a):
    """T-PRT-39-a (LIB-PRT-39): The first job stays queued; 201 and 200"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    c = inside(client, librarian, branch_a, m)
    j = ok(send(client, mh(client, m), p, 2), 201)
    ok(post(client, librarian, "access/scan", {"branch_id": branch_a["id"], "direction": "out", "card_no": c["card_no"]}))
    assert get(client, librarian, f"print-jobs/{j['id']}")["status"] == "queued"
    o = member(client, librarian, branch_a)
    oj = ok(send(client, mh(client, o), p, 2), 201)
    ok(post(client, mh(client, o), f"print-jobs/{oj['id']}/cancel"))


def test_t_prt_41_a(client, clock, admin, librarian, branch_a):
    """T-PRT-41-a (LIB-PRT-41): Two released, the third refused with OUT_OF_PAPER; paper_left 5"""
    p = printer(client, admin, branch_a, paper=25)
    m = member(client, librarian, branch_a)
    c = inside(client, librarian, branch_a, m)
    js = []
    for mm in (0, 1, 2):
        at(clock, MON, 9, 10 + mm)
        js.append(job(client, librarian, p, m, 10))
    out = ok(post(client, librarian, "print-jobs/release-by-card", {"printer_id": p["id"], "card_no": c["card_no"]}))
    assert out["released"] == [js[0]["id"], js[1]["id"]] and out["refused"] == [{"job_id": js[2]["id"], "code": "OUT_OF_PAPER"}]
    assert get_printer(client, librarian, p)["paper_left"] == 5


def test_t_prt_43_a(client, admin, librarian, branch_a):
    """T-PRT-43-a (LIB-PRT-43): One entry per event (3 print_job_submitted, 2 print_job_released)"""
    p = ok(try_printer(client, admin, branch_a), 201)
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"name": "Yeni ad"}))
    ok(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 2}))
    m = member(client, librarian, branch_a)
    a, b, c = job(client, librarian, p, m), job(client, librarian, p, m, 5), job(client, librarian, p, m)
    ok(release(client, librarian, a))
    err(release(client, librarian, b), 409, "OUT_OF_PAPER")
    ok(post(client, librarian, f"print-jobs/{b['id']}/cancel"))
    ok(release(client, librarian, c))
    ok(post(client, librarian, f"print-jobs/{c['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    ok(buy_pack(client, librarian, m), 201)
    ok(post(client, librarian, "printing/process"))
    counts = {"printer_created": 1, "printer_changed": 1, "printer_refilled": 1, "print_job_submitted": 3, "print_job_released": 2,
              "print_job_cancelled": 1, "print_job_failed": 1, "print_pack_bought": 1, "printing_processed": 1}
    for name, n in counts.items():
        assert len(items(get(client, admin, "audit-log", event=name))) == n, name


def test_t_prt_44_a(client, librarian, branch_a):
    """T-PRT-44-a (LIB-PRT-44): 422; 422; 403"""
    url = "/api/v1/reports/printing"
    assert client.get(url, headers=librarian, params={"from": TUE, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-10"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403


def test_t_prt_45_a(client, admin, librarian, branch_a):
    """T-PRT-45-a (LIB-PRT-45): {jobs_printed 3, pages 15, color_pages 2, sheets 15, free_pages 10, pack_pages 0, charged_pages 5, revenue 4.00, packs_sold 0, jobs_failed 1, refunds_pending 0.00}"""
    p = printer(client, admin, branch_a, color=True)
    s = member(client, librarian, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    printed(client, librarian, p, s, 10)
    printed(client, librarian, p, s, 2, color=True)
    j = printed(client, librarian, p, g, 3)
    ok(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    rows = items(get(client, librarian, "reports/printing", **{"from": MON, "to": MON}))
    keys = ("branch_id", "jobs_printed", "pages", "color_pages", "sheets", "free_pages", "pack_pages", "charged_pages", "revenue", "packs_sold", "jobs_failed", "refunds_pending")
    assert [tuple(r[k] for k in keys) for r in rows] == [(branch_a["id"], 3, 15, 2, 15, 10, 0, 5, "4.00", 0, 1, "0.00")]


def test_t_prt_47_a(client, admin, librarian, branch_a):
    """T-PRT-47-a (LIB-PRT-47): free_pages_left 100; then 75"""
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert get(client, h, "members/me")["free_pages_left"] == 100
    printed(client, librarian, p, m, 25)
    assert get(client, h, "members/me")["free_pages_left"] == 75
