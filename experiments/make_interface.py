"""Write INTERFACE.md for the refactoring runs (ADR 004, W3): sections 1–4 of the requirements, verbatim.

    python experiments/make_interface.py --requirements <REQUIREMENTS.md> --out <INTERFACE.md>

The model of the Single and Iterative runs sees only ``lms/``, ``requirements.txt`` and ``INTERFACE.md``. INTERFACE.md is
the part of the requirements document from the heading ``## 1.`` up to (not including) the heading ``## 5.``: purpose
and scope, technical constraints, common rules and the fixed service interface. The lines are copied byte for byte,
line endings included. Not copied: the title block above section 1 (it says that tests were written from the
document), the separator line ``---`` and the blank lines right before section 5, and everything from section 5 on.

Headings inside fenced code blocks are ignored. The script fails (exit code 1, message on stderr) if a heading of
sections 1–5 is missing, appears twice or is out of order, so a changed document can never give a silently wrong
INTERFACE.md. Exit code 2: usage error. The output is the same for the same input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FIRST, LAST = 1, 4  # sections copied
HEADING = re.compile(r"^## (\d+)\. \S")
FENCE = re.compile(r"^(```|~~~)")


class InterfaceError(Exception):
    pass


def section_starts(lines: list[str]) -> dict[int, int]:
    """Line index of every top-level numbered heading ``## N. Title`` outside fenced code blocks."""
    starts: dict[int, int] = {}
    fence: str | None = None
    for index, line in enumerate(lines):
        text = line.rstrip("\r\n")
        match = FENCE.match(text)
        if match:
            if fence is None:
                fence = match.group(1)
            elif text.startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        heading = HEADING.match(text)
        if heading:
            number = int(heading.group(1))
            if number in starts:
                raise InterfaceError(f"heading of section {number} appears twice (lines {starts[number] + 1} and {index + 1})")
            starts[number] = index
    if fence is not None:
        raise InterfaceError("a fenced code block is not closed")
    return starts


def extract(text: str) -> str:
    """Sections FIRST..LAST of ``text``, verbatim, without the separator and blank lines before section LAST + 1."""
    lines = text.splitlines(keepends=True)
    starts = section_starts(lines)
    needed = list(range(FIRST, LAST + 2))
    missing = [n for n in needed if n not in starts]
    if missing:
        raise InterfaceError("missing section heading(s): " + ", ".join(f"## {n}." for n in missing))
    order = [starts[n] for n in needed]
    if order != sorted(order):
        raise InterfaceError(f"section headings {FIRST}–{LAST + 1} are not in order")
    body = lines[starts[FIRST]:starts[LAST + 1]]
    while body and body[-1].strip() in ("", "---"):
        body.pop()
    if not body:
        raise InterfaceError("sections are empty")
    if not body[-1].endswith(("\n", "\r")):
        body[-1] += "\n"
    return "".join(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--requirements", required=True, type=Path, help="the requirements document (REQUIREMENTS.md)")
    parser.add_argument("--out", required=True, type=Path, help="the INTERFACE.md to write")
    args = parser.parse_args(argv)
    try:
        with args.requirements.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        result = extract(text)
    except (OSError, UnicodeDecodeError, InterfaceError) as error:
        print(f"make_interface.py: {error}", file=sys.stderr)
        return 1
    try:
        with args.out.open("w", encoding="utf-8", newline="") as handle:
            handle.write(result)
    except OSError as error:
        print(f"make_interface.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
