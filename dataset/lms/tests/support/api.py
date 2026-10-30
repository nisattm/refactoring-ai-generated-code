"""Helper functions for the LMS tests.

Contract (names and signatures fixed): ../README.md, "Fixture and helper contract".
Every helper takes ``expect`` (the success status by default), asserts the status code
and returns the parsed JSON body (or a header dict). With an error status the error body
is returned, so ``error_code`` can be checked.

Paths, request fields and status codes come from ../../requirements.md.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

BASE = "/api/v1"

# Unique values within one test run (each test has its own empty database).
_seq = itertools.count(1)


def _next() -> int:
    return next(_seq)


def _check(response, expect: int):
    assert response.status_code == expect, (
        f"{response.request.method} {response.request.url.path}: "
        f"expected {expect}, got {response.status_code}: {response.text[:500]}"
    )
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def post(client, path: str, headers: dict | None, body: dict | None = None, *, expect: int):
    """POST ``body`` as JSON and check the status (used by fixtures and tests)."""
    return _check(client.post(path, json=body, headers=headers or {}), expect)


def get(client, path: str, headers: dict | None, *, params: dict | None = None, expect: int = 200):
    return _check(client.get(path, params=params, headers=headers or {}), expect)


def patch(client, path: str, headers: dict | None, body: dict, *, expect: int = 200):
    return _check(client.patch(path, json=body, headers=headers or {}), expect)


# --- Identity (LIB-AUTH-06) ---------------------------------------------------------

def login(client, email: str, password: str, expect: int = 200) -> dict[str, str]:
    body = post(client, f"{BASE}/auth/login", None, {"email": email, "password": password}, expect=expect)
    if expect != 200:
        return body
    return {"Authorization": f"Bearer {body['access_token']}"}


# --- Branches (LIB-BR-01) ---------------------------------------------------------------

def create_branch(client, headers, code: str, name: str | None = None, expect: int = 201):
    body = {"code": code, "name": name or f"Branch {code}", "address": ""}
    return post(client, f"{BASE}/branches", headers, body, expect=expect)


# --- Members (LIB-MEM-01, LIB-MEM-02) ---------------------------------------------------

def register_member(client, headers, *, home_branch_id: int, membership_type: str = "student",
                    email: str | None = None, password: str = "Member1234", expect: int = 201,
                    **fields: Any):
    """Register a member. Generates a unique e-mail and, for non-guests, a unique
    ``university_id`` (4–20 alphanumeric); for guests a phone number (12 digits)."""
    n = _next()
    body: dict[str, Any] = {
        "full_name": f"Member {n}",
        "email": email or f"member{n}@example.edu.tr",
        "membership_type": membership_type,
        "home_branch_id": home_branch_id,
        "password": password,
    }
    if membership_type == "guest":
        body["phone"] = f"+90555{n:07d}"
    else:
        body["university_id"] = f"U{n:07d}"
    body.update(fields)
    return post(client, f"{BASE}/members", headers, body, expect=expect)


def member_headers(client, member: dict, password: str = "Member1234") -> dict[str, str]:
    return login(client, member["email"], password)


# --- Catalog (LIB-CAT-01, LIB-CAT-02, LIB-CAT-03, LIB-CAT-07) ---------------------------

def isbn13(number: int) -> str:
    """Valid ISBN-13: 978 + 9 digits + check digit (weights 1, 3, 1, 3, …)."""
    body = f"978{number % 10**9:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def create_book(client, headers, *, title: str = "Book", isbn: str | None = None,
                expect: int = 201, **fields: Any):
    """Create a book. Creates an author and a publisher unless ``author_ids`` /
    ``publisher_id`` are given; generates a unique valid ISBN-13 unless ``isbn`` is given."""
    n = _next()
    if "author_ids" not in fields:
        author = post(client, f"{BASE}/authors", headers, {"name": f"Author {n}"}, expect=201)
        fields["author_ids"] = [author["id"]]
    if "publisher_id" not in fields:
        publisher = post(client, f"{BASE}/publishers", headers, {"name": f"Publisher {n}"}, expect=201)
        fields["publisher_id"] = publisher["id"]
    body: dict[str, Any] = {
        "isbn": isbn or isbn13(n),
        "title": title,
        "subtitle": None,
        "publication_year": 2020,
        "language": "tr",
        "classification": "813",
    }
    body.update(fields)
    return post(client, f"{BASE}/books", headers, body, expect=expect)


def add_copy(client, headers, book_id: int, *, home_branch_id: int, price: str = "100.00",
             barcode: str | None = None, expect: int = 201):
    """Add a copy with a unique barcode. ``acquired_on`` is 2025-01-01 (contract), so it is
    never after "today" even when a test moves the clock back to 2026."""
    body = {
        "barcode": barcode or f"C{_next():06d}",
        "home_branch_id": home_branch_id,
        "price": price,
        "acquired_on": "2025-01-01",
        "shelf_location": None,
    }
    return post(client, f"{BASE}/books/{book_id}/copies", headers, body, expect=expect)


# --- Loans (LIB-LOAN-01, LIB-LOAN-09) ---------------------------------------------------

def lend(client, headers, member_id: int, copy_id: int, expect: int = 201):
    return post(client, f"{BASE}/loans", headers, {"member_id": member_id, "copy_id": copy_id}, expect=expect)


def return_loan(client, headers, loan_id: int, *, branch_id: int, condition: str = "good",
                damage_fee: str | None = None, expect: int = 200):
    body: dict[str, Any] = {"branch_id": branch_id, "condition": condition}
    if damage_fee is not None:
        body["damage_fee"] = damage_fee
    return post(client, f"{BASE}/loans/{loan_id}/return", headers, body, expect=expect)


# --- Reservations (LIB-RES-01) ----------------------------------------------------------

def reserve(client, headers, *, book_id: int, pickup_branch_id: int, member_id: int | None = None,
            expect: int = 201):
    body: dict[str, Any] = {"book_id": book_id, "pickup_branch_id": pickup_branch_id}
    if member_id is not None:
        body["member_id"] = member_id
    return post(client, f"{BASE}/reservations", headers, body, expect=expect)


# --- Small helpers ----------------------------------------------------------------------

def error_code(response) -> str:
    """Error code of an error response (LIB-COM-25). Accepts a response or a parsed body."""
    body = response if isinstance(response, dict) else response.json()
    return body["error"]["code"]


def D(value) -> Decimal:
    return Decimal(str(value))


# --- Additional helpers (not part of the fixed contract; may be extended) ---------------

LOCAL_TZ = timezone(timedelta(hours=3))  # LIB-COM-01


def set_today(clock, day: str, hour: int = 9, minute: int = 0) -> None:
    """Set the FixedClock to ``day`` (YYYY-MM-DD) at ``hour:minute`` local time."""
    clock.set(datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=LOCAL_TZ))


def items(page: dict) -> list:
    """Items of a paginated response (LIB-COM-19)."""
    return page["items"]


def get_loan(client, headers, loan_id: int, expect: int = 200):
    return get(client, f"{BASE}/loans/{loan_id}", headers, expect=expect)


def get_copy(client, headers, copy_id: int, expect: int = 200):
    return get(client, f"{BASE}/copies/{copy_id}", headers, expect=expect)


def get_reservation(client, headers, reservation_id: int, expect: int = 200):
    return get(client, f"{BASE}/reservations/{reservation_id}", headers, expect=expect)


def renew(client, headers, loan_id: int, expect: int = 200):
    return post(client, f"{BASE}/loans/{loan_id}/renew", headers, None, expect=expect)


def report_lost(client, headers, loan_id: int, expect: int = 200):
    return post(client, f"{BASE}/loans/{loan_id}/report-lost", headers, None, expect=expect)


def deactivate_member(client, headers, member_id: int, expect: int = 200):
    return post(client, f"{BASE}/members/{member_id}/deactivate", headers, None, expect=expect)


def update_member(client, headers, member_id: int, expect: int = 200, **fields: Any):
    return patch(client, f"{BASE}/members/{member_id}", headers, fields, expect=expect)


def deactivate_branch(client, admin_headers, branch_id: int, expect: int = 200):
    return patch(client, f"{BASE}/branches/{branch_id}", admin_headers, {"is_active": False}, expect=expect)


def balance(client, headers, member_id: int, expect: int = 200):
    return get(client, f"{BASE}/members/{member_id}/balance", headers, expect=expect)


def member_fees(client, headers, member_id: int, expect: int = 200, **params: Any):
    return get(client, f"{BASE}/members/{member_id}/fees", headers, params=params or None, expect=expect)


def pay(client, headers, member_id: int, amount, method: str = "cash", expect: int = 201):
    body = {"amount": amount, "method": method}
    return post(client, f"{BASE}/members/{member_id}/payments", headers, body, expect=expect)


def waive(client, headers, fee_id: int, reason: str = "Waived in test", expect: int = 200):
    return post(client, f"{BASE}/fees/{fee_id}/waive", headers, {"reason": reason}, expect=expect)


def new_copy(client, headers, *, branch_id: int, price: str = "100.00", title: str = "Book") -> tuple[dict, dict]:
    """A new book with one copy at ``branch_id``. Returns ``(book, copy)``."""
    book = create_book(client, headers, title=title)
    return book, add_copy(client, headers, book["id"], home_branch_id=branch_id, price=price)


def new_loan(client, headers, *, branch_id: int, member: dict | None = None,
             membership_type: str = "student", price: str = "100.00") -> dict:
    """Register a member (unless given), create a book with one copy at ``branch_id`` and
    lend it. Returns ``{"member", "book", "copy", "loan"}``."""
    member = member or register_member(client, headers, home_branch_id=branch_id,
                                       membership_type=membership_type)
    book, copy = new_copy(client, headers, branch_id=branch_id, price=price)
    loan = lend(client, headers, member["id"], copy["id"])
    return {"member": member, "book": book, "copy": copy, "loan": loan}
