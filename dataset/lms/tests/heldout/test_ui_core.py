"""Heldout tests: web interface, general rules and screens of modules 1–14 (step 24). Generated from cases/ui_core.md."""
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


def test_t_uigen_02_a(client):
    """T-UIGEN-02-a (LIB-UI-GEN-02): 200 HTML page; the API is unchanged (200 JSON)"""
    r = client.get("/ui/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), r.status_code
    assert client.get("/health").json()["status"] == "ok"


def test_t_uigen_04_b(client, page, librarian):
    """T-UIGEN-04-b (LIB-UI-GEN-04): Alert with INVALID_CREDENTIALS; still 'Log in' with the e-mail kept"""
    page.goto("/ui/#/login")
    page.locator('[name="email"]').fill(LIBRARIAN[0])
    page.locator('[name="password"]').fill("Wrong12345")
    button(page, "Log in").click()
    expect(page.get_by_role("alert")).to_contain_text("INVALID_CREDENTIALS")
    heading(page, "Log in")
    expect(page.locator('[name="email"]')).to_have_value(LIBRARIAN[0])


def test_t_uigen_06_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-06-a (LIB-UI-GEN-06): Librarian: links 'Member list' and 'Loan desk', no 'Users'; member: 'My loans', no 'Member list'"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "home", "Home")
    link = lambda name: page.get_by_role("link", name=name, exact=True)
    expect(link("Member list").first).to_be_visible()
    expect(link("Loan desk").first).to_be_visible()
    expect(link("Users")).to_have_count(0)
    button(page, "Log out").click()
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    log_in(page, m["email"], MEMBER_PASSWORD)
    open_screen(page, "home", "Home")
    expect(link("My loans").first).to_be_visible()
    expect(link("Member list")).to_have_count(0)


def test_t_uigen_08_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-08-a (LIB-UI-GEN-08): 'Home' with the member number"""
    m = sign_in(client, page, admin, librarian, branch_a, "member")
    page.goto("/ui/")
    heading(page, "Home")
    expect(page.get_by_text(m["member_no"]).first).to_be_visible()
    settled(page)


def test_t_uigen_12_a(client, page, admin, librarian, branch_a):
    """T-UIGEN-12-a (LIB-UI-GEN-12): Alert with CONFLICT; the entered name stays"""
    used = register_member(client, librarian, home_branch_id=branch_a["id"])
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-02", "Register member")
    page.locator('[name="full_name"]').fill("Ayşe Yılmaz")
    page.locator('[name="email"]').fill(used["email"])
    page.locator('[name="membership_type"]').select_option("student")
    page.locator('[name="university_id"]').fill("U7777777")
    page.locator('[name="home_branch_id"]').select_option(str(branch_a["id"]))
    page.locator('[name="password"]').fill("Member1234")
    button(page, "Register").click()
    expect(page.get_by_role("alert")).to_contain_text("CONFLICT")
    expect(page.locator('[name="full_name"]')).to_have_value("Ayşe Yılmaz")


def test_t_uiaud_02_a(client, page, admin, librarian, branch_a):
    """T-UIAUD-02-a (LIB-UI-AUD-02): Heading 'Import and export'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "admin")
    open_screen(page, "aud-02", "Import and export")


def test_t_uibr_02_a(client, page, admin, librarian, branch_a):
    """T-UIBR-02-a (LIB-UI-BR-02): Heading 'Transfers'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "br-02", "Transfers")


def test_t_uicat_02_a(client, page, admin, librarian, branch_a):
    """T-UICAT-02-a (LIB-UI-CAT-02): Heading 'Book page'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "cat-02", "Book page")


def test_t_uicat_04_a(client, page, admin, librarian, branch_a):
    """T-UICAT-04-a (LIB-UI-CAT-04): Heading 'Authors and publishers'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "cat-04", "Authors and publishers")


def test_t_uifee_02_a(client, page, admin, librarian, branch_a):
    """T-UIFEE-02-a (LIB-UI-FEE-02): Heading 'Fees and payments'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "fee-02", "Fees and payments")


def test_t_uiloan_01_b(client, page, admin, librarian, branch_a):
    """T-UILOAN-01-b (LIB-UI-LOAN-01): Due date 2026-11-16 shown; one open loan in the API"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "loan-01", "Loan desk")
    page.locator('[name="member_no"]').first.fill(m["member_no"])
    page.locator('[name="barcode"]').first.fill(c["barcode"])
    button(page, "Lend").click()
    expect(page.get_by_text("2026-11-16").first).to_be_visible()
    loans = items(client.get(f"/api/v1/members/{m['id']}/loans", headers=librarian).json())
    assert [(l["copy_id"], l["status"]) for l in loans] == [(c["id"], "open")]


def test_t_uiloan_02_a(client, page, admin, librarian, branch_a):
    """T-UILOAN-02-a (LIB-UI-LOAN-02): Heading 'Loans'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "loan-02", "Loans")


def test_t_uimem_02_b(client, page, admin, librarian, branch_a):
    """T-UIMEM-02-b (LIB-UI-MEM-02): Status message with the member number; the member exists in the API"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-02", "Register member")
    page.locator('[name="full_name"]').fill("Deniz Kaya")
    page.locator('[name="email"]').fill("deniz.kaya@example.edu.tr")
    page.locator('[name="membership_type"]').select_option("student")
    page.locator('[name="university_id"]').fill("U1234567")
    page.locator('[name="home_branch_id"]').select_option(str(branch_a["id"]))
    page.locator('[name="password"]').fill("Member1234")
    button(page, "Register").click()
    expect(page.get_by_role("status").first).to_be_visible()
    rows = items(client.get("/api/v1/members", headers=librarian, params={"q": "deniz.kaya"}).json())
    assert [r["full_name"] for r in rows] == ["Deniz Kaya"]
    expect(page.get_by_text(rows[0]["member_no"]).first).to_be_visible()


def test_t_uimem_04_a(client, page, admin, librarian, branch_a):
    """T-UIMEM-04-a (LIB-UI-MEM-04): Heading 'My membership'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "mem-04", "My membership")


def test_t_uinot_02_b(client, page, admin, librarian, branch_a):
    """T-UINOT-02-b (LIB-UI-NOT-02): Status message with the count"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "not-02", "Notifications")
    button(page, "Run reminders").click()
    expect(page.get_by_role("status").first).to_contain_text("0")
    settled(page)


def test_t_uipur_02_a(client, page, admin, librarian, branch_a):
    """T-UIPUR-02-a (LIB-UI-PUR-02): Heading 'Purchase orders'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pur-02", "Purchase orders")


def test_t_uirep_02_a(client, page, admin, librarian, branch_a):
    """T-UIREP-02-a (LIB-UI-REP-02): Heading 'Overdue loans'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rep-02", "Overdue loans")


def test_t_uirep_04_a(client, page, admin, librarian, branch_a):
    """T-UIREP-04-a (LIB-UI-REP-04): Heading 'Copies by status'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rep-04", "Copies by status")


def test_t_uires_02_a(client, page, admin, librarian, branch_a):
    """T-UIRES-02-a (LIB-UI-RES-02): Heading 'Reservations'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "res-02", "Reservations")


def test_t_uisrch_01_b(client, page, admin, librarian, branch_a):
    """T-UISRCH-01-b (LIB-UI-SRCH-01): The book 'Kayıp Şehir' in the results"""
    create_book(client, librarian, title="Kayıp Şehir")
    create_book(client, librarian, title="Deniz Feneri")
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "srch-01", "Search")
    page.locator('[name="q"]').fill("kayıp")
    button(page, "Search").click()
    expect(page.get_by_text("Kayıp Şehir").first).to_be_visible()
    expect(page.get_by_text("Deniz Feneri")).to_have_count(0)
