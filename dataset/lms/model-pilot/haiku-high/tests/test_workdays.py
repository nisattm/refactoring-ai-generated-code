"""Working-day rules (LIB-COM-05 to LIB-COM-10) with the worked examples of section 3.2."""

import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lms import DEFAULT_HOLIDAYS
from lms.core.workdays import (
    add_working_days,
    day_reason,
    is_working_day,
    next_working_day,
    working_days_between,
)

D = datetime.date


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (D(2026, 6, 1), D(2026, 6, 5), 4),  # LIB-COM-10
        (D(2026, 10, 23), D(2026, 10, 26), 1),
        (D(2026, 10, 27), D(2026, 10, 30), 2),
        (D(2026, 6, 5), D(2026, 6, 1), 0),  # end before start
        (D(2026, 6, 5), D(2026, 6, 5), 0),  # same day
    ],
)
def test_working_days_between(start, end, expected):
    assert working_days_between(start, end, DEFAULT_HOLIDAYS) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (D(2026, 5, 27), D(2026, 6, 1)),  # LIB-COM-08
        (D(2026, 3, 24), D(2026, 3, 24)),
        (D(2027, 1, 1), D(2027, 1, 4)),
    ],
)
def test_next_working_day(day, expected):
    assert next_working_day(day, DEFAULT_HOLIDAYS) == expected


@pytest.mark.parametrize(
    ("day", "n", "expected"),
    [
        (D(2026, 10, 28), 2, D(2026, 11, 2)),  # LIB-COM-09
        (D(2026, 5, 26), 2, D(2026, 6, 2)),
    ],
)
def test_add_working_days(day, n, expected):
    assert add_working_days(day, n, DEFAULT_HOLIDAYS) == expected


def test_add_working_days_rejects_zero():
    with pytest.raises(ValueError):
        add_working_days(D(2026, 10, 28), 0, DEFAULT_HOLIDAYS)


def test_half_day_holiday_eves_are_working_days():
    # LIB-COM-06: arife dates are not in the holiday list, so they are working days.
    # 2027-05-15 is a Saturday; the weekend rule of LIB-COM-05 still applies to it.
    for eve in [D(2026, 3, 19), D(2026, 5, 26), D(2026, 10, 28), D(2027, 3, 8), D(2027, 10, 28)]:
        assert eve not in DEFAULT_HOLIDAYS
        assert is_working_day(eve, DEFAULT_HOLIDAYS), eve
    assert D(2027, 5, 15) not in DEFAULT_HOLIDAYS
    assert not is_working_day(D(2027, 5, 15), DEFAULT_HOLIDAYS)


def test_reason_prefers_holiday_over_weekend():
    # 2026-08-30 is a Sunday and Victory Day (LIB-CORE-02)
    assert day_reason(D(2026, 8, 30), DEFAULT_HOLIDAYS) == "holiday"
    assert day_reason(D(2026, 11, 7), DEFAULT_HOLIDAYS) == "weekend"
    assert day_reason(D(2026, 11, 2), DEFAULT_HOLIDAYS) is None


def test_outside_listed_years_only_weekends_are_closed():
    # LIB-COM-07
    assert is_working_day(D(2030, 1, 1), DEFAULT_HOLIDAYS)
    assert not is_working_day(D(2030, 1, 5), DEFAULT_HOLIDAYS)  # Saturday


def test_custom_holidays_are_used():
    custom = frozenset({D(2026, 11, 3)})
    assert not is_working_day(D(2026, 11, 3), custom)
    assert next_working_day(D(2026, 11, 3), custom) == D(2026, 11, 4)


@given(
    start=st.dates(min_value=D(2000, 1, 1), max_value=D(2090, 1, 1)),
    n=st.integers(min_value=1, max_value=365),
)
@settings(max_examples=200)
def test_add_working_days_is_inverse_of_counting(start, n):
    result = add_working_days(start, n, DEFAULT_HOLIDAYS)
    assert is_working_day(result, DEFAULT_HOLIDAYS)
    assert working_days_between(start, result, DEFAULT_HOLIDAYS) == n


@given(
    a=st.dates(min_value=D(2000, 1, 1), max_value=D(2090, 1, 1)),
    span1=st.integers(min_value=0, max_value=400),
    span2=st.integers(min_value=0, max_value=400),
)
@settings(max_examples=200)
def test_working_days_between_is_additive(a, span1, span2):
    b = a + datetime.timedelta(days=span1)
    c = b + datetime.timedelta(days=span2)
    assert working_days_between(a, c, DEFAULT_HOLIDAYS) == (
        working_days_between(a, b, DEFAULT_HOLIDAYS) + working_days_between(b, c, DEFAULT_HOLIDAYS)
    )


@given(day=st.dates(min_value=D(2000, 1, 1), max_value=D(2090, 1, 1)))
@settings(max_examples=200)
def test_next_working_day_is_first_working_day_on_or_after(day):
    result = next_working_day(day, DEFAULT_HOLIDAYS)
    assert result >= day
    assert is_working_day(result, DEFAULT_HOLIDAYS)
    d = day
    while d < result:
        assert not is_working_day(d, DEFAULT_HOLIDAYS)
        d += datetime.timedelta(days=1)
