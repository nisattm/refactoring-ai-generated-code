"""Per-request access to the application settings and the clock (LIB-COM-02, LIB-IF-09)."""

from __future__ import annotations

import datetime

from fastapi import Request

from lms.core.clock import local_now, today
from lms.core.settings import Settings


def app_settings(request: Request) -> Settings:
    return request.app.state.settings


def request_now(request: Request) -> datetime.datetime:
    """The current local date-time of the application's clock."""
    return local_now(app_settings(request).clock)


def request_today(request: Request) -> datetime.date:
    """The local date of the application's clock (LIB-COM-02)."""
    return today(app_settings(request).clock)
