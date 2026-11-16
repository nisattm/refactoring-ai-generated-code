MODULE = "ui_core"
TITLE = "web interface, general rules and screens of modules 1–14 (step 24)"

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
    ("CAL-01", "Calendar", "member"),
    ("ACCT-01", "My account", "member"),
    ("USR-01", "Users", "admin"),
    ("MEM-01", "Member list", "librarian"),
    ("MEM-02", "Register member", "librarian"),
    ("MEM-03", "Member page", "librarian"),
    ("MEM-04", "My membership", "member"),
    ("CAT-01", "Books", "member"),
    ("CAT-02", "Book page", "member"),
    ("CAT-03", "Book form", "librarian"),
    ("CAT-04", "Authors and publishers", "librarian"),
    ("LOAN-01", "Loan desk", "librarian"),
    ("LOAN-02", "Loans", "librarian"),
    ("LOAN-03", "My loans", "member"),
    ("RES-01", "My reservations", "member"),
    ("RES-02", "Reservations", "librarian"),
    ("FEE-01", "My fees", "member"),
    ("FEE-02", "Fees and payments", "librarian"),
    ("NOT-01", "My notifications", "member"),
    ("NOT-02", "Notifications", "librarian"),
    ("SRCH-01", "Search", "member"),
    ("REP-01", "Most borrowed", "librarian"),
    ("REP-02", "Overdue loans", "librarian"),
    ("REP-03", "Monthly summary", "librarian"),
    ("REP-04", "Copies by status", "librarian"),
    ("BR-01", "Branches", "member"),
    ("BR-02", "Transfers", "librarian"),
    ("PUR-01", "Suppliers", "librarian"),
    ("PUR-02", "Purchase orders", "librarian"),
    ("AUD-01", "Audit log", "admin"),
    ("AUD-02", "Import and export", "admin"),
]

FLOWS = [
    dict(id="T-UIGEN-02-a", req="LIB-UI-GEN-02", type="Normal", input="`GET /ui/`; `GET /health`", expected="`200` HTML page; the API is unchanged (`200` JSON)", code="""
def TEST(client):
    r = client.get("/ui/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), r.status_code
    assert client.get("/health").json()["status"] == "ok"
"""),
    dict(id="T-UIGEN-03-a", req="LIB-UI-GEN-03", type="Normal", input="The librarian opens `#/mem-01` and reloads the page", expected="\"Member list\" before and after the reload", code="""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    page.reload()
    heading(page, "Member list")
"""),
    dict(id="T-UIGEN-04-a", req="LIB-UI-GEN-04", type="Normal", input="`#/mem-01` opened without a session; the librarian logs in there", expected="\"Log in\"; after logging in \"Member list\"", code="""
def TEST(client, page, librarian):
    page.goto("/ui/#/mem-01")
    heading(page, "Log in")
    page.locator('[name="email"]').fill(LIBRARIAN[0])
    page.locator('[name="password"]').fill(LIBRARIAN[1])
    button(page, "Log in").click()
    heading(page, "Member list")
"""),
    dict(id="T-UIGEN-04-b", req="LIB-UI-GEN-04", type="Error", input="Log in with a wrong password", expected="Alert with `INVALID_CREDENTIALS`; still \"Log in\" with the e-mail kept", code="""
def TEST(client, page, librarian):
    page.goto("/ui/#/login")
    page.locator('[name="email"]').fill(LIBRARIAN[0])
    page.locator('[name="password"]').fill("Wrong12345")
    button(page, "Log in").click()
    expect(page.get_by_role("alert")).to_contain_text("INVALID_CREDENTIALS")
    heading(page, "Log in")
    expect(page.locator('[name="email"]')).to_have_value(LIBRARIAN[0])
"""),
    dict(id="T-UIGEN-05-a", req="LIB-UI-GEN-05", type="Normal", input="The librarian logs out; opens `#/mem-01` again", expected="Header with name and role; after \"Log out\" the login screen, also for `#/mem-01`", code="""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    expect(page.get_by_text("Test Librarian").first).to_be_visible()
    button(page, "Log out").click()
    heading(page, "Log in")
    page.goto("/ui/#/mem-01")
    heading(page, "Log in")
"""),
    dict(id="T-UIGEN-06-a", req="LIB-UI-GEN-06", type="Normal", input="Menu of a librarian and of a member", expected="Librarian: links \"Member list\" and \"Loan desk\", no \"Users\"; member: \"My loans\", no \"Member list\"", code="""
def TEST(client, page, admin, librarian, branch_a):
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
"""),
    dict(id="T-UIGEN-08-a", req="LIB-UI-GEN-08", type="Normal", input="A member opens `/ui/`", expected="\"Home\" with the member number", code="""
def TEST(client, page, admin, librarian, branch_a):
    m = sign_in(client, page, admin, librarian, branch_a, "member")
    page.goto("/ui/")
    heading(page, "Home")
    expect(page.get_by_text(m["member_no"]).first).to_be_visible()
    settled(page)
"""),
    dict(id="T-UIGEN-09-a", req="LIB-UI-GEN-09", type="Error", input="A member opens `#/usr-01`", expected="\"Not allowed\" with \"You do not have access to this screen.\"", code="""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "member")
    page.goto("/ui/#/usr-01")
    heading(page, "Not allowed")
    expect(page.get_by_text("You do not have access to this screen.")).to_be_visible()
"""),
    dict(id="T-UIGEN-12-a", req="LIB-UI-GEN-12", type="Error", input="The librarian registers a member with an e-mail that is already used", expected="Alert with `CONFLICT`; the entered name stays", code="""
def TEST(client, page, admin, librarian, branch_a):
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
"""),
    dict(id="T-UIGEN-13-a", req="LIB-UI-GEN-13", type="Normal", input="The librarian opens the member list without members", expected="A table and \"No records\"", code="""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "mem-01", "Member list")
    expect(page.locator("table:visible").first).to_be_visible()
    expect(page.get_by_text("No records").first).to_be_visible()
"""),
    dict(id="T-UIMEM-02-b", req="LIB-UI-MEM-02", type="Normal", input="The librarian registers a student", expected="Status message with the member number; the member exists in the API", code="""
def TEST(client, page, admin, librarian, branch_a):
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
"""),
    dict(id="T-UILOAN-01-b", req="LIB-UI-LOAN-01", type="Normal", input="The librarian lends a copy by member number and barcode on Mon 2026-11-02", expected="Due date 2026-11-16 shown; one open loan in the API", code="""
def TEST(client, page, admin, librarian, branch_a):
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
"""),
    dict(id="T-UISRCH-01-b", req="LIB-UI-SRCH-01", type="Normal", input="A member searches `kayıp`", expected="The book \"Kayıp Şehir\" in the results", code="""
def TEST(client, page, admin, librarian, branch_a):
    create_book(client, librarian, title="Kayıp Şehir")
    create_book(client, librarian, title="Deniz Feneri")
    sign_in(client, page, admin, librarian, branch_a, "member")
    open_screen(page, "srch-01", "Search")
    page.locator('[name="q"]').fill("kayıp")
    button(page, "Search").click()
    expect(page.get_by_text("Kayıp Şehir").first).to_be_visible()
    expect(page.get_by_text("Deniz Feneri")).to_have_count(0)
"""),
    dict(id="T-UINOT-02-b", req="LIB-UI-NOT-02", type="Normal", input="The librarian runs the reminders", expected="Status message with the count", code="""
def TEST(client, page, admin, librarian, branch_a):
    sign_in(client, page, admin, librarian, branch_a, "librarian")
    open_screen(page, "not-02", "Notifications")
    button(page, "Run reminders").click()
    expect(page.get_by_role("status").first).to_contain_text("0")
    settled(page)
"""),
]

CASES = sorted([smoke(*s) for s in SCREENS] + FLOWS, key=lambda c: (c["req"].startswith("LIB-UI-GEN") is False, c["id"]))
