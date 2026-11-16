# Test Strategy

Tests serve two purposes: they check that the generated code meets its requirements, and they check that refactoring did not change behavior. Updated on 29 October 2026 for the single LMS project refactored as a whole ([`decisions/002`](decisions/002-single-lms-claude-code.md)).

## Test types

| Type | Purpose | When written | Tool |
| --- | --- | --- | --- |
| Requirement tests | Verify functional requirements: normal, boundary and error cases | Before code generation, from the requirements document | pytest, httpx (FastAPI TestClient) |
| Property-based tests | Stress invariants with random inputs (e.g. total books = on shelf + on loan) | With the requirement tests | Hypothesis |
| Scenario tests | End-to-end flows across modules (register → borrow → late return → fine → borrowing blocked) | With the requirement tests, from the scenarios section of the requirements | pytest, httpx |
| Characterization tests | Record the current behavior of the generated code; refactoring must not change it | After the final baseline measurement, before the first refactoring experiment (not part of Week 4, [`decisions/003`](decisions/003-analyzer-and-success-rule.md) D26, issue #115) | pytest (+ snapshots) |

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

Each requirement ID has tests in both sets where possible. Split rule (fixed before generation): the cases of each requirement alternate between the sets; see [`../dataset/lms/tests/README.md`](../dataset/lms/tests/README.md#feedback--held-out-split).

## Success relative to the starting code

Decided on 17 November 2026 ([`decisions/003`](decisions/003-analyzer-and-success-rule.md), D17–D19). The starting code does not pass every test (for example T-INV-20-a fails because of a code error), so a refactoring is judged against what passes at the start, not against "all tests pass".

- **Regression:** a test that passes at the start and fails, errors or is missing after refactoring. Feedback and held-out sets are compared separately. Tests that already fail at the start are reported separately and are not regressions.
- **Flaky tests:** one full run at the start; the tests that fail in it run twice more; a test with mixed results goes to a "flaky" list and is left out of the comparison. A second full start run is made (at night, in the background) for the final baseline. After refactoring, a test that passed at the start and fails runs twice more; it is a regression only if it fails **in both** repetitions.
- **Per case:** the runner records the result of every case (passed, failed, error, skipped, missing) with its module, case type and set in `tests.csv`. A case that passed at the start and does not appear in the result is a regression. A timeout (7,200 s per set) makes the run invalid.
- **Coverage** is measured in a separate run (branch coverage, `lms/` only) and is not part of the success decision.

## Test protection

Claude Code can write to files, so a model could make tests pass by editing them.

- Test files are kept outside the directory the model works in; our runner copies them in only to run them.
- Before and after every run, a SHA-256 hash of every test file is recorded. A changed hash makes the run invalid; it is reported, not used.
- The refactoring prompt states that tests must not be changed (a behavior rule, not a quality hint).

## Quality gates

- Branch coverage (coverage.py), measured on the generated baseline (`lms/` only, separate run, in Week 4 as part of the baseline script):
    - Requirement, property and scenario tests are written before the code as black-box tests, so 90% branch coverage of the generated code is not realistic for them alone. **In Week 4 their coverage is reported without a target** and does not enter the success decision.
    - The 90% target applies to the full suite: requirement tests plus the characterization tests. **Both the characterization tests and the target are not part of Week 4** ([`decisions/003`](decisions/003-analyzer-and-success-rule.md), D26): they are written after the final baseline measurement and before the first refactoring experiment, tracked in issue #115.
- Mutation score (mutmut) is reported. Because a full run on about 40,000 lines may take very long (not yet measured), mutation testing runs on **one module per complexity level** (simple, medium, complex), chosen before generation and recorded. The target is set in the pilot.
- Tests are written by the team before code generation, so they are not influenced by the generated code.

## When the generated code has bugs

Starting code that fails requirement tests is recorded as faulty. Refactoring must preserve behavior, so for such code the starting result is the reference (a test that already fails is not a regression, see above), and from issue #115 on the characterization tests too; fixing the bug is reported separately.

## Test case template

Folder layout, case IDs (`T-<AREA>-<NN>-<letter>`, one or more per requirement ID of [`../dataset/lms/requirements.md`](../dataset/lms/requirements.md)), the feedback/held-out split rule, the case table format (`tests/cases/<module>.md`) and the shared fixture contract are in [`../dataset/lms/tests/README.md`](../dataset/lms/tests/README.md).

Example rows:

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-LOAN-03-a | LIB-LOAN-03 | Normal | Student, lent 2026-11-02 | `due_date` 2026-11-16 | feedback |
| T-LOAN-03-b | LIB-LOAN-03 | Boundary | Academic, lent 2026-12-02 (2027-01-01 is a holiday) | `due_date` 2027-01-04 | held-out |
| T-LOAN-06-a | LIB-LOAN-06 | Boundary | Total debt 50.00 TL | `409 MEMBER_BLOCKED_BY_DEBT` | feedback |
| T-LOAN-06-b | LIB-LOAN-06 | Boundary | Total debt 49.99 TL | Loan created | held-out |
