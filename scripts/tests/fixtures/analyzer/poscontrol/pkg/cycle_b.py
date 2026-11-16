"""Import cycle b -> a (S18; pylint R0401)."""

from pkg import cycle_a


def b_value():
    return cycle_a.a_value() + 1
