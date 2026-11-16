# Test cases: web interface, screens of modules 22–28 (step 26)

Generated from one case list; 40 cases for 39 requirements (feedback 22, held-out 18, static 0). Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-UIACC-01-a | LIB-UI-ACC-01 | Normal | A librarian opens `/ui/#/acc-01` | Heading "Cards"; no error shown, no JavaScript error | feedback |
| T-UIACC-02-a | LIB-UI-ACC-02 | Normal | A librarian opens `/ui/#/acc-02` | Heading "Gate"; no error shown, no JavaScript error | feedback |
| T-UIACC-02-b | LIB-UI-ACC-02 | Normal | The librarian scans a member's card at branch A (in), then again | Result `entered` with the member's name, occupancy 1; then `ALREADY_INSIDE` | held-out |
| T-UIACC-03-a | LIB-UI-ACC-03 | Normal | A member opens `/ui/#/acc-03` | Heading "Occupancy"; no error shown, no JavaScript error | feedback |
| T-UIACC-04-a | LIB-UI-ACC-04 | Normal | A librarian opens `/ui/#/acc-04` | Heading "Day passes"; no error shown, no JavaScript error | held-out |
| T-UIACC-05-a | LIB-UI-ACC-05 | Normal | A librarian opens `/ui/#/acc-05` | Heading "Bans and alerts"; no error shown, no JavaScript error | feedback |
| T-UIACC-06-a | LIB-UI-ACC-06 | Normal | A librarian opens `/ui/#/acc-06` | Heading "Visits report"; no error shown, no JavaScript error | held-out |
| T-UIDON-01-a | LIB-UI-DON-01 | Normal | A librarian opens `/ui/#/don-01` | Heading "Donors"; no error shown, no JavaScript error | feedback |
| T-UIDON-02-a | LIB-UI-DON-02 | Normal | A member opens `/ui/#/don-02` | Heading "Offer form"; no error shown, no JavaScript error | held-out |
| T-UIDON-03-a | LIB-UI-DON-03 | Normal | A librarian opens `/ui/#/don-03` | Heading "Review"; no error shown, no JavaScript error | feedback |
| T-UIDON-04-a | LIB-UI-DON-04 | Normal | A librarian opens `/ui/#/don-04` | Heading "Receiving desk"; no error shown, no JavaScript error | held-out |
| T-UIDON-05-a | LIB-UI-DON-05 | Normal | A member opens `/ui/#/don-05` | Heading "Receipt and my donations"; no error shown, no JavaScript error | feedback |
| T-UIDON-06-a | LIB-UI-DON-06 | Normal | A member opens `/ui/#/don-06` | Heading "Donor wall and reports"; no error shown, no JavaScript error | held-out |
| T-UIINV-01-a | LIB-UI-INV-01 | Normal | A librarian opens `/ui/#/inv-01` | Heading "Counts"; no error shown, no JavaScript error | feedback |
| T-UIINV-02-a | LIB-UI-INV-02 | Normal | A librarian opens `/ui/#/inv-02` | Heading "Scanning"; no error shown, no JavaScript error | held-out |
| T-UIINV-03-a | LIB-UI-INV-03 | Normal | A librarian opens `/ui/#/inv-03` | Heading "Closing"; no error shown, no JavaScript error | feedback |
| T-UIINV-04-a | LIB-UI-INV-04 | Normal | A librarian opens `/ui/#/inv-04` | Heading "Problems"; no error shown, no JavaScript error | held-out |
| T-UIINV-05-a | LIB-UI-INV-05 | Normal | A librarian opens `/ui/#/inv-05` | Heading "Found copies"; no error shown, no JavaScript error | feedback |
| T-UIINV-06-a | LIB-UI-INV-06 | Normal | A librarian opens `/ui/#/inv-06` | Heading "Inventory report"; no error shown, no JavaScript error | held-out |
| T-UIMSG-01-a | LIB-UI-MSG-01 | Normal | A librarian opens `/ui/#/msg-01` | Heading "Announcements"; no error shown, no JavaScript error | feedback |
| T-UIMSG-03-a | LIB-UI-MSG-03 | Normal | A librarian opens `/ui/#/msg-03` | Heading "Inbox"; no error shown, no JavaScript error | feedback |
| T-UIMSG-04-a | LIB-UI-MSG-04 | Normal | A member opens `/ui/#/msg-04` | Heading "My messages"; no error shown, no JavaScript error | held-out |
| T-UIMSG-05-a | LIB-UI-MSG-05 | Normal | A librarian opens `/ui/#/msg-05` | Heading "Messaging report"; no error shown, no JavaScript error | feedback |
| T-UIPRE-01-a | LIB-UI-PRE-01 | Normal | A admin opens `/ui/#/pre-01` | Heading "Budgets"; no error shown, no JavaScript error | feedback |
| T-UIPRE-02-a | LIB-UI-PRE-02 | Normal | A librarian opens `/ui/#/pre-02` | Heading "Inspection"; no error shown, no JavaScript error | held-out |
| T-UIPRE-03-a | LIB-UI-PRE-03 | Normal | A librarian opens `/ui/#/pre-03` | Heading "Jobs"; no error shown, no JavaScript error | feedback |
| T-UIPRE-04-a | LIB-UI-PRE-04 | Normal | A librarian opens `/ui/#/pre-04` | Heading "Shipments"; no error shown, no JavaScript error | held-out |
| T-UIPRE-05-a | LIB-UI-PRE-05 | Normal | A librarian opens `/ui/#/pre-05` | Heading "Preservation reports"; no error shown, no JavaScript error | feedback |
| T-UIRDP-01-a | LIB-UI-RDP-01 | Normal | A librarian opens `/ui/#/rdp-01` | Heading "Programs"; no error shown, no JavaScript error | feedback |
| T-UIRDP-02-a | LIB-UI-RDP-02 | Normal | A member opens `/ui/#/rdp-02` | Heading "Join"; no error shown, no JavaScript error | held-out |
| T-UIRDP-03-a | LIB-UI-RDP-03 | Normal | A member opens `/ui/#/rdp-03` | Heading "My progress"; no error shown, no JavaScript error | feedback |
| T-UIRDP-04-a | LIB-UI-RDP-04 | Normal | A member opens `/ui/#/rdp-04` | Heading "Leaderboard"; no error shown, no JavaScript error | held-out |
| T-UIRDP-05-a | LIB-UI-RDP-05 | Normal | A librarian opens `/ui/#/rdp-05` | Heading "Manual entries"; no error shown, no JavaScript error | feedback |
| T-UIRDP-06-a | LIB-UI-RDP-06 | Normal | A librarian opens `/ui/#/rdp-06` | Heading "Programs report"; no error shown, no JavaScript error | held-out |
| T-UISUG-01-a | LIB-UI-SUG-01 | Normal | A member opens `/ui/#/sug-01` | Heading "Suggest a book"; no error shown, no JavaScript error | feedback |
| T-UISUG-02-a | LIB-UI-SUG-02 | Normal | A member opens `/ui/#/sug-02` | Heading "Suggestions board"; no error shown, no JavaScript error | held-out |
| T-UISUG-03-a | LIB-UI-SUG-03 | Normal | A member opens `/ui/#/sug-03` | Heading "My suggestions"; no error shown, no JavaScript error | feedback |
| T-UISUG-04-a | LIB-UI-SUG-04 | Normal | A librarian opens `/ui/#/sug-04` | Heading "Review queue"; no error shown, no JavaScript error | held-out |
| T-UISUG-05-a | LIB-UI-SUG-05 | Normal | A librarian opens `/ui/#/sug-05` | Heading "Ordering"; no error shown, no JavaScript error | feedback |
| T-UISUG-06-a | LIB-UI-SUG-06 | Normal | A librarian opens `/ui/#/sug-06` | Heading "Suggestions report"; no error shown, no JavaScript error | held-out |
