"""Characterization tests (feedback): staff, shifts and opening hours. Cases: cases/char_staff.md (issue #115)."""


def fields(r):
    """Expect 422 VALIDATION_ERROR; return the (field, problem) pairs in order."""
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_stf_01_a(client, admin, branch_a):
    """T-CHAR-STF-01-a (LIB-STF-12): unknown closure -> 404 NOT_FOUND"""
    r = client.delete("/api/v1/closures/999999", headers=admin)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["details"] == {"resource": "closure", "id": 999999}


def test_t_char_stf_03_a(client, admin, branch_a):
    """T-CHAR-STF-03-a (LIB-STF-14): no from and to -> 422 field required"""
    assert fields(client.get(f"/api/v1/branches/{branch_a['id']}/open-days", headers=admin)) == [("from", "field required"), ("to", "field required")]


def test_t_char_stf_05_a(client, admin, branch_a):
    """T-CHAR-STF-05-a (LIB-STF-24): invalid to date -> 422"""
    assert fields(client.get("/api/v1/shifts", headers=admin, params={"to": "bad"})) == [("to", "expected a valid date in the form YYYY-MM-DD")]


def test_t_char_stf_07_a(client, admin, branch_a):
    """T-CHAR-STF-07-a (LIB-STF-43): from after to -> 422"""
    assert fields(client.get("/api/v1/reports/staff-hours", headers=admin,
                              params={"from": "2026-11-10", "to": "2026-11-01"})) == [("from", "from must not be after to")]


def test_t_char_stf_09_a(client, admin, branch_a):
    """T-CHAR-STF-09-a (LIB-STF-45): neither date nor range -> 422"""
    assert fields(client.get("/api/v1/reports/branch-coverage", headers=admin,
                              params={"branch_id": branch_a["id"]})) == [("date", "either date or from and to is required")]
