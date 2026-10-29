# Library Management System – Requirements

**Status:** Part 1 of 4 (sections 1–6). Parts 2–4 add modules 3–14, cross-module dependencies, end-to-end scenarios and the import/export format.
**Version:** 0.1 · 2026-10-29

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
| Loans and returns (module 5) | – | Read own | Full | Full |
| Reservations (module 6) | – | Create, read, cancel own | Full | Full |
| Fines and payments (module 7) | – | Read own | Full (record payments, exemptions) | Full |
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

## Appendix A: Requirement index (Part 1)

| Area | IDs | Count |
| --- | --- | --- |
| Technical constraints | LIB-TECH-01 – LIB-TECH-12 | 12 |
| Common rules | LIB-COM-01 – LIB-COM-28 | 28 |
| Fixed service interface | LIB-IF-01 – LIB-IF-10 | 10 |
| Module 1: Core | LIB-CORE-01 – LIB-CORE-10 | 10 |
| Module 2: Identity and access | LIB-AUTH-01 – LIB-AUTH-25 | 25 |
| **Total** | | **85** |
