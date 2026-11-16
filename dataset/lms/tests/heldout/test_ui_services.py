"""Heldout tests: web interface, screens of modules 15–21 (step 25). Generated from cases/ui_services.md."""
from playwright.sync_api import expect

from support.api import add_copy, create_book, items, register_member

ADMIN = ("admin@library.local", "ChangeMe123")  # conftest.py
LIBRARIAN = ("lib@library.local", "Librarian123")
MEMBER_PASSWORD = "Member1234"


def log_in(page, email, password):
    """LIB-UI-GEN-04: log in on the login screen and wait for the header (LIB-UI-GEN-05)."""
    page.goto("/ui/#/login")
    page.locator('[name="email"]').fill(email)
    page.locator('[name="password"]').fill(password)
    page.get_by_role("button", name="Log in", exact=True).click()
    expect(page.get_by_role("button", name="Log out", exact=True)).to_be_visible()


def sign_in(client, page, admin, librarian, branch, role):
    """Log in as a new member, the fixture librarian (with a staff profile, module 19) or the admin."""
    if role == "member":
        m = register_member(client, librarian, home_branch_id=branch["id"])
        log_in(page, m["email"], MEMBER_PASSWORD)
        return m
    if role == "librarian":
        me = client.get("/api/v1/auth/me", headers=librarian).json()
        client.post("/api/v1/staff", headers=admin, json={"user_id": me["id"], "home_branch_id": branch["id"],
                                                           "employment": "full_time", "started_on": "2020-01-01"})
        log_in(page, *LIBRARIAN)
        return me
    log_in(page, *ADMIN)
    return None


def heading(page, title):
    expect(page.locator("h1:visible")).to_have_text(title)


def settled(page):
    """No error is shown and no JavaScript error happened (LIB-UI-GEN-12, LIB-UI-GEN-16)."""
    page.wait_for_timeout(700)
    expect(page.get_by_role("alert")).to_have_count(0)
    assert page.js_errors == [], page.js_errors


def open_screen(page, route, title):
    page.goto(f"/ui/#/{route}")
    heading(page, title)
    settled(page)


def button(page, name):
    return page.get_by_role("button", name=name, exact=True)


def test_t_uicrs_02_a(client, page, admin, librarian, branch_a):
    """T-UICRS-02-a (LIB-UI-CRS-02): Heading 'Enrollment'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "crs-02", "Enrollment")


def test_t_uicrs_04_a(client, page, admin, librarian, branch_a):
    """T-UICRS-04-a (LIB-UI-CRS-04): Heading 'Reserve desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "crs-04", "Reserve desk")


def test_t_uicrs_06_a(client, page, admin, librarian, branch_a):
    """T-UICRS-06-a (LIB-UI-CRS-06): Heading 'Course reserves report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "crs-06", "Course reserves report")


def test_t_uidig_02_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-02-a (LIB-UI-DIG-02): Heading 'Borrow, hold, open'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "dig-02", "Borrow, hold, open")


def test_t_uidig_04_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-04-a (LIB-UI-DIG-04): Heading 'Licenses'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "dig-04", "Licenses")


def test_t_uidig_06_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-06-a (LIB-UI-DIG-06): Heading 'Digital desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "dig-06", "Digital desk")


def test_t_uieq_02_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-02-a (LIB-UI-EQ-02): Heading 'Reserve equipment'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "eq-02", "Reserve equipment")


def test_t_uieq_04_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-04-a (LIB-UI-EQ-04): Heading 'Equipment desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "eq-04", "Equipment desk")


def test_t_uievt_02_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-02-a (LIB-UI-EVT-02): Heading 'Event page'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "evt-02", "Event page")


def test_t_uievt_04_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-04-a (LIB-UI-EVT-04): Heading 'Event management'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "evt-04", "Event management")


def test_t_uievt_06_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-06-a (LIB-UI-EVT-06): Heading 'Attendance report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "evt-06", "Attendance report")


def test_t_uiill_02_a(client, page, admin, librarian, branch_a):
    """T-UIILL-02-a (LIB-UI-ILL-02): Heading 'My interlibrary requests'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "ill-02", "My interlibrary requests")


def test_t_uiill_04_a(client, page, admin, librarian, branch_a):
    """T-UIILL-04-a (LIB-UI-ILL-04): Heading 'Interlibrary desk (outgoing)'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "ill-04", "Interlibrary desk (outgoing)")


def test_t_uiill_06_a(client, page, admin, librarian, branch_a):
    """T-UIILL-06-a (LIB-UI-ILL-06): Heading 'Interlibrary activity report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "ill-06", "Interlibrary activity report")


def test_t_uiroom_02_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-02-a (LIB-UI-ROOM-02): Heading 'Availability'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "room-02", "Availability")


def test_t_uiroom_04_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-04-a (LIB-UI-ROOM-04): Heading 'Booking form'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "room-04", "Booking form")


def test_t_uiroom_06_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-06-a (LIB-UI-ROOM-06): Heading 'Desk view'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "room-06", "Desk view")


def test_t_uistf_02_a(client, page, admin, librarian, branch_a):
    """T-UISTF-02-a (LIB-UI-STF-02): Heading 'Branch hours and closures'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "stf-02", "Branch hours and closures")


def test_t_uistf_04_a(client, page, admin, librarian, branch_a):
    """T-UISTF-04-a (LIB-UI-STF-04): Heading 'My shifts'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "stf-04", "My shifts")


def test_t_uistf_06_a(client, page, admin, librarian, branch_a):
    """T-UISTF-06-a (LIB-UI-STF-06): Heading 'Staff reports'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "stf-06", "Staff reports")
