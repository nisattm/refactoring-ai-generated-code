"""Page packs (LIB-PRT-27, LIB-PRT-28)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict
from lms.core.money import format_amount
from lms.fines.service import create_fee
from lms.members.models import Member
from lms.printing.models import PrintPack
from lms.printing.rules import PACK_LIMIT, PACK_PAGES, PACK_PRICE


def pack_list_stmt(member_id: int, with_pages_left: bool | None) -> sa.Select[tuple[PrintPack]]:
    stmt = sa.select(PrintPack).where(PrintPack.member_id == member_id).order_by(PrintPack.bought_on, PrintPack.id)
    if with_pages_left is not None:
        stmt = stmt.where(PrintPack.pages_left > 0 if with_pages_left else PrintPack.pages_left == 0)
    return stmt


def buy_pack(db: Session, now: datetime.datetime, actor: User, member: Member) -> PrintPack:
    """LIB-PRT-27."""
    today = now.date()
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    with_pages = db.scalar(
        sa.select(sa.func.count()).select_from(PrintPack).where(PrintPack.member_id == member.id, PrintPack.pages_left > 0)
    )
    if (with_pages or 0) >= PACK_LIMIT:
        raise Conflict(
            "The member already has the most page packs allowed", code="PACK_LIMIT_REACHED", details={"limit": PACK_LIMIT}
        )
    pack = PrintPack(member_id=member.id, pages=PACK_PAGES, pages_left=PACK_PAGES, bought_on=today)
    db.add(pack)
    db.flush()
    fee = create_fee(
        db, now, actor, member_id=member.id, loan_id=None, kind="print_pack", amount=PACK_PRICE
    )
    pack.fee_id = fee.id
    record(
        db,
        at=now,
        event="print_pack_bought",
        actor_user_id=actor.id,
        entity_type="print_pack",
        entity_id=pack.id,
        details={"member_id": member.id, "pages": pack.pages, "fee_id": fee.id, "amount": format_amount(PACK_PRICE)},
    )
    return pack
