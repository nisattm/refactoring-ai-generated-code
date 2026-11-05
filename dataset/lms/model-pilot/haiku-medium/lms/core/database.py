"""SQLite engine and schema setup (LIB-TECH-05, LIB-TECH-06, LIB-TECH-07, LIB-IF-03, LIB-IF-05)."""

import datetime

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.pool import StaticPool

from lms.core.clock import LOCAL_TZ


class Base(orm.DeclarativeBase):
    pass


class LocalDateTime(sqlalchemy.types.TypeDecorator):
    """Date-time stored as ISO 8601 text with its UTC offset (LIB-COM-03).

    SQLite drops time-zone information, so values are kept as text in local time.
    """

    impl = sqlalchemy.String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime.datetime | None, dialect) -> str | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("stored date-times must be timezone-aware")
        return value.astimezone(LOCAL_TZ).isoformat()

    def process_result_value(self, value: str | None, dialect) -> datetime.datetime | None:
        if value is None:
            return None
        return datetime.datetime.fromisoformat(value).astimezone(LOCAL_TZ)


def create_engine(database_url: str) -> sqlalchemy.Engine:
    url = sqlalchemy.make_url(database_url)
    if url.database in (None, "", ":memory:"):
        # One shared connection, so every request of the application sees the same data (LIB-IF-05).
        return sqlalchemy.create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return sqlalchemy.create_engine(database_url, connect_args={"check_same_thread": False})


def create_schema(engine: sqlalchemy.Engine) -> None:
    Base.metadata.create_all(engine)  # creates only missing tables (LIB-TECH-07)
