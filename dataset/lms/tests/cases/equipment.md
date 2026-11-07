# Test cases: module 16 (Equipment loans)

Generated from one case list; 110 cases for 41 requirements (feedback 59, held-out 51, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-EQ-01-a | LIB-EQ-01 | Boundary | Lend on Tue at 07:59:59, then at 08:00 | `409 DESK_CLOSED`, then 201 | feedback |
| T-EQ-01-b | LIB-EQ-01 | Boundary | Lend on Tue at 19:59, then another item at 20:00 | 201 with `due_at` 20:00; then `409 DESK_CLOSED` | held-out |
| T-EQ-01-c | LIB-EQ-01 | Error | Lend on Saturday 2026-11-07 10:00 and on the holiday 2026-10-29 10:00 | `409 DESK_CLOSED` both | feedback |
| T-EQ-02-a | LIB-EQ-02 | Normal | Lend on Fri 2026-11-06 20:30 and on Sat 10:00 | `DESK_CLOSED` with `details.opens_at` Mon 2026-11-09 08:00 both | feedback |
| T-EQ-02-b | LIB-EQ-02 | Normal | Lend on Tue 07:00 and on the holiday Thu 2026-10-29 10:00 | `opens_at` Tue 08:00; Fri 2026-10-30 08:00 | held-out |
| T-EQ-03-a | LIB-EQ-03 | Normal | Admin creates a type `chg_4` (4 hours, 5.00) without `requires_training` | 201; code `CHG_4`, `requires_training` false, active | feedback |
| T-EQ-03-b | LIB-EQ-03 | Error | Type `LAP`, then `lap` | `409 CONFLICT` with `details.field` `code` | held-out |
| T-EQ-03-c | LIB-EQ-03 | Error | hours period 9; working_days period 11; period 0; fee 0.49; fee 50.01; max_open 4; max_open 0; code `A`; code `AB-1`; unit `days` | `422 VALIDATION_ERROR` each | feedback |
| T-EQ-03-d | LIB-EQ-03 | Error | Librarian creates a type | `403 FORBIDDEN` | held-out |
| T-EQ-04-a | LIB-EQ-04 | Normal | PATCH `name` and `period`; PATCH `code`; PATCH `period_unit` | 200 with the new values; `422` twice | feedback |
| T-EQ-04-b | LIB-EQ-04 | Normal | Loan Tue 09:00 (4 hours, 5.00); type changed to 2 hours, 10.00; returned 14:30; new loan at 14:30 | Old loan due 13:00, `late_hours` 2, late fee 10.00 (old rate); new loan due 16:30 | held-out |
| T-EQ-05-a | LIB-EQ-05 | Normal | Member reserved Wed 10:00; admin deactivates the type | Reservation `cancelled` with `type_inactive`; one `equipment_reservation_cancelled` notification | feedback |
| T-EQ-05-b | LIB-EQ-05 | Error | Open loan of a type; type deactivated; lend another item; reserve; return the open loan | `409 TYPE_INACTIVE` twice; the return gives 200 | held-out |
| T-EQ-06-a | LIB-EQ-06 | Normal | Types `BB` (no items) and `AA` (available item at A, item on loan at B, retired item); list | Order AA, BB; AA `items_total` 2, `items_available` 1; BB 0 and 0 | feedback |
| T-EQ-06-b | LIB-EQ-06 | Normal | Types `AA` and `BB`, `BB` deactivated; member lists with `is_active=false` | 200; only BB | held-out |
| T-EQ-07-a | LIB-EQ-07 | Normal | Admin creates an item with asset tag `eq-ab12`, value 2500.00 | 201; `asset_tag` `EQ-AB12`, status `available` | feedback |
| T-EQ-07-b | LIB-EQ-07 | Error | Duplicate tag; inactive branch; tag `AB1`; value 0.99; `acquired_on` tomorrow; librarian creates | `409 CONFLICT`; `409 BRANCH_INACTIVE`; `422` three times; `403` | held-out |
| T-EQ-08-a | LIB-EQ-08 | Normal | PATCH an available item: `serial_no`, `value`, `branch_id` B; then `status`, `asset_tag`, `type_id` | 200 with the new values; `422` three times | feedback |
| T-EQ-08-b | LIB-EQ-08 | Error | Item on loan: PATCH `branch_id`; PATCH `value` | `409 INVALID_ITEM_STATUS`; value change 200 | held-out |
| T-EQ-08-c | LIB-EQ-08 | Error | Only item of the type at A; reservation Tue 10:00 at A; move the item to B; then with a second item at A | `409 ITEM_NEEDED_FOR_RESERVATION`; then 200 | feedback |
| T-EQ-09-a | LIB-EQ-09 | Normal | Items EQ-0003 (serial `SN-XY`), EQ-0001, EQ-0002 (branch B); EQ-0001 lent; list and filters | Order by tag; `q=sn-x` → EQ-0003; `branch_id` B → EQ-0002; `status=on_loan` → EQ-0001 | feedback |
| T-EQ-09-b | LIB-EQ-09 | Error | Member reads the item list and one item | `403 FORBIDDEN` both | held-out |
| T-EQ-10-a | LIB-EQ-10 | Normal | Retire an available item; retire it again; `repair-done` on another available item | `retired`; `409 INVALID_ITEM_STATUS` twice | feedback |
| T-EQ-10-b | LIB-EQ-10 | Normal | Two items returned damaged (`in_repair`); librarian retires one; librarian marks it repaired; admin retires the other | `403`; `available`; `retired` | held-out |
| T-EQ-10-c | LIB-EQ-10 | Error | Only item of the type at A; reservation Tue 10:00; retire | `409 ITEM_NEEDED_FOR_RESERVATION`; item stays `available` | feedback |
| T-EQ-11-a | LIB-EQ-11 | Normal | Training for a type that requires it, completed 2026-11-02 | 201; `valid_until` 2027-11-01 | feedback |
| T-EQ-11-b | LIB-EQ-11 | Error | `completed_on` tomorrow; a type without training; the same training twice | `422`; `409 TRAINING_NOT_REQUIRED`; 201 twice | held-out |
| T-EQ-11-c | LIB-EQ-11 | Boundary | Student trained 2025-11-03 (valid until 2026-11-02); lend Mon 2026-11-02, return; lend Tue | Mon 201; Tue `409 TRAINING_REQUIRED` | feedback |
| T-EQ-11-d | LIB-EQ-11 | Error | Member reads own trainings and those of another member | 200 with one record; `403 FORBIDDEN` | held-out |
| T-EQ-12-a | LIB-EQ-12 | Normal | Librarian lends a charger (4 hours) on Tue 10:20 | 201 `EquipmentLoanOut`: open, due 14:20, not extended, not overdue, accrued 0.00, asset tag and type code; item `on_loan` | feedback |
| T-EQ-12-b | LIB-EQ-12 | Error | Both `item_id` and `reservation_id`; neither; a member lends | `422`, `422`, `403` | held-out |
| T-EQ-13-a | LIB-EQ-13 | Error | Passive member; member whose membership ended (Tue 2027-11-02) | `409 MEMBER_PASSIVE`; `409 MEMBERSHIP_EXPIRED` | feedback |
| T-EQ-13-b | LIB-EQ-13 | Error | Guest member | `409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE` | held-out |
| T-EQ-13-c | LIB-EQ-13 | Boundary | Member with debt 50.00; member with debt 49.99 | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00"; 201 | feedback |
| T-EQ-13-d | LIB-EQ-13 | Normal | Type requires training: student without training; academic without training; the student after a training today | `409 TRAINING_REQUIRED`; 201; 201 | held-out |
| T-EQ-13-e | LIB-EQ-13 | Boundary | Student with 2 open equipment loans; academic with 3 (type allows 3) | Next loan: `409 EQUIPMENT_LIMIT_REACHED` with `details.limit` 2 and 3 | feedback |
| T-EQ-13-f | LIB-EQ-13 | Error | Type with `max_open_per_member` 1; student borrows a second item of it | `409 TYPE_LIMIT_REACHED` with `details.limit` 1 | held-out |
| T-EQ-13-g | LIB-EQ-13 | Error | Item on loan to another member; item `in_repair`; item `retired` | `409 ITEM_NOT_AVAILABLE` each | feedback |
| T-EQ-13-h | LIB-EQ-13 | Error | Passive member, inactive type: lend on Saturday; then on Monday 2026-11-09 10:00 | `DESK_CLOSED`; then `TYPE_INACTIVE` (desk before type before member) | held-out |
| T-EQ-14-a | LIB-EQ-14 | Boundary | Charger lent Tue 09:00 (due 13:00); the member borrows a book at 13:15 and another at 13:16 | 201; then `409 MEMBER_HAS_OVERDUE` | feedback |
| T-EQ-14-b | LIB-EQ-14 | Normal | Charger (10.00 per hour) lent Tue 09:00, due 13:00; balance at 18:00 | Loan: overdue, accrued 50.00; balance `accrued_late_fees` and `total_debt` 50.00, `blocked` true | held-out |
| T-EQ-14-c | LIB-EQ-14 | Error | Book lent Mon 2026-11-02 (due 2026-11-16); equipment lent on Tue 2026-11-17 | `409 MEMBER_HAS_OVERDUE` | feedback |
| T-EQ-15-a | LIB-EQ-15 | Normal | Charger (4 hours) lent Tue 10:20:30; another lent 17:30 | Due 14:20:30; due 20:00 | feedback |
| T-EQ-15-b | LIB-EQ-15 | Normal | Laptop (3 working days) lent Wed 2026-10-28 15:00 | Due Tue 2026-11-03 17:00 | held-out |
| T-EQ-15-c | LIB-EQ-15 | Normal | Type of 1 working day lent Fri 2026-11-06 19:00 | Due Mon 2026-11-09 17:00 | feedback |
| T-EQ-16-a | LIB-EQ-16 | Boundary | Loan due Tue 14:20 (5.00 per hour); read at 14:35:00 and at 14:35:01 | Not overdue, accrued 0.00; then overdue, accrued 5.00 | held-out |
| T-EQ-17-a | LIB-EQ-17 | Normal | Loan L2 (M2) Tue 10:00, then L1 (M1) Tue 09:00 (due 13:00); at 14:00 L2 returned; list and filters | Order L1, L2; `member_id` M2 → L2; `overdue=true` → L1; `status=returned` → L2 | feedback |
| T-EQ-17-b | LIB-EQ-17 | Error | Member reads own loan, a loan of another member, the general list, own list, list of another member | 200; 403; 403; 200 with 1 item; 403 | held-out |
| T-EQ-18-a | LIB-EQ-18 | Normal | One item; member reserved Tue 10:00; at 09:50 the librarian lends the item by `item_id` | 201 with `reservation_id`; reservation `collected` with this `loan_id` | feedback |
| T-EQ-18-b | LIB-EQ-18 | Normal | Two items; member reserved Tue 10:00; at 09:40 the member borrows by `item_id` | 201 with `reservation_id` null; reservation stays `booked` | held-out |
| T-EQ-19-a | LIB-EQ-19 | Normal | Charger lent Tue 10:20 (due 14:20); the member extends at 13:00; extends again | 200, due 18:20, `extended` true; then `409 EXTENSION_LIMIT_REACHED` | feedback |
| T-EQ-19-b | LIB-EQ-19 | Boundary | Loan due 17:30 extended at 14:00; loan lent 16:00 (due 20:00) extended | Due 20:00; `409 EXTENSION_NOT_POSSIBLE` | held-out |
| T-EQ-19-c | LIB-EQ-19 | Boundary | Two loans due Tue 14:20; extend one at 14:35:00, the other at 14:35:01 | 200 (due 18:20); `409 LOAN_OVERDUE` | feedback |
| T-EQ-19-d | LIB-EQ-19 | Error | One charger; M2 reserved Tue 16:00; M1 borrows at 10:20 (due 14:20) and extends at 13:00 | `409 ITEM_NEEDED_FOR_RESERVATION`; due stays 14:20 | held-out |
| T-EQ-19-e | LIB-EQ-19 | Normal | Laptop (3 working days) lent Tue 2026-11-03 10:00 (due Fri 17:00); extended Thu; returned; extended again | Due Wed 2026-11-11 17:00; then `409 LOAN_NOT_OPEN` | feedback |
| T-EQ-20-a | LIB-EQ-20 | Normal | Loan Tue 10:00 returned `good` at 13:00; returned again | 200: `returned`, `returned_at` 13:00, `late_hours` 0, `received_by` set; item `available`; no fee; then `409 LOAN_NOT_OPEN` | feedback |
| T-EQ-20-b | LIB-EQ-20 | Normal | Charger lent Fri 16:00 (due 20:00), returned Saturday 10:00 (desk closed) | 200; `late_hours` 14; late fee 70.00 | held-out |
| T-EQ-21-a | LIB-EQ-21 | Normal | Item (value 1000.00) returned `damaged` with `damage_fee` 300.00 | Item `in_repair`; one `equipment_damage_fee` 300.00 with `equipment_loan_id`, `loan_id` null | feedback |
| T-EQ-21-b | LIB-EQ-21 | Error | `damaged` without fee; `good` with fee 1.00; `damaged` 1000.01 (value 1000.00); `damaged` 0.00 | `422`; `422`; `409 DAMAGE_FEE_EXCEEDS_VALUE`; 200 without fee, item `in_repair` | held-out |
| T-EQ-22-a | LIB-EQ-22 | Boundary | Two loans due Tue 14:20; returned at 14:35 and at 14:36 | `late_hours` 0 (no fee) and 1 | feedback |
| T-EQ-22-b | LIB-EQ-22 | Boundary | Two loans due Tue 14:20; returned at 15:20 and at 15:21 | `late_hours` 1 and 2 | held-out |
| T-EQ-22-c | LIB-EQ-22 | Normal | Charger (5.00 per hour, value 1000.00) lent Fri 16:00 (due 20:00), returned Mon 2026-11-09 09:00 | `late_hours` 61 (nights and weekend count); fee 200.00 (cap) | feedback |
| T-EQ-23-a | LIB-EQ-23 | Normal | Type 2 hours, 25.00 per hour; item value 30,000.00; lent Tue 09:00 (due 11:00), returned Wed 17:00 | `late_hours` 30; `equipment_late_fee` 750.00 | feedback |
| T-EQ-23-b | LIB-EQ-23 | Boundary | Same type: value 30,000.00 returned 300 hours late (Sun 2026-11-15 23:00); value 333.33 at 5.00 per hour returned 20 hours late | 6000.00 (20 % cap); 66.67 (cap 66.666 rounded half up) | held-out |
| T-EQ-24-a | LIB-EQ-24 | Normal | Loan Tue 09:00 (due 13:00, 5.00 per hour, value 1000.00) reported lost at 15:00 | `lost`, `returned_at` null, `late_hours` 2; fees `equipment_late_fee` 10.00 and `equipment_lost` 1000.00; item `lost` | feedback |
| T-EQ-24-b | LIB-EQ-24 | Error | Loan reported lost before its due time; reported lost again; a returned loan reported lost | Only `equipment_lost`; `409 LOAN_NOT_OPEN` twice | held-out |
| T-EQ-25-a | LIB-EQ-25 | Normal | Equipment damage fee 30.00; payment 10.00; admin waives the fee | Fee paid 10.00, outstanding 20.00, balance 20.00; after waiving `waived` | feedback |
| T-EQ-25-b | LIB-EQ-25 | Normal | A book damage fee and an equipment damage fee; `GET /api/v1/fees?kind=equipment_damage_fee` | Only the equipment fee | held-out |
| T-EQ-26-a | LIB-EQ-26 | Normal | Member reserves a charger (4 hours) for Tue 10:00 | 201: `booked`, own `member_id`, `ends_at` 14:00, `loan_id` and `closed_at` null | feedback |
| T-EQ-26-b | LIB-EQ-26 | Error | Member sends `member_id`; librarian without `member_id`; start 10:15; start 10:00:30 | `422 VALIDATION_ERROR` each | held-out |
| T-EQ-26-c | LIB-EQ-26 | Normal | Librarian reserves a laptop (3 working days) for a member, Tue 10:00 | 201 for that member; `ends_at` Fri 2026-11-06 17:00 | feedback |
| T-EQ-27-a | LIB-EQ-27 | Boundary | One charger; M1 reserved Tue 14:30 (holds from 14:15); M2 borrows at 10:01, then at 10:00 | `409 ITEM_NEEDED_FOR_RESERVATION`; then 201 (due 14:00, needed until 14:15) | feedback |
| T-EQ-27-b | LIB-EQ-27 | Normal | Two chargers; M1 Tue 10:00, M2 Tue 12:00; M3 Tue 13:00, then Tue 14:30 | M1, M2 201; M3 13:00 `409 NO_EQUIPMENT_AVAILABLE`; M3 14:30 201 | held-out |
| T-EQ-27-c | LIB-EQ-27 | Normal | One charger lent Mon 09:00 (due 13:00) and not returned; at 14:00 another member reserves Tue 10:00 | `409 NO_EQUIPMENT_AVAILABLE` with `details.next_free_at` null (an overdue loan needs its item until returned) | feedback |
| T-EQ-27-d | LIB-EQ-27 | Normal | Two chargers, one `in_repair`; M1 and M2 reserve Tue 10:00 | M1 201; M2 `409 NO_EQUIPMENT_AVAILABLE` | held-out |
| T-EQ-28-a | LIB-EQ-28 | Error | Reservation for a passive member; for a guest | `409 MEMBER_PASSIVE`; `409 EQUIPMENT_NOT_ALLOWED_FOR_TYPE` | feedback |
| T-EQ-28-b | LIB-EQ-28 | Boundary | Membership valid until 2027-11-01; on 2027-10-25 reserve for 2027-11-02 10:00 and for 2027-11-01 10:00 | `409 MEMBERSHIP_EXPIRED`; 201 | held-out |
| T-EQ-28-c | LIB-EQ-28 | Error | Member with debt 50.00 reserves | `409 MEMBER_BLOCKED_BY_DEBT` with `details.total_debt` "50.00" | feedback |
| T-EQ-28-d | LIB-EQ-28 | Boundary | Student trained 2025-11-05 (valid until 2026-11-04); reserves Wed 2026-11-04 10:00 and Thu 2026-11-05 10:00 | 201; `409 TRAINING_REQUIRED` | held-out |
| T-EQ-28-e | LIB-EQ-28 | Boundary | Starts Sat 10:00; Tue 20:00; Tue 07:30; Tue 19:30 | `409 DESK_CLOSED` three times; Tue 19:30 201 with `ends_at` 20:00 | feedback |
| T-EQ-28-f | LIB-EQ-28 | Boundary | Now Mon 09:00: reserve Mon 09:30; at 09:01 another member reserves Mon 09:30 | 201; `409 RESERVATION_TOO_SOON` | held-out |
| T-EQ-28-g | LIB-EQ-28 | Boundary | Today Mon 2026-11-02: reserve Mon 2026-11-16 19:30; Tue 2026-11-17 08:00 | 201; `409 RESERVATION_TOO_FAR_AHEAD` with `details.latest_date` 2026-11-16 | feedback |
| T-EQ-28-h | LIB-EQ-28 | Error | Student with reservations Tue 10:00 and Wed 10:00 reserves Thu 10:00 | `409 EQUIPMENT_RESERVATION_LIMIT_REACHED` | held-out |
| T-EQ-28-i | LIB-EQ-28 | Boundary | Two chargers; member reserved Tue 10:00 (until 14:00); reserves the same type Tue 13:30, then Tue 14:00 | `409 DUPLICATE_EQUIPMENT_RESERVATION`; 201 | feedback |
| T-EQ-28-j | LIB-EQ-28 | Normal | One charger; M1 reserved Tue 10:00 (holds 09:45–14:00); M2 reserves Tue 12:00 | `409 NO_EQUIPMENT_AVAILABLE` with `details.next_free_at` Tue 14:30 | held-out |
| T-EQ-29-a | LIB-EQ-29 | Boundary | Items EQ-0002 and EQ-0001; member reserved Tue 10:00; collected with `reservation_id` at 09:45 | 201: item EQ-0001, `reservation_id` set, due 13:45; reservation `collected` with `loan_id`, `closed_at` 09:45 | feedback |
| T-EQ-29-b | LIB-EQ-29 | Boundary | Reservation Tue 10:00 collected at 09:44, at 10:30:01, then at 10:30 | `409 RESERVATION_NOT_READY`; `409 RESERVATION_EXPIRED`; 201 | held-out |
| T-EQ-29-c | LIB-EQ-29 | Error | M2 collects M1's reservation; M1 cancels and then collects | `409 RESERVATION_OF_OTHER_MEMBER`; `409 RESERVATION_NOT_ACTIVE` | feedback |
| T-EQ-29-d | LIB-EQ-29 | Error | One charger lent to M0 Mon 09:00 (due 13:00, not returned); M1 reserved Tue 10:00 on Mon; M1 collects Tue 09:50 | `409 ITEM_NOT_AVAILABLE`; reservation stays `booked` | held-out |
| T-EQ-30-a | LIB-EQ-30 | Normal | Member cancels own reservation; cancels again | 200 `cancelled`, `member_request`, `closed_at` set, no notification; then `409 RESERVATION_NOT_ACTIVE` | feedback |
| T-EQ-30-b | LIB-EQ-30 | Normal | Another member cancels M's reservation; the librarian cancels it | `403 FORBIDDEN`; then `staff_request` and one `equipment_reservation_cancelled` notification for M | held-out |
| T-EQ-31-a | LIB-EQ-31 | Boundary | Reservation Tue 10:00; process at 10:30:00 and at 10:30:01 | `expired_reservations` 0, then 1; reservation `expired` with `closed_at` 10:30:01 | feedback |
| T-EQ-31-b | LIB-EQ-31 | Normal | One charger; M1 reserved Tue 10:00; at 10:31 (not processed) M2 borrows it; at 10:40 process | 201 for M2; then 1 expired and one `equipment_reservation_expired` notification for M1 | held-out |
| T-EQ-32-a | LIB-EQ-32 | Normal | Loan due Tue 13:00; process at 14:00 twice; process Wed 09:00 | `{expired_reservations: 0, overdue_notices: 1}`, then 0 notices; Wed 1; member has 2 `equipment_overdue` notifications | held-out |
| T-EQ-33-a | LIB-EQ-33 | Normal | Two chargers; reservation Tue 10:00 (holds 09:45–14:00); availability for Tue | Capacity 2; 24 slots 08:00…19:30; free 2 at 09:00, 1 at 09:30 and 13:30, 2 at 14:00 | feedback |
| T-EQ-33-b | LIB-EQ-33 | Normal | Member reads availability for Saturday | 200; capacity 1; `slots` empty | held-out |
| T-EQ-34-a | LIB-EQ-34 | Normal | Reservations R1 (M1 Wed 10:00), R2 (M2 Tue 12:00), R3 (M1 Tue 08:00); R2 cancelled; list and filters | Order R3, R2, R1; `from`=`to`=Wed → R1; `status=cancelled` → R2; `member_id` M1 → R3, R1 | feedback |
| T-EQ-34-b | LIB-EQ-34 | Error | Member reads the general list, own list, own reservation, a reservation of another member | 403; 200 with 1 item; 200; 403 | held-out |
| T-EQ-35-a | LIB-EQ-35 | Error | Member with an open equipment loan (no book loans) is deactivated | `409 MEMBER_HAS_OPEN_LOANS` | feedback |
| T-EQ-35-b | LIB-EQ-35 | Normal | Member with a booked reservation is deactivated | Reservation `cancelled` with `member_deactivated`; one `equipment_reservation_cancelled` notification | held-out |
| T-EQ-36-a | LIB-EQ-36 | Error | Branch with one equipment item is deactivated; after the item is retired | `409 BRANCH_IN_USE`; then 200 | held-out |
| T-EQ-37-a | LIB-EQ-37 | Normal | Member reserved Wed 10:00 and borrowed Tue 09:00 (due 13:00); summary at 14:00 | `equipment` = `{open_loans: 1, overdue_loans: 1, booked_reservations: 1}`; `borrowing.eligible` false with `MEMBER_HAS_OVERDUE` | feedback |
| T-EQ-38-a | LIB-EQ-38 | Normal | Item EQ-0777 lent and returned | One `equipment_loan_created` and one `equipment_loan_returned` notification with `equipment_loan_id`; messages contain `EQ-0777` | feedback |
| T-EQ-38-b | LIB-EQ-38 | Normal | Member reserves, cancels own reservation, borrows and extends | The member's notifications: only `equipment_loan_created` | held-out |
| T-EQ-38-c | LIB-EQ-38 | Normal | Loan reported lost before its due time | One `equipment_loan_lost` and one `fee_created` notification | feedback |
| T-EQ-39-a | LIB-EQ-39 | Normal | Type and item created, training recorded, item lent and returned; audit log filtered by event | One entry each for `equipment_type_created`, `equipment_item_created`, `equipment_training_recorded`, `equipment_loan_created`, `equipment_loan_returned` | feedback |
| T-EQ-39-b | LIB-EQ-39 | Normal | Reservation created and cancelled; process run | One entry each for `equipment_reservation_created`, `equipment_reservation_cancelled`, `equipment_processed` | held-out |
| T-EQ-40-a | LIB-EQ-40 | Normal | Types AA (items at A, A, B) and BB (unused). Mon: reservation AA at A for Wed 10:00. Tue 09:00: three AA loans; 12:00 one returned damaged (40.00); 15:00 one returned 2 h late (10.00). Wed 10:31 process. Report Mon–Wed for branch A; then without branch | Branch A: AA `{loans 2, late_returns 1, late_hours 2, damaged_returns 1, lost 0, reservations 1, expired_reservations 1, fees_created "50.00"}`, BB all 0 and "0.00"; without branch AA `loans` 3 | feedback |
| T-EQ-40-b | LIB-EQ-40 | Error | `from` > `to`; range of 367 days; member reads the report; librarian reads 2026-01-01 – 2026-12-31 | `422`; `422`; `403`; 200 | held-out |
| T-EQ-41-a | LIB-EQ-41 | Normal | Equipment type, item and loan exist; `GET /api/v1/export` | The export has exactly the keys of 22.1 (no equipment data) | feedback |
