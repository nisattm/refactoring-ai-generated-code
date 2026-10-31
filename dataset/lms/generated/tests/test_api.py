"""Module 14: API layer (LIB-API-01 to LIB-API-05)."""

import re

import pytest

from tests.test_auth import admin_h, err  # noqa: F401
from tests.test_loans import API, lib, member_h, mk_book, mk_member, new_copy  # noqa: F401

ENDPOINT = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`?\s]*)")
REQUIREMENTS = __import__("pathlib").Path(__file__).resolve().parent.parent / "REQUIREMENTS.md"

# Example URLs that appear in the requirements text, not endpoints.
EXAMPLES = {"/api/v1/calendar/days/2026-10-29", "/api/v1/users/{own"}


def documented_endpoints():
    found = set()
    for method, path in ENDPOINT.findall(REQUIREMENTS.read_text(encoding="utf-8")):
        if path not in EXAMPLES:
            found.add((method.lower(), path))
    return found


def test_openapi_lists_every_documented_endpoint(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    missing = [(m, p) for m, p in sorted(documented_endpoints()) if m not in paths.get(p, {}) and p != "/openapi.json"]
    assert missing == []


def test_unknown_path_and_method(client, admin_h):
    e = err(client.get("/api/v1/nothing"), 404, "NOT_FOUND")
    assert e["message"]
    err(client.get("/nothing", headers=admin_h), 404, "NOT_FOUND")
    err(client.delete(f"{API}/branches"), 405, "METHOD_NOT_ALLOWED")
    err(client.post("/health"), 405, "METHOD_NOT_ALLOWED")
    err(client.put(f"{API}/calendar/holidays"), 405, "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize(
    "path",
    [
        "/authors/{}", "/publishers/{}", "/books/{}", "/books/{}/copies", "/books/{}/reservations", "/copies/{}",
        "/branches/{}", "/members/{}", "/members/{}/loans", "/members/{}/balance", "/members/{}/fees",
        "/members/{}/payments", "/members/{}/reservations", "/members/{}/notifications",
        "/members/{}/notifications/unread-count", "/members/{}/summary", "/loans/{}", "/reservations/{}",
        "/transfers/{}", "/purchase-orders/{}", "/users/{}",
    ],
)
@pytest.mark.parametrize("value", ["0", "-3", "abc", "1.5"])
def test_id_path_parameters_must_be_positive_integers(client, admin_h, path, value):
    e = err(client.get(API + path.format(value), headers=admin_h), 422, "VALIDATION_ERROR")
    assert e["details"]["fields"]


@pytest.mark.parametrize(
    "path",
    ["/copies/{}/withdraw", "/copies/{}/repair", "/members/{}/payments", "/loans/{}/renew", "/loans/{}/return",
     "/loans/{}/report-lost", "/fees/{}/waive", "/reservations/{}/cancel",
     "/purchase-orders/{}/submit", "/purchase-orders/{}/cancel", "/purchase-orders/{}/receive",
     "/members/{}/renew-membership", "/members/{}/activate", "/members/{}/deactivate",
     "/users/{}/reset-password"],
)
def test_id_in_action_paths(client, admin_h, path):
    err(client.post(API + path.format("0"), headers=admin_h, json={}), 422, "VALIDATION_ERROR")
    err(client.post(API + path.format("x"), headers=admin_h, json={}), 422, "VALIDATION_ERROR")


def test_non_json_content_type_is_rejected(client, admin_h):
    body = '{"code": "AAA", "name": "A"}'
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "application/xml"):
        e = err(client.post(f"{API}/branches", headers={**admin_h, "Content-Type": ctype}, content=body), 422, "VALIDATION_ERROR")
        assert e["details"]["fields"]
    r = client.post(f"{API}/branches", headers={**admin_h, "Content-Type": "application/json; charset=utf-8"}, content=body)
    assert r.status_code == 201


def test_non_json_content_type_on_login_and_import(client, admin_h):
    err(client.post(f"{API}/auth/login", content='{"email": "a@b.cd", "password": "x"}',
                    headers={"Content-Type": "text/plain"}), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/import", content="{}", headers={**admin_h, "Content-Type": "text/plain"}), 422, "VALIDATION_ERROR")


def test_malformed_json_names_body(client, admin_h):
    e = err(client.post(f"{API}/branches", headers={**admin_h, "Content-Type": "application/json"}, content="{bad"),
            422, "VALIDATION_ERROR")
    assert e["details"]["fields"][0]["field"] == "body"


def test_authentication_comes_before_validation(client):
    err(client.post(f"{API}/branches", headers={"Content-Type": "text/plain"}, content="x"), 401, "UNAUTHENTICATED")
    err(client.get(f"{API}/books/0"), 401, "UNAUTHENTICATED")


def test_null_fields_are_included(client, lib):
    book = mk_book(client, lib, 0)
    body = client.get(f"{API}/books/{book}", headers=lib).json()
    assert "subtitle" in body and body["subtitle"] is None
    m = mk_member(client, lib)
    assert client.get(f"{API}/members/{m}", headers=lib).json()["phone"] is None


def test_every_error_has_the_common_body(client, admin_h):
    for r in (
        client.get(f"{API}/books/99", headers=admin_h),
        client.get(f"{API}/books", headers=admin_h, params={"page": 0}),
        client.get(f"{API}/books", headers=admin_h, params={"page_size": 101}),
        client.get(f"{API}/branches"),
        client.get(f"{API}/audit-log", headers={"Authorization": "Bearer nope"}),
    ):
        body = r.json()
        assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}


def test_notification_id_must_be_positive(client, lib):
    mk_member(client, lib)
    err(client.post(f"{API}/notifications/0/read", headers=member_h(client)), 422, "VALIDATION_ERROR")
    err(client.post(f"{API}/notifications/abc/read", headers=member_h(client)), 422, "VALIDATION_ERROR")
