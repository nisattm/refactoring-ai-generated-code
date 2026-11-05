"""SQLite engine and schema setup (LIB-TECH-05, LIB-TECH-06, LIB-TECH-07, LIB-IF-03, LIB-IF-05)."""

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.pool import StaticPool


class Base(orm.DeclarativeBase):
    pass


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
