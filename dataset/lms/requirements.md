# Library Management System – Requirements

**Status:** Complete draft (sections 1–22), revised after team review.
**Version:** 0.5 · 2026-10-30

This document specifies a Library Management System (LMS) for a university library with several branches. It is the only specification used to build the system. Tests are written from this document before the code exists, so every name, path, field, status code and error code given here is binding.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Each testable requirement has an ID of the form `LIB-<AREA>-NN`.

---

## 1. Purpose and scope

### 1.1 System overview

The LMS manages a university library: members and their memberships, the catalog of books and physical copies, loans and returns, reservations, late fees and payments, notifications, search, reports, multiple branches with transfers between them, purchasing, an audit log, and import/export of data. It is used through a REST API.

The system consists of 14 modules:

| # | Module | Package | Section |
| --- | --- | --- | --- |
| 1 | Core | `lms.core` | 5 |
| 2 | Identity and access | `lms.auth` | 6 |
| 3 | Members | `lms.members` | 7 |
| 4 | Catalog | `lms.catalog` | 8 |
| 5 | Loans and returns | `lms.loans` | 9 |
| 6 | Reservations | `lms.reservations` | 10 |
| 7 | Fines and payments | `lms.fines` | 11 |
| 8 | Notifications | `lms.notifications` | 14 |
| 9 | Search | `lms.search` | 15 |
| 10 | Reports | `lms.reports` | 16 |
| 11 | Branches | `lms.branches` | 17 |
| 12 | Purchasing | `lms.purchasing` | 18 |
| 13 | Audit log and import/export | `lms.audit` | 19 |
| 14 | API layer | `lms.api` | 20 (endpoints are listed with each module) |

### 1.2 Out of scope

- No graphical user interface. All functions are available through the REST API.
- No e-mail, SMS or push delivery. Notifications are stored records only (module 8).
- No payment gateway. Payments are recorded by a librarian (module 7).
- No multi-process or concurrent-writer operation. One server process uses one SQLite database file.
- No database migrations. The schema is created at start-up.

### 1.3 Users and roles

| Role | Who | Summary of rights |
| --- | --- | --- |
| `member` | A person registered as a library member (student, academic, staff or guest) | Reads the catalog, manages own reservations, sees own loans, fees and notifications |
| `librarian` | Library employee | Runs daily operations: members, loans, returns, reservations, payments, transfers, purchasing |
| `admin` | System administrator | Everything a librarian can do, plus user management, settings-level data and the audit log |

The full permission matrix is in section 6.6.

---

## 2. Technical constraints

### 2.1 Platform and dependencies

| ID | Requirement |
| --- | --- |
| LIB-TECH-01 | The system MUST run on Python 3.14. |
| LIB-TECH-02 | The only third-party runtime packages allowed are FastAPI, Uvicorn, Pydantic v2 and SQLAlchemy 2.x. Everything else MUST come from the Python standard library. |
| LIB-TECH-03 | The only third-party test packages allowed are pytest, httpx and Hypothesis. |
| LIB-TECH-04 | All packages MUST be pinned in `requirements.txt` at the repository root to exactly these versions: `fastapi==0.162.0`, `uvicorn==0.54.0`, `pydantic==2.14.2`, `sqlalchemy==2.1.6`, `httpx==0.28.1`, `pytest==9.2.0`, `hypothesis==6.170.13`. Packages these depend on may be added with exact versions. |
| LIB-TECH-05 | Data MUST be stored in one SQLite database. The location is given by `Settings.database_url` (section 4.2). |
| LIB-TECH-06 | Database access MUST use the SQLAlchemy 2.x ORM in synchronous mode (`Session`, not `AsyncSession`). API endpoints MUST be synchronous (`def`, not `async def`). |
| LIB-TECH-07 | The database schema MUST be created at application start-up if the tables do not exist. No migration tool is used. |
| LIB-TECH-08 | Every HTTP request that changes data MUST run in one database transaction. If the request fails with any error response, no change from that request may remain in the database. **Exception:** a failed login keeps its changes to `failed_login_count` and `locked_until` (LIB-AUTH-09, LIB-AUTH-10) and its audit entry (LIB-AUD-01), although it returns an error. |
| LIB-TECH-09 | The system MUST NOT read the system clock directly anywhere except in `SystemClock` (section 4.3). All dates and times come from the clock in `Settings`. |
| LIB-TECH-10 | The system MUST NOT use random values except for session tokens and password salts (section 6). Every list returned by the API MUST have a defined order. |

### 2.2 Package layout

The code MUST be organized as follows. The internal structure of each module package (files, classes, functions) is not prescribed.

```
requirements.txt
lms/
├── __init__.py          Fixed service interface (section 4)
├── core/                Module 1
├── auth/                Module 2
├── members/             Module 3
├── catalog/             Module 4
├── loans/               Module 5
├── reservations/        Module 6
├── fines/               Module 7
├── notifications/       Module 8
├── search/              Module 9
├── reports/             Module 10
├── branches/            Module 11
├── purchasing/          Module 12
├── audit/               Module 13
└── api/                 Module 14 (FastAPI routers and request/response schemas)
```

| ID | Requirement |
| --- | --- |
| LIB-TECH-11 | Each module MUST live in its own package as shown above. |
| LIB-TECH-12 | The application MUST start with `uvicorn "lms:create_app" --factory`, using default `Settings`. |

---

## 3. Common rules

These rules apply to all modules.

### 3.1 Time and time zone

| ID | Requirement |
| --- | --- |
| LIB-COM-01 | The library operates in Türkiye. The local time zone is the fixed offset UTC+03:00 with no daylight saving time, independent of the operating system's time-zone settings. |
| LIB-COM-02 | "Today" is the local date of `Settings.clock.now()`. All date rules (loan periods, due dates, late days, reservation hold periods, transfers, reports) use this date. |
| LIB-COM-03 | Date-times MUST be stored and returned with their UTC offset. The API returns them in local time as ISO 8601 strings with offset, for example `"2026-11-02T09:30:00+03:00"`. |
| LIB-COM-04 | Dates MUST be returned as `"YYYY-MM-DD"`. A date or date-time in a request that cannot be parsed MUST be rejected with `422 VALIDATION_ERROR`. A request date-time without an offset MUST be rejected. |

### 3.2 Working days and official holidays

| ID | Requirement |
| --- | --- |
| LIB-COM-05 | A **working day** is a date that is not a Saturday, not a Sunday, and not in the official holiday list (`Settings.holidays`). |
| LIB-COM-06 | The default holiday list is the table below (2026–2027). Half-day holiday eves (*arife*: 19 Mar 2026, 26 May 2026, 28 Oct 2026, 8 Mar 2027, 15 May 2027, 28 Oct 2027) are **working days**. |
| LIB-COM-07 | For dates outside the years in the holiday list, only Saturdays and Sundays are non-working days. |
| LIB-COM-08 | **Next working day on or after a date** `d`: `d` itself if `d` is a working day; otherwise the first working day after `d`. |
| LIB-COM-09 | **Adding n working days** to a date `d` (n ≥ 1): move forward day by day from the day after `d` and count only working days; the result is the date on which the count reaches n. `d` itself is never counted. |
| LIB-COM-10 | **Working days between** two dates `a` and `b` (`a` < `b`): the number of working days `x` with `a` < `x` ≤ `b`. If `b` ≤ `a`, the result is 0. |

Default official holidays (`Settings.holidays`):

| Date | Day | Holiday |
| --- | --- | --- |
| 2026-01-01 | Thu | New Year's Day |
| 2026-03-20 | Fri | Ramazan Bayramı, day 1 |
| 2026-03-21 | Sat | Ramazan Bayramı, day 2 |
| 2026-03-22 | Sun | Ramazan Bayramı, day 3 |
| 2026-04-23 | Thu | National Sovereignty and Children's Day |
| 2026-05-01 | Fri | Labour and Solidarity Day |
| 2026-05-19 | Tue | Commemoration of Atatürk, Youth and Sports Day |
| 2026-05-27 | Wed | Kurban Bayramı, day 1 |
| 2026-05-28 | Thu | Kurban Bayramı, day 2 |
| 2026-05-29 | Fri | Kurban Bayramı, day 3 |
| 2026-05-30 | Sat | Kurban Bayramı, day 4 |
| 2026-07-15 | Wed | Democracy and National Unity Day |
| 2026-08-30 | Sun | Victory Day |
| 2026-10-29 | Thu | Republic Day |
| 2027-01-01 | Fri | New Year's Day |
| 2027-03-09 | Tue | Ramazan Bayramı, day 1 |
| 2027-03-10 | Wed | Ramazan Bayramı, day 2 |
| 2027-03-11 | Thu | Ramazan Bayramı, day 3 |
| 2027-04-23 | Fri | National Sovereignty and Children's Day |
| 2027-05-01 | Sat | Labour and Solidarity Day |
| 2027-05-16 | Sun | Kurban Bayramı, day 1 |
| 2027-05-17 | Mon | Kurban Bayramı, day 2 |
| 2027-05-18 | Tue | Kurban Bayramı, day 3 |
| 2027-05-19 | Wed | Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day |
| 2027-07-15 | Thu | Democracy and National Unity Day |
| 2027-08-30 | Mon | Victory Day |
| 2027-10-29 | Fri | Republic Day |

Worked examples (with the default list):

| Rule | Input | Result |
| --- | --- | --- |
| LIB-COM-08 | 2026-05-27 (holiday) | 2026-06-01 (27–30 May holidays, 31 May Sunday) |
| LIB-COM-08 | 2026-03-24 (Tuesday) | 2026-03-24 |
| LIB-COM-08 | 2027-01-01 (holiday) | 2027-01-04 |
| LIB-COM-09 | 2026-10-28 + 2 working days | 2026-11-02 (29 Oct holiday, 31 Oct–1 Nov weekend) |
| LIB-COM-09 | 2026-05-26 + 2 working days | 2026-06-02 |
| LIB-COM-10 | 2026-06-01 → 2026-06-05 | 4 |
| LIB-COM-10 | 2026-10-23 (Fri) → 2026-10-26 (Mon) | 1 |
| LIB-COM-10 | 2026-10-27 → 2026-10-30 | 2 (28 Oct is a working day; 29 Oct is a holiday) |

### 3.3 Money

| ID | Requirement |
| --- | --- |
| LIB-COM-11 | All amounts are in Turkish lira (TRY). Amounts MUST be represented with `decimal.Decimal`, never `float`, in calculations and in storage. |
| LIB-COM-12 | Amounts have exactly two decimal places. When a calculation produces more, it MUST be rounded to two places with `ROUND_HALF_UP`. |
| LIB-COM-13 | The API MUST send amounts as JSON strings with exactly two decimal places, for example `"12.50"`, `"0.00"`. The API MUST accept amounts as strings with at most two decimal places; a number, a negative amount where not allowed, or more than two decimal places MUST be rejected with `422 VALIDATION_ERROR`. |

### 3.4 Identifiers and text

| ID | Requirement |
| --- | --- |
| LIB-COM-14 | Every stored entity has an integer `id` that is assigned by the database, starts at 1 and is never reused. |
| LIB-COM-15 | Text fields are trimmed of leading and trailing white space before validation and storage. A required text field that is empty after trimming MUST be rejected with `422 VALIDATION_ERROR`. |
| LIB-COM-16 | Unless a module says otherwise, names (person names, titles, organization names) are 1–200 characters after trimming, and free-text notes are 0–1000 characters. |
| LIB-COM-17 | E-mail addresses are stored in lower case (`str.lower()`) and returned as stored; comparisons for uniqueness and login use LIB-COM-30. An e-mail address MUST contain exactly one `@` with at least one character before it and a domain containing a dot after it; otherwise `422 VALIDATION_ERROR`. |

### 3.5 Pagination and ordering

| ID | Requirement |
| --- | --- |
| LIB-COM-18 | Every endpoint that returns a list MUST be paginated with query parameters `page` (integer ≥ 1, default 1) and `page_size` (integer 1–100, default 20). Values outside these ranges MUST be rejected with `422 VALIDATION_ERROR`. **Exceptions** (not paginated): `GET /api/v1/calendar/holidays`, `GET /api/v1/reports/most-borrowed` (uses `limit`), `GET /api/v1/reports/inventory`, every response with `format=csv`, and the export endpoints. |
| LIB-COM-19 | A paginated response has this body: `{"items": [...], "page": 1, "page_size": 20, "total": 57}`. `total` is the number of matching items across all pages. A page beyond the last page returns `"items": []` with status 200. |
| LIB-COM-20 | Unless an endpoint defines another order, list items are ordered by `id` ascending. |

### 3.6 API conventions

| ID | Requirement |
| --- | --- |
| LIB-COM-21 | All endpoints are under the base path `/api/v1`, except `GET /health` and the OpenAPI document `GET /openapi.json` (LIB-API-04). Request and response bodies are JSON with `snake_case` field names. |
| LIB-COM-22 | Successful creation returns `201` with the created resource. Successful update returns `200` with the updated resource. Successful actions without a body return `204`. |
| LIB-COM-23 | Unknown fields in a request body MUST be rejected with `422 VALIDATION_ERROR`. |
| LIB-COM-24 | An endpoint that needs authentication reads the token from the header `Authorization: Bearer <token>` (section 6.3). |

### 3.7 Errors

| ID | Requirement |
| --- | --- |
| LIB-COM-25 | Every error response MUST have this body: `{"error": {"code": "<ERROR_CODE>", "message": "<human-readable text>", "details": {...}}}`. `details` is an object and MAY be empty. |
| LIB-COM-26 | For `422 VALIDATION_ERROR`, `details` MUST contain `"fields"`: a list of `{"field": "<name or dotted path>", "problem": "<text>"}`, one entry per invalid field. This replaces FastAPI's default validation response. |
| LIB-COM-27 | An unexpected internal error MUST return `500 INTERNAL_ERROR` with a generic message. Stack traces and internal details MUST NOT appear in the response. |
| LIB-COM-28 | When a request violates several rules, the first failing check in this order decides the response: (1) authentication, 401; (2) role permission (section 6.6), 403; (3) validation, 422; (4) existence of the addressed resource, 404; (5) ownership for `member` users (LIB-AUTH-25), 403; (6) state and business rules, 409. Validation (3) covers only checks on the request itself. A check that compares the request with stored data is a business rule (6) and returns `409` with a specific code. The only exception is a reference to an entity that does not exist, which returns `404 NOT_FOUND` at step (4) (LIB-COM-29, LIB-LOAN-01, LIB-PUR-06). |
| LIB-COM-29 | An id in a request body or query that refers to an entity that does not exist (for example `member_id`, `branch_id`, `book_id`) MUST be rejected with `404 NOT_FOUND` and `details` `{"field": "<name>", "id": <value>}`. |
| LIB-COM-30 | **Case-insensitive** comparison and ordering anywhere in this document use the normalization of LIB-SRCH-01: `İ`, `I` and `ı` become `i`, then `str.casefold()` is applied. This applies to uniqueness of e-mail addresses, names and codes, to `q` filters, and to ordering by names or titles. |

Common error codes (modules add their own codes in their sections):

| HTTP status | Code | When |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | No token, unknown token or revoked token |
| 401 | `TOKEN_EXPIRED` | Token is past its expiry time |
| 401 | `INVALID_CREDENTIALS` | Wrong e-mail or password at login |
| 403 | `FORBIDDEN` | The user's role or ownership does not allow the action |
| 403 | `ACCOUNT_DISABLED` | The user account is inactive |
| 403 | `ACCOUNT_LOCKED` | Too many failed logins (LIB-AUTH-09) |
| 404 | `NOT_FOUND` | The addressed resource does not exist |
| 409 | `CONFLICT` | A uniqueness constraint would be violated (for example a duplicate e-mail) |
| 409 | `BUSINESS_RULE_VIOLATION` | Generic business-rule failure; modules use more specific codes where listed |
| 422 | `VALIDATION_ERROR` | Malformed or invalid input |
| 500 | `INTERNAL_ERROR` | Unexpected failure |

---

## 4. Fixed service interface

The package `lms` MUST export exactly the names below from `lms/__init__.py`. Tests use them directly. Their names, parameters, defaults and behavior MUST NOT change. Two further functions, `import_dataset` and `export_dataset`, are specified in section 19.4.

### 4.1 `create_app`

```python
def create_app(settings: Settings | None = None) -> fastapi.FastAPI: ...
```

| ID | Requirement |
| --- | --- |
| LIB-IF-01 | `create_app` returns a new FastAPI application. With `settings=None` it uses `Settings()`. |
| LIB-IF-02 | On creation it MUST create the database schema if needed (LIB-TECH-07) and create the bootstrap administrator (LIB-AUTH-01). Calling it twice on the same database MUST NOT fail and MUST NOT create a second bootstrap administrator. |
| LIB-IF-03 | Two applications created with different `database_url` values MUST NOT share any state. |

### 4.2 `Settings`

```python
@dataclasses.dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./lms.db"
    clock: Clock = SystemClock()
    holidays: frozenset[datetime.date] = DEFAULT_HOLIDAYS
    bootstrap_admin_email: str = "admin@library.local"
    bootstrap_admin_password: str = "ChangeMe123"
    token_ttl_hours: int = 12
```

| ID | Requirement |
| --- | --- |
| LIB-IF-04 | `DEFAULT_HOLIDAYS` is the holiday table in section 3.2 and MUST also be exported from `lms`. |
| LIB-IF-05 | `database_url` accepts any SQLAlchemy SQLite URL, including `"sqlite://"` (in-memory). With an in-memory database, all requests of one application MUST see the same data. |
| LIB-IF-06 | `token_ttl_hours` MUST be between 1 and 168; otherwise creating `Settings` raises `ValueError`. |

### 4.3 `Clock`, `SystemClock`, `FixedClock`

```python
class Clock(typing.Protocol):
    def now(self) -> datetime.datetime: ...   # timezone-aware

class SystemClock:
    def now(self) -> datetime.datetime: ...

class FixedClock:
    def __init__(self, now: datetime.datetime) -> None: ...
    def now(self) -> datetime.datetime: ...
    def set(self, now: datetime.datetime) -> None: ...
    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None: ...
```

| ID | Requirement |
| --- | --- |
| LIB-IF-07 | `SystemClock.now()` returns the current time in local time (UTC+03:00). |
| LIB-IF-08 | `FixedClock.now()` returns the time it was given until `set` or `advance` changes it. `FixedClock` and `set` MUST raise `ValueError` for a naive `datetime` (no time zone). |
| LIB-IF-09 | A change made with `set` or `advance` MUST be visible to the next request of an application that was created with that clock, without restarting the application. |

### 4.4 Health endpoint

| ID | Requirement |
| --- | --- |
| LIB-IF-10 | `GET /health` needs no authentication and returns `200` with `{"status": "ok", "today": "YYYY-MM-DD"}`, where `today` follows LIB-COM-02. |

---

## 5. Module 1: Core

Module 1 provides the working-day calendar and the shared rules for money, errors and pagination that every module follows.

### 5.1 Calendar endpoints

The calendar is public: these endpoints need no authentication.

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/calendar/holidays?year=YYYY` | Official holidays of a year |
| `GET /api/v1/calendar/days/{date}` | Whether a date is a working day |
| `GET /api/v1/calendar/next-working-day?date=YYYY-MM-DD` | LIB-COM-08 |
| `GET /api/v1/calendar/add-working-days?date=YYYY-MM-DD&days=N` | LIB-COM-09 |
| `GET /api/v1/calendar/working-days-between?start=YYYY-MM-DD&end=YYYY-MM-DD` | LIB-COM-10 |

| ID | Requirement |
| --- | --- |
| LIB-CORE-01 | `GET /api/v1/calendar/holidays?year=2026` returns `200` with `{"year": 2026, "holidays": [{"date": "2026-01-01", "name": "New Year's Day"}, ...]}`, ordered by date. A year with no entries returns an empty list. `year` MUST be 1900–2100; otherwise `422 VALIDATION_ERROR`. |
| LIB-CORE-02 | `GET /api/v1/calendar/days/2026-10-29` returns `200` with `{"date": "2026-10-29", "working_day": false, "reason": "holiday"}`. `reason` is `"weekend"`, `"holiday"` or `null` (for a working day). A date that is both a weekend and a holiday has reason `"holiday"`. |
| LIB-CORE-03 | `GET /api/v1/calendar/next-working-day?date=2026-05-27` returns `200` with `{"date": "2026-06-01"}`. |
| LIB-CORE-04 | `GET /api/v1/calendar/add-working-days?date=2026-10-28&days=2` returns `200` with `{"date": "2026-11-02"}`. `days` MUST be 1–365; otherwise `422 VALIDATION_ERROR`. |
| LIB-CORE-05 | `GET /api/v1/calendar/working-days-between?start=2026-06-01&end=2026-06-05` returns `200` with `{"working_days": 4}`. If `end` ≤ `start`, the result is `0`. If `end` − `start` is more than 3660 days, the response is `422 VALIDATION_ERROR`. |
| LIB-CORE-06 | Missing or unparseable date parameters on these endpoints return `422 VALIDATION_ERROR` with the parameter named in `details.fields`. |

### 5.2 Shared behavior

| ID | Requirement |
| --- | --- |
| LIB-CORE-07 | Working-day calculations in every module MUST give the same results as the calendar endpoints for the same inputs and the same `Settings.holidays`. |
| LIB-CORE-08 | Money rounding (LIB-COM-12) MUST be applied to the final result of a calculation, not to its intermediate steps. Example: an amount of 0.125 TL is stored as `"0.13"`. |
| LIB-CORE-09 | Every error response of every module MUST follow LIB-COM-25 to LIB-COM-28. |
| LIB-CORE-10 | Pagination of every list endpoint MUST follow LIB-COM-18 to LIB-COM-20. |

### 5.3 Data

The core module stores no entities of its own. The holiday list comes from `Settings.holidays` and is not stored in the database.

---

## 6. Module 2: Identity and access

This module manages user accounts, login, sessions and permissions.

### 6.1 Data

**User**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `email` | text | Unique (case-insensitive), LIB-COM-17, at most 254 characters |
| `full_name` | text | LIB-COM-16 |
| `role` | `member` \| `librarian` \| `admin` | Required |
| `password_hash` | text | Never returned by the API |
| `is_active` | boolean | Default `true` |
| `failed_login_count` | integer | Consecutive failed logins, default 0 |
| `locked_until` | date-time or null | See LIB-AUTH-09 |
| `member_id` | integer or null | Set only for role `member`; links to the member record (module 3, section 7) |
| `created_at` | date-time | Set from the clock at creation |
| `last_login_at` | date-time or null | Set at each successful login |

**Session**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `user_id` | integer | Owner |
| `token_hash` | text | SHA-256 hex digest of the token; the token itself is never stored |
| `created_at` | date-time | From the clock |
| `expires_at` | date-time | `created_at` + `Settings.token_ttl_hours` |
| `revoked_at` | date-time or null | Set at logout or revocation |

API representation of a user (`UserOut`): `{"id", "email", "full_name", "role", "is_active", "member_id", "created_at", "last_login_at"}`.

### 6.2 Accounts and passwords

| ID | Requirement |
| --- | --- |
| LIB-AUTH-01 | **Bootstrap administrator.** When the application is created and no user with role `admin` exists, the system MUST create one active `admin` user with `Settings.bootstrap_admin_email`, full name `"Administrator"` and `Settings.bootstrap_admin_password`. |
| LIB-AUTH-02 | **Password policy.** A password MUST be 8–128 characters long and contain at least one letter and at least one digit. A password that breaks the policy MUST be rejected with `422 VALIDATION_ERROR` (field `password` or `new_password`). |
| LIB-AUTH-03 | **Password storage.** Passwords MUST be stored as `scrypt$<salt hex>$<hash hex>`, where the hash is scrypt of the UTF-8 password with n = 16384, r = 8, p = 1 and a 64-byte output, and the salt is 16 random bytes. |
| LIB-AUTH-04 | Users with role `member` are created only by member registration (module 3, section 7). `POST /api/v1/users` MUST reject `role: "member"` with `422 VALIDATION_ERROR`. |
| LIB-AUTH-05 | The e-mail address of a user MUST be unique among all users. A duplicate MUST be rejected with `409 CONFLICT`. |

### 6.3 Login, sessions and tokens

| ID | Requirement |
| --- | --- |
| LIB-AUTH-06 | **Login.** `POST /api/v1/auth/login` with `{"email": "...", "password": "..."}` returns `200` with `{"access_token": "<token>", "token_type": "bearer", "expires_at": "<date-time>", "user": UserOut}` for valid credentials of an active, unlocked user. |
| LIB-AUTH-07 | **Token.** The token MUST be a random URL-safe string of 43 characters (32 random bytes, base64url without padding). Only its SHA-256 hex digest is stored (Session). Each login creates a new session; earlier sessions of the user stay valid. |
| LIB-AUTH-08 | **Wrong credentials.** An unknown e-mail and a wrong password MUST give the same response: `401 INVALID_CREDENTIALS` with the same message. |
| LIB-AUTH-09 | **Lockout.** Each failed login for an existing user increases `failed_login_count` by 1. When it reaches 5, `locked_until` is set to now + 15 minutes and `failed_login_count` is reset to 0. While now < `locked_until`, every login for that user returns `403 ACCOUNT_LOCKED` with `details.locked_until`, even with the correct password, and does not count as a failure. A successful login resets `failed_login_count` to 0. |
| LIB-AUTH-10 | **Disabled account.** Login of an inactive user with the correct password returns `403 ACCOUNT_DISABLED` and does not change `failed_login_count`. With a wrong password it returns `401 INVALID_CREDENTIALS` and counts as a failure (LIB-AUTH-09). |
| LIB-AUTH-11 | **Login order.** Checks run in this order: e-mail exists → account locked → password correct → account active. |
| LIB-AUTH-12 | **Authenticated request.** A request with a token whose session exists, is not revoked and is not expired (now < `expires_at`) is authenticated as the session's user. Otherwise: missing header, malformed header, unknown token or revoked session → `401 UNAUTHENTICATED`; expired session → `401 TOKEN_EXPIRED`. (Sessions of a deactivated user are revoked by LIB-AUTH-21, so they return `401 UNAUTHENTICATED`.) |
| LIB-AUTH-13 | **Expiry boundary.** A session is expired when now ≥ `expires_at`. Example: `token_ttl_hours = 12`, login at 2026-11-02T09:00:00+03:00 → the token is valid at 20:59:59 and expired at 21:00:00. |
| LIB-AUTH-14 | **Logout.** `POST /api/v1/auth/logout` revokes the session of the token used and returns `204`. Using the same token afterwards returns `401 UNAUTHENTICATED`. |
| LIB-AUTH-15 | **Current user.** `GET /api/v1/auth/me` returns `200` with `UserOut` of the authenticated user. |
| LIB-AUTH-16 | **Change own password.** `POST /api/v1/auth/change-password` with `{"current_password": "...", "new_password": "..."}` returns `204`. Checks in order: `new_password` breaks LIB-AUTH-02 → `422 VALIDATION_ERROR`; wrong `current_password` → `401 INVALID_CREDENTIALS` (does not count toward lockout); `new_password` equal to the current password → `409 PASSWORD_UNCHANGED`. After a change, all other sessions of the user are revoked; the session used for the request stays valid. |

### 6.4 User management (admin)

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/users` | Create a librarian or admin |
| `GET /api/v1/users` | List users |
| `GET /api/v1/users/{user_id}` | Get one user |
| `PATCH /api/v1/users/{user_id}` | Change name, role or active state |
| `POST /api/v1/users/{user_id}/reset-password` | Set a new password |

| ID | Requirement |
| --- | --- |
| LIB-AUTH-17 | `POST /api/v1/users` with `{"email", "full_name", "role", "password"}` (role `librarian` or `admin`) returns `201` with `UserOut`. Only `admin` may call it. |
| LIB-AUTH-18 | `GET /api/v1/users` returns a paginated list of `UserOut`, ordered by `id`. Optional filters: `role` (one of the three roles), `is_active` (`true`/`false`), `q` (case-insensitive substring of `email` or `full_name`). Only `admin` may call it. |
| LIB-AUTH-19 | `GET /api/v1/users/{user_id}` returns `UserOut`. An `admin` may read any user; an unknown id returns `404 NOT_FOUND`. Any other user may read only their own record; for them every other id returns `403 FORBIDDEN`, whether or not it exists. For non-admins this ownership check is an exception to LIB-COM-28: it comes before the existence check. |
| LIB-AUTH-20 | `PATCH /api/v1/users/{user_id}` accepts any subset of `{"full_name", "role", "is_active"}` and returns `200` with `UserOut`. Only `admin` may call it. `role: "member"` in the request returns `422 VALIDATION_ERROR`. Changing the role of a user whose role is `member` returns `409 ROLE_CHANGE_NOT_ALLOWED`. |
| LIB-AUTH-21 | Setting `is_active` to `false` revokes all sessions of that user. Setting it to `true` also clears `locked_until` and `failed_login_count`. |
| LIB-AUTH-22 | **Last administrator.** A change that would leave no active `admin` (deactivating or demoting the last active admin) MUST be rejected with `409 LAST_ADMIN`. An admin MUST NOT deactivate their own account: `409 CANNOT_DEACTIVATE_SELF`. |
| LIB-AUTH-23 | `POST /api/v1/users/{user_id}/reset-password` with `{"new_password": "..."}` returns `204`. Only `admin` may call it. It revokes all sessions of that user and clears `locked_until` and `failed_login_count`. |

### 6.5 Error codes of this module

| HTTP status | Code | When |
| --- | --- | --- |
| 409 | `LAST_ADMIN` | LIB-AUTH-22 |
| 409 | `CANNOT_DEACTIVATE_SELF` | LIB-AUTH-22 |
| 409 | `PASSWORD_UNCHANGED` | LIB-AUTH-16 |
| 409 | `ROLE_CHANGE_NOT_ALLOWED` | LIB-AUTH-20 |

The common codes `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `ACCOUNT_DISABLED` and `ACCOUNT_LOCKED` (section 3.7) are raised by this module.

### 6.6 Permission matrix

Every endpoint MUST follow this matrix. "Own" means the resource belongs to the authenticated member (through `User.member_id`). Endpoint details are specified with each module; the module sections MUST follow this matrix.

| Area | Anonymous | `member` | `librarian` | `admin` |
| --- | --- | --- | --- | --- |
| Health and calendar (module 1) | Read | Read | Read | Read |
| Login (module 2) | Yes | Yes | Yes | Yes |
| Own account: me, logout, change password (module 2) | – | Yes | Yes | Yes |
| Own user record: `GET /api/v1/users/{own id}` (module 2) | – | Read | Read | Read |
| User management (module 2) | – | – | – | Full |
| Members (module 3) | – | Read own | Full | Full |
| Catalog: books, copies (module 4) | – | Read | Full | Full |
| Loans and returns (module 5) | – | Read own, renew own | Full | Full |
| Reservations (module 6) | – | Create, read, cancel own | Full | Full |
| Fines and payments (module 7) | – | Read own | Record payments, read all | Full, including waivers |
| Notifications (module 8) | – | Read own, mark own as read | Read all, run reminders | Read all, run reminders |
| Search (module 9) | – | Yes | Yes | Yes |
| Reports (module 10) | – | – | Read | Read |
| Branches and transfers (module 11) | – | Read branches | Read branches; full transfers | Full |
| Purchasing (module 12) | – | – | Full | Full |
| Audit log (module 13) | – | – | – | Read |
| Import/export (module 13) | – | – | – | Full |

| ID | Requirement |
| --- | --- |
| LIB-AUTH-24 | A request by a role without the permission in the matrix returns `403 FORBIDDEN`. A request without valid authentication to a non-anonymous endpoint returns `401` as in LIB-AUTH-12. |
| LIB-AUTH-25 | When a `member` addresses a resource that exists but is not their own, the response is `403 FORBIDDEN` (not `404`). |

### 6.7 Events for other modules

The module MUST report these events to the audit log (module 13, section 19) with the acting user, the time from the clock and the affected user id:

`login_succeeded`, `login_failed`, `account_locked`, `logout`, `password_changed`, `password_reset`, `user_created`, `user_updated`, `user_deactivated`, `user_activated`.

---


## 7. Module 3: Members

This module registers library members and manages their membership type, validity and status. Branches (`branch_id`) are managed by module 11 (section 17); here a `branch_id` refers to an existing branch.

### 7.1 Membership types

| Type | Value | Validity period | Loan period | Loan limit | Loan renewals | Late fee per working day |
| --- | --- | --- | --- | --- | --- | --- |
| Student | `student` | 365 days | 14 days | 5 | 1 | 2.00 TL |
| Academic | `academic` | 365 days | 30 days | 10 | 2 | 1.00 TL |
| Staff (university administrative staff) | `staff` | 365 days | 21 days | 7 | 2 | 1.00 TL |
| Guest | `guest` | 90 days | 7 days | 2 | 0 | 5.00 TL |

The loan columns are used by module 5, the fee column by module 7.

### 7.2 Data

**Member**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `member_no` | text | `"M"` followed by `id` padded to 6 digits, e.g. `"M000042"`; assigned at registration |
| `full_name` | text | LIB-COM-16 |
| `email` | text | LIB-COM-17; also the e-mail of the member's user account |
| `phone` | text or null | Required for `guest`, optional otherwise. Allowed characters: digits, spaces and a leading `+`; 10–15 digits |
| `membership_type` | `student` \| `academic` \| `staff` \| `guest` | Required |
| `university_id` | text or null | Required for non-guests, MUST be null for guests. 4–20 characters `[A-Za-z0-9]`; unique among members |
| `home_branch_id` | integer | Existing branch |
| `status` | `active` \| `passive` | Default `active` |
| `membership_start` | date | Today at registration |
| `valid_until` | date | See LIB-MEM-03 |
| `user_id` | integer | The member's user account (role `member`) |
| `created_at` | date-time | From the clock |

API representation (`MemberOut`): all fields above except `user_id`, plus `membership_valid` (boolean, LIB-MEM-04).

### 7.3 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/members` | librarian, admin | Register a member |
| `GET /api/v1/members` | librarian, admin | List members |
| `GET /api/v1/members/me` | member | Own member record |
| `GET /api/v1/members/{member_id}` | librarian, admin; member (own) | One member |
| `PATCH /api/v1/members/{member_id}` | librarian, admin | Change member data or type |
| `POST /api/v1/members/{member_id}/renew-membership` | librarian, admin | Extend validity |
| `POST /api/v1/members/{member_id}/deactivate` | librarian, admin | Set status `passive` |
| `POST /api/v1/members/{member_id}/activate` | librarian, admin | Set status `active` |
| `GET /api/v1/members/{member_id}/summary` | librarian, admin; member (own) | Loans, reservations, debt and borrowing eligibility |

### 7.4 Requirements

| ID | Requirement |
| --- | --- |
| LIB-MEM-01 | **Registration.** `POST /api/v1/members` with `{"full_name", "email", "phone", "membership_type", "university_id", "home_branch_id", "password"}` creates the member and a user account (role `member`, same e-mail and full name, password per LIB-AUTH-02) in one transaction and returns `201` with `MemberOut`. `phone` and `university_id` MAY be omitted where LIB-MEM-02 allows. |
| LIB-MEM-02 | **Type-specific fields.** For `guest`: `phone` is required and `university_id` MUST be absent or null. For the other types: `university_id` is required. A violation returns `422 VALIDATION_ERROR`. |
| LIB-MEM-03 | **Validity.** At registration, `membership_start` = today and `valid_until` = today + 364 days for `student`, `academic` and `staff`, and today + 89 days for `guest` (so the membership covers 365 or 90 calendar days including the first day). Example: registered 2026-11-02 → `valid_until` 2027-11-01 (guest: 2027-01-30). |
| LIB-MEM-04 | **Valid membership.** A membership is valid on a date `d` when `status` is `active` and `d` ≤ `valid_until`. `membership_valid` in `MemberOut` is this value for today. |
| LIB-MEM-05 | **Uniqueness.** `email` MUST be unique among all users (LIB-AUTH-05) and `university_id` unique among members. A duplicate returns `409 CONFLICT` with `details.field`. |
| LIB-MEM-06 | **List.** `GET /api/v1/members` is paginated (LIB-COM-18) and ordered by `id`. Filters: `q` (case-insensitive substring of `full_name`, `email`, `member_no` or `university_id`), `membership_type`, `status`, `home_branch_id`, `membership_valid` (`true`/`false`). |
| LIB-MEM-07 | **Update.** `PATCH /api/v1/members/{member_id}` accepts any subset of `{"full_name", "email", "phone", "membership_type", "university_id", "home_branch_id"}`. If the resulting member breaks LIB-MEM-02, the response is `409 MEMBER_FIELDS_INVALID` with `details.fields`; LIB-MEM-05 applies as well. A changed `email` or `full_name` is also changed on the user account. `membership_start` and `valid_until` do not change. |
| LIB-MEM-08 | **Type change.** A change of `membership_type` applies only to loans created after the change. Open loans keep their due date, renewal limit and daily fee (LIB-LOAN-04). A change to `guest` requires `phone` and sets `university_id` to null; a change from `guest` requires `university_id` in the same request. |
| LIB-MEM-09 | **Renew membership.** `POST /api/v1/members/{member_id}/renew-membership` returns `200` with `MemberOut`. If `valid_until` ≥ today, `valid_until` increases by 365 days (guest: 90 days). If `valid_until` < today, `valid_until` = today + 364 days (guest: today + 89 days). A `passive` member returns `409 MEMBER_PASSIVE`. |
| LIB-MEM-10 | **Deactivate.** `POST /api/v1/members/{member_id}/deactivate` sets `status` to `passive` and returns `200` with `MemberOut`. A member with at least one open loan returns `409 MEMBER_HAS_OPEN_LOANS`. Unpaid fees do not prevent deactivation. All active reservations of the member are cancelled with reason `member_deactivated` (LIB-RES-13). The user account stays active, so the member can still log in, read own data and see fees. Deactivating a `passive` member returns `409 MEMBER_PASSIVE`. |
| LIB-MEM-11 | **Activate.** `POST /api/v1/members/{member_id}/activate` sets `status` to `active` and returns `200`. `valid_until` does not change. Activating an `active` member returns `409 MEMBER_ALREADY_ACTIVE`. |
| LIB-MEM-12 | **Summary.** `GET /api/v1/members/{member_id}/summary` returns `200` with `{"member": MemberOut, "open_loans": <int>, "overdue_loans": <int>, "active_reservations": <int>, "balance": BalanceOut, "borrowing": {"eligible": <bool>, "reasons": [<error codes>]}}`. `BalanceOut` is defined in LIB-FEE-10. `reasons` lists every code from LIB-LOAN-05 steps 1–5 that currently applies, in that order; it is empty when `eligible` is `true`. |
| LIB-MEM-13 | **Own record.** `GET /api/v1/members/me` returns the member linked to the authenticated user. A user without a linked member returns `404 NOT_FOUND`. |

---

## 8. Module 4: Catalog

This module manages authors, publishers, books (titles) and copies (physical items).

### 8.1 Data

**Author:** `id`, `name` (LIB-COM-16).
**Publisher:** `id`, `name` (LIB-COM-16, unique case-insensitively).

**Book**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `isbn` | text | ISBN-13, unique; see LIB-CAT-02 |
| `title` | text | LIB-COM-16 |
| `subtitle` | text or null | 0–200 characters |
| `author_ids` | list of integers | 1–10 existing authors, in the given order, no duplicates |
| `publisher_id` | integer | Existing publisher |
| `publication_year` | integer | 1450 to the current year (from the clock) |
| `language` | text | Two lower-case letters (ISO 639-1), e.g. `"tr"`, `"en"` |
| `classification` | text | Dewey-style class: three digits, optionally a dot and 1–6 digits, e.g. `"005"`, `"005.133"` |
| `created_at` | date-time | From the clock |

API representation (`BookOut`): the fields above, `authors` as `[{"id", "name"}]` in order instead of `author_ids`, `publisher` as `{"id", "name"}`, and `availability`: `[{"branch_id", "available", "total"}]` per branch that holds copies, ordered by `branch_id`, where `available` counts copies with status `available` at that branch (current branch) and `total` counts copies at that branch whose status is not `lost` or `withdrawn`. Copies in transfer (no current branch) are not counted.

**Copy**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `book_id` | integer | Existing book |
| `barcode` | text | 6–20 characters `[A-Z0-9-]`, unique; stored in upper case |
| `home_branch_id` | integer | The branch that owns the copy |
| `current_branch_id` | integer or null | Where the copy is now; null while in transfer |
| `price` | amount | 0.01–100000.00 TL (LIB-COM-11–13); used for lost and damaged books |
| `status` | see 8.2 | Initially `available` |
| `acquired_on` | date | Not after today |
| `shelf_location` | text or null | 0–50 characters |
| `withdrawn_reason` | text or null | Set when withdrawn |

### 8.2 Copy statuses

| Status | Meaning | Can be lent |
| --- | --- | --- |
| `available` | On the shelf at `current_branch_id` | Yes |
| `on_loan` | Lent to a member (module 5) | No |
| `on_hold` | Kept for a ready reservation (module 6) | Only to that member |
| `in_transfer` | Moving between branches (module 11) | No |
| `damaged` | Returned damaged, waiting for repair | No |
| `lost` | Reported lost (module 5) | No |
| `withdrawn` | Removed from the collection; final | No |

Allowed transitions: `available` → `on_loan`, `on_hold`, `in_transfer`, `withdrawn`; `on_hold` → `on_loan`, `available`, `in_transfer`; `on_loan` → `available`, `on_hold`, `in_transfer`, `damaged`, `lost`; `in_transfer` → `available`, `on_hold`; `damaged` → `available`, `on_hold`, `in_transfer`, `withdrawn`; `lost` → `withdrawn`. The release procedure (LIB-RES-08) and transfer arrival (LIB-BR-07) may also keep a copy `on_hold` (held for the next reservation in the queue) or `in_transfer` (a new transfer starts on arrival); these are allowed. On arrival, the copy goes directly from `in_transfer` to the status that LIB-BR-07 gives it; no intermediate status is stored. Any other transition MUST be rejected with `409 INVALID_COPY_STATUS`.

### 8.3 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST`, `GET /api/v1/authors`; `GET`, `PATCH`, `DELETE /api/v1/authors/{author_id}` | write: librarian, admin; read: all authenticated users | Authors |
| `POST`, `GET /api/v1/publishers`; `GET`, `PATCH`, `DELETE /api/v1/publishers/{publisher_id}` | same | Publishers |
| `POST`, `GET /api/v1/books`; `GET`, `PATCH`, `DELETE /api/v1/books/{book_id}` | same | Books |
| `POST`, `GET /api/v1/books/{book_id}/copies` | same | Copies of a book |
| `GET`, `PATCH /api/v1/copies/{copy_id}`; `GET /api/v1/copies/by-barcode/{barcode}` | same | One copy |
| `POST /api/v1/copies/{copy_id}/withdraw` | librarian, admin | Remove from collection |
| `POST /api/v1/copies/{copy_id}/repair` | librarian, admin | Damaged copy repaired |

### 8.4 Requirements

| ID | Requirement |
| --- | --- |
| LIB-CAT-01 | Authors and publishers: `POST` with `{"name"}` returns `201`; `GET` lists are paginated, ordered by `name` then `id`, with filter `q` (case-insensitive substring); `PATCH` changes `name`. A duplicate publisher name returns `409 CONFLICT`. |
| LIB-CAT-02 | **ISBN.** The `isbn` input MAY contain hyphens and spaces, which are removed. The result MUST be either (a) an ISBN-10: 9 digits plus a check character `0–9` or `X`/`x`, where the sum of digit × weight for weights 10 down to 1 (`X` = 10) is divisible by 11; or (b) an ISBN-13: 13 digits starting with `978` or `979`, where the sum of digits with weights 1, 3, 1, 3, … is divisible by 10. Anything else returns `422 VALIDATION_ERROR`. An ISBN-10 is stored as ISBN-13: `978` + its first 9 digits + the ISBN-13 check digit. Example: `"0-306-40615-2"` is stored as `"9780306406157"`. |
| LIB-CAT-03 | **Create book.** `POST /api/v1/books` with `{"isbn", "title", "subtitle", "author_ids", "publisher_id", "publication_year", "language", "classification"}` returns `201` with `BookOut`. An ISBN that is already stored (after normalization) returns `409 CONFLICT`. |
| LIB-CAT-04 | **List books.** `GET /api/v1/books` is paginated, ordered by `title` (case-insensitive) then `id`. Filters: `isbn` (normalized, exact), `author_id`, `publisher_id`, `language`, `classification_prefix`. Full-text search is module 9. |
| LIB-CAT-05 | **Update book.** `PATCH /api/v1/books/{book_id}` accepts any subset of the create fields with the same rules. |
| LIB-CAT-06 | **Delete.** `DELETE` returns `204`. A book that has any copy returns `409 BOOK_HAS_COPIES`. An author or publisher that is used by any book returns `409 IN_USE`. |
| LIB-CAT-07 | **Add copy.** `POST /api/v1/books/{book_id}/copies` with `{"barcode", "home_branch_id", "price", "acquired_on", "shelf_location"}` returns `201` with the copy. `current_branch_id` = `home_branch_id`, `status` = `available`. A duplicate barcode returns `409 CONFLICT`. The new copy is then released (LIB-RES-08), so a waiting reservation can take it at once. |
| LIB-CAT-08 | **List copies.** `GET /api/v1/books/{book_id}/copies` is paginated, ordered by `id`, with filters `status` and `branch_id` (current branch). |
| LIB-CAT-09 | **Update copy.** `PATCH /api/v1/copies/{copy_id}` accepts any subset of `{"price", "shelf_location", "home_branch_id"}`. `home_branch_id` can change only while the copy is `available` at its home branch; it then also changes `current_branch_id`. Otherwise `409 INVALID_COPY_STATUS`. |
| LIB-CAT-10 | **Withdraw.** `POST /api/v1/copies/{copy_id}/withdraw` with `{"reason"}` (5–500 characters) sets `status` to `withdrawn` and stores the reason. Allowed from `available`, `damaged` and `lost` (8.2); otherwise `409 INVALID_COPY_STATUS`. |
| LIB-CAT-11 | **Repair.** `POST /api/v1/copies/{copy_id}/repair` is allowed only for a `damaged` copy (otherwise `409 INVALID_COPY_STATUS`). The copy is released (LIB-RES-08). |
| LIB-CAT-12 | **Lendable book.** A book is *lendable* when it has at least one copy whose status is not `lost` or `withdrawn`. |

---

## 9. Module 5: Loans and returns

### 9.1 Data

**Loan**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `copy_id`, `member_id` | integer | Existing copy and member |
| `branch_id` | integer | Branch where the loan was made (the copy's current branch) |
| `loan_date` | date | Today at creation |
| `due_date` | date | LIB-LOAN-03 |
| `loan_period_days`, `max_renewals`, `daily_fee` | integer, integer, amount | Copied from the member's type at creation (LIB-LOAN-04) |
| `renewal_count` | integer | Starts at 0 |
| `status` | `open` \| `returned` \| `lost` | |
| `returned_on` | date or null | Set at return |
| `return_branch_id` | integer or null | Set at return |
| `condition_on_return` | `good` \| `damaged` \| null | Set at return |
| `late_days` | integer or null | Set when the loan is closed (returned or lost) |
| `created_by` | integer | Acting user |

API representation (`LoanOut`): all fields, plus `is_overdue` (LIB-LOAN-02) and `accrued_late_fee` (LIB-FEE-02, for open loans; the final late fee for closed loans).

### 9.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/loans` | librarian, admin | Lend a copy |
| `GET /api/v1/loans` | librarian, admin | List loans |
| `GET /api/v1/loans/{loan_id}` | librarian, admin; member (own) | One loan |
| `GET /api/v1/members/{member_id}/loans` | librarian, admin; member (own) | Loans of a member |
| `POST /api/v1/loans/{loan_id}/renew` | librarian, admin; member (own) | Renew |
| `POST /api/v1/loans/{loan_id}/return` | librarian, admin | Return |
| `POST /api/v1/loans/{loan_id}/report-lost` | librarian, admin | Report lost |

### 9.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-LOAN-01 | **Lend.** `POST /api/v1/loans` with `{"member_id"}` and exactly one of `{"copy_id"}` or `{"barcode"}` returns `201` with `LoanOut`. Both or neither returns `422 VALIDATION_ERROR`. The copy's status becomes `on_loan`. An unknown `barcode` returns `404 NOT_FOUND` with `details` `{"field": "barcode", "value": "<barcode>"}`. |
| LIB-LOAN-02 | **Overdue.** An open loan is overdue when today > `due_date`. |
| LIB-LOAN-03 | **Due date.** `due_date` = the next working day on or after `loan_date` + `loan_period_days` calendar days (LIB-COM-08). Examples: student, lent 2026-11-02 → due 2026-11-16; academic, lent 2026-12-02 → 2027-01-01 is a holiday → due 2027-01-04. |
| LIB-LOAN-04 | **Terms are fixed per loan.** `loan_period_days`, `max_renewals` and `daily_fee` are copied from the member's type (7.1) when the loan is created and are used for that loan until it closes, even if the member's type changes. |
| LIB-LOAN-05 | **Lending checks.** The checks run in this order; the first failure decides the response (all `409`): (1) member `passive` → `MEMBER_PASSIVE`; (2) today > `valid_until` → `MEMBERSHIP_EXPIRED`; (3) the member has an overdue loan → `MEMBER_HAS_OVERDUE`; (4) the member's total debt (LIB-FEE-09) ≥ 50.00 TL → `MEMBER_BLOCKED_BY_DEBT`, with `details.total_debt`; (5) the member's open loans ≥ the loan limit of the member's current type → `LOAN_LIMIT_REACHED`; (6) copy status: `available` → allowed; `on_hold` → allowed only if the hold belongs to a `ready` reservation of this member (LIB-RES-10), otherwise `COPY_ON_HOLD`; any other status → `COPY_NOT_AVAILABLE`, with `details.status`. |
| LIB-LOAN-06 | **Debt boundary.** Total debt 49.99 TL allows lending; 50.00 TL does not. |
| LIB-LOAN-07 | **Renew.** `POST /api/v1/loans/{loan_id}/renew` returns `200` with `LoanOut`. Checks in order (all `409`): loan not `open` → `LOAN_NOT_OPEN`; member `passive` → `MEMBER_PASSIVE`; membership expired → `MEMBERSHIP_EXPIRED`; loan overdue → `LOAN_OVERDUE`; `renewal_count` ≥ `max_renewals` → `RENEWAL_LIMIT_REACHED`; the book has an active reservation (status `waiting`, `in_transit` or `ready`) by any member → `BOOK_RESERVED`. |
| LIB-LOAN-08 | **Renewed due date.** New `due_date` = the next working day on or after today + `loan_period_days` (the new period starts on the renewal day). Because today is never before the previous loan or renewal date, the new due date is never earlier than the current one. `renewal_count` increases by 1. A renewal on the due date itself is allowed (not overdue). Examples: student loan due 2026-11-16, renewed on 2026-11-10 → due 2026-11-24. Student loan due 2026-06-01, renewed on 2026-05-15 → 2026-05-29 is a holiday → due 2026-06-01 (unchanged); the renewal still counts. |
| LIB-LOAN-09 | **Return.** `POST /api/v1/loans/{loan_id}/return` with `{"branch_id", "condition": "good" \| "damaged", "damage_fee"}` closes the loan (`status` `returned`, `returned_on` = today, `return_branch_id`, `condition_on_return`, `late_days`) and returns `200` with `LoanOut`. Business checks in order: loan not `open` → `409 LOAN_NOT_OPEN`; return branch inactive → `409 BRANCH_INACTIVE`; `damage_fee` above the copy's `price` → `409 DAMAGE_FEE_EXCEEDS_PRICE`. The book may be returned at any active branch. |
| LIB-LOAN-10 | **Late fee at return.** `late_days` = working days between `due_date` and `returned_on` (LIB-COM-10). If `late_days` > 0, a late fee is created (LIB-FEE-02). Example: student loan due 2026-11-16 (Mon), returned 2026-11-20 (Fri) → 4 late days → 8.00 TL. |
| LIB-LOAN-11 | **Damaged return.** With `condition` `damaged`, `damage_fee` is required and MUST be > 0.00 (`422 VALIDATION_ERROR` otherwise) and ≤ the copy's `price` (`409 DAMAGE_FEE_EXCEEDS_PRICE` otherwise, LIB-LOAN-09). A damage fee is created (LIB-FEE-03) and the copy's status becomes `damaged` at the return branch (`current_branch_id` = `branch_id`). With `condition` `good`, `damage_fee` MUST be absent or null (`422 VALIDATION_ERROR`). |
| LIB-LOAN-12 | **Copy after a good return.** The copy's `current_branch_id` becomes the return branch and the copy is released (LIB-RES-08). |
| LIB-LOAN-13 | **Report lost.** `POST /api/v1/loans/{loan_id}/report-lost` closes an open loan with `status` `lost`, `late_days` = working days between `due_date` and today, and creates the fees of LIB-FEE-04. The copy's status becomes `lost` and `current_branch_id` becomes null. A loan that is not `open` returns `409 LOAN_NOT_OPEN`. Returns `200` with `LoanOut`. |
| LIB-LOAN-14 | **List.** `GET /api/v1/loans` is paginated, ordered by `id` descending. Filters: `member_id`, `copy_id`, `book_id`, `branch_id`, `status`, `overdue` (`true` selects open loans that are overdue; `false` selects all other loans), `due_before` (date, due date ≤ value). `GET /api/v1/members/{member_id}/loans` has the same filters except `member_id`. |

---

## 10. Module 6: Reservations

### 10.1 Data

**Reservation**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `book_id`, `member_id`, `pickup_branch_id` | integer | Existing book, member and branch |
| `status` | `waiting` \| `in_transit` \| `ready` \| `fulfilled` \| `cancelled` \| `expired` | Initially `waiting` |
| `created_at` | date-time | From the clock; defines the queue order |
| `copy_id` | integer or null | Copy assigned in `in_transit` and `ready` |
| `ready_on`, `hold_until` | date or null | Set when `ready` (LIB-RES-09) |
| `closed_at` | date-time or null | Set when fulfilled, cancelled or expired |
| `cancel_reason` | text or null | `"member_request"`, `"staff_request"` or `"member_deactivated"` |

*Active* reservations have status `waiting`, `in_transit` or `ready`. API representation (`ReservationOut`): all fields, plus `queue_position` (integer ≥ 1 for `waiting`, otherwise null): 1 + the number of `waiting` reservations of the same book with an earlier `created_at` (ties broken by smaller `id`).

### 10.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/reservations` | member (own), librarian, admin | Create |
| `GET /api/v1/reservations` | librarian, admin | List |
| `GET /api/v1/reservations/{reservation_id}` | librarian, admin; member (own) | One reservation |
| `GET /api/v1/members/{member_id}/reservations` | librarian, admin; member (own) | Reservations of a member |
| `GET /api/v1/books/{book_id}/reservations` | librarian, admin | Queue of a book |
| `POST /api/v1/reservations/{reservation_id}/cancel` | member (own), librarian, admin | Cancel |
| `POST /api/v1/reservations/process-expired` | librarian, admin | Expire uncollected holds |

### 10.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-RES-01 | **Create.** `POST /api/v1/reservations` with `{"book_id", "pickup_branch_id"}` returns `201` with `ReservationOut`. A librarian or admin MUST also send `member_id`; a member MUST NOT send it (`422 VALIDATION_ERROR`) and reserves for themselves. |
| LIB-RES-02 | **Creation checks.** In order (all `409`): (1) member `passive` → `MEMBER_PASSIVE`; (2) membership expired → `MEMBERSHIP_EXPIRED`; (3) the book is not lendable (LIB-CAT-12) → `BOOK_NOT_LENDABLE`; (4) the member already has an active reservation for this book → `DUPLICATE_RESERVATION`; (5) the member has an open loan of a copy of this book → `ALREADY_BORROWED`; (6) the member has 3 active reservations → `RESERVATION_LIMIT_REACHED`; (7) a copy of the book is `available` with `current_branch_id` = `pickup_branch_id` → `COPY_AVAILABLE_AT_BRANCH`. |
| LIB-RES-03 | **Limit boundary.** A member with 2 active reservations can create a third; with 3 they cannot. Fulfilled, cancelled and expired reservations do not count. |
| LIB-RES-04 | **Queue.** Each book has one first-come, first-served queue across all pickup branches, ordered by `created_at`, then `id`. There is no priority by membership type. |
| LIB-RES-05 | **Immediate assignment.** After a reservation is created, if a copy of the book is `available` at another branch, that copy is assigned at once by the release procedure (LIB-RES-08) applied to it. |
| LIB-RES-06 | **Queue view.** `GET /api/v1/books/{book_id}/reservations` returns the active reservations of the book, paginated (LIB-COM-18) and in queue order (LIB-RES-04). |
| LIB-RES-07 | **List.** `GET /api/v1/reservations` is paginated, ordered by `id`. Filters: `member_id`, `book_id`, `pickup_branch_id`, `status`. |
| LIB-RES-08 | **Release procedure.** When a copy becomes free (good return LIB-LOAN-12, new copy LIB-CAT-07, repair LIB-CAT-11, cancellation or expiry of the reservation it was held for, transfer arrival in module 11, or LIB-RES-05), the system takes the first `waiting` reservation of the copy's book (LIB-RES-04) and: (a) if none exists — the copy becomes `available` if it is at its home branch; otherwise a return transfer to the home branch starts (module 11) and the copy becomes `in_transfer`; (b) if its `pickup_branch_id` = the copy's `current_branch_id` — the reservation becomes `ready` (LIB-RES-09); (c) otherwise — the copy is assigned (`copy_id`), the reservation becomes `in_transit`, and a transfer of the copy to the pickup branch starts (module 11). |
| LIB-RES-09 | **Ready.** A reservation becomes `ready` with `copy_id` set, `ready_on` = today and `hold_until` = today + 3 working days (LIB-COM-09). The copy's status becomes `on_hold`. The member is notified (event `reservation_ready`). Example: ready on 2026-10-28 → `hold_until` 2026-11-03. |
| LIB-RES-10 | **Fulfilment.** When a member borrows a copy of a book for which they have an active reservation, that reservation becomes `fulfilled`: (a) `ready` with the held copy lent (LIB-LOAN-05 step 6, on or before `hold_until`) — nothing else changes; (b) `ready` with another available copy lent — the held copy is released (LIB-RES-08); (c) `in_transit` — the transfer continues and the copy is released when it arrives (LIB-BR-07); (d) `waiting` — no copy is involved. |
| LIB-RES-11 | **Expiry.** A `ready` reservation with today > `hold_until` is expired. `POST /api/v1/reservations/process-expired` marks every such reservation `expired` (in queue order of their books), releases each held copy (LIB-RES-08), notifies the member (event `reservation_expired`) and returns `200` with `{"expired": <count>}`. Before lending a copy that is `on_hold`, the system MUST first expire its reservation if it is past `hold_until`. |
| LIB-RES-12 | **Hold boundary.** With `hold_until` 2026-11-03, the member can collect on 2026-11-03; on 2026-11-04 the reservation is expired. |
| LIB-RES-13 | **Cancel.** `POST /api/v1/reservations/{reservation_id}/cancel` sets an active reservation to `cancelled` with `cancel_reason` (`member_request` when the member cancels, `staff_request` otherwise) and returns `200` with `ReservationOut`. A reservation that is not active returns `409 RESERVATION_NOT_ACTIVE`. If the reservation was `ready`, its copy is released (LIB-RES-08). If it was `in_transit`, the transfer continues and the copy is released when it arrives. |
| LIB-RES-14 | **No expiry while waiting.** A `waiting` or `in_transit` reservation never expires by time; it stays until it becomes ready, is cancelled, or the member is deactivated. |

---

## 11. Module 7: Fines and payments

### 11.1 Data

**Fee**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `member_id` | integer | |
| `loan_id` | integer or null | The loan the fee comes from |
| `kind` | `late_fee` \| `damage_fee` \| `lost_book` \| `lost_processing` | |
| `amount` | amount | > 0.00 |
| `paid_amount` | amount | 0.00 ≤ `paid_amount` ≤ `amount` |
| `status` | `open` \| `paid` \| `waived` | `paid` when `paid_amount` = `amount` |
| `created_on` | date | Today at creation |
| `waived_by`, `waived_at`, `waive_reason` | | Set when waived |

API representation (`FeeOut`): all fields, plus `outstanding` = `amount` − `paid_amount` for `open` fees, `"0.00"` otherwise.

**Payment:** `id`, `member_id`, `amount`, `method` (`cash` \| `card`), `received_by` (user id), `paid_at` (date-time), `allocations` (`[{"fee_id", "amount"}]`).

### 11.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `GET /api/v1/members/{member_id}/fees` | librarian, admin; member (own) | Fees of a member |
| `GET /api/v1/fees` | librarian, admin | All fees |
| `GET /api/v1/members/{member_id}/balance` | librarian, admin; member (own) | Debt summary |
| `POST /api/v1/members/{member_id}/payments` | librarian, admin | Record a payment |
| `GET /api/v1/members/{member_id}/payments` | librarian, admin; member (own) | Payments of a member |
| `POST /api/v1/fees/{fee_id}/waive` | admin | Waive a fee |

### 11.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-FEE-01 | Amounts follow section 3.3. All fee amounts are rounded once, at creation. |
| LIB-FEE-02 | **Late fee.** For a loan with `late_days` > 0, the late fee is `min(late_days × daily_fee, 100.00)` TL. The cap of 100.00 TL applies per loan and does not depend on the copy's price. For an open loan, `accrued_late_fee` is the same formula with `late_days` = working days between `due_date` and today. Example: guest loan (5.00 TL), 25 working days late → 125.00 → 100.00 TL. |
| LIB-FEE-03 | **Damage fee.** At a damaged return (LIB-LOAN-11), a fee of kind `damage_fee` with the given `damage_fee` amount is created. It is not capped by LIB-FEE-02. |
| LIB-FEE-04 | **Lost book.** At report-lost (LIB-LOAN-13), up to three fees are created: `late_fee` per LIB-FEE-02 for the late days until the report date (only if > 0); `lost_book` = the copy's `price`; `lost_processing` = 25.00 TL. Example: student loan due 2026-11-16, reported lost 2026-11-18, copy price 180.00 → late fee 4.00 (2 working days), lost book 180.00, processing 25.00. |
| LIB-FEE-05 | **Payment.** `POST /api/v1/members/{member_id}/payments` with `{"amount", "method"}` records a payment and returns `201` with the payment including `allocations`. `amount` MUST be > 0.00 (`422 VALIDATION_ERROR`) and ≤ the member's `outstanding_fees` (LIB-FEE-10); otherwise `409 PAYMENT_EXCEEDS_BALANCE` with `details.outstanding_fees`. Accrued late fees of open loans cannot be paid before the loan is closed. |
| LIB-FEE-06 | **Allocation.** A payment is applied to the member's `open` fees in order of `created_on`, then `id`: each fee receives as much as it still owes until the payment is used up. A fee whose `paid_amount` reaches `amount` becomes `paid`. Partial payment is allowed. Example: open fees A 6.00 (older) and B 20.00; payment 10.00 → A 6.00 paid (status `paid`), B 4.00 paid (status `open`, outstanding 16.00). |
| LIB-FEE-07 | **Waive.** `POST /api/v1/fees/{fee_id}/waive` with `{"reason"}` (5–500 characters) sets an `open` fee to `waived` and returns `200` with `FeeOut`. Only `admin` may waive (`403 FORBIDDEN` for librarians). A fee that is not `open` returns `409 FEE_NOT_OPEN`. Amounts already paid stay paid; only the outstanding part is waived. |
| LIB-FEE-08 | **Fee lists.** `GET /api/v1/members/{member_id}/fees` and `GET /api/v1/fees` are paginated, ordered by `created_on`, then `id`. Filters: `status`, `kind`, `loan_id`; `GET /api/v1/fees` also `member_id`. |
| LIB-FEE-09 | **Total debt.** A member's total debt = the sum of `outstanding` of all `open` fees + the sum of `accrued_late_fee` of all open overdue loans. This value is used by LIB-LOAN-05 step 4. |
| LIB-FEE-10 | **Balance.** `GET /api/v1/members/{member_id}/balance` returns `200` with `BalanceOut`: `{"outstanding_fees": "<amount>", "accrued_late_fees": "<amount>", "total_debt": "<amount>", "blocked": <bool>}`, where `blocked` is `total_debt` ≥ 50.00. |
| LIB-FEE-11 | **Payments list.** `GET /api/v1/members/{member_id}/payments` is paginated, ordered by `paid_at`, then `id`. |

---

## 12. Error codes of modules 3–7

All codes below use HTTP status `409`.

| Code | Module | Requirement |
| --- | --- | --- |
| `MEMBER_PASSIVE` | 3, 5, 6 | LIB-MEM-09, LIB-MEM-10, LIB-LOAN-05, LIB-LOAN-07, LIB-RES-02 |
| `MEMBER_ALREADY_ACTIVE` | 3 | LIB-MEM-11 |
| `MEMBER_HAS_OPEN_LOANS` | 3 | LIB-MEM-10 |
| `MEMBERSHIP_EXPIRED` | 5, 6 | LIB-LOAN-05, LIB-LOAN-07, LIB-RES-02 |
| `INVALID_COPY_STATUS` | 4, 11 | 8.2, LIB-CAT-09–11, LIB-BR-06 |
| `BOOK_HAS_COPIES` | 4 | LIB-CAT-06 |
| `IN_USE` | 4 | LIB-CAT-06 |
| `MEMBER_HAS_OVERDUE` | 5 | LIB-LOAN-05 |
| `MEMBER_BLOCKED_BY_DEBT` | 5 | LIB-LOAN-05 |
| `LOAN_LIMIT_REACHED` | 5 | LIB-LOAN-05 |
| `COPY_ON_HOLD` | 5 | LIB-LOAN-05 |
| `COPY_NOT_AVAILABLE` | 5 | LIB-LOAN-05 |
| `DAMAGE_FEE_EXCEEDS_PRICE` | 5 | LIB-LOAN-09, LIB-LOAN-11 |
| `MEMBER_FIELDS_INVALID` | 3 | LIB-MEM-07 |
| `LOAN_NOT_OPEN` | 5 | LIB-LOAN-07, LIB-LOAN-09, LIB-LOAN-13 |
| `LOAN_OVERDUE` | 5 | LIB-LOAN-07 |
| `RENEWAL_LIMIT_REACHED` | 5 | LIB-LOAN-07 |
| `BOOK_RESERVED` | 5 | LIB-LOAN-07 |
| `BOOK_NOT_LENDABLE` | 6 | LIB-RES-02 |
| `DUPLICATE_RESERVATION` | 6 | LIB-RES-02 |
| `ALREADY_BORROWED` | 6 | LIB-RES-02 |
| `RESERVATION_LIMIT_REACHED` | 6 | LIB-RES-02 |
| `COPY_AVAILABLE_AT_BRANCH` | 6 | LIB-RES-02 |
| `RESERVATION_NOT_ACTIVE` | 6 | LIB-RES-13 |
| `PAYMENT_EXCEEDS_BALANCE` | 7 | LIB-FEE-05 |
| `FEE_NOT_OPEN` | 7 | LIB-FEE-07 |

## 13. Events of modules 3–7

Modules 3–7 MUST report these events to notifications (module 8) and the audit log (module 13), with the acting user (if any), the time from the clock, and the ids of the affected entities. Which events create a notification for the member is specified in LIB-NOT-01.

| Module | Events |
| --- | --- |
| 3 | `member_registered`, `member_updated`, `membership_renewed`, `member_deactivated`, `member_activated` |
| 4 | `book_created`, `book_updated`, `book_deleted`, `copy_added`, `copy_updated`, `copy_withdrawn`, `copy_repaired` |
| 5 | `loan_created`, `loan_renewed`, `loan_returned`, `loan_lost` |
| 6 | `reservation_created`, `reservation_in_transit`, `reservation_ready`, `reservation_fulfilled`, `reservation_cancelled`, `reservation_expired` |
| 7 | `fee_created`, `payment_received`, `fee_waived` |

---


## 14. Module 8: Notifications

Notifications are stored messages for members. Nothing is sent outside the system (1.2).

### 14.1 Data

**Notification**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `member_id` | integer | Recipient |
| `type` | text | One of the types in LIB-NOT-01 |
| `message` | text | Human-readable text in English; content is not prescribed beyond LIB-NOT-02 |
| `loan_id`, `reservation_id`, `fee_id` | integer or null | Related entity, where applicable |
| `created_at` | date-time | From the clock |
| `read_at` | date-time or null | Set when the member marks it read |

### 14.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `GET /api/v1/members/{member_id}/notifications` | librarian, admin; member (own) | Notifications of a member |
| `GET /api/v1/members/{member_id}/notifications/unread-count` | librarian, admin; member (own) | Number of unread notifications |
| `POST /api/v1/notifications/{notification_id}/read` | member (own) | Mark one as read |
| `POST /api/v1/members/{member_id}/notifications/read-all` | member (own) | Mark all as read |
| `GET /api/v1/notifications` | librarian, admin | All notifications |
| `POST /api/v1/notifications/run-reminders` | librarian, admin | Create due and overdue reminders for today |

### 14.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-NOT-01 | **Which events notify the member.** Exactly these events create one notification for the affected member, in the same transaction as the event: `reservation_ready` (type `reservation_ready`), `reservation_in_transit` (`reservation_in_transit`), `reservation_expired` (`reservation_expired`), `reservation_cancelled` with reason `staff_request` or `member_deactivated` (`reservation_cancelled`), `loan_created` (`loan_created`), `loan_renewed` (`loan_renewed`), `loan_returned` (`loan_returned`), `loan_lost` (`loan_lost`), `fee_created` (`fee_created`, one per fee), `payment_received` (`payment_received`), `fee_waived` (`fee_waived`), `membership_renewed` (`membership_renewed`), `member_deactivated` (`member_deactivated`), plus the reminders of LIB-NOT-05. No other event creates a notification. |
| LIB-NOT-02 | The `message` MUST contain the book title for loan and reservation notifications, the amount (as in LIB-COM-13) for fee and payment notifications, and the relevant date (`due_date`, `hold_until` or `valid_until`) where one exists. |
| LIB-NOT-03 | **Lists.** Notification lists are paginated and ordered by `created_at` descending, then `id` descending. Filters: `unread` (`true` selects `read_at` null, `false` selects `read_at` not null), `type`; `GET /api/v1/notifications` also `member_id`. |
| LIB-NOT-04 | **Read.** `POST /api/v1/notifications/{notification_id}/read` sets `read_at` (if still null) and returns `200` with the notification; marking an already read notification again does not change `read_at`. `read-all` sets `read_at` on all unread notifications of the member and returns `200` with `{"updated": <count>}`. Only the member who owns the notification may mark it (`403 FORBIDDEN` for others, including staff). |
| LIB-NOT-05 | **Reminders.** `POST /api/v1/notifications/run-reminders` creates, for today: a `due_reminder` for every open loan whose `due_date` is the next working day after today (LIB-COM-09 with n = 1); and an `overdue_notice` for every open overdue loan. It returns `200` with `{"due_reminders": <count>, "overdue_notices": <count>}`. Example: run on Friday 2026-11-13 → loans due Monday 2026-11-16 get a `due_reminder`. |
| LIB-NOT-06 | **No duplicate reminders.** A loan gets at most one `due_reminder` per `due_date` (a renewal that changes the due date allows a new one), and at most one `overdue_notice` per day, however often reminders are run. |
| LIB-NOT-07 | **Unread count.** `unread-count` returns `200` with `{"unread": <count>}`. |

---

## 15. Module 9: Search

### 15.1 Endpoint

| Method and path | Who | Purpose |
| --- | --- | --- |
| `GET /api/v1/search/books` | all authenticated users | Search the catalog |

Query parameters: `q` (text, 0–200 characters), `author` (text), `publisher` (text), `language`, `year_from`, `year_to`, `classification_prefix`, `branch_id`, `available_only` (`true`/`false`, default `false`), `sort` (`relevance` (default), `title`, `year_desc`, `year_asc`, `popularity`), `page`, `page_size`.

### 15.2 Requirements

| ID | Requirement |
| --- | --- |
| LIB-SRCH-01 | **Normalization.** Text is compared after normalization: the characters `İ`, `I` and `ı` are replaced by `i`, then `str.casefold()` is applied. No other characters are folded. Examples: `"ISTANBUL"`, `"İstanbul"` and `"istanbul"` are equal after normalization. `"Işık"` becomes `"işik"`: it matches `"IŞIK"` and `"işik"`, but not `"isik"`, because `ş` is not folded. |
| LIB-SRCH-02 | **Tokens.** `q` is split on white space into tokens; empty tokens are ignored. A book matches `q` when **every** token is a substring of at least one of: title, subtitle, any author name, publisher name, ISBN. An empty or missing `q` matches all books. |
| LIB-SRCH-03 | **Filters.** `author` and `publisher` match by normalized substring of any author name or the publisher name. `language` is exact. `year_from`/`year_to` are inclusive bounds on `publication_year` (`year_from` > `year_to` → `422 VALIDATION_ERROR`). `classification_prefix` matches the start of `classification`. All given filters must hold (AND). |
| LIB-SRCH-04 | **Availability filter.** With `available_only=true`, only books with at least one `available` copy are returned; with `branch_id` as well, the copy must be at that branch (current branch). `branch_id` alone (without `available_only`) restricts results to books that have at least one non-lost, non-withdrawn copy at that branch. |
| LIB-SRCH-05 | **Relevance score.** For each token, a book scores the highest applicable value: 10 if the token equals the ISBN; 3 if it is in the title; 2 if it is in an author name; 1 if it is in the subtitle or publisher name. The book's score is the sum over tokens. With no `q`, every score is 0. |
| LIB-SRCH-06 | **Sorting.** `relevance`: score descending, then normalized title ascending, then `id`. `title`: normalized title ascending, then `id`. `year_desc` / `year_asc`: `publication_year`, then normalized title, then `id`. `popularity`: number of loans of the book's copies (all time, any status) descending, then normalized title, then `id`. |
| LIB-SRCH-07 | **Response.** Paginated (LIB-COM-19). Each item: `{"book": BookOut, "score": <int>, "loan_count": <int>}`. |
| LIB-SRCH-08 | **Scale.** Search MUST return correct results on a catalog of 100,000 books and 200,000 copies. |

---

## 16. Module 10: Reports

All report endpoints are for `librarian` and `admin`. Dates are inclusive.

### 16.1 Endpoints and requirements

| ID | Requirement |
| --- | --- |
| LIB-REP-01 | **Most borrowed.** `GET /api/v1/reports/most-borrowed?from=YYYY-MM-DD&to=YYYY-MM-DD&branch_id=&limit=` returns `200` with `{"from", "to", "branch_id", "items": [{"rank", "book_id", "title", "isbn", "loan_count"}]}`. `loan_count` counts loans with `loan_date` in [`from`, `to`] (and `branch_id` = loan branch, if given). Items with `loan_count` 0 are omitted. Order: `loan_count` descending, then normalized title, then `book_id`. `rank` is 1, 2, 3, … in that order (no shared ranks). `limit` is 1–100, default 10. `from` > `to`, or `to` − `from` more than 365 days (more than 366 calendar days including both ends) → `422 VALIDATION_ERROR`. |
| LIB-REP-02 | **Overdue.** `GET /api/v1/reports/overdue?branch_id=` returns a paginated list of open overdue loans (today), each `{"loan_id", "member_id", "member_no", "member_name", "book_id", "title", "copy_barcode", "due_date", "late_days", "accrued_late_fee"}`, ordered by `due_date`, then `loan_id`. `branch_id` filters by loan branch. The response also has `"total_accrued": "<amount>"` for all matching loans (all pages). |
| LIB-REP-03 | **Monthly summary.** `GET /api/v1/reports/monthly-summary?year=&month=&branch_id=` returns `200` with counts for that calendar month: `new_members` (by `membership_start`; `branch_id` = home branch), `loans_created` (by `loan_date`), `loans_returned` (by `returned_on`), `loans_lost` (closed as lost, by report date), `reservations_created`, `reservations_fulfilled`, `reservations_expired` (by the date of `created_at` / `closed_at`; `branch_id` = pickup branch), and amounts `fees_created` (sum of `amount` by `created_on`), `payments_received` (sum by date of `paid_at`), `fees_waived` (sum of waived outstanding amounts by date of `waived_at`). With `branch_id`, loan counts use the loan branch (`loans_returned`: the return branch); fee and payment amounts use the branch of the related loan, and fees without a loan are excluded. `month` MUST be 1–12 and `year` 1900–2100 (as in LIB-CORE-01); a month after the current month returns `422 VALIDATION_ERROR`. |
| LIB-REP-04 | **Inventory.** `GET /api/v1/reports/inventory?branch_id=` returns `200` with `{"items": [{"branch_id", "status", "copies"}]}`: the number of copies per current branch and status (copies in transfer and lost copies under `branch_id` null), ordered by `branch_id` (null last), then status in the order of section 8.2. Rows with 0 copies are omitted. |
| LIB-REP-05 | **CSV format.** `most-borrowed` and `overdue` accept `format=csv` (default `json`). The response is `text/csv; charset=utf-8` in the format of 22.3, with the item fields as columns in the order listed above; `overdue` with `format=csv` contains all matching rows (no pagination). |

---

## 17. Module 11: Branches and transfers

### 17.1 Data

**Branch:** `id`, `code` (2–10 characters `[A-Z0-9]`, unique), `name` (LIB-COM-16), `address` (0–300 characters), `is_active` (default `true`), `created_at`.

**Transfer**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `copy_id` | integer | |
| `from_branch_id`, `to_branch_id` | integer | Different branches |
| `reason` | `return_home` \| `reservation` \| `relocation` | |
| `reservation_id` | integer or null | Set for `reservation` |
| `started_on` | date | Today at start |
| `expected_on` | date | `started_on` + 2 working days (LIB-COM-09) |
| `status` | `in_transit` \| `received` | |
| `received_on` | date or null | |

### 17.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/branches` | admin | Create a branch |
| `GET /api/v1/branches`, `GET /api/v1/branches/{branch_id}` | all authenticated users | Read branches |
| `PATCH /api/v1/branches/{branch_id}` | admin | Change name, address, active state |
| `POST /api/v1/transfers` | librarian, admin | Relocate a copy to another branch |
| `GET /api/v1/transfers`, `GET /api/v1/transfers/{transfer_id}` | librarian, admin | Read transfers |
| `POST /api/v1/transfers/process-arrivals` | librarian, admin | Receive transfers that have arrived |

### 17.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-BR-01 | **Create branch.** `POST /api/v1/branches` with `{"code", "name", "address"}` returns `201`. `code` is stored in upper case; a duplicate returns `409 CONFLICT`. |
| LIB-BR-02 | **List branches.** `GET /api/v1/branches` is paginated, ordered by `code`, with filter `is_active`. |
| LIB-BR-03 | **Deactivate branch.** `PATCH` with `{"is_active": false}` is rejected with `409 BRANCH_IN_USE` if any copy that is not `withdrawn` has the branch as home or current branch, any member has it as home branch, or any active reservation has it as pickup branch. |
| LIB-BR-04 | **Inactive branch.** An inactive branch MUST NOT be used as `home_branch_id`, `pickup_branch_id`, return `branch_id`, transfer target or purchase-order branch: `409 BRANCH_INACTIVE`. In every check sequence of this document, `BRANCH_INACTIVE` is checked before all other `409` checks of the same request, unless the sequence places it explicitly (LIB-LOAN-09). |
| LIB-BR-05 | **Start of a transfer.** A transfer starts with `started_on` = today and `expected_on` = today + 2 working days. The copy's status becomes `in_transfer` and `current_branch_id` becomes null. Example: started Friday 2026-11-06 → expected Tuesday 2026-11-10. Transfers start in three ways: `return_home` (LIB-RES-08 a), `reservation` (LIB-RES-08 c), `relocation` (LIB-BR-06). |
| LIB-BR-06 | **Relocation.** `POST /api/v1/transfers` with `{"copy_id", "to_branch_id"}` starts a `relocation` transfer for an `available` copy and returns `201` with the transfer. Business checks in order: target branch inactive → `409 BRANCH_INACTIVE`; copy not `available` → `409 INVALID_COPY_STATUS`; `to_branch_id` equal to the copy's current branch → `409 SAME_BRANCH`. |
| LIB-BR-07 | **Arrival.** `POST /api/v1/transfers/process-arrivals` receives every `in_transit` transfer with `expected_on` ≤ today, in order of `expected_on`, then `id`, and returns `200` with `{"received": <count>}`. Receiving sets `status` `received`, `received_on` = today and the copy's `current_branch_id` = `to_branch_id`. Then: for `relocation`, the copy's `home_branch_id` also becomes `to_branch_id` and the copy is released (LIB-RES-08); for `reservation`, if the reservation is still `in_transit` it becomes `ready` (LIB-RES-09) at the pickup branch, otherwise the copy is released; for `return_home`, the copy is released. |
| LIB-BR-08 | **Boundary.** A transfer with `expected_on` 2026-11-10 is not received by `process-arrivals` on 2026-11-09 and is received on 2026-11-10. |
| LIB-BR-09 | **List transfers.** `GET /api/v1/transfers` is paginated, ordered by `id` descending, with filters `status`, `copy_id`, `from_branch_id`, `to_branch_id`, `reason`. |

---

## 18. Module 12: Purchasing

### 18.1 Data

**Supplier:** `id`, `name` (LIB-COM-16, unique case-insensitively), `email` (optional, LIB-COM-17), `phone` (optional, as member phone), `is_active` (default `true`).

**Purchase order**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `supplier_id` | integer | Active supplier |
| `branch_id` | integer | Receiving branch; becomes the copies' home branch |
| `status` | `draft` \| `ordered` \| `partially_received` \| `received` \| `cancelled` | Initially `draft` |
| `lines` | list | 1–50 lines when submitted |
| `created_by`, `created_at`, `ordered_on` | | `ordered_on` set at submit |
| `total` | amount | Sum of `quantity` × `unit_price` over lines (computed) |

**Order line:** `id`, `book_id` (existing book), `quantity` (1–100), `unit_price` (amount 0.01–100000.00), `received_quantity` (0 ≤ value ≤ `quantity`). One book at most once per order.

### 18.2 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST`, `GET /api/v1/suppliers`; `GET`, `PATCH /api/v1/suppliers/{supplier_id}` | librarian, admin | Suppliers |
| `POST /api/v1/purchase-orders` | librarian, admin | Create a draft order |
| `GET /api/v1/purchase-orders`, `GET /api/v1/purchase-orders/{order_id}` | librarian, admin | Read orders |
| `PATCH /api/v1/purchase-orders/{order_id}` | librarian, admin | Replace supplier, branch or lines of a draft |
| `POST /api/v1/purchase-orders/{order_id}/submit` | librarian, admin | Draft → ordered |
| `POST /api/v1/purchase-orders/{order_id}/cancel` | librarian, admin | Cancel |
| `POST /api/v1/purchase-orders/{order_id}/receive` | librarian, admin | Receive delivered copies |

### 18.3 Requirements

| ID | Requirement |
| --- | --- |
| LIB-PUR-01 | **Suppliers.** `POST /api/v1/suppliers` with `{"name", "email", "phone"}` returns `201`; a duplicate name returns `409 CONFLICT`. Lists are paginated, ordered by `name`, then `id`, with filters `q` and `is_active`. `PATCH` changes any of `name`, `email`, `phone`, `is_active`. |
| LIB-PUR-02 | **Create order.** `POST /api/v1/purchase-orders` with `{"supplier_id", "branch_id", "lines": [{"book_id", "quantity", "unit_price"}]}` (0–50 lines) returns `201` with the order (`status` `draft`, `total`). An inactive supplier returns `409 SUPPLIER_INACTIVE`. A book repeated in `lines` returns `422 VALIDATION_ERROR`. |
| LIB-PUR-03 | **Edit draft.** `PATCH` accepts any subset of `{"supplier_id", "branch_id", "lines"}`; `lines` replaces all lines. Only a `draft` can be edited: otherwise `409 INVALID_ORDER_STATUS`. |
| LIB-PUR-04 | **Submit.** `submit` changes `draft` to `ordered` and sets `ordered_on` = today. An order without lines returns `409 ORDER_EMPTY`; a non-draft returns `409 INVALID_ORDER_STATUS`. |
| LIB-PUR-05 | **Cancel.** `cancel` is allowed for `draft`, and for `ordered` when nothing has been received; then `status` becomes `cancelled`. Otherwise `409 INVALID_ORDER_STATUS`. |
| LIB-PUR-06 | **Receive.** `receive` with `{"lines": [{"line_id", "barcodes": ["...", ...]}]}` is allowed for `ordered` and `partially_received` (otherwise `409 INVALID_ORDER_STATUS`). An empty `lines` list, an empty `barcodes` list or a `line_id` repeated in the request returns `422 VALIDATION_ERROR`; a `line_id` that is not a line of this order returns `404 NOT_FOUND` (LIB-COM-29). For each barcode a copy is created (LIB-CAT-07) with `home_branch_id` = order branch, `price` = line `unit_price`, `acquired_on` = today; each new copy is released (LIB-RES-08). `received_quantity` increases by the number of barcodes. |
| LIB-PUR-07 | **Receive limits.** If any line would exceed its `quantity`, the whole request is rejected with `409 RECEIVE_EXCEEDS_ORDERED` and nothing is created. A duplicate or existing barcode rejects the whole request with `409 CONFLICT`. |
| LIB-PUR-08 | **Order status after receiving.** When every line has `received_quantity` = `quantity`, the status becomes `received`; otherwise, after at least one copy is received, `partially_received`. |
| LIB-PUR-09 | **List orders.** Paginated, ordered by `id` descending, with filters `status`, `supplier_id`, `branch_id`. |

---

## 19. Module 13: Audit log, import and export

### 19.1 Audit log

**Audit entry:** `id`, `at` (date-time from the clock), `actor_user_id` (null for unauthenticated requests such as failed logins), `event` (event name), `entity_type` (e.g. `"user"`, `"member"`, `"loan"`), `entity_id` (integer or null), `details` (JSON object).

| ID | Requirement |
| --- | --- |
| LIB-AUD-01 | Every event listed in 6.7, 13 and 20.2 MUST create one audit entry in the same transaction as the change it records. If the change is rolled back, the entry is rolled back too. A failed login (`login_failed`) is recorded even though the request returns an error. |
| LIB-AUD-02 | `details` contains the changed fields with old and new values for update events (`{"field": {"old": ..., "new": ...}}`) and the main input values for other events. Passwords, password hashes and tokens MUST NOT appear in `details`. |
| LIB-AUD-03 | `GET /api/v1/audit-log` (admin only) is paginated, ordered by `id` descending, with filters `event`, `actor_user_id`, `entity_type`, `entity_id`, `from`, `to` (dates, inclusive, on the local date of `at`). |
| LIB-AUD-04 | Audit entries cannot be changed or deleted through the API. |

### 19.2 Import

| ID | Requirement |
| --- | --- |
| LIB-IO-01 | `POST /api/v1/import` (admin only) with a JSON body in the format of 22.1 imports the data and returns `200` with `{"imported": {"branches": n, "authors": n, "publishers": n, "books": n, "copies": n, "members": n, "loans": n}}`. |
| LIB-IO-02 | Import is allowed only when the database contains no branch, no book and no member (the bootstrap administrator and other staff users may exist). If at least one branch, book or member exists, the response is `409 DATABASE_NOT_EMPTY`. |
| LIB-IO-03 | Import is all or nothing. If any record is invalid, nothing is imported and the response is `422 VALIDATION_ERROR` with `details.fields` listing up to 100 problems, each with `field` as a path such as `"members[17].email"`. |
| LIB-IO-04 | The `id` values in the file are kept. References between records use these ids. Every record follows the rules of its module (field formats, uniqueness, ISBN normalization, membership fields). |
| LIB-IO-05 | Imported members get a user account (role `member`) without a usable password: login for them returns `401 INVALID_CREDENTIALS` until an admin resets the password (LIB-AUTH-23). |
| LIB-IO-06 | Imported loans carry `status`: `returned` (requires `returned_on` and `return_branch_id`), `open` or `lost` (both without `returned_on`). Copy statuses MUST be consistent: a copy with an `open` imported loan MUST be `on_loan`, a copy with a `lost` loan MUST be `lost` with `current_branch_id` null (as after LIB-LOAN-13); otherwise `422`. Import creates no fees, notifications or transfers. One audit entry `data_imported` with the counts is created. |

### 19.3 Export

| ID | Requirement |
| --- | --- |
| LIB-IO-07 | `GET /api/v1/export` (admin only) returns `200` with all data in the format of 22.1. Importing an export into an empty database and exporting again MUST give the same document, provided no copy is `on_hold` or `in_transfer` at export time (LIB-IO-11). |
| LIB-IO-08 | `GET /api/v1/export/{entity}.csv` (admin only), `entity` one of `branches`, `books`, `copies`, `members`, `loans`, returns `text/csv; charset=utf-8` in the format of 22.3 with the columns of 22.2, rows ordered by `id`. An unknown entity returns `404 NOT_FOUND`. |
| LIB-IO-09 | Each export creates one audit entry `data_exported` with the entity (or `"all"`). |

### 19.4 Additions to the fixed service interface

`lms` MUST also export these functions (section 4). They import and export data without HTTP.

```python
def import_dataset(settings: Settings, data: dict) -> dict[str, int]: ...
def export_dataset(settings: Settings) -> dict: ...
```

| ID | Requirement |
| --- | --- |
| LIB-IF-11 | `import_dataset` behaves as `POST /api/v1/import` without authentication: same checks, same result counts. On a validation failure it raises `ValueError` whose message lists the problems; on a non-empty database it raises `RuntimeError`. The schema is created first if needed. |
| LIB-IF-12 | `export_dataset` returns the same document as `GET /api/v1/export`. |

---

## 20. Module 14: API layer

### 20.1 Requirements

| ID | Requirement |
| --- | --- |
| LIB-API-01 | Every endpoint listed in this document MUST exist with the given method and path. Path parameters named `*_id` are positive integers; any other value returns `422 VALIDATION_ERROR`. |
| LIB-API-02 | A request to an unknown path returns `404 NOT_FOUND`, and an unsupported method on a known path returns `405` with code `METHOD_NOT_ALLOWED`, both in the error format of LIB-COM-25. |
| LIB-API-03 | Every response with a body uses the representations defined in this document (`UserOut`, `MemberOut`, `BookOut`, `LoanOut`, `ReservationOut`, `FeeOut`, `BalanceOut` and the objects given in each requirement). Fields that are null are included with value `null`. |
| LIB-API-04 | The OpenAPI document is served at `GET /openapi.json` and MUST list every endpoint of this document. |
| LIB-API-05 | Requests with a body MUST use `Content-Type: application/json`; another content type returns `422 VALIDATION_ERROR`. |

### 20.2 Events of modules 8–13

| Module | Events |
| --- | --- |
| 8 | `reminders_run` (with the two counts) |
| 11 | `branch_created`, `branch_updated`, `transfer_started`, `transfer_received` |
| 12 | `supplier_created`, `supplier_updated`, `purchase_order_created`, `purchase_order_updated`, `purchase_order_submitted`, `purchase_order_cancelled`, `purchase_order_received` |
| 13 | `data_imported`, `data_exported` |

### 20.3 Error codes of modules 8–14

| HTTP status | Code | Requirement |
| --- | --- | --- |
| 405 | `METHOD_NOT_ALLOWED` | LIB-API-02 |
| 409 | `BRANCH_IN_USE` | LIB-BR-03 |
| 409 | `BRANCH_INACTIVE` | LIB-BR-04 |
| 409 | `SAME_BRANCH` | LIB-BR-06 |
| 409 | `SUPPLIER_INACTIVE` | LIB-PUR-02 |
| 409 | `INVALID_ORDER_STATUS` | LIB-PUR-03–06 |
| 409 | `ORDER_EMPTY` | LIB-PUR-04 |
| 409 | `RECEIVE_EXCEEDS_ORDERED` | LIB-PUR-07 |
| 409 | `DATABASE_NOT_EMPTY` | LIB-IO-02 |

---

## 21. End-to-end scenarios

Each scenario starts from an empty database with a `FixedClock`, the default holidays, one branch `A` (and `B` where named), and the bootstrap admin, who creates one librarian. Dates are "today" from the clock. Every step lists the expected result.

| ID | Scenario |
| --- | --- |
| LIB-E2E-01 | **Late return and borrowing block.** 2026-11-02: register student S (home A); add book K with copy C1 and book K2 with copy C2, both at A; lend C1 to S → due 2026-11-16. 2026-12-14: lending C2 to S → `409 MEMBER_HAS_OVERDUE`. 2026-12-21: return C1 at A → 25 late days, late fee 50.00; balance `total_debt` `"50.00"`, `blocked` true; lending C2 → `409 MEMBER_BLOCKED_BY_DEBT`. Pay 0.01 → `total_debt` `"49.99"`; lending C2 succeeds. |
| LIB-E2E-02 | **Reservation at another branch.** Branches A and B. Book K has one copy C1 (home A), lent to student S1 on 2026-11-02. Student S2 reserves K with pickup B → `waiting`, queue position 1. 2026-11-10: S1 tries to renew → `409 BOOK_RESERVED`. 2026-11-20: C1 returned at A → transfer to B (`reservation`), reservation `in_transit`, notification `reservation_in_transit`. 2026-11-23: `process-arrivals` → nothing received. 2026-11-24: `process-arrivals` → received; reservation `ready`, `hold_until` 2026-11-27; notification `reservation_ready`. 2026-11-27: lend C1 to S2 at B → reservation `fulfilled`. |
| LIB-E2E-03 | **Hold expires and passes on.** Book K has one copy C1 (home A), lent to student S3. Students S1 and S2 reserve K with pickup A, in this order. 2026-10-28: C1 returned at A → S1's reservation `ready`, `hold_until` 2026-11-03. 2026-11-04: `process-expired` → S1's reservation `expired` (notification `reservation_expired`), S2's reservation `ready` with `hold_until` 2026-11-09 (notification `reservation_ready`), C1 stays `on_hold`. Lending C1 to S1 → `409 COPY_ON_HOLD`. |
| LIB-E2E-04 | **Lost book.** Student S borrows copy C1 (price 180.00) on 2026-11-02, due 2026-11-16. 2026-11-18: report lost → fees 4.00 (late), 180.00 (lost book), 25.00 (processing); C1 `lost`; `total_debt` `"209.00"`. Payment 209.01 → `409 PAYMENT_EXCEEDS_BALANCE`. Payment 209.00 → all three fees `paid`, allocated in creation order. Admin withdraws C1 → `withdrawn`. |
| LIB-E2E-05 | **Renewal limits by type.** Guest G borrows on 2026-11-02 → due 2026-11-09; renew → `409 RENEWAL_LIMIT_REACHED`. Academic A1 borrows on 2026-11-02 → due 2026-12-02; renews on 2026-11-20 → due 2026-12-21 (2026-12-20 is a Sunday); renews again on 2026-12-01 → due 2026-12-31; a third renewal on 2026-12-10 → `409 RENEWAL_LIMIT_REACHED`. |
| LIB-E2E-06 | **Type change keeps open loan terms.** Student S borrows on 2026-11-02 (due 2026-11-16, 2.00 TL/day). S is changed to `academic`. The open loan keeps due 2026-11-16 and 2.00 TL/day; a new loan on 2026-11-03 gets 30 days and 1.00 TL/day. |
| LIB-E2E-07 | **Damaged return and repair.** 2026-11-02: student S borrows copy C1 (price 120.00, home A), the only copy of book K; student S2 reserves K with pickup A. 2026-11-05: return C1 at A as damaged with `damage_fee` 130.00 → `409 DAMAGE_FEE_EXCEEDS_PRICE`; with 40.00 → damage fee created, C1 `damaged`, S2's reservation stays `waiting`. 2026-11-06: `repair` C1 → S2's reservation `ready`, `hold_until` 2026-11-11. |
| LIB-E2E-08 | **Waiver by admin only.** A librarian waives a fee → `403 FORBIDDEN`. Admin waives it with a reason → `waived`; the member's `outstanding_fees` decreases by the outstanding amount. |
| LIB-E2E-09 | **Purchasing to shelf.** Draft order (supplier P, branch A, book K × 3 at 95.50); `total` `"286.50"`; submit; receive 2 barcodes → `partially_received`, 2 copies `available` at A with price 95.50; receive 2 more on the same line → `409 RECEIVE_EXCEEDS_ORDERED`, nothing created; receive 1 → `received`. |
| LIB-E2E-10 | **Login lockout.** Five wrong passwords for a librarian → the fifth returns `401 INVALID_CREDENTIALS` and sets the lock; the sixth attempt with the correct password returns `403 ACCOUNT_LOCKED`; after advancing the clock 15 minutes, login succeeds. |
| LIB-E2E-11 | **Import, export, search.** Import a dataset with 2 branches, 3 books, 5 copies, 2 members and 1 open loan; `GET /api/v1/export` returns the same records; search `q=istanbul` finds a book titled "İstanbul Hatırası"; imported member login → `401 INVALID_CREDENTIALS`. |

---

## 22. Data exchange formats

### 22.1 JSON dataset (import and export)

```json
{
  "format_version": 1,
  "branches":   [{"id": 1, "code": "MERKEZ", "name": "Central Library", "address": "", "is_active": true}],
  "authors":    [{"id": 1, "name": "Orhan Pamuk"}],
  "publishers": [{"id": 1, "name": "Example Publishing"}],
  "books":      [{"id": 1, "isbn": "9780306406157", "title": "Example Title", "subtitle": null,
                  "author_ids": [1], "publisher_id": 1, "publication_year": 2020,
                  "language": "tr", "classification": "813.54"}],
  "copies":     [{"id": 1, "book_id": 1, "barcode": "C000001", "home_branch_id": 1,
                  "current_branch_id": 1, "price": "180.00", "status": "available",
                  "acquired_on": "2025-09-01", "shelf_location": "A-12"}],
  "members":    [{"id": 1, "full_name": "Ayşe Yılmaz", "email": "ayse@example.edu.tr",
                  "phone": null, "membership_type": "student", "university_id": "20231234",
                  "home_branch_id": 1, "status": "active",
                  "membership_start": "2026-09-15", "valid_until": "2027-09-14"}],
  "loans":      [{"id": 1, "copy_id": 1, "member_id": 1, "branch_id": 1,
                  "loan_date": "2026-10-01", "due_date": "2026-10-15", "renewal_count": 0,
                  "status": "returned", "returned_on": "2026-10-14", "return_branch_id": 1}]
}
```

| ID | Requirement |
| --- | --- |
| LIB-IO-10 | `format_version` MUST be `1`. All seven lists MUST be present (they may be empty). Unknown fields are rejected (LIB-COM-23). |
| LIB-IO-11 | Imported copies may have status `available`, `on_loan`, `damaged`, `lost` or `withdrawn` (not `on_hold` or `in_transfer`). Imported loans take `loan_period_days`, `max_renewals` and `daily_fee` from the member's type. |
| LIB-IO-12 | In an export, lists are ordered by `id`, amounts are strings (LIB-COM-13) and dates are `"YYYY-MM-DD"`. Exports contain only the fields shown above; users, fees, payments, reservations, notifications, transfers, purchase orders and audit entries are not exported. |

### 22.2 CSV columns

| Entity | Columns, in order |
| --- | --- |
| `branches` | `id`, `code`, `name`, `address`, `is_active` |
| `books` | `id`, `isbn`, `title`, `subtitle`, `authors` (names joined with `"; "`), `publisher`, `publication_year`, `language`, `classification` |
| `copies` | `id`, `book_id`, `barcode`, `home_branch_id`, `current_branch_id`, `price`, `status`, `acquired_on`, `shelf_location` |
| `members` | `id`, `member_no`, `full_name`, `email`, `phone`, `membership_type`, `university_id`, `home_branch_id`, `status`, `membership_start`, `valid_until` |
| `loans` | `id`, `copy_id`, `member_id`, `branch_id`, `loan_date`, `due_date`, `renewal_count`, `status`, `returned_on`, `return_branch_id`, `late_days` |

### 22.3 CSV format

| ID | Requirement |
| --- | --- |
| LIB-IO-13 | CSV files are UTF-8 without BOM, comma-separated, with one header row, `\r\n` line endings and RFC 4180 quoting (as produced by Python's `csv` module with default settings). |
| LIB-IO-14 | Null values are empty fields. Booleans are `true`/`false`. Dates are `YYYY-MM-DD`. Amounts have two decimals without currency sign. |

---

## Appendix A: Requirement index

| Area | IDs | Count |
| --- | --- | --- |
| Technical constraints | LIB-TECH-01 – LIB-TECH-12 | 12 |
| Common rules | LIB-COM-01 – LIB-COM-30 | 30 |
| Fixed service interface | LIB-IF-01 – LIB-IF-12 | 12 |
| Module 1: Core | LIB-CORE-01 – LIB-CORE-10 | 10 |
| Module 2: Identity and access | LIB-AUTH-01 – LIB-AUTH-25 | 25 |
| Module 3: Members | LIB-MEM-01 – LIB-MEM-13 | 13 |
| Module 4: Catalog | LIB-CAT-01 – LIB-CAT-12 | 12 |
| Module 5: Loans and returns | LIB-LOAN-01 – LIB-LOAN-14 | 14 |
| Module 6: Reservations | LIB-RES-01 – LIB-RES-14 | 14 |
| Module 7: Fines and payments | LIB-FEE-01 – LIB-FEE-11 | 11 |
| Module 8: Notifications | LIB-NOT-01 – LIB-NOT-07 | 7 |
| Module 9: Search | LIB-SRCH-01 – LIB-SRCH-08 | 8 |
| Module 10: Reports | LIB-REP-01 – LIB-REP-05 | 5 |
| Module 11: Branches and transfers | LIB-BR-01 – LIB-BR-09 | 9 |
| Module 12: Purchasing | LIB-PUR-01 – LIB-PUR-09 | 9 |
| Module 13: Audit, import, export | LIB-AUD-01 – LIB-AUD-04, LIB-IO-01 – LIB-IO-14 | 18 |
| Module 14: API layer | LIB-API-01 – LIB-API-05 | 5 |
| End-to-end scenarios | LIB-E2E-01 – LIB-E2E-11 | 11 |
| **Total** | | **225** |
