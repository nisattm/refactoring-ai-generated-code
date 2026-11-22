"""Shared HTTP response helpers."""

from __future__ import annotations

from fastapi import Response

CSV_TYPE = "text/csv; charset=utf-8"


def csv_response(text: str) -> Response:
    """A ``format=csv`` / CSV export response."""
    return Response(content=text.encode("utf-8"), media_type=CSV_TYPE)
