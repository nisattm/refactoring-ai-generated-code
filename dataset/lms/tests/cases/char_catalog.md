# Characterization cases: module 4 (Catalog)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-CAT-01-a | LIB-CAT-01 | Characterization | GET `/authors/999999` | `404 NOT_FOUND`, details `{resource: author, id: 999999}` | feedback |
| T-CHAR-CAT-02-a | LIB-CAT-01 | Characterization | GET `/publishers/999999` | `404 NOT_FOUND`, details `{resource: publisher, id: 999999}` | held-out |
| T-CHAR-CAT-03-a | LIB-CAT-01 | Characterization | PATCH an author with `{}` | 200; name unchanged | feedback |
| T-CHAR-CAT-04-a | LIB-CAT-01 | Characterization | PATCH a publisher with `{}` | 200; name unchanged | held-out |
| T-CHAR-CAT-05-a | LIB-CAT-01 | Characterization | Rename publisher P1; rename P2 to P1's new name | 200 with the new name; `409 CONFLICT`, details `{field: name}` | feedback |
| T-CHAR-CAT-06-a | LIB-CAT-01 | Characterization | DELETE an unused author and an unused publisher; GET each | 204 each; then `404 NOT_FOUND` each | held-out |
| T-CHAR-CAT-07-a | LIB-CAT-05 | Characterization | PATCH a book with `author_ids` `[999999]` | `404 NOT_FOUND`, details `{field: author_ids, id: 999999}` | feedback |
| T-CHAR-CAT-08-a | LIB-CAT-05 | Characterization | PATCH a book with `publisher_id` `999999` | `404 NOT_FOUND`, details `{field: publisher_id, id: 999999}` | held-out |
| T-CHAR-CAT-09-a | LIB-CAT-05 | Characterization | PATCH a book with its own `isbn` | 200; `isbn` unchanged | feedback |
| T-CHAR-CAT-10-a | LIB-CAT-05 | Characterization | Book with authors [A, B]; PATCH `author_ids` [B, A]; PATCH [B, A] again | 200 with authors [B, A] both times | held-out |
| T-CHAR-CAT-11-a | LIB-CAT-09 | Characterization | GET `/copies/999999` | `404 NOT_FOUND`, details `{resource: copy, id: 999999}` | feedback |
| T-CHAR-CAT-12-a | LIB-CAT-09 | Characterization | GET `/copies/by-barcode/` with the barcode in lower case; with `NOPE-0` | 200 with the copy; `404 NOT_FOUND`, details `{resource: copy, barcode: NOPE-0}` | held-out |
| T-CHAR-CAT-13-a | LIB-CAT-09 | Characterization | PATCH a copy with its own `price` `100.00` | 200; `price` `100.00` | feedback |
