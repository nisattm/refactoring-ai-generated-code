"""Response schemas of module 9 (LIB-SRCH-07)."""

from __future__ import annotations

from pydantic import BaseModel

from lms.catalog.schemas import BookOut


class SearchItemOut(BaseModel):
    book: BookOut
    score: int
    loan_count: int
