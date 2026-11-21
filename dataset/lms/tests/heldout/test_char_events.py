"""Characterization tests (held-out): module 20 (Events). Cases: cases/char_events.md (issue #115)."""


def test_t_char_evt_02_a(client, librarian, branch_a):
    """T-CHAR-EVT-02-a (LIB-EVT-08): no events; filter by branch_id and series_id -> 200, empty page"""
    r = client.get("/api/v1/events", headers=librarian, params={"branch_id": branch_a["id"], "series_id": 1})
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_t_char_evt_04_a(client, librarian, branch_a):
    """T-CHAR-EVT-04-a (LIB-EVT-01): end before start, unknown room and staff -> 422 with three problems"""
    body = {"title": "Characterization Talk", "kind": "talk", "branch_id": branch_a["id"], "date": "2026-11-10",
            "start_time": "10:00", "end_time": "09:00", "capacity": 10, "room_id": 999999, "staff_id": 999999}
    r = client.post("/api/v1/events", headers=librarian, json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]] == [
        ("end_time", "end_time must be after start_time"),
        ("room_id", "room 999999 does not exist"),
        ("staff_id", "staff 999999 does not exist"),
    ]
