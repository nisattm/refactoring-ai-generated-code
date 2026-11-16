"""Loan service: one example of each smell, with known counts (see test_analyzer.py)."""

import json  # noqa: F401
import os
from typing import Any, cast

import requests


def too_many(a, b, c, d, e, f):
    return a


def unused_local():
    value = 1
    return 0


def complex_condition(a, b, c):
    if a and b and c and a and b and c:
        return 1
    return 0


def nested_if(a, b):
    if a:
        if b:
            return 1
    return 0


def magic(x):
    if x > 42 or x < 7:
        return "out"
    return "in"


def swallow():
    try:
        os.remove("x")
    except Exception:
        pass


def mutable(items=[]):
    items.append(1)
    return items


def redundant_else(x):
    if x:
        return "a"
    else:
        return "b"


def bypass(x: Any) -> Any:
    y = cast(int, x)
    z = x  # type: ignore
    return y, z


def casting(x):
    return cast(int, x)


def deep(a):
    for i in a:
        for j in i:
            for k in j:
                for m in k:
                    for n in m:
                        for p in n:
                            return p
    return None


def fetch():
    return requests.get("https://example.invalid")


def long_function(x):
    """Docstring lines do not count.

    Second docstring line.
    """
    total = 0
    total += x + 1
    total += x + 2
    total += x + 3
    total += x + 4
    total += x + 5
    total += x + 6
    total += x + 7
    total += x + 8
    total += x + 9
    total += x + 10
    total += x + 11
    total += x + 12
    total += x + 13
    total += x + 14
    total += x + 15
    total += x + 16
    total += x + 17
    total += x + 18
    total += x + 19
    total += x + 20
    total += x + 21
    total += x + 22
    total += x + 23
    total += x + 24
    total += x + 25
    total += x + 26
    total += x + 27
    total += x + 28
    total += x + 29
    total += x + 30
    total += x + 31
    total += x + 32
    total += x + 33
    total += x + 34
    total += x + 35
    total += x + 36
    total += x + 37
    total += x + 38
    total += x + 39
    total += x + 40
    total += x + 41
    total += x + 42
    total += x + 43
    total += x + 44
    total += x + 45
    total += x + 46
    return total


class Big:
    def m01(self):
        return 1
    def m02(self):
        return 2
    def m03(self):
        return 3
    def m04(self):
        return 4
    def m05(self):
        return 5
    def m06(self):
        return 6
    def m07(self):
        return 7
    def m08(self):
        return 8
    def m09(self):
        return 9
    def m10(self):
        return 10
    def m11(self):
        return 11
    def m12(self):
        return 12
    def m13(self):
        return 13
    def m14(self):
        return 14
    def m15(self):
        return 15
    def m16(self):
        return 16
