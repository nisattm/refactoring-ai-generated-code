"""CSV output (LIB-IO-13, LIB-IO-14)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def to_csv(columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> str:
    """Header row, ``\\r\\n`` line ends, RFC 4180 quoting, null as an empty field."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_value(row[c]) for c in columns])
    return out.getvalue()
