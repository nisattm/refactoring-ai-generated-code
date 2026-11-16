MODULE = "ui_community"
TITLE = "web interface, screens of modules 22–28 (step 26)"

HEADER = '''
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
'''


def smoke(code, title, role):
    """One case per screen: the role named in the screen opens its route (LIB-UI-GEN-03, LIB-UI-GEN-07)."""
    route = code.lower()
    return dict(
        id=f"T-UI{code}-a", req=f"LIB-UI-{code}", type="Normal",
        input=f"A {role} opens `/ui/#/{route}`",
        expected=f'Heading "{title}"; no error shown, no JavaScript error',
        code=f"""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "{role}")
    open_screen(page, "{route}", "{title}")
""")


# (screen code, screen name, role that opens it) for every screen with a route (LIB-UI-GEN-03)
SCREENS = [
    ("DON-01", "Donors", "librarian"),
    ("DON-02", "Offer form", "member"),
    ("DON-03", "Review", "librarian"),
    ("DON-04", "Receiving desk", "librarian"),
    ("DON-05", "Receipt and my donations", "member"),
    ("DON-06", "Donor wall and reports", "member"),
    ("PRE-01", "Budgets", "admin"),
    ("PRE-02", "Inspection", "librarian"),
    ("PRE-03", "Jobs", "librarian"),
    ("PRE-04", "Shipments", "librarian"),
    ("PRE-05", "Preservation reports", "librarian"),
    ("INV-01", "Counts", "librarian"),
    ("INV-02", "Scanning", "librarian"),
    ("INV-03", "Closing", "librarian"),
    ("INV-04", "Problems", "librarian"),
    ("INV-05", "Found copies", "librarian"),
    ("INV-06", "Inventory report", "librarian"),
    ("SUG-01", "Suggest a book", "member"),
    ("SUG-02", "Suggestions board", "member"),
    ("SUG-03", "My suggestions", "member"),
    ("SUG-04", "Review queue", "librarian"),
    ("SUG-05", "Ordering", "librarian"),
    ("SUG-06", "Suggestions report", "librarian"),
    ("RDP-01", "Programs", "librarian"),
    ("RDP-02", "Join", "member"),
    ("RDP-03", "My progress", "member"),
    ("RDP-04", "Leaderboard", "member"),
    ("RDP-05", "Manual entries", "librarian"),
    ("RDP-06", "Programs report", "librarian"),
    ("MSG-01", "Announcements", "librarian"),
    ("MSG-03", "Inbox", "librarian"),
    ("MSG-04", "My messages", "member"),
    ("MSG-05", "Messaging report", "librarian"),
    ("ACC-01", "Cards", "librarian"),
    ("ACC-02", "Gate", "librarian"),
    ("ACC-03", "Occupancy", "member"),
    ("ACC-04", "Day passes", "librarian"),
    ("ACC-05", "Bans and alerts", "librarian"),
    ("ACC-06", "Visits report", "librarian"),
]

FLOWS = [
    dict(id="T-UIACC-02-b", req="LIB-UI-ACC-02", type="Normal", input="The librarian scans a member's card at branch A (in), then again", expected="Result `entered` with the member's name, occupancy 1; then `ALREADY_INSIDE`", code="""
def TEST(client, page, admin, librarian, branch_a):
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
"""),
]

CASES = sorted([smoke(*s) for s in SCREENS] + FLOWS, key=lambda c: (c["req"].startswith("LIB-UI-GEN") is False, c["id"]))
