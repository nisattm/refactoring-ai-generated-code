"""Loan routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/loans")
def list_loans(a, b, c, d, e, f):
    return [a, b, c, d, e, f]
