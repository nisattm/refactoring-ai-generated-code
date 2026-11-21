# Characterization cases: module 10 (Reports)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-REP-01-a | LIB-REP-01 | Characterization | GET `/reports/most-borrowed` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-02-a | LIB-ROOM-44 | Characterization | GET `/reports/room-usage` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-REP-03-a | LIB-EQ-40 | Characterization | GET `/reports/equipment-usage` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-04-a | LIB-DIG-39 | Characterization | GET `/reports/digital-usage` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-REP-05-a | LIB-ILL-38 | Characterization | GET `/reports/ill-activity` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-06-a | LIB-CRS-46 | Characterization | GET `/reports/course-reserves` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-REP-07-a | LIB-DON-43 | Characterization | GET `/reports/donations` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-08-a | LIB-PRE-38 | Characterization | GET `/reports/damage-recovery` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-REP-09-a | LIB-SUG-44 | Characterization | GET `/reports/suggestions` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-10-a | LIB-RDP-44 | Characterization | GET `/reports/programs` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | held-out |
| T-CHAR-REP-11-a | LIB-MSG-39 | Characterization | GET `/reports/messaging` without `from` and `to` | `422 VALIDATION_ERROR`, fields `(from, field required)`, `(to, field required)` | feedback |
| T-CHAR-REP-12-a | LIB-DON-44 | Characterization | GET `/reports/donors` without `year` (no donations) | 200 with `items` `[]` | held-out |
