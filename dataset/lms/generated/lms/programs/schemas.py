"""Request and response schemas of module 26 (section 34)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from lms.core.money import ZERO, Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.programs.models import Entry, Participation, Program
from lms.programs.rules import MAX_REWARD
from lms.rooms.schemas import DateValue

Audience = Literal["all", "students", "academics"]
ProgramStatus = Literal["draft", "published", "closed", "cancelled"]
ParticipationStatus = Literal["active", "left", "completed"]
EntrySource = Literal["loan", "manual", "event", "bonus"]

Name = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=1000)]
Goal = Annotated[StrictInt, Field(ge=1, le=50)]
MaxParticipants = Annotated[StrictInt, Field(ge=1, le=1000)]
Note = Annotated[str, Field(max_length=200)]


def _check_waiver(value: Decimal) -> Decimal:
    if not ZERO <= value <= MAX_REWARD:
        raise ValueError("reward_waiver must be between 0.00 and 50.00")
    return value


# --- requests --------------------------------------------------------------------------------


class ProgramCreateIn(RequestModel):
    name: Name
    description: Description = ""
    branch_id: StrictInt | None = None
    audience: Audience = "all"
    starts_on: DateValue
    ends_on: DateValue
    goal_books: Goal
    max_participants: MaxParticipants | None = None
    reward_waiver: Money = ZERO

    @field_validator("reward_waiver")
    @classmethod
    def _waiver(cls, value: Decimal) -> Decimal:
        return _check_waiver(value)


class ProgramPatchIn(RequestModel):
    """Any subset of the fields of LIB-RDP-01."""

    name: Name = None  # type: ignore[assignment]
    description: Description = None  # type: ignore[assignment]
    branch_id: StrictInt | None = None
    audience: Audience = None  # type: ignore[assignment]
    starts_on: DateValue = None  # type: ignore[assignment]
    ends_on: DateValue = None  # type: ignore[assignment]
    goal_books: Goal = None  # type: ignore[assignment]
    max_participants: MaxParticipants | None = None
    reward_waiver: Money = None  # type: ignore[assignment]

    @field_validator("reward_waiver")
    @classmethod
    def _waiver(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else _check_waiver(value)

    @field_validator("name", "description", "audience", "starts_on", "ends_on", "goal_books", "reward_waiver", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("this field cannot be null")
        return value


class BooksIn(RequestModel):
    book_ids: list[StrictInt] = Field(max_length=30)


class CopyIn(RequestModel):
    starts_on: DateValue


class JoinIn(RequestModel):
    member_id: StrictInt | None = None
    public: StrictBool | None = None


class LeaveIn(RequestModel):
    member_id: StrictInt | None = None


class VisibilityIn(RequestModel):
    public: StrictBool


class EntryIn(RequestModel):
    book_id: StrictInt
    note: Note = ""


# --- responses -------------------------------------------------------------------------------


def _dt(value: datetime.datetime | None) -> str | None:
    return None if value is None else format_datetime(value)


class ParticipationOut(BaseModel):
    id: int
    program_id: int
    member_id: int
    status: str
    joined_at: str
    left_at: str | None
    leave_reason: str | None
    public: bool
    points: int
    books: int
    level: str
    completed_at: str | None
    reward_waived: str
    rank: int | None


def participation_out(p: Participation, rank: int | None) -> ParticipationOut:
    return ParticipationOut(
        id=p.id,
        program_id=p.program_id,
        member_id=p.member_id,
        status=p.status,
        joined_at=format_datetime(p.joined_at),
        left_at=_dt(p.left_at),
        leave_reason=p.leave_reason,
        public=p.public,
        points=p.points,
        books=p.books,
        level=p.level,
        completed_at=_dt(p.completed_at),
        reward_waived=format_amount(p.reward_waived),
        rank=rank,
    )


class ProgramOut(BaseModel):
    id: int
    name: str
    description: str
    branch_id: int | None
    audience: str
    starts_on: datetime.date
    ends_on: datetime.date
    goal_books: int
    max_participants: int | None
    reward_waiver: str
    status: str
    published_at: str | None
    closed_at: str | None
    participants: int
    completed: int
    free_places: int | None
    # Only for members (LIB-RDP-07): left out of the response when not set.
    my_participation: ParticipationOut | None = None


def program_out(program: Program, *, participants: int, completed: int) -> ProgramOut:
    limit = program.max_participants
    return ProgramOut(
        id=program.id,
        name=program.name,
        description=program.description,
        branch_id=program.branch_id,
        audience=program.audience,
        starts_on=program.starts_on,
        ends_on=program.ends_on,
        goal_books=program.goal_books,
        max_participants=limit,
        reward_waiver=format_amount(program.reward_waiver),
        status=program.status,
        published_at=_dt(program.published_at),
        closed_at=_dt(program.closed_at),
        participants=participants,
        completed=completed,
        free_places=None if limit is None else max(limit - participants, 0),
    )


class BookOut(BaseModel):
    book_id: int
    title: str


class BooksOut(BaseModel):
    items: list[BookOut]


class MemberProgramOut(BaseModel):
    participation_id: int
    program_id: int
    program_name: str
    status: str
    points: int
    books: int
    level: str
    goal_books: int
    rank: int | None


class ParticipantOut(BaseModel):
    participation_id: int
    member_id: int
    full_name: str
    status: str
    points: int
    books: int
    level: str
    rank: int | None
    public: bool
    reward_waived: str


class LeaderboardOut(BaseModel):
    rank: int
    name: str
    points: int
    books: int
    level: str
    member_id: int | None = None


class EntryOut(BaseModel):
    id: int
    participation_id: int
    source: str
    book_id: int | None
    book_title: str | None
    loan_id: int | None
    event_id: int | None
    points: int
    on: datetime.date
    note: str
    created_at: str


def entry_out(entry: Entry, book_title: str | None) -> EntryOut:
    return EntryOut(
        id=entry.id,
        participation_id=entry.participation_id,
        source=entry.source,
        book_id=entry.book_id,
        book_title=book_title,
        loan_id=entry.loan_id,
        event_id=entry.event_id,
        points=entry.points,
        on=entry.on,
        note=entry.note,
        created_at=format_datetime(entry.created_at),
    )


class CertificateOut(BaseModel):
    certificate_no: str
    member_name: str
    program_name: str
    completed_at: str
    level: str
    books: int
    points: int


class ProcessOut(BaseModel):
    closed: int
    participants_completed: int
    participants_not_completed: int
    reminders: int


class TopBookOut(BaseModel):
    book_id: int
    title: str
    count: int


class ProgramReportOut(BaseModel):
    program_id: int
    name: str
    status: str
    participants: int
    completed: int
    completion_rate: str
    books_counted: int
    points: int
    rewards_waived: str
    top_books: list[TopBookOut]


class ProgramSummaryOut(BaseModel):
    active: int
    completed_this_year: int
    points_this_year: int
