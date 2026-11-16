"""Class kinds: orm, enum, schema, plain."""

import enum

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Loan(Base):
    __tablename__ = "loans"


class Status(enum.Enum):
    OPEN = "open"


class LoanIn(BaseModel):
    name: str


class Helper:
    def run(self):
        return 1
