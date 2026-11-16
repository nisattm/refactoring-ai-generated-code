"""Request and response schemas of module 29 (section 37)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from lms.core.money import ZERO, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.printing.models import Printer, PrintJob, PrintPack
from lms.printing.rules import MAX_PAPER

PrinterStatus = Literal["active", "out_of_service", "retired"]
JobStatus = Literal["queued", "printed", "cancelled", "expired", "failed"]


# --- requests --------------------------------------------------------------------------------


class PrinterCreateIn(RequestModel):
    branch_id: StrictInt
    code: str
    name: Annotated[str, Field(min_length=1, max_length=200)]
    color: StrictBool
    duplex: StrictBool

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if len(value) != 6 or not value.startswith("PR-") or not value[3:].isascii() or not value[3:].isdigit():
            raise ValueError('code must be "PR-" followed by 3 digits')
        return value


class PrinterPatchIn(RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them (LIB-PRT-03)."""

    name: Annotated[str, Field(min_length=1, max_length=200)] = None  # type: ignore[assignment]
    color: StrictBool = None  # type: ignore[assignment]
    duplex: StrictBool = None  # type: ignore[assignment]
    status: PrinterStatus = None  # type: ignore[assignment]

    @field_validator("name", "color", "duplex", "status", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("this field cannot be null")
        return value


class RefillIn(RequestModel):
    sheets: Annotated[StrictInt, Field(ge=1, le=MAX_PAPER)]


class PrintJobIn(RequestModel):
    member_id: StrictInt | None = None
    printer_id: StrictInt
    title: Annotated[str, Field(min_length=1, max_length=100)]
    pages: Annotated[StrictInt, Field(ge=1, le=500)]
    copies: Annotated[StrictInt, Field(ge=1, le=20)] = 1
    color: StrictBool = False
    duplex: StrictBool = False


class FailIn(RequestModel):
    reason: Annotated[str, Field(min_length=5, max_length=200)]


class ReleaseByCardIn(RequestModel):
    printer_id: StrictInt
    card_no: Annotated[str, Field(min_length=1)]


# --- responses -------------------------------------------------------------------------------


class PrinterOut(BaseModel):
    id: int
    branch_id: int
    code: str
    name: str
    color: bool
    duplex: bool
    paper_left: int
    status: str
    low_paper: bool


def printer_out(printer: Printer) -> PrinterOut:
    return PrinterOut(
        id=printer.id,
        branch_id=printer.branch_id,
        code=printer.code,
        name=printer.name,
        color=printer.color,
        duplex=printer.duplex,
        paper_left=printer.paper_left,
        status=printer.status,
        low_paper=printer.low_paper,
    )


class JobPrinterOut(BaseModel):
    id: int
    code: str
    branch_id: int


class PrintJobOut(BaseModel):
    id: int
    member_id: int
    printer_id: int
    printer: JobPrinterOut
    title: str
    pages: int
    copies: int
    color: bool
    duplex: bool
    status: str
    submitted_at: str
    released_at: str | None
    sheets: int
    free_pages: int
    pack_pages: int
    charged_pages: int
    fee_id: int | None
    amount: str
    failed_reason: str | None


def job_out(job: PrintJob, printer: Printer, amount: Decimal = ZERO) -> PrintJobOut:
    return PrintJobOut(
        id=job.id,
        member_id=job.member_id,
        printer_id=job.printer_id,
        printer=JobPrinterOut(id=printer.id, code=printer.code, branch_id=printer.branch_id),
        title=job.title,
        pages=job.pages,
        copies=job.copies,
        color=job.color,
        duplex=job.duplex,
        status=job.status,
        submitted_at=format_datetime(job.submitted_at),
        released_at=format_datetime(job.released_at) if job.released_at is not None else None,
        sheets=job.sheets,
        free_pages=job.free_pages,
        pack_pages=job.pack_pages,
        charged_pages=job.charged_pages,
        fee_id=job.fee_id,
        amount=format_amount(amount),
        failed_reason=job.failed_reason,
    )


class RefusedOut(BaseModel):
    job_id: int
    code: str


class ReleaseByCardOut(BaseModel):
    released: list[int]
    refused: list[RefusedOut]


class PackOut(BaseModel):
    id: int
    member_id: int
    pages: int
    pages_left: int
    bought_on: str
    fee_id: int | None


def pack_out(pack: PrintPack) -> PackOut:
    return PackOut(
        id=pack.id,
        member_id=pack.member_id,
        pages=pack.pages,
        pages_left=pack.pages_left,
        bought_on=pack.bought_on.isoformat(),
        fee_id=pack.fee_id,
    )


class QuotaOut(BaseModel):
    month: str
    membership_type: str
    free_pages: int
    free_pages_used: int
    free_pages_left: int
    pack_pages_left: int
    pages_printed: int
    amount_charged: str


class ProcessOut(BaseModel):
    jobs_expired: int


class PrintingSummaryOut(BaseModel):
    free_pages_left: int
    pack_pages_left: int
    queued_jobs: int


class PrintingReportOut(BaseModel):
    branch_id: int
    jobs_printed: int
    pages: int
    color_pages: int
    sheets: int
    free_pages: int
    pack_pages: int
    charged_pages: int
    revenue: str
    packs_sold: int
    jobs_failed: int
    refunds_pending: str
