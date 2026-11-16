MODULE = "printing"
TITLE = "module 29 (Printing and copying)"

HEADER = '''
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
'''


CASES = [
    # ---------------------------------------------------------------- printers
    dict(id="T-PRT-01-a", req="LIB-PRT-01", type="Error", input="Admin creates PR-001 at A; the same code again; a printer of an inactive branch; a librarian creates one", expected="201 `active` with `paper_left` 0; `409 CONFLICT`; `409 BRANCH_INACTIVE`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = ok(post(client, admin, "printers", {"branch_id": branch_a["id"], "code": "PR-001", "name": "Giriş katı", "color": True, "duplex": True}), 201)
    assert (p["branch_id"], p["code"], p["status"], p["paper_left"], p["color"], p["duplex"]) == (branch_a["id"], "PR-001", "active", 0, True, True)
    err(post(client, admin, "printers", {"branch_id": branch_a["id"], "code": "PR-001", "name": "İkinci", "color": False, "duplex": False}), 409, "CONFLICT")
    qq = create_branch(client, admin, "QQ")
    ok(client.patch(f"/api/v1/branches/{qq['id']}", headers=admin, json={"is_active": False}))
    err(try_printer(client, admin, qq), 409, "BRANCH_INACTIVE")
    assert try_printer(client, librarian, branch_a).status_code == 403
'''),
    dict(id="T-PRT-02-a", req="LIB-PRT-02", type="Normal", input="Printers PR-003 (A, color), PR-001 (B), PR-002 (A); a member lists; filters `branch_id` A and `color` true", expected="[PR-001, PR-002, PR-003]; [PR-002, PR-003]; [PR-003]", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
    printer(client, admin, branch_a, code="PR-003", color=True)
    printer(client, admin, branch_b, code="PR-001")
    printer(client, admin, branch_a, code="PR-002")
    h = mh(client, member(client, librarian, branch_a))
    codes = lambda **f: [p["code"] for p in items(get(client, h, "printers", **f))]
    assert codes() == ["PR-001", "PR-002", "PR-003"]
    assert codes(branch_id=branch_a["id"]) == ["PR-002", "PR-003"]
    assert codes(color="true") == ["PR-003"]
'''),
    dict(id="T-PRT-03-a", req="LIB-PRT-03", type="Error", input="Printer set `out_of_service`, back to `active`, `retired`; then renamed", expected="200 each; `409 PRINTER_RETIRED`", code='''
def TEST(client, admin, branch_a):
    p = printer(client, admin, branch_a)
    url = f"/api/v1/printers/{p['id']}"
    for status in ("out_of_service", "active", "retired"):
        assert ok(client.patch(url, headers=admin, json={"status": status}))["status"] == status
    err(client.patch(url, headers=admin, json={"name": "Yeni"}), 409, "PRINTER_RETIRED")
'''),
    dict(id="T-PRT-04-a", req="LIB-PRT-04", type="Normal", input="Color duplex printer with a color job and a plain job queued; `color` set false; then `out_of_service`", expected="The color job `cancelled` with one `print_job_cancelled` notification; then the plain job `cancelled`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-05-a", req="LIB-PRT-05", type="Error", input="Librarian refills 500 sheets; 0 sheets; a retired printer", expected="200 `paper_left` 500; `422`; `409 PRINTER_RETIRED`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, paper=0)
    assert ok(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 500}))["paper_left"] == 500
    assert post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 0}).status_code == 422
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "retired"}))
    err(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 10}), 409, "PRINTER_RETIRED")
'''),
    dict(id="T-PRT-06-a", req="LIB-PRT-06", type="Boundary", input="`paper_left` 4900: refill 101; refill 100", expected="`PAPER_CAPACITY_EXCEEDED` with `details.paper_left` 4900; 5000", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, paper=4900)
    assert err(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 101}), 409, "PAPER_CAPACITY_EXCEEDED")["details"]["paper_left"] == 4900
    assert ok(post(client, librarian, f"printers/{p['id']}/refill", {"sheets": 100}))["paper_left"] == 5000
'''),
    # ---------------------------------------------------------------- jobs
    dict(id="T-PRT-07-a", req="LIB-PRT-07", type="Error", input="A member sends 4 pages; the librarian sends without `member_id`; the member sends with `member_id`", expected="201 `queued` with copies 1, color and duplex false, `sheets` 4; `422`; `422`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    j = ok(send(client, mh(client, m), p, 4), 201)
    assert (j["member_id"], j["printer_id"], j["status"], j["copies"], j["color"], j["duplex"], j["sheets"]) == (m["id"], p["id"], "queued", 1, False, False, 4)
    assert same(j["submitted_at"], MON, 9) and j["released_at"] is None
    assert send(client, librarian, p, 4).status_code == 422
    assert send(client, mh(client, m), p, 4, member_id=m["id"]).status_code == 422
'''),
    dict(id="T-PRT-08-a", req="LIB-PRT-08", type="Error", input="A passive member; printer `out_of_service`; color on a black-and-white printer; duplex on a simplex printer; a member whose membership ended (2027-11-02)", expected="`MEMBER_PASSIVE`; `PRINTER_UNAVAILABLE` with `details.status`; `PRINTER_NO_COLOR`; `PRINTER_NO_DUPLEX`; `MEMBERSHIP_EXPIRED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-08-b", req="LIB-PRT-08", type="Boundary", input="A member with 3 queued jobs sends a fourth; after cancelling one, again", expected="`409 PRINT_QUEUE_FULL`; 201", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    js = [job(client, librarian, p, m) for _ in range(3)]
    err(send(client, librarian, p, member_id=m["id"]), 409, "PRINT_QUEUE_FULL")
    ok(post(client, librarian, f"print-jobs/{js[0]['id']}/cancel"))
    job(client, librarian, p, m)
'''),
    dict(id="T-PRT-09-a", req="LIB-PRT-09", type="Normal", input="5 pages × 2 copies without and with duplex; 1 page × 2 copies with duplex", expected="`sheets` 10, 6, 2", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, duplex=True)
    m = member(client, librarian, branch_a)
    sheets = [job(client, librarian, p, m, pages, copies=2, duplex=d)["sheets"] for pages, d in ((5, False), (5, True), (1, True))]
    assert sheets == [10, 6, 2]
'''),
    dict(id="T-PRT-10-a", req="LIB-PRT-10", type="Boundary", input="150 pages printed today and a queued job of 30: jobs of 21 and 20 pages; on Tue after cancelling the queued jobs, 200 pages", expected="`DAILY_PAGE_LIMIT` with `details.remaining` 20; 201; Tue 201", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-11-a", req="LIB-PRT-11", type="Normal", input="Jobs J1 (P1, 09:00), J2 (P2, 09:10, cancelled), J3 (P1, 09:20); member list; `status=queued`; `printer_id` P2; another member reads", expected="[J3, J2, J1] with `printer` and `amount` \"0.00\"; [J3, J1]; [J2]; `403`", code='''
def TEST(client, clock, admin, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-PRT-12-a", req="LIB-PRT-12", type="Error", input="A member cancels a queued job; cancels it again; cancels another member's job", expected="200 `cancelled`; `409 PRINT_JOB_NOT_QUEUED` with `details.status` `cancelled`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    j, oj = job(client, librarian, p, m), job(client, librarian, p, o)
    h = mh(client, m)
    assert ok(post(client, h, f"print-jobs/{j['id']}/cancel"))["status"] == "cancelled"
    assert err(post(client, h, f"print-jobs/{j['id']}/cancel"), 409, "PRINT_JOB_NOT_QUEUED")["details"]["status"] == "cancelled"
    assert post(client, h, f"print-jobs/{oj['id']}/cancel").status_code == 403
'''),
    # ---------------------------------------------------------------- release and charging
    dict(id="T-PRT-13-a", req="LIB-PRT-13", type="Normal", input="Librarian releases a job of 3 pages × 2 copies at 10:00 (paper 100)", expected="200 `printed`, `released_at` 10:00; `paper_left` 94", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, paper=100)
    j = job(client, librarian, p, member(client, librarian, branch_a), 3, copies=2)
    at(clock, MON, 10)
    out = ok(release(client, librarian, j))
    assert out["status"] == "printed" and same(out["released_at"], MON, 10)
    assert get_printer(client, librarian, p)["paper_left"] == 94
'''),
    dict(id="T-PRT-14-a", req="LIB-PRT-14", type="Error", input="Release a cancelled job; a job on Saturday; the member releases while not inside branch A; a job of 20 sheets with 10 left", expected="`PRINT_JOB_NOT_QUEUED`; `BRANCH_NOT_OPEN`; `NOT_IN_BRANCH` with `details.branch_id` A; `OUT_OF_PAPER`", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-15-a", req="LIB-PRT-15", type="Normal", input="A member inside A releases own job; the librarian releases a job of a member who is not inside", expected="200 both", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m, o = member(client, librarian, branch_a), member(client, librarian, branch_a)
    inside(client, librarian, branch_a, m)
    j = ok(send(client, mh(client, m), p, 2), 201)
    assert ok(release(client, mh(client, m), j))["status"] == "printed"
    assert ok(release(client, librarian, job(client, librarian, p, o, 2)))["status"] == "printed"
'''),
    dict(id="T-PRT-16-a", req="LIB-PRT-16", type="Boundary", input="`paper_left` 10: a job of 11 sheets; a job of 10 sheets", expected="`OUT_OF_PAPER` with `details.paper_left` 10; printed, `paper_left` 0", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, paper=10)
    m = member(client, librarian, branch_a)
    assert err(release(client, librarian, job(client, librarian, p, m, 11)), 409, "OUT_OF_PAPER")["details"]["paper_left"] == 10
    ok(release(client, librarian, job(client, librarian, p, m, 10)))
    assert get_printer(client, librarian, p)["paper_left"] == 0
'''),
    dict(id="T-PRT-17-a", req="LIB-PRT-17", type="Normal", input="Student with a pack: black-and-white job of 120 pages; then a color job of 2 pages", expected="`free_pages` 100, `pack_pages` 20, `charged_pages` 0; then 0, 0, 2", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, color=True)
    m = member(client, librarian, branch_a)
    ok(buy_pack(client, librarian, m), 201)
    a = printed(client, librarian, p, m, 120)
    b = printed(client, librarian, p, m, 2, color=True)
    assert [(j["free_pages"], j["pack_pages"], j["charged_pages"]) for j in (a, b)] == [(100, 20, 0), (0, 0, 2)]
'''),
    dict(id="T-PRT-18-a", req="LIB-PRT-18", type="Normal", input="Guest job of 4 black-and-white pages; student job of 4 pages", expected="Open `printing` fee 2.00 with `print_job_id`, stored in `fee_id`; one `fee_created` notification; the student job has no fee", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    j = printed(client, librarian, p, g, 4)
    f = fee_of(client, librarian, g, j["fee_id"])
    assert (f["kind"], f["amount"], f["status"], f["print_job_id"]) == ("printing", "2.00", "open", j["id"])
    assert len(notes(client, librarian, g["id"], "fee_created")) == 1
    s = member(client, librarian, branch_a)
    assert printed(client, librarian, p, s, 4)["fee_id"] is None
'''),
    dict(id="T-PRT-19-a", req="LIB-PRT-19", type="Normal", input="Student who used 95 free pages, with a pack of 50: black-and-white job of 30 pages", expected="`free_pages` 5, `pack_pages` 25, `charged_pages` 0, no fee; the pack has 25 pages left", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 95)
    pack = ok(buy_pack(client, librarian, m), 201)
    j = printed(client, librarian, p, m, 30)
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"], j["fee_id"]) == (5, 25, 0, None)
    packs = items(get(client, librarian, f"members/{m['id']}/print-packs"))
    assert [(x["id"], x["pages_left"]) for x in packs] == [(pack["id"], 25)]
'''),
    dict(id="T-PRT-20-a", req="LIB-PRT-20", type="Normal", input="Guest: color job of 3 pages × 2 copies; black-and-white job of 7 pages", expected="`charged_pages` 6, fee 12.00; fee 3.50", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, color=True)
    g = member(client, librarian, branch_a, membership_type="guest")
    a = printed(client, librarian, p, g, 3, copies=2, color=True)
    b = printed(client, librarian, p, g, 7)
    assert a["charged_pages"] == 6
    assert [fee_of(client, librarian, g, j["fee_id"])["amount"] for j in (a, b)] == ["12.00", "3.50"]
'''),
    dict(id="T-PRT-21-a", req="LIB-PRT-21", type="Boundary", input="Student prints 100 pages on 2026-11-30; quota on 2026-11-30 and on 2026-12-01", expected="`free_pages_left` 0; then 100", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, "2026-11-30", 10)
    printed(client, librarian, p, m, 100)
    assert quota(client, librarian, m)["free_pages_left"] == 0
    at(clock, "2026-12-01", 10)
    assert quota(client, librarian, m)["free_pages_left"] == 100
'''),
    dict(id="T-PRT-22-a", req="LIB-PRT-22", type="Boundary", input="Guest with total debt 46.50: a job of 7 pages; a job of 6 pages; after buying a pack, a job of 10 pages", expected="`MEMBER_BLOCKED_BY_DEBT` with `details.amount` 3.50; printed; printed from the pack", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    printed(client, librarian, p, g, 93)
    assert get(client, librarian, f"members/{g['id']}/balance")["total_debt"] == "46.50"
    assert err(release(client, librarian, job(client, librarian, p, g, 7)), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["amount"] == "3.50"
    ok(release(client, librarian, job(client, librarian, p, g, 6)))
    ok(buy_pack(client, librarian, g), 201)
    assert printed(client, librarian, p, g, 10)["pack_pages"] == 10
'''),
    # ---------------------------------------------------------------- failed jobs, packs, quota
    dict(id="T-PRT-23-a", req="LIB-PRT-23", type="Error", input="Fail a printed job with a reason; fail it again; fail a queued job; a reason of 4 characters", expected="200 `failed` with `failed_reason`; `PRINT_JOB_NOT_PRINTED` twice; `422`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    j = printed(client, librarian, p, m, 2)
    assert post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Leke"}).status_code == 422
    out = ok(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    assert (out["status"], out["failed_reason"]) == ("failed", "Kâğıt sıkıştı")
    err(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "PRINT_JOB_NOT_PRINTED")
    q = job(client, librarian, p, m)
    err(post(client, librarian, f"print-jobs/{q['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "PRINT_JOB_NOT_PRINTED")
'''),
    dict(id="T-PRT-24-a", req="LIB-PRT-24", type="Normal", input="A guest's charged job of 4 pages is paid (2.00), then fails; a student's free job of 10 pages fails", expected="The paid fee stays `paid`; the student's used free pages decrease by 10; one `print_job_failed` notification each", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-25-a", req="LIB-PRT-25", type="Normal", input="Student with 95 free pages used and a pack: a job of 33 pages (5 free, 25 pack, 3 charged, fee 1.50) fails", expected="Fee `waived`; free pages used 95; the pack has 50 pages left", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 95)
    ok(buy_pack(client, librarian, m), 201)
    j = printed(client, librarian, p, m, 33)
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"]) == (5, 25, 3)
    assert fee_of(client, librarian, m, j["fee_id"])["amount"] == "1.50"
    ok(post(client, librarian, f"print-jobs/{j['id']}/fail", {"reason": "Sayfalar boş çıktı"}))
    assert fee_of(client, librarian, m, j["fee_id"])["status"] == "waived"
    q = quota(client, librarian, m)
    assert (q["free_pages_used"], q["pack_pages_left"]) == (95, 50)
'''),
    dict(id="T-PRT-26-a", req="LIB-PRT-26", type="Boundary", input="Two jobs released Mon 10:00; one fails on Tue 10:00, the other on Tue 10:01", expected="`failed`; `FAIL_WINDOW_CLOSED`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, MON, 10)
    a, b = printed(client, librarian, p, m, 1), printed(client, librarian, p, m, 1)
    at(clock, TUE, 10)
    ok(post(client, librarian, f"print-jobs/{a['id']}/fail", {"reason": "Kâğıt sıkıştı"}))
    at(clock, TUE, 10, 1)
    err(post(client, librarian, f"print-jobs/{b['id']}/fail", {"reason": "Kâğıt sıkıştı"}), 409, "FAIL_WINDOW_CLOSED")
'''),
    dict(id="T-PRT-27-a", req="LIB-PRT-27", type="Error", input="Buy a pack; four more packs; a pack for a passive member; a member buys", expected="201 with 50 pages and an open `print_pack` fee of 20.00; the fifth with 4 packs left → `PACK_LIMIT_REACHED`; `MEMBER_PASSIVE`; `403`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-28-a", req="LIB-PRT-28", type="Normal", input="Guest with two packs, the first used up; the member lists packs; `with_pages_left=false`", expected="[first, second]; [first]", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    first = ok(buy_pack(client, librarian, g), 201)
    second = ok(buy_pack(client, librarian, g), 201)
    printed(client, librarian, p, g, 50)
    h = mh(client, g)
    assert [x["id"] for x in items(get(client, h, f"members/{g['id']}/print-packs"))] == [first["id"], second["id"]]
    assert [x["id"] for x in items(get(client, h, f"members/{g['id']}/print-packs", with_pages_left="false"))] == [first["id"]]
'''),
    dict(id="T-PRT-29-a", req="LIB-PRT-29", type="Error", input="Student printed 30 free pages and a color job of 2 pages; the member reads the quota; `month` 2026-10; `month` 2026-12", expected="`{2026-11, student, 100, 30, 70, 0, 32, 4.00}`; October with 0 used; `422`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, color=True)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 30)
    printed(client, librarian, p, m, 2, color=True)
    q = quota(client, mh(client, m), m)
    keys = ("month", "membership_type", "free_pages", "free_pages_used", "free_pages_left", "pack_pages_left", "pages_printed", "amount_charged")
    assert tuple(q[k] for k in keys) == ("2026-11", "student", 100, 30, 70, 0, 32, "4.00")
    assert quota(client, librarian, m, month="2026-10")["free_pages_used"] == 0
    assert client.get(f"/api/v1/members/{m['id']}/print-quota", headers=librarian, params={"month": "2026-12"}).status_code == 422
'''),
    dict(id="T-PRT-30-a", req="LIB-PRT-30", type="Normal", input="Student uses 100 free pages, becomes a guest; quota; a job of 2 pages", expected="`free_pages` 0, `free_pages_left` 0; the job is charged (1.00)", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 100)
    ok(client.patch(f"/api/v1/members/{m['id']}", headers=librarian, json={"membership_type": "guest", "phone": "+905551112233", "university_id": None}))
    q = quota(client, librarian, m)
    assert (q["free_pages"], q["free_pages_left"]) == (0, 0)
    j = printed(client, librarian, p, m, 2)
    assert fee_of(client, librarian, m, j["fee_id"])["amount"] == "1.00"
'''),
    dict(id="T-PRT-31-a", req="LIB-PRT-31", type="Normal", input="Two jobs sent Mon 09:00, one released; process on Tue 09:30", expected="`jobs_expired` 1; the queued job `expired` with one `print_job_expired` notification", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    q = job(client, librarian, p, m)
    printed(client, librarian, p, m)
    at(clock, TUE, 9, 30)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 1
    assert get(client, librarian, f"print-jobs/{q['id']}")["status"] == "expired"
    ns = notes(client, librarian, m["id"], "print_job_expired")
    assert len(ns) == 1 and ns[0]["print_job_id"] == q["id"]
'''),
    dict(id="T-PRT-32-a", req="LIB-PRT-32", type="Boundary", input="Job sent Mon 10:00; process on Tue 09:59 and Tue 10:00", expected="`jobs_expired` 0; then 1", code='''
def TEST(client, clock, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    at(clock, MON, 10)
    job(client, librarian, p, member(client, librarian, branch_a))
    at(clock, TUE, 9, 59)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 0
    at(clock, TUE, 10)
    assert ok(post(client, librarian, "printing/process"))["jobs_expired"] == 1
'''),
    dict(id="T-PRT-33-a", req="LIB-PRT-33", type="Boundary", input="Printer with 100 sheets; after releasing 1 sheet; filter `low_paper=true`", expected="`low_paper` false; true; the printer listed", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a, paper=100)
    printer(client, admin, branch_a, paper=500)
    assert get_printer(client, librarian, p)["low_paper"] is False
    printed(client, librarian, p, member(client, librarian, branch_a), 1)
    assert get_printer(client, librarian, p)["low_paper"] is True
    assert [x["id"] for x in items(get(client, librarian, "printers", low_paper="true"))] == [p["id"]]
'''),
    # ---------------------------------------------------------------- effects and reports
    dict(id="T-PRT-34-a", req="LIB-PRT-34", type="Normal", input="Guest with a printing fee of 2.50 and a pack fee of 20.00; balance; payment of 22.50", expected="`outstanding_fees` 22.50; both fees `paid`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    g = member(client, librarian, branch_a, membership_type="guest")
    j = printed(client, librarian, p, g, 5)
    pack = ok(buy_pack(client, librarian, g), 201)
    assert get(client, librarian, f"members/{g['id']}/balance")["outstanding_fees"] == "22.50"
    ok(post(client, librarian, f"members/{g['id']}/payments", {"amount": "22.50", "method": "cash"}), 201)
    assert [fee_of(client, librarian, g, i)["status"] for i in (j["fee_id"], pack["fee_id"])] == ["paid", "paid"]
'''),
    dict(id="T-PRT-35-a", req="LIB-PRT-35", type="Normal", input="A member with two queued jobs and a pack is deactivated", expected="Both jobs `cancelled`, no `print_job_cancelled` notification; the pack keeps 50 pages", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    js = [job(client, librarian, p, m) for _ in range(2)]
    ok(buy_pack(client, librarian, m), 201)
    ok(post(client, librarian, f"members/{m['id']}/payments", {"amount": "20.00", "method": "cash"}), 201)
    deactivate_member(client, librarian, m["id"])
    assert [get(client, librarian, f"print-jobs/{j['id']}")["status"] for j in js] == ["cancelled", "cancelled"]
    assert notes(client, librarian, m["id"], "print_job_cancelled") == []
    assert [x["pages_left"] for x in items(get(client, librarian, f"members/{m['id']}/print-packs"))] == [50]
'''),
    dict(id="T-PRT-36-a", req="LIB-PRT-36", type="Normal", input="Student who printed 40 free pages, with a pack and one queued job", expected="Summary `printing` `{free_pages_left 60, pack_pages_left 50, queued_jobs 1}`", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 40)
    ok(buy_pack(client, librarian, m), 201)
    job(client, librarian, p, m)
    assert get(client, librarian, f"members/{m['id']}/summary")["printing"] == {"free_pages_left": 60, "pack_pages_left": 50, "queued_jobs": 1}
'''),
    dict(id="T-PRT-37-a", req="LIB-PRT-37", type="Error", input="Branch QQ with an `out_of_service` printer is deactivated; after retiring the printer, again", expected="`409 BRANCH_IN_USE`; 200", code='''
def TEST(client, admin, branch_a):
    qq = create_branch(client, admin, "QQ")
    p = printer(client, admin, qq, paper=0)
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "out_of_service"}))
    url = f"/api/v1/branches/{qq['id']}"
    err(client.patch(url, headers=admin, json={"is_active": False}), 409, "BRANCH_IN_USE")
    ok(client.patch(f"/api/v1/printers/{p['id']}", headers=admin, json={"status": "retired"}))
    ok(client.patch(url, headers=admin, json={"is_active": False}))
'''),
    dict(id="T-PRT-38-a", req="LIB-PRT-38", type="Normal", input="Closure of A on Tue (created Mon); on Tue 10:00 a job is sent and released", expected="Sent 201; release `BRANCH_NOT_OPEN`", code='''
def TEST(client, clock, admin, librarian, branch_a):
    ok(post(client, admin, f"branches/{branch_a['id']}/closures", {"date": TUE, "reason": "Sayım"}), 201)
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    at(clock, TUE, 10)
    err(release(client, librarian, job(client, librarian, p, m)), 409, "BRANCH_NOT_OPEN")
'''),
    dict(id="T-PRT-39-a", req="LIB-PRT-39", type="Normal", input="A member inside A sends a job and leaves; a member who is not inside sends and cancels a job", expected="The first job stays `queued`; 201 and 200", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    c = inside(client, librarian, branch_a, m)
    j = ok(send(client, mh(client, m), p, 2), 201)
    ok(post(client, librarian, "access/scan", {"branch_id": branch_a["id"], "direction": "out", "card_no": c["card_no"]}))
    assert get(client, librarian, f"print-jobs/{j['id']}")["status"] == "queued"
    o = member(client, librarian, branch_a)
    oj = ok(send(client, mh(client, o), p, 2), 201)
    ok(post(client, mh(client, o), f"print-jobs/{oj['id']}/cancel"))
'''),
    dict(id="T-PRT-40-a", req="LIB-PRT-40", type="Error", input="Release by card for a member inside A with two queued jobs at P (and one at another printer); a lost card; an unknown card; a member who is not inside", expected="`released` the two ids, `refused` []; the other job stays queued; `CARD_NOT_ACTIVE`; `404`; refused with `NOT_IN_BRANCH`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-41-a", req="LIB-PRT-41", type="Boundary", input="Three queued jobs of 10 sheets and `paper_left` 25; release by card", expected="Two released, the third refused with `OUT_OF_PAPER`; `paper_left` 5", code='''
def TEST(client, clock, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-42-a", req="LIB-PRT-42", type="Normal", input="A student sends, releases and cancels jobs (all free)", expected="No notifications", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    before = len(items(get(client, librarian, f"members/{m['id']}/notifications")))
    printed(client, librarian, p, m, 3)
    j = ok(send(client, mh(client, m), p, 2), 201)
    ok(post(client, mh(client, m), f"print-jobs/{j['id']}/cancel"))
    assert len(items(get(client, librarian, f"members/{m['id']}/notifications"))) == before
'''),
    dict(id="T-PRT-43-a", req="LIB-PRT-43", type="Normal", input="Printer created, changed, refilled; jobs sent, released, cancelled, failed; a pack; process; a refused release; audit log", expected="One entry per event (3 `print_job_submitted`, 2 `print_job_released`)", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-44-a", req="LIB-PRT-44", type="Error", input="`from` > `to`; 2026-01-01 – 2027-01-10; a member reads the report", expected="`422`; `422`; `403`", code='''
def TEST(client, librarian, branch_a):
    url = "/api/v1/reports/printing"
    assert client.get(url, headers=librarian, params={"from": TUE, "to": MON}).status_code == 422
    assert client.get(url, headers=librarian, params={"from": "2026-01-01", "to": "2027-01-10"}).status_code == 422
    assert client.get(url, headers=member_headers(client, member(client, librarian, branch_a)), params={"from": MON, "to": MON}).status_code == 403
'''),
    dict(id="T-PRT-44-b", req="LIB-PRT-44", type="Normal", input="Printers at A and B; at B one job of 4 duplex pages; a student of B buys a pack; report 2026-11-02 – 2026-11-08 with and without `branch_id`", expected="Rows [A (all 0), B {jobs_printed 1, pages 4, sheets 2, free_pages 4, packs_sold 1, revenue 0.00}]; with `branch_id` B only B", code='''
def TEST(client, admin, librarian, branch_a, branch_b):
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
'''),
    dict(id="T-PRT-45-a", req="LIB-PRT-45", type="Normal", input="At A: a student's job of 10 pages (free), a color job of 2 pages (4.00), a guest's job of 3 pages (1.50) that fails", expected="`{jobs_printed 3, pages 15, color_pages 2, sheets 15, free_pages 10, pack_pages 0, charged_pages 5, revenue 4.00, packs_sold 0, jobs_failed 1, refunds_pending 0.00}`", code='''
def TEST(client, admin, librarian, branch_a):
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
'''),
    dict(id="T-PRT-46-a", req="LIB-PRT-46", type="Normal", input="A printer, a job and a pack exist; `GET /api/v1/export`", expected="The export has exactly the keys of 22.1", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    printed(client, librarian, p, m, 2)
    ok(buy_pack(client, librarian, m), 201)
    out = ok(client.get("/api/v1/export", headers=admin))
    assert set(out) == {"format_version", "branches", "authors", "publishers", "books", "copies", "members", "loans"}
'''),
    dict(id="T-PRT-47-a", req="LIB-PRT-47", type="Normal", input="A student reads `members/me`; after printing 25 free pages", expected="`free_pages_left` 100; then 75", code='''
def TEST(client, admin, librarian, branch_a):
    p = printer(client, admin, branch_a)
    m = member(client, librarian, branch_a)
    h = mh(client, m)
    assert get(client, h, "members/me")["free_pages_left"] == 100
    printed(client, librarian, p, m, 25)
    assert get(client, h, "members/me")["free_pages_left"] == 75
'''),
]
