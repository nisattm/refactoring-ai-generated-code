"""Release of a free copy (LIB-RES-08).

Called when a copy becomes free: a returned copy (LIB-LOAN-12), a new copy (LIB-CAT-07), a
repaired copy (LIB-CAT-11). Only case (a) of LIB-RES-08 exists until the reservation module is
added: no reservation can be waiting, so the copy becomes ``available`` at its home branch, or
returns home by a ``return_home`` transfer (module 11) when it is elsewhere.
"""

from __future__ import annotations

import datetime
from collections.abc import Container

from sqlalchemy.orm import Session

from lms.branches.service import start_transfer
from lms.catalog.models import Copy
from lms.catalog.status import set_status


def release_copy(
    db: Session,
    copy: Copy,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor_user_id: int | None = None,
) -> None:
    if copy.current_branch_id == copy.home_branch_id:
        if copy.status != "available":
            set_status(copy, "available")
    else:
        start_transfer(db, now, actor_user_id, copy, copy.home_branch_id, "return_home", holidays)
