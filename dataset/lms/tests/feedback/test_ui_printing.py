"""Feedback tests: web interface, screens of module 29 (step 27). Generated from cases/ui_printing.md."""
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


def test_t_uiprt_01_a(client, page, admin, librarian, branch_a):
    """T-UIPRT-01-a (LIB-UI-PRT-01): Heading 'Print'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "prt-01", "Print")


def test_t_uiprt_03_a(client, page, admin, librarian, branch_a):
    """T-UIPRT-03-a (LIB-UI-PRT-03): Heading 'Printers'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "prt-03", "Printers")


def test_t_uiprt_05_a(client, page, admin, librarian, branch_a):
    """T-UIPRT-05-a (LIB-UI-PRT-05): Heading 'Printing report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "prt-05", "Printing report")
