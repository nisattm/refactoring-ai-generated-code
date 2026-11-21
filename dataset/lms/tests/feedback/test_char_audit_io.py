"""Characterization tests (feedback): module 13 (Audit log, import and export). Cases: cases/char_audit_io.md (issue #115)."""


def dataset():
    """Small valid dataset (same as feedback/test_audit_io.py)."""
    return {
        "format_version": 1,
        "branches": [{"id": 1, "code": "MERKEZ", "name": "Central", "address": "", "is_active": True},
                     {"id": 2, "code": "KAMPUS", "name": "Campus, North", "address": "Çankaya", "is_active": True}],
        "authors": [{"id": 1, "name": "Sabahattin Ali"}],
        "publishers": [{"id": 1, "name": "Example Publishing"}],
        "books": [{"id": 7, "isbn": "9780306406157", "title": "Kürk Mantolu Madonna", "subtitle": None, "author_ids": [1],
                   "publisher_id": 1, "publication_year": 1943, "language": "tr", "classification": "813.54"}],
        "copies": [{"id": 1, "book_id": 7, "barcode": "C000001", "home_branch_id": 1, "current_branch_id": 1, "price": "150.00",
                    "status": "on_loan", "acquired_on": "2025-09-01", "shelf_location": None},
                   {"id": 2, "book_id": 7, "barcode": "C000002", "home_branch_id": 2, "current_branch_id": 2, "price": "150.00",
                    "status": "available", "acquired_on": "2025-09-01", "shelf_location": "A-1"}],
        "members": [{"id": 1, "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr", "phone": None, "membership_type": "student",
                     "university_id": "20231234", "home_branch_id": 1, "status": "active", "membership_start": "2026-09-15",
                     "valid_until": "2027-09-14"},
                    {"id": 2, "full_name": "John Smith", "email": "john@example.com", "phone": "+905320000000", "membership_type": "guest",
                     "university_id": None, "home_branch_id": 2, "status": "active", "membership_start": "2026-10-01",
                     "valid_until": "2026-12-29"}],
        "loans": [{"id": 1, "copy_id": 1, "member_id": 2, "branch_id": 1, "loan_date": "2026-10-26", "due_date": "2026-11-02",
                   "renewal_count": 0, "status": "open", "returned_on": None, "return_branch_id": None}],
    }


def loan(**kw):
    data = {"id": 1, "copy_id": 1, "member_id": 2, "branch_id": 1, "loan_date": "2026-10-26", "due_date": "2026-11-02",
            "renewal_count": 0, "status": "open", "returned_on": None, "return_branch_id": None}
    data.update(kw)
    return data


def problems(client, admin, data):
    """Import ``data``; expect 422 VALIDATION_ERROR and return the (field, problem) pairs in order."""
    r = client.post("/api/v1/import", headers=admin, json=data)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    return [(f["field"], f["problem"]) for f in r.json()["error"]["details"]["fields"]]


def test_t_char_io_01_a(client, admin):
    """T-CHAR-IO-01-a (LIB-IO-03): body is a list -> exactly (body, the dataset must be a JSON object)"""
    assert problems(client, admin, []) == [("body", "the dataset must be a JSON object")]


def test_t_char_io_03_a(client, admin):
    """T-CHAR-IO-03-a (LIB-IO-03): non-object book element -> (books[1], must be an object)"""
    data = dataset()
    data["books"].append("x")
    assert ("books[1]", "must be an object") in problems(client, admin, data)


def test_t_char_io_05_a(client, admin):
    """T-CHAR-IO-05-a (LIB-IO-04): valid_until before membership_start; guest without phone"""
    data = dataset()
    data["members"][0]["valid_until"] = "2026-09-01"
    data["members"][1]["phone"] = None
    found = problems(client, admin, data)
    assert ("members[0].valid_until", "valid_until must not be before membership_start") in found
    assert ("members[1].phone", "phone is required for guests") in found


def test_t_char_io_07_a(client, admin):
    """T-CHAR-IO-07-a (LIB-IO-06): returned loans without returned_on/return_branch_id, or returned before loan_date"""
    data = dataset()
    data["loans"].append(loan(id=2, copy_id=2, status="returned"))
    data["loans"].append(loan(id=3, copy_id=2, status="returned", returned_on="2026-10-20", return_branch_id=1))
    found = problems(client, admin, data)
    assert ("loans[1].returned_on", "returned_on is required for a returned loan") in found
    assert ("loans[1].return_branch_id", "return_branch_id is required for a returned loan") in found
    assert ("loans[2].returned_on", "returned_on must not be before loan_date") in found


def test_t_char_io_09_a(client, admin):
    """T-CHAR-IO-09-a (LIB-IO-04): member e-mail of the bootstrap admin -> exactly (members[0].email, ... already exists)"""
    data = dataset()
    data["members"][0]["email"] = "admin@library.local"
    assert problems(client, admin, data) == [("members[0].email", "a user with this e-mail address already exists")]
