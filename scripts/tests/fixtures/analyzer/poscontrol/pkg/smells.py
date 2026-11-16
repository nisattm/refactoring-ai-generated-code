"""Positive control: every rule of the frozen smell list fires at least once (PR 1, tool check).

Not real code. Each block names the smell it must trigger.
"""

import os  # S07 F401: unused import
import json  # noqa: F401  (S07 with --ignore-noqa)
import sys
from typing import Any, cast  # S23: ANN401 below, cast( further down

import requests  # S22: not in the allowed library list


def long_parameter_list(a, b, c, d, e, f):  # S03 PLR0913: 6 parameters
    return a + b + c + d + e + f


def unused_local():
    value = 1  # S07 F841
    return 0


def complex_condition(a, b, c, d, e, f):  # S09 PLR0916 (--preview): 6 boolean operands
    if a and b and c and d and e and f:
        return 1
    return 0


def nested_if(a, b):  # S09 SIM102
    if a:
        if b:
            return 1
    return 0


def magic_number(x):
    if x > 42:  # S11 PLR2004
        return 1
    return 0


def swallow():
    try:
        os.remove("x")
    except Exception:  # S19 BLE001
        pass  # S19 S110


def swallow_narrow():
    try:
        os.remove("x")
    except OSError:  # S19 S110 (narrow exception, still swallowed)
        pass


def broad_but_logged():
    try:
        os.remove("x")
    except Exception as exc:  # BLE001 only, no S110: pylint W0718
        print(exc)


def mutable_default(items=[]):  # S20 B006
    items.append(1)
    return items


def redundant_else(x):  # S21 RET505
    if x:
        return 1
    else:
        return 2


def inconsistent_return(x):  # pylint R1710 (S21 secondary)
    if x:
        return 1


def unreachable():  # pylint W0101
    return 1
    print("never")


def bypass(x: Any) -> Any:  # S23 ANN401 (2x)
    y = cast(int, x)  # S23 cast(
    z = x  # type: ignore
    return y, z


def deep(a, b, c, d, e, f):  # S10 pylint R1702: 6 nested blocks (limit 5)
    for i in a:
        for j in b:
            for k in c:
                for m in d:
                    for n in e:
                        for p in f:
                            return i, j, k, m, n, p
    return None


def uses_sys():
    return sys.argv


def never_called_by_anyone():  # vulture (confidence 60, below 80: must NOT be reported at 80)
    return requests
