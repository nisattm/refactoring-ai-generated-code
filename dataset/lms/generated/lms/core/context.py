"""Shared request-context plumbing for the API layer: settings, current time and date, holidays, path ids.

The dependencies never raise, so adding them to an endpoint does not change the order of the checks
authentication (401), role (403), validation (422) of LIB-COM-28.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import Depends, Path, Request

from lms.core.clock import local_now
from lms.core.settings import Settings

# A positive integer id taken from the URL path.
PathId = Annotated[int, Path(ge=1)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_now(settings: SettingsDep) -> datetime.datetime:
    """Current local time of the application's clock (LIB-COM-02)."""
    return local_now(settings.clock)


NowDep = Annotated[datetime.datetime, Depends(get_now)]


def get_today(now: NowDep) -> datetime.date:
    """Today's local date (LIB-COM-02)."""
    return now.date()


TodayDep = Annotated[datetime.date, Depends(get_today)]


def get_holidays(settings: SettingsDep) -> frozenset[datetime.date]:
    return settings.holidays


HolidaysDep = Annotated[frozenset[datetime.date], Depends(get_holidays)]
