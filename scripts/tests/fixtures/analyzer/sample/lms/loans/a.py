"""Import cycle a -> b -> a."""

from lms.loans import b


def a_value():
    return b.b_value() + 1
