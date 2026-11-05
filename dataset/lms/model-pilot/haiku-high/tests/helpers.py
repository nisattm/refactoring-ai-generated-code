import datetime

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base

LOCAL = datetime.timezone(datetime.timedelta(hours=3))


class Probe(Base):
    """Test-only table used to check transactions, pagination and isolation (no module entity yet)."""

    __tablename__ = "probe"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.String(200))


def local_datetime(*args) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=LOCAL)
