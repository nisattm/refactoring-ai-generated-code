"""Business logic of module 10: reports (LIB-REP-01 to LIB-REP-05)."""

from __future__ import annotations

import calendar
import csv
import datetime
import io
from collections.abc import Container, Iterable, Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.models import AuditEntry
from lms.catalog.models import Book, Copy
from lms.catalog.status import ALLOWED_TRANSITIONS
from lms.core.calendar import working_days_between
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount
from lms.core.pagination import PageParams
from lms.fines.models import Fee, Payment, PaymentAllocation
from lms.fines.service import late_fee_amount
from lms.loans.models import Loan
from lms.members.models import Member
from lms.reports.schemas import (
    InventoryItemOut,
    MonthlySummaryOut,
    MostBorrowedItemOut,
    OverdueItemOut,
)
from lms.reservations.models import Reservation

# Order of section 8.2.
STATUS_ORDER = ("available", "on_loan", "on_hold", "in_transfer", "damaged", "lost", "withdrawn")
assert set(STATUS_ORDER) == set(ALLOWED_TRANSITIONS)


def _bounds(first: datetime.date, last: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Local date-times ``[start, end)`` covering the inclusive dates ``first`` to ``last``."""
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    return start, end


# --- LIB-REP-01 -----------------------------------------------------------------


def most_borrowed(
    db: Session, first: datetime.date, last: datetime.date, branch_id: int | None, limit: int
) -> list[MostBorrowedItemOut]:
    loan_count = sa.func.count(Loan.id)
    stmt = (
        sa.select(Book.id, Book.title, Book.isbn, loan_count.label("loan_count"))
        .join(Copy, Copy.book_id == Book.id)
        .join(Loan, Loan.copy_id == Copy.id)
        .where(Loan.loan_date >= first, Loan.loan_date <= last)
        .group_by(Book.id)
        .order_by(loan_count.desc(), Book.title_key, Book.id)
        .limit(limit)
    )
    if branch_id is not None:
        stmt = stmt.where(Loan.branch_id == branch_id)
    return [
        MostBorrowedItemOut(rank=rank, book_id=book_id, title=title, isbn=isbn, loan_count=count)
        for rank, (book_id, title, isbn, count) in enumerate(db.execute(stmt), start=1)
    ]


# --- LIB-REP-02 -----------------------------------------------------------------


def _overdue_where(today: datetime.date, branch_id: int | None) -> list[sa.ColumnElement[bool]]:
    conditions = [Loan.status == "open", Loan.due_date < today]
    if branch_id is not None:
        conditions.append(Loan.branch_id == branch_id)
    return conditions


def overdue_total(
    db: Session, today: datetime.date, holidays: Container[datetime.date], branch_id: int | None
) -> tuple[int, Decimal]:
    """Number of matching loans and the sum of their accrued late fees (all pages)."""
    groups = db.execute(
        sa.select(Loan.due_date, Loan.daily_fee, sa.func.count(Loan.id))
        .where(*_overdue_where(today, branch_id))
        .group_by(Loan.due_date, Loan.daily_fee)
    )
    count = 0
    total = ZERO
    for due_date, daily_fee, n in groups:
        count += n
        total += n * late_fee_amount(working_days_between(due_date, today, holidays), daily_fee)
    return count, total


def overdue_items(
    db: Session,
    today: datetime.date,
    holidays: Container[datetime.date],
    branch_id: int | None,
    page: PageParams | None,
) -> list[OverdueItemOut]:
    """Overdue loans ordered by due date, then loan id; all of them when ``page`` is ``None``."""
    stmt = (
        sa.select(Loan, Member, Book, Copy.barcode)
        .join(Member, Member.id == Loan.member_id)
        .join(Copy, Copy.id == Loan.copy_id)
        .join(Book, Book.id == Copy.book_id)
        .where(*_overdue_where(today, branch_id))
        .order_by(Loan.due_date, Loan.id)
    )
    if page is not None:
        stmt = stmt.limit(page.page_size).offset(page.offset)
    late_days_cache: dict[datetime.date, int] = {}
    items = []
    for loan, member, book, barcode in db.execute(stmt):
        if loan.due_date not in late_days_cache:
            late_days_cache[loan.due_date] = working_days_between(loan.due_date, today, holidays)
        late_days = late_days_cache[loan.due_date]
        items.append(
            OverdueItemOut(
                loan_id=loan.id,
                member_id=member.id,
                member_no=member.member_no,
                member_name=member.full_name,
                book_id=book.id,
                title=book.title,
                copy_barcode=barcode,
                due_date=loan.due_date.isoformat(),
                late_days=late_days,
                accrued_late_fee=format_amount(late_fee_amount(late_days, loan.daily_fee)),
            )
        )
    return items


# --- LIB-REP-03 -----------------------------------------------------------------


def month_range(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])


def _count(db: Session, stmt: sa.Select[Any]) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery())) or 0


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, ZERO)


def monthly_summary(db: Session, year: int, month: int, branch_id: int | None) -> MonthlySummaryOut:
    first, last = month_range(year, month)
    start, end = _bounds(first, last)

    def in_month(column: sa.ColumnElement[Any]) -> sa.ColumnElement[bool]:
        return sa.and_(column >= first, column <= last)

    def at_in_month(column: sa.ColumnElement[Any]) -> sa.ColumnElement[bool]:
        return sa.and_(column >= start, column < end)

    # Members
    members = sa.select(Member.id).where(in_month(Member.membership_start))
    if branch_id is not None:
        members = members.where(Member.home_branch_id == branch_id)

    # Loans
    created = sa.select(Loan.id).where(in_month(Loan.loan_date))
    returned = sa.select(Loan.id).where(Loan.status == "returned", in_month(Loan.returned_on))
    lost = (
        sa.select(Loan.id)
        .join(AuditEntry, sa.and_(AuditEntry.entity_type == "loan", AuditEntry.entity_id == Loan.id))
        .where(Loan.status == "lost", AuditEntry.event == "loan_lost", at_in_month(AuditEntry.at))
    )
    if branch_id is not None:
        created = created.where(Loan.branch_id == branch_id)
        returned = returned.where(Loan.return_branch_id == branch_id)
        lost = lost.where(Loan.branch_id == branch_id)

    # Reservations
    res_created = sa.select(Reservation.id).where(at_in_month(Reservation.created_at))
    res_fulfilled = sa.select(Reservation.id).where(
        Reservation.status == "fulfilled", at_in_month(Reservation.closed_at)
    )
    res_expired = sa.select(Reservation.id).where(Reservation.status == "expired", at_in_month(Reservation.closed_at))
    if branch_id is not None:
        res_created = res_created.where(Reservation.pickup_branch_id == branch_id)
        res_fulfilled = res_fulfilled.where(Reservation.pickup_branch_id == branch_id)
        res_expired = res_expired.where(Reservation.pickup_branch_id == branch_id)

    # Amounts. With a branch, the branch of the related loan counts and fees without a loan are excluded.
    fees = sa.select(Fee.amount).where(in_month(Fee.created_on))
    waived = sa.select(Fee.amount, Fee.paid_amount).where(Fee.status == "waived", at_in_month(Fee.waived_at))
    if branch_id is None:
        payments = sa.select(Payment.amount).where(at_in_month(Payment.paid_at))
    else:
        fees = fees.join(Loan, Loan.id == Fee.loan_id).where(Loan.branch_id == branch_id)
        waived = waived.join(Loan, Loan.id == Fee.loan_id).where(Loan.branch_id == branch_id)
        payments = (
            sa.select(PaymentAllocation.amount)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .join(Fee, Fee.id == PaymentAllocation.fee_id)
            .join(Loan, Loan.id == Fee.loan_id)
            .where(Loan.branch_id == branch_id, at_in_month(Payment.paid_at))
        )

    return MonthlySummaryOut(
        year=year,
        month=month,
        branch_id=branch_id,
        new_members=_count(db, members),
        loans_created=_count(db, created),
        loans_returned=_count(db, returned),
        loans_lost=_count(db, lost),
        reservations_created=_count(db, res_created),
        reservations_fulfilled=_count(db, res_fulfilled),
        reservations_expired=_count(db, res_expired),
        fees_created=format_amount(_sum(db.scalars(fees))),
        payments_received=format_amount(_sum(db.scalars(payments))),
        fees_waived=format_amount(_sum(amount - paid for amount, paid in db.execute(waived))),
    )


# --- LIB-REP-04 -----------------------------------------------------------------


def inventory(db: Session, branch_id: int | None) -> list[InventoryItemOut]:
    stmt = sa.select(Copy.current_branch_id, Copy.status, sa.func.count(Copy.id)).group_by(
        Copy.current_branch_id, Copy.status
    )
    if branch_id is not None:
        stmt = stmt.where(Copy.current_branch_id == branch_id)
    rows = [(b, s, n) for b, s, n in db.execute(stmt) if n > 0]
    rows.sort(key=lambda r: (r[0] is None, r[0] or 0, STATUS_ORDER.index(r[1])))
    return [InventoryItemOut(branch_id=b, status=s, copies=n) for b, s, n in rows]


# --- LIB-REP-05 -----------------------------------------------------------------


def to_csv(columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> str:
    """LIB-IO-13, LIB-IO-14: header row, ``\\r\\n`` line ends, RFC 4180 quoting, null as an empty field."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_value(row[c]) for c in columns])
    return out.getvalue()


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value
