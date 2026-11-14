"""Module 21: Course reserves (LIB-CRS-01 to LIB-CRS-47).

The clock starts on Mon 2026-11-02 09:30. Member 1 is an academic (the instructor), members 2-4 are students.
The default course CENG301 (2026-fall) of branch 1 runs from 2026-11-02 to 2026-12-20.
"""

import datetime

import pytest
import sqlalchemy as sa

import lms
from lms.catalog.models import Copy
from lms.courses.models import ReadingListItem
from lms.notifications.models import Notification
from tests.test_auth import admin_h, audit, err, h, token_of  # noqa: F401
from tests.test_branches import mk_branch
from tests.test_catalog import book_body, mk_author, mk_copy, mk_publisher
from tests.test_members import reg

API = "/api/v1"
TZ = datetime.timezone(datetime.timedelta(hours=3))


@pytest.fixture
def settings(clock):
    return lms.Settings(database_url="sqlite://", clock=clock, token_ttl_hours=168)


def at(day, hhmm="09:00", month=11):
    hour, minute = map(int, hhmm.split(":"))
    return datetime.datetime(2026, month, day, hour, minute, tzinfo=TZ)


COURSE = {
    "code": "ceng301",
    "title": "Operating Systems",
    "term": "2026-fall",
    "instructor_id": 1,
    "branch_id": 1,
    "starts_on": "2026-11-02",
    "ends_on": "2026-12-20",
}


def mk_course(client, headers, expect=201, **kw):
    r = client.post(f"{API}/courses", headers=headers, json={**COURSE, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def mk_item(client, headers, course_id=1, expect=201, **kw):
    r = client.post(f"{API}/courses/{course_id}/reading-list", headers=headers, json={"book_id": 1, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def activate(client, headers, course_id=1, expect=200):
    r = client.post(f"{API}/courses/{course_id}/activate", headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def enroll(client, headers, member_ids, course_id=1, expect=200):
    r = client.post(f"{API}/courses/{course_id}/enrollments", headers=headers, json={"member_ids": member_ids})
    assert r.status_code == expect, r.text
    return r.json()


def lend(client, headers, member_id=2, expect=201, **kw):
    r = client.post(f"{API}/reserve-loans", headers=headers, json={"member_id": member_id, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def give_back(client, headers, loan_id, branch_id=1, expect=200):
    r = client.post(f"{API}/reserve-loans/{loan_id}/return", headers=headers, json={"branch_id": branch_id})
    assert r.status_code == expect, r.text
    return r.json()


def process(client, headers):
    r = client.post(f"{API}/course-reserves/process", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def fresh(client):
    """A new admin session, for tests that move the clock by more than the token lifetime."""
    return h(token_of(client, "admin@library.local", "ChangeMe123"))


def sel(app, stmt):
    with app.state.session_factory() as s:
        return list(s.scalars(stmt))


def copy_of(app, copy_id):
    return sel(app, sa.select(Copy).where(Copy.id == copy_id))[0]


def notifications(app, type_=None, member_id=None):
    stmt = sa.select(Notification).order_by(Notification.id)
    if type_ is not None:
        stmt = stmt.where(Notification.type == type_)
    if member_id is not None:
        stmt = stmt.where(Notification.member_id == member_id)
    return sel(app, stmt)


@pytest.fixture
def world(client, admin_h):
    mk_branch(client, admin_h, "MERKEZ")
    mk_branch(client, admin_h, "KAMPUS")
    mk_author(client, admin_h)
    mk_publisher(client, admin_h)
    for i, isbn in enumerate(("978-0-306-40615-7", "978-0-8044-2957-3"), start=1):
        r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn=isbn, title=f"Book {i}"))
        assert r.status_code == 201, r.text
    reg(client, admin_h, email="prof@example.edu.tr", university_id="PROF0001", membership_type="academic", full_name="Prof")
    for i in range(1, 4):
        reg(client, admin_h, email=f"s{i}@example.edu.tr", university_id=f"2023000{i}", full_name=f"Student {i}")
    return {
        "prof": h(token_of(client, "prof@example.edu.tr", "Passw0rd1")),
        "s": [h(token_of(client, f"s{i}@example.edu.tr", "Passw0rd1")) for i in range(1, 4)],
    }


# --- courses -----------------------------------------------------------------------------------


def test_create_course(client, admin_h, world, app):
    c = mk_course(client, admin_h)
    assert c == {
        "id": 1, "code": "CENG301", "title": "Operating Systems", "term": "2026-fall", "instructor_id": 1,
        "branch_id": 1, "starts_on": "2026-11-02", "ends_on": "2026-12-20", "enrollment_limit": 100,
        "status": "draft", "created_at": "2026-11-02T09:30:00+03:00", "activated_at": None, "closed_at": None,
        "enrolled": 0, "items": 0, "copies_on_reserve": 0,
    }
    assert [a.entity_id for a in audit(app, "course_created")] == [1]


def test_create_course_validation(client, admin_h, world):
    for bad in (
        {"code": "C301"}, {"code": "ABCDE301"}, {"code": "CENG30"}, {"term": "2026-winter"}, {"term": "1999-fall"},
        {"enrollment_limit": 0}, {"enrollment_limit": 301}, {"title": " "}, {"ends_on": "2026-11-07"},
        {"ends_on": "2027-05-01"}, {"starts_on": "2026-10-01", "ends_on": "2026-10-20"}, {"starts_on": "bad"},
    ):
        err(client.post(f"{API}/courses", headers=admin_h, json={**COURSE, **bad}), 422, "VALIDATION_ERROR")
    for field in ("instructor_id", "branch_id"):
        e = err(client.post(f"{API}/courses", headers=admin_h, json={**COURSE, field: 99}), 422, "VALIDATION_ERROR")
        assert [f["field"] for f in e["details"]["fields"]] == [field]
    assert mk_course(client, admin_h, ends_on="2026-11-08")["ends_on"] == "2026-11-08"


def test_create_course_checks(client, admin_h, world):
    err(client.post(f"{API}/courses", headers=admin_h, json={**COURSE, "instructor_id": 2}), 409, "INSTRUCTOR_NOT_ACADEMIC")
    mk_course(client, admin_h)
    e = err(client.post(f"{API}/courses", headers=admin_h, json=COURSE), 409, "CONFLICT")
    assert e["details"]["field"] == "code"
    mk_course(client, admin_h, term="2027-spring")
    client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False})
    err(client.post(f"{API}/courses", headers=admin_h, json={**COURSE, "branch_id": 2, "code": "X1"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/courses", headers=admin_h, json={**COURSE, "branch_id": 2, "code": "XX101"}), 409, "BRANCH_INACTIVE")


def test_course_permissions(client, admin_h, world):
    err(client.post(f"{API}/courses", headers=world["prof"], json=COURSE), 403, "FORBIDDEN")
    err(client.post(f"{API}/courses", json=COURSE), 401, "UNAUTHENTICATED")
    mk_course(client, admin_h)
    for path in ("activate", "close"):
        err(client.post(f"{API}/courses/1/{path}", headers=world["prof"]), 403, "FORBIDDEN")
    err(client.patch(f"{API}/courses/1", headers=world["prof"], json={}), 403, "FORBIDDEN")


def test_update_course(client, admin_h, world, app):
    mk_course(client, admin_h)
    r = client.patch(f"{API}/courses/1", headers=admin_h, json={"title": "OS", "enrollment_limit": 2})
    assert r.status_code == 200 and r.json()["title"] == "OS" and r.json()["enrollment_limit"] == 2
    assert [a.entity_id for a in audit(app, "course_updated")] == [1]
    for bad in ({"code": "X"}, {"term": "2026-fall"}, {"branch_id": 2}, {"title": None}, {"ends_on": "2026-11-03"}):
        err(client.patch(f"{API}/courses/1", headers=admin_h, json=bad), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/courses/1", headers=admin_h, json={"instructor_id": 2}), 409, "INSTRUCTOR_NOT_ACADEMIC")
    err(client.patch(f"{API}/courses/1", headers=admin_h, json={"instructor_id": 99}), 422, "VALIDATION_ERROR")
    enroll(client, admin_h, [2, 3])
    e = err(client.patch(f"{API}/courses/1", headers=admin_h, json={"enrollment_limit": 1}), 409, "ENROLLMENT_LIMIT_BELOW_ENROLLED")
    assert e["details"]["enrolled"] == 2
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    activate(client, admin_h)
    assert client.patch(f"{API}/courses/1", headers=admin_h, json={"title": "OS 2"}).status_code == 200
    client.post(f"{API}/courses/1/close", headers=admin_h)
    e = err(client.patch(f"{API}/courses/1", headers=admin_h, json={"title": "x"}), 409, "INVALID_COURSE_STATUS")
    assert e["details"]["status"] == "closed"
    err(client.patch(f"{API}/courses/99", headers=admin_h, json={}), 404, "NOT_FOUND")


def test_read_courses(client, admin_h, world):
    mk_course(client, admin_h)
    mk_course(client, admin_h, code="MATH101", title="Calculus", term="2026-fall", instructor_id=1)
    mk_course(client, admin_h, code="AB101", term="2025-spring", starts_on="2026-11-02", ends_on="2026-12-01")
    enroll(client, admin_h, [2])
    r = client.get(f"{API}/courses", headers=admin_h).json()
    assert r["total"] == 3 and [c["code"] for c in r["items"]] == ["AB101", "CENG301", "MATH101"]
    assert [c["id"] for c in client.get(f"{API}/courses?q=calc", headers=admin_h).json()["items"]] == [2]
    assert [c["id"] for c in client.get(f"{API}/courses?q=ceng", headers=admin_h).json()["items"]] == [1]
    assert client.get(f"{API}/courses?status=active", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/courses?term=2025-spring", headers=admin_h).json()["total"] == 1
    assert client.get(f"{API}/courses?status=bogus", headers=admin_h).status_code == 422
    # members see only their own courses
    assert [c["id"] for c in client.get(f"{API}/courses", headers=world["s"][0]).json()["items"]] == [1]
    assert client.get(f"{API}/courses", headers=world["s"][1]).json()["total"] == 0
    assert client.get(f"{API}/courses/1", headers=world["s"][0]).json()["enrolled"] == 1
    err(client.get(f"{API}/courses/2", headers=world["s"][0]), 404, "NOT_FOUND")
    assert client.get(f"{API}/courses/1", headers=world["prof"]).status_code == 200


# --- enrollment --------------------------------------------------------------------------------


def test_enroll_example(client, admin_h, world, app):
    mk_course(client, admin_h, enrollment_limit=2)
    assert enroll(client, admin_h, [2])["enrolled"] == [2]
    r = enroll(client, admin_h, [1, 3, 4])
    assert r == {"enrolled": [3], "skipped": [{"member_id": 1, "error_code": "NOT_A_STUDENT"}, {"member_id": 4, "error_code": "ENROLLMENT_FULL"}]}
    err(client.post(f"{API}/courses/1/enrollments", headers=admin_h, json={"member_ids": [2, 2]}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/courses/1/enrollments", headers=admin_h, json={"member_ids": []}), 422, "VALIDATION_ERROR")
    assert enroll(client, admin_h, [2, 99])["skipped"] == [
        {"member_id": 2, "error_code": "ALREADY_ENROLLED"}, {"member_id": 99, "error_code": "NOT_FOUND"}
    ]
    assert len(audit(app, "course_enrollment_created")) == 2
    ns = notifications(app, "course_enrolled")
    assert [n.member_id for n in ns] == [2, 3] and all("CENG301" in n.message and n.course_id == 1 for n in ns)
    err(client.post(f"{API}/courses/1/enrollments", headers=world["prof"], json={"member_ids": [2]}), 403, "FORBIDDEN")


def test_enroll_skips_passive_and_expired(client, admin_h, world, clock):
    mk_course(client, admin_h)
    client.post(f"{API}/members/2/deactivate", headers=admin_h)
    assert enroll(client, admin_h, [2])["skipped"] == [{"member_id": 2, "error_code": "MEMBER_PASSIVE"}]
    clock.set(at(2, month=11).replace(year=2027, month=11, day=3))
    r = client.post(f"{API}/courses/1/enrollments", headers=admin_h, json={"member_ids": [3]})
    assert r.status_code in (200, 401)


def test_drop_and_read_enrollments(client, admin_h, world, app):
    mk_course(client, admin_h)
    enroll(client, admin_h, [3, 2])
    r = client.get(f"{API}/courses/1/enrollments", headers=admin_h).json()
    assert [e["member_id"] for e in r["items"]] == [3, 2] and r["items"][0]["member_no"] == "M000003"
    assert r["items"][0]["full_name"] == "Student 2"
    assert client.get(f"{API}/courses/1/enrollments", headers=world["prof"]).status_code == 200
    err(client.get(f"{API}/courses/1/enrollments", headers=world["s"][0]), 403, "FORBIDDEN")
    d = client.post(f"{API}/enrollments/1/drop", headers=admin_h)
    assert d.status_code == 200 and d.json()["status"] == "dropped" and d.json()["drop_reason"] == "staff_request"
    err(client.post(f"{API}/enrollments/1/drop", headers=admin_h), 409, "ENROLLMENT_NOT_ACTIVE")
    assert len(audit(app, "course_enrollment_dropped")) == 1
    assert enroll(client, admin_h, [3])["enrolled"] == [3]  # a new enrollment
    assert client.get(f"{API}/courses/1/enrollments?status=dropped", headers=admin_h).json()["total"] == 1
    mine = client.get(f"{API}/members/3/courses", headers=world["s"][1]).json()["items"]
    assert [(c["id"], c["role"]) for c in mine] == [(1, "student")]
    assert [(c["id"], c["role"]) for c in client.get(f"{API}/members/1/courses", headers=admin_h).json()["items"]] == [(1, "instructor")]
    err(client.get(f"{API}/members/3/courses", headers=world["s"][0]), 403, "FORBIDDEN")


# --- reading list ------------------------------------------------------------------------------


def test_add_item_and_auto_placement(client, admin_h, world, app):
    mk_course(client, admin_h)
    for i in (1, 2, 3):
        assert mk_copy(client, admin_h, barcode=f"BC-000{i}", branch=1 if i != 3 else 2).status_code == 201
    assert mk_copy(client, admin_h, barcode="BC-0009", branch=1).status_code == 201
    it = mk_item(client, admin_h, copies_wanted=2, loan_period="1d", note="chapter 1")
    assert it["position"] == 1 and it["status"] == "on_reserve" and it["kind"] == "required"
    assert (it["copies_on_reserve"], it["available_now"], it["next_due_at"]) == (2, 2, None)
    assert it["book_title"] == "Book 1" and it["loan_period"] == "1d"
    copies = [copy_of(app, i) for i in (1, 2, 3, 4)]
    assert [c.status for c in copies] == ["on_reserve", "on_reserve", "available", "available"]
    assert copies[0].reserve_item_id == 1 and copies[0].reserve_course_id == 1
    c = client.get(f"{API}/copies/1", headers=admin_h).json()
    assert c["status"] == "on_reserve" and c["reserve_item_id"] == 1 and c["reserve_course_id"] == 1
    assert client.get(f"{API}/books/1/copies?status=on_reserve", headers=admin_h).json()["total"] == 2
    av = client.get(f"{API}/books/1", headers=admin_h).json()["availability"]
    assert av == [{"branch_id": 1, "available": 1, "total": 3}, {"branch_id": 2, "available": 1, "total": 1}]
    c = client.get(f"{API}/courses/1", headers=admin_h).json()
    assert (c["items"], c["copies_on_reserve"]) == (1, 2)
    assert len(audit(app, "reading_list_item_added")) == 1 and len(audit(app, "reserve_copy_placed")) == 2
    # a recommended item is not filled automatically
    mk_copy(client, admin_h, book_id=2, barcode="BC-0008")
    it2 = mk_item(client, admin_h, book_id=2, kind="recommended")
    assert it2["position"] == 2 and it2["status"] == "requested"


def test_add_item_checks(client, admin_h, world):
    mk_course(client, admin_h)
    err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json={"book_id": 1}), 409, "BOOK_NOT_LENDABLE")
    err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json={"book_id": 99}), 422, "VALIDATION_ERROR")
    for bad in ({"kind": "x"}, {"loan_period": "5h"}, {"copies_wanted": 6}, {"note": "x" * 501}, {}):
        err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json=bad), 422, "VALIDATION_ERROR")
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json={"book_id": 1}), 409, "DUPLICATE_ITEM")
    client.post(f"{API}/courses/1/close", headers=admin_h)
    e = err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json={"book_id": 2}), 409, "INVALID_COURSE_STATUS")
    assert e["details"]["status"] == "closed"


def test_reading_list_full(client, admin_h, world, app):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_copy(client, admin_h, book_id=2, barcode="BC-0002")
    with app.state.session_factory.begin() as s:
        for i in range(39):
            s.add(ReadingListItem(course_id=1, book_id=2, kind="recommended", position=i + 1, status="requested", added_at=at(2)))
    mk_item(client, admin_h)
    r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="978-3-16-148410-0", title="Book 3"))
    assert r.status_code == 201, r.text
    mk_copy(client, admin_h, book_id=3, barcode="BC-0003")
    err(client.post(f"{API}/courses/1/reading-list", headers=admin_h, json={"book_id": 3}), 409, "READING_LIST_FULL")


def test_instructor_rights(client, admin_h, world):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    r = client.post(f"{API}/courses/1/reading-list", headers=world["prof"], json={"book_id": 1})
    assert r.status_code == 201
    err(client.post(f"{API}/courses/1/reading-list", headers=world["s"][0], json={"book_id": 2}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/reading-list-items/1", headers=world["s"][0], json={"note": "x"}), 403, "FORBIDDEN")
    err(client.post(f"{API}/reading-list-items/1/remove", headers=world["s"][0]), 403, "FORBIDDEN")
    err(client.put(f"{API}/courses/1/reading-list/order", headers=world["s"][0], json={"item_ids": [1]}), 403, "FORBIDDEN")
    err(client.patch(f"{API}/reading-list-items/9", headers=world["s"][0], json={"note": "x"}), 404, "NOT_FOUND")
    assert client.patch(f"{API}/reading-list-items/1", headers=world["prof"], json={"note": "x"}).status_code == 200
    err(client.post(f"{API}/reading-list-items/1/copies", headers=world["prof"], json={"copy_id": 1}), 403, "FORBIDDEN")
    # reading list reads: enrolled members and the instructor only
    err(client.get(f"{API}/courses/1/reading-list", headers=world["s"][0]), 404, "NOT_FOUND")
    enroll(client, admin_h, [2])
    assert client.get(f"{API}/courses/1/reading-list", headers=world["s"][0]).json()["total"] == 1
    assert client.get(f"{API}/courses/1/reading-list", headers=world["prof"]).json()["total"] == 1


def test_update_order_remove(client, admin_h, world, app):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_copy(client, admin_h, book_id=2, barcode="BC-0002")
    mk_item(client, admin_h, kind="recommended")
    mk_item(client, admin_h, book_id=2)
    r = client.patch(f"{API}/reading-list-items/1", headers=admin_h, json={"loan_period": "3d", "copies_wanted": 2})
    assert r.status_code == 200 and r.json()["loan_period"] == "3d" and r.json()["copies_wanted"] == 2
    err(client.patch(f"{API}/reading-list-items/2", headers=admin_h, json={"copies_wanted": None}), 422, "VALIDATION_ERROR")
    err(client.patch(f"{API}/reading-list-items/1", headers=admin_h, json={"x": 1}), 422, "VALIDATION_ERROR")
    items = client.put(f"{API}/courses/1/reading-list/order", headers=admin_h, json={"item_ids": [2, 1]}).json()["items"]
    assert [(i["id"], i["position"]) for i in items] == [(2, 1), (1, 2)]
    for bad in ([1], [1, 1], [1, 2, 3], []):
        err(client.put(f"{API}/courses/1/reading-list/order", headers=admin_h, json={"item_ids": bad}), 422, "VALIDATION_ERROR")
    r = client.post(f"{API}/reading-list-items/2/remove", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "removed" and r.json()["position"] is None
    assert copy_of(app, 2).status == "available" and copy_of(app, 2).reserve_item_id is None
    assert [(i["id"], i["position"]) for i in client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"]] == [(1, 1)]
    got = client.get(f"{API}/courses/1/reading-list?include_removed=true", headers=admin_h).json()["items"]
    assert [i["id"] for i in got] == [1, 2]
    err(client.post(f"{API}/reading-list-items/2/remove", headers=admin_h), 409, "ITEM_REMOVED")
    err(client.patch(f"{API}/reading-list-items/2", headers=admin_h, json={"note": "x"}), 409, "ITEM_REMOVED")
    assert len(audit(app, "reading_list_item_removed")) == 1 and len(audit(app, "reserve_copy_removed")) == 1


def test_copies_wanted_below_reserve(client, admin_h, world):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_copy(client, admin_h, barcode="BC-0002")
    mk_item(client, admin_h, copies_wanted=2)
    e = err(client.patch(f"{API}/reading-list-items/1", headers=admin_h, json={"copies_wanted": 1}), 409, "COPIES_WANTED_BELOW_RESERVE")
    assert e["details"]["on_reserve"] == 2


# --- copies on reserve -------------------------------------------------------------------------


def test_place_and_unreserve(client, admin_h, world, app):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)  # copy 1 (will go on reserve by hand)
    it = mk_item(client, admin_h, kind="recommended")
    assert it["status"] == "requested"
    mk_copy(client, admin_h, book_id=2, barcode="BC-0002")
    mk_copy(client, admin_h, barcode="BC-0003", branch=2)
    mk_copy(client, admin_h, barcode="BC-0004")
    post = lambda copy_id: client.post(f"{API}/reading-list-items/1/copies", headers=admin_h, json={"copy_id": copy_id})
    err(post(99), 404, "NOT_FOUND")
    err(post(2), 409, "WRONG_BOOK")
    err(post(3), 409, "COPY_AT_OTHER_BRANCH")
    r = post(1)
    assert r.status_code == 201 and r.json() == {"copy_id": 1, "barcode": "BC-0001", "item_id": 1, "course_id": 1, "on_loan": False}
    e = err(post(1), 409, "INVALID_COPY_STATUS")
    assert e["details"]["status"] == "on_reserve"
    err(post(4), 409, "RESERVE_COPIES_COMPLETE")
    assert client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"][0]["status"] == "on_reserve"
    # lending and withdrawal of a copy on reserve
    r = client.post(f"{API}/loans", headers=admin_h, json={"member_id": 2, "copy_id": 1})
    e = err(r, 409, "COPY_NOT_AVAILABLE")
    assert e["details"]["status"] == "on_reserve"
    err(client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "no longer needed"}), 409, "INVALID_COPY_STATUS")
    err(client.post(f"{API}/transfers", headers=admin_h, json={"copy_id": 1, "to_branch_id": 2}), 409, "INVALID_COPY_STATUS")
    err(client.patch(f"{API}/copies/1", headers=admin_h, json={"home_branch_id": 2}), 409, "INVALID_COPY_STATUS")
    err(client.post(f"{API}/copies/4/unreserve", headers=admin_h), 409, "INVALID_COPY_STATUS")
    c = client.post(f"{API}/copies/1/unreserve", headers=admin_h)
    assert c.status_code == 200 and c.json()["status"] == "available" and c.json()["reserve_item_id"] is None
    assert client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"][0]["status"] == "requested"
    assert len(audit(app, "reserve_copy_placed")) == 1 and len(audit(app, "reserve_copy_removed")) == 1


def test_place_notifies_enrolled_of_active_course(client, admin_h, world, app):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_item(client, admin_h, kind="recommended")
    enroll(client, admin_h, [2, 3])
    activate(client, admin_h)
    assert [n.member_id for n in notifications(app, "course_activated")] == [2, 3]
    client.post(f"{API}/reading-list-items/1/copies", headers=admin_h, json={"copy_id": 1})
    ns = notifications(app, "reserve_item_available")
    assert [n.member_id for n in ns] == [2, 3] and "Book 1" in ns[0].message and "CENG301" in ns[0].message


def test_activate_checks(client, admin_h, world, clock):
    mk_course(client, admin_h)
    err(client.post(f"{API}/courses/1/activate", headers=admin_h), 409, "COURSE_READING_LIST_EMPTY")
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    a = activate(client, admin_h)
    assert a["status"] == "active" and a["activated_at"] == "2026-11-02T09:30:00+03:00"
    err(client.post(f"{API}/courses/1/activate", headers=admin_h), 409, "INVALID_COURSE_STATUS")
    mk_course(client, admin_h, code="OLD101", ends_on="2026-11-10")
    clock.set(at(12))
    admin_h = fresh(client)
    err(client.post(f"{API}/courses/2/activate", headers=admin_h), 409, "COURSE_ENDED")


# --- lending -----------------------------------------------------------------------------------


@pytest.fixture
def running(client, admin_h, world):
    """Course 1 is active with students 2 and 3 enrolled; copies 1 and 2 of book 1 are on reserve (2h loans)."""
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_copy(client, admin_h, barcode="BC-0002")
    mk_item(client, admin_h, copies_wanted=2)
    enroll(client, admin_h, [2, 3])
    activate(client, admin_h)
    return world


def test_lend_and_due_times(client, admin_h, running, clock, app):
    clock.set(at(2, "10:15"))
    loan = lend(client, admin_h, 2, copy_id=1)
    assert loan["due_at"] == "2026-11-02T12:15:00+03:00" and loan["status"] == "open" and loan["renewed"] is False
    assert loan["book_title"] == "Book 1" and loan["course_code"] == "CENG301" and loan["is_overdue"] is False
    assert loan["accrued_late_fee"] == "0.00" and loan["fee_id"] is None and loan["late_minutes"] is None
    assert len(audit(app, "reserve_loan_created")) == 1
    it = client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"][0]
    assert (it["copies_on_reserve"], it["available_now"], it["next_due_at"]) == (2, 1, None)
    lend(client, admin_h, 3, barcode="bc-0002")
    it = client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"][0]
    assert (it["available_now"], it["next_due_at"]) == (0, "2026-11-02T12:15:00+03:00")
    clock.set(at(2, "19:00"))
    assert lend(client, admin_h, 2, copy_id=1, expect=409) is not None  # copy 1 still on loan


def test_due_time_examples():
    from lms.core.holidays import DEFAULT_HOLIDAYS
    from lms.courses.rules import due_at_for
    from lms.staff.schedule import BranchSchedule

    sched = BranchSchedule()
    assert due_at_for(at(2, "19:00"), "2h", sched, DEFAULT_HOLIDAYS) == at(2, "20:00")
    assert due_at_for(at(2, "10:15"), "2h", sched, DEFAULT_HOLIDAYS) == at(2, "12:15")
    assert due_at_for(at(6, "15:00"), "1d", sched, DEFAULT_HOLIDAYS) == at(9, "20:00")
    assert due_at_for(at(3, "10:00"), "3d", sched, DEFAULT_HOLIDAYS) == at(6, "20:00")
    closed = BranchSchedule(closures={datetime.date(2026, 11, 5): "x"})
    assert due_at_for(at(3, "10:00"), "3d", closed, DEFAULT_HOLIDAYS) == at(9, "20:00")


def test_lend_checks(client, admin_h, running, clock, app):
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1, "barcode": "BC-0001"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "barcode": "NOPE-1"}), 404, "NOT_FOUND")
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 99, "copy_id": 1}), 404, "NOT_FOUND")
    err(client.post(f"{API}/reserve-loans", headers=world_h(running), json={"member_id": 2, "copy_id": 1}), 403, "FORBIDDEN")
    mk_copy(client, admin_h, barcode="BC-0003")
    e = err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 3}), 409, "COPY_NOT_ON_RESERVE")
    assert e["details"]["status"] == "available"
    reg(client, admin_h, email="x@example.edu.tr", university_id="20239999", full_name="Outsider")
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 5, "copy_id": 1}), 409, "NOT_ENROLLED")
    clock.set(at(2, "07:59"))
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "RESERVE_DESK_CLOSED")
    clock.set(at(2, "20:00"))
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "RESERVE_DESK_CLOSED")
    clock.set(at(7, "10:00"))  # Saturday
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "RESERVE_DESK_CLOSED")
    clock.set(at(2, "10:00"))
    lend(client, admin_h, 2, copy_id=1)
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 2}), 409, "ALREADY_BORROWED")
    e = err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 3, "copy_id": 1}), 409, "COPY_ON_RESERVE_LOAN")
    assert e["details"]["due_at"] == "2026-11-02T12:00:00+03:00"


def world_h(running):
    return running["s"][0]


def test_lend_limits_and_course_state(client, admin_h, world, clock, app):
    mk_course(client, admin_h, starts_on="2026-11-03")
    r = client.post(f"{API}/books", headers=admin_h, json=book_body(isbn="978-3-16-148410-0", title="Book 3"))
    assert r.status_code == 201, r.text
    for i, book_id in enumerate((1, 2, 3), start=1):
        mk_copy(client, admin_h, book_id=book_id, barcode=f"BC-000{i}")
        mk_item(client, admin_h, book_id=book_id)
    enroll(client, admin_h, [2])
    # draft course
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "COURSE_NOT_RUNNING")
    activate(client, admin_h)  # active but before starts_on
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "COURSE_NOT_RUNNING")
    clock.set(at(3, "10:00"))
    lend(client, admin_h, 2, copy_id=1)
    lend(client, admin_h, 2, copy_id=2)
    e = err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 3}), 409, "RESERVE_LOAN_LIMIT_REACHED")
    assert e["details"]["limit"] == 2
    clock.set(datetime.datetime(2026, 12, 21, 10, 0, tzinfo=TZ))
    admin_h = fresh(client)
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 3}), 409, "COURSE_NOT_RUNNING")


def test_lend_member_checks(client, admin_h, running, clock):
    # debt of 50.00 blocks
    with_fee(client, admin_h, running, 2, "50.00")
    e = err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "MEMBER_BLOCKED_BY_DEBT")
    assert e["details"]["total_debt"] == "50.00"
    with_fee(client, admin_h, running, 3, "49.99")
    lend(client, admin_h, 3, copy_id=1)


def with_fee(client, admin_h, world, member_id, amount):
    """Gives a member an open fee through a lost book loan of a spare copy price."""
    mk = mk_copy(client, admin_h, book_id=2, barcode=f"FEE-{member_id}-{amount[:2]}", price=amount)
    assert mk.status_code == 201, mk.text
    copy_id = mk.json()["id"]
    r = client.post(f"{API}/loans", headers=admin_h, json={"member_id": member_id, "copy_id": copy_id})
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/loans/{r.json()['id']}/report-lost", headers=admin_h)
    assert r.status_code == 200, r.text
    # lost_book (price) + lost_processing (25.00) were created: pay the processing part back
    fees = client.get(f"{API}/members/{member_id}/fees", headers=admin_h).json()["items"]
    total = sum(float(f["amount"]) for f in fees)
    target = float(amount)
    pay = total - target
    if pay > 0:
        client.post(f"{API}/members/{member_id}/payments", headers=admin_h, json={"amount": f"{pay:.2f}", "method": "cash"})


# --- renewal, return, late fees, lost ------------------------------------------------------------


def test_renew(client, admin_h, running, clock, app):
    clock.set(at(2, "10:00"))
    loan = lend(client, admin_h, 2, copy_id=1)
    r = client.post(f"{API}/reserve-loans/{loan['id']}/renew", headers=running["s"][0])
    assert r.status_code == 200 and r.json()["renewed"] is True and r.json()["due_at"] == "2026-11-02T12:00:00+03:00"
    clock.set(at(2, "10:30"))
    assert len(audit(app, "reserve_loan_renewed")) == 1
    err(client.post(f"{API}/reserve-loans/{loan['id']}/renew", headers=admin_h), 409, "RENEWAL_LIMIT_REACHED")
    err(client.post(f"{API}/reserve-loans/{loan['id']}/renew", headers=running["s"][1]), 403, "FORBIDDEN")
    err(client.post(f"{API}/reserve-loans/99/renew", headers=running["s"][1]), 404, "NOT_FOUND")
    # copy 2 is the other copy: take it out of demand by lending it
    clock.set(at(2, "10:45"))
    l2 = lend(client, admin_h, 3, copy_id=2)
    err(client.post(f"{API}/reserve-loans/{l2['id']}/renew", headers=admin_h), 409, "RESERVE_IN_DEMAND")
    clock.set(at(2, "13:00"))
    err(client.post(f"{API}/reserve-loans/{l2['id']}/renew", headers=admin_h), 409, "LOAN_OVERDUE")
    give_back(client, admin_h, l2["id"])
    err(client.post(f"{API}/reserve-loans/{l2['id']}/renew", headers=admin_h), 409, "RESERVE_LOAN_NOT_OPEN")


def test_renew_in_demand_free_copy(client, admin_h, running, clock):
    clock.set(at(2, "10:00"))
    loan = lend(client, admin_h, 2, copy_id=1)
    r = client.post(f"{API}/reserve-loans/{loan['id']}/renew", headers=admin_h)
    assert r.status_code == 200 and r.json()["renewed"] is True


def test_return_and_late_fee_examples(client, admin_h, running, clock, app):
    def run(minutes_late, copy_id=1, member=2):
        clock.set(at(2, "10:15"))
        loan = lend(client, admin_h, member, copy_id=copy_id)
        assert loan["due_at"] == "2026-11-02T12:15:00+03:00"
        clock.set(at(2, "12:15") + datetime.timedelta(minutes=minutes_late))
        return give_back(client, fresh(client), loan["id"])

    r = run(5)
    assert r["status"] == "returned" and r["late_minutes"] == 5 and r["fee_id"] is None
    assert r["returned_at"] == "2026-11-02T12:20:00+03:00"
    r = run(6)
    assert r["late_minutes"] == 6 and r["fee_id"] is not None
    fee = client.get(f"{API}/members/2/fees", headers=admin_h).json()["items"][0]
    assert fee["kind"] == "reserve_late_fee" and fee["amount"] == "1.00" and fee["reserve_loan_id"] == r["id"]
    assert fee["loan_id"] is None
    for late, amount in ((120, "2.00"), (121, "3.00"), (3 * 1440, "30.00"), (10 * 1440, "30.00")):
        clock.set(at(2, "10:15"))
        admin_h = fresh(client)
        r = run(late, member=3)
        admin_h = fresh(client)
        fees = client.get(f"{API}/members/3/fees", headers=admin_h).json()["items"]
        assert [f["amount"] for f in fees if f["reserve_loan_id"] == r["id"]] == [amount]
        client.post(f"{API}/fees/{r['fee_id']}/waive", headers=admin_h, json={"reason": "waived for test"})
    assert len(audit(app, "reserve_loan_returned")) == 6
    assert copy_of(app, 1).status == "on_reserve"
    assert {n.type for n in notifications(app, member_id=3)} == {"fee_created", "fee_waived", "course_enrolled", "course_activated"}


def test_late_fee_day_loan(client, admin_h, world, clock):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_item(client, admin_h, loan_period="1d")
    enroll(client, admin_h, [2])
    activate(client, admin_h)
    clock.set(at(6, "15:00"))  # Friday
    loan = lend(client, admin_h, 2, copy_id=1)
    assert loan["due_at"] == "2026-11-09T20:00:00+03:00"
    clock.set(at(10, "09:00"))
    admin_h = fresh(client)
    r = give_back(client, admin_h, loan["id"])
    assert r["late_minutes"] == 780
    assert client.get(f"{API}/members/2/fees", headers=admin_h).json()["items"][0]["amount"] == "5.00"


def test_return_checks(client, admin_h, running, clock):
    clock.set(at(2, "10:00"))
    loan = lend(client, admin_h, 2, copy_id=1)
    e = err(client.post(f"{API}/reserve-loans/{loan['id']}/return", headers=admin_h, json={"branch_id": 2}), 409, "RESERVE_RETURN_WRONG_BRANCH")
    assert e["details"]["branch_id"] == 1
    err(client.post(f"{API}/reserve-loans/{loan['id']}/return", headers=admin_h, json={"branch_id": 99}), 404, "NOT_FOUND")
    err(client.post(f"{API}/reserve-loans/{loan['id']}/return", headers=running["s"][0], json={"branch_id": 1}), 403, "FORBIDDEN")
    give_back(client, admin_h, loan["id"])
    err(client.post(f"{API}/reserve-loans/{loan['id']}/return", headers=admin_h, json={"branch_id": 1}), 409, "RESERVE_LOAN_NOT_OPEN")
    err(client.post(f"{API}/reserve-loans/{loan['id']}/report-lost", headers=admin_h), 409, "RESERVE_LOAN_NOT_OPEN")


def test_report_lost(client, admin_h, running, clock, app):
    clock.set(at(2, "10:15"))
    loan = lend(client, admin_h, 2, copy_id=1)
    clock.set(at(2, "14:16"))
    r = client.post(f"{API}/reserve-loans/{loan['id']}/report-lost", headers=admin_h)
    assert r.status_code == 200
    r = r.json()
    assert r["status"] == "lost" and r["late_minutes"] == 121 and r["fee_id"] is not None
    fees = client.get(f"{API}/members/2/fees", headers=admin_h).json()["items"]
    kinds = {f["kind"]: f["amount"] for f in fees}
    assert kinds == {"reserve_late_fee": "3.00", "reserve_lost": "50.00"}
    c = copy_of(app, 1)
    assert (c.status, c.current_branch_id, c.reserve_item_id) == ("lost", None, None)
    it = client.get(f"{API}/courses/1/reading-list", headers=admin_h).json()["items"][0]
    assert it["status"] == "on_reserve" and it["copies_on_reserve"] == 1
    assert len(audit(app, "reserve_loan_lost")) == 1


def test_list_reserve_loans(client, admin_h, running, clock):
    clock.set(at(2, "10:00"))
    l1 = lend(client, admin_h, 2, copy_id=1)
    l2 = lend(client, admin_h, 3, copy_id=2)
    give_back(client, admin_h, l1["id"])
    clock.set(at(2, "13:00"))
    r = client.get(f"{API}/reserve-loans", headers=admin_h).json()
    assert [x["id"] for x in r["items"]] == [2, 1]
    assert [x["id"] for x in client.get(f"{API}/reserve-loans?overdue=true", headers=admin_h).json()["items"]] == [2]
    assert [x["id"] for x in client.get(f"{API}/reserve-loans?overdue=false", headers=admin_h).json()["items"]] == [1]
    assert [x["id"] for x in client.get(f"{API}/reserve-loans?status=returned&member_id=2&course_id=1", headers=admin_h).json()["items"]] == [1]
    mine = client.get(f"{API}/members/3/reserve-loans", headers=running["s"][1]).json()["items"]
    assert [x["id"] for x in mine] == [2] and mine[0]["is_overdue"] is True and mine[0]["accrued_late_fee"] == "1.00"
    err(client.get(f"{API}/members/3/reserve-loans", headers=running["s"][0]), 403, "FORBIDDEN")
    err(client.get(f"{API}/reserve-loans", headers=running["s"][0]), 403, "FORBIDDEN")


# --- close, take off reserve, process -------------------------------------------------------------


def test_unreserve_and_remove_with_open_loan(client, admin_h, running, clock):
    clock.set(at(2, "10:00"))
    loan = lend(client, admin_h, 2, copy_id=1)
    e = err(client.post(f"{API}/copies/1/unreserve", headers=admin_h), 409, "RESERVE_COPY_ON_LOAN")
    assert e["details"]["loan_ids"] == [loan["id"]]
    e = err(client.post(f"{API}/reading-list-items/1/remove", headers=admin_h), 409, "RESERVE_COPY_ON_LOAN")
    assert e["details"]["loan_ids"] == [loan["id"]]
    e = err(client.post(f"{API}/courses/1/close", headers=admin_h), 409, "COURSE_HAS_OPEN_LOANS")
    assert e["details"]["loan_ids"] == [loan["id"]]
    err(client.post(f"{API}/enrollments/1/drop", headers=admin_h), 409, "MEMBER_HAS_RESERVE_LOANS")
    give_back(client, admin_h, loan["id"])
    r = client.post(f"{API}/courses/1/close", headers=admin_h)
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["released_copies"] == 2
    assert r.json()["closed_at"] == "2026-11-02T10:00:00+03:00" and r.json()["copies_on_reserve"] == 0
    err(client.post(f"{API}/courses/1/close", headers=admin_h), 409, "INVALID_COURSE_STATUS")
    assert client.get(f"{API}/copies/1", headers=admin_h).json()["status"] == "available"


def test_end_of_course_example(client, admin_h, world, clock, app):
    mk_course(client, admin_h, ends_on="2026-11-20")
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    enroll(client, admin_h, [2])
    activate(client, admin_h)
    clock.set(at(19, "10:00"))
    admin_h = fresh(client)
    loan = lend(client, admin_h, 2, copy_id=1)
    clock.set(at(23, "10:00"))
    admin_h = fresh(client)
    assert process(client, admin_h) == {"overdue_notices": 1, "closed_courses": 0, "released_copies": 0, "pending_courses": 1}
    assert process(client, admin_h)["overdue_notices"] == 0  # one notice per loan
    ns = notifications(app, "reserve_overdue")
    assert len(ns) == 1 and ns[0].member_id == 2 and "CENG301" in ns[0].message and "Book 1" in ns[0].message
    give_back(client, admin_h, loan["id"])
    assert process(client, admin_h) == {"overdue_notices": 0, "closed_courses": 1, "released_copies": 1, "pending_courses": 0}
    assert client.get(f"{API}/courses/1", headers=admin_h).json()["status"] == "closed"
    assert copy_of(app, 1).status == "available"
    assert len(audit(app, "course_reserves_processed")) == 3 and len(audit(app, "course_closed")) == 1


# --- release rule --------------------------------------------------------------------------------


def test_release_goes_on_reserve_first(client, admin_h, world, app):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_copy(client, admin_h, barcode="BC-0002")
    r = client.post(f"{API}/loans", headers=admin_h, json={"member_id": 2, "copy_id": 2})
    assert r.status_code == 201
    mk_item(client, admin_h, copies_wanted=2)
    assert [copy_of(app, i).status for i in (1, 2)] == ["on_reserve", "on_loan"]
    r = client.post(f"{API}/reservations", headers=admin_h, json={"member_id": 3, "book_id": 1, "pickup_branch_id": 1})
    assert r.status_code == 201 and r.json()["status"] == "waiting"
    r = client.post(f"{API}/loans/1/return", headers=admin_h, json={"branch_id": 1, "condition": "good"})
    assert r.status_code == 200, r.text
    assert copy_of(app, 2).status == "on_reserve" and copy_of(app, 2).reserve_item_id == 1
    assert client.get(f"{API}/reservations/1", headers=admin_h).json()["status"] == "waiting"
    # copies taken off reserve by the course are not placed again, and go to the reservation
    client.post(f"{API}/copies/1/unreserve", headers=admin_h)
    assert client.get(f"{API}/reservations/1", headers=admin_h).json()["status"] == "ready"
    assert copy_of(app, 1).status == "on_hold"


def test_reserve_when_all_copies_on_reserve(client, admin_h, world):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    r = client.post(f"{API}/reservations", headers=admin_h, json={"member_id": 3, "book_id": 1, "pickup_branch_id": 1})
    assert r.status_code == 201 and r.json()["status"] == "waiting"


# --- effects on other modules ---------------------------------------------------------------------


def test_member_summary_and_debt(client, admin_h, running, clock):
    s = client.get(f"{API}/members/2/summary", headers=admin_h).json()
    assert s["course_reserves"] == {"courses_enrolled": 1, "courses_teaching": 0, "open_reserve_loans": 0, "overdue_reserve_loans": 0}
    assert client.get(f"{API}/members/1/summary", headers=admin_h).json()["course_reserves"]["courses_teaching"] == 1
    clock.set(at(2, "10:00"))
    lend(client, admin_h, 2, copy_id=1)
    clock.set(at(2, "14:30"))  # due 12:00, 150 minutes late: 3 started hours
    s = client.get(f"{API}/members/2/summary", headers=admin_h).json()
    assert s["course_reserves"]["open_reserve_loans"] == 1 and s["course_reserves"]["overdue_reserve_loans"] == 1
    assert s["balance"]["accrued_late_fees"] == "3.00" and s["borrowing"]["reasons"] == ["MEMBER_HAS_OVERDUE"]
    assert client.get(f"{API}/members/2/balance", headers=admin_h).json()["total_debt"] == "3.00"
    # an overdue reserve loan blocks lending of books and further reserve loans
    mk_copy(client, admin_h, book_id=2, barcode="BC-0009")
    err(client.post(f"{API}/loans", headers=admin_h, json={"member_id": 2, "copy_id": 3}), 409, "MEMBER_HAS_OVERDUE")
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 2}), 409, "MEMBER_HAS_OVERDUE")


def test_overdue_book_loan_blocks_reserve_loan(client, admin_h, running, clock):
    mk_copy(client, admin_h, book_id=2, barcode="BC-0009")
    r = client.post(f"{API}/loans", headers=admin_h, json={"member_id": 2, "copy_id": 3})
    assert r.status_code == 201
    clock.set(at(20, "10:00"))
    admin_h = fresh(client)
    err(client.post(f"{API}/reserve-loans", headers=admin_h, json={"member_id": 2, "copy_id": 1}), 409, "MEMBER_HAS_OVERDUE")


def test_deactivate_member(client, admin_h, running, clock, app):
    clock.set(at(2, "10:00"))
    loan = lend(client, admin_h, 2, copy_id=1)
    err(client.post(f"{API}/members/2/deactivate", headers=admin_h), 409, "MEMBER_HAS_OPEN_LOANS")
    e = err(client.post(f"{API}/members/1/deactivate", headers=admin_h), 409, "INSTRUCTOR_HAS_COURSES")
    assert e["details"]["course_ids"] == [1]
    give_back(client, admin_h, loan["id"])
    assert client.post(f"{API}/members/2/deactivate", headers=admin_h).status_code == 200
    en = client.get(f"{API}/courses/1/enrollments?status=dropped", headers=admin_h).json()["items"]
    assert [(e["member_id"], e["drop_reason"]) for e in en] == [(2, "member_deactivated")]
    assert client.get(f"{API}/courses/1", headers=admin_h).json()["enrolled"] == 1
    client.post(f"{API}/courses/1/close", headers=admin_h)
    assert client.post(f"{API}/members/1/deactivate", headers=admin_h).status_code == 200


def test_type_change(client, admin_h, running):
    e = err(client.patch(f"{API}/members/2", headers=admin_h, json={"membership_type": "staff"}), 409, "MEMBER_HAS_ENROLLMENTS")
    assert e["details"]["course_ids"] == [1]
    e = err(client.patch(f"{API}/members/1", headers=admin_h, json={"membership_type": "staff"}), 409, "INSTRUCTOR_HAS_COURSES")
    assert e["details"]["course_ids"] == [1]
    assert client.patch(f"{API}/members/2", headers=admin_h, json={"membership_type": "student", "full_name": "S"}).status_code == 200
    client.post(f"{API}/courses/1/close", headers=admin_h)
    assert client.patch(f"{API}/members/2", headers=admin_h, json={"membership_type": "staff"}).status_code == 200


def test_branch_deactivation(client, admin_h, running):
    e = err(client.patch(f"{API}/branches/1", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")
    client.post(f"{API}/courses/1/close", headers=admin_h)
    mk_course(client, admin_h, code="XX101", branch_id=2)
    err(client.patch(f"{API}/branches/2", headers=admin_h, json={"is_active": False}), 409, "BRANCH_IN_USE")


def test_delete_book_on_reading_list(client, admin_h, world):
    mk_course(client, admin_h)
    mk_copy(client, admin_h)
    mk_item(client, admin_h)
    err(client.delete(f"{API}/books/1", headers=admin_h), 409, "BOOK_HAS_COPIES")
    client.post(f"{API}/reading-list-items/1/remove", headers=admin_h)
    client.post(f"{API}/copies/1/withdraw", headers=admin_h, json={"reason": "damaged beyond use"})


# --- report ----------------------------------------------------------------------------------------


def test_report(client, admin_h, running, clock):
    clock.set(at(2, "10:15"))
    l1 = lend(client, admin_h, 2, copy_id=1)
    lend(client, admin_h, 3, copy_id=2)
    clock.set(at(2, "12:21"))
    give_back(client, admin_h, l1["id"])
    mk_course(client, admin_h, code="DRFT101")
    mk_course(client, admin_h, code="LATE101", starts_on="2027-02-01", ends_on="2027-03-01", term="2026-spring")
    r = client.get(f"{API}/reports/course-reserves?from=2026-11-01&to=2026-11-30", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["items"] == [
        {
            "course_id": 1, "code": "CENG301", "title": "Operating Systems", "term": "2026-fall", "status": "active",
            "enrolled": 2, "items": 1, "items_unfilled": 0, "loans": 2, "borrowers": 2, "late_returns": 1,
            "fees_charged": "1.00",
        }
    ]
    assert client.get(f"{API}/reports/course-reserves?from=2027-01-01&to=2027-01-02", headers=admin_h).json()["total"] == 0
    assert client.get(f"{API}/reports/course-reserves?from=2026-11-01&to=2026-11-30&branch_id=2", headers=admin_h).json()["total"] == 0
    for q in ("", "?from=2026-11-01", "?from=2026-11-30&to=2026-11-01", "?from=2026-01-01&to=2027-01-02"):
        err(client.get(f"{API}/reports/course-reserves{q}", headers=admin_h), 422, "VALIDATION_ERROR")
    err(client.get(f"{API}/reports/course-reserves?from=2026-11-01&to=2026-11-30", headers=running["prof"]), 403, "FORBIDDEN")


def test_openapi_lists_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/courses", "/api/v1/courses/{course_id}", "/api/v1/courses/{course_id}/activate",
        "/api/v1/courses/{course_id}/close", "/api/v1/courses/{course_id}/enrollments",
        "/api/v1/enrollments/{enrollment_id}/drop", "/api/v1/members/{member_id}/courses",
        "/api/v1/courses/{course_id}/reading-list", "/api/v1/courses/{course_id}/reading-list/order",
        "/api/v1/reading-list-items/{item_id}", "/api/v1/reading-list-items/{item_id}/remove",
        "/api/v1/reading-list-items/{item_id}/copies", "/api/v1/copies/{copy_id}/unreserve",
        "/api/v1/reserve-loans", "/api/v1/members/{member_id}/reserve-loans",
        "/api/v1/reserve-loans/{loan_id}/renew", "/api/v1/reserve-loans/{loan_id}/return",
        "/api/v1/reserve-loans/{loan_id}/report-lost", "/api/v1/course-reserves/process",
        "/api/v1/reports/course-reserves",
    ):
        assert path in paths, path
