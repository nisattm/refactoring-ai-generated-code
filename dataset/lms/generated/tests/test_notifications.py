import pytest

from tests.test_loans import (  # noqa: F401
    API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret,
)
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_reservations import arrivals, reserve


def notes(client, hd, member, **params):
    r = client.get(f"{API}/members/{member}/notifications", headers=hd, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def types(client, hd, member, **params):
    return [n["type"] for n in reversed(notes(client, hd, member, **params)["items"])]


def test_loan_notifications(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib, 1)
    loan = lend(client, lib, m, c).json()
    first = notes(client, lib, m)["items"][0]
    assert first["type"] == "loan_created" and first["loan_id"] == loan["id"]
    assert "Book 0" in first["message"] and loan["due_date"] in first["message"]
    assert first["read_at"] is None and first["created_at"].endswith("+03:00")
    assert first["reservation_id"] is None and first["fee_id"] is None
    assert client.post(f"{API}/loans/{loan['id']}/renew", headers=lib).status_code == 200
    at(clock, 2026, 11, 20)
    assert ret(client, lib, loan["id"]).status_code == 200
    assert types(client, lib, m) == ["loan_created", "loan_renewed", "loan_returned", "fee_created"]
    fee = notes(client, lib, m, type="fee_created")["items"][0]
    assert fee["fee_id"] == 1 and fee["loan_id"] == loan["id"] and "8.00" in fee["message"]


def test_fee_payment_waive_notifications(client, lib, admin_h, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", price="180.00")
    m = mk_member(client, lib, 1)
    loan = lend(client, lib, m, c).json()
    at(clock, 2026, 11, 18)
    assert client.post(f"{API}/loans/{loan['id']}/report-lost", headers=lib).status_code == 200
    assert types(client, lib, m) == ["loan_created", "loan_lost", "fee_created", "fee_created", "fee_created"]
    amounts = [n["message"] for n in reversed(notes(client, lib, m, type="fee_created")["items"])]
    assert "4.00" in amounts[0] and "180.00" in amounts[1] and "25.00" in amounts[2]
    r = client.post(f"{API}/members/{m}/payments", headers=lib, json={"amount": "10.50", "method": "cash"})
    assert r.status_code == 201
    assert "10.50" in notes(client, lib, m, type="payment_received")["items"][0]["message"]
    admin_h.update(h(token_of(client)))
    assert client.post(f"{API}/fees/3/waive", headers=admin_h, json={"reason": "goodwill"}).status_code == 200
    waived = notes(client, lib, m, type="fee_waived")["items"][0]
    assert waived["fee_id"] == 3 and "25.00" in waived["message"]


def test_membership_notifications(client, lib):
    m = mk_member(client, lib, 1)
    assert notes(client, lib, m)["total"] == 0  # registration does not notify
    r = client.post(f"{API}/members/{m}/renew-membership", headers=lib)
    assert r.json()["valid_until"] in notes(client, lib, m)["items"][0]["message"]
    client.post(f"{API}/members/{m}/deactivate", headers=lib)
    client.post(f"{API}/members/{m}/activate", headers=lib)  # no notification
    assert types(client, lib, m) == ["membership_renewed", "member_deactivated"]


def test_reservation_notifications_e2e(client, lib, clock):
    """LIB-E2E-02 notifications and LIB-NOT-01 for cancellations."""
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001", branch=1)
    s1, s2, s3 = (mk_member(client, lib, n) for n in (1, 2, 3))
    assert lend(client, lib, s1, c).status_code == 201
    r2 = reserve(client, lib, book, 2, s2).json()
    r3 = reserve(client, member_h(client, 3), book, 1).json()
    assert types(client, lib, s2) == []
    at(clock, 2026, 11, 20)
    loan = client.get(f"{API}/loans", headers=lib).json()["items"][0]
    assert ret(client, lib, loan["id"]).status_code == 200
    n = notes(client, lib, s2)["items"][0]
    assert n["type"] == "reservation_in_transit" and n["reservation_id"] == r2["id"] and "Book 0" in n["message"]
    at(clock, 2026, 11, 24)
    assert arrivals(client, lib) == 1
    n = notes(client, lib, s2)["items"][0]
    assert n["type"] == "reservation_ready" and "2026-11-27" in n["message"]
    # the member's own cancellation does not notify, a staff cancellation does
    assert client.post(f"{API}/reservations/{r3['id']}/cancel", headers=member_h(client, 3)).status_code == 200
    assert types(client, lib, s3) == []
    r = reserve(client, lib, book, 1, s3)
    assert client.post(f"{API}/reservations/{r.json()['id']}/cancel", headers=lib).status_code == 200
    assert types(client, lib, s3) == ["reservation_cancelled"]
    # expiry
    at(clock, 2026, 11, 28)
    assert client.post(f"{API}/reservations/process-expired", headers=lib).json() == {"expired": 1}
    assert types(client, lib, s2)[-1] == "reservation_expired"

def test_deactivation_cancel_notifies(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, m1, c)
    assert reserve(client, lib, book, 1, m2).status_code == 201
    assert client.post(f"{API}/members/{m2}/deactivate", headers=lib).status_code == 200
    assert sorted(types(client, lib, m2)) == ["member_deactivated", "reservation_cancelled"]


def test_read_endpoints_and_permissions(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    lend(client, lib, m1, c)
    h1, h2 = member_h(client, 1), member_h(client, 2)
    assert client.get(f"{API}/members/{m1}/notifications/unread-count", headers=h1).json() == {"unread": 1}
    err(client.get(f"{API}/members/{m1}/notifications", headers=h2), 403, "FORBIDDEN")
    err(client.get(f"{API}/members/99/notifications", headers=h2), 404, "NOT_FOUND")
    err(client.get(f"{API}/members/{m1}/notifications"), 401, "UNAUTHENTICATED")
    err(client.post(f"{API}/notifications/1/read", headers=lib), 403, "FORBIDDEN")  # staff cannot mark
    err(client.post(f"{API}/notifications/1/read", headers=h2), 403, "FORBIDDEN")
    err(client.post(f"{API}/notifications/99/read", headers=h2), 404, "NOT_FOUND")
    err(client.post(f"{API}/members/{m1}/notifications/read-all", headers=lib), 403, "FORBIDDEN")
    err(client.post(f"{API}/members/{m1}/notifications/read-all", headers=h2), 403, "FORBIDDEN")
    err(client.get(f"{API}/notifications", headers=h1), 403, "FORBIDDEN")
    r = client.post(f"{API}/notifications/1/read", headers=h1)
    assert r.status_code == 200 and r.json()["read_at"] is not None
    again = client.post(f"{API}/notifications/1/read", headers=h1).json()
    assert again["read_at"] == r.json()["read_at"]
    assert client.get(f"{API}/members/{m1}/notifications/unread-count", headers=h1).json() == {"unread": 0}
    assert notes(client, h1, m1, unread="true")["total"] == 0 and notes(client, h1, m1, unread="false")["total"] == 1
    client.post(f"{API}/loans/1/renew", headers=lib)
    client.post(f"{API}/loans/1/renew", headers=lib)
    assert client.post(f"{API}/members/{m1}/notifications/read-all", headers=h1).json() == {"updated": 1}
    assert client.post(f"{API}/members/{m1}/notifications/read-all", headers=h1).json() == {"updated": 0}
    allr = client.get(f"{API}/notifications", headers=lib, params={"member_id": m1}).json()
    assert allr["total"] == 2 and client.get(f"{API}/notifications", headers=lib).json()["total"] == 2
    assert client.get(f"{API}/notifications", headers=lib, params={"member_id": m2}).json()["total"] == 0
    assert client.get(f"{API}/notifications", headers=lib, params={"page_size": 0}).status_code == 422


def test_reminders(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    book2 = mk_book(client, lib, 1)
    c2 = new_copy(client, lib, book2, "BC-0002")
    m = mk_member(client, lib, 1)
    lend(client, lib, m, c)  # due 2026-11-16 (Monday)
    at(clock, 2026, 11, 13)  # Friday
    r = client.post(f"{API}/notifications/run-reminders", headers=lib)
    assert r.status_code == 200 and r.json() == {"due_reminders": 1, "overdue_notices": 0}
    n = notes(client, lib, m, type="due_reminder")["items"][0]
    assert n["loan_id"] == 1 and "2026-11-16" in n["message"] and "Book 0" in n["message"]
    # no duplicates
    assert client.post(f"{API}/notifications/run-reminders", headers=lib).json() == {"due_reminders": 0, "overdue_notices": 0}
    # a renewal moves the due date and allows a new reminder
    assert client.post(f"{API}/loans/1/renew", headers=lib).status_code == 200  # new due 2026-11-27
    at(clock, 2026, 11, 26)
    assert client.post(f"{API}/notifications/run-reminders", headers=lib).json()["due_reminders"] == 1
    # overdue: one per day
    at(clock, 2026, 11, 30)
    assert client.post(f"{API}/notifications/run-reminders", headers=lib).json() == {"due_reminders": 0, "overdue_notices": 1}
    assert client.post(f"{API}/notifications/run-reminders", headers=lib).json()["overdue_notices"] == 0
    at(clock, 2026, 12, 1)
    assert client.post(f"{API}/notifications/run-reminders", headers=lib).json()["overdue_notices"] == 1
    assert len(notes(client, lib, m, type="overdue_notice")["items"]) == 2
    runs = audit(client.app, "reminders_run")
    assert len(runs) == 6 and runs[-1].details == {"due_reminders": 0, "overdue_notices": 1}
    assert runs[0].actor_user_id is not None
    err(client.post(f"{API}/notifications/run-reminders", headers=member_h(client, 1)), 403, "FORBIDDEN")


def test_audit_member_events(client, lib, app):
    m = mk_member(client, lib, 1)
    client.patch(f"{API}/members/{m}", headers=lib, json={"full_name": "New Name"})
    client.patch(f"{API}/members/{m}", headers=lib, json={"full_name": "New Name"})
    client.post(f"{API}/members/{m}/renew-membership", headers=lib)
    client.post(f"{API}/members/{m}/deactivate", headers=lib)
    client.post(f"{API}/members/{m}/activate", headers=lib)
    for ev in ("member_registered", "member_updated", "membership_renewed", "member_deactivated", "member_activated"):
        entries = audit(app, ev)
        assert len(entries) == 1 and entries[0].entity_type == "member" and entries[0].entity_id == m, ev
        assert entries[0].actor_user_id is not None
    reg = audit(app, "member_registered")[0].details
    assert "password" not in str(reg).lower() and reg["email"] == "m1@example.edu.tr"
    assert audit(app, "member_updated")[0].details["full_name"]["new"] == "New Name"


def test_audit_log_endpoint(client, lib, admin_h, clock):
    m = mk_member(client, lib, 1)
    at(clock, 2026, 11, 5)
    client.post(f"{API}/members/{m}/deactivate", headers=lib)
    err(client.get(f"{API}/audit-log", headers=lib), 403, "FORBIDDEN")
    err(client.get(f"{API}/audit-log"), 401, "UNAUTHENTICATED")
    admin_h.update(h(token_of(client)))
    body = client.get(f"{API}/audit-log", headers=admin_h).json()
    ids = [i["id"] for i in body["items"]]
    assert ids == sorted(ids, reverse=True) and body["total"] == len(ids)
    e = client.get(f"{API}/audit-log", headers=admin_h, params={"event": "member_deactivated"}).json()
    assert e["total"] == 1
    item = e["items"][0]
    assert set(item) == {"id", "at", "actor_user_id", "event", "entity_type", "entity_id", "details"}
    assert item["at"] == "2026-11-05T09:00:00+03:00" and item["entity_type"] == "member" and item["entity_id"] == m
    q = client.get(f"{API}/audit-log", headers=admin_h, params={"entity_type": "member", "entity_id": m}).json()
    assert q["total"] == 2  # registered, deactivated
    day = client.get(f"{API}/audit-log", headers=admin_h, params={"from": "2026-11-05", "to": "2026-11-05"}).json()
    assert {i["event"] for i in day["items"]} >= {"member_deactivated"} and all(
        i["at"].startswith("2026-11-05") for i in day["items"]
    )
    assert client.get(f"{API}/audit-log", headers=admin_h, params={"to": "2026-11-04"}).json()["total"] > 0
    assert client.get(f"{API}/audit-log", headers=admin_h, params={"from": "2026-11-06"}).json()["total"] == 0
    assert client.get(f"{API}/audit-log", headers=admin_h, params={"actor_user_id": 99}).json()["total"] == 0
    err(client.get(f"{API}/audit-log", headers=admin_h, params={"from": "bad"}), 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/audit-log", headers=admin_h, params={"page_size": 2}).json()["page_size"] == 2
    assert client.delete(f"{API}/audit-log", headers=admin_h).status_code == 405


def test_failed_request_rolls_back_notification(client, lib):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib, 1)
    lend(client, lib, m, c)
    assert lend(client, lib, m, c).status_code == 409
    assert notes(client, lib, m)["total"] == 1
