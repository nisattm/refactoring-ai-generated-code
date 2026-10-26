# Test Strategy

Tests serve two purposes: they check that the generated code meets its requirements, and they check that refactoring did not change behavior.

## Test types

| Type | Purpose | When written | Tool |
| --- | --- | --- | --- |
| Requirement tests | Verify functional requirements: normal, boundary and error cases | Before code generation, from the requirements document | pytest |
| Property-based tests | Stress invariants with random inputs (e.g. total books = on shelf + on loan) | With the requirement tests | Hypothesis |
| Scenario tests | End-to-end flows in the Library Management System (register → borrow → late return → fine) | For the complex task | pytest |
| Characterization tests | Record the current behavior of the starting code; refactoring must not change it | After generation, before refactoring | pytest (+ snapshots) |

## Feedback set and held-out set

Iterative and Multi-Agent receive test feedback. If a model only fixes what those tests report, it may overfit to them. Each task's suite is therefore split into:

- **Feedback set:** the LLM sees the results of these tests during refactoring.
- **Held-out set:** used only to evaluate the final result.

The split ratio is decided in the metrics meeting (proposal: 50/50).

## Quality gates

- Branch coverage target: 90% (coverage.py)
- Mutation score (mutmut) is reported; the target is set in the pilot
- Tests are written by the team before code generation, so they are not influenced by the generated code

## When the generated code has bugs

Starting code that fails requirement tests is recorded as faulty. Refactoring must preserve behavior, so for such code the characterization tests are the reference; fixing the bug is reported separately.

## Test case template

Each task folder contains `tests/cases.md` with this table:

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| LIB-L-01 | A book on the shelf can be lent to a member without fines | Normal | Book on shelf, member has no fines | Loan is created, book is "on loan" | Feedback |
| LIB-L-02 | A member with unpaid fines cannot borrow | Error | Member has an unpaid fine | Request is rejected | Held-out |
| LIB-L-03 | A member can borrow at most 5 books | Boundary | Member has 5 books, requests a 6th | Request is rejected | Feedback |
| LIB-F-01 | Late fee is a fixed amount per day | Normal | Returned 3 days late | Fine = 3 × daily fee | Held-out |
| LIB-P-01 | The total number of books is preserved | Property | Random sequence of loans and returns | on shelf + on loan = total | Feedback |

The numbers (5 books, daily fee) are examples; real values are set in each task's requirements document.
