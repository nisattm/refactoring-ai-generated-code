# Test cases: module 4 (Catalog)

Generated from one case list; 23 cases for 12 requirements (feedback 12, held-out 11, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CAT-01-a | LIB-CAT-01 | Normal | Authors `Zeynep`, `ahmet`, `Mehmet`; list; `q=ZEY`; PATCH name | 201 each; ordered by name (case-insensitive); `q` finds Zeynep; PATCH returns new name | feedback |
| T-CAT-01-b | LIB-CAT-01 | Error | Publisher `Yapı Kredi` twice (second as `YAPI KREDİ`); member creates an author | `409 CONFLICT`; `403 FORBIDDEN` | heldout |
| T-CAT-02-a | LIB-CAT-02 | Normal | ISBN-10 `0-306-40615-2` | Stored as `9780306406157` | feedback |
| T-CAT-02-b | LIB-CAT-02 | Boundary | ISBN-10 with check `x` (`0-8044-2957-x`); ISBN-13 with 979 prefix and spaces (`979 10 90636 07 1`) | `9780804429573`; `9791090636071` | heldout |
| T-CAT-02-c | LIB-CAT-02 | Error | Wrong check digits (`9780306406158`, `0306406153`), prefix 977 with a valid checksum (`9770000000003`), 12 digits | `422 VALIDATION_ERROR` each | feedback |
| T-CAT-03-a | LIB-CAT-03 | Normal | Create a book with two authors in order [B, A] | 201 `BookOut` with `authors` in the given order, `publisher` object, `availability` [] | feedback |
| T-CAT-03-b | LIB-CAT-03 | Error | Same ISBN once as ISBN-10 and once as ISBN-13 | Second `409 CONFLICT` | heldout |
| T-CAT-03-c | LIB-CAT-03 | Boundary | `publication_year` 1449 and 2027 (clock in 2026); `language` `TR`; `classification` `5.1`; 11 authors; duplicate author id | `422` each; year 1450 and 2026 accepted | feedback |
| T-CAT-04-a | LIB-CAT-04 | Normal | Books `zebra`, `apple`; filters `isbn` as ISBN-10, `classification_prefix=81` | Ordered case-insensitively by title; filters return the matching book | heldout |
| T-CAT-05-a | LIB-CAT-05 | Normal | PATCH `title`; PATCH invalid `isbn` | 200 with new title; `422` | feedback |
| T-CAT-06-a | LIB-CAT-06 | Normal | Delete a book without copies | 204; then 404 | feedback |
| T-CAT-06-b | LIB-CAT-06 | Error | Delete a book with a copy; delete its author; delete its publisher | `409 BOOK_HAS_COPIES`; `409 IN_USE`; `409 IN_USE` | heldout |
| T-CAT-07-a | LIB-CAT-07 | Normal | Add copy with barcode `abc-123` | 201; barcode `ABC-123`, `status` `available`, `current_branch_id` = home | feedback |
| T-CAT-07-b | LIB-CAT-07 | Boundary | Barcodes `ABC12` (5) and 21 chars; `ABC-123` again; price `0.00` and `100000.01`; `acquired_on` tomorrow | `422`; `409 CONFLICT`; `422`; `422` | heldout |
| T-CAT-07-c | LIB-CAT-07 | Normal | Waiting reservation (pickup A) for a lent-out book; a new copy is added at A | New copy `on_hold`; reservation `ready` | feedback |
| T-CAT-08-a | LIB-CAT-08 | Normal | Copies at A and B, one lent; filters `branch_id`, `status=on_loan`; `availability` in `BookOut` | Before lending: availability A 2/2, B 1/1; after lending: filters return B's copy and the lent copy | heldout |
| T-CAT-09-a | LIB-CAT-09 | Normal | PATCH `price`, `shelf_location`; PATCH `home_branch_id` of an available copy at home | 200; home and current branch both change | feedback |
| T-CAT-09-b | LIB-CAT-09 | Error | PATCH `home_branch_id` of a lent copy | `409 INVALID_COPY_STATUS` | heldout |
| T-CAT-10-a | LIB-CAT-10 | Normal | Withdraw an available copy with reason `Water damage` | 200; `withdrawn`, `withdrawn_reason` stored | feedback |
| T-CAT-10-b | LIB-CAT-10 | Error | Withdraw a lent copy; reason of 4 characters; withdraw twice | `409 INVALID_COPY_STATUS`; `422`; `409 INVALID_COPY_STATUS` | heldout |
| T-CAT-11-a | LIB-CAT-11 | Normal | Copy returned damaged at A, then repaired | `damaged`, then `available` | feedback |
| T-CAT-11-b | LIB-CAT-11 | Error | Repair an available copy | `409 INVALID_COPY_STATUS` | heldout |
| T-CAT-12-a | LIB-CAT-12 | Boundary | Book whose only copy is damaged (not lost/withdrawn); member reserves it | Reservation accepted (book is lendable) | heldout |
