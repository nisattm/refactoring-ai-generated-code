"""Purchase suggestion endpoints (section 33.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from lms.api.params import own_member as _own_member
from lms.api.params import reject_nulls
from lms.auth.deps import AnyUser, CurrentPrincipal, Principal, StaffOnly, require_roles
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed
from lms.core.pagination import Page, PageDep, paginate
from lms.catalog.models import Book
from lms.members.service import get_member_or_404
from lms.purchasing.schemas import OrderOut
from lms.purchasing.service import order_response
from lms.suggestions import ordering, review, service
from lms.suggestions.models import Suggestion
from lms.suggestions.schemas import (
    ApprovalPatchIn,
    ApproveIn,
    MemberSuggestionsOut,
    MergeIn,
    OrderIn,
    ProcessOut,
    RejectIn,
    SuggestIn,
    SuggestionOut,
    SuggestionStatus,
    SuggestPatchIn,
    SupporterOut,
    SupportIn,
)

router = APIRouter(tags=["suggestions"])

SuggestionId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]

MemberOnly = Annotated[Principal, Depends(require_roles("member"))]


def _now(request: Request) -> datetime.datetime:
    return local_now(request.app.state.settings.clock)


def _is_member(principal: Principal) -> bool:
    return principal.user.role == "member"


def _viewer(principal: Principal, *, hide_member_id: bool = False) -> service.Viewer:
    if _is_member(principal):
        return service.Viewer(member_id=principal.user.member_id, hide_member_id=hide_member_id)
    return service.STAFF


def _require_own(principal: Principal, suggestion: Suggestion) -> None:
    """LIB-AUTH-25."""
    if _is_member(principal) and suggestion.member_id != principal.user.member_id:
        raise Forbidden("Only your own suggestions can be changed")


def _not_found(suggestion_id: int) -> NotFound:
    return NotFound(f"Suggestion {suggestion_id} does not exist", details={"resource": "suggestion", "id": suggestion_id})


# --- suggesting and reading -----------------------------------------------------------------------


@router.post("/suggestions", response_model=SuggestionOut, status_code=201, response_model_exclude_unset=True)
def suggest(body: SuggestIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> SuggestionOut:
    now = _now(request)
    if _is_member(principal):
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "members suggest for themselves and must not send member_id")
    elif body.member_id is None:
        raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
    service.check_year(body.publication_year, now.date())
    branch = service.require_known_branch(db, body.branch_id)
    member = _own_member(db, principal) if _is_member(principal) else service.get_member_or_reference_404(db, body.member_id)
    suggestion = service.suggest(
        db,
        now,
        principal.user,
        member,
        branch,
        title=body.title,
        author_text=body.author_text,
        isbn=body.isbn,
        publication_year=body.publication_year,
        reason=body.reason,
    )
    return service.to_out(db, suggestion, _viewer(principal))


@router.get("/suggestions", response_model=Page[SuggestionOut], response_model_exclude_unset=True)
def list_suggestions(
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    status: Annotated[SuggestionStatus | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    isbn: Annotated[str | None, Query()] = None,
) -> Page[SuggestionOut]:
    viewer = _viewer(principal, hide_member_id=True)
    stmt = service.list_stmt(viewer, status=status, branch_id=branch_id, member_id=member_id, q=q, isbn=isbn)
    result = paginate(db, stmt, page)
    return Page[SuggestionOut](
        items=service.to_outs(db, result.items, viewer), page=result.page, page_size=result.page_size, total=result.total
    )


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionOut, response_model_exclude_unset=True)
def get_suggestion(suggestion_id: SuggestionId, db: SessionDep, principal: AnyUser) -> SuggestionOut:
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    if _is_member(principal) and not suggestion.is_open and suggestion.member_id != principal.user.member_id:
        raise _not_found(suggestion_id)  # LIB-SUG-12
    return service.to_out(db, suggestion, _viewer(principal))


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionOut, response_model_exclude_unset=True)
def update_suggestion(
    suggestion_id: SuggestionId, body: SuggestPatchIn, request: Request, db: SessionDep, principal: MemberOnly
) -> SuggestionOut:
    now = _now(request)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    reject_nulls(fields, ("title", "author_text", "reason", "branch_id"))
    service.check_year(fields.get("publication_year"), now.date())
    if "branch_id" in fields:
        service.require_known_branch(db, fields["branch_id"])
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    _require_own(principal, suggestion)
    updated = service.update(db, now, principal.user, suggestion, fields)
    return service.to_out(db, updated, _viewer(principal))


@router.post("/suggestions/{suggestion_id}/withdraw", response_model=SuggestionOut, response_model_exclude_unset=True)
def withdraw_suggestion(
    suggestion_id: SuggestionId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> SuggestionOut:
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    _require_own(principal, suggestion)
    withdrawn = service.withdraw(db, _now(request), principal.user, suggestion, by_member=_is_member(principal))
    return service.to_out(db, withdrawn, _viewer(principal))


# --- support -------------------------------------------------------------------------------------


@router.post(
    "/suggestions/{suggestion_id}/support", response_model=SuggestionOut, status_code=201, response_model_exclude_unset=True
)
def support_suggestion(
    suggestion_id: SuggestionId,
    request: Request,
    db: SessionDep,
    principal: MemberOnly,
    body: SupportIn | None = None,
) -> SuggestionOut:
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    member = _own_member(db, principal)
    reserve = body.reserve_on_arrival if body is not None else True
    service.support(db, _now(request), principal.user, member, suggestion, reserve)
    return service.to_out(db, suggestion, _viewer(principal))


@router.delete("/suggestions/{suggestion_id}/support", status_code=204)
def stop_supporting(suggestion_id: SuggestionId, request: Request, db: SessionDep, principal: MemberOnly) -> Response:
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    service.remove_support(db, _now(request), principal.user, _own_member(db, principal), suggestion)
    return Response(status_code=204)


@router.get("/suggestions/{suggestion_id}/supporters", response_model=Page[SupporterOut])
def list_supporters(suggestion_id: SuggestionId, db: SessionDep, _: StaffOnly, page: PageDep) -> Page[SupporterOut]:
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    stmt = service.supporters_stmt(suggestion.id)
    total = len(db.execute(stmt).all())
    rows = db.execute(stmt.limit(page.page_size).offset(page.offset)).all()
    return Page[SupporterOut](
        items=[service.supporter_out(r) for r in rows], page=page.page, page_size=page.page_size, total=total
    )


@router.get(
    "/members/{member_id}/suggestions", response_model=MemberSuggestionsOut, response_model_exclude_unset=True
)
def member_suggestions(member_id: MemberId, db: SessionDep, principal: CurrentPrincipal) -> MemberSuggestionsOut:
    member = get_member_or_404(db, member_id)
    if _is_member(principal) and principal.user.member_id != member.id:
        raise Forbidden("Only your own suggestions can be accessed")
    own, supported = service.member_suggestions(db, member.id, _viewer(principal))
    return MemberSuggestionsOut(own=own, supported=supported)


# --- review --------------------------------------------------------------------------------------


@router.post("/suggestions/{suggestion_id}/approve", response_model=SuggestionOut, response_model_exclude_unset=True)
def approve_suggestion(
    suggestion_id: SuggestionId, body: ApproveIn, request: Request, db: SessionDep, staff: StaffOnly
) -> SuggestionOut:
    review.check_approval_rights(staff.user, body.quantity, body.estimated_price)  # LIB-SUG-20
    book = db.get(Book, body.book_id)
    if book is None:
        raise ValidationFailed.single("book_id", f"book {body.book_id} does not exist")
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    approved = review.approve(
        db,
        _now(request),
        staff.user,
        suggestion,
        book=book,
        quantity=body.quantity,
        estimated_price=body.estimated_price,
        review_note=body.review_note,
    )
    return service.to_out(db, approved, service.STAFF)


@router.patch("/suggestions/{suggestion_id}/approval", response_model=SuggestionOut, response_model_exclude_unset=True)
def change_approval(
    suggestion_id: SuggestionId, body: ApprovalPatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> SuggestionOut:
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    reject_nulls(fields)
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    changed = review.change_approval(db, _now(request), staff.user, suggestion, fields)
    return service.to_out(db, changed, service.STAFF)


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionOut, response_model_exclude_unset=True)
def reject_suggestion(
    suggestion_id: SuggestionId, body: RejectIn, request: Request, db: SessionDep, staff: StaffOnly
) -> SuggestionOut:
    settings = request.app.state.settings
    suggestion = service.get_suggestion_or_404(db, suggestion_id)
    rejected = review.reject(
        db,
        local_now(settings.clock),
        staff.user,
        settings.holidays,
        suggestion,
        reject_reason=body.reject_reason,
        review_note=body.review_note,
        book_id=body.book_id,
    )
    return service.to_out(db, rejected, service.STAFF)


@router.post("/suggestions/{suggestion_id}/merge", response_model=SuggestionOut, response_model_exclude_unset=True)
def merge_suggestion(
    suggestion_id: SuggestionId, body: MergeIn, request: Request, db: SessionDep, staff: StaffOnly
) -> SuggestionOut:
    if body.into_suggestion_id == suggestion_id:
        raise ValidationFailed.single("into_suggestion_id", "a suggestion cannot be merged into itself")
    source = service.get_suggestion_or_404(db, suggestion_id)
    target = review.merge(db, _now(request), staff.user, source, body.into_suggestion_id)
    return service.to_out(db, target, service.STAFF)


# --- ordering and expiry -----------------------------------------------------------------------


@router.post("/suggestions/order", response_model=OrderOut, status_code=201)
def order_suggestions(body: OrderIn, request: Request, db: SessionDep, staff: StaffOnly) -> OrderOut:
    purchase_order = ordering.order(
        db,
        _now(request),
        staff.user,
        supplier_id=body.supplier_id,
        branch_id=body.branch_id,
        suggestion_ids=body.suggestion_ids,
    )
    return order_response(db, purchase_order)


@router.post("/suggestions/process", response_model=ProcessOut)
def process_suggestions(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    return ordering.process(db, _now(request), staff.user)
