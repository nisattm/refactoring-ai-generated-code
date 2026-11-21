"""Characterization tests (held-out): module 13 (Audit log, import and export). Cases: cases/char_audit_io.md (issue #115)."""


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


def test_t_char_io_02_a(client, admin):
    """T-CHAR-IO-02-a (LIB-IO-03): missing format_version, unknown key, authors not a list, publishers missing"""
    data = dataset()
    del data["format_version"]
    del data["publishers"]
    data["extra"] = 1
    data["authors"] = "x"
    found = problems(client, admin, data)
    for pair in (("format_version", "field required"), ("extra", "unknown field"),
                 ("authors", "must be a list"), ("publishers", "field required")):
        assert pair in found


def test_t_char_io_04_a(client, admin):
    """T-CHAR-IO-04-a (LIB-IO-04): future publication_year; future acquired_on; available copy without current branch"""
    data = dataset()
    data["books"][0]["publication_year"] = 2027
    data["copies"][1]["acquired_on"] = "2026-12-01"
    data["copies"][1]["current_branch_id"] = None
    found = problems(client, admin, data)
    assert ("books[0].publication_year", "publication_year must not be after 2026") in found
    assert ("copies[1].acquired_on", "acquired_on must not be after today") in found
    assert ("copies[1].current_branch_id", "a copy with status available needs a current branch") in found


def test_t_char_io_06_a(client, admin):
    """T-CHAR-IO-06-a (LIB-IO-06): open loan with due_date before loan_date, returned_on and return_branch_id"""
    data = dataset()
    data["loans"][0].update(due_date="2026-10-20", returned_on="2026-10-30", return_branch_id=1)
    found = problems(client, admin, data)
    assert ("loans[0].due_date", "due_date must not be before loan_date") in found
    assert ("loans[0].returned_on", "returned_on must be null for a open loan") in found
    assert ("loans[0].return_branch_id", "return_branch_id must be null for a open loan") in found


def test_t_char_io_08_a(client, admin):
    """T-CHAR-IO-08-a (LIB-IO-06): second open loan on a copy; loan on copy 99; non-object loan element"""
    data = dataset()
    data["loans"].append(loan(id=2))
    data["loans"].append(loan(id=3, copy_id=99))
    data["loans"].append("x")
    found = problems(client, admin, data)
    assert ("loans[1].copy_id", "the copy already has an open or lost loan") in found
    assert ("loans[2].copy_id", "copies id 99 does not exist") in found
    assert ("loans[3]", "must be an object") in found


def test_t_char_io_10_a(client, admin):
    """T-CHAR-IO-10-a (LIB-IO-03): 150 unknown keys -> exactly 100 problems"""
    data = dataset()
    for i in range(150):
        data[f"x{i}"] = 1
    assert len(problems(client, admin, data)) == 100
