"""Module 27: Announcements and messages (LIB-MSG-01 to LIB-MSG-47).

The clock starts on Mon 2026-11-02 09:30. Branches 1 (AAA) and 2 (BBB), students 1 to 3.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, make_user, token_of  # noqa: F401
from tests.test_loans import API, at, lend, lib, mk_book, mk_member, member_h, new_copy, ret  # noqa: F401

TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def iso(*a):
    return datetime.datetime(*a, tzinfo=TZ).isoformat()


def ann(client, hd, expect=201, **kw):
    r = client.post(f"{API}/announcements", headers=hd, json={"title": "Hello", "body": "World", **kw})
    assert r.status_code == expect, r.text
    return r.json()


def pub(client, hd, expect=200, **kw):
    a = ann(client, hd, **kw)
    r = client.post(f"{API}/announcements/{a['id']}/publish", headers=hd)
    assert r.status_code == expect, r.text
    return r.json()


def thread(client, mh, expect=201, **kw):
    r = client.post(f"{API}/threads", headers=mh, json={"branch_id": 1, "subject": "Help", "body": "Hi", **kw})
    assert r.status_code == expect, r.text
    return r.json()


def reply(client, hd, tid, expect=201, **kw):
    r = client.post(f"{API}/threads/{tid}/messages", headers=hd, json={"body": "Answer", **kw})
    assert r.status_code == expect, r.text
    return r.json()


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def notes(app, type_):
    return sel(app, sa.select(Notification).where(Notification.type == type_).order_by(Notification.id))


@pytest.fixture
def world(client, lib):
    members = [mk_member(client, lib, n) for n in range(1, 4)]
    mh = [member_h(client, n) for n in range(1, 4)]
    return {"lib": lib, "members": members, "mh": mh}


def test_create_announcement(client, world, clock, admin_h):
    a = ann(client, world["lib"])
    assert a["status"] == "draft" and a["priority"] == "normal" and a["pinned"] is False
    assert a["audience"] == ["student", "academic", "staff", "guest"]
    assert a["publish_at"] == clock.now().isoformat() and a["branch_id"] is None
    assert len(audit(client.app, "announcement_created")) == 1
    ann(client, world["mh"][0], expect=403)
    ann(client, world["lib"], expect=422, audience=[])
    ann(client, world["lib"], expect=422, audience=["x"])
    ann(client, world["lib"], expect=422, audience=["student", "student"])
    ann(client, world["lib"], expect=422, priority="urgent")
    ann(client, world["lib"], expect=422, publish_at="2026-11-03T09:00:00")
    ann(client, world["lib"], expect=422, expires_at=clock.now().isoformat())
    ann(client, world["lib"], expect=422, expires_at=iso(2027, 2, 1, 9, 31))
    ann(client, world["lib"], expect=201, expires_at=iso(2027, 1, 31, 9, 30))
    r = client.post(f"{API}/announcements", headers=world["lib"], json={"title": "a", "body": "b", "branch_id": 99})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"]
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/announcements", headers=world["lib"], json={"title": "a", "body": "b", "branch_id": 2}),
        409, "BRANCH_INACTIVE")


def test_update_and_status_rules(client, world, clock):
    a = ann(client, world["lib"])
    r = client.patch(f"{API}/announcements/{a['id']}", headers=world["lib"], json={"title": "New"})
    assert r.status_code == 200 and r.json()["title"] == "New"
    assert len(audit(client.app, "announcement_updated")) == 1
    client.post(f"{API}/announcements/{a['id']}/publish", headers=world["lib"])
    e = err(client.patch(f"{API}/announcements/{a['id']}", headers=world["lib"], json={"publish_at": iso(2026, 11, 1, 9)}),
            409, "ANNOUNCEMENT_LIVE")
    assert e is not None
    client.post(f"{API}/announcements/{a['id']}/withdraw", headers=world["lib"])
    e = err(client.patch(f"{API}/announcements/{a['id']}", headers=world["lib"], json={"title": "X"}),
            409, "INVALID_ANNOUNCEMENT_STATUS")
    assert e["details"]["status"] == "withdrawn"
    for path in ("publish", "withdraw"):
        err(client.post(f"{API}/announcements/{a['id']}/{path}", headers=world["lib"]), 409, "INVALID_ANNOUNCEMENT_STATUS")


def test_publish_checks_and_pin_limit(client, world, clock):
    a = ann(client, world["lib"], expires_at=iso(2026, 11, 2, 10))
    clock.set(datetime.datetime(2026, 11, 2, 10, tzinfo=TZ))
    err(client.post(f"{API}/announcements/{a['id']}/publish", headers=world["lib"]), 409, "ANNOUNCEMENT_EXPIRED")
    clock.set(datetime.datetime(2026, 11, 2, 9, 30, tzinfo=TZ))
    live = [pub(client, world["lib"], pinned=True, branch_id=1) for _ in range(3)]
    d = ann(client, world["lib"], pinned=True, branch_id=1)
    e = err(client.post(f"{API}/announcements/{d['id']}/publish", headers=world["lib"]), 409, "PIN_LIMIT_REACHED")
    assert e["details"]["limit"] == 3
    pub(client, world["lib"], pinned=True)  # all branches
    client.patch(f"{API}/announcements/{live[0]['id']}", headers=world["lib"], json={"expires_at": iso(2026, 11, 2, 9, 31)})
    clock.set(datetime.datetime(2026, 11, 2, 9, 31, tzinfo=TZ))
    assert client.post(f"{API}/announcements/{d['id']}/publish", headers=world["lib"]).status_code == 200
    got = client.get(f"{API}/announcements/{live[0]['id']}", headers=world["lib"]).json()
    assert got["live"] is False and got["status"] == "published"


def test_schedule_and_process(client, world, clock):
    a = pub(client, world["lib"], priority="important", audience=["student"], publish_at=iso(2026, 11, 3, 9))
    assert a["published_at"] is None and a["scheduled"] is True and a["live"] is False
    assert notes(client.app, "announcement") == []
    assert client.get(f"{API}/announcements", headers=world["mh"][0]).json()["items"] == []
    clock.set(datetime.datetime(2026, 11, 3, 8, 59, tzinfo=TZ))
    r = client.post(f"{API}/messaging/process", headers=world["lib"])
    assert r.json() == {"announcements_released": 0, "threads_closed": 0}
    clock.set(datetime.datetime(2026, 11, 3, 9, 0, tzinfo=TZ))
    r = client.post(f"{API}/messaging/process", headers=world["lib"])
    assert r.json() == {"announcements_released": 1, "threads_closed": 0}
    got = notes(client.app, "announcement")
    assert sorted(n.member_id for n in got) == sorted(world["members"]) and got[0].announcement_id == a["id"]
    assert "Hello" in got[0].message
    r = client.post(f"{API}/messaging/process", headers=world["lib"])
    assert r.json()["announcements_released"] == 0
    assert len(notes(client.app, "announcement")) == 3
    assert len(audit(client.app, "messaging_processed")) == 3
    assert client.get(f"{API}/announcements/{a['id']}", headers=world["lib"]).json()["published_at"] is not None
    err(client.post(f"{API}/messaging/process", headers=world["mh"][0]), 403, "FORBIDDEN")


def test_immediate_important_notifies_active_audience(client, world):
    client.post(f"{API}/members/{world['members'][2]}/deactivate", headers=world["lib"])
    pub(client, world["lib"], priority="important", branch_id=1)
    assert len(notes(client.app, "announcement")) == 2
    pub(client, world["lib"], priority="normal")
    assert len(notes(client.app, "announcement")) == 2


def test_member_feed_read_and_order(client, world, clock):
    old = pub(client, world["lib"], title="old", publish_at=iso(2026, 10, 1, 9))
    new = pub(client, world["lib"], title="new")
    pinned = pub(client, world["lib"], title="pinned", pinned=True, publish_at=iso(2026, 9, 1, 9))
    pub(client, world["lib"], title="other", audience=["guest"])
    pub(client, world["lib"], title="branch2", branch_id=2)
    ann(client, world["lib"], title="draft")
    r = client.get(f"{API}/announcements", headers=world["mh"][0]).json()
    assert [i["title"] for i in r["items"]] == ["pinned", "new", "old"]
    assert r["unread"] == 3 and r["total"] == 3 and all(i["read"] is False for i in r["items"])
    r = client.post(f"{API}/announcements/{old['id']}/read", headers=world["mh"][0])
    assert r.status_code == 200 and r.json()["announcement_id"] == old["id"]
    first = r.json()["read_at"]
    clock.advance(minutes=5)
    assert client.post(f"{API}/announcements/{old['id']}/read", headers=world["mh"][0]).json()["read_at"] == first
    r = client.get(f"{API}/announcements", headers=world["mh"][0]).json()
    assert r["unread"] == 2 and [i["read"] for i in r["items"]] == [False, False, True]
    assert client.get(f"{API}/announcements/{new['id']}", headers=world["mh"][0]).json()["read"] is True
    assert client.get(f"{API}/announcements", headers=world["mh"][0]).json()["unread"] == 1
    other = client.get(f"{API}/announcements", headers=world["lib"]).json()["items"]
    assert [i["title"] for i in other[:3]] == ["draft", "branch2", "other"] and "read" not in other[0]
    for i in range(3):
        err(client.get(f"{API}/announcements/{other[i]['id']}", headers=world["mh"][0]), 404, "NOT_FOUND")
        err(client.post(f"{API}/announcements/{other[i]['id']}/read", headers=world["mh"][0]), 404, "NOT_FOUND")
    err(client.post(f"{API}/announcements/{old['id']}/read", headers=world["lib"]), 403, "FORBIDDEN")
    s = client.get(f"{API}/members/{world['members'][0]}/summary", headers=world["lib"]).json()
    assert s["messages"] == {"unread_announcements": 1, "open_threads": 0, "unread_replies": 0}
    assert pinned["id"]


def test_edit_clears_reads_and_stats(client, world):
    a = pub(client, world["lib"], audience=["student", "academic"], branch_id=1)
    mk_member(client, world["lib"], 4, "academic")
    client.post(f"{API}/announcements/{a['id']}/read", headers=world["mh"][0])
    s = client.get(f"{API}/announcements/{a['id']}/stats", headers=world["lib"]).json()
    assert s == {"audience_size": 4, "reads": 1, "read_rate": "25.0"}
    client.patch(f"{API}/announcements/{a['id']}", headers=world["lib"], json={"pinned": True})
    assert client.get(f"{API}/announcements/{a['id']}/stats", headers=world["lib"]).json()["reads"] == 1
    client.patch(f"{API}/announcements/{a['id']}", headers=world["lib"], json={"body": "changed"})
    assert client.get(f"{API}/announcements/{a['id']}/stats", headers=world["lib"]).json()["reads"] == 0
    assert client.get(f"{API}/announcements", headers=world["mh"][0]).json()["unread"] == 1
    empty = pub(client, world["lib"], audience=["guest"])
    assert client.get(f"{API}/announcements/{empty['id']}/stats", headers=world["lib"]).json()["read_rate"] == "0.0"
    err(client.get(f"{API}/announcements/{a['id']}/stats", headers=world["mh"][0]), 403, "FORBIDDEN")


def test_staff_list_filters(client, world, clock):
    ann(client, world["lib"])
    pub(client, world["lib"], branch_id=1)
    pub(client, world["lib"], publish_at=iso(2026, 11, 5, 9))
    w = pub(client, world["lib"])
    client.post(f"{API}/announcements/{w['id']}/withdraw", headers=world["lib"])
    r = client.get(f"{API}/announcements", headers=world["lib"]).json()
    assert [i["id"] for i in r["items"]] == [4, 3, 2, 1]

    def ids(q):
        return [i["id"] for i in client.get(f"{API}/announcements?{q}", headers=world["lib"]).json()["items"]]

    assert ids("status=draft") == [1] and ids("branch_id=1") == [2]
    assert ids("scheduled=true") == [3] and ids("live=true") == [2]
    assert ids("live=false") == [4, 3, 1]


def relog(client, world):
    """Tokens expire when the clock jumps by weeks."""
    for n, hd in enumerate(world["mh"], 1):
        hd.update(h(token_of(client, f"m{n}@example.edu.tr", "Passw0rd1")))
    world["lib"].update(h(token_of(client, "lib@example.com", "Passw0rd1")))


def test_thread_flow_and_example(client, world, clock):
    t = thread(client, world["mh"][0])
    assert t["status"] == "open" and t["due_at"] == iso(2026, 11, 4, 9, 30) and len(t["messages"]) == 1
    assert t["messages"][0]["author"] == "member" and "member" not in t
    clock.set(datetime.datetime(2026, 11, 2, 10, tzinfo=TZ))
    reply(client, world["lib"], t["id"], internal=True)
    assert client.get(f"{API}/threads/{t['id']}", headers=world["mh"][0]).json()["status"] == "open"
    assert notes(client.app, "message_reply") == []
    clock.set(datetime.datetime(2026, 11, 2, 11, tzinfo=TZ))
    reply(client, world["lib"], t["id"])
    mine = client.get(f"{API}/threads", headers=world["mh"][0]).json()["items"][0]
    assert mine["status"] == "answered" and mine["first_reply_at"] == iso(2026, 11, 2, 11) and mine["due_at"] is None
    assert mine["unread"] == 1 and mine["last_message_at"] == iso(2026, 11, 2, 11)
    n = notes(client.app, "message_reply")
    assert len(n) == 1 and n[0].thread_id == t["id"] and "Help" in n[0].message
    s = client.get(f"{API}/members/{world['members'][0]}/summary", headers=world["lib"]).json()
    assert s["messages"] == {"unread_announcements": 0, "open_threads": 1, "unread_replies": 1}
    full = client.get(f"{API}/threads/{t['id']}", headers=world["mh"][0]).json()
    assert [m["internal"] for m in full["messages"]] == [False, False] and full["messages"][1]["read_at"] is not None
    assert full["unread"] == 0 and full["assigned_to"] is not None
    clock.set(datetime.datetime(2026, 11, 2, 12, tzinfo=TZ))
    reply(client, world["mh"][0], t["id"])
    got = client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()
    assert got["status"] == "open" and got["due_at"] == iso(2026, 11, 4, 12)
    assert got["member"]["member_no"] == "M000001" and len(got["messages"]) == 4
    assert len(audit(client.app, "thread_message_added")) == 3 and len(audit(client.app, "thread_created")) == 1
    assert all(m["read_at"] is None for m in got["messages"] if m["internal"])
    reply(client, world["mh"][0], t["id"], expect=422, internal=True)
    err(client.get(f"{API}/threads/{t['id']}", headers=world["mh"][1]), 404, "NOT_FOUND")
    err(client.post(f"{API}/threads/{t['id']}/messages", headers=world["mh"][1], json={"body": "x"}), 403, "FORBIDDEN")


def test_thread_write_checks(client, world, admin_h):
    thread(client, world["lib"], expect=403)
    thread(client, world["mh"][0], expect=422, category="x")
    thread(client, world["mh"][0], expect=422, loan_id=1)
    thread(client, world["mh"][0], expect=422, fee_id=1, category="loan")
    thread(client, world["mh"][0], expect=404, branch_id=99)
    for _ in range(3):
        thread(client, world["mh"][0])
    e = err(client.post(f"{API}/threads", headers=world["mh"][0], json={"branch_id": 1, "subject": "s", "body": "b"}),
            409, "THREAD_LIMIT_REACHED")
    assert e["details"]["limit"] == 3
    client.post(f"{API}/threads/1/close", headers=world["mh"][0])
    thread(client, world["mh"][0])
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/threads", headers=world["mh"][1], json={"branch_id": 2, "subject": "s", "body": "b"}),
        409, "BRANCH_INACTIVE")
    client.post(f"{API}/members/{world['members'][2]}/deactivate", headers=world["lib"])
    err(client.post(f"{API}/threads", headers=world["mh"][2], json={"branch_id": 1, "subject": "s", "body": "b"}),
        409, "MEMBER_PASSIVE")


def test_records_in_thread(client, world):
    book = mk_book(client, world["lib"], 0)
    copy = new_copy(client, world["lib"], book, "BC0001")
    loan = lend(client, world["lib"], world["members"][0], copy).json()["id"]
    t = thread(client, world["mh"][0], category="loan", loan_id=loan)
    e = err(client.post(f"{API}/threads", headers=world["mh"][1],
                        json={"branch_id": 1, "subject": "s", "body": "b", "category": "loan", "loan_id": loan}),
            409, "NOT_OWN_RECORD")
    assert e["details"]["field"] == "loan_id"
    staff = client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()
    assert staff["loan"]["id"] == loan and staff["loan"]["status"] == "open" and "fee" not in staff
    assert "loan" not in client.get(f"{API}/threads/{t['id']}", headers=world["mh"][0]).json()


def test_message_limit(client, world, clock):
    t = thread(client, world["mh"][0])
    for _ in range(9):
        reply(client, world["mh"][0], t["id"])
    e = err(client.post(f"{API}/threads/{t['id']}/messages", headers=world["mh"][0], json={"body": "x"}),
            409, "MESSAGE_LIMIT_REACHED")
    assert e["details"]["limit"] == 10
    for _ in range(12):
        reply(client, world["lib"], t["id"])
    clock.advance(days=1)
    reply(client, world["mh"][0], t["id"])


def test_assign_close_reopen_rate(client, world, clock, admin_h):
    t = thread(client, world["mh"][0])
    other = make_user(client, admin_h, email="two@example.com")
    r = client.post(f"{API}/threads/{t['id']}/assign", headers=world["lib"], json={"user_id": other["id"]})
    assert r.status_code == 200 and r.json()["assigned_to"] == other["id"]
    reply(client, world["lib"], t["id"])
    assert client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()["assigned_to"] == other["id"]
    client.post(f"{API}/threads/{t['id']}/assign", headers=world["lib"], json={"user_id": None})
    assert client.post(f"{API}/threads/{t['id']}/assign", headers=world["lib"], json={"user_id": 99}).status_code == 422
    err(client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0]), 409, "THREAD_NOT_CLOSED")
    err(client.post(f"{API}/threads/{t['id']}/rate", headers=world["mh"][0], json={"rating": 5}), 409, "THREAD_NOT_CLOSED")
    r = client.post(f"{API}/threads/{t['id']}/close", headers=world["lib"])
    assert r.json()["status"] == "closed" and r.json()["close_reason"] == "staff_request"
    err(client.post(f"{API}/threads/{t['id']}/close", headers=world["lib"]), 409, "THREAD_CLOSED")
    err(client.post(f"{API}/threads/{t['id']}/assign", headers=world["lib"], json={"user_id": None}), 409, "THREAD_CLOSED")
    err(client.post(f"{API}/threads/{t['id']}/messages", headers=world["lib"], json={"body": "x"}), 409, "THREAD_CLOSED")
    assert client.post(f"{API}/threads/{t['id']}/rate", headers=world["mh"][0], json={"rating": 6}).status_code == 422
    assert client.post(f"{API}/threads/{t['id']}/rate", headers=world["mh"][0], json={"rating": 4}).json()["rating"] == 4
    err(client.post(f"{API}/threads/{t['id']}/rate", headers=world["mh"][0], json={"rating": 5}), 409, "ALREADY_RATED")
    clock.advance(days=14)
    relog(client, world)
    r = client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0])
    assert r.status_code == 200 and r.json()["status"] == "open" and r.json()["close_reason"] is None
    assert r.json()["closed_at"] is None and r.json()["due_at"] is not None
    client.post(f"{API}/threads/{t['id']}/close", headers=world["mh"][0])
    assert client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()["close_reason"] == "member_request"
    clock.advance(days=14, minutes=1)
    relog(client, world)
    err(client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0]), 409, "THREAD_REOPEN_NOT_ALLOWED")
    t2 = thread(client, world["mh"][1])
    client.post(f"{API}/threads/{t2['id']}/close", headers=world["mh"][1])
    err(client.post(f"{API}/threads/{t2['id']}/rate", headers=world["mh"][1], json={"rating": 3}), 409, "NOTHING_TO_RATE")
    for name in ("thread_assigned", "thread_closed", "thread_reopened", "thread_rated"):
        assert audit(client.app, name)


def test_reopen_limit(client, world):
    t = thread(client, world["mh"][0])
    client.post(f"{API}/threads/{t['id']}/close", headers=world["mh"][0])
    for _ in range(3):
        thread(client, world["mh"][0])
    err(client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0]), 409, "THREAD_LIMIT_REACHED")


def test_overdue_and_due_dates(client, world, clock):
    clock.set(datetime.datetime(2026, 11, 6, 16, tzinfo=TZ))
    t = thread(client, world["mh"][0])
    assert t["due_at"] == iso(2026, 11, 10, 16)
    clock.set(datetime.datetime(2026, 11, 10, 16, tzinfo=TZ))
    assert client.get(f"{API}/threads?overdue=true", headers=world["lib"]).json()["total"] == 0
    clock.set(datetime.datetime(2026, 11, 10, 18, 59, tzinfo=TZ))
    r = client.get(f"{API}/threads?overdue=true", headers=world["lib"]).json()
    assert r["total"] == 1 and r["items"][0]["overdue_by_hours"] == 2 and r["items"][0]["is_overdue"] is True
    assert client.get(f"{API}/threads?overdue=false", headers=world["lib"]).json()["total"] == 0
    assert client.get(f"{API}/threads?assigned_to=me", headers=world["lib"]).json()["total"] == 0
    rep = client.get(f"{API}/reports/messaging?from=2026-11-01&to=2026-11-30", headers=world["lib"]).json()
    assert rep["overdue_now"] == 1


def test_inactive_threads(client, world, clock):
    t = thread(client, world["mh"][0])
    clock.set(datetime.datetime(2026, 11, 2, 10, tzinfo=TZ))
    reply(client, world["lib"], t["id"])
    clock.set(datetime.datetime(2026, 11, 16, 10, tzinfo=TZ))
    assert client.post(f"{API}/messaging/process", headers=world["lib"]).json()["threads_closed"] == 0
    clock.set(datetime.datetime(2026, 11, 16, 10, 0, 1, tzinfo=TZ))
    assert client.post(f"{API}/messaging/process", headers=world["lib"]).json()["threads_closed"] == 1
    relog(client, world)
    got = client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()
    assert got["status"] == "closed" and got["close_reason"] == "inactive"
    assert client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0]).status_code == 200


def test_member_deactivation_and_user_deactivation(client, world, admin_h):
    t = thread(client, world["mh"][0])
    t2 = thread(client, world["mh"][0])
    client.post(f"{API}/threads/{t2['id']}/close", headers=world["mh"][0])
    other = make_user(client, admin_h, email="two@example.com")
    client.post(f"{API}/threads/{t['id']}/assign", headers=world["lib"], json={"user_id": other["id"]})
    r = client.patch(f"{API}/users/{other['id']}", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200
    assert client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()["assigned_to"] is None
    assert client.post(f"{API}/members/{world['members'][0]}/deactivate", headers=world["lib"]).status_code == 200
    got = client.get(f"{API}/threads/{t['id']}", headers=world["lib"]).json()
    assert got["status"] == "closed" and got["close_reason"] == "member_deactivated"
    err(client.post(f"{API}/threads/{t['id']}/reopen", headers=world["mh"][0]), 409, "THREAD_REOPEN_NOT_ALLOWED")
    assert client.get(f"{API}/threads/{t2['id']}", headers=world["lib"]).json()["close_reason"] == "member_request"


def test_branch_with_announcement_in_use(client, world, admin_h):
    r = client.post(f"{API}/branches", headers=admin_h, json={"code": "CCC", "name": "Third", "address": "x"})
    assert r.status_code == 201, r.text
    b = r.json()["id"]
    a = pub(client, world["lib"], branch_id=b)
    err(client.patch(f"{API}/branches/{b}", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/announcements/{a['id']}/withdraw", headers=world["lib"])
    assert client.patch(f"{API}/branches/{b}", headers=admin_h, json={"is_active": False}).status_code == 200


def test_branch_with_thread_in_use(client, world, admin_h):
    r = client.post(f"{API}/branches", headers=admin_h, json={"code": "CCC", "name": "Third", "address": "x"})
    assert r.status_code == 201, r.text
    b = r.json()["id"]
    t = thread(client, world["mh"][0], branch_id=b)
    err(client.patch(f"{API}/branches/{b}", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/threads/{t['id']}/close", headers=world["mh"][0])
    assert client.patch(f"{API}/branches/{b}", headers=admin_h, json={"is_active": False}).status_code == 200


def test_type_change_keeps_reads(client, world):
    a = pub(client, world["lib"], audience=["academic"])
    assert client.get(f"{API}/announcements", headers=world["mh"][0]).json()["total"] == 0
    r = client.patch(f"{API}/members/{world['members'][0]}", headers=world["lib"], json={"membership_type": "academic"})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/announcements", headers=world["mh"][0]).json()["total"] == 1
    client.post(f"{API}/announcements/{a['id']}/read", headers=world["mh"][0])


def test_plural_audience_and_notification_columns(client, world):
    a = pub(client, world["lib"], audience=["students", "academics"], priority="important")
    assert a["audience"] == ["students", "academics"]
    r = client.get(f"{API}/members/{world['members'][0]}/notifications", headers=world["mh"][0]).json()["items"]
    assert r[0]["type"] == "announcement" and r[0]["announcement_id"] == a["id"] and r[0]["thread_id"] is None
    t = thread(client, world["mh"][0])
    reply(client, world["lib"], t["id"])
    r = client.get(f"{API}/notifications?type=message_reply", headers=world["lib"]).json()["items"]
    assert r[0]["thread_id"] == t["id"] and r[0]["announcement_id"] is None


def test_messaging_report(client, world, clock):
    t = thread(client, world["mh"][0], category="fee")
    thread(client, world["mh"][1])
    clock.advance(hours=3)
    reply(client, world["lib"], t["id"])
    client.post(f"{API}/threads/{t['id']}/close", headers=world["mh"][0])
    client.post(f"{API}/threads/{t['id']}/rate", headers=world["mh"][0], json={"rating": 5})
    a = pub(client, world["lib"], priority="important")
    client.post(f"{API}/announcements/{a['id']}/read", headers=world["mh"][0])
    r = client.get(f"{API}/reports/messaging?from=2026-11-02&to=2026-11-02", headers=world["lib"])
    assert r.status_code == 200, r.text
    assert r.json() == {
        "threads": 2,
        "by_category": {"general": 1, "loan": 0, "fee": 1, "room": 0, "other": 0},
        "answered": 1,
        "average_first_reply_hours": "3.0",
        "overdue_now": 0,
        "closed": 1,
        "average_rating": "5.0",
        "announcements": {"published": 1, "important": 1, "reads": 1},
    }
    q = client.get(f"{API}/reports/messaging?from=2026-11-02&to=2026-11-02&branch_id=2", headers=world["lib"]).json()
    assert q["threads"] == 0 and q["average_rating"] is None
    for q in ("from=2026-11-03&to=2026-11-02", "from=2025-01-01&to=2026-11-02", "from=2026-11-02"):
        assert client.get(f"{API}/reports/messaging?{q}", headers=world["lib"]).status_code == 422
    assert client.get(f"{API}/reports/messaging?from=2026-11-02&to=2026-11-02", headers=world["mh"][0]).status_code == 403
