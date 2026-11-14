"""Donation figures of the member summary (LIB-DON-38)."""

from __future__ import annotations

from pydantic import BaseModel


class DonationSummaryOut(BaseModel):
    open: int
    copies_received: int
    value_this_year: str
    level: str
