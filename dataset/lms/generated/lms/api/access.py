"""Member card and building access endpoints (section 36.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.access import bans, cards, gate, occupancy, passes
from lms.access import reports as access_reports
from lms.access.models import AccessAlert, AccessBan, Card, Visit
from lms.access.schemas import (
    AlertOut,
    BanIn,
    BanOut,
    CardDetailOut,
    CardMemberOut,
    CardOut,
    DayPassIn,
    DayPassOut,
    InsideOut,
    OccupancyOut,
    PassStatus,
    ProcessOut,
    ReportIn,
    ScanIn,
    ScanOut,
    SettingsIn,
    SettingsOut,
    VisitOut,
    VisitsReportOut,
    ban_out,
    card_out,
    day_pass_out,
    visit_out,
)
from lms.auth.deps import AdminOnly, CurrentPrincipal, Principal, StaffOnly
from lms.branches.models import Branch
from lms.branches.service import get_branch_or_404
from lms.core.clock import LOCAL_TZ, local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.timeutil import format_datetime, parse_date
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["access"])

MemberId = Annotated[int, Path(ge=1)]
BranchId = Annotated[int, Path(ge=1)]
PassId = Annotated[int, Path(ge=1)]
VisitId = Annotated[int, Path(ge=1)]
BanId = Annotated[int, Path(ge=1)]
CardNo = Annotated[str, Path(min_length=1)]


def _now(request: Request) -> datetime.datetime:
    return local_now(request.app.state.settings.clock)


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25: a member may only address their own cards, visits and bans."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own data can be accessed")


def _branch_reference(db: SessionDep, branch_id: int) -> Branch:
    """A branch named in a request body: ``404 NOT_FOUND`` when missing (LIB-COM-29)."""
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    return branch


def _opt_date(name: str, raw: str | None) -> datetime.date | None:
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, "expected a valid date in the form YYYY-MM-DD") from None


# --- cards ------------------------------------------------------------------------------------------


@router.post("/members/{member_id}/cards", response_model=CardOut, status_code=201)
def issue_card(member_id: MemberId, request: Request, db: SessionDep, staff: StaffOnly) -> CardOut:
    member = get_member_or_404(db, member_id)
    return card_out(cards.issue_card(db, _now(request), staff.user, member))


@router.get("/members/{member_id}/cards", response_model=Page[CardOut])
def list_cards(member_id: MemberId, db: SessionDep, principal: CurrentPrincipal, page: PageDep) -> Page[CardOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = sa.select(Card).where(Card.member_id == member.id).order_by(Card.issued_on.desc(), Card.id.desc())
    return paginate(db, stmt, page, card_out)


@router.get("/cards/{card_no}", response_model=CardDetailOut)
def get_card(card_no: CardNo, db: SessionDep, _: StaffOnly) -> CardDetailOut:
    card = cards.get_card_or_404(db, card_no)
    member = db.get(Member, card.member_id)
    assert member is not None
    return CardDetailOut(
        **card_out(card).model_dump(),
        member=CardMemberOut(
            id=member.id,
            member_no=member.member_no,
            full_name=member.full_name,
            membership_type=member.membership_type,
            status=member.status,
        ),
    )


@router.post("/cards/{card_no}/report", response_model=CardOut)
def report_card(
    card_no: CardNo, body: ReportIn, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> CardOut:
    card = cards.get_card_or_404(db, card_no)
    _own_or_staff(principal, card.member_id)
    return card_out(cards.report_card(db, _now(request), principal.user, card, body.reason))


# --- settings and occupancy -----------------------------------------------------------------------------


@router.put("/access-settings/{branch_id}", response_model=SettingsOut)
def put_settings(
    branch_id: BranchId, body: SettingsIn, request: Request, db: SessionDep, admin: AdminOnly
) -> SettingsOut:
    branch = get_branch_or_404(db, branch_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return occupancy.update_settings(db, _now(request), admin.user, branch.id, fields)


@router.get("/access-settings/{branch_id}", response_model=SettingsOut)
def get_settings(branch_id: BranchId, db: SessionDep, _: StaffOnly) -> SettingsOut:
    branch = get_branch_or_404(db, branch_id)
    return occupancy.settings_out(db, branch.id)


@router.get("/branches/{branch_id}/occupancy", response_model=OccupancyOut)
def get_occupancy(branch_id: BranchId, db: SessionDep, _: CurrentPrincipal) -> OccupancyOut:
    branch = get_branch_or_404(db, branch_id)
    return occupancy.occupancy_out(db, branch.id)


@router.get("/branches/{branch_id}/inside", response_model=Page[InsideOut])
def get_inside(branch_id: BranchId, db: SessionDep, _: StaffOnly, page: PageDep) -> Page[InsideOut]:
    branch = get_branch_or_404(db, branch_id)
    return paginate(db, occupancy.inside_stmt(branch.id), page, lambda v: occupancy.inside_out(db, v))


# --- gate -------------------------------------------------------------------------------------------


@router.post("/access/scan", response_model=ScanOut)
def scan(body: ScanIn, request: Request, db: SessionDep, staff: StaffOnly) -> ScanOut:
    if (body.card_no is None) == (body.pass_code is None):
        raise ValidationFailed.single("card_no", "exactly one of card_no and pass_code is required")
    branch = _branch_reference(db, body.branch_id)
    settings = request.app.state.settings
    return gate.scan(
        db, _now(request), staff.user, settings.holidays, branch, body.direction, body.card_no, body.pass_code
    )


@router.get("/access/alerts", response_model=Page[AlertOut])
def list_alerts(db: SessionDep, _: StaffOnly, page: PageDep) -> Page[AlertOut]:
    stmt = sa.select(AccessAlert).order_by(AccessAlert.at.desc(), AccessAlert.id.desc())
    return paginate(
        db,
        stmt,
        page,
        lambda alert: AlertOut(
            card_no=db.get(Card, alert.card_id).card_no, branch_id=alert.branch_id, at=format_datetime(alert.at)
        ),
    )


@router.post("/visits/{visit_id}/close", response_model=VisitOut)
def close_visit(visit_id: VisitId, request: Request, db: SessionDep, staff: StaffOnly) -> VisitOut:
    visit = gate.get_visit_or_404(db, visit_id)
    return visit_out(gate.close_by_hand(db, _now(request), staff.user, visit))


@router.post("/access/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    return gate.process(db, _now(request), staff.user, request.app.state.settings.holidays)


# --- day passes -------------------------------------------------------------------------------------


@router.post("/day-passes", response_model=DayPassOut, status_code=201)
def sell_pass(body: DayPassIn, request: Request, db: SessionDep, staff: StaffOnly) -> DayPassOut:
    branch = _branch_reference(db, body.branch_id)
    return day_pass_out(passes.sell_pass(db, _now(request), staff.user, branch, body.visitor_name))


@router.get("/day-passes", response_model=Page[DayPassOut])
def list_passes(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    valid_on: Annotated[str | None, Query()] = None,
    status: Annotated[PassStatus | None, Query()] = None,
) -> Page[DayPassOut]:
    stmt = passes.list_stmt(branch_id=branch_id, valid_on=_opt_date("valid_on", valid_on), status=status)
    return paginate(db, stmt, page, day_pass_out)


@router.post("/day-passes/{pass_id}/cancel", response_model=DayPassOut)
def cancel_pass(pass_id: PassId, request: Request, db: SessionDep, staff: StaffOnly) -> DayPassOut:
    day_pass = passes.get_pass_or_404(db, pass_id)
    return day_pass_out(passes.cancel_pass(db, _now(request), staff.user, day_pass))


# --- bans -------------------------------------------------------------------------------------------


@router.post("/members/{member_id}/access-bans", response_model=BanOut, status_code=201)
def create_ban(member_id: MemberId, body: BanIn, request: Request, db: SessionDep, staff: StaffOnly) -> BanOut:
    now = _now(request)
    member = get_member_or_404(db, member_id)
    ban = bans.create_ban(db, now, staff.user, member, body.reason, body.starts_on, body.ends_on)
    return ban_out(ban, now.date())


@router.get("/members/{member_id}/access-bans", response_model=Page[BanOut])
def list_bans(
    member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal, page: PageDep
) -> Page[BanOut]:
    day = _now(request).date()
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = sa.select(AccessBan).where(AccessBan.member_id == member.id).order_by(
        AccessBan.starts_on.desc(), AccessBan.id.desc()
    )
    return paginate(db, stmt, page, lambda b: ban_out(b, day))


@router.post("/access-bans/{ban_id}/lift", response_model=BanOut)
def lift_ban(ban_id: BanId, request: Request, db: SessionDep, staff: StaffOnly) -> BanOut:
    now = _now(request)
    ban = bans.get_ban_or_404(db, ban_id)
    return ban_out(bans.lift_ban(db, now, staff.user, ban), now.date())


# --- visits and report ------------------------------------------------------------------------------------


@router.get("/members/{member_id}/visits", response_model=Page[VisitOut])
def list_visits(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[VisitOut]:
    start = _opt_date("from", first)
    end = _opt_date("to", to)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = sa.select(Visit).where(Visit.member_id == member.id).order_by(Visit.entered_at.desc(), Visit.id.desc())
    if start is not None:
        stmt = stmt.where(Visit.entered_at >= datetime.datetime.combine(start, datetime.time.min, LOCAL_TZ))
    if end is not None and end < datetime.date.max:
        after = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
        stmt = stmt.where(Visit.entered_at < after)
    if branch_id is not None:
        stmt = stmt.where(Visit.branch_id == branch_id)
    return paginate(db, stmt, page, visit_out)


@router.get("/reports/visits", response_model=Page[VisitsReportOut])
def visits_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[VisitsReportOut]:
    problems: list[dict[str, str]] = []
    dates: dict[str, datetime.date] = {}
    for name, raw in (("from", first), ("to", to)):
        if raw is None:
            problems.append({"field": name, "problem": "field required"})
            continue
        try:
            dates[name] = parse_date(raw.strip())
        except ValueError:
            problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
    if problems:
        raise ValidationFailed(problems)
    start, end = dates["from"], dates["to"]
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return paginate_sequence(access_reports.visits_report(db, start, end, branch_id), page)
