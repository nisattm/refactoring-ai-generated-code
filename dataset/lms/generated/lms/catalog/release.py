"""Release of a free copy (LIB-RES-08).

Called when a copy becomes free: a new copy (LIB-CAT-07), a repaired copy (LIB-CAT-11).
Only case (a) of LIB-RES-08 exists until the reservation and transfer modules are added: no
reservation can be waiting, and a copy is always at its home branch because only a relocation
(module 11) moves it away.
"""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from lms.catalog.models import Copy
from lms.catalog.status import set_status


def release_copy(db: Session, copy: Copy, now: datetime.datetime) -> None:
    if copy.status != "available":
        set_status(copy, "available")
