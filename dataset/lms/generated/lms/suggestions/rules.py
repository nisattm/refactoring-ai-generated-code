"""Rules by membership type (section 33.2) and fixed limits of module 25."""

from __future__ import annotations

# Weight of a member in the score of a suggestion; guests cannot take part (LIB-SUG-03), so a member who became
# a guest later (LIB-SUG-37) counts for nothing.
WEIGHTS = {"academic": 2, "student": 1, "staff": 1}
OPEN_LIMITS = {"student": 3, "academic": 10, "staff": 5, "guest": 0}

SUPPORT_LIMIT = 20  # LIB-SUG-13
SUPPORTERS_TO_KEEP = 3  # LIB-SUG-14
REJECTED_DAYS = 180  # LIB-SUG-03
SUBMITTED_EXPIRY_DAYS = 120  # LIB-SUG-34
APPROVED_EXPIRY_DAYS = 90  # LIB-SUG-34
LIBRARIAN_LIMIT = "300.00"  # LIB-SUG-20
MIN_YEAR = 1450
