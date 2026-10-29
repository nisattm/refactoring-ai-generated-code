# Test Strategy

Tests serve two purposes: they check that the generated code meets its requirements, and they check that refactoring did not change behavior. Updated on 29 October 2026 for the single LMS project refactored as a whole ([`decisions/002`](decisions/002-single-lms-claude-code.md)).

## Test types

| Type | Purpose | When written | Tool |
| --- | --- | --- | --- |
| Requirement tests | Verify functional requirements: normal, boundary and error cases | Before code generation, from the requirements document | pytest, httpx (FastAPI TestClient) |
| Property-based tests | Stress invariants with random inputs (e.g. total books = on shelf + on loan) | With the requirement tests | Hypothesis |
| Scenario tests | End-to-end flows across modules (register → borrow → late return → fine → borrowing blocked) | With the requirement tests, from the scenarios section of the requirements | pytest, httpx |
| Characterization tests | Record the current behavior of the generated code; refactoring must not change it | After generation, before refactoring | pytest (+ snapshots) |

## Where tests attach: a stable interface

The whole project is refactored at once, so internal classes and function signatures may change. Tests bound to internals would fail even when behavior is preserved.

- **Behavior tests call the REST API** (FastAPI TestClient) and, where needed, a small **fixed service interface** defined in the requirements document (function names, parameters and return types).
- The REST API and the fixed service interface are part of the "externally visible behavior" that refactoring must not change ([`approaches.md`](approaches.md)).
- **Precise API in the requirements:** tests are written before the code, so the requirements document fixes every endpoint (method, path), request and response schema, and error status code with error body. Without this, the tests cannot attach to the generated code.
- **"Today" is injected:** services take the current date from a replaceable clock defined in the requirements, so date rules (due dates, working days, fines) give the same result on every run.

## Feedback set and held-out set

Iterative and Multi-Agent receive test feedback. If a model only fixes what those tests report, it may overfit to them. The suite is therefore split into:

- **Feedback set:** the LLM sees the results of these tests during refactoring.
- **Held-out set:** used only to evaluate the final result.

Each requirement ID has tests in both sets where possible. Proposed split: 50/50, stratified by module and test type.

## Test protection

Claude Code can write to files, so a model could make tests pass by editing them.

- Test files are kept outside the directory the model works in; our runner copies them in only to run them.
- Before and after every run, a SHA-256 hash of every test file is recorded. A changed hash makes the run invalid; it is reported, not used.
- The refactoring prompt states that tests must not be changed (a behavior rule, not a quality hint).

## Quality gates

- Branch coverage (coverage.py), measured on the generated baseline:
    - Requirement, property and scenario tests are written before the code as black-box tests, so 90% branch coverage of about 40,000 lines is not realistic for them alone. Their coverage is reported without a target.
    - The 90% target applies to the full suite: requirement tests plus the characterization tests added after generation.
- Mutation score (mutmut) is reported. Because a full run on about 40,000 lines may take very long (not yet measured), mutation testing runs on **one module per complexity level** (simple, medium, complex), chosen before generation and recorded. The target is set in the pilot.
- Tests are written by the team before code generation, so they are not influenced by the generated code.

## When the generated code has bugs

Starting code that fails requirement tests is recorded as faulty. Refactoring must preserve behavior, so for such code the characterization tests are the reference; fixing the bug is reported separately.

## Test case template

The LMS test folder contains `tests/cases.md` with this table. IDs follow `LIB-<module>-NN` from the requirements document.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| LIB-L-01 | A book on the shelf can be lent to a member with no debt | Normal | Book on shelf, student with 0 TL debt | Loan is created, book is "on loan", due date = today + 14 days (moved to the next working day if needed) | Feedback |
| LIB-L-02 | A member with debt of 50 TL or more cannot borrow | Boundary | Debt 50.00 TL | Request is rejected | Held-out |
| LIB-L-03 | A student can borrow at most 5 books | Boundary | Student has 5 books, requests a 6th | Request is rejected | Feedback |
| LIB-F-01 | Late fee counts working days after the due date | Normal | Student returns 3 working days late | Fine = 3 × 2 TL = 6.00 TL | Held-out |
| LIB-P-01 | The total number of copies is preserved | Property | Random sequence of loans and returns | on shelf + on loan + in transfer = total | Feedback |

Rules and numbers come from the requirements document ([`../dataset/README.md`](../dataset/README.md)).
