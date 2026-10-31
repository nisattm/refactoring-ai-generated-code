"""Request and response schemas of module 11, branches (section 17)."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from lms.branches.models import Branch, Transfer
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime

_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")

BranchName = Annotated[str, Field(min_length=1, max_length=200)]
BranchAddress = Annotated[str, Field(max_length=300)]


class BranchCreateIn(RequestModel):
    code: str
    name: BranchName
    address: BranchAddress = ""

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not _CODE_RE.match(value):
            raise ValueError("code must be 2-10 characters from A-Z and 0-9")
        return value


class BranchPatchIn(RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    name: BranchName = None  # type: ignore[assignment]
    address: BranchAddress = None  # type: ignore[assignment]
    is_active: StrictBool = None  # type: ignore[assignment]


class BranchOut(BaseModel):
    id: int
    code: str
    name: str
    address: str
    is_active: bool
    created_at: str


def branch_out(branch: Branch) -> BranchOut:
    return BranchOut(
        id=branch.id,
        code=branch.code,
        name=branch.name,
        address=branch.address,
        is_active=branch.is_active,
        created_at=format_datetime(branch.created_at),
    )


class TransferCreateIn(RequestModel):
    copy_id: StrictInt
    to_branch_id: StrictInt


class TransferOut(BaseModel):
    id: int
    copy_id: int
    from_branch_id: int
    to_branch_id: int
    reason: str
    reservation_id: int | None
    started_on: str
    expected_on: str
    status: str
    received_on: str | None


class ReceivedOut(BaseModel):
    received: int


def transfer_out(transfer: Transfer) -> TransferOut:
    return TransferOut(
        id=transfer.id,
        copy_id=transfer.copy_id,
        from_branch_id=transfer.from_branch_id,
        to_branch_id=transfer.to_branch_id,
        reason=transfer.reason,
        reservation_id=transfer.reservation_id,
        started_on=transfer.started_on.isoformat(),
        expected_on=transfer.expected_on.isoformat(),
        status=transfer.status,
        received_on=transfer.received_on.isoformat() if transfer.received_on is not None else None,
    )
