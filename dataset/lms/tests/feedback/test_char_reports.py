"""Characterization tests (feedback): reports (section 16). Cases: cases/char_reports.md (issue #115)."""


def fields(r):
    """Expect 422 VALIDATION_ERROR; return the (field, problem) pairs in order."""
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_rep_01_a(client, librarian):
    """T-CHAR-REP-01-a (LIB-REP-01): GET /reports/most-borrowed without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/most-borrowed", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_03_a(client, librarian):
    """T-CHAR-REP-03-a (LIB-EQ-40): GET /reports/equipment-usage without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/equipment-usage", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_05_a(client, librarian):
    """T-CHAR-REP-05-a (LIB-ILL-38): GET /reports/ill-activity without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/ill-activity", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_07_a(client, librarian):
    """T-CHAR-REP-07-a (LIB-DON-43): GET /reports/donations without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/donations", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_09_a(client, librarian):
    """T-CHAR-REP-09-a (LIB-SUG-44): GET /reports/suggestions without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/suggestions", headers=librarian)) == [("from", "field required"), ("to", "field required")]


def test_t_char_rep_11_a(client, librarian):
    """T-CHAR-REP-11-a (LIB-MSG-39): GET /reports/messaging without from and to -> 422, both field required"""
    assert fields(client.get("/api/v1/reports/messaging", headers=librarian)) == [("from", "field required"), ("to", "field required")]
