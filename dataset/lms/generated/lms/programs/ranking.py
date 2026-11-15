"""Points, levels and ranks (sections 34.2 and 34.7)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.programs.models import LEVELS, Participation


def level_for(books: int, goal_books: int) -> str:
    """34.2: the level by the number of books."""
    if books >= 3 * goal_books:
        return "gold"
    if books >= 2 * goal_books:
        return "silver"
    if books >= goal_books:
        return "bronze"
    return "none"


def level_index(level: str) -> int:
    return LEVELS.index(level)


def _key(p: Participation) -> tuple:
    """LIB-RDP-26: points descending, completed first (earliest completion), then ``joined_at``, then ``id``."""
    return (
        -p.points,
        p.completed_at is None,
        p.completed_at if p.completed_at is not None else p.joined_at,
        p.joined_at,
        p.id,
    )


def counted(db: Session, program_id: int) -> list[Participation]:
    """The ``active`` and ``completed`` participations of a program."""
    stmt = sa.select(Participation).where(
        Participation.program_id == program_id, Participation.status.in_(("active", "completed"))
    )
    return list(db.scalars(stmt))


def ranked(db: Session, program_id: int) -> list[Participation]:
    """The participations with points, in rank order."""
    return sorted((p for p in counted(db, program_id) if p.points > 0), key=_key)


def ranks(db: Session, program_id: int) -> dict[int, int]:
    """``{participation id: rank}`` for the ranked participations (LIB-RDP-26)."""
    return {p.id: position for position, p in enumerate(ranked(db, program_id), start=1)}


def order_all(db: Session, program_id: int, status: str | None) -> tuple[list[Participation], dict[int, int]]:
    """LIB-RDP-47: ranked participations first, then the others by ``joined_at``; with the ranks."""
    rank_of = ranks(db, program_id)
    stmt = sa.select(Participation).where(Participation.program_id == program_id)
    if status is not None:
        stmt = stmt.where(Participation.status == status)
    items = list(db.scalars(stmt))
    items.sort(key=lambda p: (0, rank_of[p.id]) if p.id in rank_of else (1, p.joined_at, p.id))
    return items, rank_of
