"""Characterization tests (held-out): reports (section 16). Cases: cases/char_reports.md (issue #115)."""


def fields(r):
    """Expect 422 VALIDATION_ERROR; return the (field, problem) pairs in order."""
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_rep_02_a(client, librarian):
    """T-CHAR-REP-02-a (LIB-ROOM-44): GET /reports/room-usage without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/room-usage", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_04_a(client, librarian):
    """T-CHAR-REP-04-a (LIB-DIG-39): GET /reports/digital-usage without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/digital-usage", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_06_a(client, librarian):
    """T-CHAR-REP-06-a (LIB-CRS-46): GET /reports/course-reserves without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/course-reserves", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_08_a(client, librarian):
    """T-CHAR-REP-08-a (LIB-PRE-38): GET /reports/damage-recovery without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/damage-recovery", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_10_a(client, librarian):
    """T-CHAR-REP-10-a (LIB-RDP-44): GET /reports/programs without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/programs", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_12_a(client, librarian):
    """T-CHAR-REP-12-a (LIB-DON-44): GET /reports/donors without year -> 200, items []"""
    r = client.get("/api/v1/reports/donors", headers=librarian)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
