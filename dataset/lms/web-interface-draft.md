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

