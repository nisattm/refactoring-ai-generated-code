"""Characterization tests (held-out): staff, shifts and opening hours. Cases: cases/char_staff.md (issue #115)."""


def fields(r):
    """Expect 422 VALIDATION_ERROR; return the (field, problem) pairs in order."""
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_stf_02_a(client, admin, branch_a):
    """T-CHAR-STF-02-a (LIB-STF-13): invalid from date -> 422"""
    assert fields(client.get("/api/v1/closures", headers=admin, params={"from": "2026-13-01"})) == [("from", "expected a valid date in the form YYYY-MM-DD")]


def test_t_char_stf_04_a(client, admin, branch_a):
    """T-CHAR-STF-04-a (LIB-STF-14): from after to -> 422"""
    assert fields(client.get(f"/api/v1/branches/{branch_a['id']}/open-days", headers=admin,
                              params={"from": "2026-11-10", "to": "2026-11-01"})) == [("from", "from must not be after to")]


def test_t_char_stf_06_a(client, admin, branch_a):
    """T-CHAR-STF-06-a (LIB-STF-43): no from and to -> 422 field required"""
    assert fields(client.get("/api/v1/reports/staff-hours", headers=admin)) == [("from", "field required"), ("to", "field required")]


def test_t_char_stf_08_a(client, admin, branch_a):
    """T-CHAR-STF-08-a (LIB-STF-44): invalid date -> 422"""
    assert fields(client.get("/api/v1/reports/branch-coverage", headers=admin,
                              params={"branch_id": branch_a["id"], "date": "bad"})) == [("date", "expected a valid date in the form YYYY-MM-DD")]


def test_t_char_stf_10_a(client, admin, branch_a):
    """T-CHAR-STF-10-a (LIB-STF-45): from after to -> 422"""
    assert fields(client.get("/api/v1/reports/branch-coverage", headers=admin,
                              params={"branch_id": branch_a["id"], "from": "2026-11-10", "to": "2026-11-01"})) == [("from", "from must not be after to")]
