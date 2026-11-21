"""Characterization tests (feedback): module 20 (Events). Cases: cases/char_events.md (issue #115)."""


def test_t_char_evt_01_a(client, librarian):
    """T-CHAR-EVT-01-a (LIB-EVT-08): GET unknown event -> 404 NOT_FOUND"""
    r = client.get("/api/v1/events/999999", headers=librarian)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "event", "id": 999999}


def test_t_char_evt_03_a(client, librarian):
    """T-CHAR-EVT-03-a (LIB-EVT-08): no events; search q=xyz -> 200, empty page"""
    r = client.get("/api/v1/events", headers=librarian, params={"q": "xyz"})
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    assert r.json()["total"] == 0
