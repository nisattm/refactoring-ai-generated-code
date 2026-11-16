"""Feedback tests: web interface, general rules and screens of modules 1–14 (step 24). Generated from cases/ui_core.md."""
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


def test_t_uigen_03_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-03-a (LIB-UI-GEN-03): 'Member list' before and after the reload"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    page.reload()
    heading(page, "Member list")


def test_t_uigen_04_a(client, page, librarian):
    """T-UIGEN-04-a (LIB-UI-GEN-04): 'Log in'; after logging in 'Member list'"""
    page.goto("/ui/#/mem-01")
    heading(page, "Log in")
    page.locator('[name="email"]').fill(LIBRARIAN[0])
    page.locator('[name="password"]').fill(LIBRARIAN[1])
    button(page, "Log in").click()
    heading(page, "Member list")


def test_t_uigen_05_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-05-a (LIB-UI-GEN-05): Header with name and role; after 'Log out' the login screen, also for #/mem-01"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    expect(page.get_by_text("Test Librarian").first).to_be_visible()
    button(page, "Log out").click()
    heading(page, "Log in")
    page.goto("/ui/#/mem-01")
    heading(page, "Log in")


def test_t_uigen_09_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-09-a (LIB-UI-GEN-09): 'Not allowed' with 'You do not have access to this screen.'"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    page.goto("/ui/#/usr-01")
    heading(page, "Not allowed")
    expect(page.get_by_text("You do not have access to this screen.")).to_be_visible()


def test_t_uigen_13_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-13-a (LIB-UI-GEN-13): A table and 'No records'"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    expect(page.locator("table:visible").first).to_be_visible()
    expect(page.get_by_text("No records").first).to_be_visible()


def test_t_uiacct_01_a(client, page, admin, librarian, branch_a):
    """T-UIACCT-01-a (LIB-UI-ACCT-01): Heading 'My account'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "acct-01", "My account")


def test_t_uiaud_01_a(client, page, admin, librarian, branch_a):
    """T-UIAUD-01-a (LIB-UI-AUD-01): Heading 'Audit log'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "aud-01", "Audit log")


def test_t_uibr_01_a(client, page, admin, librarian, branch_a):
    """T-UIBR-01-a (LIB-UI-BR-01): Heading 'Branches'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "br-01", "Branches")


def test_t_uical_01_a(client, page, admin, librarian, branch_a):
    """T-UICAL-01-a (LIB-UI-CAL-01): Heading 'Calendar'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "cal-01", "Calendar")


def test_t_uicat_01_a(client, page, admin, librarian, branch_a):
    """T-UICAT-01-a (LIB-UI-CAT-01): Heading 'Books'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "cat-01", "Books")


def test_t_uicat_03_a(client, page, admin, librarian, branch_a):
    """T-UICAT-03-a (LIB-UI-CAT-03): Heading 'Book form'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "cat-03", "Book form")


def test_t_uifee_01_a(client, page, admin, librarian, branch_a):
    """T-UIFEE-01-a (LIB-UI-FEE-01): Heading 'My fees'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "fee-01", "My fees")


def test_t_uiloan_01_a(client, page, admin, librarian, branch_a):
    """T-UILOAN-01-a (LIB-UI-LOAN-01): Heading 'Loan desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "loan-01", "Loan desk")


def test_t_uiloan_03_a(client, page, admin, librarian, branch_a):
    """T-UILOAN-03-a (LIB-UI-LOAN-03): Heading 'My loans'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "loan-03", "My loans")


def test_t_uimem_01_a(client, page, admin, librarian, branch_a):
    """T-UIMEM-01-a (LIB-UI-MEM-01): Heading 'Member list'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")


def test_t_uimem_02_a(client, page, admin, librarian, branch_a):
    """T-UIMEM-02-a (LIB-UI-MEM-02): Heading 'Register member'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-02", "Register member")


def test_t_uimem_03_a(client, page, admin, librarian, branch_a):
    """T-UIMEM-03-a (LIB-UI-MEM-03): Heading 'Member page'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-03", "Member page")


def test_t_uinot_01_a(client, page, admin, librarian, branch_a):
    """T-UINOT-01-a (LIB-UI-NOT-01): Heading 'My notifications'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "not-01", "My notifications")


def test_t_uinot_02_a(client, page, admin, librarian, branch_a):
    """T-UINOT-02-a (LIB-UI-NOT-02): Heading 'Notifications'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "not-02", "Notifications")


def test_t_uipur_01_a(client, page, admin, librarian, branch_a):
    """T-UIPUR-01-a (LIB-UI-PUR-01): Heading 'Suppliers'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pur-01", "Suppliers")


def test_t_uirep_01_a(client, page, admin, librarian, branch_a):
    """T-UIREP-01-a (LIB-UI-REP-01): Heading 'Most borrowed'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rep-01", "Most borrowed")


def test_t_uirep_03_a(client, page, admin, librarian, branch_a):
    """T-UIREP-03-a (LIB-UI-REP-03): Heading 'Monthly summary'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rep-03", "Monthly summary")


def test_t_uires_01_a(client, page, admin, librarian, branch_a):
    """T-UIRES-01-a (LIB-UI-RES-01): Heading 'My reservations'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "res-01", "My reservations")


def test_t_uisrch_01_a(client, page, admin, librarian, branch_a):
    """T-UISRCH-01-a (LIB-UI-SRCH-01): Heading 'Search'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "srch-01", "Search")


def test_t_uiusr_01_a(client, page, admin, librarian, branch_a):
    """T-UIUSR-01-a (LIB-UI-USR-01): Heading 'Users'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "usr-01", "Users")
