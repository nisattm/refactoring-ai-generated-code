MODULE = "ui_services"
TITLE = "web interface, screens of modules 15–21 (step 25)"

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
    ("ROOM-01", "Room list", "member"),
    ("ROOM-02", "Availability", "member"),
    ("ROOM-03", "Find a free room", "member"),
    ("ROOM-04", "Booking form", "member"),
    ("ROOM-05", "My room bookings", "member"),
    ("ROOM-06", "Desk view", "librarian"),
    ("ROOM-07", "Room management", "admin"),
    ("ROOM-09", "Room usage report", "librarian"),
    ("EQ-01", "Equipment catalog", "member"),
    ("EQ-02", "Reserve equipment", "member"),
    ("EQ-03", "My equipment", "member"),
    ("EQ-04", "Equipment desk", "librarian"),
    ("EQ-05", "Types and items", "admin"),
    ("EQ-07", "Equipment usage report", "librarian"),
    ("DIG-01", "Digital library", "member"),
    ("DIG-02", "Borrow, hold, open", "member"),
    ("DIG-03", "My digital library", "member"),
    ("DIG-04", "Licenses", "admin"),
    ("DIG-05", "Resources", "librarian"),
    ("DIG-06", "Digital desk", "librarian"),
    ("DIG-07", "Digital usage report", "librarian"),
    ("ILL-01", "Request a book from another library", "member"),
    ("ILL-02", "My interlibrary requests", "member"),
    ("ILL-03", "Interlibrary desk (incoming)", "librarian"),
    ("ILL-04", "Interlibrary desk (outgoing)", "librarian"),
    ("ILL-05", "Partners", "admin"),
    ("ILL-06", "Interlibrary activity report", "librarian"),
    ("STF-01", "Staff", "admin"),
    ("STF-02", "Branch hours and closures", "admin"),
    ("STF-03", "Shift plan", "admin"),
    ("STF-04", "My shifts", "librarian"),
    ("STF-05", "Leave", "librarian"),
    ("STF-06", "Staff reports", "admin"),
    ("EVT-01", "Event calendar", "member"),
    ("EVT-02", "Event page", "member"),
    ("EVT-03", "My events", "member"),
    ("EVT-04", "Event management", "librarian"),
    ("EVT-05", "Event desk", "librarian"),
    ("EVT-06", "Attendance report", "librarian"),
    ("CRS-01", "Courses", "librarian"),
    ("CRS-02", "Enrollment", "librarian"),
    ("CRS-03", "Reading list", "librarian"),
    ("CRS-04", "Reserve desk", "librarian"),
    ("CRS-05", "My courses", "member"),
    ("CRS-06", "Course reserves report", "librarian"),
]

FLOWS = []

CASES = sorted([smoke(*s) for s in SCREENS] + FLOWS, key=lambda c: (c["req"].startswith("LIB-UI-GEN") is False, c["id"]))
