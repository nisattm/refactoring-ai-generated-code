# Characterization cases: module 20 (Events)

Characterization tests record the **current** behavior of the starting code (`v0-ai-baseline`, `3bd1412`) where the requirement tests leave branches uncovered (issue #115). They are not derived from a requirement; `Requirement` names the closest one. Behavior that contradicts a requirement is not recorded. Split rule: [`../README.md`](../README.md#feedback--held-out-split).

| ID | Requirement | Type | Input | Expected | Set |
| --- | --- | --- | --- | --- | --- |
| T-CHAR-EVT-01-a | LIB-EVT-08 | Characterization | GET `/events/999999` | `404 NOT_FOUND`, details `{resource: event, id: 999999}` | feedback |
| T-CHAR-EVT-02-a | LIB-EVT-08 | Characterization | No events; GET `/events?branch_id=A&series_id=1` | 200; `items` `[]`, `total` 0 | held-out |
| T-CHAR-EVT-03-a | LIB-EVT-08 | Characterization | No events; GET `/events?q=xyz` | 200; `items` `[]`, `total` 0 | feedback |
| T-CHAR-EVT-04-a | LIB-EVT-01 | Characterization | POST an event with `start_time` 10:00, `end_time` 09:00, `room_id` 999999, `staff_id` 999999 | `422`, fields `(end_time, end_time must be after start_time)`, `(room_id, room 999999 does not exist)`, `(staff_id, staff 999999 does not exist)` | held-out |
