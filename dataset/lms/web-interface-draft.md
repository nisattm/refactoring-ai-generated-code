# Web interface: draft requirements

> **Not given to the model yet.** The web interface (frontend) is generated in its own step after all backend modules. It is not part of the measured code and is not refactored (ADR 002); it lets the instructor and the team use the system. Screens are collected here per module as the modules are written; general rules (login, navigation, error display, technology) are added before the interface step.

## Module 15: Study rooms

Every action calls the endpoint named in brackets and shows the result; an error response shows `error.message` and keeps the entered values. The interface shows only the actions the user's role may perform (6.6).

| ID | Requirement |
| --- | --- |
| LIB-UI-ROOM-01 | **Room list.** All roles. Lists rooms (LIB-ROOM-03) with filters branch, kind, minimum capacity and features; each row shows code, name, branch, kind, capacity, features, hours and active state. Selecting a room opens its availability. |
| LIB-UI-ROOM-02 | **Availability.** All roles. A date picker and the room's slots of that day (LIB-ROOM-08) as a grid: free slots selectable, booked slots marked, a closed day shown as "closed". Selecting one or more consecutive free slots opens the booking form with room, date and times filled in. |
| LIB-UI-ROOM-03 | **Find a free room.** All roles. Date, start and end time and optional filters; shows the matching rooms (LIB-ROOM-09); each result has a "Book" action that opens the booking form. |
| LIB-UI-ROOM-04 | **Booking form.** Member (for themselves); librarian and admin also choose the organizer member. Fields: room, date, start, end, participants (group rooms only; members searched by name or member number), purpose. "Book" sends LIB-ROOM-10 and on success shows the booking. Error codes of LIB-ROOM-12 to LIB-ROOM-15 are shown with their `details` (for example the latest allowed date or the quota used). |
| LIB-UI-ROOM-05 | **My room bookings.** Member. Lists their bookings (LIB-ROOM-18) with status; actions per booking as allowed: "Check in" (LIB-ROOM-27), "Check out" (LIB-ROOM-29), "Cancel" with a warning when the cancellation is late (LIB-ROOM-24), "Leave" for participants (LIB-ROOM-21), "Edit participants" (LIB-ROOM-20). Shows room bans in force and this week's hours (LIB-ROOM-40). |
| LIB-UI-ROOM-06 | **Desk view.** Librarian and admin. Today's bookings of a chosen branch ordered by start time, with check-in, check-out and cancel actions, and a "Process" action (LIB-ROOM-28) that shows the three counts. A "Send reminders" action calls LIB-ROOM-42 and shows the count. |
| LIB-UI-ROOM-07 | **Room management.** Admin. Create a room and edit name, features, hours, capacity and active state (LIB-ROOM-01, LIB-ROOM-04); `ROOM_HAS_BOOKINGS` shows the listed booking ids; deactivation asks for confirmation and states that future bookings will be cancelled (LIB-ROOM-06). |
| LIB-UI-ROOM-08 | **Bans.** Librarian and admin see a member's bans (LIB-ROOM-36) on the member page; admin can create a ban (LIB-ROOM-34) and lift one (LIB-ROOM-35). |
| LIB-UI-ROOM-09 | **Room usage report.** Librarian and admin. Date range and branch; shows LIB-ROOM-44 as a table. |

## Module 16: Equipment loans

Same conventions as module 15: every action calls the endpoint named in brackets, an error shows `error.message` and keeps the entered values, and only the actions of the user's role are shown (6.6).

| ID | Requirement |
| --- | --- |
| LIB-UI-EQ-01 | **Equipment catalog.** All roles. Lists types (LIB-EQ-06) with items total and available; selecting a type and a branch shows the availability grid of a chosen date (LIB-EQ-33), a closed day shown as "closed". |
| LIB-UI-EQ-02 | **Reserve equipment.** Member for themselves; librarian and admin also choose the member. Type, branch and start (picked from the grid); shows the resulting `ends_at` before sending LIB-EQ-26. Errors of LIB-EQ-28 are shown with their `details`; for `NO_EQUIPMENT_AVAILABLE` the next free time is offered as a button that fills in the start. |
| LIB-UI-EQ-03 | **My equipment.** Member. Open and past loans (LIB-EQ-17) with due time, overdue flag and accrued fee; "Extend" (LIB-EQ-19) on open loans; booked reservations (LIB-EQ-34) with "Cancel" (LIB-EQ-30); own trainings with validity (LIB-EQ-11). |
| LIB-UI-EQ-04 | **Equipment desk.** Librarian and admin. Find a member; lend by asset tag (LIB-EQ-12) or collect one of the member's reservations (LIB-EQ-29); return with condition and damage fee (LIB-EQ-20, LIB-EQ-21); report lost (LIB-EQ-24); today's reservations of a chosen branch; "Process" (LIB-EQ-31, LIB-EQ-32) shows both counts. `DESK_CLOSED` shows the opening time. |
| LIB-UI-EQ-05 | **Types and items.** Admin creates and changes types and items (LIB-EQ-03, LIB-EQ-04, LIB-EQ-07, LIB-EQ-08) and retires items (LIB-EQ-10); deactivating a type asks for confirmation and states that booked reservations will be cancelled (LIB-EQ-05). Librarian sees the item list with filters (LIB-EQ-09) and marks repairs done. |
| LIB-UI-EQ-06 | **Trainings.** Librarian and admin record a training on the member page (LIB-EQ-11) and see the member's trainings with validity. |
| LIB-UI-EQ-07 | **Equipment usage report.** Librarian and admin. Date range and branch; shows LIB-EQ-40 as a table. |

## Module 17: Digital resources

Same conventions as modules 15 and 16.

| ID | Requirement |
| --- | --- |
| LIB-UI-DIG-01 | **Digital library.** All roles. Resources with kind, availability and waiting holds; e-books also on the book page (LIB-DIG-09). |
| LIB-UI-DIG-02 | **Borrow, hold, open.** Member for themselves, staff choose the member. "Borrow" when a copy is free, otherwise "Place hold" with the queue length; "Open session" for databases with the remaining minutes; errors with `details`. |
| LIB-UI-DIG-03 | **My digital library.** Member. Active and past loans with due time, "Return" and "Renew" (with `renewable_from`); holds with position or "ready until", "Borrow" and "Cancel"; open sessions with "Close". |
| LIB-UI-DIG-04 | **Licenses.** Admin adds and cancels licenses (with an optional purchase order); librarian sees them. |
| LIB-UI-DIG-05 | **Resources.** Librarian and admin create and change resources; deactivation asks for confirmation (holds will be cancelled). |
| LIB-UI-DIG-06 | **Digital desk.** Librarian and admin. Hold queue of a resource; "Process" (LIB-DIG-35) with its four counts. |
| LIB-UI-DIG-07 | **Digital usage report.** Librarian and admin. Date range and kind; LIB-DIG-39 as a table. |

## Module 18: Interlibrary loans

Same conventions as modules 15–17.

| ID | Requirement |
| --- | --- |
| LIB-UI-ILL-01 | **Request a book from another library.** Member for themselves, staff choose the member. Title, author, ISBN; `AVAILABLE_LOCALLY` links to the book page. |
| LIB-UI-ILL-02 | **My interlibrary requests.** Member. Requests with status, pickup branch and `collect_until`, due date and accrued late fee; "Cancel" and "Ask for more time". |
| LIB-UI-ILL-03 | **Interlibrary desk (incoming).** Librarian and admin. Requests by status; send to a partner (partners already tried are not offered), record rejection, receive (with the computed member due date shown before saving), collect, return, close, report lost, answer renewal requests; "Process" with its counts. |
| LIB-UI-ILL-04 | **Interlibrary desk (outgoing).** Librarian and admin. New outgoing request, ship with a copy chosen from the available copies, decline, returned, lost; overdue outgoing requests highlighted. |
| LIB-UI-ILL-05 | **Partners.** Admin creates and changes partners; librarian sees them with their open counts. |
| LIB-UI-ILL-06 | **Interlibrary activity report.** Librarian and admin. Date range; LIB-ILL-38 as a table. |

## Module 19: Staff and shifts

Same conventions as modules 15–18.

| ID | Requirement |
| --- | --- |
| LIB-UI-STF-01 | **Staff.** Admin. List, create and change staff profiles; deactivation asks for confirmation (planned shifts will be cancelled). |
| LIB-UI-STF-02 | **Branch hours and closures.** Admin sets hours and `min_staff`; adds and removes closures and sees the counts of cancelled shifts and bookings. All users see a branch's open days for a month. |
| LIB-UI-STF-03 | **Shift plan.** Admin. Week view per branch with shifts per day; plan, change, cancel; "Copy last week" with the skipped shifts and their reasons; coverage per half hour with missing slots highlighted. |
| LIB-UI-STF-04 | **My shifts.** Librarian and admin. Own shifts; "Check in" and "Check out" buttons in the allowed window; worked and late minutes. |
| LIB-UI-STF-05 | **Leave.** Request leave (with the working days computed before sending), see own requests and balance; admin sees pending requests and approves or rejects them, with the shifts that will be cancelled shown before approving. |
| LIB-UI-STF-06 | **Staff reports.** Admin. Staff hours and branch coverage reports as tables. |

## Module 20: Events

Same conventions as modules 15–19.

| ID | Requirement |
| --- | --- |
| LIB-UI-EVT-01 | **Event calendar.** All roles. Month and list views of published events with free places and waiting list; filters by branch and kind; staff also see drafts. |
| LIB-UI-EVT-02 | **Event page.** Details, "Register" (or "Join waiting list" with the position), "Cancel" with a warning when the cancellation is late; errors with `details`. |
| LIB-UI-EVT-03 | **My events.** Member. Upcoming and past registrations with status, position and fee; bans with end dates. |
| LIB-UI-EVT-04 | **Event management.** Librarian and admin. Create and change events and series (with the skipped dates shown), choose a free group room and the responsible staff (with `staff_covered`), publish, cancel; registrations list. |
| LIB-UI-EVT-05 | **Event desk.** Librarian and admin. Today's events with check-in for each registered member; "Process" with its counts. |
| LIB-UI-EVT-06 | **Attendance report.** Librarian and admin. Date range, branch, kind; LIB-EVT-46 as a table. |
