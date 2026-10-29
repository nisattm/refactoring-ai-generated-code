# Library Management System – Requirements

**Status:** Parts 1–2 of 4 (sections 1–13). Parts 3–4 add modules 8–14, cross-module dependencies, end-to-end scenarios and the import/export format.
**Version:** 0.2 · 2026-10-29

This document specifies a Library Management System (LMS) for a university library with several branches. It is the only specification used to build the system. Tests are written from this document before the code exists, so every name, path, field, status code and error code given here is binding.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Each testable requirement has an ID of the form `LIB-<AREA>-NN`.

---

## 1. Purpose and scope

### 1.1 System overview

The LMS manages a university library: members and their memberships, the catalog of books and physical copies, loans and returns, reservations, late fees and payments, notifications, search, reports, multiple branches with transfers between them, purchasing, an audit log, and import/export of data. It is used through a REST API.

The system consists of 14 modules:

| # | Module | Package | Specified in |
| --- | --- | --- | --- |
| 1 | Core | `lms.core` | Part 1 |
| 2 | Identity and access | `lms.auth` | Part 1 |
| 3 | Members | `lms.members` | Part 2 |
| 4 | Catalog | `lms.catalog` | Part 2 |
| 5 | Loans and returns | `lms.loans` | Part 2 |
| 6 | Reservations | `lms.reservations` | Part 2 |
| 7 | Fines and payments | `lms.fines` | Part 2 |
| 8 | Notifications | `lms.notifications` | Part 3 |
| 9 | Search | `lms.search` | Part 3 |
| 10 | Reports | `lms.reports` | Part 3 |
| 11 | Branches | `lms.branches` | Part 3 |
| 12 | Purchasing | `lms.purchasing` | Part 3 |
| 13 | Audit log and import/export | `lms.audit` | Part 3 |
| 14 | API layer | `lms.api` | All parts (endpoints are listed with each module) |

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
| LIB-TECH-04 | All packages MUST be pinned to exact versions (`==`) in `requirements.txt` at the repository root. |
| LIB-TECH-05 | Data MUST be stored in one SQLite database. The location is given by `Settings.database_url` (section 4.2). |
| LIB-TECH-06 | Database access MUST use the SQLAlchemy 2.x ORM in synchronous mode (`Session`, not `AsyncSession`). API endpoints MUST be synchronous (`def`, not `async def`). |
| LIB-TECH-07 | The database schema MUST be created at application start-up if the tables do not exist (for example with `metadata.create_all`). No migration tool is used. |
| LIB-TECH-08 | Every HTTP request that changes data MUST run in one database transaction. If the request fails with any error response, no change from that request may remain in the database. |
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
| LIB-COM-01 | The library operates in Türkiye. The local time zone is the fixed offset UTC+03:00 (no daylight saving time). The system MUST use `datetime.timezone(datetime.timedelta(hours=3))` for local time. |
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
| LIB-COM-17 | E-mail addresses are compared case-insensitively and stored in lower case. An e-mail address MUST contain exactly one `@` with at least one character before it and a domain containing a dot after it; otherwise `422 VALIDATION_ERROR`. |

### 3.5 Pagination and ordering

| ID | Requirement |
| --- | --- |
| LIB-COM-18 | Every endpoint that returns a list MUST be paginated with query parameters `page` (integer ≥ 1, default 1) and `page_size` (integer 1–100, default 20). Values outside these ranges MUST be rejected with `422 VALIDATION_ERROR`. |
| LIB-COM-19 | A paginated response has this body: `{"items": [...], "page": 1, "page_size": 20, "total": 57}`. `total` is the number of matching items across all pages. A page beyond the last page returns `"items": []` with status 200. |
| LIB-COM-20 | Unless an endpoint defines another order, list items are ordered by `id` ascending. |

### 3.6 API conventions

| ID | Requirement |
| --- | --- |
| LIB-COM-21 | All endpoints except `GET /health` are under the base path `/api/v1`. Request and response bodies are JSON with `snake_case` field names. |
| LIB-COM-22 | Successful creation returns `201` with the created resource. Successful update returns `200` with the updated resource. Successful actions without a body return `204`. |
| LIB-COM-23 | Unknown fields in a request body MUST be rejected with `422 VALIDATION_ERROR`. |
| LIB-COM-24 | An endpoint that needs authentication reads the token from the header `Authorization: Bearer <token>` (section 6.3). |

### 3.7 Errors

| ID | Requirement |
| --- | --- |
| LIB-COM-25 | Every error response MUST have this body: `{"error": {"code": "<ERROR_CODE>", "message": "<human-readable text>", "details": {...}}}`. `details` is an object and MAY be empty. |
| LIB-COM-26 | For `422 VALIDATION_ERROR`, `details` MUST contain `"fields"`: a list of `{"field": "<name or dotted path>", "problem": "<text>"}`, one entry per invalid field. This replaces FastAPI's default validation response. |
| LIB-COM-27 | An unexpected internal error MUST return `500 INTERNAL_ERROR` with a generic message. Stack traces and internal details MUST NOT appear in the response. |
| LIB-COM-28 | When a request violates several rules, the first failing check in this order decides the response: (1) authentication, 401; (2) role permission (section 6.6), 403; (3) validation, 422; (4) existence of the addressed resource, 404; (5) ownership for `member` users (LIB-AUTH-25), 403; (6) state and business rules, 409. |
| LIB-COM-29 | An id in a request body or query that refers to an entity that does not exist (for example `member_id`, `branch_id`, `book_id`) MUST be rejected with `404 NOT_FOUND` and `details` `{"field": "<name>", "id": <value>}`. |

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

The package `lms` MUST export exactly the names below from `lms/__init__.py`. Tests and measurement scripts use them directly. Their names, parameters, defaults and behavior MUST NOT change. Further names exported by `lms` are added in Part 3 (import/export).

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
| LIB-IF-05 | `database_url` accepts any SQLAlchemy SQLite URL, including `"sqlite://"` (in-memory). With an in-memory database, all requests of one application MUST use the same database (for example through a static connection pool). |
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

The core module provides shared types, errors, date and money helpers, the calendar of working days and the settings.

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
| LIB-CORE-05 | `GET /api/v1/calendar/working-days-between?start=2026-06-01&end=2026-06-05` returns `200` with `{"working_days": 4}`. If `end` ≤ `start`, the result is `0`. The range MUST NOT exceed 3660 days; otherwise `422 VALIDATION_ERROR`. |
| LIB-CORE-06 | Missing or unparseable date parameters on these endpoints return `422 VALIDATION_ERROR` with the parameter named in `details.fields`. |

### 5.2 Shared behavior

| ID | Requirement |
| --- | --- |
| LIB-CORE-07 | Working-day calculations in every module MUST give the same results as the calendar endpoints for the same inputs and the same `Settings.holidays`. |
| LIB-CORE-08 | Money rounding (LIB-COM-12) MUST be applied to the final result of a calculation, not to its intermediate steps. Example: 10.00 TL split into 3 equal parts is 3.333… and is stored as `"3.33"`; 0.125 TL is stored as `"0.13"`. |
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
| `member_id` | integer or null | Set only for role `member`; links to the member record (module 3, Part 2) |
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
| LIB-AUTH-03 | **Password storage.** Passwords MUST be stored as `scrypt$<salt hex>$<hash hex>`, where the hash is `hashlib.scrypt(password_utf8, salt=salt, n=16384, r=8, p=1, dklen=64)` and the salt is 16 bytes from `secrets.token_bytes`. Password checks MUST use `hmac.compare_digest`. |
| LIB-AUTH-04 | Users with role `member` are created only by member registration (module 3, Part 2). `POST /api/v1/users` MUST reject `role: "member"` with `422 VALIDATION_ERROR`. |
| LIB-AUTH-05 | The e-mail address of a user MUST be unique among all users. A duplicate MUST be rejected with `409 CONFLICT`. |

### 6.3 Login, sessions and tokens

| ID | Requirement |
| --- | --- |
| LIB-AUTH-06 | **Login.** `POST /api/v1/auth/login` with `{"email": "...", "password": "..."}` returns `200` with `{"access_token": "<token>", "token_type": "bearer", "expires_at": "<date-time>", "user": UserOut}` for valid credentials of an active, unlocked user. |
| LIB-AUTH-07 | **Token.** The token MUST be created with `secrets.token_urlsafe(32)`. Only its SHA-256 hex digest is stored (Session). Each login creates a new session; earlier sessions of the user stay valid. |
| LIB-AUTH-08 | **Wrong credentials.** An unknown e-mail and a wrong password MUST give the same response: `401 INVALID_CREDENTIALS` with the same message. |
| LIB-AUTH-09 | **Lockout.** Each failed login for an existing user increases `failed_login_count` by 1. When it reaches 5, `locked_until` is set to now + 15 minutes and `failed_login_count` is reset to 0. While now < `locked_until`, every login for that user returns `403 ACCOUNT_LOCKED` with `details.locked_until`, even with the correct password, and does not count as a failure. A successful login resets `failed_login_count` to 0. |
| LIB-AUTH-10 | **Disabled account.** Login of an inactive user with the correct password returns `403 ACCOUNT_DISABLED` and does not change `failed_login_count`. With a wrong password it returns `401 INVALID_CREDENTIALS` and counts as a failure (LIB-AUTH-09). |
| LIB-AUTH-11 | **Login order.** Checks run in this order: e-mail exists → account locked → password correct → account active. |
| LIB-AUTH-12 | **Authenticated request.** A request with a token whose session exists, is not revoked, is not expired (now < `expires_at`) and belongs to an active user is authenticated as that user. Otherwise: missing header, malformed header, unknown token or revoked session → `401 UNAUTHENTICATED`; expired session → `401 TOKEN_EXPIRED`; inactive user → `403 ACCOUNT_DISABLED`. |
| LIB-AUTH-13 | **Expiry boundary.** A session is expired when now ≥ `expires_at`. Example: `token_ttl_hours = 12`, login at 2026-11-02T09:00:00+03:00 → the token is valid at 20:59:59 and expired at 21:00:00. |
| LIB-AUTH-14 | **Logout.** `POST /api/v1/auth/logout` revokes the session of the token used and returns `204`. Using the same token afterwards returns `401 UNAUTHENTICATED`. |
| LIB-AUTH-15 | **Current user.** `GET /api/v1/auth/me` returns `200` with `UserOut` of the authenticated user. |
| LIB-AUTH-16 | **Change own password.** `POST /api/v1/auth/change-password` with `{"current_password": "...", "new_password": "..."}` returns `204`. A wrong `current_password` returns `401 INVALID_CREDENTIALS` and does not count toward lockout. A `new_password` equal to the current one returns `422 VALIDATION_ERROR`. After a change, all other sessions of the user are revoked; the session used for the request stays valid. |

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
| LIB-AUTH-19 | `GET /api/v1/users/{user_id}` returns `UserOut`. An `admin` may read any user; an unknown id returns `404 NOT_FOUND`. Any other user may read only their own record; for them every other id returns `403 FORBIDDEN`, whether or not it exists. |
| LIB-AUTH-20 | `PATCH /api/v1/users/{user_id}` accepts any subset of `{"full_name", "role", "is_active"}` and returns `200` with `UserOut`. Only `admin` may call it. A role change to or from `member` returns `422 VALIDATION_ERROR`. |
| LIB-AUTH-21 | Setting `is_active` to `false` revokes all sessions of that user. Setting it to `true` also clears `locked_until` and `failed_login_count`. |
| LIB-AUTH-22 | **Last administrator.** A change that would leave no active `admin` (deactivating or demoting the last active admin) MUST be rejected with `409 LAST_ADMIN`. An admin MUST NOT deactivate their own account: `409 CANNOT_DEACTIVATE_SELF`. |
| LIB-AUTH-23 | `POST /api/v1/users/{user_id}/reset-password` with `{"new_password": "..."}` returns `204`. Only `admin` may call it. It revokes all sessions of that user and clears `locked_until` and `failed_login_count`. |

### 6.5 Error codes of this module

| HTTP status | Code | When |
| --- | --- | --- |
| 409 | `LAST_ADMIN` | LIB-AUTH-22 |
| 409 | `CANNOT_DEACTIVATE_SELF` | LIB-AUTH-22 |

The common codes `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `ACCOUNT_DISABLED` and `ACCOUNT_LOCKED` (section 3.7) are raised by this module.

### 6.6 Permission matrix

Permissions are checked in this module and applied by every endpoint. "Own" means the resource belongs to the authenticated member (through `User.member_id`). Endpoint details are specified with each module; Parts 2–3 MUST follow this matrix.

| Area | Anonymous | `member` | `librarian` | `admin` |
| --- | --- | --- | --- | --- |
| Health and calendar (module 1) | Read | Read | Read | Read |
| Login (module 2) | Yes | Yes | Yes | Yes |
| Own account: me, logout, change password (module 2) | – | Yes | Yes | Yes |
| User management (module 2) | – | – | – | Full |
| Members (module 3) | – | Read own | Full | Full |
| Catalog: books, copies (module 4) | – | Read | Full | Full |
| Loans and returns (module 5) | – | Read own, renew own | Full | Full |
| Reservations (module 6) | – | Create, read, cancel own | Full | Full |
| Fines and payments (module 7) | – | Read own | Record payments, read all | Full, including waivers |
| Notifications (module 8) | – | Read own, mark own as read | Read all | Read all |
| Search (module 9) | – | Yes | Yes | Yes |
| Reports (module 10) | – | – | Read | Read |
| Branches and transfers (module 11) | – | Read branches | Full | Full |
| Purchasing (module 12) | – | – | Full | Full |
| Audit log (module 13) | – | – | – | Read |
| Import/export (module 13) | – | – | – | Full |

| ID | Requirement |
| --- | --- |
| LIB-AUTH-24 | A request by a role without the permission in the matrix returns `403 FORBIDDEN`. A request without valid authentication to a non-anonymous endpoint returns `401` as in LIB-AUTH-12. |
| LIB-AUTH-25 | When a `member` addresses a resource that exists but is not their own, the response is `403 FORBIDDEN` (not `404`). |

### 6.7 Events for other modules

The module MUST report these events to the audit log (module 13, Part 3) with the acting user, the time from the clock and the affected user id:

`login_succeeded`, `login_failed`, `account_locked`, `logout`, `password_changed`, `password_reset`, `user_created`, `user_updated`, `user_deactivated`, `user_activated`.

---


## 7. Module 3: Members

This module registers library members and manages their membership type, validity and status. Branches (`branch_id`) are managed by module 11 (Part 3); here a `branch_id` refers to an existing branch.

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
| LIB-MEM-07 | **Update.** `PATCH /api/v1/members/{member_id}` accepts any subset of `{"full_name", "email", "phone", "membership_type", "university_id", "home_branch_id"}`. The result MUST satisfy LIB-MEM-02 and LIB-MEM-05. A changed `email` or `full_name` is also changed on the user account. `membership_start` and `valid_until` do not change. |
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

Allowed transitions: `available` → `on_loan`, `on_hold`, `in_transfer`, `withdrawn`; `on_hold` → `on_loan`, `available`, `in_transfer`; `on_loan` → `available`, `on_hold`, `in_transfer`, `damaged`, `lost`; `in_transfer` → `available`, `on_hold`; `damaged` → `available`, `on_hold`, `in_transfer`, `withdrawn`; `lost` → `withdrawn`. Any other transition MUST be rejected with `409 INVALID_COPY_STATUS`.

### 8.3 Endpoints

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST`, `GET /api/v1/authors`; `GET`, `PATCH`, `DELETE /api/v1/authors/{author_id}` | write: librarian, admin; read: all users | Authors |
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
| LIB-LOAN-01 | **Lend.** `POST /api/v1/loans` with `{"member_id"}` and exactly one of `{"copy_id"}` or `{"barcode"}` returns `201` with `LoanOut`. Both or neither returns `422 VALIDATION_ERROR`. The copy's status becomes `on_loan`. |
| LIB-LOAN-02 | **Overdue.** An open loan is overdue when today > `due_date`. |
| LIB-LOAN-03 | **Due date.** `due_date` = the next working day on or after `loan_date` + `loan_period_days` calendar days (LIB-COM-08). Examples: student, lent 2026-11-02 → due 2026-11-16; academic, lent 2026-12-02 → 2027-01-01 is a holiday → due 2027-01-04. |
| LIB-LOAN-04 | **Terms are fixed per loan.** `loan_period_days`, `max_renewals` and `daily_fee` are copied from the member's type (7.1) when the loan is created and are used for that loan until it closes, even if the member's type changes. |
| LIB-LOAN-05 | **Lending checks.** The checks run in this order; the first failure decides the response (all `409`): (1) member `passive` → `MEMBER_PASSIVE`; (2) today > `valid_until` → `MEMBERSHIP_EXPIRED`; (3) the member has an overdue loan → `MEMBER_HAS_OVERDUE`; (4) the member's total debt (LIB-FEE-09) ≥ 50.00 TL → `MEMBER_BLOCKED_BY_DEBT`, with `details.total_debt`; (5) the member's open loans ≥ the loan limit of the member's current type → `LOAN_LIMIT_REACHED`; (6) copy status: `available` → allowed; `on_hold` → allowed only if the hold belongs to a `ready` reservation of this member (LIB-RES-10), otherwise `COPY_ON_HOLD`; any other status → `COPY_NOT_AVAILABLE`, with `details.status`. |
| LIB-LOAN-06 | **Debt boundary.** Total debt 49.99 TL allows lending; 50.00 TL does not. |
| LIB-LOAN-07 | **Renew.** `POST /api/v1/loans/{loan_id}/renew` returns `200` with `LoanOut`. Checks in order (all `409`): loan not `open` → `LOAN_NOT_OPEN`; member `passive` → `MEMBER_PASSIVE`; membership expired → `MEMBERSHIP_EXPIRED`; loan overdue → `LOAN_OVERDUE`; `renewal_count` ≥ `max_renewals` → `RENEWAL_LIMIT_REACHED`; the book has an active reservation (status `waiting`, `in_transit` or `ready`) by any member → `BOOK_RESERVED`. |
| LIB-LOAN-08 | **Renewed due date.** New `due_date` = the later of the current `due_date` and the next working day on or after today + `loan_period_days`. `renewal_count` increases by 1. A renewal on the due date itself is allowed (not overdue). Examples: student loan due 2026-11-16, renewed on 2026-11-10 → due 2026-11-24. Loan due 2026-06-01, renewed on 2026-05-15 → 2026-05-29 is a holiday → 2026-06-01, so the due date stays 2026-06-01 and the renewal still counts. |
| LIB-LOAN-09 | **Return.** `POST /api/v1/loans/{loan_id}/return` with `{"branch_id", "condition": "good" \| "damaged", "damage_fee"}` closes the loan (`status` `returned`, `returned_on` = today, `return_branch_id`, `condition_on_return`, `late_days`) and returns `200` with `LoanOut`. A loan that is not `open` returns `409 LOAN_NOT_OPEN`. The book may be returned at any branch. |
| LIB-LOAN-10 | **Late fee at return.** `late_days` = working days between `due_date` and `returned_on` (LIB-COM-10). If `late_days` > 0, a late fee is created (LIB-FEE-02). Example: student loan due 2026-11-16 (Mon), returned 2026-11-20 (Fri) → 4 late days → 8.00 TL. |
| LIB-LOAN-11 | **Damaged return.** With `condition` `damaged`, `damage_fee` is required and MUST be > 0.00 and ≤ the copy's `price`; otherwise `422 VALIDATION_ERROR`. A damage fee is created (LIB-FEE-03) and the copy's status becomes `damaged` at the return branch (`current_branch_id` = `branch_id`). With `condition` `good`, `damage_fee` MUST be absent or null. |
| LIB-LOAN-12 | **Copy after a good return.** The copy's `current_branch_id` becomes the return branch and the copy is released (LIB-RES-08). |
| LIB-LOAN-13 | **Report lost.** `POST /api/v1/loans/{loan_id}/report-lost` closes an open loan with `status` `lost`, `late_days` = working days between `due_date` and today, and creates the fees of LIB-FEE-04. The copy's status becomes `lost` and `current_branch_id` becomes null. A loan that is not `open` returns `409 LOAN_NOT_OPEN`. Returns `200` with `LoanOut`. |
| LIB-LOAN-14 | **List.** `GET /api/v1/loans` is paginated, ordered by `id` descending. Filters: `member_id`, `copy_id`, `book_id`, `branch_id`, `status`, `overdue` (`true` selects open overdue loans), `due_before` (date, due date ≤ value). `GET /api/v1/members/{member_id}/loans` has the same filters except `member_id`. |

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
| LIB-RES-10 | **Fulfilment.** When the member borrows the held copy (LIB-LOAN-05 step 6) on or before `hold_until`, the reservation becomes `fulfilled`. A `ready` reservation is collected only with its assigned copy; another available copy of the same book can also be lent to the member, and the reservation then also becomes `fulfilled` and its held copy is released (LIB-RES-08). |
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
| `INVALID_COPY_STATUS` | 4 | 8.2, LIB-CAT-09–11 |
| `BOOK_HAS_COPIES` | 4 | LIB-CAT-06 |
| `IN_USE` | 4 | LIB-CAT-06 |
| `MEMBER_HAS_OVERDUE` | 5 | LIB-LOAN-05 |
| `MEMBER_BLOCKED_BY_DEBT` | 5 | LIB-LOAN-05 |
| `LOAN_LIMIT_REACHED` | 5 | LIB-LOAN-05 |
| `COPY_ON_HOLD` | 5 | LIB-LOAN-05 |
| `COPY_NOT_AVAILABLE` | 5 | LIB-LOAN-05 |
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

Modules 3–7 MUST report these events to notifications (module 8) and the audit log (module 13), with the acting user (if any), the time from the clock, and the ids of the affected entities. Which events create a notification for the member is specified in Part 3.

| Module | Events |
| --- | --- |
| 3 | `member_registered`, `member_updated`, `membership_renewed`, `member_deactivated`, `member_activated` |
| 4 | `book_created`, `book_updated`, `book_deleted`, `copy_added`, `copy_updated`, `copy_withdrawn`, `copy_repaired` |
| 5 | `loan_created`, `loan_renewed`, `loan_returned`, `loan_lost` |
| 6 | `reservation_created`, `reservation_in_transit`, `reservation_ready`, `reservation_fulfilled`, `reservation_cancelled`, `reservation_expired` |
| 7 | `fee_created`, `payment_received`, `fee_waived` |

---

## Appendix A: Requirement index (Parts 1–2)

| Area | IDs | Count |
| --- | --- | --- |
| Technical constraints | LIB-TECH-01 – LIB-TECH-12 | 12 |
| Common rules | LIB-COM-01 – LIB-COM-29 | 29 |
| Fixed service interface | LIB-IF-01 – LIB-IF-10 | 10 |
| Module 1: Core | LIB-CORE-01 – LIB-CORE-10 | 10 |
| Module 2: Identity and access | LIB-AUTH-01 – LIB-AUTH-25 | 25 |
| Module 3: Members | LIB-MEM-01 – LIB-MEM-13 | 13 |
| Module 4: Catalog | LIB-CAT-01 – LIB-CAT-12 | 12 |
| Module 5: Loans and returns | LIB-LOAN-01 – LIB-LOAN-14 | 14 |
| Module 6: Reservations | LIB-RES-01 – LIB-RES-14 | 14 |
| Module 7: Fines and payments | LIB-FEE-01 – LIB-FEE-11 | 11 |
| **Total** | | **150** |
