"""Heldout tests: module 14 (API layer). Generated from cases/api.md."""
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
            found.add((method.upper(), re.sub(r"\{[^}]+\}", "{}", path)))
    return found


def test_t_api_01_b(client, librarian):
    """T-API-01-b (LIB-API-01): 422 VALIDATION_ERROR each"""
    for bad in ("abc", "0", "-1"):
        r = client.get(f"/api/v1/books/{bad}", headers=librarian)
        assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR", bad


def test_t_api_02_a(client, admin):
    """T-API-02-a (LIB-API-02): 404 NOT_FOUND; 405 METHOD_NOT_ALLOWED; both in the error format"""
    r = client.get("/api/v1/nothing-here", headers=admin)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND" and "message" in r.json()["error"]
    r = client.delete("/api/v1/branches", headers=admin)
    assert r.status_code == 405 and error_code(r) == "METHOD_NOT_ALLOWED"


def test_t_api_04_a(client):
    """T-API-04-a (LIB-API-04): Lists every endpoint of the requirements (path parameters compared by position)"""
    found = openapi_endpoints(client)
    missing = [e for e in ENDPOINTS if e not in found]
    assert missing == []
