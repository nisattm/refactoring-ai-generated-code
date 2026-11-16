"""Import cycle b -> a."""

from lms.loans import a


def b_value():
    return a.a_value() + 1
