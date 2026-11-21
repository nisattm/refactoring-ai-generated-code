"""Characterization tests (feedback): module 26 (Reading programs). Cases: cases/char_programs.md (issue #115)."""

_seq = [0]


def try_prog(client, lib, branch=None, **fields):
    _seq[0] += 1
    body = {"name": f"Characterization Program {_seq[0]:03d}", "branch_id": branch["id"] if branch else None,
            "starts_on": "2026-11-02", "ends_on": "2026-11-30", "goal_books": 2}
    body.update(fields)
    return client.post("/api/v1/programs", headers=lib, json=body)


def prog(client, lib, branch=None, **fields):
    r = try_prog(client, lib, branch, **fields)
    assert r.status_code == 201, r.text
    return r.json()


def patch(client, lib, p, body, status=200):
    r = client.patch(f"/api/v1/programs/{p['id']}", headers=lib, json=body)
    assert r.status_code == status, r.text
    return r.json()


def fields(r):
    """Expect 422 VALIDATION_ERROR; return the (field, problem) pairs in order."""
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_rdp_01_a(client, librarian):
    """T-CHAR-RDP-01-a (LIB-RDP-02): PATCH unknown program -> 404 NOT_FOUND"""
    r = client.patch("/api/v1/programs/999999", headers=librarian, json={})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "program", "id": 999999}


def test_t_char_rdp_03_a(client, librarian):
    """T-CHAR-RDP-03-a (LIB-RDP-02): rename a draft -> 200 with the new name"""
    p = prog(client, librarian)
    assert patch(client, librarian, p, {"name": "Renamed Reading Program"})["name"] == "Renamed Reading Program"


def test_t_char_rdp_05_a(client, librarian):
    """T-CHAR-RDP-05-a (LIB-RDP-02): PATCH ends_on and reward_waiver of a draft -> 200"""
    p = prog(client, librarian)
    out = patch(client, librarian, p, {"ends_on": "2026-12-01", "reward_waiver": "5.00"})
    assert out["ends_on"] == "2026-12-01"
    assert out["reward_waiver"] == "5.00"


def test_t_char_rdp_07_a(client, librarian):
    """T-CHAR-RDP-07-a (LIB-RDP-02): published program: max_participants 10 -> 200; earlier ends_on -> 422"""
    p = prog(client, librarian)
    r = client.post(f"/api/v1/programs/{p['id']}/publish", headers=librarian)
    assert r.status_code == 200, r.text
    assert patch(client, librarian, p, {"max_participants": 10})["max_participants"] == 10
    r = client.patch(f"/api/v1/programs/{p['id']}", headers=librarian, json={"ends_on": "2026-11-20"})
    assert fields(r) == [("ends_on", "ends_on must not be earlier than today or the current ends_on")]


def test_t_char_rdp_09_a(client, librarian, branch_a, branch_b):
    """T-CHAR-RDP-09-a (LIB-RDP-07): filter by branch_id -> only the program of that branch"""
    pa = prog(client, librarian, branch_a)
    prog(client, librarian, branch_b)
    r = client.get("/api/v1/programs", headers=librarian, params={"branch_id": branch_a["id"]})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["items"]] == [pa["id"]]
