"""Clock, settings and common-rule helpers (sections 3 and 4)."""

import datetime
import decimal

import pytest

from lms import DEFAULT_HOLIDAYS, FixedClock, Settings, SystemClock
from lms.core.localtime import LOCAL_TZ, format_datetime, today
from lms.core.money import format_money, parse_amount, round_money
from lms.core.pagination import page_body
from lms.core.text import clean_email, clean_text, normalize
from lms.core.request_types import parse_aware_datetime, parse_iso_date

LOCAL = datetime.timezone(datetime.timedelta(hours=3))


# LIB-IF-06
@pytest.mark.parametrize("ttl", [1, 168])
def test_token_ttl_bounds_accepted(ttl):
    assert Settings(token_ttl_hours=ttl).token_ttl_hours == ttl


@pytest.mark.parametrize("ttl", [0, 169, -1])
def test_token_ttl_out_of_bounds_rejected(ttl):
    with pytest.raises(ValueError):
        Settings(token_ttl_hours=ttl)


def test_settings_defaults_match_section_4_2():
    settings = Settings()
    assert settings.database_url == "sqlite:///./lms.db"
    assert settings.holidays == DEFAULT_HOLIDAYS
    assert settings.bootstrap_admin_email == "admin@library.local"
    assert settings.bootstrap_admin_password == "ChangeMe123"
    assert settings.token_ttl_hours == 12
    assert isinstance(settings.clock, SystemClock)


def test_settings_is_frozen():
    with pytest.raises(Exception):
        Settings().token_ttl_hours = 5  # type: ignore[misc]


# LIB-IF-08
def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError):
        FixedClock(datetime.datetime(2026, 11, 5, 9, 30))
    clock = FixedClock(datetime.datetime(2026, 11, 5, 9, 30, tzinfo=LOCAL))
    with pytest.raises(ValueError):
        clock.set(datetime.datetime(2026, 11, 5, 9, 30))


def test_fixed_clock_returns_and_advances_time():
    start = datetime.datetime(2026, 11, 5, 9, 30, tzinfo=LOCAL)
    clock = FixedClock(start)
    assert clock.now() == start
    clock.advance(days=1, hours=2, minutes=3)
    assert clock.now() == start + datetime.timedelta(days=1, hours=2, minutes=3)


# LIB-IF-07
def test_system_clock_is_local_time():
    now = SystemClock().now()
    assert now.utcoffset() == datetime.timedelta(hours=3)


# LIB-COM-01, LIB-COM-02
def test_today_is_local_date_of_clock():
    # 22:30 UTC on 4 Nov is 01:30 on 5 Nov in Türkiye
    clock = FixedClock(datetime.datetime(2026, 11, 4, 22, 30, tzinfo=datetime.timezone.utc))
    assert today(clock) == datetime.date(2026, 11, 5)


# LIB-COM-03
def test_datetimes_are_returned_in_local_time_with_offset():
    value = datetime.datetime(2026, 11, 2, 6, 30, tzinfo=datetime.timezone.utc)
    assert format_datetime(value) == "2026-11-02T09:30:00+03:00"


# LIB-COM-04
def test_request_date_must_be_iso_date():
    assert parse_iso_date("2026-11-02") == datetime.date(2026, 11, 2)
    for bad in ["2026-2-3", "02-11-2026", "2026-11-02T00:00:00", "2026-02-30", "20261102", 5]:
        with pytest.raises(ValueError):
            parse_iso_date(bad)


def test_request_datetime_must_have_offset():
    parsed = parse_aware_datetime("2026-11-02T09:30:00+03:00")
    assert parsed.utcoffset() == datetime.timedelta(hours=3)
    with pytest.raises(ValueError):
        parse_aware_datetime("2026-11-02T09:30:00")
    with pytest.raises(ValueError):
        parse_aware_datetime("not a date")


# LIB-COM-11 to LIB-COM-13, LIB-CORE-08
def test_amounts_are_strings_with_two_decimals():
    assert format_money(decimal.Decimal("12.5")) == "12.50"
    assert format_money(decimal.Decimal("0")) == "0.00"
    assert parse_amount("12.5") == decimal.Decimal("12.50")
    assert parse_amount("0") == decimal.Decimal("0.00")


@pytest.mark.parametrize("bad", [12.5, 12, "12.505", "-1.00", "abc", "1e3", "NaN", " 12.00", "١٢.٠٠"])
def test_invalid_amounts_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_negative_amount_allowed_when_requested():
    assert parse_amount("-1.00", allow_negative=True) == decimal.Decimal("-1.00")


def test_money_rounds_half_up_once_at_the_end():
    assert round_money(decimal.Decimal("0.125")) == decimal.Decimal("0.13")
    assert round_money(decimal.Decimal("-0.125")) == decimal.Decimal("-0.13")
    assert round_money(decimal.Decimal("2.345")) == decimal.Decimal("2.35")


# LIB-SRCH-01
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ISTANBUL", "istanbul"),
        ("İstanbul", "istanbul"),
        ("istanbul", "istanbul"),
        ("Işık", "işik"),
        ("IŞIK", "işik"),
    ],
)
def test_normalization(text, expected):
    assert normalize(text) == expected


def test_normalization_does_not_match_isik_with_s_cedilla():
    assert normalize("Işık") != normalize("isik")


# LIB-COM-15, LIB-COM-16
def test_text_is_trimmed_and_checked():
    assert clean_text("  Ayşe  ", min_length=1, max_length=200) == "Ayşe"
    with pytest.raises(ValueError):
        clean_text("   ", min_length=1, max_length=200)
    assert clean_text("x" * 200, min_length=1, max_length=200) == "x" * 200
    with pytest.raises(ValueError):
        clean_text("x" * 201, min_length=1, max_length=200)
    assert clean_text("", min_length=0, max_length=1000) == ""
    with pytest.raises(ValueError):
        clean_text("x" * 1001, max_length=1000)


# LIB-COM-17
def test_email_is_lowercased_and_checked():
    assert clean_email("  Ali.Veli@Library.EDU.tr ") == "ali.veli@library.edu.tr"
    for bad in ["a@@b.com", "@b.com", "ab.com", "a@bcom", "a@b@c.com", "  "]:
        with pytest.raises(ValueError):
            clean_email(bad)


# LIB-COM-18, LIB-COM-19
def test_page_body_shape():
    assert page_body(["a"], page=1, page_size=20, total=57) == {
        "items": ["a"],
        "page": 1,
        "page_size": 20,
        "total": 57,
    }
