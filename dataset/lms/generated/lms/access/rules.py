"""Constants of module 28 (sections 36.1, 36.2, 36.4 and 36.7)."""

from __future__ import annotations

from decimal import Decimal

CARD_FEES = {"lost": Decimal("25.00"), "damaged": Decimal("10.00")}
REPEAT_FEE = Decimal("50.00")
REPEAT_REPLACEMENTS = 3
REPEAT_WINDOW_DAYS = 365
DAY_PASS_LIMIT = 50
MAX_BAN_DAYS = 365
MAX_CAPACITY = 5000
MAX_DAY_PASS_PRICE = Decimal("100.00")
MAX_REPORT_DAYS = 365
