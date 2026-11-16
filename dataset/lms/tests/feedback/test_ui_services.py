"""Feedback tests: web interface, screens of modules 15–21 (step 25). Generated from cases/ui_services.md."""
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


def test_t_uicrs_01_a(client, page, admin, librarian, branch_a):
    """T-UICRS-01-a (LIB-UI-CRS-01): Heading 'Courses'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "crs-01", "Courses")


def test_t_uicrs_03_a(client, page, admin, librarian, branch_a):
    """T-UICRS-03-a (LIB-UI-CRS-03): Heading 'Reading list'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "crs-03", "Reading list")


def test_t_uicrs_05_a(client, page, admin, librarian, branch_a):
    """T-UICRS-05-a (LIB-UI-CRS-05): Heading 'My courses'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "crs-05", "My courses")


def test_t_uidig_01_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-01-a (LIB-UI-DIG-01): Heading 'Digital library'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "dig-01", "Digital library")


def test_t_uidig_03_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-03-a (LIB-UI-DIG-03): Heading 'My digital library'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "dig-03", "My digital library")


def test_t_uidig_05_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-05-a (LIB-UI-DIG-05): Heading 'Resources'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "dig-05", "Resources")


def test_t_uidig_07_a(client, page, admin, librarian, branch_a):
    """T-UIDIG-07-a (LIB-UI-DIG-07): Heading 'Digital usage report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "dig-07", "Digital usage report")


def test_t_uieq_01_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-01-a (LIB-UI-EQ-01): Heading 'Equipment catalog'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "eq-01", "Equipment catalog")


def test_t_uieq_03_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-03-a (LIB-UI-EQ-03): Heading 'My equipment'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "eq-03", "My equipment")


def test_t_uieq_05_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-05-a (LIB-UI-EQ-05): Heading 'Types and items'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "eq-05", "Types and items")


def test_t_uieq_07_a(client, page, admin, librarian, branch_a):
    """T-UIEQ-07-a (LIB-UI-EQ-07): Heading 'Equipment usage report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "eq-07", "Equipment usage report")


def test_t_uievt_01_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-01-a (LIB-UI-EVT-01): Heading 'Event calendar'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "evt-01", "Event calendar")


def test_t_uievt_03_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-03-a (LIB-UI-EVT-03): Heading 'My events'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "evt-03", "My events")


def test_t_uievt_05_a(client, page, admin, librarian, branch_a):
    """T-UIEVT-05-a (LIB-UI-EVT-05): Heading 'Event desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "evt-05", "Event desk")


def test_t_uiill_01_a(client, page, admin, librarian, branch_a):
    """T-UIILL-01-a (LIB-UI-ILL-01): Heading 'Request a book from another library'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "ill-01", "Request a book from another library")


def test_t_uiill_03_a(client, page, admin, librarian, branch_a):
    """T-UIILL-03-a (LIB-UI-ILL-03): Heading 'Interlibrary desk (incoming)'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "ill-03", "Interlibrary desk (incoming)")


def test_t_uiill_05_a(client, page, admin, librarian, branch_a):
    """T-UIILL-05-a (LIB-UI-ILL-05): Heading 'Partners'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "ill-05", "Partners")


def test_t_uiroom_01_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-01-a (LIB-UI-ROOM-01): Heading 'Room list'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "room-01", "Room list")


def test_t_uiroom_03_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-03-a (LIB-UI-ROOM-03): Heading 'Find a free room'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "room-03", "Find a free room")


def test_t_uiroom_05_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-05-a (LIB-UI-ROOM-05): Heading 'My room bookings'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "room-05", "My room bookings")


def test_t_uiroom_07_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-07-a (LIB-UI-ROOM-07): Heading 'Room management'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "room-07", "Room management")


def test_t_uiroom_09_a(client, page, admin, librarian, branch_a):
    """T-UIROOM-09-a (LIB-UI-ROOM-09): Heading 'Room usage report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "room-09", "Room usage report")


def test_t_uistf_01_a(client, page, admin, librarian, branch_a):
    """T-UISTF-01-a (LIB-UI-STF-01): Heading 'Staff'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "stf-01", "Staff")


def test_t_uistf_03_a(client, page, admin, librarian, branch_a):
    """T-UISTF-03-a (LIB-UI-STF-03): Heading 'Shift plan'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "stf-03", "Shift plan")


def test_t_uistf_05_a(client, page, admin, librarian, branch_a):
    """T-UISTF-05-a (LIB-UI-STF-05): Heading 'Leave'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "stf-05", "Leave")
