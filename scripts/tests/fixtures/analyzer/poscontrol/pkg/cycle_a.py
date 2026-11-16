"""Import cycle a -> b -> a (S18; pylint R0401)."""

from pkg import cycle_b


def a_value():
    return cycle_b.b_value() + 1
