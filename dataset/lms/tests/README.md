# LMS Tests

Tests are written from [`../requirements.md`](../requirements.md) **before** the code is generated ([`../../../docs/testing.md`](../../../docs/testing.md)). Until the code exists, they fail at `import lms`; this is expected.

This folder is never given to the model and is kept outside the directory the model works in ([test protection](../../../docs/testing.md#test-protection)).

## Layout

```
dataset/lms/tests/
├── README.md              This file
├── conftest.py            Shared fixtures (contract below)
├── support/
│   ├── __init__.py
│   └── api.py             Helper functions (contract below)
├── cases/<module>.md      Test case table per module
├── feedback/test_<module>.py   Tests whose results the model may see
└── heldout/test_<module>.py    Tests used only for evaluation
```

Module file names: `core`, `auth`, `members`, `catalog`, `loans`, `reservations`, `fees`, `notifications`, `search`, `reports`, `branches`, `purchasing`, `audit_io`, `api`, `e2e`.

## Ownership (30 October 2026)

| Files | Owner |
| --- | --- |
| `conftest.py`, `support/` | Fatima |
| `core`, `auth`, `reservations`, `members`, `catalog`, `branches`, `e2e` | Nisa |
| `loans`, `fees`, `notifications`, `purchasing` | Fatima |
| `search`, `reports`, `audit_io`, `api` | Open |

Only the owner edits a file. A missing helper is requested from the owner of `support/`; until it exists, a test calls the API through `client` directly.

## Test case IDs and names

- Case ID: `T-<AREA>-<NN>-<letter>`, where `<AREA>-<NN>` is the requirement it checks: `LIB-LOAN-05` → `T-LOAN-05-a`, `T-LOAN-05-b`, …; scenarios: `T-E2E-01`; properties: `T-P-<NN>`.
- Test function name: the case ID in lower case with `_`: `test_t_loan_05_a`.
- The first line of the test's docstring is the case ID.
- Every requirement has at least one case. Requirements that only constrain the implementation and cannot be observed through the API or the fixed interface (for example LIB-TECH-02 allowed packages) are listed in the case table with Set `static` and checked by script, not by pytest.

## Feedback / held-out split

Fixed before any code exists, so it cannot be tuned to results:

- The cases of one requirement alternate: `a` → feedback, `b` → held-out, `c` → feedback, …
- A requirement with a single case: odd requirement number → feedback, even → held-out (`T-AUTH-09-a` → feedback, `T-AUTH-10-a` → held-out).
- Scenarios: odd numbers → feedback, even → held-out. Property tests: odd → feedback, even → held-out.

## Case table format (`cases/<module>.md`)

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-LOAN-03-a | LIB-LOAN-03 | Normal | Student, lent 2026-11-02 | `due_date` 2026-11-16 | feedback |

Type is one of `Normal`, `Boundary`, `Error`, `Property`, `Scenario`, `Static`.

## Fixture and helper contract

Names and signatures are fixed; both test authors rely on them.

**`conftest.py` fixtures**

| Fixture | Value |
| --- | --- |
| `start` | `datetime(2026, 11, 2, 9, 0, tzinfo=timezone(timedelta(hours=3)))` (Monday) |
| `clock` | `lms.FixedClock(start)` |
| `settings` | `lms.Settings(database_url="sqlite://", clock=clock)` |
| `app` | `lms.create_app(settings)` |
| `client` | `fastapi.testclient.TestClient(app)` |
| `admin` | Authorization header dict of the bootstrap admin (`admin@library.local` / `ChangeMe123`) |
| `librarian` | Header dict of a librarian created by the admin (`lib@library.local` / `Librarian123`) |
| `branch_a`, `branch_b` | Branches created by the admin, codes `A` and `B` (JSON dicts) |

**`support/api.py`** — every function takes `expect` (the success status by default), asserts the status code and returns the parsed JSON (or a header dict).

| Function | Purpose |
| --- | --- |
| `login(client, email, password, expect=200)` | Header dict `{"Authorization": "Bearer …"}` |
| `create_branch(client, headers, code, name=None, expect=201)` | New branch |
| `register_member(client, headers, *, home_branch_id, membership_type="student", email=None, password="Member1234", expect=201, **fields)` | New member; unique e-mail and `university_id` (or `phone` for guests) generated |
| `member_headers(client, member, password="Member1234")` | Header dict for that member |
| `create_book(client, headers, *, title="Book", isbn=None, expect=201, **fields)` | New book; creates author and publisher if needed; unique valid ISBN-13 generated |
| `add_copy(client, headers, book_id, *, home_branch_id, price="100.00", barcode=None, expect=201)` | New copy |
| `lend(client, headers, member_id, copy_id, expect=201)` | New loan |
| `return_loan(client, headers, loan_id, *, branch_id, condition="good", damage_fee=None, expect=200)` | Closed loan |
| `reserve(client, headers, *, book_id, pickup_branch_id, member_id=None, expect=201)` | New reservation |
| `error_code(response)` | `response.json()["error"]["code"]` |
| `D(value)` | `decimal.Decimal(str(value))` |

## Generated test files

For `core`, `auth`, `members`, `catalog` and `reservations`, the case table and both test files are generated from one case list in `spec/<module>.py`, so that the table, the tests and the split rule cannot drift apart. Edit the spec, then run:

```bash
python scripts/gen_tests.py dataset/lms/tests/spec/<module>.py dataset/lms/tests
```

Hand-written modules follow the same ID, naming and split rules.

## Running

Inside the Docker image, with the generated code on `PYTHONPATH`; the runner script (`scripts/run_tests.py`) runs `feedback/` and `heldout/` separately and checks the test-file hashes first.
