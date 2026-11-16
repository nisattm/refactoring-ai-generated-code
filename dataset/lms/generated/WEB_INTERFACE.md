# Web interface requirements

> Version 1.0 · 2026-11-16. The web interface (frontend) of the Library Management System specified in `REQUIREMENTS.md`. It is generated in three steps after all backend modules (step 24: sections 1 and 2; step 25: section 3, modules 15–21; step 26: section 3, modules 22–28). The screens of module 29 (section 3.15) are generated with the module itself in step 27. It only calls the REST API, is not part of the measured code and is not refactored (ADR 002); it lets the instructor and the team use the system. Section and requirement numbers without a prefix (6.6, LIB-MEM-01) refer to `REQUIREMENTS.md`.

## 1. General rules

| ID | Requirement |
| --- | --- |
| LIB-UI-GEN-01 | **Technology.** Plain HTML, CSS and JavaScript (ES modules allowed) in the folder `web/` next to the `lms` package. No build step, no package manager and no files, fonts or scripts loaded from the internet. The interface uses only the REST API under `/api/v1` and `GET /health`, on the same origin. |
| LIB-UI-GEN-02 | **Serving.** `create_app` serves the folder `web/` at `/ui/`: `GET /ui/` returns `web/index.html`, other files by their path (for example `/ui/app.js`). When the folder does not exist the application starts and the API works unchanged. No other path of the API changes. |
| LIB-UI-GEN-03 | **Routes.** The interface is one page. Every screen of sections 2 and 3 has the hash route `#/<id>`, where `<id>` is its requirement ID without `LIB-UI-`, in lower case (LIB-UI-ROOM-01 → `/ui/#/room-01`). Opening the URL of a route shows that screen directly, also after a reload. Screens marked "Part of …" have no route; their content is shown on the named screen. A screen about one record (a member, a book, an event …) opened without one first shows a field to choose it. `/ui/` without a route shows the home screen (LIB-UI-GEN-08). |
| LIB-UI-GEN-04 | **Login.** Route `#/login`, heading "Log in", fields `email` and `password`, button "Log in" (LIB-AUTH-06). The token is kept in `sessionStorage`. After a successful login the screen that was requested is shown, otherwise the home screen. A route opened without a session, and any response `401`, shows the login screen; after logging in the requested screen is shown. A failed login shows the error as in LIB-UI-GEN-12. |
| LIB-UI-GEN-05 | **Header.** After login every screen has a header with the user's full name, the role and a button "Log out", which calls LIB-AUTH-14, removes the token and shows the login screen. |
| LIB-UI-GEN-06 | **Menu.** A navigation menu, grouped by module, has one link per screen that the user's role may use (6.6 and the roles named in each screen); the link text is the screen name. Screens marked "Part of …" have no link. |
| LIB-UI-GEN-07 | **Heading.** Every screen shows exactly one visible `<h1>`, whose text is the screen name: the bold text of its requirement without the final period (LIB-UI-ROOM-01 → "Room list"). |
| LIB-UI-GEN-08 | **Home.** Route `#/home`, heading "Home". A member sees their member number, membership validity, open loans, active reservations and balance (LIB-MEM-12); librarians and admins see links to the desk screens of their role. |
| LIB-UI-GEN-09 | **Not allowed.** A route of a screen that the user's role may not use shows the heading "Not allowed" and the text "You do not have access to this screen."; no API request of that screen is made. |
| LIB-UI-GEN-10 | **Form fields.** Every `input`, `select` and `textarea` has a visible label. A field that holds a request field or a query parameter has `name` equal to its API name (for example `name="full_name"`, `name="membership_type"`). Fields with fixed values (6.6, statuses, types, kinds) are `select` elements whose option values are the API values. Branches, rooms, types, partners, suppliers and other short lists are `select` elements whose option values are the record ids. Members are chosen by a text field `member_no` (looked up with the filter `q` of LIB-MEM-06, exact `member_no` match), books by `isbn` and copies by `barcode`; where the API accepts `barcode` or `card_no` directly, the field sends it unchanged. Dates are `type="date"` inputs, times `type="time"`. |
| LIB-UI-GEN-11 | **Buttons.** Actions are `button` elements. A button's text is the action name written in quotes in the screen's requirement (for example "Book", "Check in"); otherwise it is the verb of the action ("Create", "Save", "Cancel"). |
| LIB-UI-GEN-12 | **Results and errors.** After a successful action a short message is shown in an element with `role="status"` and the data on the screen is reloaded. An error response shows `error.code` and `error.message` (and `details` where the screen says so) in an element with `role="alert"`; the entered values stay. A failed request without a response shows "The server cannot be reached." the same way. An element with `role="alert"` exists only while an error is shown. |
| LIB-UI-GEN-13 | **Lists.** Lists are `table` elements with a header row. Paginated lists (LIB-COM-18) have the buttons "Previous" and "Next"; an empty list shows "No records". |
| LIB-UI-GEN-14 | **Values.** Dates are shown as `YYYY-MM-DD`, times as `HH:MM` in local time, amounts as returned by the API with "TL". "Today" is `today` of `GET /health`; the browser clock is not used for library dates. |
| LIB-UI-GEN-15 | **Confirmation.** Actions that delete, cancel, deactivate, withdraw or lift show a confirmation inside the page with the buttons "Confirm" and "Back" before the request. Browser dialogs (`alert`, `confirm`, `prompt`) are not used. |
| LIB-UI-GEN-16 | **Quality.** Text is in English. Screens work with the keyboard and at widths from 390 to 1920 pixels in a current Chromium browser. Using any screen causes no uncaught JavaScript error. |

## 2. Screens of modules 1–14

Every action calls the endpoint named in brackets and shows the result as in LIB-UI-GEN-12. Only the actions of the user's role are shown (6.6).

| ID | Requirement |
| --- | --- |
| LIB-UI-CAL-01 | **Calendar.** All roles. Official holidays of a chosen year (section 5); a date field showing whether that date is a working day; tools for the next working day, adding working days and counting working days between two dates (LIB-COM-08 to LIB-COM-10). |
| LIB-UI-ACCT-01 | **My account.** All roles. Own user data (LIB-AUTH-15); a form with `current_password` and `new_password` and the button "Change password" (LIB-AUTH-16). |
| LIB-UI-USR-01 | **Users.** Admin. Users with filters (role, active); create a librarian or admin with `email`, `full_name`, `role`, `password` and the button "Create"; change name, role and active state; "Reset password" (section 6). |
| LIB-UI-MEM-01 | **Member list.** Librarian and admin. Members with the filters of LIB-MEM-06; each row shows member number, full name, type, status and valid until; selecting a row opens the member page. |
| LIB-UI-MEM-02 | **Register member.** Librarian and admin. Fields `full_name`, `email`, `phone`, `membership_type`, `university_id`, `home_branch_id`, `password` and the button "Register" (LIB-MEM-01); the field rules of LIB-MEM-02 are shown next to the fields; on success the member number is shown and a link opens the member page. |
| LIB-UI-MEM-03 | **Member page.** Librarian and admin. Member data and summary (LIB-MEM-12) with borrowing eligibility and reasons; "Edit" (LIB-MEM-07), "Renew membership" (LIB-MEM-09), "Deactivate" and "Activate" (LIB-MEM-10, LIB-MEM-11); the member's loans, reservations, fees and notifications. Screens of later modules add parts to this page. |
| LIB-UI-MEM-04 | **My membership.** Member. Own member record (LIB-MEM-13) and summary (LIB-MEM-12) with borrowing eligibility and reasons. |
| LIB-UI-CAT-01 | **Books.** All roles. Books with the filters of LIB-CAT-04, title, authors, year and availability; selecting a row opens the book page; librarian and admin have "New book". |
| LIB-UI-CAT-02 | **Book page.** All roles. Book data, availability per branch and copies with status, current branch and shelf; a member has "Reserve" (LIB-RES-01); librarian and admin edit and delete the book (LIB-CAT-05, LIB-CAT-06), add copies with `barcode`, `home_branch_id`, `price`, `acquired_on`, `shelf_location` and the button "Add copy" (LIB-CAT-07), change a copy (LIB-CAT-09), "Withdraw" and "Repaired" (section 8). |
| LIB-UI-CAT-03 | **Book form.** Librarian and admin. Fields `isbn`, `title`, `subtitle`, authors (searched by name, 1–10 in order), `publisher_id`, `publication_year`, `language`, `classification` and the button "Save" (LIB-CAT-03, LIB-CAT-05); ISBN errors are shown next to the field. |
| LIB-UI-CAT-04 | **Authors and publishers.** Librarian and admin. Two lists with search (LIB-CAT-01); create, rename and delete (`IN_USE` is shown as an error). |
| LIB-UI-LOAN-01 | **Loan desk.** Librarian and admin. Lending: fields `member_no` and `barcode` and the button "Lend" (LIB-LOAN-01); the new loan's due date is shown. Return: field `barcode`, the return branch (`branch_id`), `condition` and `damage_fee` and the button "Return" (LIB-LOAN-09) for the open loan of that copy; late days and fees are shown. |
| LIB-UI-LOAN-02 | **Loans.** Librarian and admin. Loans with the filters of LIB-LOAN-14; per open loan "Renew", "Return" and "Report lost" (LIB-LOAN-07, LIB-LOAN-09, LIB-LOAN-13). |
| LIB-UI-LOAN-03 | **My loans.** Member. Own loans with due date, overdue flag, renewals and accrued late fee; "Renew" on open loans (LIB-LOAN-07). |
| LIB-UI-RES-01 | **My reservations.** Member. Own reservations with status, queue position and `hold_until`; "Cancel" (section 10). |
| LIB-UI-RES-02 | **Reservations.** Librarian and admin. Reservations with filters; create one for a member (`member_no`, `isbn`, `pickup_branch_id`, button "Reserve"); the queue of a book; "Cancel"; "Process expired" shows the count (section 10). |
| LIB-UI-FEE-01 | **My fees.** Member. Own balance (LIB-FEE-10), fees with outstanding amounts and payments. |
| LIB-UI-FEE-02 | **Fees and payments.** Librarian and admin. A member's balance, fees and payments; a payment with `amount` and `method` and the button "Pay" (LIB-FEE-05) shows its allocations; admin has "Waive" with `reason` (LIB-FEE-07); all fees with filters (section 11). |
| LIB-UI-NOT-01 | **My notifications.** Member. Own notifications, newest first, unread marked; "Mark as read" and "Mark all as read"; the unread count is shown in the header (section 14). |
| LIB-UI-NOT-02 | **Notifications.** Librarian and admin. All notifications with filters; "Run reminders" shows the count (section 14). |
| LIB-UI-SRCH-01 | **Search.** All roles. Fields `q`, `author`, `publisher`, `language`, `year_from`, `year_to`, `classification_prefix`, `available_only`, `branch_id` and the button "Search" (section 15); results with title, authors, year and availability; selecting a result opens the book page. |
| LIB-UI-REP-01 | **Most borrowed.** Librarian and admin. Range, branch and limit; LIB-REP-01 as a table. |
| LIB-UI-REP-02 | **Overdue loans.** Librarian and admin. Branch filter; LIB-REP-02 as a table. |
| LIB-UI-REP-03 | **Monthly summary.** Librarian and admin. Year, month and branch; LIB-REP-03 as a table. |
| LIB-UI-REP-04 | **Copies by status.** Librarian and admin. Branch filter; LIB-REP-04 as a table. |
| LIB-UI-BR-01 | **Branches.** All roles. Branches with code, name, address and active state (LIB-BR-02); admin creates a branch (`code`, `name`, `address`, button "Create") and changes name, address and active state; `BRANCH_IN_USE` is shown with its `details`. |
| LIB-UI-BR-02 | **Transfers.** Librarian and admin. Relocate a copy by `barcode` to a branch; transfers with filters; "Process arrivals" shows the count (section 17). |
| LIB-UI-PUR-01 | **Suppliers.** Librarian and admin. List, create and change suppliers (section 18). |
| LIB-UI-PUR-02 | **Purchase orders.** Librarian and admin. Orders with filters; a draft with supplier, branch and lines (book, quantity, unit price); change a draft; "Submit", "Cancel" and "Receive" with the received quantities (section 18). |
| LIB-UI-AUD-01 | **Audit log.** Admin. The audit log with the filters of LIB-AUD-03. |
| LIB-UI-AUD-02 | **Import and export.** Admin. Choose a JSON file and "Import" (LIB-IO-01) shows the counts or the validation errors; "Export" downloads the JSON of LIB-IO-07; one download link per CSV entity (LIB-IO-08). |

## 3. Screens of modules 15–29

Same conventions as section 2.

### 3.1 Module 15: Study rooms

| ID | Requirement |
| --- | --- |
| LIB-UI-ROOM-01 | **Room list.** All roles. Lists rooms (LIB-ROOM-03) with filters branch, kind, minimum capacity and features; each row shows code, name, branch, kind, capacity, features, hours and active state. Selecting a room opens its availability. |
| LIB-UI-ROOM-02 | **Availability.** All roles. A date picker and the room's slots of that day (LIB-ROOM-08) as a grid: free slots selectable, booked slots marked, a closed day shown as "closed". Selecting one or more consecutive free slots opens the booking form with room, date and times filled in. |
| LIB-UI-ROOM-03 | **Find a free room.** All roles. Date, start and end time and optional filters; shows the matching rooms (LIB-ROOM-09); each result has a "Book" action that opens the booking form. |
| LIB-UI-ROOM-04 | **Booking form.** Member (for themselves); librarian and admin also choose the organizer member. Fields: room, date, start, end, participants (group rooms only; members searched by name or member number), purpose. "Book" sends LIB-ROOM-10 and on success shows the booking. Error codes of LIB-ROOM-12 to LIB-ROOM-15 are shown with their `details` (for example the latest allowed date or the quota used). |
| LIB-UI-ROOM-05 | **My room bookings.** Member. Lists their bookings (LIB-ROOM-18) with status; actions per booking as allowed: "Check in" (LIB-ROOM-27), "Check out" (LIB-ROOM-29), "Cancel" with a warning when the cancellation is late (LIB-ROOM-24), "Leave" for participants (LIB-ROOM-21), "Edit participants" (LIB-ROOM-20). Shows room bans in force and this week's hours (LIB-ROOM-40). |
| LIB-UI-ROOM-06 | **Desk view.** Librarian and admin. Today's bookings of a chosen branch ordered by start time, with check-in, check-out and cancel actions, and a "Process" action (LIB-ROOM-28) that shows the three counts. A "Send reminders" action calls LIB-ROOM-42 and shows the count. |
| LIB-UI-ROOM-07 | **Room management.** Admin. Create a room and edit name, features, hours, capacity and active state (LIB-ROOM-01, LIB-ROOM-04); `ROOM_HAS_BOOKINGS` shows the listed booking ids; deactivation asks for confirmation and states that future bookings will be cancelled (LIB-ROOM-06). |
| LIB-UI-ROOM-08 | **Room bans.** Part of the member page (LIB-UI-MEM-03). Librarian and admin see a member's bans (LIB-ROOM-36) on the member page; admin can create a ban (LIB-ROOM-34) and lift one (LIB-ROOM-35). |
| LIB-UI-ROOM-09 | **Room usage report.** Librarian and admin. Date range and branch; shows LIB-ROOM-44 as a table. |

### 3.2 Module 16: Equipment loans

| ID | Requirement |
| --- | --- |
| LIB-UI-EQ-01 | **Equipment catalog.** All roles. Lists types (LIB-EQ-06) with items total and available; selecting a type and a branch shows the availability grid of a chosen date (LIB-EQ-33), a closed day shown as "closed". |
| LIB-UI-EQ-02 | **Reserve equipment.** Member for themselves; librarian and admin also choose the member. Type, branch and start (picked from the grid); shows the resulting `ends_at` before sending LIB-EQ-26. Errors of LIB-EQ-28 are shown with their `details`; for `NO_EQUIPMENT_AVAILABLE` the next free time is offered as a button that fills in the start. |
| LIB-UI-EQ-03 | **My equipment.** Member. Open and past loans (LIB-EQ-17) with due time, overdue flag and accrued fee; "Extend" (LIB-EQ-19) on open loans; booked reservations (LIB-EQ-34) with "Cancel" (LIB-EQ-30); own trainings with validity (LIB-EQ-11). |
| LIB-UI-EQ-04 | **Equipment desk.** Librarian and admin. Find a member; lend by asset tag (LIB-EQ-12) or collect one of the member's reservations (LIB-EQ-29); return with condition and damage fee (LIB-EQ-20, LIB-EQ-21); report lost (LIB-EQ-24); today's reservations of a chosen branch; "Process" (LIB-EQ-31, LIB-EQ-32) shows both counts. `DESK_CLOSED` shows the opening time. |
| LIB-UI-EQ-05 | **Types and items.** Admin creates and changes types and items (LIB-EQ-03, LIB-EQ-04, LIB-EQ-07, LIB-EQ-08) and retires items (LIB-EQ-10); deactivating a type asks for confirmation and states that booked reservations will be cancelled (LIB-EQ-05). Librarian sees the item list with filters (LIB-EQ-09) and marks repairs done. |
| LIB-UI-EQ-06 | **Trainings.** Part of the member page (LIB-UI-MEM-03). Librarian and admin record a training on the member page (LIB-EQ-11) and see the member's trainings with validity. |
| LIB-UI-EQ-07 | **Equipment usage report.** Librarian and admin. Date range and branch; shows LIB-EQ-40 as a table. |

### 3.3 Module 17: Digital resources

| ID | Requirement |
| --- | --- |
| LIB-UI-DIG-01 | **Digital library.** All roles. Resources with kind, availability and waiting holds; e-books also on the book page (LIB-DIG-09). |
| LIB-UI-DIG-02 | **Borrow, hold, open.** Member for themselves, staff choose the member. "Borrow" when a copy is free, otherwise "Place hold" with the queue length; "Open session" for databases with the remaining minutes; errors with `details`. |
| LIB-UI-DIG-03 | **My digital library.** Member. Active and past loans with due time, "Return" and "Renew" (with `renewable_from`); holds with position or "ready until", "Borrow" and "Cancel"; open sessions with "Close". |
| LIB-UI-DIG-04 | **Licenses.** Admin adds and cancels licenses (with an optional purchase order); librarian sees them. |
| LIB-UI-DIG-05 | **Resources.** Librarian and admin create and change resources; deactivation asks for confirmation (holds will be cancelled). |
| LIB-UI-DIG-06 | **Digital desk.** Librarian and admin. Hold queue of a resource; "Process" (LIB-DIG-35) with its four counts. |
| LIB-UI-DIG-07 | **Digital usage report.** Librarian and admin. Date range and kind; LIB-DIG-39 as a table. |

### 3.4 Module 18: Interlibrary loans

| ID | Requirement |
| --- | --- |
| LIB-UI-ILL-01 | **Request a book from another library.** Member for themselves, staff choose the member. Title, author, ISBN; `AVAILABLE_LOCALLY` links to the book page. |
| LIB-UI-ILL-02 | **My interlibrary requests.** Member. Requests with status, pickup branch and `collect_until`, due date and accrued late fee; "Cancel" and "Ask for more time". |
| LIB-UI-ILL-03 | **Interlibrary desk (incoming).** Librarian and admin. Requests by status; send to a partner (partners already tried are not offered), record rejection, receive (with the computed member due date shown before saving), collect, return, close, report lost, answer renewal requests; "Process" with its counts. |
| LIB-UI-ILL-04 | **Interlibrary desk (outgoing).** Librarian and admin. New outgoing request, ship with a copy chosen from the available copies, decline, returned, lost; overdue outgoing requests highlighted. |
| LIB-UI-ILL-05 | **Partners.** Admin creates and changes partners; librarian sees them with their open counts. |
| LIB-UI-ILL-06 | **Interlibrary activity report.** Librarian and admin. Date range; LIB-ILL-38 as a table. |

### 3.5 Module 19: Staff and shifts

| ID | Requirement |
| --- | --- |
| LIB-UI-STF-01 | **Staff.** Admin. List, create and change staff profiles; deactivation asks for confirmation (planned shifts will be cancelled). |
| LIB-UI-STF-02 | **Branch hours and closures.** Admin sets hours and `min_staff`; adds and removes closures and sees the counts of cancelled shifts and bookings. All users see a branch's open days for a month. |
| LIB-UI-STF-03 | **Shift plan.** Admin. Week view per branch with shifts per day; plan, change, cancel; "Copy last week" with the skipped shifts and their reasons; coverage per half hour with missing slots highlighted. |
| LIB-UI-STF-04 | **My shifts.** Librarian and admin. Own shifts; "Check in" and "Check out" buttons in the allowed window; worked and late minutes. |
| LIB-UI-STF-05 | **Leave.** Librarian and admin. Request leave (with the working days computed before sending), see own requests and balance; admin sees pending requests and approves or rejects them, with the shifts that will be cancelled shown before approving. |
| LIB-UI-STF-06 | **Staff reports.** Admin. Staff hours and branch coverage reports as tables. |

### 3.6 Module 20: Events

| ID | Requirement |
| --- | --- |
| LIB-UI-EVT-01 | **Event calendar.** All roles. Month and list views of published events with free places and waiting list; filters by branch and kind; staff also see drafts. |
| LIB-UI-EVT-02 | **Event page.** All roles. Details, "Register" (or "Join waiting list" with the position), "Cancel" with a warning when the cancellation is late; errors with `details`. |
| LIB-UI-EVT-03 | **My events.** Member. Upcoming and past registrations with status, position and fee; bans with end dates. |
| LIB-UI-EVT-04 | **Event management.** Librarian and admin. Create and change events and series (with the skipped dates shown), choose a free group room and the responsible staff (with `staff_covered`), publish, cancel; registrations list. |
| LIB-UI-EVT-05 | **Event desk.** Librarian and admin. Today's events with check-in for each registered member; "Process" with its counts. |
| LIB-UI-EVT-06 | **Attendance report.** Librarian and admin. Date range, branch, kind; LIB-EVT-46 as a table. |

### 3.7 Module 21: Course reserves

| ID | Requirement |
| --- | --- |
| LIB-UI-CRS-01 | **Courses.** Librarian and admin. List with filters; create and change courses; activate and close (with the open loans shown when closing is refused). |
| LIB-UI-CRS-02 | **Enrollment.** Librarian and admin. Paste or pick members, see the enrolled ones and the skipped ones with their reasons; drop. |
| LIB-UI-CRS-03 | **Reading list.** Librarian, admin and the course's instructor. Add books from search, change kind, loan period and wanted copies, drag to reorder, remove; for each item the copies on reserve, available now and next due time. |
| LIB-UI-CRS-04 | **Reserve desk.** Librarian and admin. Scan a barcode to lend, return, renew or report lost; place copies on reserve or take them off; overdue reserve loans highlighted; "Process" with its counts. |
| LIB-UI-CRS-05 | **My courses.** Member. Own courses with reading lists, what is available now, own reserve loans with due times and fees. |
| LIB-UI-CRS-06 | **Course reserves report.** Librarian and admin. Date range and branch; LIB-CRS-46 as a table. |

### 3.8 Module 22: Donations

| ID | Requirement |
| --- | --- |
| LIB-UI-DON-01 | **Donors.** Librarian and admin. List with filters and levels; create and change donors; admin merges two donors; a donor page with its history. |
| LIB-UI-DON-02 | **Offer form.** Member (own) and staff. Branch, note and a list of titles with author, ISBN, year, condition and quantity; change or cancel while `offered`. |
| LIB-UI-DON-03 | **Review.** Librarian and admin. The offer's items with the suggestions pre-filled; for each item accept (search the catalog for the book, quantity, value per copy) or decline with a reason. |
| LIB-UI-DON-04 | **Receiving desk.** Librarian and admin. Scan barcodes per accepted item, see what is still expected and the `expected_by` date; "Process" with its count. |
| LIB-UI-DON-05 | **Receipt and my donations.** Member: own donations with status and receipts. Staff: print view of a receipt. |
| LIB-UI-DON-06 | **Donor wall and reports.** All users see the donor wall of a year; librarian and admin see the donations and donor reports. |

### 3.9 Module 23: Preservation

| ID | Requirement |
| --- | --- |
| LIB-UI-PRE-01 | **Budgets.** Admin sets the yearly budget of each branch; librarian and admin see committed, spent and available. |
| LIB-UI-PRE-02 | **Inspection.** Librarian and admin. Scan a copy, record its condition with a note, see its inspection history. |
| LIB-UI-PRE-03 | **Jobs.** Librarian and admin. Suggestions of a branch, create jobs from them, approve (with the budget shown), cancel, send in-house jobs, return with outcome and cost; overdue jobs highlighted; "Process" with its counts. |
| LIB-UI-PRE-04 | **Shipments.** Librarian and admin. Pick approved supplier jobs of a branch and send them as one shipment; list shipments with their open jobs. |
| LIB-UI-PRE-05 | **Preservation reports.** Librarian and admin. Preservation report of a year and damage recovery report of a range as tables. |
| LIB-UI-PRE-06 | **Repairs on the book page.** Part of the book page (LIB-UI-CAT-02). All users see "in repair, expected back on …" in the availability of a book. |

### 3.10 Module 24: Inventory counts

| ID | Requirement |
| --- | --- |
| LIB-UI-INV-01 | **Counts.** Librarian and admin. Start a count for a branch or a shelf prefix; list counts with status and progress. |
| LIB-UI-INV-02 | **Scanning.** Librarian and admin. A scan field that accepts a barcode scanner; each scan shows its result in colour; undo the last scan; progress bar of expected copies. |
| LIB-UI-INV-03 | **Closing.** Librarian and admin. Summary with accuracy; lists of missing and moved copies with shelf locations; cancel or apply (admin when more than 10 copies are missing). |
| LIB-UI-INV-04 | **Problems.** Librarian and admin. Scans grouped by result (unknown, wrong branch, unexpected status, found lost) with what applying will do. |
| LIB-UI-INV-05 | **Found copies.** Librarian and admin. Mark a missing or lost copy as found at a branch. |
| LIB-UI-INV-06 | **Inventory report.** Librarian and admin. The yearly report per branch as a table. |

### 3.11 Module 25: Purchase suggestions

| ID | Requirement |
| --- | --- |
| LIB-UI-SUG-01 | **Suggest a book.** Member. Form with title, author, ISBN, year, reason and branch; the "already owned" and "already suggested" answers link to the book or the suggestion. |
| LIB-UI-SUG-02 | **Suggestions board.** All users. Open suggestions by score with search; members support or stop supporting with one click and choose "reserve when it arrives". |
| LIB-UI-SUG-03 | **My suggestions.** Member. Own suggestions with status and review notes; supported suggestions; change or withdraw while submitted. |
| LIB-UI-SUG-04 | **Review queue.** Librarian and admin. Submitted suggestions by score; approve (catalog search for the book, quantity, price), reject with a reason, merge duplicates. |
| LIB-UI-SUG-05 | **Ordering.** Librarian and admin. Pick approved suggestions of a branch and a supplier; preview the order lines and total; create the draft order. |
| LIB-UI-SUG-06 | **Suggestions report.** Librarian and admin. Date range and branch; LIB-SUG-44 with the top list. |

### 3.12 Module 26: Reading programs

| ID | Requirement |
| --- | --- |
| LIB-UI-RDP-01 | **Programs.** Librarian and admin. Create, change, publish and cancel programs; see participants and completion. |
| LIB-UI-RDP-02 | **Join.** Member. Running and upcoming programs with goal, dates and free places; join with "show my name" choice; leave. |
| LIB-UI-RDP-03 | **My progress.** Member. Points, books, level and rank per program, with the entries that counted and the reward received. |
| LIB-UI-RDP-04 | **Leaderboard.** All users. Ranked list with short names, points, books and level. |
| LIB-UI-RDP-05 | **Manual entries.** Librarian and admin. Add or remove a book read elsewhere for a participant (at most 3). |
| LIB-UI-RDP-06 | **Programs report.** Librarian and admin. LIB-RDP-44 as a table with top books. |

### 3.13 Module 27: Announcements and messages

| ID | Requirement |
| --- | --- |
| LIB-UI-MSG-01 | **Announcements.** Librarian and admin. Write, schedule, pin, publish and withdraw announcements for a branch and membership types; reach and read rate. |
| LIB-UI-MSG-02 | **Member home.** Part of the home screen (LIB-UI-GEN-08). Member. Live announcements (pinned first, unread marked) with an unread counter. |
| LIB-UI-MSG-03 | **Inbox.** Librarian and admin. Threads with filters (mine, overdue, category); assign, reply, write internal notes, close. |
| LIB-UI-MSG-04 | **My messages.** Member. Own threads with unread replies; write to a branch about a loan or a fee; close, reopen and rate. |
| LIB-UI-MSG-05 | **Messaging report.** Librarian and admin. LIB-MSG-39 as a table. |
| LIB-UI-MSG-06 | **Header badges.** Part of the header (LIB-UI-GEN-05). All users. Unread announcement and reply counters in the page header. |

### 3.14 Module 28: Member cards and building access

| ID | Requirement |
| --- | --- |
| LIB-UI-ACC-01 | **Cards.** Librarian and admin. Issue a card, report it lost or damaged, see the replacement fee; card history of a member. |
| LIB-UI-ACC-02 | **Gate.** Librarian and admin. Fields `branch_id`, `direction` (`in` or `out`) and `card_no` or `pass_code`, and the button "Scan" (LIB-ACC-14); the result (`entered` or `left` with the member's name or the pass code) is shown large in green, an error with its code large in red. |
| LIB-UI-ACC-03 | **Occupancy.** All users see how full a branch is; staff see who is inside and can end a visit. |
| LIB-UI-ACC-04 | **Day passes.** Librarian and admin. Sell, print and cancel passes; today's passes of a branch. |
| LIB-UI-ACC-05 | **Bans and alerts.** Librarian and admin. Create and lift bans; lost-card alerts. |
| LIB-UI-ACC-06 | **Visits report.** Librarian and admin. LIB-ACC-44 as a table; members see their own visit history. |

### 3.15 Module 29: Printing and copying

| ID | Requirement |
| --- | --- |
| LIB-UI-PRT-01 | **Print.** Member. Fields `printer_id`, `title`, `pages`, `copies`, `color`, `duplex` and the button "Send" (LIB-PRT-07), with sheets and expected cost shown before sending; own queued jobs with "Release" and "Cancel"; free pages and pack pages left. |
| LIB-UI-PRT-02 | **My printing.** Member. Own jobs with status, pages and amount; own packs; quota of a chosen month. |
| LIB-UI-PRT-03 | **Printers.** All roles see printers with branch, color, duplex and status; admin creates and changes them; librarian and admin "Refill" with `sheets`; printers with low paper are marked. |
| LIB-UI-PRT-04 | **Print desk.** Librarian and admin. Jobs with filters; send a job for a member; "Release", "Cancel", "Fail" with `reason`; "Release by card" with `printer_id` and `card_no`; sell a pack ("Buy pack"); "Process" shows the count. |
| LIB-UI-PRT-05 | **Printing report.** Librarian and admin. LIB-PRT-44 as a table. |
