from tests.test_auth import admin_h, audit, err  # noqa: F401
from tests.test_loans import API, at, copy_of, lend, lib, member_h, mk_book, mk_member, new_copy, ret  # noqa: F401
from tests.test_reservations import arrivals, reserve  # noqa: F401


def relocate(client, hd, copy_id, to):
    return client.post(f"{API}/transfers", headers=hd, json={"copy_id": copy_id, "to_branch_id": to})


def test_relocation_lifecycle(client, lib, clock, app):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    at(clock, 2026, 11, 6)  # Friday
    r = relocate(client, lib, c, 2)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t == {
        "id": 1, "copy_id": c, "from_branch_id": 1, "to_branch_id": 2, "reason": "relocation",
        "reservation_id": None, "started_on": "2026-11-06", "expected_on": "2026-11-10",
        "status": "in_transit", "received_on": None,
    }
    cp = copy_of(client, lib, c)
    assert cp["status"] == "in_transfer" and cp["current_branch_id"] is None
    assert [a.entity_id for a in audit(app, "transfer_started")] == [1]
    at(clock, 2026, 11, 9)
    assert arrivals(client, lib) == 0
    at(clock, 2026, 11, 10)
    assert arrivals(client, lib) == 1
    cp = copy_of(client, lib, c)
    assert (cp["status"], cp["current_branch_id"], cp["home_branch_id"]) == ("available", 2, 2)
    got = client.get(f"{API}/transfers/1", headers=lib).json()
    assert got["status"] == "received" and got["received_on"] == "2026-11-10"
    assert arrivals(client, lib) == 0


def test_relocation_checks(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib)
    assert err(relocate(client, lib, c, 1), 409, "SAME_BRANCH")
    assert err(relocate(client, lib, 99, 2), 404, "NOT_FOUND")["details"] == {"field": "copy_id", "id": 99}
    assert err(relocate(client, lib, c, 99), 404, "NOT_FOUND")["details"] == {"field": "to_branch_id", "id": 99}
    assert err(client.post(f"{API}/transfers", headers=lib, json={"copy_id": c}), 422, "VALIDATION_ERROR")
    lend(client, lib, m, c)
    assert err(relocate(client, lib, c, 2), 409, "INVALID_COPY_STATUS")
    # BRANCH_INACTIVE comes before INVALID_COPY_STATUS
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    assert err(relocate(client, lib, c, 2), 409, "BRANCH_INACTIVE")


def test_transfer_permissions_and_lists(client, lib, admin_h):
    book = mk_book(client, lib, 0)
    c1 = new_copy(client, lib, book, "BC-0001")
    c2 = new_copy(client, lib, book, "BC-0002", branch=2)
    m = mk_member(client, lib)
    mh = member_h(client, 1)
    assert err(relocate(client, mh, c1, 2), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/transfers", headers=mh), 403, "FORBIDDEN")
    assert err(client.post(f"{API}/transfers/process-arrivals", headers=mh), 403, "FORBIDDEN")
    assert err(client.get(f"{API}/transfers"), 401, "UNAUTHENTICATED")
    assert relocate(client, admin_h, c1, 2).status_code == 201
    assert relocate(client, lib, c2, 1).status_code == 201
    items = client.get(f"{API}/transfers", headers=lib).json()["items"]
    assert [t["id"] for t in items] == [2, 1]
    q = lambda s: client.get(f"{API}/transfers?{s}", headers=lib).json()["total"]  # noqa: E731
    assert q(f"copy_id={c1}") == 1 and q("from_branch_id=2") == 1 and q("to_branch_id=2") == 1
    assert q("reason=relocation") == 2 and q("reason=return_home") == 0 and q("status=received") == 0
    assert err(client.get(f"{API}/transfers?reason=x", headers=lib), 422, "VALIDATION_ERROR")
    assert err(client.get(f"{API}/transfers/99", headers=lib), 404, "NOT_FOUND")
    assert m


def test_return_home_transfer(client, lib, clock):
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m = mk_member(client, lib)
    loan = lend(client, lib, m, c).json()
    assert ret(client, lib, loan["id"], branch=2).status_code == 200
    t = client.get(f"{API}/transfers/1", headers=lib).json()
    assert (t["reason"], t["from_branch_id"], t["to_branch_id"], t["expected_on"]) == ("return_home", 2, 1, "2026-11-04")
    at(clock, 2026, 11, 4)
    assert arrivals(client, lib) == 1
    cp = copy_of(client, lib, c)
    assert (cp["status"], cp["current_branch_id"]) == ("available", 1)


def test_arrival_with_waiting_reservation_continues(client, lib, clock):
    """A relocated copy that arrives while someone waits is given to the first reservation."""
    book = mk_book(client, lib, 0)
    c = new_copy(client, lib, book, "BC-0001")
    m1, m2 = mk_member(client, lib, 1), mk_member(client, lib, 2)
    relocate(client, lib, c, 2)
    assert reserve(client, lib, book, 2, m1).status_code == 201  # nothing available: waits
    at(clock, 2026, 11, 4)
    assert arrivals(client, lib) == 1
    r = client.get(f"{API}/reservations/1", headers=lib).json()
    assert r["status"] == "ready" and r["copy_id"] == c
    assert m2
