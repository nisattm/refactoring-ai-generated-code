"""Characterization tests (held-out): module 26 (Reading programs). Cases: cases/char_programs.md (issue #115)."""
from support.api import create_book

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


def test_t_char_rdp_02_a(client, librarian):
    """T-CHAR-RDP-02-a (LIB-RDP-01): create with unknown branch -> 422 branch_id"""
    r = try_prog(client, librarian, branch_id=999999)
    assert fields(r) == [("branch_id", "branch 999999 does not exist")]


def test_t_char_rdp_04_a(client, librarian):
    """T-CHAR-RDP-04-a (LIB-RDP-02): PATCH a draft with its own goal_books -> 200, unchanged"""
    p = prog(client, librarian)
    assert patch(client, librarian, p, {"goal_books": 2})["goal_books"] == 2


def test_t_char_rdp_06_a(client, librarian, branch_a, branch_b):
    """T-CHAR-RDP-06-a (LIB-RDP-02): move a draft to another branch -> 200"""
    p = prog(client, librarian, branch_a)
    assert patch(client, librarian, p, {"branch_id": branch_b["id"]})["branch_id"] == branch_b["id"]


def test_t_char_rdp_08_a(client, librarian):
    """T-CHAR-RDP-08-a (LIB-RDP-08): duplicate and unknown book ids -> 422 with both problems"""
    p = prog(client, librarian)
    b = create_book(client, librarian)
    r = client.put(f"/api/v1/programs/{p['id']}/books", headers=librarian, json={"book_ids": [b["id"], b["id"], 999999]})
    assert fields(r) == [("book_ids", "book_ids must be distinct"), ("book_ids.2", "book 999999 does not exist")]
