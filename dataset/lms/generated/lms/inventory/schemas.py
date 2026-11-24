"""Request and response schemas of module 24 (section 32)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt

from lms.core.limits import MAX_REPORT_YEAR, MIN_REPORT_YEAR
from lms.core.schemas import RequestModel

CountStatus = Literal["open", "closed", "applied", "cancelled"]
ScanResult = Literal[
    "unknown", "duplicate", "expected", "found_lost", "withdrawn", "wrong_branch", "unexpected_status", "out_of_scope"
]
Outcome = Literal["found", "missing", "moved"]

MIN_YEAR = MIN_REPORT_YEAR
MAX_YEAR = MAX_REPORT_YEAR


class CountIn(RequestModel):
    branch_id: StrictInt
    name: Annotated[str, Field(min_length=1, max_length=200)]
    shelf_prefix: Annotated[str, Field(min_length=1, max_length=20)] | None = None


class ScansIn(RequestModel):
    barcodes: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1, max_length=200)]


class FoundIn(RequestModel):
    branch_id: StrictInt


class SummaryOut(BaseModel):
    expected: int
    found: int
    missing: int
    moved: int
    accuracy: str


class ProblemsOut(BaseModel):
    unknown: int
    duplicate: int
    found_lost: int
    withdrawn: int
    wrong_branch: int
    unexpected_status: int
    out_of_scope: int


class ProgressOut(BaseModel):
    expected: int
    scanned_expected: int
    remaining: int
    problems: ProblemsOut


class CountOut(BaseModel):
    id: int
    branch_id: int
    name: str
    shelf_prefix: str | None
    status: str
    cancel_reason: str | None
    started_at: str
    closed_at: str | None
    applied_at: str | None
    expected: list[int]
    expected_count: int


class CountDetailOut(CountOut):
    progress: ProgressOut
    summary: SummaryOut | None


class ScanOut(BaseModel):
    id: int
    count_id: int
    barcode: str
    copy_id: int | None
    result: str
    scanned_at: str
    scanned_by: int


class AddedScanOut(BaseModel):
    id: int
    barcode: str
    copy_id: int | None
    result: str


class ScansAddedOut(BaseModel):
    scans: list[AddedScanOut]


class LineOut(BaseModel):
    copy_id: int
    outcome: str
    barcode: str
    book_title: str
    shelf_location: str | None


class ApplyOut(BaseModel):
    missing_marked: int
    found: int
    relocated: int


class ProcessOut(BaseModel):
    expired_counts: int
    marked_lost: int


class InventoryReportRowOut(BaseModel):
    branch_id: int
    counts_applied: int
    last_applied_on: str
    expected: int
    found: int
    missing: int
    accuracy: str
    missing_now: int
    found_again: int


class InventoryYearReportOut(BaseModel):
    items: list[InventoryReportRowOut]
