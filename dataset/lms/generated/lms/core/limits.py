"""Numeric limits that several modules share."""

from __future__ import annotations

MIN_PUBLICATION_YEAR = 1450  # earliest ``publication_year`` of a book, suggestion or donated item
MIN_REPORT_YEAR = 2000  # earliest ``year`` of a yearly report or a budget
MAX_REPORT_YEAR = 2100  # latest ``year`` of a yearly report or a budget
MAX_REPORT_DAYS = 365  # longest ``from`` to ``to`` range of a report (366 days including both ends)
