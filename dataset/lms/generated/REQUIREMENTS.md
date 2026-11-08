# Library Management System – Requirements

**Status:** Complete draft (sections 1–26), revised after team review.
**Version:** 0.11 · 2026-11-07 (adds section 26, module 18 Interlibrary loans)

This document specifies a Library Management System (LMS) for a university library with several branches. It is the only specification used to build the system. Tests are written from this document before the code exists, so every name, path, field, status code and error code given here is binding.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Each testable requirement has an ID of the form `LIB-<AREA>-NN`.

---

## 1. Purpose and scope

### 1.1 System overview

The LMS manages a university library: members and their memberships, the catalog of books and physical copies, loans and returns, reservations, late fees and payments, notifications, search, reports, multiple branches with transfers between them, purchasing, an audit log, import/export of data, study rooms, equipment loans, digital resources and interlibrary loans. It is used through a REST API.

The system consists of 18 modules:

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
| 15 | Study rooms | `lms.rooms` | 23 |
| 16 | Equipment loans | `lms.equipment` | 24 |
| 17 | Digital resources | `lms.digital` | 25 |
| 18 | Interlibrary loans | `lms.ill` | 26 |

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
├── api/                 Module 14 (FastAPI routers and request/response schemas)
├── rooms/               Module 15
├── equipment/           Module 16
├── digital/             Module 17
└── ill/                 Module 18
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
| Study rooms (module 15) | – | Read rooms and availability; book, change, cancel, leave, check in and out own bookings; read own bans | Full, except creating and changing rooms and bans | Full |
| Equipment loans (module 16) | – | Read types and availability; reserve and cancel own reservations; extend own loans; read own loans, reservations and trainings | Full, except creating and changing types and items and retiring items | Full |
| Digital resources (module 17) | – | Read resources and calendars; borrow, return and renew own e-book loans; own holds and database sessions | Full, except licenses: read only | Full |
| Interlibrary loans (module 18) | – | Create, read and cancel own incoming requests; ask for a renewal | Full, except partners: read only | Full |
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
| LIB-MEM-10 | **Deactivate.** `POST /api/v1/members/{member_id}/deactivate` sets `status` to `passive` and returns `200` with `MemberOut`. A member with at least one open loan returns `409 MEMBER_HAS_OPEN_LOANS`. Unpaid fees do not prevent deactivation. All active reservations of the member are cancelled with reason `member_deactivated` (LIB-RES-13). The user account stays active, so the member can still log in, read own data and see fees. Deactivating a `passive` member returns `409 MEMBER_PASSIVE`. Room bookings: LIB-ROOM-37. Equipment: LIB-EQ-35. Digital resources: LIB-DIG-37. Interlibrary loans: LIB-ILL-32. |
| LIB-MEM-11 | **Activate.** `POST /api/v1/members/{member_id}/activate` sets `status` to `active` and returns `200`. `valid_until` does not change. Activating an `active` member returns `409 MEMBER_ALREADY_ACTIVE`. |
| LIB-MEM-12 | **Summary.** `GET /api/v1/members/{member_id}/summary` returns `200` with `{"member": MemberOut, "open_loans": <int>, "overdue_loans": <int>, "active_reservations": <int>, "balance": BalanceOut, "borrowing": {"eligible": <bool>, "reasons": [<error codes>]}}`. `BalanceOut` is defined in LIB-FEE-10. `reasons` lists every code from LIB-LOAN-05 steps 1–5 that currently applies, in that order; it is empty when `eligible` is `true`. The summary also contains `rooms` (LIB-ROOM-40), `equipment` (LIB-EQ-37), `digital` (LIB-DIG-36) and `ill` (LIB-ILL-34). |
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
| `current_branch_id` | integer or null | Where the copy is now; null while in transfer; unchanged while `on_loan` (the branch the copy was lent from) |
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
| `at_partner` | Lent to a partner library (module 18, LIB-ILL-31) | No |

Allowed transitions: `available` → `on_loan`, `on_hold`, `in_transfer`, `withdrawn`; `on_hold` → `on_loan`, `available`, `in_transfer`; `on_loan` → `available`, `on_hold`, `in_transfer`, `damaged`, `lost`; `in_transfer` → `available`, `on_hold`; `damaged` → `available`, `on_hold`, `in_transfer`, `withdrawn`; `lost` → `withdrawn`; module 18 adds `available` → `at_partner` and `at_partner` → `available`, `lost` (LIB-ILL-31). The release procedure (LIB-RES-08) and transfer arrival (LIB-BR-07) may also keep a copy `on_hold` (held for the next reservation in the queue) or `in_transfer` (a new transfer starts on arrival); these are allowed. On arrival, the copy goes directly from `in_transfer` to the status that LIB-BR-07 gives it; no intermediate status is stored. Any other transition MUST be rejected with `409 INVALID_COPY_STATUS`.

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
| LIB-CAT-06 | **Delete.** `DELETE` returns `204`. A book that has any copy returns `409 BOOK_HAS_COPIES`. An author or publisher that is used by any book returns `409 IN_USE`. Books with interlibrary requests: LIB-ILL-40. |
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
| LIB-LOAN-01 | **Lend.** `POST /api/v1/loans` with `{"member_id"}` and exactly one of `{"copy_id"}` or `{"barcode"}` returns `201` with `LoanOut`. Both or neither returns `422 VALIDATION_ERROR`. The copy's status becomes `on_loan`; its `current_branch_id` does not change until the return (LIB-LOAN-11, LIB-LOAN-12) or report-lost (LIB-LOAN-13). An unknown `barcode` returns `404 NOT_FOUND` with `details` `{"field": "barcode", "value": "<barcode>"}`. |
| LIB-LOAN-02 | **Overdue.** An open loan is overdue when today > `due_date`. |
| LIB-LOAN-03 | **Due date.** `due_date` = the next working day on or after `loan_date` + `loan_period_days` calendar days (LIB-COM-08). Examples: student, lent 2026-11-02 → due 2026-11-16; academic, lent 2026-12-02 → 2027-01-01 is a holiday → due 2027-01-04. |
| LIB-LOAN-04 | **Terms are fixed per loan.** `loan_period_days`, `max_renewals` and `daily_fee` are copied from the member's type (7.1) when the loan is created and are used for that loan until it closes, even if the member's type changes. |
| LIB-LOAN-05 | **Lending checks.** The checks run in this order; the first failure decides the response (all `409`): (1) member `passive` → `MEMBER_PASSIVE`; (2) today > `valid_until` → `MEMBERSHIP_EXPIRED`; (3) the member has an overdue loan (equipment loans: LIB-EQ-14; interlibrary requests: LIB-ILL-19) → `MEMBER_HAS_OVERDUE`; (4) the member's total debt (LIB-FEE-09) ≥ 50.00 TL → `MEMBER_BLOCKED_BY_DEBT`, with `details.total_debt`; (5) the member's open loans ≥ the loan limit of the member's current type → `LOAN_LIMIT_REACHED`; (6) copy status: `available` → allowed; `on_hold` → allowed only if the hold belongs to a `ready` reservation of this member (LIB-RES-10), otherwise `COPY_ON_HOLD`; any other status → `COPY_NOT_AVAILABLE`, with `details.status`. |
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
| `kind` | `late_fee` \| `damage_fee` \| `lost_book` \| `lost_processing` \| `no_show_fee` \| `equipment_late_fee` \| `equipment_damage_fee` \| `equipment_lost` | `no_show_fee`: LIB-ROOM-30; `equipment_*`: LIB-EQ-25; `ill_request_fee`, `ill_late_fee`, `ill_lost`: LIB-ILL-35 |
| `room_booking_id` | integer or null | The room booking a `no_show_fee` comes from |
| `equipment_loan_id` | integer or null | The equipment loan an `equipment_*` fee comes from |
| `ill_request_id` | integer or null | The incoming interlibrary request an `ill_*` fee comes from |
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
| LIB-FEE-09 | **Total debt.** A member's total debt = the sum of `outstanding` of all `open` fees + the sum of `accrued_late_fee` of all open overdue loans. This value is used by LIB-LOAN-05 step 4. Equipment loans: LIB-EQ-14. Interlibrary requests: LIB-ILL-19. |
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
| `loan_id`, `reservation_id`, `fee_id`, `room_booking_id`, `equipment_loan_id`, `equipment_reservation_id`, `digital_loan_id`, `digital_hold_id`, `ill_request_id` | integer or null | Related entity, where applicable |
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
| LIB-NOT-01 | **Which events notify the member.** Exactly these events create one notification for the affected member, in the same transaction as the event: `reservation_ready` (type `reservation_ready`), `reservation_in_transit` (`reservation_in_transit`), `reservation_expired` (`reservation_expired`), `reservation_cancelled` with reason `staff_request` or `member_deactivated` (`reservation_cancelled`), `loan_created` (`loan_created`), `loan_renewed` (`loan_renewed`), `loan_returned` (`loan_returned`), `loan_lost` (`loan_lost`), `fee_created` (`fee_created`, one per fee), `payment_received` (`payment_received`), `fee_waived` (`fee_waived`), `membership_renewed` (`membership_renewed`), `member_deactivated` (`member_deactivated`), plus the reminders of LIB-NOT-05, the room events of LIB-ROOM-41, the room reminders of LIB-ROOM-42 the equipment events of LIB-EQ-38 the digital events of LIB-DIG-33 and the interlibrary events of LIB-ILL-36. No other event creates a notification. |
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

All report endpoints are for `librarian` and `admin`. Dates are inclusive. The room usage report is LIB-ROOM-44; the equipment usage report is LIB-EQ-40; the digital usage report is LIB-DIG-39; the interlibrary activity report is LIB-ILL-38.

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
| LIB-BR-03 | **Deactivate branch.** `PATCH` with `{"is_active": false}` is rejected with `409 BRANCH_IN_USE` if any copy that is not `withdrawn` has the branch as home or current branch, any member has it as home branch, or any active reservation has it as pickup branch. Rooms: LIB-ROOM-39. Equipment: LIB-EQ-36. Interlibrary loans: LIB-ILL-33. |
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
| LIB-PUR-05 | **Cancel.** `cancel` is allowed for `draft`, and for `ordered` when nothing has been received; then `status` becomes `cancelled`. Otherwise `409 INVALID_ORDER_STATUS`. An order referenced by a digital license: LIB-DIG-06. |
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
| LIB-IO-06 | Imported loans carry `status`: `returned` (requires `returned_on` and `return_branch_id`), `open` or `lost` (both without `returned_on`). Copy statuses MUST be consistent: a copy with an `open` imported loan MUST be `on_loan`, a copy with a `lost` loan MUST be `lost` with `current_branch_id` null (as after LIB-LOAN-13); otherwise `422`. Member status does not restrict imported loans: a `passive` member MAY have `open` loans in the file (LIB-MEM-10 applies only to the deactivate endpoint). Import creates no fees, notifications or transfers. One audit entry `data_imported` with the counts is created. |

### 19.3 Export

| ID | Requirement |
| --- | --- |
| LIB-IO-07 | `GET /api/v1/export` (admin only) returns `200` with all data in the format of 22.1. Importing an export into an empty database and exporting again MUST give the same document, provided no copy is `on_hold`, `in_transfer` or `at_partner` at export time (LIB-IO-11, LIB-ILL-39). |
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
| LIB-API-03 | Every response with a body uses the representations defined in this document (`UserOut`, `MemberOut`, `BookOut`, `LoanOut`, `ReservationOut`, `FeeOut`, `BalanceOut`, `RoomBookingOut`, `EquipmentLoanOut` and the objects given in each requirement). Fields that are null are included with value `null`. |
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

The error codes of module 15 are listed in 23.9, those of module 16 in 24.10, those of module 17 in 25.9, those of module 18 in 26.9.

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

## 23. Module 15: Study rooms

Members book study rooms of a branch for short periods. Package `lms.rooms`. Rooms are open only on working days (LIB-COM-05), within their own opening hours. Times in this section are local times (LIB-COM-01) written `"HH:MM"`.

### 23.1 Data

**Room**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `branch_id` | integer | Existing branch |
| `code` | text | 2–10 characters `[A-Z0-9]`, stored in upper case, unique within the branch |
| `name` | text | LIB-COM-16 |
| `kind` | `individual` \| `group` | |
| `capacity` | integer | `individual`: exactly 1. `group`: 3–12 |
| `min_participants` | integer | `individual`: exactly 1. `group`: 2 to `capacity` |
| `features` | list of text | Each one of `whiteboard`, `projector`, `power_outlets`, `accessible`; no duplicates; stored in this order |
| `opens_at`, `closes_at` | time `"HH:MM"` | Minutes `00` or `30`; `07:00` ≤ `opens_at` < `closes_at` ≤ `23:00` |
| `is_active` | boolean | Default `true` |
| `created_at` | date-time | From the clock |

**Room booking**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `room_id` | integer | |
| `member_id` | integer | Organizer |
| `participant_ids` | list of integers | Other members (group rooms only); ordered ascending; does not contain the organizer |
| `date` | date | The booked day |
| `start_time`, `end_time` | time `"HH:MM"` | Minutes `00` or `30`; `start_time` < `end_time` |
| `status` | `booked` \| `checked_in` \| `completed` \| `cancelled` \| `no_show` | Initially `booked` |
| `purpose` | text | 0–200 characters |
| `created_at` | date-time | From the clock |
| `created_by` | integer | User id of the creator |
| `checked_in_at`, `closed_at` | date-time or null | Set by check-in, and by completion, cancellation or no-show |
| `cancel_reason` | text or null | `member_request`, `staff_request`, `member_deactivated`, `member_banned`, `room_closed`, `not_enough_participants` |
| `late_cancellation` | boolean | `true` when cancelled with reason `member_request` less than 2 hours before the start (LIB-ROOM-24) |

A booking's *interval* is from `date` `start_time` to `date` `end_time`; its *duration* is `end_time` − `start_time`. *Active* bookings have status `booked` or `checked_in`. A booking *counts for quota* when its status is `booked`, `checked_in`, `completed` or `no_show`. *Persons* of a booking are the organizer and the participants.

API representation (`RoomBookingOut`): all fields, plus `room_code`, `branch_id` and `duration_minutes`.

**Room ban**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `member_id` | integer | |
| `starts_on`, `ends_on` | date | Inclusive; `ends_on` ≥ `starts_on` |
| `reason` | `no_shows` \| `staff` | |
| `note` | text | 0–500 characters |
| `created_at` | date-time | From the clock |
| `created_by` | integer or null | Null for bans created by the system (LIB-ROOM-31) |
| `lifted_at`, `lifted_by` | date-time / integer or null | Set when lifted (LIB-ROOM-35) |

A ban is *in force* on a date `d` when it is not lifted and `starts_on` ≤ `d` ≤ `ends_on`.

### 23.2 Room rules by membership type

| Type | Daily hours | Weekly hours | Booking ahead (days) | Active future bookings |
| --- | --- | --- | --- | --- |
| `student` | 2 | 6 | 7 | 2 |
| `academic` | 4 | 12 | 14 | 4 |
| `staff` | 3 | 9 | 14 | 3 |
| `guest` | 0 | 0 | – | 0 |

Weeks run Monday to Sunday. Hours are summed over the durations of bookings that count for quota and in which the member is a person (organizer or participant).

### 23.3 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/rooms` | admin | Create a room |
| `GET /api/v1/rooms`, `GET /api/v1/rooms/{room_id}` | all authenticated users | Read rooms |
| `PATCH /api/v1/rooms/{room_id}` | admin | Change name, features, hours, capacity, active state |
| `GET /api/v1/rooms/{room_id}/availability` | all authenticated users | Free and booked slots of one day |
| `GET /api/v1/rooms/free` | all authenticated users | Rooms free for a whole interval |
| `POST /api/v1/room-bookings` | member (own), librarian, admin | Book a room |
| `GET /api/v1/room-bookings` | librarian, admin | All bookings |
| `GET /api/v1/room-bookings/{booking_id}` | librarian, admin; member (organizer or participant) | One booking |
| `GET /api/v1/members/{member_id}/room-bookings` | librarian, admin; member (own) | Bookings in which the member is a person |
| `PATCH /api/v1/room-bookings/{booking_id}` | member (organizer), librarian, admin | Change participants or purpose |
| `POST /api/v1/room-bookings/{booking_id}/cancel` | member (organizer), librarian, admin | Cancel |
| `POST /api/v1/room-bookings/{booking_id}/leave` | member (participant) | Leave a group booking |
| `POST /api/v1/room-bookings/{booking_id}/check-in` | member (organizer), librarian, admin | Check in |
| `POST /api/v1/room-bookings/{booking_id}/check-out` | member (organizer), librarian, admin | End early |
| `POST /api/v1/room-bookings/process` | librarian, admin | Mark no-shows and completed bookings |
| `POST /api/v1/room-bookings/run-reminders` | librarian, admin | Reminders for tomorrow's bookings |
| `GET /api/v1/members/{member_id}/room-bans` | librarian, admin; member (own) | Bans of a member |
| `POST /api/v1/members/{member_id}/room-bans` | admin | Ban a member from rooms |
| `POST /api/v1/room-bans/{ban_id}/lift` | admin | Lift a ban |
| `GET /api/v1/reports/room-usage` | librarian, admin | Usage per room (section 16) |

### 23.4 Rooms

| ID | Requirement |
| --- | --- |
| LIB-ROOM-01 | **Create room.** `POST /api/v1/rooms` with `{"branch_id", "code", "name", "kind", "capacity", "min_participants", "features", "opens_at", "closes_at"}` returns `201` with the room. `features` MAY be omitted (empty list); for `individual`, `capacity` and `min_participants` MAY be omitted and are then 1. A value outside the rules of 23.1 returns `422 VALIDATION_ERROR`. A duplicate `code` in the same branch returns `409 CONFLICT` with `details.field` `"code"`; the same code in another branch is allowed. |
| LIB-ROOM-02 | **Branch of a room.** A room cannot be created in an inactive branch (`409 BRANCH_INACTIVE`, LIB-BR-04). `branch_id` cannot be changed. |
| LIB-ROOM-03 | **List rooms.** `GET /api/v1/rooms` is paginated, ordered by `branch_id`, then `code`. Filters: `branch_id`, `kind`, `is_active`, `min_capacity` (rooms with `capacity` ≥ value), `feature` (repeatable; a room matches when it has every given feature). |
| LIB-ROOM-04 | **Update room.** `PATCH /api/v1/rooms/{room_id}` accepts any subset of `{"name", "features", "capacity", "min_participants", "opens_at", "closes_at", "is_active"}` and returns `200`. The resulting room MUST satisfy 23.1 (`422 VALIDATION_ERROR`, checked on the combined values). `kind` cannot be changed. |
| LIB-ROOM-05 | **Changes that conflict with bookings.** A change of `opens_at` or `closes_at` that would leave an active booking with a future start outside the new hours returns `409 ROOM_HAS_BOOKINGS` with `details.booking_ids` (ascending). A reduction of `capacity` below, or an increase of `min_participants` above, the number of persons of an active booking with a future start returns the same error. Bookings are not changed by a rejected update. |
| LIB-ROOM-06 | **Deactivate room.** `PATCH` with `{"is_active": false}` cancels every `booked` booking of the room whose start is after now with reason `room_closed` (LIB-ROOM-26), in order of `date`, `start_time`, then `id`, and returns `200` with the room. A `checked_in` booking is not affected and ends normally. An inactive room cannot be booked (`409 ROOM_INACTIVE`) and does not appear in `free` (LIB-ROOM-09). |
| LIB-ROOM-07 | **Open slots.** A room is open on a date `d` when `d` is a working day (LIB-COM-05) and the room and its branch are active. On an open date the room has 30-minute slots from `opens_at` to `closes_at`. Example: `opens_at` `09:00`, `closes_at` `11:00` → slots 09:00, 09:30, 10:00, 10:30. |
| LIB-ROOM-08 | **Availability.** `GET /api/v1/rooms/{room_id}/availability?date=YYYY-MM-DD` returns `200` with `{"room_id", "date", "open": <bool>, "slots": [{"start": "HH:MM", "end": "HH:MM", "free": <bool>, "booking_id": <int or null>}]}`. On a date that is not open, `open` is `false` and `slots` is empty. A slot is not free when an active booking's interval covers it. `booking_id` is shown to librarians and admins and to persons of that booking; for other members it is null. A missing `date` returns `422 VALIDATION_ERROR`. Not paginated. |
| LIB-ROOM-09 | **Free rooms.** `GET /api/v1/rooms/free?date=&start_time=&end_time=` returns a paginated list of active rooms that are open on `date` and have every slot in the interval free, ordered like LIB-ROOM-03. Filters: `branch_id`, `kind`, `min_capacity`, `feature`. Times follow 23.1 (`422 VALIDATION_ERROR` otherwise). A room whose hours do not contain the whole interval is not listed. |

### 23.5 Booking

| ID | Requirement |
| --- | --- |
| LIB-ROOM-10 | **Create booking.** `POST /api/v1/room-bookings` with `{"room_id", "date", "start_time", "end_time", "participant_ids", "purpose"}` returns `201` with `RoomBookingOut`. `participant_ids` and `purpose` MAY be omitted (empty list, empty text). A librarian or admin MUST also send `member_id` (the organizer); a member MUST NOT send it (`422 VALIDATION_ERROR`) and books for themselves. |
| LIB-ROOM-11 | **Request validation.** These return `422 VALIDATION_ERROR`: times not on minutes `00` or `30`; `start_time` ≥ `end_time`; a duration below 30 minutes or above 4 hours; a participant id listed twice; the organizer listed as participant; more than 11 participants. |
| LIB-ROOM-12 | **Booking checks.** After LIB-COM-28 steps 1–5, the checks run in this order; the first failure decides the response (all `409`): (1) branch of the room inactive → `BRANCH_INACTIVE`; (2) room inactive → `ROOM_INACTIVE`; (3) organizer `passive` → `MEMBER_PASSIVE`; (4) organizer's membership not valid on `date` (LIB-MEM-04 with `date` instead of today) → `MEMBERSHIP_EXPIRED`; (5) organizer is a `guest` → `ROOM_NOT_ALLOWED_FOR_TYPE`; (6) a ban of the organizer is in force today or on `date` → `MEMBER_BANNED_FROM_ROOMS` with `details.ends_on` (latest `ends_on` of such bans); (7) organizer's total debt (LIB-FEE-09) ≥ 50.00 → `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt`; (8) `date` is not a working day → `ROOM_CLOSED`; (9) the interval is not within `opens_at`–`closes_at` → `OUTSIDE_ROOM_HOURS`; (10) the start is not after now → `BOOKING_IN_PAST`; (11) `date` is later than today + the organizer's booking-ahead days (23.2, calendar days) → `BOOKING_TOO_FAR_AHEAD` with `details.latest_date`; (12) participant rules (LIB-ROOM-13); (13) another active booking of the room overlaps the interval → `ROOM_ALREADY_BOOKED`; (14) a person already has another active booking whose interval overlaps (any room) → `MEMBER_DOUBLE_BOOKED` with `details.member_id` (smallest such id); (15) quotas (LIB-ROOM-15) → the codes there. |
| LIB-ROOM-13 | **Participants.** In this order: (a) an `individual` room with a non-empty `participant_ids` → `409 PARTICIPANTS_NOT_ALLOWED`; (b) a participant id that does not exist → `404 NOT_FOUND` (LIB-COM-29, checked at step 4 of LIB-COM-28); (c) persons < `min_participants` → `409 NOT_ENOUGH_PARTICIPANTS` with `details.min_participants`; (d) persons > `capacity` → `409 ROOM_CAPACITY_EXCEEDED` with `details.capacity`; (e) a participant who is `passive`, a `guest`, has no valid membership on `date`, or has a ban in force on `date` → `409 PARTICIPANT_NOT_ELIGIBLE` with `details.member_id` (smallest such id) and `details.reason` (the code that applies to the participant: `MEMBER_PASSIVE`, `ROOM_NOT_ALLOWED_FOR_TYPE`, `MEMBERSHIP_EXPIRED` or `MEMBER_BANNED_FROM_ROOMS`, first in this order). |
| LIB-ROOM-14 | **Overlap.** Two intervals on the same date overlap when one starts before the other ends. Bookings that only touch (09:00–10:00 and 10:00–11:00) do not overlap. |
| LIB-ROOM-15 | **Quotas.** For each person, in order of member id, with the new booking included: (a) hours on `date` > daily hours (23.2) → `DAILY_ROOM_QUOTA_EXCEEDED`; (b) hours in the week of `date` > weekly hours → `WEEKLY_ROOM_QUOTA_EXCEEDED`; (c) only for the organizer: active bookings with a start after now in which the organizer is organizer, plus the new one, > the limit of active future bookings → `ROOM_BOOKING_LIMIT_REACHED`. Each error has `details.member_id`, `details.limit` and `details.used` (hours as a decimal string with one decimal place, for example `"2.5"`, or a count for (c)). Quota rules use the membership type of each person at the time of the request. |
| LIB-ROOM-16 | **Quota examples.** A student with a 1.5-hour booking on Tuesday can book another 30 minutes on Tuesday but not 1 hour (`DAILY_ROOM_QUOTA_EXCEEDED`, `used` `"2.5"`). A student with 2 hours each on Monday, Tuesday and Wednesday of one week cannot book on Thursday of that week (`WEEKLY_ROOM_QUOTA_EXCEEDED`), but can book on Monday of the next week. |
| LIB-ROOM-17 | **Staff booking.** A booking created by a librarian or admin for a member follows the same checks as a member's own booking (LIB-ROOM-11 to LIB-ROOM-15); `created_by` is the staff user. |
| LIB-ROOM-18 | **Lists.** `GET /api/v1/room-bookings` and `GET /api/v1/members/{member_id}/room-bookings` are paginated, ordered by `date`, `start_time`, then `id`. Filters: `status`, `room_id`, `branch_id`, `from`, `to` (dates, inclusive); `GET /api/v1/room-bookings` also `member_id` (bookings in which that member is a person). |
| LIB-ROOM-19 | **Read one booking.** A member who is neither organizer nor participant of the booking receives `403 FORBIDDEN` (LIB-AUTH-25). |

### 23.6 Changes, cancellation and check-in

| ID | Requirement |
| --- | --- |
| LIB-ROOM-20 | **Change booking.** `PATCH /api/v1/room-bookings/{booking_id}` accepts `{"participant_ids"}` and/or `{"purpose"}` for a `booked` booking whose start is after now, and returns `200`. Other states return `409 BOOKING_NOT_CHANGEABLE`. New participant lists follow LIB-ROOM-11, LIB-ROOM-13 and, for added participants only, steps (14) and (15) of LIB-ROOM-12. Date, times and room cannot be changed; a member cancels and books again. |
| LIB-ROOM-21 | **Leave.** `POST /api/v1/room-bookings/{booking_id}/leave` by a participant of a `booked` booking whose start is after now removes the member from `participant_ids` and returns `200` with the booking. A member who is not a participant receives `403 FORBIDDEN`; another state returns `409 BOOKING_NOT_CHANGEABLE`. If the remaining persons are fewer than `min_participants`, the booking is cancelled at once with reason `not_enough_participants` (LIB-ROOM-26). |
| LIB-ROOM-22 | **Cancel.** `POST /api/v1/room-bookings/{booking_id}/cancel` sets a `booked` booking to `cancelled`, sets `closed_at` and `cancel_reason` (`member_request` when the organizer cancels, `staff_request` otherwise) and returns `200` with `RoomBookingOut`. A booking that is not `booked` returns `409 BOOKING_NOT_ACTIVE`. A participant who is not the organizer receives `403 FORBIDDEN` (and uses `leave`). |
| LIB-ROOM-23 | **Cancel after start.** A `booked` booking whose start has passed but which is not yet due as a no-show (now ≤ start + 15 minutes) can still be cancelled; it counts as a late cancellation if the organizer cancels. A booking due as a no-show (LIB-ROOM-28) cannot be cancelled: `409 BOOKING_NOT_ACTIVE`. |
| LIB-ROOM-24 | **Late cancellation.** A cancellation with reason `member_request` less than 2 hours before the start sets `late_cancellation` to `true`. Exactly 2 hours before the start is not late. Example: booking 14:00–15:00; cancelled at 12:00 → not late; at 12:01 → late. No fee is created for a late cancellation; it counts for bans (LIB-ROOM-31). |
| LIB-ROOM-25 | **Cancellation and quota.** Cancelled bookings never count for quota, late or not. |
| LIB-ROOM-26 | **System cancellations.** Cancellations with reasons `member_deactivated`, `member_banned`, `room_closed` and `not_enough_participants` set `closed_at`, never set `late_cancellation`, and notify every person of the booking (event `room_booking_cancelled`). |
| LIB-ROOM-27 | **Check-in.** `POST /api/v1/room-bookings/{booking_id}/check-in` sets a `booked` booking to `checked_in` and `checked_in_at` = now, and returns `200`. Allowed from 10 minutes before the start until 15 minutes after the start, both inclusive: earlier → `409 CHECK_IN_TOO_EARLY` with `details.earliest` (date-time); later (the booking is due as a no-show) → `409 CHECK_IN_TOO_LATE`. Another state returns `409 BOOKING_NOT_ACTIVE`. Example: start 10:00 → check-in from 09:50:00 to 10:15:00. |
| LIB-ROOM-28 | **No-show.** A `booked` booking with now > start + 15 minutes is a no-show. `POST /api/v1/room-bookings/process` marks every such booking `no_show` with `closed_at` = now, in order of `date`, `start_time`, then `id`, and applies LIB-ROOM-30 and LIB-ROOM-31 to each. It also marks every `checked_in` booking with now ≥ end as `completed` with `closed_at` = now. It returns `200` with `{"no_shows": <count>, "completed": <count>, "bans": <count>}`. A `booked` booking that is due as a no-show but not yet processed keeps status `booked`, but every other rule treats it as a no-show: it is not active, so it does not block its room for new bookings (LIB-ROOM-12 (13)) and does not make its persons double-booked (14); it counts for quota; it cannot be checked in (LIB-ROOM-27) or cancelled (LIB-ROOM-23). Its fee and ban are created only when it is processed. |
| LIB-ROOM-29 | **Check-out.** `POST /api/v1/room-bookings/{booking_id}/check-out` on a `checked_in` booking sets `status` `completed`, `closed_at` = now and `end_time` = now rounded up to the next full or half hour, but not earlier than `start_time` + 30 minutes and not later than the old `end_time`. It returns `200`. The freed slots become free; quota counts the new duration. Another state returns `409 BOOKING_NOT_ACTIVE`. Example: 10:00–12:00, check-out at 10:41 → `end_time` `11:00`, duration 60 minutes. |

### 23.7 No-show fees and bans

| ID | Requirement |
| --- | --- |
| LIB-ROOM-30 | **No-show fee.** Each no-show creates a fee of kind `no_show_fee` with amount 10.00 TL for the organizer (module 7, `loan_id` null, `room_booking_id` set). Participants are not charged. The fee counts for total debt (LIB-FEE-09) like any other fee. |
| LIB-ROOM-31 | **Automatic ban.** After a no-show or a late cancellation of a booking organized by a member, the system counts the member's *incidents*: bookings they organized with status `no_show`, or `cancelled` with `late_cancellation` `true`, whose `date` is in the 30 days ending on today (today − 29 to today). If the count is 3 or more and no ban of the member is in force today, a ban with reason `no_shows`, `starts_on` = today and `ends_on` = today + 13 days (14 calendar days) is created (event `room_ban_started`), and LIB-ROOM-33 applies. Incidents that led to a ban do not count again: only incidents with `closed_at` after the `created_at` of the member's latest `no_shows` ban count. |
| LIB-ROOM-32 | **Ban example.** No-shows on 2026-11-03 and 2026-11-10 and a late cancellation on 2026-11-20 → ban from 2026-11-20 to 2026-12-03. A no-show on 2026-11-03, one on 2026-12-03 and one on 2026-12-04 → no ban (on 2026-12-04 the 30 days are 2026-11-05 to 2026-12-04, so the first is outside). |
| LIB-ROOM-33 | **Effect of a ban.** When a ban starts, every `booked` booking organized by the member whose `date` is within the ban is cancelled with reason `member_banned` (LIB-ROOM-26). Group bookings in which the member is only a participant: the member is removed, and LIB-ROOM-21 applies to the remaining persons. |
| LIB-ROOM-34 | **Staff ban.** `POST /api/v1/members/{member_id}/room-bans` with `{"starts_on", "ends_on", "note"}` creates a ban with reason `staff` and returns `201`. `starts_on` MUST NOT be before today and `ends_on` ≥ `starts_on` (`422 VALIDATION_ERROR`); the ban may overlap other bans. LIB-ROOM-33 applies to the dates of the ban. |
| LIB-ROOM-35 | **Lift.** `POST /api/v1/room-bans/{ban_id}/lift` sets `lifted_at` and `lifted_by` on a ban that is not lifted and whose `ends_on` ≥ today, and returns `200`. Otherwise `409 BAN_NOT_ACTIVE`. Cancelled bookings are not restored. |
| LIB-ROOM-36 | **Ban lists.** `GET /api/v1/members/{member_id}/room-bans` is paginated, ordered by `starts_on` descending, then `id` descending. Each item has `in_force` (boolean, for today). |

### 23.8 Effects on other modules

| ID | Requirement |
| --- | --- |
| LIB-ROOM-37 | **Member deactivation.** LIB-MEM-10 also cancels every `booked` booking organized by the member with reason `member_deactivated`, and removes the member from every `booked` group booking in which they are a participant (LIB-ROOM-21 then applies). A member who is a person of a `checked_in` booking cannot be deactivated: `409 MEMBER_IN_ROOM`, checked after `MEMBER_HAS_OPEN_LOANS`. |
| LIB-ROOM-38 | **Member type change.** A change of `membership_type` (LIB-MEM-08) does not change existing bookings. A change to `guest` cancels the member's future `booked` organized bookings with reason `staff_request` and removes them from group bookings as in LIB-ROOM-37. |
| LIB-ROOM-39 | **Branch deactivation.** LIB-BR-03 also rejects deactivation (`409 BRANCH_IN_USE`) if the branch has an active room or a room with an active booking. |
| LIB-ROOM-40 | **Member summary.** `GET /api/v1/members/{member_id}/summary` (LIB-MEM-12) also returns `"rooms": {"upcoming_bookings": <int>, "banned_until": <date or null>, "hours_this_week": "<hours>"}`: active bookings with a start after now in which the member is a person; the latest `ends_on` of bans in force today; hours of the current week per 23.2 (format of LIB-ROOM-15). |
| LIB-ROOM-41 | **Notifications.** Events that notify (added to LIB-NOT-01): `room_booking_cancelled` (every person, for reasons in LIB-ROOM-26, type `room_booking_cancelled`), `room_no_show` (organizer, type `room_no_show`), `room_ban_started` (member, type `room_ban_started`), `room_participant_added` (each added participant, type `room_participant_added`). Messages contain the room code, the date and the start time (bans: `starts_on` and `ends_on`). Notifications get a nullable `room_booking_id`. |
| LIB-ROOM-42 | **Room reminders.** `POST /api/v1/room-bookings/run-reminders` creates a notification of type `room_reminder` for each person of every `booked` booking whose `date` is the next working day after today (LIB-COM-09 with n = 1), at most once per booking and person however often it is run, and returns `200` with `{"room_reminders": <count>}`. `POST /api/v1/notifications/run-reminders` (LIB-NOT-05) is not changed. |
| LIB-ROOM-43 | **Audit.** Module 15 reports these events to the audit log: `room_created`, `room_updated`, `room_booking_created`, `room_booking_updated`, `room_booking_cancelled`, `room_participant_left`, `room_checked_in`, `room_checked_out`, `room_no_show`, `room_booking_completed`, `room_ban_started`, `room_ban_lifted`, `room_bookings_processed` (with the three counts), `room_reminders_run` (with the count). |
| LIB-ROOM-44 | **Room usage report.** `GET /api/v1/reports/room-usage?from=&to=` (dates, inclusive, `from` ≤ `to`, at most 366 days; otherwise `422 VALIDATION_ERROR`) returns a paginated list, one item per room (filters `branch_id`, `kind`), ordered by `branch_id`, then `code`: `{"room_id", "room_code", "branch_id", "open_hours", "booked_hours", "used_hours", "no_shows", "late_cancellations", "utilization"}`. `open_hours`: hours from `opens_at` to `closes_at` (current values) on every working day in the range; `booked_hours`: durations of bookings with status `checked_in`, `completed` or `no_show`; `used_hours`: `completed` and `checked_in` only; `utilization` = `used_hours` / `open_hours` as a percentage with one decimal place (`ROUND_HALF_UP`), `"0.0"` when `open_hours` is 0. Hours are strings with one decimal place. |
| LIB-ROOM-45 | **Not exported.** Rooms, bookings and bans are not part of import and export (module 13); an import into a database that has rooms returns `409 DATABASE_NOT_EMPTY` (LIB-IO-02). |

### 23.9 Error codes of module 15

| HTTP status | Code | Requirement |
| --- | --- | --- |
| 409 | `ROOM_INACTIVE` | LIB-ROOM-06, LIB-ROOM-12 |
| 409 | `ROOM_HAS_BOOKINGS` | LIB-ROOM-05 |
| 409 | `ROOM_NOT_ALLOWED_FOR_TYPE` | LIB-ROOM-12, LIB-ROOM-13 |
| 409 | `MEMBER_BANNED_FROM_ROOMS` | LIB-ROOM-12, LIB-ROOM-13 |
| 409 | `ROOM_CLOSED` | LIB-ROOM-12 |
| 409 | `OUTSIDE_ROOM_HOURS` | LIB-ROOM-12 |
| 409 | `BOOKING_IN_PAST` | LIB-ROOM-12 |
| 409 | `BOOKING_TOO_FAR_AHEAD` | LIB-ROOM-12 |
| 409 | `PARTICIPANTS_NOT_ALLOWED` | LIB-ROOM-13 |
| 409 | `NOT_ENOUGH_PARTICIPANTS` | LIB-ROOM-13 |
| 409 | `ROOM_CAPACITY_EXCEEDED` | LIB-ROOM-13 |
| 409 | `PARTICIPANT_NOT_ELIGIBLE` | LIB-ROOM-13 |
| 409 | `ROOM_ALREADY_BOOKED` | LIB-ROOM-12 |
| 409 | `MEMBER_DOUBLE_BOOKED` | LIB-ROOM-12 |
| 409 | `DAILY_ROOM_QUOTA_EXCEEDED` | LIB-ROOM-15 |
| 409 | `WEEKLY_ROOM_QUOTA_EXCEEDED` | LIB-ROOM-15 |
| 409 | `ROOM_BOOKING_LIMIT_REACHED` | LIB-ROOM-15 |
| 409 | `BOOKING_NOT_CHANGEABLE` | LIB-ROOM-20, LIB-ROOM-21 |
| 409 | `BOOKING_NOT_ACTIVE` | LIB-ROOM-22, LIB-ROOM-27, LIB-ROOM-29 |
| 409 | `CHECK_IN_TOO_EARLY` | LIB-ROOM-27 |
| 409 | `CHECK_IN_TOO_LATE` | LIB-ROOM-27 |
| 409 | `BAN_NOT_ACTIVE` | LIB-ROOM-35 |
| 409 | `MEMBER_IN_ROOM` | LIB-ROOM-37 |

---

## 24. Module 16: Equipment loans

The library lends devices (chargers, tablets, laptops, cameras and others) for short periods at the equipment desk of a branch. Package `lms.equipment`. Times are local (LIB-COM-01); date-times in requests and responses follow LIB-COM-03 and LIB-COM-04.

### 24.1 Desk hours

| ID | Requirement |
| --- | --- |
| LIB-EQ-01 | **Desk hours.** The equipment desk of every active branch is open on working days (LIB-COM-05) from 08:00 to 20:00. "Desk open at `t`" means: the local date of `t` is a working day and 08:00 ≤ local time of `t` < 20:00. |
| LIB-EQ-02 | **Next desk opening.** For a date-time `t` at which the desk is closed: 08:00 of the date of `t` if that date is a working day and `t` is before 08:00; otherwise 08:00 of the first working day after the date of `t`. Examples: Friday 2026-11-06 20:30 → Monday 2026-11-09 08:00; Tuesday 2026-11-03 07:00 → Tuesday 08:00; Thursday 2026-10-29 (holiday) 10:00 → Friday 2026-10-30 08:00. |

### 24.2 Data

**Equipment type**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `code` | text | 2–20 characters `[A-Z0-9_]`, stored in upper case, unique |
| `name` | text | LIB-COM-16 |
| `period_unit` | `hours` \| `working_days` | |
| `period` | integer | `hours`: 1–8; `working_days`: 1–10 |
| `hourly_late_fee` | amount | 0.50–50.00 |
| `requires_training` | boolean | Default `false` |
| `max_open_per_member` | integer | 1–3; open loans of this type per member |
| `is_active` | boolean | Default `true` |

**Equipment item**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `type_id` | integer | Existing type |
| `asset_tag` | text | 4–20 characters `[A-Z0-9-]`, stored in upper case, unique |
| `serial_no` | text | 1–50 characters |
| `branch_id` | integer | The branch whose desk lends and receives the item |
| `value` | amount | 1.00–100000.00 |
| `status` | `available` \| `on_loan` \| `in_repair` \| `lost` \| `retired` | Initially `available` |
| `acquired_on` | date | Not after today |
| `created_at` | date-time | From the clock |

*Lendable items* of a type at a branch are its items with status `available` or `on_loan`. Items `in_repair`, `lost` or `retired` are not lendable.

**Training record:** `id`, `member_id`, `type_id`, `completed_on` (date, not after today), `valid_until` (= `completed_on` + 364 days), `recorded_by` (user id), `created_at`.

**Equipment loan**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `item_id`, `member_id` | integer | |
| `branch_id` | integer | The item's branch |
| `reservation_id` | integer or null | Set when the loan collects a reservation |
| `loaned_at` | date-time | From the clock |
| `due_at` | date-time | LIB-EQ-15 |
| `extended` | boolean | `true` after an extension (LIB-EQ-19) |
| `status` | `open` \| `returned` \| `lost` | |
| `returned_at` | date-time or null | |
| `return_condition` | `good` \| `damaged` \| null | |
| `late_hours` | integer or null | Set when closed (LIB-EQ-22) |
| `lent_by`, `received_by` | integer or null | User ids |
| `hourly_late_fee` | amount | Copied from the type when the loan is created (LIB-EQ-04); not part of the API representation |

API representation (`EquipmentLoanOut`): all fields except `hourly_late_fee`, plus `asset_tag`, `type_id`, `type_code`, `overdue` (boolean: `open` and now > `due_at` + 15 minutes) and `accrued_late_fee` (amount; LIB-EQ-23 for an open loan as if returned now, `"0.00"` otherwise).

**Equipment reservation**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `type_id`, `branch_id`, `member_id` | integer | |
| `starts_at` | date-time | Minutes `00` or `30`, seconds 0; desk open at `starts_at` |
| `ends_at` | date-time | The `due_at` a loan collected at `starts_at` would get (LIB-EQ-15) |
| `status` | `booked` \| `collected` \| `cancelled` \| `expired` | Initially `booked` |
| `loan_id` | integer or null | Set when collected |
| `created_at`, `closed_at` | date-time | `closed_at` null while `booked` |
| `cancel_reason` | text or null | `member_request`, `staff_request`, `member_deactivated`, `type_inactive` |

A reservation *holds* an item of its type at its branch during the interval [`starts_at` − 15 minutes, `ends_at`) while it is `booked` and not expired (LIB-EQ-31). An open loan *needs* its item during [`loaned_at`, `due_at` + 15 minutes); an overdue open loan needs it at every moment until it is closed. Intervals include their start and exclude their end.

### 24.3 Rules by membership type

| Type | Open equipment loans in total | Equipment reservations (`booked`) | Training needed for types with `requires_training` |
| --- | --- | --- | --- |
| `student` | 2 | 2 | yes |
| `academic` | 3 | 3 | no |
| `staff` | 3 | 3 | no |
| `guest` | 0 | 0 | – |

### 24.4 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/equipment-types`, `PATCH /api/v1/equipment-types/{type_id}` | admin | Create, change |
| `GET /api/v1/equipment-types`, `GET /api/v1/equipment-types/{type_id}` | all authenticated users | Read |
| `GET /api/v1/equipment-types/{type_id}/availability` | all authenticated users | Free capacity per half hour |
| `POST /api/v1/equipment-items`, `PATCH /api/v1/equipment-items/{item_id}` | admin | Create, change |
| `GET /api/v1/equipment-items`, `GET /api/v1/equipment-items/{item_id}` | librarian, admin | Read |
| `POST /api/v1/equipment-items/{item_id}/retire` | admin | Retire |
| `POST /api/v1/equipment-items/{item_id}/repair-done` | librarian, admin | Back from repair |
| `POST /api/v1/members/{member_id}/equipment-trainings` | librarian, admin | Record a training |
| `GET /api/v1/members/{member_id}/equipment-trainings` | librarian, admin; member (own) | Trainings of a member |
| `POST /api/v1/equipment-loans` | librarian, admin | Lend |
| `GET /api/v1/equipment-loans`, `GET /api/v1/equipment-loans/{loan_id}` | librarian, admin; member (own, single loan) | Read |
| `GET /api/v1/members/{member_id}/equipment-loans` | librarian, admin; member (own) | Loans of a member |
| `POST /api/v1/equipment-loans/{loan_id}/return` | librarian, admin | Return |
| `POST /api/v1/equipment-loans/{loan_id}/extend` | member (own), librarian, admin | Extend once |
| `POST /api/v1/equipment-loans/{loan_id}/report-lost` | librarian, admin | Lost |
| `POST /api/v1/equipment-reservations` | member (own), librarian, admin | Reserve |
| `GET /api/v1/equipment-reservations`, `GET /api/v1/equipment-reservations/{reservation_id}` | librarian, admin; member (own, single) | Read |
| `GET /api/v1/members/{member_id}/equipment-reservations` | librarian, admin; member (own) | Reservations of a member |
| `POST /api/v1/equipment-reservations/{reservation_id}/cancel` | member (own), librarian, admin | Cancel |
| `POST /api/v1/equipment/process` | librarian, admin | Expire reservations, send overdue notices |
| `GET /api/v1/reports/equipment-usage` | librarian, admin | Usage per type (section 16) |

### 24.5 Types, items and training

| ID | Requirement |
| --- | --- |
| LIB-EQ-03 | **Create type.** `POST /api/v1/equipment-types` with `{"code", "name", "period_unit", "period", "hourly_late_fee", "requires_training", "max_open_per_member"}` returns `201`. `requires_training` MAY be omitted. Values outside 24.2 return `422 VALIDATION_ERROR`; a duplicate code `409 CONFLICT` with `details.field` `"code"`. |
| LIB-EQ-04 | **Change type.** `PATCH /api/v1/equipment-types/{type_id}` accepts any subset of `{"name", "period", "hourly_late_fee", "requires_training", "max_open_per_member", "is_active"}` and returns `200`. `code` and `period_unit` cannot be changed (`422`). A change applies to loans and reservations created afterwards; open loans keep their `due_at`, and their late fee uses the `hourly_late_fee` stored with the loan (24.2). |
| LIB-EQ-05 | **Deactivate type.** `PATCH` with `{"is_active": false}` cancels every `booked` reservation of the type with reason `type_inactive` (event `equipment_reservation_cancelled`). Open loans are not affected. An inactive type cannot be lent or reserved: `409 TYPE_INACTIVE`. |
| LIB-EQ-06 | **Lists of types.** `GET /api/v1/equipment-types` is paginated, ordered by `code`, filter `is_active`. Each item has `items_total` (items of the type that are not `retired`) and `items_available` (status `available`), both over all branches. |
| LIB-EQ-07 | **Create item.** `POST /api/v1/equipment-items` with `{"type_id", "asset_tag", "serial_no", "branch_id", "value", "acquired_on"}` returns `201`. A duplicate `asset_tag` returns `409 CONFLICT`; an inactive branch `409 BRANCH_INACTIVE`. |
| LIB-EQ-08 | **Change item.** `PATCH /api/v1/equipment-items/{item_id}` accepts `{"serial_no", "value", "branch_id"}` and returns `200`. `branch_id` can only be changed while the item is `available` and no `booked` reservation would lose its held item by the move (LIB-EQ-27 check at the old branch); otherwise `409 INVALID_ITEM_STATUS` or `409 ITEM_NEEDED_FOR_RESERVATION`. `status`, `type_id` and `asset_tag` cannot be changed (`422`). |
| LIB-EQ-09 | **Item list.** `GET /api/v1/equipment-items` is paginated, ordered by `asset_tag`. Filters: `type_id`, `branch_id`, `status`, `q` (case-insensitive substring of `asset_tag` or `serial_no`, LIB-COM-30). |
| LIB-EQ-10 | **Retire and repair.** `retire` sets an `available` or `in_repair` item to `retired` (`200`); `repair-done` sets an `in_repair` item to `available` (`200`). Any other status returns `409 INVALID_ITEM_STATUS`. Retiring follows the check of LIB-EQ-08 (`409 ITEM_NEEDED_FOR_RESERVATION`). |
| LIB-EQ-11 | **Training.** `POST /api/v1/members/{member_id}/equipment-trainings` with `{"type_id", "completed_on"}` records a training and returns `201`. `completed_on` after today returns `422 VALIDATION_ERROR`; a type without `requires_training` returns `409 TRAINING_NOT_REQUIRED`. Several records for the same member and type are allowed. A member *has valid training* for a type on a date `d` when a record of that type has `completed_on` ≤ `d` ≤ `valid_until`. Example: completed 2026-11-02 → valid until 2027-11-01. |

### 24.6 Lending

| ID | Requirement |
| --- | --- |
| LIB-EQ-12 | **Lend.** `POST /api/v1/equipment-loans` with `{"member_id", "item_id"}` or `{"member_id", "reservation_id"}` (exactly one of `item_id` and `reservation_id`, otherwise `422 VALIDATION_ERROR`) creates an `open` loan with `loaned_at` = now and `lent_by` = the user, sets the item `on_loan` and returns `201` with `EquipmentLoanOut` (event `equipment_loan_created`). |
| LIB-EQ-13 | **Lending checks.** After LIB-COM-28 steps 1–5, in this order (all `409`): (1) the item's branch inactive → `BRANCH_INACTIVE`; (2) desk not open now (LIB-EQ-01) → `DESK_CLOSED` with `details.opens_at` (LIB-EQ-02); (3) type inactive → `TYPE_INACTIVE`; (4) member `passive` → `MEMBER_PASSIVE`; (5) membership not valid today → `MEMBERSHIP_EXPIRED`; (6) member is a `guest` → `EQUIPMENT_NOT_ALLOWED_FOR_TYPE`; (7) member has an overdue equipment loan (LIB-EQ-16) or an overdue book loan (LIB-LOAN-02) → `MEMBER_HAS_OVERDUE`; (8) total debt (LIB-FEE-09) ≥ 50.00 → `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt`; (9) the type requires training, the member is a `student` and has no valid training today → `TRAINING_REQUIRED`; (10) open equipment loans of the member ≥ the total of 24.3 → `EQUIPMENT_LIMIT_REACHED` with `details.limit`; (11) open loans of this type ≥ `max_open_per_member` → `TYPE_LIMIT_REACHED` with `details.limit`; (12) the item is not `available` → `ITEM_NOT_AVAILABLE`; (13) the new loan would break the capacity rule (LIB-EQ-27) → `ITEM_NEEDED_FOR_RESERVATION`. With `reservation_id`, checks (12) and (13) are replaced by LIB-EQ-29. |
| LIB-EQ-14 | **Debt and overdue across modules.** An overdue equipment loan also blocks book lending: LIB-LOAN-05 step 3 (`MEMBER_HAS_OVERDUE`) applies when the member has an overdue book loan **or** an overdue equipment loan. Accrued equipment late fees count for total debt: LIB-FEE-09 adds the `accrued_late_fee` of open overdue equipment loans, and `accrued_late_fees` of `BalanceOut` (LIB-FEE-10) includes them. |
| LIB-EQ-15 | **Due time.** For `period_unit` `hours`: `due_at` = `loaned_at` + `period` hours, but at most 20:00 of the date of `loaned_at`. For `working_days`: `due_at` = 17:00 on the date `loaned_at`'s date + `period` working days (LIB-COM-09). Seconds are kept. Examples: charger (4 hours) lent Tue 2026-11-03 10:20 → due 14:20; lent 17:30 → due 20:00; laptop (3 working days) lent Wed 2026-10-28 15:00 → due Tue 2026-11-03 17:00 (29 Oct holiday, 30 Oct counts 1, 31 Oct–1 Nov weekend, 2 Nov counts 2, 3 Nov counts 3). |
| LIB-EQ-16 | **Overdue boundary.** A loan is overdue when now > `due_at` + 15 minutes. Due 14:20: at 14:35 not overdue; at 14:35 plus one second overdue. |
| LIB-EQ-17 | **Lists.** `GET /api/v1/equipment-loans` and `GET /api/v1/members/{member_id}/equipment-loans` are paginated, ordered by `loaned_at`, then `id`. Filters: `status`, `type_id`, `branch_id`, `overdue` (`true`/`false`); the first also `member_id`. A member reading a loan of another member receives `403 FORBIDDEN`. |
| LIB-EQ-18 | **Reservations of the same member.** When a member with a `booked` reservation of the type at the branch borrows an item of that type at that branch with `item_id` from 15 minutes before `starts_at` to 30 minutes after it, the given item is lent and the reservation becomes `collected` as in LIB-EQ-29; checks (12) and (13) of LIB-EQ-13 apply, and in (13) this reservation no longer counts. |

### 24.7 Extension, return and loss

| ID | Requirement |
| --- | --- |
| LIB-EQ-19 | **Extend.** `POST /api/v1/equipment-loans/{loan_id}/extend` on an `open` loan sets a new `due_at` by applying LIB-EQ-15 with the current `due_at` in place of `loaned_at` (for `hours` types at most 20:00 of the date of the current `due_at`), sets `extended` and returns `200` (event `equipment_loan_extended`). Checks in order (all `409`): loan not `open` → `LOAN_NOT_OPEN`; already extended → `EXTENSION_LIMIT_REACHED`; overdue → `LOAN_OVERDUE`; the longer loan would break the capacity rule (LIB-EQ-27) → `ITEM_NEEDED_FOR_RESERVATION`. For `hours` types, an extension that would not move `due_at` (already 20:00) returns `409 EXTENSION_NOT_POSSIBLE`. Example: charger due Tue 14:20, extended at 13:00 → due 18:20; due 17:30, extended → due 20:00. |
| LIB-EQ-20 | **Return.** `POST /api/v1/equipment-loans/{loan_id}/return` with `{"condition": "good" \| "damaged", "damage_fee": "<amount>"}` closes an `open` loan: `status` `returned`, `returned_at` = now, `received_by`, `late_hours` (LIB-EQ-22); `200` with `EquipmentLoanOut` (event `equipment_loan_returned`). A loan not `open` returns `409 LOAN_NOT_OPEN`. Returns are accepted at any time, also when the desk is closed (drop box). |
| LIB-EQ-21 | **Condition.** `good`: the item becomes `available`. `damaged`: `damage_fee` is required (`422` without it, `422` with it for `good`), MUST be ≥ 0.00 and ≤ the item's `value` (`409 DAMAGE_FEE_EXCEEDS_VALUE`); a fee of kind `equipment_damage_fee` is created if `damage_fee` > 0.00; the item becomes `in_repair`. |
| LIB-EQ-22 | **Late hours.** `late_hours` = 0 if `returned_at` ≤ `due_at` + 15 minutes; otherwise the number of started hours between `due_at` and `returned_at` (wall-clock time, including nights, weekends and holidays). Examples: due 14:20, returned 14:35 → 0; returned 14:36 → 1; returned 15:20 → 1; returned 15:21 → 2. |
| LIB-EQ-23 | **Late fee.** At return, if `late_hours` > 0, a fee of kind `equipment_late_fee` = `min(late_hours × hourly_late_fee, 20 % of value)` is created, rounded per LIB-COM-12. `hourly_late_fee` is the value stored with the loan (LIB-EQ-04). Example: laptop value 30,000.00, 25.00 per hour, 30 hours late → 750.00; 300 hours late → 6,000.00 (cap 20 %). |
| LIB-EQ-24 | **Lost.** `POST /api/v1/equipment-loans/{loan_id}/report-lost` closes an `open` loan with `status` `lost`, `returned_at` null and `late_hours` computed with now as return time; it creates `equipment_late_fee` (if `late_hours` > 0, LIB-EQ-23) and `equipment_lost` = the item's `value`; the item becomes `lost`; `200` (event `equipment_loan_lost`). |
| LIB-EQ-25 | **Fees.** Equipment fees are fees of module 7 with `loan_id` null and `equipment_loan_id` set; they are paid, allocated and waived like other fees (LIB-FEE-05–07) and appear in fee lists and balances. |

### 24.8 Reservations

| ID | Requirement |
| --- | --- |
| LIB-EQ-26 | **Reserve.** `POST /api/v1/equipment-reservations` with `{"type_id", "branch_id", "starts_at"}` returns `201` with the reservation and its `ends_at` (event `equipment_reservation_created`). A librarian or admin MUST also send `member_id`; a member MUST NOT (`422`). `starts_at` with minutes other than `00`/`30` or with seconds returns `422 VALIDATION_ERROR`. |
| LIB-EQ-27 | **Capacity.** The *demand* of a type at a branch at a moment `t` is the number of open loans of the type at the branch that need their item at `t` plus the number of reservations of the type at the branch that hold an item at `t` (24.2). The *capacity* is the number of lendable items of the type at the branch (24.2). A new reservation, a new loan or an extension is possible only if, counting it with its new interval, the demand does not exceed the capacity at any moment `t` ≥ now of that interval. Example: one charger (4 hours); a reservation of another member for Tue 14:30 holds it from 14:15; a loan at 10:00 (due 14:00, needed until 14:15) is possible, a loan at 10:01 is not. |
| LIB-EQ-28 | **Reservation checks.** In order (all `409`): (1) branch inactive → `BRANCH_INACTIVE`; (2) type inactive → `TYPE_INACTIVE`; (3) member `passive` → `MEMBER_PASSIVE`; (4) membership not valid on the date of `ends_at` → `MEMBERSHIP_EXPIRED`; (5) `guest` → `EQUIPMENT_NOT_ALLOWED_FOR_TYPE`; (6) total debt (LIB-FEE-09) ≥ 50.00 → `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt`; (7) `student` without valid training on the date of `starts_at` for a type that requires it → `TRAINING_REQUIRED`; (8) desk not open at `starts_at` → `DESK_CLOSED`; (9) `starts_at` earlier than now + 30 minutes → `RESERVATION_TOO_SOON`; (10) the date of `starts_at` later than today + 14 days → `RESERVATION_TOO_FAR_AHEAD` with `details.latest_date`; (11) `booked` reservations of the member ≥ the limit of 24.3 → `EQUIPMENT_RESERVATION_LIMIT_REACHED`; (12) the member already has a `booked` reservation of the same type whose interval [`starts_at`, `ends_at`) overlaps the new one → `DUPLICATE_EQUIPMENT_RESERVATION`; (13) capacity (LIB-EQ-27) → `NO_EQUIPMENT_AVAILABLE` with `details.next_free_at` (the earliest `starts_at` after the requested one, at minutes `00` or `30`, with the desk open and on or before today + 14 days, at which the capacity rule holds; null if there is none). |
| LIB-EQ-29 | **Collect.** A loan with `reservation_id` collects a `booked` reservation of the same member, from 15 minutes before `starts_at` to 30 minutes after it (both inclusive): earlier → `409 RESERVATION_NOT_READY`, later → `409 RESERVATION_EXPIRED`; another member's reservation → `409 RESERVATION_OF_OTHER_MEMBER`; not `booked` → `409 RESERVATION_NOT_ACTIVE`. The system lends the `available` item of the type at the reservation's branch with the smallest `asset_tag`; none → `409 ITEM_NOT_AVAILABLE` (the reservation stays `booked`). The capacity rule is not checked again. The reservation becomes `collected` with `loan_id` and `closed_at`. `due_at` follows LIB-EQ-15 from `loaned_at`, not from `starts_at`. |
| LIB-EQ-30 | **Cancel.** `cancel` sets a `booked` reservation to `cancelled` with `member_request` (member) or `staff_request` (staff) and returns `200`. Not `booked` → `409 RESERVATION_NOT_ACTIVE`. |
| LIB-EQ-31 | **Expiry.** A `booked` reservation with now > `starts_at` + 30 minutes is expired. `POST /api/v1/equipment/process` marks every such reservation `expired` (`closed_at` = now, event `equipment_reservation_expired`) in order of `starts_at`, then `id`. Until processed, an expired reservation no longer holds an item (LIB-EQ-27) and cannot be collected. |
| LIB-EQ-32 | **Overdue notices.** `POST /api/v1/equipment/process` also creates one `equipment_overdue` notification for every overdue open equipment loan, at most one per loan per day, and returns `200` with `{"expired_reservations": <count>, "overdue_notices": <count>}`. |
| LIB-EQ-33 | **Availability.** `GET /api/v1/equipment-types/{type_id}/availability?branch_id=&date=` returns `200` with `{"type_id", "branch_id", "date", "capacity", "slots": [{"start": "HH:MM", "free": <int>}]}`: one slot per half hour of desk hours of that date (`08:00` … `19:30`; none if the desk is closed that day), where `free` = capacity − the highest demand (LIB-EQ-27) during the slot, never below 0. |
| LIB-EQ-34 | **Lists.** Reservation lists are paginated, ordered by `starts_at`, then `id`; filters `status`, `type_id`, `branch_id`, `from`, `to` (dates of `starts_at`, inclusive); the general list also `member_id`. |

### 24.9 Effects on other modules

| ID | Requirement |
| --- | --- |
| LIB-EQ-35 | **Member deactivation.** LIB-MEM-10 also returns `409 MEMBER_HAS_OPEN_LOANS` when the member has an open equipment loan, and cancels the member's `booked` equipment reservations with reason `member_deactivated`. |
| LIB-EQ-36 | **Branch deactivation.** LIB-BR-03 also rejects deactivation (`409 BRANCH_IN_USE`) if an equipment item that is not `retired` or `lost` belongs to the branch. |
| LIB-EQ-37 | **Member summary.** LIB-MEM-12 also returns `"equipment": {"open_loans": <int>, "overdue_loans": <int>, "booked_reservations": <int>}`. `borrowing.reasons` includes `MEMBER_HAS_OVERDUE` also for an overdue equipment loan (LIB-EQ-14). |
| LIB-EQ-38 | **Notifications.** Added to LIB-NOT-01: `equipment_loan_created`, `equipment_loan_returned`, `equipment_loan_lost`, `equipment_reservation_cancelled` (reasons `staff_request`, `member_deactivated`, `type_inactive`), `equipment_reservation_expired`, plus `equipment_overdue` (LIB-EQ-32). Messages contain the type name, the asset tag (loans) and `due_at` or `starts_at`. Notifications get a nullable `equipment_loan_id` and `equipment_reservation_id`. Fees created by this module also notify as `fee_created`. |
| LIB-EQ-39 | **Audit.** Module 16 reports to the audit log: `equipment_type_created`, `equipment_type_updated`, `equipment_item_created`, `equipment_item_updated`, `equipment_item_retired`, `equipment_item_repaired`, `equipment_training_recorded`, `equipment_loan_created`, `equipment_loan_extended`, `equipment_loan_returned`, `equipment_loan_lost`, `equipment_reservation_created`, `equipment_reservation_cancelled`, `equipment_reservation_expired`, `equipment_processed`. |
| LIB-EQ-40 | **Usage report.** `GET /api/v1/reports/equipment-usage?from=&to=&branch_id=` (dates inclusive, `from` ≤ `to`, at most 366 days; otherwise `422`) returns a paginated list ordered by type `code`, one item per type (all types, also inactive ones and those without activity): `{"type_id", "type_code", "loans", "late_returns", "late_hours", "damaged_returns", "lost", "reservations", "expired_reservations", "fees_created"}`. `loans`: loans by the date of `loaned_at`; `late_returns`, `late_hours` and `damaged_returns`: returned loans by the date of `returned_at` with `late_hours` > 0 (count and sum of `late_hours`) and with `return_condition` `damaged`; `lost`: loans reported lost on a date in the range; `reservations` (any status) and `expired_reservations`: by the date of `starts_at`; `fees_created`: sum (amount) of the fees of the type's loans with `created_on` in the range. With `branch_id`, only loans and reservations of that branch. |
| LIB-EQ-41 | **Not exported.** Equipment data is not part of import and export (module 13). |

### 24.10 Error codes of module 16

| HTTP status | Code | Requirement |
| --- | --- | --- |
| 409 | `DESK_CLOSED` | LIB-EQ-13, LIB-EQ-28 |
| 409 | `TYPE_INACTIVE` | LIB-EQ-05, LIB-EQ-13, LIB-EQ-28 |
| 409 | `EQUIPMENT_NOT_ALLOWED_FOR_TYPE` | LIB-EQ-13, LIB-EQ-28 |
| 409 | `TRAINING_REQUIRED` | LIB-EQ-13, LIB-EQ-28 |
| 409 | `TRAINING_NOT_REQUIRED` | LIB-EQ-11 |
| 409 | `EQUIPMENT_LIMIT_REACHED` | LIB-EQ-13 |
| 409 | `TYPE_LIMIT_REACHED` | LIB-EQ-13 |
| 409 | `ITEM_NOT_AVAILABLE` | LIB-EQ-13, LIB-EQ-29 |
| 409 | `ITEM_NEEDED_FOR_RESERVATION` | LIB-EQ-08, LIB-EQ-10, LIB-EQ-13, LIB-EQ-19 |
| 409 | `INVALID_ITEM_STATUS` | LIB-EQ-08, LIB-EQ-10 |
| 409 | `EXTENSION_LIMIT_REACHED` | LIB-EQ-19 |
| 409 | `EXTENSION_NOT_POSSIBLE` | LIB-EQ-19 |
| 409 | `DAMAGE_FEE_EXCEEDS_VALUE` | LIB-EQ-21 |
| 409 | `RESERVATION_TOO_SOON` | LIB-EQ-28 |
| 409 | `RESERVATION_TOO_FAR_AHEAD` | LIB-EQ-28 |
| 409 | `EQUIPMENT_RESERVATION_LIMIT_REACHED` | LIB-EQ-28 |
| 409 | `DUPLICATE_EQUIPMENT_RESERVATION` | LIB-EQ-28 |
| 409 | `NO_EQUIPMENT_AVAILABLE` | LIB-EQ-28 |
| 409 | `RESERVATION_NOT_READY` | LIB-EQ-29 |
| 409 | `RESERVATION_EXPIRED` | LIB-EQ-29 |
| 409 | `RESERVATION_OF_OTHER_MEMBER` | LIB-EQ-29 |

`MEMBER_PASSIVE`, `MEMBERSHIP_EXPIRED`, `MEMBER_HAS_OVERDUE`, `MEMBER_BLOCKED_BY_DEBT`, `BRANCH_INACTIVE`, `LOAN_NOT_OPEN`, `LOAN_OVERDUE`, `RESERVATION_NOT_ACTIVE` and `CONFLICT` keep their meaning from earlier sections.

---

## 25. Module 17: Digital resources

The library licenses e-books, which members borrow for a number of days, and online databases, which members use in sessions of one hour. Package `lms.digital`. Times are local (LIB-COM-01); date-times follow LIB-COM-03 and LIB-COM-04. Digital loans have no late fees: they end by themselves.

### 25.1 Data

**Digital resource**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `kind` | `ebook` \| `database` | Cannot be changed |
| `title` | text | LIB-COM-16 |
| `provider` | text | 1–100 characters |
| `book_id` | integer or null | An existing book; only for `ebook` (`422` for `database`) |
| `loan_days` | integer or null | `ebook`: 1–21, default 14; `database`: null (`422` if given) |
| `is_active` | boolean | Default `true` |
| `created_at` | date-time | From the clock |

**License**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `resource_id` | integer | Existing resource |
| `model` | `perpetual` \| `subscription` | |
| `copies` | integer | `ebook`: 1–100 copies; `database`: 1–500 concurrent seats |
| `starts_on` | date | Any date |
| `ends_on` | date or null | `perpetual`: null (`422` if given); `subscription`: required, ≥ `starts_on` |
| `cost` | amount | 0.00–1000000.00 |
| `order_id` | integer or null | A purchase order (module 12), LIB-DIG-06 |
| `cancelled_on` | date or null | Set by LIB-DIG-07 |
| `status` | derived | `cancelled` if `cancelled_on` is set; otherwise `pending` if today < `starts_on`, `ended` if `ends_on` < today, else `active` |

A license *counts on date `d`* when `starts_on` ≤ `d`, (`ends_on` is null or `d` ≤ `ends_on`) and (`cancelled_on` is null or `d` < `cancelled_on`). The **capacity** of a resource at a moment `t` is the sum of `copies` of its licenses that count on the date of `t`.

**Digital loan (e-books)**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `resource_id`, `member_id` | integer | |
| `hold_id` | integer or null | The hold this loan fulfils |
| `borrowed_at` | date-time | From the clock |
| `due_at` | date-time | `borrowed_at` + `loan_days` × 24 hours |
| `renewed` | boolean | LIB-DIG-21 |
| `renewed_at` | date-time or null | Time of the renewal |
| `status` | `open` \| `returned` \| `expired` | |
| `ended_at` | date-time or null | Return time, or `due_at` for `expired` |

An `open` loan with now ≥ `due_at` is *finished*: it no longer uses a copy, cannot be returned or renewed, and is shown with `status` `expired` and `ended_at` = `due_at` in every response, also before LIB-DIG-35 stores this.

**Hold (e-books)**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `resource_id`, `member_id` | integer | |
| `status` | `waiting` \| `ready` \| `fulfilled` \| `cancelled` \| `expired` | Initially `waiting` |
| `created_at` | date-time | From the clock |
| `ready_at`, `ready_until` | date-time or null | Set when `ready`; `ready_until` = `ready_at` + 48 hours |
| `closed_at` | date-time or null | |
| `cancel_reason` | text or null | `member_request`, `staff_request`, `member_deactivated`, `resource_inactive` |
| `position` | integer or null | Derived: for `waiting`, 1 + the number of `waiting` holds of the resource created earlier (ties by `id`); null otherwise |

A `ready` hold with now > `ready_until` is *lapsed*: it no longer keeps a copy and cannot be used, also before LIB-DIG-35 marks it `expired`.

**Session (databases)**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `resource_id`, `member_id` | integer | |
| `started_at` | date-time | From the clock |
| `expires_at` | date-time | `started_at` + 60 minutes |
| `closed_at` | date-time or null | Set by LIB-DIG-03, LIB-DIG-29 or LIB-DIG-37 |

A session is *open* at `t` when `closed_at` is null and `t` < `expires_at`.

**Counts used by the rules.** For an e-book at moment `t`: *active loans* = `open` loans with `t` < `due_at`; *kept copies* = `ready` holds that are not lapsed; *waiting* = `waiting` holds. **Free copies** = capacity − active loans − kept copies − waiting, never below 0. For a database: **free seats** = capacity − open sessions, never below 0.

### 25.2 Rules by membership type

| Type | Open digital loans | Holds (`waiting` + `ready`) | Database sessions at the same time |
| --- | --- | --- | --- |
| `student` | 5 | 5 | 1 |
| `academic` | 10 | 10 | 2 |
| `staff` | 5 | 5 | 1 |
| `guest` | 0 | 0 | 0 |

### 25.3 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/digital-resources`, `PATCH /api/v1/digital-resources/{resource_id}` | librarian, admin | Create, change |
| `GET /api/v1/digital-resources`, `GET /api/v1/digital-resources/{resource_id}` | all authenticated users | Read, with availability |
| `GET /api/v1/books/{book_id}/digital-resources` | all authenticated users | E-books of a book |
| `POST /api/v1/digital-resources/{resource_id}/licenses` | admin | Add a license |
| `GET /api/v1/digital-resources/{resource_id}/licenses` | librarian, admin | Licenses of a resource |
| `PATCH /api/v1/digital-licenses/{license_id}`, `POST /api/v1/digital-licenses/{license_id}/cancel`, `POST /api/v1/digital-licenses/{license_id}/renew` | admin | Change, cancel, renew a license |
| `GET /api/v1/digital-licenses` | librarian, admin | Subscriptions ending soon |
| `GET /api/v1/digital-resources/{resource_id}/calendar` | all authenticated users | Capacity per day |
| `POST /api/v1/digital-loans` | member (own), librarian, admin | Borrow an e-book |
| `GET /api/v1/digital-loans`, `GET /api/v1/digital-loans/{loan_id}` | librarian, admin; member (own, single) | Read |
| `GET /api/v1/members/{member_id}/digital-loans` | librarian, admin; member (own) | Loans of a member |
| `POST /api/v1/digital-loans/{loan_id}/return`, `/renew` | member (own), librarian, admin | Return early, renew |
| `POST /api/v1/digital-holds` | member (own), librarian, admin | Place a hold |
| `GET /api/v1/digital-resources/{resource_id}/holds` | librarian, admin | Hold queue of a resource |
| `GET /api/v1/members/{member_id}/digital-holds` | librarian, admin; member (own) | Holds of a member |
| `POST /api/v1/digital-holds/{hold_id}/cancel` | member (own), librarian, admin | Cancel a hold |
| `POST /api/v1/digital-sessions` | member (own), librarian, admin | Open a database session |
| `POST /api/v1/digital-sessions/{session_id}/close` | member (own), librarian, admin | Close a session |
| `GET /api/v1/members/{member_id}/digital-sessions` | librarian, admin; member (own) | Sessions of a member |
| `POST /api/v1/digital/process` | librarian, admin | Expire loans and holds, move the queues |
| `GET /api/v1/reports/digital-usage` | librarian, admin | Usage per resource (section 16) |

`member_id` in request bodies: a librarian or admin MUST send it; a member MUST NOT (`422`) and acts for themselves. A member acting on a loan, hold or session of another member receives `403 FORBIDDEN`.

### 25.4 Resources and licenses

| ID | Requirement |
| --- | --- |
| LIB-DIG-01 | **Create resource.** `POST /api/v1/digital-resources` with `{"kind", "title", "provider", "book_id", "loan_days"}` returns `201` (event `digital_resource_created`). `book_id` and `loan_days` MAY be omitted. Values outside 25.1 return `422 VALIDATION_ERROR`; an unknown `book_id` returns `422` with `details.fields` naming `book_id`. |
| LIB-DIG-02 | **Change resource.** `PATCH` accepts any subset of `{"title", "provider", "book_id", "loan_days", "is_active"}` and returns `200`. `kind` cannot be changed (`422`). A new `loan_days` applies to loans created afterwards. |
| LIB-DIG-03 | **Deactivate resource.** `{"is_active": false}` cancels every `waiting` and `ready` hold of the resource with reason `resource_inactive` (event `digital_hold_cancelled`) and closes its open sessions (`closed_at` = now). Open loans run until their `due_at`. An inactive resource cannot be borrowed, held or opened: `409 RESOURCE_INACTIVE`. |
| LIB-DIG-04 | **Read resources.** `GET /api/v1/digital-resources` is paginated, ordered by `title` (LIB-COM-30 comparison), then `id`. Filters: `kind`, `is_active`, `q` (case-insensitive substring of `title` or `provider`), `book_id`. Each item and the single resource contain `capacity` (now), `in_use` (e-book: active loans; database: open sessions), `available` (e-book: free copies; database: free seats) and `waiting_holds` (e-book: number of `waiting` holds; database: 0). |
| LIB-DIG-05 | **Add license.** `POST /api/v1/digital-resources/{resource_id}/licenses` with `{"model", "copies", "starts_on", "ends_on", "cost", "order_id"}` returns `201` with the license and its `status` (event `digital_license_added`). `ends_on` and `order_id` MAY be omitted. Values outside 25.1 return `422 VALIDATION_ERROR`. A license may be added to an inactive resource. |
| LIB-DIG-06 | **License and order.** `order_id` MUST be an existing purchase order (`422` otherwise) with status `ordered`, `partially_received` or `received`; a `draft` or `cancelled` order returns `409 INVALID_ORDER_STATUS`. A purchase order referenced by a license cannot be cancelled: LIB-PUR-05 returns `409 ORDER_HAS_LICENSE`. |
| LIB-DIG-07 | **Cancel license.** `POST /api/v1/digital-licenses/{license_id}/cancel` sets `cancelled_on` = today and returns `200` (event `digital_license_cancelled`). An already cancelled or `ended` license returns `409 INVALID_LICENSE_STATUS`. Open loans and sessions are not ended; the lower capacity applies to new loans, holds becoming ready and sessions. |
| LIB-DIG-08 | **License list.** `GET /api/v1/digital-resources/{resource_id}/licenses` is paginated, ordered by `starts_on`, then `id`, filter `status`. The resource of a license is read with `resource_id`. |
| LIB-DIG-09 | **E-books of a book.** `GET /api/v1/books/{book_id}/digital-resources` returns `200` with the active e-books of that book in the format of LIB-DIG-04 (not paginated, ordered by `id`); an unknown book returns `404 NOT_FOUND`. |
| LIB-DIG-10 | **Change license.** `PATCH /api/v1/digital-licenses/{license_id}` (admin) accepts any subset of `{"copies", "cost", "ends_on"}` and returns `200`. `copies` and `cost` can only be changed while the license is `pending`, and `ends_on` only while it is `pending` or `active`; otherwise `409 INVALID_LICENSE_STATUS`. The new `ends_on` of a `subscription` MUST be ≥ today and ≥ `starts_on` (`422` otherwise); a `perpetual` license has no `ends_on` (`422`). |
| LIB-DIG-11 | **Renew subscription.** `POST /api/v1/digital-licenses/{license_id}/renew` with `{"ends_on", "cost", "order_id"}` on a `subscription` that is `active` or `ended` creates a new `subscription` license of the same resource with the same `copies`, `starts_on` = the old `ends_on` + 1 day and the given `ends_on` (≥ the new `starts_on`, otherwise `422`), and returns `201` (event `digital_license_added`). A `perpetual` license → `409 NOT_A_SUBSCRIPTION`; a `cancelled` or `pending` one → `409 INVALID_LICENSE_STATUS`; a license already renewed (a license of the resource that is not cancelled has `starts_on` = its `ends_on` + 1 day) → `409 ALREADY_RENEWED`. `order_id` follows LIB-DIG-06. |
| LIB-DIG-12 | **Expiring subscriptions.** `GET /api/v1/digital-licenses?ending_within_days=<n>` (librarian, admin; `n` 1–365, default 30) returns the `active` subscriptions with today ≤ `ends_on` ≤ today + `n` days that are not renewed (LIB-DIG-11), paginated, ordered by `ends_on`, then `id`; each item also has `resource_title`. |
| LIB-DIG-13 | **Availability calendar.** `GET /api/v1/digital-resources/{resource_id}/calendar?from=&to=` (all authenticated users; at most 92 days, `from` ≤ `to`, otherwise `422`) returns `200` with `{"resource_id", "days": [{"date", "capacity"}]}`, one item per date with the capacity of that date (licenses only; loans are not considered). |
| LIB-DIG-14 | **Capacity examples.** A perpetual license of 2 copies from 2026-11-01 and a subscription of 3 copies from 2026-11-01 to 2026-11-30: capacity 5 on 2026-11-30, 2 on 2026-12-01. A subscription from 2026-11-10: not counted on 2026-11-09 (`status` `pending`). A license cancelled on 2026-11-04 counts on 2026-11-03 and not on 2026-11-04. |

### 25.5 E-book loans

| ID | Requirement |
| --- | --- |
| LIB-DIG-15 | **Borrow.** `POST /api/v1/digital-loans` with `{"resource_id"}` (member) or `{"resource_id", "member_id"}` (staff) creates an `open` loan and returns `201` (event `digital_loan_created`). If the member has a `ready` hold for the resource that is not lapsed, the loan fulfils it: the hold becomes `fulfilled` with `closed_at` = now, and the loan gets `hold_id`. |
| LIB-DIG-16 | **Borrow checks.** In order (all `409` unless stated): (1) the resource is a database → `WRONG_RESOURCE_KIND`; (2) resource inactive → `RESOURCE_INACTIVE`; (3) member `passive` → `MEMBER_PASSIVE`; (4) membership not valid today → `MEMBERSHIP_EXPIRED`; (5) `guest` → `DIGITAL_NOT_ALLOWED_FOR_TYPE`; (6) total debt (LIB-FEE-09) ≥ 50.00 → `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt`; (7) the member has an active loan of the resource → `ALREADY_BORROWED`; (8) active loans of the member ≥ the limit of 25.2 → `DIGITAL_LOAN_LIMIT_REACHED` with `details.limit`; (9) capacity now is 0 → `NO_ACTIVE_LICENSE`; (10) without a usable `ready` hold of the member: free copies = 0 → `NO_COPY_AVAILABLE` with `details.waiting` (number of `waiting` holds). With a usable `ready` hold, (10) is not checked. |
| LIB-DIG-17 | **Due time.** `due_at` = `borrowed_at` + `loan_days` × 24 hours, with seconds kept. Example: borrowed Mon 2026-11-02 09:00 with 14 days → due Mon 2026-11-16 09:00. Weekends and holidays do not matter. |
| LIB-DIG-18 | **End of a loan.** At `due_at` the loan is finished (25.1): at `due_at` − 1 second it is still active, at `due_at` it no longer uses a copy. A finished loan does not count for limits (LIB-DIG-16 (7), (8)). |
| LIB-DIG-19 | **Return early.** `POST /api/v1/digital-loans/{loan_id}/return` on an active loan sets `status` `returned`, `ended_at` = now and returns `200` (event `digital_loan_returned`); then LIB-DIG-26 runs. A loan that is not active returns `409 LOAN_NOT_OPEN`. |
| LIB-DIG-20 | **Read loans.** Lists are paginated, ordered by `borrowed_at`, then `id`; filters `status` (as shown, 25.1), `resource_id`; the general list also `member_id`. |
| LIB-DIG-21 | **Renew.** `POST /api/v1/digital-loans/{loan_id}/renew` sets `due_at` = `due_at` + `loan_days` × 24 hours (the resource's current `loan_days`), sets `renewed` and `renewed_at` = now and returns `200` (event `digital_loan_renewed`). Checks in order (all `409`): loan not active → `LOAN_NOT_OPEN`; already renewed → `RENEWAL_LIMIT_REACHED`; now < `due_at` − 72 hours → `RENEWAL_TOO_EARLY` with `details.renewable_from`; the resource has `waiting` holds → `RESOURCE_HAS_HOLDS`; capacity now is 0 → `NO_ACTIVE_LICENSE`. |

### 25.6 Holds

| ID | Requirement |
| --- | --- |
| LIB-DIG-22 | **Place hold.** `POST /api/v1/digital-holds` with `{"resource_id"}` (member) or `{"resource_id", "member_id"}` (staff) creates a `waiting` hold and returns `201` with its `position` (event `digital_hold_created`). |
| LIB-DIG-23 | **Hold checks.** LIB-DIG-16 (1)–(7) in that order, then (all `409`): the member has a `waiting` or not lapsed `ready` hold of the resource → `DUPLICATE_HOLD`; holds of the member (`waiting` and not lapsed `ready`) ≥ the limit of 25.2 → `DIGITAL_HOLD_LIMIT_REACHED` with `details.limit`; capacity now is 0 → `NO_ACTIVE_LICENSE`; free copies > 0 → `HOLD_NOT_NEEDED` (the member can borrow now). |
| LIB-DIG-24 | **Queue.** The waiting holds of a resource form a queue ordered by `created_at`, then `id`. `GET /api/v1/digital-resources/{resource_id}/holds` returns it paginated with `status=waiting` by default; filter `status`. `GET /api/v1/members/{member_id}/digital-holds` returns the member's holds of every status, paginated, ordered by `created_at`, then `id`; filter `status`. A `ready` hold that is lapsed keeps `status` `ready` until LIB-DIG-35. |
| LIB-DIG-25 | **Cancel hold.** `cancel` sets a `waiting` or `ready` hold to `cancelled` with `member_request` (member) or `staff_request` (staff), `closed_at` = now, `200` (event `digital_hold_cancelled`). Other statuses or a lapsed `ready` hold → `409 HOLD_NOT_ACTIVE`. Cancelling a `ready` hold runs LIB-DIG-26. |
| LIB-DIG-26 | **Move the queue.** After a return (LIB-DIG-19), a cancelled `ready` hold (LIB-DIG-25), a new or changed license (LIB-DIG-05, LIB-DIG-10, LIB-DIG-11) and in LIB-DIG-35, while the resource is active, has `waiting` holds and capacity − active loans − kept copies > 0, the first waiting hold becomes `ready` with `ready_at` = now and `ready_until` = now + 48 hours (event `digital_hold_ready`). This repeats until one of the conditions fails. |
| LIB-DIG-27 | **Ready hold.** Only the member of a `ready` hold that is not lapsed can borrow the kept copy (LIB-DIG-15). Example: hold ready at Tue 10:00 → usable until Thu 10:00 inclusive; at Thu 10:00:01 lapsed. |

### 25.7 Database sessions

| ID | Requirement |
| --- | --- |
| LIB-DIG-28 | **Open session.** `POST /api/v1/digital-sessions` with `{"resource_id"}` (member) or `{"resource_id", "member_id"}` (staff) returns `201` with the session (`expires_at` = `started_at` + 60 minutes, event `digital_session_opened`). Checks in order (all `409`): the resource is an e-book → `WRONG_RESOURCE_KIND`; LIB-DIG-16 (2)–(6); the member has an open session of this resource → `SESSION_ALREADY_OPEN` with `details.session_id`; open sessions of the member ≥ the limit of 25.2 → `SESSION_LIMIT_REACHED` with `details.limit`; capacity now is 0 → `NO_ACTIVE_LICENSE`; free seats = 0 → `NO_SEAT_AVAILABLE` with `details.next_free_at` (the earliest `expires_at` of the open sessions). |
| LIB-DIG-29 | **Close session.** `close` on an open session sets `closed_at` = now and returns `200`; a session that is not open returns `409 SESSION_NOT_OPEN`. |
| LIB-DIG-30 | **Daily sessions.** A member can open at most 6 sessions per resource per calendar day (counted by the date of `started_at`, closed ones included); the 7th returns `409 DAILY_SESSION_LIMIT_REACHED` (checked after `SESSION_ALREADY_OPEN`). |
| LIB-DIG-31 | **End of a session.** At `expires_at` the session stops counting. Example: opened 10:00 → open at 10:59:59, not open at 11:00. Sessions are not stored as closed by LIB-DIG-35; their responses show `closed_at` null and `open` (boolean, derived). |
| LIB-DIG-32 | **Session lists.** `GET /api/v1/members/{member_id}/digital-sessions` is paginated, ordered by `started_at` descending, then `id` descending; filter `open` (`true`/`false`), `resource_id`. |

### 25.8 Processing and effects on other modules

| ID | Requirement |
| --- | --- |
| LIB-DIG-33 | **Notifications.** Added to LIB-NOT-01: `digital_hold_ready` (contains the title and `ready_until`), `digital_hold_expired`, `digital_hold_cancelled` (reasons `staff_request`, `member_deactivated`, `resource_inactive`), `digital_loan_expired` (by LIB-DIG-35), `digital_loan_due_soon` (LIB-DIG-34). Notifications get a nullable `digital_loan_id` and `digital_hold_id`. Borrowing, returning, renewing and sessions do not notify. |
| LIB-DIG-34 | **Due soon.** LIB-DIG-35 also creates one `digital_loan_due_soon` notification for every active digital loan with now < `due_at` ≤ now + 24 hours, at most one per loan however often it runs. LIB-NOT-05 is not changed. |
| LIB-DIG-35 | **Process.** `POST /api/v1/digital/process` (1) stores every finished open loan as `expired` with `ended_at` = `due_at` (event `digital_loan_expired`), in order of `due_at`, then `id`; (2) stores every lapsed `ready` hold as `expired` with `closed_at` = now (event `digital_hold_expired`); (3) runs LIB-DIG-26 for every active resource in order of `id`. It returns `200` with `{"expired_loans", "expired_holds", "holds_ready", "due_soon_notices"}` (counts of this call; `due_soon_notices` from LIB-DIG-34). |
| LIB-DIG-36 | **Member summary.** LIB-MEM-12 also returns `"digital": {"open_loans": <int>, "waiting_holds": <int>, "ready_holds": <int>}` (active loans; not lapsed `ready` holds). Digital loans and holds do not change `borrowing`. |
| LIB-DIG-37 | **Member deactivation.** LIB-MEM-10 is not blocked by digital loans. It returns the member's active loans (`returned`, `ended_at` = now), cancels the `waiting` and `ready` holds with reason `member_deactivated` and closes open sessions; then LIB-DIG-26 runs for the affected resources. |
| LIB-DIG-38 | **Audit.** Module 17 reports to the audit log: `digital_resource_created`, `digital_resource_updated`, `digital_license_added`, `digital_license_cancelled`, `digital_loan_created`, `digital_loan_returned`, `digital_loan_renewed`, `digital_loan_expired`, `digital_hold_created`, `digital_hold_ready`, `digital_hold_cancelled`, `digital_hold_expired`, `digital_session_opened`, `digital_processed`. Session closing is not audited. |
| LIB-DIG-39 | **Usage report.** `GET /api/v1/reports/digital-usage?from=&to=&kind=` (dates inclusive, `from` ≤ `to`, at most 366 days; otherwise `422`) returns a paginated list ordered by `title`, then `id`, one item per resource (also inactive ones and those without activity): `{"resource_id", "kind", "title", "loans", "renewals", "holds_placed", "holds_expired", "sessions", "license_cost"}`. `loans` and `sessions` are counted by the date of `borrowed_at` and `started_at`, `renewals` by the date of `renewed_at`, `holds_placed` by the date of `created_at`, `holds_expired` (holds with `status` `expired`) by the date of `closed_at`; `license_cost` sums `cost` of licenses with `starts_on` in the range. |
| LIB-DIG-40 | **Not exported.** Digital data is not part of import and export (module 13). |

### 25.9 Error codes of module 17

| HTTP status | Code | Requirement |
| --- | --- | --- |
| 409 | `WRONG_RESOURCE_KIND` | LIB-DIG-16, LIB-DIG-28 |
| 409 | `RESOURCE_INACTIVE` | LIB-DIG-03, LIB-DIG-16 |
| 409 | `DIGITAL_NOT_ALLOWED_FOR_TYPE` | LIB-DIG-16 |
| 409 | `ALREADY_BORROWED` | LIB-DIG-16 |
| 409 | `DIGITAL_LOAN_LIMIT_REACHED` | LIB-DIG-16 |
| 409 | `NO_ACTIVE_LICENSE` | LIB-DIG-16, LIB-DIG-21, LIB-DIG-23, LIB-DIG-28 |
| 409 | `NO_COPY_AVAILABLE` | LIB-DIG-16 |
| 409 | `RENEWAL_LIMIT_REACHED` | LIB-DIG-21 |
| 409 | `RENEWAL_TOO_EARLY` | LIB-DIG-21 |
| 409 | `RESOURCE_HAS_HOLDS` | LIB-DIG-21 |
| 409 | `DUPLICATE_HOLD` | LIB-DIG-23 |
| 409 | `DIGITAL_HOLD_LIMIT_REACHED` | LIB-DIG-23 |
| 409 | `HOLD_NOT_NEEDED` | LIB-DIG-23 |
| 409 | `HOLD_NOT_ACTIVE` | LIB-DIG-25 |
| 409 | `SESSION_ALREADY_OPEN` | LIB-DIG-28 |
| 409 | `SESSION_LIMIT_REACHED` | LIB-DIG-28 |
| 409 | `NO_SEAT_AVAILABLE` | LIB-DIG-28 |
| 409 | `SESSION_NOT_OPEN` | LIB-DIG-29 |
| 409 | `INVALID_LICENSE_STATUS` | LIB-DIG-07, LIB-DIG-10, LIB-DIG-11 |
| 409 | `NOT_A_SUBSCRIPTION` | LIB-DIG-11 |
| 409 | `ALREADY_RENEWED` | LIB-DIG-11 |
| 409 | `DAILY_SESSION_LIMIT_REACHED` | LIB-DIG-30 |
| 409 | `ORDER_HAS_LICENSE` | LIB-DIG-06 |

`MEMBER_PASSIVE`, `MEMBERSHIP_EXPIRED`, `MEMBER_BLOCKED_BY_DEBT`, `LOAN_NOT_OPEN` and `INVALID_ORDER_STATUS` keep their meaning from earlier sections.

---

## 26. Module 18: Interlibrary loans

The library borrows books it does not have from partner libraries for its members (**incoming** requests) and lends its own copies to partner libraries (**outgoing** requests). Package `lms.ill`. Dates are local dates (LIB-COM-01); amounts follow LIB-COM-12.

### 26.1 Data

**Partner**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `code` | text | 2–10 characters `[A-Z0-9]`, stored in upper case, unique |
| `name` | text | LIB-COM-16 |
| `email` | text | LIB-COM-17 |
| `request_fee` | amount | 0.00–50.00; charged to the member per incoming request (LIB-ILL-14) |
| `daily_late_fee` | amount | 0.00–10.00 per day (LIB-ILL-18) |
| `max_outgoing` | integer | 1–20; open outgoing requests of this partner (LIB-ILL-27) |
| `is_active` | boolean | Default `true` |

**Incoming request**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `member_id` | integer | |
| `title` | text | LIB-COM-16 |
| `author` | text | 1–200 characters |
| `isbn` | text or null | Normalized as LIB-CAT-02 when given |
| `status` | see 26.2 | Initially `requested` |
| `partner_id` | integer or null | The partner it was last sent to |
| `tried_partner_ids` | list of integers | Partners it was sent to, in order |
| `pickup_branch_id` | integer or null | Set on receipt |
| `received_on`, `collect_until` | date or null | `collect_until` = `received_on` + 7 days |
| `partner_due_on`, `due_on` | date or null | LIB-ILL-12 |
| `replacement_cost` | amount or null | Given by the partner on receipt |
| `renewal` | `none` \| `requested` \| `approved` \| `refused` | Default `none` |
| `collected_on`, `returned_on`, `closed_on` | date or null | |
| `cancel_reason`, `reject_reason` | text or null | `cancel_reason`: `member_request`, `staff_request`, `member_deactivated` |
| `created_at` | date-time | From the clock |

An incoming request with `status` `on_loan` is **overdue** when today > `due_on`. The API representation of an incoming request has all fields above except the stored fees, plus `overdue` (boolean) and `accrued_late_fee` (amount: the fee of LIB-ILL-18 if it were returned today; `"0.00"` when not overdue).

**Outgoing request**

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | LIB-COM-14 |
| `partner_id`, `book_id` | integer | Active partner, existing book |
| `status` | `requested` \| `shipped` \| `declined` \| `returned` \| `lost` | Initially `requested` |
| `copy_id` | integer or null | Set when shipped |
| `shipped_on`, `due_on`, `returned_on` | date or null | `due_on` = `shipped_on` + 28 days |
| `amount_due` | amount or null | Set when lost: the copy's `price` |
| `created_at` | date-time | From the clock |

An outgoing request with `status` `shipped` is **overdue** when today > `due_on`.

### 26.2 Status of an incoming request

| Status | Meaning | Next statuses |
| --- | --- | --- |
| `requested` | Made by or for the member | `sent`, `cancelled` |
| `sent` | Sent to a partner | `received`, `rejected`, `cancelled` |
| `rejected` | The partner said no | `sent` (to another partner), `cancelled` |
| `received` | The book arrived and waits at the pickup branch | `on_loan`, `uncollected` |
| `on_loan` | The member has the book | `returned`, `lost` |
| `returned` | The member returned it; not yet sent back | `closed` |
| `uncollected` | Not collected within 7 days | `closed` |
| `closed`, `cancelled`, `lost` | Final | – |

A request is **open** in the statuses `requested`, `sent`, `rejected`, `received` and `on_loan`. A wrong transition returns `409 INVALID_ILL_STATUS` with `details.status`.

### 26.3 Rules by membership type

| Type | Open incoming requests |
| --- | --- |
| `student` | 2 |
| `academic` | 5 |
| `staff` | 2 |
| `guest` | 0 (not allowed) |

### 26.4 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/v1/ill-partners`, `PATCH /api/v1/ill-partners/{partner_id}` | admin | Create, change |
| `GET /api/v1/ill-partners`, `GET /api/v1/ill-partners/{partner_id}` | librarian, admin | Read |
| `POST /api/v1/ill-requests` | member (own), librarian, admin | New incoming request |
| `GET /api/v1/ill-requests`, `GET /api/v1/ill-requests/{request_id}` | librarian, admin; member (own, single) | Read |
| `GET /api/v1/members/{member_id}/ill-requests` | librarian, admin; member (own) | Requests of a member |
| `POST /api/v1/ill-requests/{request_id}/send`, `/reject`, `/receive`, `/collect`, `/return`, `/close`, `/report-lost`, `/renewal-answer` | librarian, admin | Staff steps |
| `POST /api/v1/ill-requests/{request_id}/cancel`, `/renewal-request` | member (own), librarian, admin | Cancel, ask for more time |
| `POST /api/v1/ill-outgoing` | librarian, admin | New outgoing request |
| `GET /api/v1/ill-outgoing`, `GET /api/v1/ill-outgoing/{outgoing_id}` | librarian, admin | Read |
| `POST /api/v1/ill-outgoing/{outgoing_id}/ship`, `/decline`, `/returned`, `/report-lost` | librarian, admin | Outgoing steps |
| `POST /api/v1/ill/process` | librarian, admin | Mark uncollected requests |
| `GET /api/v1/reports/ill-activity` | librarian, admin | Activity per partner (section 16) |

`member_id` in `POST /api/v1/ill-requests`: a librarian or admin MUST send it; a member MUST NOT (`422`).

### 26.5 Partners

| ID | Requirement |
| --- | --- |
| LIB-ILL-01 | **Create partner.** `POST /api/v1/ill-partners` with `{"code", "name", "email", "request_fee", "daily_late_fee", "max_outgoing"}` returns `201` (event `ill_partner_created`). Values outside 26.1 return `422 VALIDATION_ERROR`; a duplicate `code` returns `409 CONFLICT` with `details.field` `"code"`. |
| LIB-ILL-02 | **Change partner.** `PATCH` accepts any subset of `{"name", "email", "request_fee", "daily_late_fee", "max_outgoing", "is_active"}` and returns `200`; `code` cannot be changed (`422`). A changed `request_fee` or `daily_late_fee` applies to requests sent afterwards: the request keeps the values of the partner at the time it was sent (stored with the request, not returned). |
| LIB-ILL-03 | **Inactive partner.** An inactive partner cannot be chosen for `send` or a new outgoing request: `409 PARTNER_INACTIVE`. Requests already sent to it continue. |
| LIB-ILL-04 | **Read partners.** `GET /api/v1/ill-partners` is paginated, ordered by `code`, with filters `is_active` and `q` (case-insensitive substring of `code` or `name`). Each item has `open_incoming` (open incoming requests last sent to it with status `sent`, `received`, `on_loan`) and `open_outgoing` (outgoing requests `requested` or `shipped`). |

### 26.6 Incoming requests

| ID | Requirement |
| --- | --- |
| LIB-ILL-05 | **New request.** `POST /api/v1/ill-requests` with `{"title", "author", "isbn"}` (member) or with `member_id` (staff) returns `201` with `status` `requested` (event `ill_request_created`). `isbn` MAY be omitted; an invalid ISBN returns `422`. |
| LIB-ILL-06 | **Request checks.** In order (all `409`): (1) member `passive` → `MEMBER_PASSIVE`; (2) membership not valid today → `MEMBERSHIP_EXPIRED`; (3) `guest` → `ILL_NOT_ALLOWED_FOR_TYPE`; (4) total debt (LIB-FEE-09) ≥ 50.00 → `MEMBER_BLOCKED_BY_DEBT` with `details.total_debt`; (5) the member has an overdue book loan (LIB-LOAN-02) or an overdue incoming request → `MEMBER_HAS_OVERDUE`; (6) open incoming requests of the member ≥ the limit of 26.3 → `ILL_LIMIT_REACHED` with `details.limit`; (7) `isbn` is the ISBN of a book in the catalog that has a copy with status `available` → `AVAILABLE_LOCALLY` with `details.book_id`; (8) the member has an open request with the same `isbn` → `DUPLICATE_ILL_REQUEST`. A book in the catalog without an available copy can be requested. |
| LIB-ILL-07 | **Send.** `send` with `{"partner_id"}` on a `requested` or `rejected` request sets `status` `sent`, `partner_id`, appends the partner to `tried_partner_ids`, stores the partner's `request_fee` and `daily_late_fee` with the request and returns `200` (event `ill_request_sent`). Checks in order: status → `INVALID_ILL_STATUS`; partner inactive → `PARTNER_INACTIVE`; partner already in `tried_partner_ids` → `409 PARTNER_ALREADY_TRIED`; `tried_partner_ids` already has 3 partners → `409 ILL_TRY_LIMIT_REACHED`. |
| LIB-ILL-08 | **Reject.** `reject` with `{"reason"}` (1–200 characters) on a `sent` request sets `status` `rejected`, `reject_reason` and returns `200` (event `ill_request_rejected`). The member is notified. |
| LIB-ILL-09 | **Cancel.** `cancel` on a `requested`, `sent` or `rejected` request sets `status` `cancelled`, `cancel_reason` `member_request` (member) or `staff_request` (staff), `closed_on` = today and returns `200` (event `ill_request_cancelled`). Other statuses → `INVALID_ILL_STATUS`. Only `staff_request` and `member_deactivated` notify the member. |
| LIB-ILL-10 | **Receive.** `receive` with `{"partner_due_on", "replacement_cost", "pickup_branch_id"}` on a `sent` request sets `status` `received`, `received_on` = today, `collect_until` = today + 7 days, `partner_due_on`, `due_on` (LIB-ILL-12), `replacement_cost` (0.01–100000.00), `pickup_branch_id` (active branch, `409 BRANCH_INACTIVE` otherwise) and returns `200` (event `ill_request_received`, notifies the member). |
| LIB-ILL-11 | **Too short.** If `due_on` (LIB-ILL-12) is earlier than today + 7 days, `receive` returns `409 ILL_PERIOD_TOO_SHORT` with `details.due_on`. |
| LIB-ILL-12 | **Member due date.** `due_on` is the 3rd working day before `partner_due_on`: counting back from the day before `partner_due_on`, only working days (LIB-COM-05) count. Examples: `partner_due_on` Fri 2026-11-20 → `due_on` Tue 2026-11-17; Mon 2026-11-16 → Wed 2026-11-11; Mon 2026-11-02 → Tue 2026-10-27 (counting 30 Oct, 28 Oct, 27 Oct; 29 Oct is a holiday). |
| LIB-ILL-13 | **Collect.** `collect` on a `received` request with today ≤ `collect_until` sets `status` `on_loan`, `collected_on` = today and returns `200` (event `ill_request_collected`). The member checks of LIB-ILL-06 (1), (2), (4) and (5) apply; a member blocked by them keeps the book waiting. After `collect_until` → `409 ILL_COLLECT_PERIOD_OVER`. |
| LIB-ILL-14 | **Request fee.** On `collect`, if the stored `request_fee` > 0.00, a fee of kind `ill_request_fee` is created for the member with that amount and `ill_request_id` set. |
| LIB-ILL-15 | **Renewal request.** `renewal-request` on an `on_loan` request that is not overdue and has `renewal` `none` sets `renewal` `requested` and returns `200` (event `ill_renewal_requested`). Otherwise: not `on_loan` → `INVALID_ILL_STATUS`; overdue → `409 ILL_OVERDUE`; `renewal` not `none` → `409 ILL_RENEWAL_ALREADY_REQUESTED`. |
| LIB-ILL-16 | **Renewal answer.** `renewal-answer` with `{"approved": true, "partner_due_on"}` or `{"approved": false}` on a request with `renewal` `requested`: approved sets `renewal` `approved`, the new `partner_due_on` (later than the old one, `422` otherwise) and a new `due_on` (LIB-ILL-12); refused sets `renewal` `refused`. Returns `200` and notifies the member (`ill_renewal_answered`). `renewal` not `requested` → `409 ILL_NO_RENEWAL_REQUESTED`. |
| LIB-ILL-17 | **Return.** `return` with `{"branch_id"}` on an `on_loan` request sets `status` `returned`, `returned_on` = today and returns `200` (event `ill_request_returned`). A return at any active branch is accepted. |
| LIB-ILL-18 | **Late fee.** On `return`, if `returned_on` > `due_on`, a fee of kind `ill_late_fee` = days late × the stored `daily_late_fee` is created, at most `replacement_cost`. Days late = `returned_on` − `due_on` in calendar days. Example: due 2026-11-17, returned 2026-11-20, 2.50 per day → 7.50. |
| LIB-ILL-19 | **Overdue across modules.** An overdue incoming request blocks book lending (LIB-LOAN-05 step 3 `MEMBER_HAS_OVERDUE`) and counts in the debt: LIB-FEE-09 and `accrued_late_fees` of `BalanceOut` add, for every overdue incoming request, the late fee it would get if returned today. |
| LIB-ILL-20 | **Close.** `close` on a `returned` or `uncollected` request (the book went back to the partner) sets `status` `closed`, `closed_on` = today and returns `200` (event `ill_request_closed`). |
| LIB-ILL-21 | **Lost.** `report-lost` on an `on_loan` request sets `status` `lost`, `closed_on` = today, creates a fee of kind `ill_lost` = `replacement_cost` and, if overdue, the `ill_late_fee` of LIB-ILL-18 with today as return date, and returns `200` (event `ill_request_lost`). |
| LIB-ILL-22 | **Uncollected.** `POST /api/v1/ill/process` sets every `received` request with today > `collect_until` to `uncollected` (event `ill_request_uncollected`, notifies the member) in order of `id` and returns `200` with `{"uncollected": <count>, "overdue_outgoing": <count of shipped outgoing requests that are overdue today>}`. No fee is created for an uncollected book. |
| LIB-ILL-23 | **Read requests.** Lists are paginated, ordered by `created_at`, then `id`; filters `status`, `partner_id`, `overdue` (`true`/`false`); the general list also `member_id`. A member reading a request of another member receives `403 FORBIDDEN`. |

### 26.7 Outgoing requests

| ID | Requirement |
| --- | --- |
| LIB-ILL-24 | **New outgoing request.** `POST /api/v1/ill-outgoing` with `{"partner_id", "book_id"}` returns `201` with `status` `requested` (event `ill_outgoing_created`). Unknown book → `404 NOT_FOUND`; partner inactive → `409 PARTNER_INACTIVE`. |
| LIB-ILL-25 | **Ship.** `ship` with `{"copy_id"}` on a `requested` outgoing request sets `status` `shipped`, `copy_id`, `shipped_on` = today, `due_on` = today + 28 days and the copy's status to `at_partner`, and returns `200` (event `ill_outgoing_shipped`). Checks in order (all `409`): status → `INVALID_ILL_STATUS`; partner inactive → `PARTNER_INACTIVE`; the partner has an overdue outgoing request → `PARTNER_HAS_OVERDUE`; the copy is not of the requested book → `422`; the copy is not `available` → `INVALID_COPY_STATUS`. |
| LIB-ILL-26 | **Decline.** `decline` on a `requested` outgoing request sets `status` `declined` and returns `200`. |
| LIB-ILL-27 | **Limit.** A new outgoing request when the partner already has `max_outgoing` requests `requested` or `shipped` returns `409 PARTNER_LIMIT_REACHED` with `details.limit` (checked after `PARTNER_INACTIVE`). |
| LIB-ILL-28 | **Returned.** `returned` with `{"branch_id"}` on a `shipped` outgoing request sets `status` `returned`, `returned_on` = today; the copy becomes `available` with `current_branch_id` = `branch_id`; then the copy is released (LIB-RES-08). Returns `200` (event `ill_outgoing_returned`). |
| LIB-ILL-29 | **Lost by partner.** `report-lost` on a `shipped` outgoing request sets `status` `lost`, `amount_due` = the copy's `price`; the copy becomes `lost`. Returns `200` (event `ill_outgoing_lost`). No member fee is created. |
| LIB-ILL-30 | **Read outgoing.** `GET /api/v1/ill-outgoing` is paginated, ordered by `created_at`, then `id`, filters `status`, `partner_id`, `overdue`. Each item also has `book_title` and `barcode` (null before shipping). |

### 26.8 Effects on other modules

| ID | Requirement |
| --- | --- |
| LIB-ILL-31 | **Copy status.** 8.2 adds `at_partner` (lent to a partner, module 18; cannot be lent). Transitions: `available` → `at_partner`; `at_partner` → `available`, `lost`. A copy `at_partner` counts as not available in `BookOut.availability` and in search. |
| LIB-ILL-32 | **Member deactivation.** LIB-MEM-10 returns `409 MEMBER_HAS_OPEN_LOANS` when the member has an incoming request `received` or `on_loan`; it cancels the member's `requested`, `sent` and `rejected` requests with reason `member_deactivated`. |
| LIB-ILL-33 | **Branch deactivation.** LIB-BR-03 also rejects deactivation (`409 BRANCH_IN_USE`) when the branch is the `pickup_branch_id` of a `received` or `on_loan` incoming request. |
| LIB-ILL-34 | **Member summary.** LIB-MEM-12 also returns `"ill": {"open_requests": <int>, "on_loan": <int>, "overdue": <int>}`. `borrowing.reasons` includes `MEMBER_HAS_OVERDUE` also for an overdue incoming request. |
| LIB-ILL-35 | **Fees.** Fee `kind` adds `ill_request_fee`, `ill_late_fee`, `ill_lost`; Fee gets a nullable `ill_request_id`. These fees are paid, allocated and waived like other fees (LIB-FEE-05–07). |
| LIB-ILL-36 | **Notifications.** Added to LIB-NOT-01: `ill_request_rejected`, `ill_request_cancelled` (reasons `staff_request`, `member_deactivated`), `ill_request_received` (contains the title, the pickup branch name and `collect_until`), `ill_request_uncollected`, `ill_renewal_answered`; fees also notify as `fee_created`. Notifications get a nullable `ill_request_id`. LIB-NOT-05 is not changed. |
| LIB-ILL-37 | **Audit.** Module 18 reports to the audit log: `ill_partner_created`, `ill_partner_updated`, `ill_request_created`, `ill_request_sent`, `ill_request_rejected`, `ill_request_cancelled`, `ill_request_received`, `ill_request_collected`, `ill_renewal_requested`, `ill_renewal_answered`, `ill_request_returned`, `ill_request_closed`, `ill_request_lost`, `ill_request_uncollected`, `ill_outgoing_created`, `ill_outgoing_shipped`, `ill_outgoing_declined`, `ill_outgoing_returned`, `ill_outgoing_lost`. |
| LIB-ILL-38 | **Activity report.** `GET /api/v1/reports/ill-activity?from=&to=` (dates inclusive, `from` ≤ `to`, at most 366 days; otherwise `422`) returns a paginated list ordered by partner `code`, one item per partner (also inactive ones and those without activity): `{"partner_id", "partner_code", "sent", "rejected", "received", "late_returns", "outgoing_shipped", "outgoing_returned", "outgoing_lost", "amount_due"}`. `sent` and `rejected` count the send and reject actions on dates in the range; `received` by `received_on`; `late_returns` incoming requests with `returned_on` in the range and `returned_on` > `due_on`; outgoing by `shipped_on`, `returned_on` and the date reported lost; `amount_due` sums `amount_due` of outgoing requests reported lost in the range. |
| LIB-ILL-39 | **Not exported.** Interlibrary data is not part of import and export (module 13). A copy `at_partner` is exported with that status; import rejects the status `at_partner` (`422`), so the round trip of LIB-IO-07 does not hold while a copy is `at_partner` (as for LIB-IO-11). |
| LIB-ILL-40 | **Book deletion.** A book that has an outgoing request (any status) cannot be deleted: LIB-CAT-06 returns `409 IN_USE` (checked after `BOOK_HAS_COPIES`). |

### 26.9 Error codes of module 18

| HTTP status | Code | Requirement |
| --- | --- | --- |
| 409 | `INVALID_ILL_STATUS` | 26.2 |
| 409 | `ILL_NOT_ALLOWED_FOR_TYPE` | LIB-ILL-06 |
| 409 | `ILL_LIMIT_REACHED` | LIB-ILL-06 |
| 409 | `AVAILABLE_LOCALLY` | LIB-ILL-06 |
| 409 | `DUPLICATE_ILL_REQUEST` | LIB-ILL-06 |
| 409 | `PARTNER_INACTIVE` | LIB-ILL-03, LIB-ILL-07, LIB-ILL-24, LIB-ILL-25 |
| 409 | `PARTNER_ALREADY_TRIED` | LIB-ILL-07 |
| 409 | `ILL_TRY_LIMIT_REACHED` | LIB-ILL-07 |
| 409 | `ILL_PERIOD_TOO_SHORT` | LIB-ILL-11 |
| 409 | `ILL_COLLECT_PERIOD_OVER` | LIB-ILL-13 |
| 409 | `ILL_OVERDUE` | LIB-ILL-15 |
| 409 | `ILL_RENEWAL_ALREADY_REQUESTED` | LIB-ILL-15 |
| 409 | `ILL_NO_RENEWAL_REQUESTED` | LIB-ILL-16 |
| 409 | `PARTNER_HAS_OVERDUE` | LIB-ILL-25 |
| 409 | `PARTNER_LIMIT_REACHED` | LIB-ILL-27 |

`MEMBER_PASSIVE`, `MEMBERSHIP_EXPIRED`, `MEMBER_BLOCKED_BY_DEBT`, `MEMBER_HAS_OVERDUE`, `BRANCH_INACTIVE`, `INVALID_COPY_STATUS`, `IN_USE` and `CONFLICT` keep their meaning from earlier sections.

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
| Module 15: Study rooms | LIB-ROOM-01 – LIB-ROOM-45 | 45 |
| Module 16: Equipment loans | LIB-EQ-01 – LIB-EQ-41 | 41 |
| Module 17: Digital resources | LIB-DIG-01 – LIB-DIG-40 | 40 |
| Module 18: Interlibrary loans | LIB-ILL-01 – LIB-ILL-40 | 40 |
| **Total** | | **391** |
