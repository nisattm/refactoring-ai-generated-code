"""Feedback tests: web interface, screens of modules 22–28 (step 26). Generated from cases/ui_community.md."""
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


def test_t_uiacc_01_a(client, page, admin, librarian, branch_a):
    """T-UIACC-01-a (LIB-UI-ACC-01): Heading 'Cards'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-01", "Cards")


def test_t_uiacc_02_a(client, page, admin, librarian, branch_a):
    """T-UIACC-02-a (LIB-UI-ACC-02): Heading 'Gate'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-02", "Gate")


def test_t_uiacc_03_a(client, page, admin, librarian, branch_a):
    """T-UIACC-03-a (LIB-UI-ACC-03): Heading 'Occupancy'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "acc-03", "Occupancy")


def test_t_uiacc_05_a(client, page, admin, librarian, branch_a):
    """T-UIACC-05-a (LIB-UI-ACC-05): Heading 'Bans and alerts'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-05", "Bans and alerts")


def test_t_uidon_01_a(client, page, admin, librarian, branch_a):
    """T-UIDON-01-a (LIB-UI-DON-01): Heading 'Donors'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "don-01", "Donors")


def test_t_uidon_03_a(client, page, admin, librarian, branch_a):
    """T-UIDON-03-a (LIB-UI-DON-03): Heading 'Review'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "don-03", "Review")


def test_t_uidon_05_a(client, page, admin, librarian, branch_a):
    """T-UIDON-05-a (LIB-UI-DON-05): Heading 'Receipt and my donations'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "don-05", "Receipt and my donations")


def test_t_uiinv_01_a(client, page, admin, librarian, branch_a):
    """T-UIINV-01-a (LIB-UI-INV-01): Heading 'Counts'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-01", "Counts")


def test_t_uiinv_03_a(client, page, admin, librarian, branch_a):
    """T-UIINV-03-a (LIB-UI-INV-03): Heading 'Closing'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-03", "Closing")


def test_t_uiinv_05_a(client, page, admin, librarian, branch_a):
    """T-UIINV-05-a (LIB-UI-INV-05): Heading 'Found copies'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-05", "Found copies")


def test_t_uimsg_01_a(client, page, admin, librarian, branch_a):
    """T-UIMSG-01-a (LIB-UI-MSG-01): Heading 'Announcements'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "msg-01", "Announcements")


def test_t_uimsg_03_a(client, page, admin, librarian, branch_a):
    """T-UIMSG-03-a (LIB-UI-MSG-03): Heading 'Inbox'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "msg-03", "Inbox")


def test_t_uimsg_05_a(client, page, admin, librarian, branch_a):
    """T-UIMSG-05-a (LIB-UI-MSG-05): Heading 'Messaging report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "msg-05", "Messaging report")


def test_t_uipre_01_a(client, page, admin, librarian, branch_a):
    """T-UIPRE-01-a (LIB-UI-PRE-01): Heading 'Budgets'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "pre-01", "Budgets")


def test_t_uipre_03_a(client, page, admin, librarian, branch_a):
    """T-UIPRE-03-a (LIB-UI-PRE-03): Heading 'Jobs'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pre-03", "Jobs")


def test_t_uipre_05_a(client, page, admin, librarian, branch_a):
    """T-UIPRE-05-a (LIB-UI-PRE-05): Heading 'Preservation reports'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pre-05", "Preservation reports")


def test_t_uirdp_01_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-01-a (LIB-UI-RDP-01): Heading 'Programs'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rdp-01", "Programs")


def test_t_uirdp_03_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-03-a (LIB-UI-RDP-03): Heading 'My progress'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "rdp-03", "My progress")


def test_t_uirdp_05_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-05-a (LIB-UI-RDP-05): Heading 'Manual entries'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rdp-05", "Manual entries")


def test_t_uisug_01_a(client, page, admin, librarian, branch_a):
    """T-UISUG-01-a (LIB-UI-SUG-01): Heading 'Suggest a book'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "sug-01", "Suggest a book")


def test_t_uisug_03_a(client, page, admin, librarian, branch_a):
    """T-UISUG-03-a (LIB-UI-SUG-03): Heading 'My suggestions'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "sug-03", "My suggestions")


def test_t_uisug_05_a(client, page, admin, librarian, branch_a):
    """T-UISUG-05-a (LIB-UI-SUG-05): Heading 'Ordering'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "sug-05", "Ordering")
