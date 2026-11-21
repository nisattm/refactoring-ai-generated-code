# Characterization cases: module 19 (Staff and shifts)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-STF-01-a | LIB-STF-12 | Characterization | DELETE `/closures/999999` (admin) | `404 NOT_FOUND`, details `{resource: closure, id: 999999}` | feedback |
| T-CHAR-STF-02-a | LIB-STF-13 | Characterization | GET `/closures?from=2026-13-01` | `422`, fields `(from, expected a valid date in the form YYYY-MM-DD)` | held-out |
| T-CHAR-STF-03-a | LIB-STF-14 | Characterization | GET `/branches/{id}/open-days` without `from` and `to` | `422`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-STF-04-a | LIB-STF-14 | Characterization | GET `/branches/{id}/open-days?from=2026-11-10&to=2026-11-01` | `422`, fields `(from, from must not be after to)` | held-out |
| T-CHAR-STF-05-a | LIB-STF-24 | Characterization | GET `/shifts?to=bad` (admin) | `422`, fields `(to, expected a valid date in the form YYYY-MM-DD)` | feedback |
| T-CHAR-STF-06-a | LIB-STF-43 | Characterization | GET `/reports/staff-hours` without `from` and `to` | `422`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-STF-07-a | LIB-STF-43 | Characterization | GET `/reports/staff-hours?from=2026-11-10&to=2026-11-01` | `422`, fields `(from, from must not be after to)` | feedback |
| T-CHAR-STF-08-a | LIB-STF-44 | Characterization | GET `/reports/branch-coverage?branch_id=…&date=bad` | `422`, fields `(date, expected a valid date in the form YYYY-MM-DD)` | held-out |
| T-CHAR-STF-09-a | LIB-STF-45 | Characterization | GET `/reports/branch-coverage?branch_id=…` only | `422`, fields `(date, either date or from and to is required)` | feedback |
| T-CHAR-STF-10-a | LIB-STF-45 | Characterization | GET `/reports/branch-coverage?branch_id=…&from=2026-11-10&to=2026-11-01` | `422`, fields `(from, from must not be after to)` | held-out |
