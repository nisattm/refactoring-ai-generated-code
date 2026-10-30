# Test cases: Module 12: Purchasing

Requirements: [`../../requirements.md`](../../requirements.md). Tests: [`../feedback/test_purchasing.py`](../feedback/test_purchasing.py), [`../heldout/test_purchasing.py`](../heldout/test_purchasing.py). Split rule and conventions: [`../README.md`](../README.md).

Dates are the clock's local date (`FixedClock`, start 2026-11-02 09:00 +03:00, a Monday). Expected dates and amounts come from the examples in the requirements or were computed with the working-day rules of section 3.2 and the default holiday list.

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-PUR-01-a | LIB-PUR-01 | Normal | Librarian creates supplier "Ankara Kitap" with e-mail and phone | `201` with the fields and `is_active` true | feedback |
| T-PUR-01-b | LIB-PUR-01, LIB-COM-30 | Error | Supplier "Istanbul Yayin" exists; create "İSTANBUL YAYIN" | `409 CONFLICT` (names compared with LIB-COM-30 normalization) | held-out |
| T-PUR-01-c | LIB-PUR-01 | Normal | Suppliers "Beta", "alpha", "Gamma" (Gamma inactive); list, `q=AL`, `is_active=false` | Ordered by name: alpha, Beta, Gamma; `q=AL` → alpha; `is_active=false` → Gamma | feedback |
| T-PUR-01-d | LIB-PUR-01 | Normal | `PATCH` a supplier's `name`, `email`, `phone` and `is_active` | `200` with the new values; `GET` returns the same | held-out |
| T-PUR-01-e | LIB-PUR-01, 18.2 | Error | A member creates a supplier and lists suppliers | Both `403 FORBIDDEN` | feedback |
| T-PUR-01-f | LIB-PUR-01, 18.1, LIB-COM-17 | Error | Supplier with e-mail "no-at-sign.example.com" | `422 VALIDATION_ERROR`; without e-mail and phone (both null) `201` | held-out |
| T-PUR-02-a | LIB-PUR-02 | Normal | Draft order: supplier P, branch A, book K × 3 at 95.50 (LIB-E2E-09) | `201`, `status` draft, `total` "286.50", one line with `received_quantity` 0 | feedback |
| T-PUR-02-b | LIB-PUR-02 | Error | Order with an inactive supplier | `409 SUPPLIER_INACTIVE` | held-out |
| T-PUR-02-c | LIB-PUR-02 | Error | The same book twice in `lines` | `422 VALIDATION_ERROR` | feedback |
| T-PUR-02-d | LIB-PUR-02 | Boundary | Draft order with 0 lines | `201`, `total` "0.00", `lines` empty | held-out |
| T-PUR-02-e | LIB-PUR-02 | Boundary | Orders with 50 lines and with 51 lines (different books) | 50: `201`; 51: `422 VALIDATION_ERROR` | feedback |
| T-PUR-02-f | LIB-PUR-02, 18.1 | Boundary | Line `quantity` 0 and 101; `unit_price` "0.00" and "100000.01" | Each `422 VALIDATION_ERROR` | held-out |
| T-PUR-02-g | LIB-PUR-02, 18.1 | Boundary | Line with `quantity` 100 and `unit_price` "100000.00" (upper limits) | `201`, `total` "10000000.00" | feedback |
| T-PUR-02-h | LIB-PUR-02, LIB-BR-04 | Error | Order for an inactive branch | `409 BRANCH_INACTIVE` | held-out |
| T-PUR-02-i | LIB-PUR-02, LIB-COM-29 | Error | Line with unknown `book_id` 999999 | `404 NOT_FOUND` | feedback |
| T-PUR-02-j | LIB-PUR-02, 18.2 | Error | A member creates an order | `403 FORBIDDEN` | held-out |
| T-PUR-03-a | LIB-PUR-03 | Normal | Draft with 2 lines (2 × 10.00, 1 × 5.00); `PATCH` `lines` with one line 4 × 7.50 | `200`; one line; `total` "30.00" | feedback |
| T-PUR-03-b | LIB-PUR-03 | Normal | `PATCH` a draft's `supplier_id` and `branch_id` only | `200`; new supplier and branch; lines unchanged | held-out |
| T-PUR-03-c | LIB-PUR-03 | Error | `PATCH` an `ordered` order | `409 INVALID_ORDER_STATUS` | feedback |
| T-PUR-03-d | LIB-PUR-03 | Error | `PATCH` a `cancelled` order | `409 INVALID_ORDER_STATUS` | held-out |
| T-PUR-04-a | LIB-PUR-04 | Normal | Draft submitted on 2026-11-05 | `status` ordered, `ordered_on` 2026-11-05 | feedback |
| T-PUR-04-b | LIB-PUR-04 | Error | Submit a draft without lines | `409 ORDER_EMPTY`; status stays draft | held-out |
| T-PUR-04-c | LIB-PUR-04 | Error | Submit an order twice | Second submit `409 INVALID_ORDER_STATUS` | feedback |
| T-PUR-05-a | LIB-PUR-05 | Normal | Cancel a draft | `status` cancelled | feedback |
| T-PUR-05-b | LIB-PUR-05 | Normal | Cancel an `ordered` order with nothing received | `status` cancelled | held-out |
| T-PUR-05-c | LIB-PUR-05 | Error | Cancel a `partially_received` order (1 of 3 received) | `409 INVALID_ORDER_STATUS`; status unchanged | feedback |
| T-PUR-05-d | LIB-PUR-05 | Error | Cancel an order that is already cancelled | `409 INVALID_ORDER_STATUS` | held-out |
| T-PUR-05-e | LIB-PUR-05 | Error | Cancel a fully `received` order | `409 INVALID_ORDER_STATUS` | feedback |
| T-PUR-06-a | LIB-PUR-06 | Normal | Ordered K × 3 at 95.50 for branch A; receive barcodes PUR-0001, PUR-0002 on 2026-11-05 | Two copies: home and current branch A, `price` "95.50", `acquired_on` 2026-11-05, `status` available; line `received_quantity` 2 | feedback |
| T-PUR-06-b | LIB-PUR-06 | Error | Receive on a draft | `409 INVALID_ORDER_STATUS`; no copy created | held-out |
| T-PUR-06-c | LIB-PUR-06 | Error | Receive with an empty `lines` list; with an empty `barcodes` list; with the same `line_id` twice | Each `422 VALIDATION_ERROR` | feedback |
| T-PUR-06-d | LIB-PUR-06, LIB-COM-29 | Error | Receive with the `line_id` of another order | `404 NOT_FOUND`; no copy created | held-out |
| T-PUR-06-e | LIB-PUR-06, LIB-RES-08 | Normal | Book K's only copy is on loan; S2 waits (pickup A); the order for K (branch A) receives one copy | The new copy is released: S2's reservation `ready`, the copy `on_hold` | feedback |
| T-PUR-06-f | LIB-PUR-06 | Error | Receive on a cancelled order | `409 INVALID_ORDER_STATUS` | held-out |
| T-PUR-07-a | LIB-PUR-07 | Boundary | Line of 3 with 2 received; receive 2 more (LIB-E2E-09) | `409 RECEIVE_EXCEEDS_ORDERED`; still 2 copies, `received_quantity` 2 | feedback |
| T-PUR-07-b | LIB-PUR-07 | Error | Two lines (quantity 1 each); one request receives 1 on the first and 2 on the second | `409 RECEIVE_EXCEEDS_ORDERED`; nothing created on either line | held-out |
| T-PUR-07-c | LIB-PUR-07 | Error | Receive a barcode that already exists in the catalog, together with a new one | `409 CONFLICT`; neither copy created | feedback |
| T-PUR-07-d | LIB-PUR-07 | Error | The same barcode twice in one request | `409 CONFLICT`; no copy created | held-out |
| T-PUR-08-a | LIB-PUR-08 | Normal | Line of 3: receive 2, then 1 (LIB-E2E-09) | `partially_received` after 2, `received` after 3 | feedback |
| T-PUR-08-b | LIB-PUR-08 | Boundary | Two lines (1 and 2): first line complete, second 1 of 2; then the last copy | `partially_received`, then `received` | held-out |
| T-PUR-09-a | LIB-PUR-09 | Normal | Three orders, no filter | Ordered by `id` descending: o3, o2, o1 | feedback |
| T-PUR-09-b | LIB-PUR-09 | Normal | Filters `status=draft`, `supplier_id`=p1, `branch_id`=B | draft → o3, o1; p1 → o3, o1; B → o3 | held-out |
| T-PUR-09-c | LIB-PUR-09, LIB-COM-18 | Normal | `page_size=2`, page 2 | One item (o1), `total` 3 | feedback |
| T-PUR-09-d | LIB-PUR-09, 18.2 | Error | A member lists orders and reads one order | Both `403 FORBIDDEN` | held-out |
