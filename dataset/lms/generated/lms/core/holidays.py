"""Default official holidays (LIB-COM-06)."""
import datetime

_D = datetime.date

HOLIDAY_NAMES: dict[datetime.date, str] = {
    _D(2026, 1, 1): "New Year's Day",
    _D(2026, 3, 20): "Ramazan Bayramı, day 1",
    _D(2026, 3, 21): "Ramazan Bayramı, day 2",
    _D(2026, 3, 22): "Ramazan Bayramı, day 3",
    _D(2026, 4, 23): "National Sovereignty and Children's Day",
    _D(2026, 5, 1): "Labour and Solidarity Day",
    _D(2026, 5, 19): "Commemoration of Atatürk, Youth and Sports Day",
    _D(2026, 5, 27): "Kurban Bayramı, day 1",
    _D(2026, 5, 28): "Kurban Bayramı, day 2",
    _D(2026, 5, 29): "Kurban Bayramı, day 3",
    _D(2026, 5, 30): "Kurban Bayramı, day 4",
    _D(2026, 7, 15): "Democracy and National Unity Day",
    _D(2026, 8, 30): "Victory Day",
    _D(2026, 10, 29): "Republic Day",
    _D(2027, 1, 1): "New Year's Day",
    _D(2027, 3, 9): "Ramazan Bayramı, day 1",
    _D(2027, 3, 10): "Ramazan Bayramı, day 2",
    _D(2027, 3, 11): "Ramazan Bayramı, day 3",
    _D(2027, 4, 23): "National Sovereignty and Children's Day",
    _D(2027, 5, 1): "Labour and Solidarity Day",
    _D(2027, 5, 16): "Kurban Bayramı, day 1",
    _D(2027, 5, 17): "Kurban Bayramı, day 2",
    _D(2027, 5, 18): "Kurban Bayramı, day 3",
    _D(2027, 5, 19): "Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day",
    _D(2027, 7, 15): "Democracy and National Unity Day",
    _D(2027, 8, 30): "Victory Day",
    _D(2027, 10, 29): "Republic Day",
}

DEFAULT_HOLIDAYS: frozenset[datetime.date] = frozenset(HOLIDAY_NAMES)
