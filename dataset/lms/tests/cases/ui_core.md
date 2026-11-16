# Test cases: web interface, general rules and screens of modules 1–14 (step 24)

Generated from one case list; 45 cases for 40 requirements (feedback 25, held-out 20, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-UIGEN-02-a | LIB-UI-GEN-02 | Normal | `GET /ui/`; `GET /health` | `200` HTML page; the API is unchanged (`200` JSON) | held-out |
| T-UIGEN-03-a | LIB-UI-GEN-03 | Normal | The librarian opens `#/mem-01` and reloads the page | "Member list" before and after the reload | feedback |
| T-UIGEN-04-a | LIB-UI-GEN-04 | Normal | `#/mem-01` opened without a session; the librarian logs in there | "Log in"; after logging in "Member list" | feedback |
| T-UIGEN-04-b | LIB-UI-GEN-04 | Error | Log in with a wrong password | Alert with `INVALID_CREDENTIALS`; still "Log in" with the e-mail kept | held-out |
| T-UIGEN-05-a | LIB-UI-GEN-05 | Normal | The librarian logs out; opens `#/mem-01` again | Header with name and role; after "Log out" the login screen, also for `#/mem-01` | feedback |
| T-UIGEN-06-a | LIB-UI-GEN-06 | Normal | Menu of a librarian and of a member | Librarian: links "Member list" and "Loan desk", no "Users"; member: "My loans", no "Member list" | held-out |
| T-UIGEN-08-a | LIB-UI-GEN-08 | Normal | A member opens `/ui/` | "Home" with the member number | held-out |
| T-UIGEN-09-a | LIB-UI-GEN-09 | Error | A member opens `#/usr-01` | "Not allowed" with "You do not have access to this screen." | feedback |
| T-UIGEN-12-a | LIB-UI-GEN-12 | Error | The librarian registers a member with an e-mail that is already used | Alert with `CONFLICT`; the entered name stays | held-out |
| T-UIGEN-13-a | LIB-UI-GEN-13 | Normal | The librarian opens the member list without members | A table and "No records" | feedback |
| T-UIACCT-01-a | LIB-UI-ACCT-01 | Normal | A member opens `/ui/#/acct-01` | Heading "My account"; no error shown, no JavaScript error | feedback |
| T-UIAUD-01-a | LIB-UI-AUD-01 | Normal | A admin opens `/ui/#/aud-01` | Heading "Audit log"; no error shown, no JavaScript error | feedback |
| T-UIAUD-02-a | LIB-UI-AUD-02 | Normal | A admin opens `/ui/#/aud-02` | Heading "Import and export"; no error shown, no JavaScript error | held-out |
| T-UIBR-01-a | LIB-UI-BR-01 | Normal | A member opens `/ui/#/br-01` | Heading "Branches"; no error shown, no JavaScript error | feedback |
| T-UIBR-02-a | LIB-UI-BR-02 | Normal | A librarian opens `/ui/#/br-02` | Heading "Transfers"; no error shown, no JavaScript error | held-out |
| T-UICAL-01-a | LIB-UI-CAL-01 | Normal | A member opens `/ui/#/cal-01` | Heading "Calendar"; no error shown, no JavaScript error | feedback |
| T-UICAT-01-a | LIB-UI-CAT-01 | Normal | A member opens `/ui/#/cat-01` | Heading "Books"; no error shown, no JavaScript error | feedback |
| T-UICAT-02-a | LIB-UI-CAT-02 | Normal | A member opens `/ui/#/cat-02` | Heading "Book page"; no error shown, no JavaScript error | held-out |
| T-UICAT-03-a | LIB-UI-CAT-03 | Normal | A librarian opens `/ui/#/cat-03` | Heading "Book form"; no error shown, no JavaScript error | feedback |
| T-UICAT-04-a | LIB-UI-CAT-04 | Normal | A librarian opens `/ui/#/cat-04` | Heading "Authors and publishers"; no error shown, no JavaScript error | held-out |
| T-UIFEE-01-a | LIB-UI-FEE-01 | Normal | A member opens `/ui/#/fee-01` | Heading "My fees"; no error shown, no JavaScript error | feedback |
| T-UIFEE-02-a | LIB-UI-FEE-02 | Normal | A librarian opens `/ui/#/fee-02` | Heading "Fees and payments"; no error shown, no JavaScript error | held-out |
| T-UILOAN-01-a | LIB-UI-LOAN-01 | Normal | A librarian opens `/ui/#/loan-01` | Heading "Loan desk"; no error shown, no JavaScript error | feedback |
| T-UILOAN-01-b | LIB-UI-LOAN-01 | Normal | The librarian lends a copy by member number and barcode on Mon 2026-11-02 | Due date 2026-11-16 shown; one open loan in the API | held-out |
| T-UILOAN-02-a | LIB-UI-LOAN-02 | Normal | A librarian opens `/ui/#/loan-02` | Heading "Loans"; no error shown, no JavaScript error | held-out |
| T-UILOAN-03-a | LIB-UI-LOAN-03 | Normal | A member opens `/ui/#/loan-03` | Heading "My loans"; no error shown, no JavaScript error | feedback |
| T-UIMEM-01-a | LIB-UI-MEM-01 | Normal | A librarian opens `/ui/#/mem-01` | Heading "Member list"; no error shown, no JavaScript error | feedback |
| T-UIMEM-02-a | LIB-UI-MEM-02 | Normal | A librarian opens `/ui/#/mem-02` | Heading "Register member"; no error shown, no JavaScript error | feedback |
| T-UIMEM-02-b | LIB-UI-MEM-02 | Normal | The librarian registers a student | Status message with the member number; the member exists in the API | held-out |
| T-UIMEM-03-a | LIB-UI-MEM-03 | Normal | A librarian opens `/ui/#/mem-03` | Heading "Member page"; no error shown, no JavaScript error | feedback |
| T-UIMEM-04-a | LIB-UI-MEM-04 | Normal | A member opens `/ui/#/mem-04` | Heading "My membership"; no error shown, no JavaScript error | held-out |
| T-UINOT-01-a | LIB-UI-NOT-01 | Normal | A member opens `/ui/#/not-01` | Heading "My notifications"; no error shown, no JavaScript error | feedback |
| T-UINOT-02-a | LIB-UI-NOT-02 | Normal | A librarian opens `/ui/#/not-02` | Heading "Notifications"; no error shown, no JavaScript error | feedback |
| T-UINOT-02-b | LIB-UI-NOT-02 | Normal | The librarian runs the reminders | Status message with the count | held-out |
| T-UIPUR-01-a | LIB-UI-PUR-01 | Normal | A librarian opens `/ui/#/pur-01` | Heading "Suppliers"; no error shown, no JavaScript error | feedback |
| T-UIPUR-02-a | LIB-UI-PUR-02 | Normal | A librarian opens `/ui/#/pur-02` | Heading "Purchase orders"; no error shown, no JavaScript error | held-out |
| T-UIREP-01-a | LIB-UI-REP-01 | Normal | A librarian opens `/ui/#/rep-01` | Heading "Most borrowed"; no error shown, no JavaScript error | feedback |
| T-UIREP-02-a | LIB-UI-REP-02 | Normal | A librarian opens `/ui/#/rep-02` | Heading "Overdue loans"; no error shown, no JavaScript error | held-out |
| T-UIREP-03-a | LIB-UI-REP-03 | Normal | A librarian opens `/ui/#/rep-03` | Heading "Monthly summary"; no error shown, no JavaScript error | feedback |
| T-UIREP-04-a | LIB-UI-REP-04 | Normal | A librarian opens `/ui/#/rep-04` | Heading "Copies by status"; no error shown, no JavaScript error | held-out |
| T-UIRES-01-a | LIB-UI-RES-01 | Normal | A member opens `/ui/#/res-01` | Heading "My reservations"; no error shown, no JavaScript error | feedback |
| T-UIRES-02-a | LIB-UI-RES-02 | Normal | A librarian opens `/ui/#/res-02` | Heading "Reservations"; no error shown, no JavaScript error | held-out |
| T-UISRCH-01-a | LIB-UI-SRCH-01 | Normal | A member opens `/ui/#/srch-01` | Heading "Search"; no error shown, no JavaScript error | feedback |
| T-UISRCH-01-b | LIB-UI-SRCH-01 | Normal | A member searches `kayıp` | The book "Kayıp Şehir" in the results | held-out |
| T-UIUSR-01-a | LIB-UI-USR-01 | Normal | A admin opens `/ui/#/usr-01` | Heading "Users"; no error shown, no JavaScript error | feedback |
