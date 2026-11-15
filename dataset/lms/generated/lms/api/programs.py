"""Reading program endpoints (section 34.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from lms.auth.deps import AnyUser, Principal, StaffOnly, require_roles
from lms.catalog.models import Book
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.members.models import Member
from lms.members.service import get_member_or_404
from lms.programs import entries, participation, process, programs
from lms.programs.models import Participation, Program
from lms.programs.schemas import (
    BookOut,
    BooksIn,
    BooksOut,
    CertificateOut,
    CopyIn,
    EntryIn,
    EntryOut,
    EntrySource,
    JoinIn,
    LeaderboardOut,
    LeaveIn,
    MemberProgramOut,
    ParticipantOut,
    ParticipationOut,
    ParticipationStatus,
    ProcessOut,
    ProgramCreateIn,
    ProgramOut,
    ProgramPatchIn,
    ProgramStatus,
    VisibilityIn,
    entry_out,
)

router = APIRouter(tags=["programs"])

ProgramId = Annotated[int, Path(ge=1)]
ParticipationId = Annotated[int, Path(ge=1)]
EntryId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]

MemberOnly = Annotated[Principal, Depends(require_roles("member"))]


def _now(request: Request) -> datetime.datetime:
    return local_now(request.app.state.settings.clock)


def _is_member(principal: Principal) -> bool:
    return principal.user.role == "member"


def _program_not_found(program_id: int) -> NotFound:
    return NotFound(f"Program {program_id} does not exist", details={"resource": "program", "id": program_id})


def _visible_program(db: SessionDep, program_id: int, principal: Principal) -> Program:
    """LIB-RDP-07: members do not see ``draft`` and ``cancelled`` programs."""
    program = programs.get_program_or_404(db, program_id)
    if _is_member(principal) and program.status not in ("published", "closed"):
        raise _program_not_found(program_id)
    return program


def _own_member(db: SessionDep, principal: Principal) -> Member:
    member = db.get(Member, principal.user.member_id) if principal.user.member_id is not None else None
    if member is None:
        raise Forbidden("The authenticated user has no member record")
    return member


def _require_own(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if _is_member(principal) and member_id != principal.user.member_id:
        raise Forbidden("Only your own data can be read")


def _participation_for(db: SessionDep, participation_id: int, principal: Principal) -> Participation:
    found = entries.get_participation_or_404(db, participation_id)
    _require_own(principal, found.member_id)
    return found


def _program_out(db: SessionDep, program: Program, principal: Principal) -> ProgramOut:
    result = programs.to_out(db, program)
    if _is_member(principal):
        mine = participation.find(db, program.id, principal.user.member_id) if principal.user.member_id else None
        result.my_participation = participation.out(db, mine) if mine is not None else None
    return result


# --- programs -----------------------------------------------------------------------------------


@router.post("/programs", response_model=ProgramOut, status_code=201, response_model_exclude_unset=True)
def create_program(body: ProgramCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> ProgramOut:
    program = programs.create_program(db, _now(request), staff.user, body.model_dump())
    return programs.to_out(db, program)


@router.get("/programs", response_model=Page[ProgramOut], response_model_exclude_unset=True)
def list_programs(
    request: Request,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    status: Annotated[ProgramStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    running: Annotated[bool | None, Query()] = None,
) -> Page[ProgramOut]:
    stmt = programs.list_stmt(
        status=status,
        branch_id=branch_id,
        running=running,
        today=_now(request).date(),
        member_view=_is_member(principal),
    )
    return paginate(db, stmt, page, lambda program: _program_out(db, program, principal))


@router.get("/programs/{program_id}", response_model=ProgramOut, response_model_exclude_unset=True)
def get_program(program_id: ProgramId, db: SessionDep, principal: AnyUser) -> ProgramOut:
    return _program_out(db, _visible_program(db, program_id, principal), principal)


@router.patch("/programs/{program_id}", response_model=ProgramOut, response_model_exclude_unset=True)
def update_program(
    program_id: ProgramId, body: ProgramPatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> ProgramOut:
    program = programs.get_program_or_404(db, program_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    programs.update_program(db, _now(request), staff.user, program, fields)
    return programs.to_out(db, program)


@router.post("/programs/process", response_model=ProcessOut)
def process_programs(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    return process.process(db, _now(request), staff.user)


@router.post("/programs/{program_id}/publish", response_model=ProgramOut, response_model_exclude_unset=True)
def publish_program(program_id: ProgramId, request: Request, db: SessionDep, staff: StaffOnly) -> ProgramOut:
    program = programs.get_program_or_404(db, program_id)
    programs.publish(db, _now(request), staff.user, program)
    return programs.to_out(db, program)


@router.post("/programs/{program_id}/cancel", response_model=ProgramOut, response_model_exclude_unset=True)
def cancel_program(program_id: ProgramId, request: Request, db: SessionDep, staff: StaffOnly) -> ProgramOut:
    program = programs.get_program_or_404(db, program_id)
    programs.cancel(db, _now(request), staff.user, program)
    return programs.to_out(db, program)


@router.post("/programs/{program_id}/copy", response_model=ProgramOut, status_code=201, response_model_exclude_unset=True)
def copy_program(
    program_id: ProgramId, body: CopyIn, request: Request, db: SessionDep, staff: StaffOnly
) -> ProgramOut:
    source = programs.get_program_or_404(db, program_id)
    copy = programs.copy_program(db, _now(request), staff.user, source, body.starts_on)
    return programs.to_out(db, copy)


# --- featured books -----------------------------------------------------------------------------


def _books_out(rows: list[tuple[int, str]]) -> BooksOut:
    return BooksOut(items=[BookOut(book_id=book_id, title=title) for book_id, title in rows])


@router.put("/programs/{program_id}/books", response_model=BooksOut)
def set_books(program_id: ProgramId, body: BooksIn, request: Request, db: SessionDep, staff: StaffOnly) -> BooksOut:
    program = programs.get_program_or_404(db, program_id)
    return _books_out(programs.set_books(db, _now(request), staff.user, program, body.book_ids))


@router.get("/programs/{program_id}/books", response_model=BooksOut)
def get_books(program_id: ProgramId, db: SessionDep, principal: AnyUser) -> BooksOut:
    program = _visible_program(db, program_id, principal)
    return _books_out(programs.featured_books(db, program.id))


# --- joining and leaving ------------------------------------------------------------------------


def _target_member(db: SessionDep, principal: Principal, member_id: int | None) -> Member:
    """LIB-RDP-10: members act for themselves, staff name the member."""
    if _is_member(principal):
        if member_id is not None:
            raise ValidationFailed.single("member_id", "members act for themselves and must not send member_id")
        return _own_member(db, principal)
    if member_id is None:
        raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    return member


@router.post("/programs/{program_id}/join", response_model=ParticipationOut, status_code=201)
def join_program(
    program_id: ProgramId, request: Request, db: SessionDep, principal: AnyUser, body: JoinIn | None = None
) -> ParticipationOut:
    body = body or JoinIn()
    program = programs.get_program_or_404(db, program_id)
    member = _target_member(db, principal, body.member_id)
    settings = request.app.state.settings
    joined = participation.join(db, _now(request), settings.holidays, principal.user, program, member, body.public)
    return participation.out(db, joined)


@router.post("/programs/{program_id}/leave", response_model=ParticipationOut)
def leave_program(
    program_id: ProgramId, request: Request, db: SessionDep, principal: AnyUser, body: LeaveIn | None = None
) -> ParticipationOut:
    body = body or LeaveIn()
    program = programs.get_program_or_404(db, program_id)
    member = _target_member(db, principal, body.member_id)
    left = participation.leave(db, _now(request), principal.user, program, member)
    return participation.out(db, left)


@router.patch("/participations/{participation_id}", response_model=ParticipationOut)
def set_visibility(
    participation_id: ParticipationId, body: VisibilityIn, db: SessionDep, principal: MemberOnly
) -> ParticipationOut:
    found = entries.get_participation_or_404(db, participation_id)
    _require_own(principal, found.member_id)
    found.public = body.public
    return participation.out(db, found)


# --- participants and leaderboard ---------------------------------------------------------------


@router.get("/programs/{program_id}/participants", response_model=Page[ParticipantOut])
def list_participants(
    program_id: ProgramId,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[ParticipationStatus | None, Query()] = None,
) -> Page[ParticipantOut]:
    program = programs.get_program_or_404(db, program_id)
    return paginate_sequence(participation.participants(db, program.id, status), page)


@router.get(
    "/programs/{program_id}/leaderboard", response_model=Page[LeaderboardOut], response_model_exclude_none=True
)
def get_leaderboard(program_id: ProgramId, db: SessionDep, principal: AnyUser, page: PageDep) -> Page[LeaderboardOut]:
    program = _visible_program(db, program_id, principal)
    rows = participation.leaderboard(db, program.id, staff=not _is_member(principal))
    return paginate_sequence(rows, page)


# --- entries ------------------------------------------------------------------------------------


@router.get("/participations/{participation_id}/entries", response_model=Page[EntryOut])
def list_entries(
    participation_id: ParticipationId,
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    source: Annotated[EntrySource | None, Query()] = None,
) -> Page[EntryOut]:
    found = _participation_for(db, participation_id, principal)
    result = paginate(db, entries.entries_stmt(found.id, source), page)
    titles = entries.book_titles(db, result.items)
    return Page[EntryOut](
        items=[entry_out(e, titles.get(e.book_id) if e.book_id is not None else None) for e in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post("/participations/{participation_id}/entries", response_model=EntryOut, status_code=201)
def add_entry(
    participation_id: ParticipationId, body: EntryIn, request: Request, db: SessionDep, staff: StaffOnly
) -> EntryOut:
    found = entries.get_participation_or_404(db, participation_id)
    book = db.get(Book, body.book_id)
    if book is None:
        raise ValidationFailed.single("book_id", f"book {body.book_id} does not exist")
    program = programs.get_program_or_404(db, found.program_id)
    entry = entries.add_manual(db, _now(request), staff.user, found, program, book, body.note)
    return entry_out(entry, book.title)


@router.delete("/program-entries/{entry_id}", status_code=204)
def remove_entry(entry_id: EntryId, request: Request, db: SessionDep, staff: StaffOnly) -> Response:
    entry = entries.get_entry_or_404(db, entry_id)
    entries.remove_manual(db, _now(request), staff.user, entry)
    return Response(status_code=204)


@router.get("/participations/{participation_id}/certificate", response_model=CertificateOut)
def get_certificate(participation_id: ParticipationId, db: SessionDep, principal: AnyUser) -> CertificateOut:
    found = _participation_for(db, participation_id, principal)
    return participation.certificate(db, found)


@router.get("/members/{member_id}/programs", response_model=Page[MemberProgramOut])
def member_programs(member_id: MemberId, db: SessionDep, principal: AnyUser, page: PageDep) -> Page[MemberProgramOut]:
    member = get_member_or_404(db, member_id)
    _require_own(principal, member.id)
    cache: dict[int, dict[int, int]] = {}
    return paginate(
        db, participation.member_programs_stmt(member.id), page, lambda p: participation.member_program_out(db, p, cache)
    )
