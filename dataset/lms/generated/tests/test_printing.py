"""Module 29: Printing and copying (LIB-PRT-01 to LIB-PRT-47).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), students 1 to 3, printer 1 (PR-001, AAA,
color and duplex) with 1000 sheets.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.notifications.models import Notification
from tests.test_access import go, issue, notes, scan, sel
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_loans import API, lib, mk_member, member_h  # noqa: F401


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def mk_printer(client, hd, code="PR-001", branch=1, color=True, duplex=True, paper=1000, expect=201):
    r = client.post(
        f"{API}/printers",
        headers=hd,
        json={"branch_id": branch, "code": code, "name": f"Printer {code}", "color": color, "duplex": duplex},
    )
    assert r.status_code == expect, r.text
    body = r.json()
    if expect == 201 and paper:
        refill = client.post(f"{API}/printers/{body['id']}/refill", headers=hd, json={"sheets": paper})
        assert refill.status_code == 200, refill.text
        body = refill.json()
    return body


def send(client, hd, member=None, printer=1, pages=5, expect=201, **kw):
    body = {"printer_id": printer, "title": "Thesis", "pages": pages, **kw}
    if member is not None:
        body["member_id"] = member
    r = client.post(f"{API}/print-jobs", headers=hd, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def release(client, hd, job_id, expect=200):
    r = client.post(f"{API}/print-jobs/{job_id}/release", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


def job(client, hd, job_id):
    return client.get(f"{API}/print-jobs/{job_id}", headers=hd).json()


def printer(client, hd, printer_id=1):
    return client.get(f"{API}/printers/{printer_id}", headers=hd).json()


def quota(client, hd, member=1, month=None):
    r = client.get(f"{API}/members/{member}/print-quota", headers=hd, params={"month": month} if month else {})
    assert r.status_code == 200, r.text
    return r.json()


def buy_pack(client, hd, member=1, expect=201):
    r = client.post(f"{API}/members/{member}/print-packs", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


def fees(client, hd, member=1, **params):
    return client.get(f"{API}/members/{member}/fees", headers=hd, params=params).json()["items"]


def inside(client, hd, member=1, branch=1):
    card = issue(client, hd, member)
    scan(client, hd, "in", branch, card_no=card["card_no"])
    return card


@pytest.fixture
def world(client, lib, admin_h):
    members = [mk_member(client, lib, n) for n in range(1, 4)]
    mh = [member_h(client, n) for n in range(1, 4)]
    mk_printer(client, admin_h)
    return {"lib": lib, "admin": admin_h, "members": members, "mh": mh}


# --- printers -----------------------------------------------------------------------


def test_create_printer(client, lib, admin_h, app):
    mk_printer(client, admin_h, paper=0)
    p = printer(client, lib)
    assert p == {
        "id": 1, "branch_id": 1, "code": "PR-001", "name": "Printer PR-001", "color": True, "duplex": True,
        "paper_left": 0, "status": "active", "low_paper": True,
    }
    assert len(audit(app, "printer_created")) == 1
    err(client.post(f"{API}/printers", headers=admin_h, json={"branch_id": 1, "code": "PR-001", "name": "X", "color": False, "duplex": False}), 409, "CONFLICT")
    assert client.post(f"{API}/printers", headers=lib, json={"branch_id": 1, "code": "PR-002", "name": "X", "color": False, "duplex": False}).status_code == 403
    assert client.post(f"{API}/printers", headers=admin_h, json={"branch_id": 99, "code": "PR-002", "name": "X", "color": False, "duplex": False}).status_code == 404
    for body in (
        {"branch_id": 1, "code": "PR-02", "name": "X", "color": False, "duplex": False},
        {"branch_id": 1, "code": "PX-002", "name": "X", "color": False, "duplex": False},
        {"branch_id": 1, "code": "PR-002", "name": " ", "color": False, "duplex": False},
        {"branch_id": 1, "code": "PR-002", "name": "X", "color": "yes", "duplex": False},
        {"branch_id": 1, "code": "PR-002", "name": "X", "color": False, "duplex": False, "paper_left": 5},
    ):
        assert client.post(f"{API}/printers", headers=admin_h, json=body).status_code == 422, body


def test_create_printer_in_inactive_branch(client, lib, admin_h):
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200
    err(client.post(f"{API}/printers", headers=admin_h, json={"branch_id": 2, "code": "PR-002", "name": "X", "color": False, "duplex": False}), 409, "BRANCH_INACTIVE")


def test_list_printers(client, world):
    lib, admin = world["lib"], world["admin"]
    mk_printer(client, admin, "PR-003", branch=2, color=False, duplex=False, paper=50)
    mk_printer(client, admin, "PR-002", branch=1, color=False, duplex=True, paper=100)
    got = client.get(f"{API}/printers", headers=world["mh"][0]).json()
    assert [p["code"] for p in got["items"]] == ["PR-001", "PR-002", "PR-003"] and got["total"] == 3
    q = lambda **kw: [p["code"] for p in client.get(f"{API}/printers", headers=lib, params=kw).json()["items"]]
    assert q(branch_id=2) == ["PR-003"]
    assert q(color="true") == ["PR-001"]
    assert q(color="false") == ["PR-002", "PR-003"]
    assert q(low_paper="true") == ["PR-003"]
    assert q(low_paper="false") == ["PR-001", "PR-002"]
    assert client.patch(f"{API}/printers/3", headers=admin, json={"status": "out_of_service"}).status_code == 200
    assert q(status="out_of_service") == ["PR-002"]
    assert client.get(f"{API}/printers", headers=lib, params={"status": "broken"}).status_code == 422
    assert client.get(f"{API}/printers/9", headers=lib).status_code == 404
    assert client.get(f"{API}/printers").status_code == 401


def test_patch_printer(client, world, app):
    lib, admin = world["lib"], world["admin"]
    r = client.patch(f"{API}/printers/1", headers=admin, json={"name": "Main", "status": "out_of_service"})
    assert r.status_code == 200 and r.json()["name"] == "Main" and r.json()["status"] == "out_of_service"
    ev = audit(app, "printer_changed")
    assert len(ev) == 1 and ev[0].details["status"] == {"old": "active", "new": "out_of_service"}
    assert client.patch(f"{API}/printers/1", headers=admin, json={"status": "active"}).json()["status"] == "active"
    assert client.patch(f"{API}/printers/1", headers=lib, json={"name": "X"}).status_code == 403
    assert client.patch(f"{API}/printers/1", headers=admin, json={"status": "broken"}).status_code == 422
    assert client.patch(f"{API}/printers/1", headers=admin, json={"name": None}).status_code == 422
    assert client.patch(f"{API}/printers/1", headers=admin, json={"code": "PR-009"}).status_code == 422
    assert client.patch(f"{API}/printers/1", headers=admin, json={"status": "retired"}).json()["status"] == "retired"
    err(client.patch(f"{API}/printers/1", headers=admin, json={"name": "Again"}), 409, "PRINTER_RETIRED")
    err(client.patch(f"{API}/printers/1", headers=admin, json={"status": "active"}), 409, "PRINTER_RETIRED")


def test_status_change_cancels_queued_jobs(client, world, app):
    lib, admin = world["lib"], world["admin"]
    mk_printer(client, admin, "PR-002", color=False, duplex=False)
    a = send(client, world["mh"][0], printer=1)
    b = send(client, world["mh"][1], printer=1)
    c = send(client, world["mh"][0], printer=2)
    client.patch(f"{API}/printers/1", headers=admin, json={"status": "out_of_service"})
    assert job(client, lib, a["id"])["status"] == "cancelled" and job(client, lib, b["id"])["status"] == "cancelled"
    assert job(client, lib, c["id"])["status"] == "queued"
    n = notes(app, "print_job_cancelled")
    assert sorted(x.member_id for x in n) == [1, 2] and all("Thesis" in x.message for x in n)
    assert {x.print_job_id for x in n} == {a["id"], b["id"]}
    got = client.get(f"{API}/members/1/notifications", headers=world["mh"][0]).json()["items"]
    assert any(i["type"] == "print_job_cancelled" and i["print_job_id"] == a["id"] for i in got)
    client.patch(f"{API}/printers/2", headers=admin, json={"status": "retired"})
    assert job(client, lib, c["id"])["status"] == "cancelled"


def test_losing_color_or_duplex_cancels_the_jobs_that_need_it(client, world):
    lib, admin = world["lib"], world["admin"]
    plain = send(client, world["mh"][0])
    color = send(client, world["mh"][0], color=True)
    duplex = send(client, world["mh"][1], duplex=True)
    client.patch(f"{API}/printers/1", headers=admin, json={"color": False})
    assert [job(client, lib, j["id"])["status"] for j in (plain, color, duplex)] == ["queued", "cancelled", "queued"]
    client.patch(f"{API}/printers/1", headers=admin, json={"duplex": False})
    assert [job(client, lib, j["id"])["status"] for j in (plain, color, duplex)] == ["queued", "cancelled", "cancelled"]


def test_refill(client, world, app):
    lib, admin = world["lib"], world["admin"]
    p = mk_printer(client, admin, "PR-002", paper=4900)
    assert p["paper_left"] == 4900
    r = client.post(f"{API}/printers/{p['id']}/refill", headers=lib, json={"sheets": 100})
    assert r.status_code == 200 and r.json()["paper_left"] == 5000
    p2 = mk_printer(client, admin, "PR-003", paper=4900)
    e = err(client.post(f"{API}/printers/{p2['id']}/refill", headers=lib, json={"sheets": 101}), 409, "PAPER_CAPACITY_EXCEEDED")
    assert e["details"]["paper_left"] == 4900
    assert printer(client, lib, p2["id"])["paper_left"] == 4900
    for bad in (0, 5001, "5", 1.5, None):
        assert client.post(f"{API}/printers/1/refill", headers=lib, json={"sheets": bad}).status_code == 422
    assert client.post(f"{API}/printers/1/refill", headers=world["mh"][0], json={"sheets": 5}).status_code == 403
    assert client.post(f"{API}/printers/9/refill", headers=lib, json={"sheets": 5}).status_code == 404
    client.patch(f"{API}/printers/1", headers=admin, json={"status": "retired"})
    err(client.post(f"{API}/printers/1/refill", headers=lib, json={"sheets": 5}), 409, "PRINTER_RETIRED")
    assert len(audit(app, "printer_refilled")) == 4


def test_low_paper_flag(client, world):
    lib, admin = world["lib"], world["admin"]
    p = mk_printer(client, admin, "PR-002", paper=100)
    assert p["low_paper"] is False
    j = send(client, world["mh"][0], printer=p["id"], pages=1)
    inside(client, lib)
    release(client, world["mh"][0], j["id"])
    assert printer(client, lib, p["id"])["paper_left"] == 99 and printer(client, lib, p["id"])["low_paper"] is True


# --- send ---------------------------------------------------------------------------


def test_send_job(client, world, app):
    j = send(client, world["mh"][0], pages=5, copies=2)
    assert j["status"] == "queued" and j["member_id"] == 1 and j["sheets"] == 10 and j["copies"] == 2
    assert j["color"] is False and j["duplex"] is False and j["released_at"] is None
    assert j["submitted_at"] == "2026-11-02T09:30:00+03:00"
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"], j["fee_id"], j["amount"], j["failed_reason"]) == (0, 0, 0, None, "0.00", None)
    assert j["printer"] == {"id": 1, "code": "PR-001", "branch_id": 1}
    assert send(client, world["mh"][0], pages=5, copies=2, duplex=True)["sheets"] == 6
    assert send(client, world["mh"][1], pages=1, duplex=True)["sheets"] == 1
    assert send(client, world["mh"][1], pages=3, duplex=True)["sheets"] == 2
    assert len(audit(app, "print_job_submitted")) == 4
    assert notes(app, "print_job_cancelled") == []
    assert sel(app, sa.select(Notification)) == []


def test_send_by_staff_needs_member_id(client, world):
    lib = world["lib"]
    j = send(client, lib, member=2, pages=3)
    assert j["member_id"] == 2
    r = client.post(f"{API}/print-jobs", headers=lib, json={"printer_id": 1, "title": "T", "pages": 3})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"][0]["field"] == "member_id"
    r = client.post(f"{API}/print-jobs", headers=world["mh"][0], json={"member_id": 1, "printer_id": 1, "title": "T", "pages": 3})
    assert r.status_code == 422
    assert client.post(f"{API}/print-jobs", headers=lib, json={"member_id": 99, "printer_id": 1, "title": "T", "pages": 3}).status_code == 404
    assert client.post(f"{API}/print-jobs", headers=lib, json={"member_id": 1, "printer_id": 99, "title": "T", "pages": 3}).status_code == 404
    assert client.post(f"{API}/print-jobs", json={"printer_id": 1, "title": "T", "pages": 3}).status_code == 401


@pytest.mark.parametrize(
    "patch",
    [
        {"title": ""}, {"title": "x" * 101}, {"pages": 0}, {"pages": 501}, {"pages": "5"}, {"copies": 0}, {"copies": 21},
        {"color": "yes"}, {"duplex": 1}, {"unknown": 1},
    ],
)
def test_send_validation(client, world, patch):
    body = {"printer_id": 1, "title": "Thesis", "pages": 5, **patch}
    assert client.post(f"{API}/print-jobs", headers=world["mh"][0], json=body).status_code == 422


def test_send_limits_accepted(client, world):
    assert send(client, world["mh"][0], title="x" * 100, pages=1, copies=20)["copies"] == 20
    assert send(client, world["mh"][1], pages=1, copies=1)["copies"] == 1


def test_send_checks_in_order(client, world, clock, admin_h):
    lib, mh = world["lib"], world["mh"][0]
    admin = world["admin"]
    mk_printer(client, admin, "PR-002", color=False, duplex=False)
    err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 2, "title": "T", "pages": 1, "color": True}), 409, "PRINTER_NO_COLOR")
    err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 2, "title": "T", "pages": 1, "color": True, "duplex": True}), 409, "PRINTER_NO_COLOR")
    err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 2, "title": "T", "pages": 1, "duplex": True}), 409, "PRINTER_NO_DUPLEX")
    client.patch(f"{API}/printers/2", headers=admin, json={"status": "out_of_service"})
    e = err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 2, "title": "T", "pages": 1, "color": True}), 409, "PRINTER_UNAVAILABLE")
    assert e["details"]["status"] == "out_of_service"
    client.patch(f"{API}/printers/2", headers=admin, json={"status": "retired"})
    assert err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 2, "title": "T", "pages": 1}), 409, "PRINTER_UNAVAILABLE")["details"]["status"] == "retired"
    client.post(f"{API}/members/2/deactivate", headers=lib)
    err(client.post(f"{API}/print-jobs", headers=lib, json={"member_id": 2, "printer_id": 2, "title": "T", "pages": 1}), 409, "MEMBER_PASSIVE")
    go(clock, 2027, 11, 2)
    err(client.post(f"{API}/print-jobs", headers=lib, json={"member_id": 3, "printer_id": 2, "title": "T", "pages": 1}), 409, "MEMBERSHIP_EXPIRED")


def test_queue_limit(client, world):
    mh = world["mh"][0]
    for _ in range(3):
        send(client, mh, pages=1)
    err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 1, "title": "T", "pages": 1}), 409, "PRINT_QUEUE_FULL")
    assert send(client, world["mh"][1], pages=1)["member_id"] == 2
    cancel = client.post(f"{API}/print-jobs/1/cancel", headers=mh)
    assert cancel.status_code == 200
    send(client, mh, pages=1)


def test_daily_page_limit(client, world, clock):
    lib = world["lib"]
    a = mk_member(client, lib, 5, "academic")
    mh = member_h(client, 5)
    # 150 pages printed yesterday do not count
    go(clock, 2026, 10, 30)
    for _ in range(3):
        release(client, lib, send(client, lib, member=a, pages=50)["id"])
    go(clock, 2026, 11, 2)
    mh = member_h(client, 5)
    for _ in range(3):
        release(client, lib, send(client, lib, member=a, pages=50)["id"])
    # 150 printed today + a queued job of 30
    send(client, mh, pages=30)
    e = err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 1, "title": "T", "pages": 21}), 409, "DAILY_PAGE_LIMIT")
    assert e["details"]["remaining"] == 20
    assert send(client, mh, pages=20)["pages"] == 20
    # copies count as pages
    e = err(client.post(f"{API}/print-jobs", headers=world["mh"][1], json={"printer_id": 1, "title": "T", "pages": 100, "copies": 3}), 409, "DAILY_PAGE_LIMIT")
    assert e["details"]["remaining"] == 200
    assert send(client, world["mh"][1], pages=100, copies=2)["sheets"] == 200


def test_daily_limit_remaining_never_negative(client, world):
    mh = world["mh"][0]
    send(client, mh, pages=100, copies=2)
    err(client.post(f"{API}/print-jobs", headers=mh, json={"printer_id": 1, "title": "T", "pages": 1}), 409, "DAILY_PAGE_LIMIT")


# --- reading jobs -------------------------------------------------------------------


def test_read_jobs(client, world, clock):
    lib = world["lib"]
    a = send(client, world["mh"][0], pages=1)
    go(clock, 2026, 11, 3)
    b = send(client, world["mh"][1], pages=1)
    c = send(client, world["mh"][0], pages=1)
    got = client.get(f"{API}/print-jobs", headers=lib).json()
    assert [j["id"] for j in got["items"]] == [c["id"], b["id"], a["id"]] and got["total"] == 3
    q = lambda path="/print-jobs", **kw: [j["id"] for j in client.get(f"{API}{path}", headers=lib, params=kw).json()["items"]]
    assert q(member_id=1) == [c["id"], a["id"]]
    assert q(**{"from": "2026-11-03"}) == [c["id"], b["id"]]
    assert q(to="2026-11-02") == [a["id"]]
    assert q(**{"from": "2026-11-03", "to": "2026-11-03"}) == [c["id"], b["id"]]
    assert q(status="printed") == []
    assert q(printer_id=1) == [c["id"], b["id"], a["id"]] and q(printer_id=2) == []
    assert q(branch_id=1) == [c["id"], b["id"], a["id"]] and q(branch_id=2) == []
    assert q("/members/1/print-jobs") == [c["id"], a["id"]]
    assert q("/members/1/print-jobs", status="queued", printer_id=1) == [c["id"], a["id"]]
    assert client.get(f"{API}/print-jobs", headers=lib, params={"from": "bad"}).status_code == 422
    assert client.get(f"{API}/print-jobs", headers=lib, params={"status": "x"}).status_code == 422
    assert client.get(f"{API}/print-jobs", headers=world["mh"][0]).status_code == 403
    mine = client.get(f"{API}/members/1/print-jobs", headers=world["mh"][0]).json()
    assert [j["id"] for j in mine["items"]] == [c["id"], a["id"]]
    assert client.get(f"{API}/members/1/print-jobs", headers=world["mh"][1]).status_code == 403
    assert client.get(f"{API}/members/99/print-jobs", headers=lib).status_code == 404
    assert client.get(f"{API}/print-jobs/{a['id']}", headers=world["mh"][0]).status_code == 200
    assert client.get(f"{API}/print-jobs/{a['id']}", headers=world["mh"][1]).status_code == 403
    assert client.get(f"{API}/print-jobs/{a['id']}", headers=lib).status_code == 200
    assert client.get(f"{API}/print-jobs/99", headers=lib).status_code == 404


def test_same_time_jobs_are_ordered_by_id_descending(client, world):
    a = send(client, world["mh"][0], pages=1)
    b = send(client, world["mh"][0], pages=1)
    ids = [j["id"] for j in client.get(f"{API}/members/1/print-jobs", headers=world["mh"][0]).json()["items"]]
    assert ids == [b["id"], a["id"]]


# --- cancel -------------------------------------------------------------------------


def test_cancel(client, world, app):
    lib = world["lib"]
    a = send(client, world["mh"][0])
    assert client.post(f"{API}/print-jobs/{a['id']}/cancel", headers=world["mh"][1]).status_code == 403
    r = client.post(f"{API}/print-jobs/{a['id']}/cancel", headers=world["mh"][0])
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    e = err(client.post(f"{API}/print-jobs/{a['id']}/cancel", headers=lib), 409, "PRINT_JOB_NOT_QUEUED")
    assert e["details"]["status"] == "cancelled"
    assert client.post(f"{API}/print-jobs/99/cancel", headers=lib).status_code == 404
    b = send(client, world["mh"][1])
    assert client.post(f"{API}/print-jobs/{b['id']}/cancel", headers=lib).status_code == 200
    assert len(audit(app, "print_job_cancelled")) == 2
    assert notes(app, "print_job_cancelled") == []


# --- release ------------------------------------------------------------------------


def test_release(client, world, app):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    j = send(client, mh, pages=5, copies=2)
    r = release(client, mh, j["id"])
    assert r["status"] == "printed" and r["released_at"] == "2026-11-02T09:30:00+03:00"
    assert (r["free_pages"], r["pack_pages"], r["charged_pages"], r["fee_id"], r["amount"]) == (10, 0, 0, None, "0.00")
    assert printer(client, lib)["paper_left"] == 990
    assert fees(client, lib) == []
    assert len(audit(app, "print_job_released")) == 1
    assert notes(app, "fee_created") == []
    e = err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=mh), 409, "PRINT_JOB_NOT_QUEUED")
    assert e["details"]["status"] == "printed"


def test_release_ownership(client, world):
    j = send(client, world["mh"][0])
    assert client.post(f"{API}/print-jobs/{j['id']}/release", headers=world["mh"][1]).status_code == 403
    assert client.post(f"{API}/print-jobs/99/release", headers=world["mh"][1]).status_code == 404
    assert client.post(f"{API}/print-jobs/{j['id']}/release").status_code == 401


def test_release_checks_in_order(client, world, clock):
    lib, admin, mh = world["lib"], world["admin"], world["mh"][0]
    mk_printer(client, admin, "PR-002", branch=2, paper=5)
    j = send(client, mh, printer=2, pages=10)
    # (5) a member who is not inside
    e = err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=mh), 409, "NOT_IN_BRANCH")
    assert e["details"]["branch_id"] == 2
    # inside another branch is not inside this one
    inside(client, lib, 1, branch=1)
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=mh), 409, "NOT_IN_BRANCH")
    # (4) the branch is closed outside its hours; staff are checked too
    go(clock, 2026, 11, 2, 21)
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=lib), 409, "BRANCH_NOT_OPEN")
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=mh), 409, "BRANCH_NOT_OPEN")
    go(clock, 2026, 11, 2, 9, 30)
    # (6) not enough paper; staff skip check (5)
    e = err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=lib), 409, "OUT_OF_PAPER")
    assert e["details"]["paper_left"] == 5
    # (3) printer out of service comes before the branch and the paper (a queued job is cancelled by LIB-PRT-04, so
    # the printer is changed back and forth only through the status of an already released job's printer)
    client.patch(f"{API}/printers/2", headers=admin, json={"status": "out_of_service"})
    assert job(client, lib, j["id"])["status"] == "cancelled"
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=lib), 409, "PRINT_JOB_NOT_QUEUED")


def test_release_passive_member(client, world):
    lib = world["lib"]
    j = send(client, world["mh"][0])
    client.post(f"{API}/members/1/deactivate", headers=lib)
    # deactivation cancels the queued job (LIB-PRT-35)
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=lib), 409, "PRINT_JOB_NOT_QUEUED")


def test_paper_example(client, world, admin_h):
    lib, mh = world["lib"], world["mh"][0]
    p = mk_printer(client, admin_h, "PR-002", paper=10)
    inside(client, lib)
    a = send(client, mh, printer=p["id"], pages=10)
    b = send(client, mh, printer=p["id"], pages=11)
    release(client, lib, a["id"])
    assert printer(client, lib, p["id"])["paper_left"] == 0
    e = err(client.post(f"{API}/print-jobs/{b['id']}/release", headers=lib), 409, "OUT_OF_PAPER")
    assert e["details"]["paper_left"] == 0
    client.post(f"{API}/printers/{p['id']}/refill", headers=lib, json={"sheets": 11})
    release(client, lib, b["id"])
    assert printer(client, lib, p["id"])["paper_left"] == 0
    c = send(client, mh, printer=p["id"], pages=1)
    assert err(client.post(f"{API}/print-jobs/{c['id']}/release", headers=lib), 409, "OUT_OF_PAPER")["details"]["paper_left"] == 0


def test_closure_stops_releases_but_not_sending(client, world, admin_h, clock):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    j = send(client, mh, pages=1)
    go(clock, 2026, 11, 1)
    r = client.post(f"{API}/branches/1/closures", headers=admin_h, json={"date": "2026-11-02", "reason": "Cleaning"})
    assert r.status_code == 201, r.text
    go(clock, 2026, 11, 2)
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=lib), 409, "BRANCH_NOT_OPEN")
    assert send(client, mh, pages=1)["status"] == "queued"


def test_leaving_the_branch_keeps_queued_jobs(client, world):
    lib, mh = world["lib"], world["mh"][0]
    card = inside(client, lib)
    j = send(client, mh, pages=1)
    scan(client, lib, "out", 1, card_no=card["card_no"])
    assert job(client, lib, j["id"])["status"] == "queued"
    assert send(client, mh, pages=1)["status"] == "queued"
    assert client.post(f"{API}/print-jobs/{j['id']}/cancel", headers=mh).status_code == 200
    err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=mh), 409, "PRINT_JOB_NOT_QUEUED")


# --- charging -----------------------------------------------------------------------


def test_charging_free_pack_and_fee(client, world, app):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    # 95 free pages used this month
    release(client, lib, send(client, lib, member=1, pages=95)["id"])
    assert quota(client, lib)["free_pages_left"] == 5
    buy_pack(client, lib)
    r = release(client, mh, send(client, mh, pages=30)["id"])
    assert (r["free_pages"], r["pack_pages"], r["charged_pages"], r["fee_id"], r["amount"]) == (5, 25, 0, None, "0.00")
    packs = client.get(f"{API}/members/1/print-packs", headers=lib).json()["items"]
    assert [p["pages_left"] for p in packs] == [25]
    # nothing left but 25 pack pages: 40 pages = 25 from the pack + 15 charged
    r = release(client, mh, send(client, mh, pages=40)["id"])
    assert (r["free_pages"], r["pack_pages"], r["charged_pages"], r["amount"]) == (0, 25, 15, "7.50")
    fee = [f for f in fees(client, lib) if f["kind"] == "printing"][0]
    assert fee["id"] == r["fee_id"] and fee["amount"] == "7.50" and fee["print_job_id"] == r["id"] and fee["status"] == "open"
    assert fee["loan_id"] is None
    n = notes(app, "fee_created")
    assert len(n) == 2 and n[1].fee_id == fee["id"]  # the pack fee and the printing fee
    assert client.get(f"{API}/members/1/print-packs", headers=lib).json()["items"][0]["pages_left"] == 0


def test_guest_pays_everything(client, world):
    lib = world["lib"]
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    r = release(client, gh, send(client, gh, pages=3, copies=2, color=True)["id"])
    assert (r["free_pages"], r["pack_pages"], r["charged_pages"], r["amount"]) == (0, 0, 6, "12.00")
    r = release(client, gh, send(client, gh, pages=7)["id"])
    assert (r["charged_pages"], r["amount"]) == (7, "3.50")
    assert sorted(f["amount"] for f in fees(client, lib, g)) == ["12.00", "3.50"]


def test_color_pages_ignore_free_pages_and_packs(client, world):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    buy_pack(client, lib)
    r = release(client, mh, send(client, mh, pages=4, color=True)["id"])
    assert (r["free_pages"], r["pack_pages"], r["charged_pages"], r["amount"]) == (0, 0, 4, "8.00")
    assert quota(client, lib)["free_pages_left"] == 100 and quota(client, lib)["pack_pages_left"] == 50


def test_packs_are_used_oldest_first(client, world, clock):
    lib, mh = world["lib"], world["mh"][0]
    admin = world["admin"]
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    p1 = buy_pack(client, lib, g)
    go(clock, 2026, 11, 3)
    p2 = buy_pack(client, lib, g)
    assert p1["id"] < p2["id"] and p2["bought_on"] == "2026-11-03"
    j = send(client, gh, pages=70)
    release(client, gh, j["id"])
    left = [p["pages_left"] for p in client.get(f"{API}/members/{g}/print-packs", headers=lib).json()["items"]]
    assert left == [0, 30]
    assert job(client, lib, j["id"]) ["pack_pages"] == 50 + 20 and job(client, lib, j["id"])["charged_pages"] == 0
    assert [p["pages_left"] for p in client.get(f"{API}/members/{g}/print-packs", headers=lib, params={"with_pages_left": "true"}).json()["items"]] == [30]
    assert [p["pages_left"] for p in client.get(f"{API}/members/{g}/print-packs", headers=lib, params={"with_pages_left": "false"}).json()["items"]] == [0]


def test_new_month_restores_free_pages(client, world, clock):
    lib, mh = world["lib"], world["mh"][0]
    go(clock, 2026, 11, 30)
    j = send(client, lib, member=1, pages=100)
    release(client, lib, j["id"])
    assert quota(client, lib)["free_pages_left"] == 100 - 100
    go(clock, 2026, 12, 1)
    assert quota(client, lib)["free_pages_left"] == 100
    assert quota(client, lib, month="2026-11")["free_pages_left"] == 0
    r = release(client, lib, send(client, lib, member=1, pages=100)["id"])
    assert (r["free_pages"], r["charged_pages"]) == (100, 0)


def test_debt_example(client, world, admin_h):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    # a lost-card style fee is not available; use packs (20.00 each) and printing fees to reach 46.50
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    buy_pack(client, lib, g)  # 20.00
    buy_pack(client, lib, g)  # 20.00
    release(client, gh, send(client, gh, pages=2, color=True)["id"])  # 4.00 -> 44.00 (color is always charged)
    # 44.00 + 5 colour pages... use black-and-white pages once the packs are used up: 100 pages from the packs
    release(client, gh, send(client, gh, pages=100)["id"])
    # packs empty; debt is 44.00; 5 pages are 2.50 -> 46.50
    release(client, gh, send(client, gh, pages=5)["id"])
    summary = client.get(f"{API}/members/{g}/balance", headers=lib).json()
    assert summary["total_debt"] == "46.50"
    j = send(client, gh, pages=7)
    e = err(client.post(f"{API}/print-jobs/{j['id']}/release", headers=gh), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["amount"] == "3.50"
    assert job(client, lib, j["id"])["status"] == "queued" and printer(client, lib)["paper_left"] == 1000 - 4 // 2 * 0 - 2 - 100 - 5
    client.post(f"{API}/print-jobs/{j['id']}/cancel", headers=gh)
    j = send(client, gh, pages=6)
    assert release(client, gh, j["id"])["amount"] == "3.00"
    assert client.get(f"{API}/members/{g}/balance", headers=lib).json()["total_debt"] == "49.50"


def test_job_paid_from_free_pages_is_printed_with_any_debt(client, world):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    # 60.00 of fees through three packs
    for _ in range(3):
        buy_pack(client, lib)
    assert client.get(f"{API}/members/1/balance", headers=lib).json()["blocked"] is True
    j = send(client, mh, pages=10)
    assert release(client, mh, j["id"])["amount"] == "0.00"
    # a colour job would be charged and is refused
    c = send(client, mh, pages=1, color=True)
    assert err(client.post(f"{API}/print-jobs/{c['id']}/release", headers=mh), 409, "MEMBER_BLOCKED_BY_DEBT")["details"]["amount"] == "2.00"


def test_blocked_job_changes_nothing(client, world, app):
    lib, mh = world["lib"], world["mh"][0]
    for _ in range(3):
        buy_pack(client, lib)
    inside(client, lib)
    c = send(client, mh, pages=1, color=True)
    client.post(f"{API}/print-jobs/{c['id']}/release", headers=mh)
    assert job(client, lib, c["id"])["status"] == "queued" and printer(client, lib)["paper_left"] == 1000
    assert audit(app, "print_job_released") == []


# --- failed prints ------------------------------------------------------------------


def test_fail_refunds_free_pages_packs_and_waives_the_fee(client, world, app):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    release(client, lib, send(client, lib, member=1, pages=95)["id"])
    buy_pack(client, lib)
    j = release(client, mh, send(client, mh, pages=30)["id"])
    assert (j["free_pages"], j["pack_pages"], j["charged_pages"]) == (5, 25, 0)
    # give the job a fee as well: 40 more pages
    k = release(client, mh, send(client, mh, pages=40)["id"])
    assert (k["pack_pages"], k["charged_pages"], k["amount"]) == (25, 15, "7.50")
    r = client.post(f"{API}/print-jobs/{k['id']}/fail", headers=lib, json={"reason": "Paper jam"})
    assert r.status_code == 200 and r.json()["status"] == "failed" and r.json()["failed_reason"] == "Paper jam"
    fee = [f for f in fees(client, lib) if f["kind"] == "printing"][0]
    assert fee["status"] == "waived" and fee["waive_reason"] == "Failed print" and fee["waived_by"] is not None
    assert client.get(f"{API}/members/1/print-packs", headers=lib).json()["items"][0]["pages_left"] == 25
    n = notes(app, "print_job_failed")
    assert len(n) == 1 and "Thesis" in n[0].message and n[0].print_job_id == k["id"]
    assert len(audit(app, "print_job_failed")) == 1
    assert printer(client, lib)["paper_left"] == 1000 - 95 - 30 - 40
    # refund example: free pages come back
    r = client.post(f"{API}/print-jobs/{j['id']}/fail", headers=lib, json={"reason": "Paper jam"})
    assert r.status_code == 200
    q = quota(client, lib)
    assert q["free_pages_used"] == 95 and q["free_pages_left"] == 5 and q["pack_pages_left"] == 50


def test_fail_with_paid_fee_keeps_it_and_counts_a_pending_refund(client, world, admin_h):
    lib, mh = world["lib"], world["mh"][0]
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    j = release(client, gh, send(client, gh, pages=10)["id"])
    assert j["amount"] == "5.00"
    assert client.post(f"{API}/members/{g}/payments", headers=lib, json={"amount": "2.00", "method": "cash"}).status_code == 201
    assert client.post(f"{API}/print-jobs/{j['id']}/fail", headers=lib, json={"reason": "Blank pages"}).status_code == 200
    fee = fees(client, lib, g)[0]
    assert fee["status"] == "open" and fee["paid_amount"] == "2.00"
    row = client.get(f"{API}/reports/printing", headers=lib, params={"from": "2026-11-02", "to": "2026-11-02"}).json()["items"][0]
    assert row["jobs_failed"] == 1 and row["refunds_pending"] == "2.00" and row["revenue"] == "5.00"
    # fully paid
    k = release(client, gh, send(client, gh, pages=4)["id"])
    client.post(f"{API}/members/{g}/payments", headers=lib, json={"amount": "5.00", "method": "cash"})
    assert [f["status"] for f in fees(client, lib, g)] == ["paid", "paid"]
    client.post(f"{API}/print-jobs/{k['id']}/fail", headers=lib, json={"reason": "Blank pages"})
    row = client.get(f"{API}/reports/printing", headers=lib, params={"from": "2026-11-02", "to": "2026-11-02"}).json()["items"][0]
    assert row["refunds_pending"] == "7.00" and row["revenue"] == "7.00"


def test_fail_checks(client, world, clock):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    q = send(client, mh, pages=1)
    e = err(client.post(f"{API}/print-jobs/{q['id']}/fail", headers=lib, json={"reason": "Paper jam"}), 409, "PRINT_JOB_NOT_PRINTED")
    assert e["details"]["status"] == "queued"
    assert client.post(f"{API}/print-jobs/{q['id']}/fail", headers=mh, json={"reason": "Paper jam"}).status_code == 403
    for bad in ({"reason": "Jam"}, {"reason": "x" * 201}, {}, {"reason": "Paper jam", "x": 1}):
        assert client.post(f"{API}/print-jobs/{q['id']}/fail", headers=lib, json=bad).status_code == 422
    assert client.post(f"{API}/print-jobs/99/fail", headers=lib, json={"reason": "Paper jam"}).status_code == 404
    release(client, lib, q["id"])
    r = client.post(f"{API}/print-jobs/{q['id']}/fail", headers=lib, json={"reason": "Paper jam"})
    assert r.status_code == 200
    err(client.post(f"{API}/print-jobs/{q['id']}/fail", headers=lib, json={"reason": "Paper jam"}), 409, "PRINT_JOB_NOT_PRINTED")


def test_fail_window(client, world, clock):
    lib, mh = world["lib"], world["mh"][0]
    go(clock, 2026, 11, 2, 10, 0)
    inside(client, lib)
    a = release(client, lib, send(client, lib, member=1, pages=1)["id"])
    b = release(client, lib, send(client, lib, member=1, pages=1)["id"])
    go(clock, 2026, 11, 3, 10, 0)
    assert client.post(f"{API}/print-jobs/{a['id']}/fail", headers=lib, json={"reason": "Paper jam"}).json()["status"] == "failed"
    go(clock, 2026, 11, 3, 10, 1)
    err(client.post(f"{API}/print-jobs/{b['id']}/fail", headers=lib, json={"reason": "Paper jam"}), 409, "FAIL_WINDOW_CLOSED")


# --- packs and quota ----------------------------------------------------------------


def test_buy_pack(client, world, app):
    lib = world["lib"]
    p = buy_pack(client, lib)
    assert (p["pages"], p["pages_left"], p["bought_on"], p["member_id"]) == (50, 50, "2026-11-02", 1)
    fee = fees(client, lib)[0]
    assert fee["kind"] == "print_pack" and fee["amount"] == "20.00" and fee["status"] == "open" and fee["id"] == p["fee_id"]
    assert fee["print_job_id"] is None
    assert len(audit(app, "print_pack_bought")) == 1
    assert client.post(f"{API}/members/1/print-packs", headers=world["mh"][0]).status_code == 403
    assert client.post(f"{API}/members/99/print-packs", headers=lib).status_code == 404
    mine = client.get(f"{API}/members/1/print-packs", headers=world["mh"][0])
    assert mine.status_code == 200 and mine.json()["total"] == 1
    assert client.get(f"{API}/members/1/print-packs", headers=world["mh"][1]).status_code == 403
    assert client.get(f"{API}/members/1/print-packs", headers=lib, params={"with_pages_left": "maybe"}).status_code == 422


def test_pack_limit_and_checks(client, world, clock):
    lib = world["lib"]
    for _ in range(4):
        buy_pack(client, lib, 2)
    e = err(client.post(f"{API}/members/2/print-packs", headers=lib), 409, "PACK_LIMIT_REACHED")
    assert quota(client, lib, 2)["pack_pages_left"] == 200
    client.post(f"{API}/members/1/deactivate", headers=lib)
    err(client.post(f"{API}/members/1/print-packs", headers=lib), 409, "MEMBER_PASSIVE")
    go(clock, 2027, 11, 2)
    err(client.post(f"{API}/members/3/print-packs", headers=lib), 409, "MEMBERSHIP_EXPIRED")


def test_pack_with_no_pages_left_does_not_count(client, world):
    lib = world["lib"]
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    buy_pack(client, lib, g)
    release(client, gh, send(client, gh, pages=50)["id"])
    for _ in range(3):
        buy_pack(client, lib, g)
    assert buy_pack(client, lib, g)["pages_left"] == 50
    err(client.post(f"{API}/members/{g}/print-packs", headers=lib), 409, "PACK_LIMIT_REACHED")


def test_quota(client, world, clock):
    lib, mh = world["lib"], world["mh"][0]
    q = quota(client, mh)
    assert q == {
        "month": "2026-11", "membership_type": "student", "free_pages": 100, "free_pages_used": 0,
        "free_pages_left": 100, "pack_pages_left": 0, "pages_printed": 0, "amount_charged": "0.00",
    }
    inside(client, lib)
    buy_pack(client, lib)
    release(client, mh, send(client, mh, pages=40, copies=2)["id"])
    q = quota(client, mh)
    assert (q["free_pages_used"], q["free_pages_left"], q["pack_pages_left"], q["pages_printed"]) == (80, 20, 50, 80)
    release(client, mh, send(client, mh, pages=2, copies=1, color=True)["id"])
    q = quota(client, mh)
    assert q["pages_printed"] == 82 and q["amount_charged"] == "4.00"
    go(clock, 2026, 12, 1)
    mh = member_h(client, 1)
    q = quota(client, mh)
    assert (q["month"], q["free_pages_used"], q["pages_printed"], q["pack_pages_left"], q["amount_charged"]) == ("2026-12", 0, 0, 50, "0.00")
    q = quota(client, mh, month="2026-11")
    assert (q["month"], q["free_pages_used"], q["free_pages_left"], q["pages_printed"], q["amount_charged"]) == ("2026-11", 80, 20, 82, "4.00")
    for bad in ("2027-01", "2026-13", "2026-1", "nov", "2026-00"):
        assert client.get(f"{API}/members/1/print-quota", headers=mh, params={"month": bad}).status_code == 422
    assert client.get(f"{API}/members/1/print-quota", headers=member_h(client, 2)).status_code == 403
    assert client.get(f"{API}/members/99/print-quota", headers=lib).status_code == 404
    assert quota(client, lib, 1, "2020-01")["free_pages_used"] == 0


def test_free_pages_by_type(client, world):
    lib, admin = world["lib"], world["admin"]
    a = mk_member(client, lib, 5, "academic")
    s = mk_member(client, lib, 6, "staff")
    g = mk_member(client, lib, 7, "guest")
    assert [quota(client, lib, m)["free_pages"] for m in (1, a, s, g)] == [100, 300, 300, 0]


def test_type_change_changes_later_releases(client, world):
    lib, mh = world["lib"], world["mh"][0]
    inside(client, lib)
    release(client, mh, send(client, mh, pages=100)["id"])
    assert quota(client, lib)["free_pages_left"] == 0
    r = client.patch(f"{API}/members/1", headers=lib, json={"membership_type": "academic"})
    assert r.status_code == 200, r.text
    q = quota(client, lib)
    assert (q["free_pages"], q["free_pages_used"], q["free_pages_left"]) == (300, 100, 200)
    j = release(client, mh, send(client, mh, pages=90)["id"])
    assert j["free_pages"] == 90 and j["charged_pages"] == 0
    r = client.patch(f"{API}/members/1", headers=lib, json={"membership_type": "guest", "university_id": None, "phone": "+905321234567"})
    assert r.status_code == 200, r.text
    q = quota(client, lib)
    assert (q["free_pages"], q["free_pages_used"], q["free_pages_left"]) == (0, 190, 0)
    j = release(client, mh, send(client, mh, pages=10)["id"])
    assert (j["free_pages"], j["charged_pages"], j["amount"]) == (0, 10, "5.00")


# --- process ------------------------------------------------------------------------


def test_expiry(client, world, clock, app):
    lib, mh = world["lib"], world["mh"][0]
    go(clock, 2026, 11, 2, 10, 0)
    a = send(client, mh, pages=1)
    go(clock, 2026, 11, 3, 9, 59)
    assert client.post(f"{API}/printing/process", headers=lib).json() == {"jobs_expired": 0}
    assert job(client, lib, a["id"])["status"] == "queued"
    go(clock, 2026, 11, 3, 10, 0)
    b = send(client, world["mh"][1], pages=1)
    assert client.post(f"{API}/printing/process", headers=lib).json() == {"jobs_expired": 1}
    assert job(client, lib, a["id"])["status"] == "expired" and job(client, lib, b["id"])["status"] == "queued"
    n = notes(app, "print_job_expired")
    assert len(n) == 1 and n[0].member_id == 1 and "Thesis" in n[0].message and n[0].print_job_id == a["id"]
    assert len(audit(app, "printing_processed")) == 2
    assert client.post(f"{API}/printing/process", headers=lib).json() == {"jobs_expired": 0}
    assert client.post(f"{API}/printing/process", headers=world["mh"][0]).status_code == 403
    assert client.post(f"{API}/printing/process").status_code == 401
    err(client.post(f"{API}/print-jobs/{a['id']}/release", headers=lib), 409, "PRINT_JOB_NOT_QUEUED")


# --- release by card ----------------------------------------------------------------


def test_release_by_card(client, world, admin_h):
    lib = world["lib"]
    p = mk_printer(client, admin_h, "PR-002", paper=25)
    card = inside(client, lib)
    ids = [send(client, world["mh"][0], printer=p["id"], pages=10)["id"] for _ in range(3)]
    r = client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": p["id"], "card_no": card["card_no"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"released": ids[:2], "refused": [{"job_id": ids[2], "code": "OUT_OF_PAPER"}]}
    assert job(client, lib, ids[2])["status"] == "queued"
    assert printer(client, lib, p["id"])["paper_left"] == 5
    # jobs of other printers and of other members are not touched
    other = send(client, world["mh"][0], printer=1, pages=1)
    someone = send(client, world["mh"][1], printer=1, pages=1)
    again = client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1, "card_no": card["card_no"]})
    assert again.json() == {"released": [other["id"]], "refused": []}
    assert job(client, lib, someone["id"])["status"] == "queued"
    empty = client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1, "card_no": card["card_no"]})
    assert empty.json() == {"released": [], "refused": []}


def test_release_by_card_checks_inside_and_card(client, world):
    lib = world["lib"]
    card = issue(client, lib)
    j = send(client, world["mh"][0], pages=1)
    r = client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1, "card_no": card["card_no"]})
    assert r.json() == {"released": [], "refused": [{"job_id": j["id"], "code": "NOT_IN_BRANCH"}]}
    assert job(client, lib, j["id"])["status"] == "queued"
    assert client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1, "card_no": "LC00000099"}).status_code == 404
    assert client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 9, "card_no": card["card_no"]}).status_code == 404
    assert client.post(f"{API}/print-jobs/release-by-card", headers=world["mh"][0], json={"printer_id": 1, "card_no": card["card_no"]}).status_code == 403
    assert client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1}).status_code == 422
    client.post(f"{API}/cards/{card['card_no']}/report", headers=lib, json={"reason": "lost"})
    e = err(client.post(f"{API}/print-jobs/release-by-card", headers=lib, json={"printer_id": 1, "card_no": card["card_no"]}), 409, "CARD_NOT_ACTIVE")
    assert e["details"]["status"] == "lost"


# --- effects on other modules -------------------------------------------------------


def test_deactivation_cancels_queued_jobs_without_notification(client, world, app):
    lib = world["lib"]
    a = send(client, world["mh"][0], pages=1)
    b = send(client, world["mh"][1], pages=1)
    buy_pack(client, lib)
    client.post(f"{API}/members/1/deactivate", headers=lib)
    assert job(client, lib, a["id"])["status"] == "cancelled" and job(client, lib, b["id"])["status"] == "queued"
    assert notes(app, "print_job_cancelled") == []
    assert client.get(f"{API}/members/1/print-packs", headers=lib).json()["items"][0]["pages_left"] == 50
    assert len(audit(app, "print_job_cancelled")) == 1


def test_member_summary_and_me(client, world):
    lib, mh = world["lib"], world["mh"][0]
    s = client.get(f"{API}/members/1/summary", headers=lib).json()
    assert s["printing"] == {"free_pages_left": 100, "pack_pages_left": 0, "queued_jobs": 0}
    inside(client, lib)
    buy_pack(client, lib)
    send(client, mh, pages=1)
    send(client, mh, pages=30)
    release(client, mh, 2)
    s = client.get(f"{API}/members/1/summary", headers=mh).json()
    assert s["printing"] == {"free_pages_left": 70, "pack_pages_left": 50, "queued_jobs": 1}
    me = client.get(f"{API}/members/me", headers=mh).json()
    assert me["free_pages_left"] == 70 and me["card_no"] == "LC00000001"


def test_branch_deactivation(client, world, admin_h):
    # branch 2 has no members, copies, rooms or others; a printer blocks it until it is retired
    mk_printer(client, admin_h, "PR-002", branch=2)
    e = err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"{API}/printers/2", headers=admin_h, json={"status": "out_of_service"})
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.patch(f"{API}/printers/2", headers=admin_h, json={"status": "retired"})
    assert client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}).status_code == 200


def test_fee_kinds_can_be_filtered(client, world):
    lib = world["lib"]
    buy_pack(client, lib)
    assert [f["kind"] for f in client.get(f"{API}/fees", headers=lib, params={"kind": "print_pack"}).json()["items"]] == ["print_pack"]
    assert client.get(f"{API}/fees", headers=lib, params={"kind": "printing"}).json()["total"] == 0
    got = client.get(f"{API}/members/1/notifications", headers=world["mh"][0]).json()["items"]
    assert got[0]["type"] == "fee_created" and "print pack" in got[0]["message"] and got[0]["print_job_id"] is None


def test_notification_type_filter_accepts_printing_types(client, world):
    lib = world["lib"]
    for t in ("print_job_cancelled", "print_job_expired", "print_job_failed"):
        assert client.get(f"{API}/notifications", headers=lib, params={"type": t}).status_code == 200


# --- report -------------------------------------------------------------------------


def test_report(client, world, admin_h):
    lib, mh = world["lib"], world["mh"][0]
    mk_printer(client, admin_h, "PR-002", branch=2)
    inside(client, lib)
    g = mk_member(client, lib, 4, "guest")
    gh = member_h(client, 4)
    inside(client, lib, member=g)
    release(client, mh, send(client, mh, pages=10)["id"])
    release(client, gh, send(client, gh, pages=2, color=True)["id"])
    bad = release(client, gh, send(client, gh, pages=3)["id"])
    assert bad["charged_pages"] == 3
    client.post(f"{API}/print-jobs/{bad['id']}/fail", headers=lib, json={"reason": "Paper jam"})
    queued = send(client, mh, pages=1)
    buy_pack(client, lib, 2)
    params = {"from": "2026-11-02", "to": "2026-11-02"}
    got = client.get(f"{API}/reports/printing", headers=lib, params=params).json()
    assert [r["branch_id"] for r in got["items"]] == [1, 2] and got["total"] == 2
    a, b = got["items"]
    assert a == {
        "branch_id": 1, "jobs_printed": 3, "pages": 15, "color_pages": 2, "sheets": 15, "free_pages": 10, "pack_pages": 0,
        "charged_pages": 5, "revenue": "4.00", "packs_sold": 1, "jobs_failed": 1, "refunds_pending": "0.00",
    }
    assert b["jobs_printed"] == 0 and b["packs_sold"] == 0 and b["revenue"] == "0.00"
    one = client.get(f"{API}/reports/printing", headers=lib, params={**params, "branch_id": 2}).json()
    assert [r["branch_id"] for r in one["items"]] == [2]
    assert client.get(f"{API}/reports/printing", headers=lib, params={"from": "2026-11-03", "to": "2026-11-03"}).json()["items"][0]["jobs_printed"] == 0
    for bad_params in ({"from": "2026-11-03", "to": "2026-11-02"}, {"from": "2026-01-01", "to": "2027-01-02"}, {"from": "2026-11-02"}, {"to": "2026-11-02"}, {"from": "x", "to": "y"}):
        assert client.get(f"{API}/reports/printing", headers=lib, params=bad_params).status_code == 422, bad_params
    assert client.get(f"{API}/reports/printing", headers=lib, params={"from": "2026-01-01", "to": "2027-01-01"}).status_code == 200
    assert client.get(f"{API}/reports/printing", headers=mh, params=params).status_code == 403
    assert queued["status"] == "queued"


def test_report_without_printers_is_empty(client, lib):
    got = client.get(f"{API}/reports/printing", headers=lib, params={"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert got["items"] == [] and got["total"] == 0


def test_printing_is_not_exported(client, world, admin_h):
    r = client.get(f"{API}/export/json", headers=admin_h)
    if r.status_code == 200:
        assert not any("print" in key for key in r.json())
