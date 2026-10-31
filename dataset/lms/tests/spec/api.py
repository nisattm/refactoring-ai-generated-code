MODULE = "api"
TITLE = "module 14 (API layer)"

HEADER = '''
import re

from support.api import add_copy, create_book, error_code

ENDPOINTS = [
    ("GET", "/health"),
    ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout"), ("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/change-password"),
    ("GET", "/api/v1/users"), ("POST", "/api/v1/users"), ("GET", "/api/v1/users/{}"), ("PATCH", "/api/v1/users/{}"),
    ("POST", "/api/v1/users/{}/reset-password"),
    ("GET", "/api/v1/calendar/holidays"), ("GET", "/api/v1/calendar/days/{}"), ("GET", "/api/v1/calendar/next-working-day"),
    ("GET", "/api/v1/calendar/add-working-days"), ("GET", "/api/v1/calendar/working-days-between"),
    ("GET", "/api/v1/members"), ("POST", "/api/v1/members"), ("GET", "/api/v1/members/me"), ("GET", "/api/v1/members/{}"),
    ("PATCH", "/api/v1/members/{}"), ("POST", "/api/v1/members/{}/renew-membership"), ("POST", "/api/v1/members/{}/deactivate"),
    ("POST", "/api/v1/members/{}/activate"), ("GET", "/api/v1/members/{}/summary"), ("GET", "/api/v1/members/{}/loans"),
    ("GET", "/api/v1/members/{}/reservations"), ("GET", "/api/v1/members/{}/fees"), ("GET", "/api/v1/members/{}/balance"),
    ("GET", "/api/v1/members/{}/payments"), ("POST", "/api/v1/members/{}/payments"), ("GET", "/api/v1/members/{}/notifications"),
    ("GET", "/api/v1/members/{}/notifications/unread-count"), ("POST", "/api/v1/members/{}/notifications/read-all"),
    ("GET", "/api/v1/authors"), ("POST", "/api/v1/authors"), ("GET", "/api/v1/authors/{}"), ("PATCH", "/api/v1/authors/{}"),
    ("DELETE", "/api/v1/authors/{}"),
    ("GET", "/api/v1/publishers"), ("POST", "/api/v1/publishers"), ("GET", "/api/v1/publishers/{}"), ("PATCH", "/api/v1/publishers/{}"),
    ("DELETE", "/api/v1/publishers/{}"),
    ("GET", "/api/v1/books"), ("POST", "/api/v1/books"), ("GET", "/api/v1/books/{}"), ("PATCH", "/api/v1/books/{}"),
    ("DELETE", "/api/v1/books/{}"), ("GET", "/api/v1/books/{}/copies"), ("POST", "/api/v1/books/{}/copies"),
    ("GET", "/api/v1/books/{}/reservations"),
    ("GET", "/api/v1/copies/{}"), ("PATCH", "/api/v1/copies/{}"), ("GET", "/api/v1/copies/by-barcode/{}"),
    ("POST", "/api/v1/copies/{}/withdraw"), ("POST", "/api/v1/copies/{}/repair"),
    ("GET", "/api/v1/loans"), ("POST", "/api/v1/loans"), ("GET", "/api/v1/loans/{}"), ("POST", "/api/v1/loans/{}/renew"),
    ("POST", "/api/v1/loans/{}/return"), ("POST", "/api/v1/loans/{}/report-lost"),
    ("GET", "/api/v1/reservations"), ("POST", "/api/v1/reservations"), ("GET", "/api/v1/reservations/{}"),
    ("POST", "/api/v1/reservations/{}/cancel"), ("POST", "/api/v1/reservations/process-expired"),
    ("GET", "/api/v1/fees"), ("POST", "/api/v1/fees/{}/waive"),
    ("GET", "/api/v1/notifications"), ("POST", "/api/v1/notifications/{}/read"), ("POST", "/api/v1/notifications/run-reminders"),
    ("GET", "/api/v1/search/books"),
    ("GET", "/api/v1/reports/most-borrowed"), ("GET", "/api/v1/reports/overdue"), ("GET", "/api/v1/reports/monthly-summary"),
    ("GET", "/api/v1/reports/inventory"),
    ("GET", "/api/v1/branches"), ("POST", "/api/v1/branches"), ("GET", "/api/v1/branches/{}"), ("PATCH", "/api/v1/branches/{}"),
    ("GET", "/api/v1/transfers"), ("POST", "/api/v1/transfers"), ("GET", "/api/v1/transfers/{}"),
    ("POST", "/api/v1/transfers/process-arrivals"),
    ("GET", "/api/v1/suppliers"), ("POST", "/api/v1/suppliers"), ("GET", "/api/v1/suppliers/{}"), ("PATCH", "/api/v1/suppliers/{}"),
    ("GET", "/api/v1/purchase-orders"), ("POST", "/api/v1/purchase-orders"), ("GET", "/api/v1/purchase-orders/{}"),
    ("PATCH", "/api/v1/purchase-orders/{}"), ("POST", "/api/v1/purchase-orders/{}/submit"), ("POST", "/api/v1/purchase-orders/{}/cancel"),
    ("POST", "/api/v1/purchase-orders/{}/receive"),
    ("GET", "/api/v1/audit-log"), ("POST", "/api/v1/import"), ("GET", "/api/v1/export"), ("GET", "/api/v1/export/{}.csv"),
]


def openapi_endpoints(client):
    doc = client.get("/openapi.json").json()
    found = set()
    for path, ops in doc["paths"].items():
        for method in ops:
            found.add((method.upper(), re.sub(r"\\{[^}]+\\}", "{}", path)))
    return found
'''


CASES = [
    dict(id="T-API-01-a", req="LIB-API-01", type="Normal", input="Every endpoint of the requirements, called without token with id 1", expected="No call returns `404` or `405` (authentication or validation answers first, so the route exists)", code='''
def TEST(client):
    for method, path in ENDPOINTS:
        url = path.replace("{}", "1")
        r = client.request(method, url, json={} if method in {"POST", "PATCH"} else None)
        assert r.status_code not in {404, 405}, (method, path, r.status_code)
'''),
    dict(id="T-API-01-b", req="LIB-API-01", type="Error", input="`GET /api/v1/books/abc`, `/books/0`, `/books/-1` as librarian", expected="`422 VALIDATION_ERROR` each", code='''
def TEST(client, librarian):
    for bad in ("abc", "0", "-1"):
        r = client.get(f"/api/v1/books/{bad}", headers=librarian)
        assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR", bad
'''),
    dict(id="T-API-02-a", req="LIB-API-02", type="Error", input="`GET /api/v1/nothing-here`; `DELETE /api/v1/branches`", expected="`404 NOT_FOUND`; `405 METHOD_NOT_ALLOWED`; both in the error format", code='''
def TEST(client, admin):
    r = client.get("/api/v1/nothing-here", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND" and "message" in r.json()["error"]
    r = client.delete("/api/v1/branches", headers=admin)
    assert r.status_code == 405 and error_code(r) == "METHOD_NOT_ALLOWED"
'''),
    dict(id="T-API-03-a", req="LIB-API-03", type="Normal", input="Copy without `shelf_location`; librarian's `UserOut`", expected="`shelf_location` present with `null`; `member_id` and `last_login_at` keys present", code='''
def TEST(client, librarian, branch_a):
    c = add_copy(client, librarian, create_book(client, librarian)["id"], home_branch_id=branch_a["id"])
    got = client.get(f"/api/v1/copies/{c['id']}", headers=librarian).json()
    assert "shelf_location" in got and got["shelf_location"] is None and got["withdrawn_reason"] is None
    me = client.get("/api/v1/auth/me", headers=librarian).json()
    assert "member_id" in me and me["member_id"] is None
'''),
    dict(id="T-API-04-a", req="LIB-API-04", type="Normal", input="`GET /openapi.json`", expected="Lists every endpoint of the requirements (path parameters compared by position)", code='''
def TEST(client):
    found = openapi_endpoints(client)
    missing = [e for e in ENDPOINTS if e not in found]
    assert missing == []
'''),
    dict(id="T-API-05-a", req="LIB-API-05", type="Error", input="`POST /api/v1/branches` with a JSON text but `Content-Type: text/plain`", expected="`422 VALIDATION_ERROR`", code='''
def TEST(client, admin):
    r = client.post("/api/v1/branches", headers={**admin, "Content-Type": "text/plain"}, content=b'{"code": "ZZ", "name": "Z", "address": ""}')
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
'''),
]
