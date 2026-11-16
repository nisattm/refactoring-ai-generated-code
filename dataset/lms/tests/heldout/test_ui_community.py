"""Heldout tests: web interface, screens of modules 22–28 (step 26). Generated from cases/ui_community.md."""
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


def test_t_uiacc_02_b(client, page, admin, librarian, branch_a):
    """T-UIACC-02-b (LIB-UI-ACC-02): Result entered with the member's name, occupancy 1; then ALREADY_INSIDE"""
    m = register_member(client, librarian, home_branch_id=branch_a["id"])
    card = client.post(f"/api/v1/members/{m['id']}/cards", headers=librarian).json()
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-02", "Gate")
    page.locator('[name="branch_id"]').select_option(str(branch_a["id"]))
    page.locator('[name="direction"]').select_option("in")
    page.locator('[name="card_no"]').fill(card["card_no"])
    button(page, "Scan").click()
    expect(page.get_by_text("entered").first).to_be_visible()
    expect(page.get_by_text(m["full_name"]).first).to_be_visible()
    assert client.get(f"/api/v1/branches/{branch_a['id']}/occupancy", headers=librarian).json()["inside"] == 1
    page.locator('[name="card_no"]').fill(card["card_no"])
    button(page, "Scan").click()
    expect(page.get_by_role("alert")).to_contain_text("ALREADY_INSIDE")


def test_t_uiacc_04_a(client, page, admin, librarian, branch_a):
    """T-UIACC-04-a (LIB-UI-ACC-04): Heading 'Day passes'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-04", "Day passes")


def test_t_uiacc_06_a(client, page, admin, librarian, branch_a):
    """T-UIACC-06-a (LIB-UI-ACC-06): Heading 'Visits report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "acc-06", "Visits report")


def test_t_uidon_02_a(client, page, admin, librarian, branch_a):
    """T-UIDON-02-a (LIB-UI-DON-02): Heading 'Offer form'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "don-02", "Offer form")


def test_t_uidon_04_a(client, page, admin, librarian, branch_a):
    """T-UIDON-04-a (LIB-UI-DON-04): Heading 'Receiving desk'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "don-04", "Receiving desk")


def test_t_uidon_06_a(client, page, admin, librarian, branch_a):
    """T-UIDON-06-a (LIB-UI-DON-06): Heading 'Donor wall and reports'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "don-06", "Donor wall and reports")


def test_t_uiinv_02_a(client, page, admin, librarian, branch_a):
    """T-UIINV-02-a (LIB-UI-INV-02): Heading 'Scanning'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-02", "Scanning")


def test_t_uiinv_04_a(client, page, admin, librarian, branch_a):
    """T-UIINV-04-a (LIB-UI-INV-04): Heading 'Problems'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-04", "Problems")


def test_t_uiinv_06_a(client, page, admin, librarian, branch_a):
    """T-UIINV-06-a (LIB-UI-INV-06): Heading 'Inventory report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "inv-06", "Inventory report")


def test_t_uimsg_04_a(client, page, admin, librarian, branch_a):
    """T-UIMSG-04-a (LIB-UI-MSG-04): Heading 'My messages'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "msg-04", "My messages")


def test_t_uipre_02_a(client, page, admin, librarian, branch_a):
    """T-UIPRE-02-a (LIB-UI-PRE-02): Heading 'Inspection'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pre-02", "Inspection")


def test_t_uipre_04_a(client, page, admin, librarian, branch_a):
    """T-UIPRE-04-a (LIB-UI-PRE-04): Heading 'Shipments'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "pre-04", "Shipments")


def test_t_uirdp_02_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-02-a (LIB-UI-RDP-02): Heading 'Join'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "rdp-02", "Join")


def test_t_uirdp_04_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-04-a (LIB-UI-RDP-04): Heading 'Leaderboard'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "rdp-04", "Leaderboard")


def test_t_uirdp_06_a(client, page, admin, librarian, branch_a):
    """T-UIRDP-06-a (LIB-UI-RDP-06): Heading 'Programs report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "rdp-06", "Programs report")


def test_t_uisug_02_a(client, page, admin, librarian, branch_a):
    """T-UISUG-02-a (LIB-UI-SUG-02): Heading 'Suggestions board'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "sug-02", "Suggestions board")


def test_t_uisug_04_a(client, page, admin, librarian, branch_a):
    """T-UISUG-04-a (LIB-UI-SUG-04): Heading 'Review queue'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "sug-04", "Review queue")


def test_t_uisug_06_a(client, page, admin, librarian, branch_a):
    """T-UISUG-06-a (LIB-UI-SUG-06): Heading 'Suggestions report'; no error shown, no JavaScript error"""
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "sug-06", "Suggestions report")
