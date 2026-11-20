"""Test feedback between rounds (ADR 004, W2): the confirmed regressions of a round as a short, clean text.

    format_feedback(tests_before_csv, tests_after_csv, repeat_csvs, log_dir) -> str

Used by the Iterative runner after every round that changed ``lms/`` and, in Week 6, by Multi-Agent. Rules (W2):

- Only **confirmed regressions**: a case that passed at the start, is ``failed``, ``error``, ``skipped`` or ``missing``
  after the round, is not in ``flaky.txt`` and does not pass in either of the two repetitions. The decision is the one
  of ``scripts/compare.py`` (``compare_tests``), so the feedback never disagrees with ``round_accepted``. Fewer than
  two repetitions means "not confirmed": such a case is not shown.
- Per case: its test ID and a short error message (the exception message, the deepest line in ``lms/`` where it was
  raised); at most 6 lines per test, 60 lines in total and 15 tests. Lines of our test files, introspection lines
  of pytest, colour codes, absolute and temporary paths and memory addresses are removed. Cases with the same
  cleaned message are merged into one block.
- Never shown: metrics, held-out cases, the OpenAPI result, cases that already failed at the start, flaky cases.
- No confirmed regression: the empty text. The same input always gives the same output.

Inputs as the engine passes them (ADR 004, interfaces): ``tests_before_csv`` is the ``tests.csv`` of the starting
measurement (both sets; ``flaky.txt`` is read from the same folder if it exists), ``tests_after_csv`` the ``tests.csv``
of the round (feedback set only), ``repeat_csvs`` the ``tests.csv`` of the repetitions (0–2) and ``log_dir`` the
round's test folder with ``<set>.junit.xml`` written by ``scripts/run_tests.py``.

Command line (for checks and the pilot report):

    python experiments/feedback.py --tests-before <csv> --tests-after <csv> [--repeat <csv>]... --log-dir <dir>
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare  # noqa: E402  (scripts/compare.py: the regression rule of D17-D19)

MAX_TESTS = 15
MAX_LINES_PER_TEST = 6          # the ID line and at most 5 detail lines
MAX_LINES = 60                  # the whole text, header and last line included
MAX_MESSAGE_LINES = 4           # detail lines from the error message; one more for the location
MAX_LINE_CHARS = 200

HEADER = "These feedback tests passed before your changes and fail now:"
MORE = "{n} more failing feedback tests are not shown."
NO_MESSAGE = "(no error message recorded)"
MISSING = "not reported by the test run"

ANSI = re.compile(r"(?:\x1b|#x1B)\[[0-9;]*[A-Za-z]")
ADDRESS = re.compile(r"\b0x[0-9A-Fa-f]{4,}\b")
LMS_PATH = re.compile(r"""(?:[A-Za-z]:)?[^\s:'"]*?[\\/](lms[\\/][^\s:'"]*)""")
# Absolute file system paths only (Windows drives and the usual Linux roots), never URL paths like /api/v1/loans
ABS_PATH = re.compile(r"""(?:(?<![\w.])[A-Za-z]:[\\/]|(?<![\w.])/(?:tmp|exp|work|out|code|usr|home|root|opt|var|private|"""
                      r"""Users|mnt|srv)/)(?:[^\s:'"\\/]+[\\/])*([^\s:'"\\/]*)""")
LOCATION = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<rest>.*)$")
INTROSPECTION = re.compile(r"^\s*[+]\s+(where|and)\b")
OUR_TEST_FILES = re.compile(r"(^|[\\/\s])(support[\\/]|conftest\.py|test_[A-Za-z0-9_]+\.py|tests[\\/])")


def format_feedback(tests_before_csv, tests_after_csv, repeat_csvs, log_dir) -> str:
    before_path, after_path = Path(tests_before_csv), Path(tests_after_csv)
    try:
        before = compare.read_tests(before_path)
        after = compare.read_tests(after_path)
        repeats = [compare.read_tests(Path(p)) for p in repeat_csvs]
        flaky = compare.read_flaky(before_path.parent / "flaky.txt") if (before_path.parent / "flaky.txt").is_file() \
            else set()
    except compare.Stop as exc:
        raise ValueError(f"feedback.py: {exc}") from exc
    report = compare.compare_tests(before, after, repeats, flaky)
    confirmed = sorted((r["set"], r["case"], r["after"]) for r in report["regressions"] if r["confirmed"])
    if not confirmed:
        return ""
    junit: dict[str, dict] = {}
    entries = []
    for test_set, case, result in confirmed:
        if test_set not in junit:
            junit[test_set] = read_junit(Path(log_dir) / f"{test_set}.junit.xml")
        entries.append((case, details(result, junit[test_set].get(case))))
    return render(entries)


# --- error messages -------------------------------------------------------------------------------------------------

def read_junit(path: Path) -> dict[str, list[tuple[str, ET.Element | None]]]:
    """Case ID -> [(test name, failure/error/skipped element or None)], the test names sorted."""
    if not path.is_file():
        return {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    cases: dict[str, list] = {}
    for tc in root.iter("testcase"):
        name = tc.get("name", "")
        outcome = next((child for child in tc if child.tag in ("failure", "error", "skipped")), None)
        cases.setdefault(case_id(name), []).append((name, outcome))
    return {case: sorted(items, key=lambda item: item[0]) for case, items in cases.items()}


def case_id(test_name: str) -> str:
    """``test_t_loan_05_c[2]`` → ``T-LOAN-05-c`` (the rule of ``scripts/run_tests.py``)."""
    name = test_name.split("[", 1)[0]
    if not name.startswith("test_t_"):
        return test_name
    parts = name[len("test_t_"):].split("_")
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha() and len(parts) >= 3:
        return "T-" + "-".join(p.upper() for p in parts[:-1]) + "-" + parts[-1]
    return "T-" + "-".join(p.upper() for p in parts)


def details(result: str, items: list | None) -> tuple[str, ...]:
    """The detail lines of one case: message lines and the location in lms/, cleaned and limited."""
    if result == "missing":
        return (MISSING,)
    outcomes = [element for _, element in items or [] if element is not None]
    failing = [e for e in outcomes if e.tag in ("failure", "error")]
    if failing:
        element = failing[0]
        lines = message_lines(element)[:MAX_MESSAGE_LINES] or [NO_MESSAGE]
        where = location(element.text or "")
        if where:
            lines.append(f"at {where}")
        prefix = "error during setup or teardown: " if element.tag == "error" else ""
        lines[0] = prefix + lines[0]
        return tuple(clip(line) for line in lines)
    skipped = [e for e in outcomes if e.tag == "skipped"]
    if skipped:
        reason = message_lines(skipped[0])
        return (clip("skipped" + (f": {reason[0]}" if reason else "")),)
    return (NO_MESSAGE,)


def message_lines(element: ET.Element) -> list[str]:
    text = element.get("message") or ""
    if not text.strip():                                   # no message attribute: the "E" lines of the traceback
        text = "\n".join(line[1:].strip() for line in (element.text or "").splitlines() if line.startswith("E "))
    out = []
    for raw in text.splitlines():
        line = clean(raw)
        # our test files are recognized before the paths are shortened (``/exp/run/tests/support/api.py`` → ``api.py``)
        if not line or INTROSPECTION.match(raw) or OUR_TEST_FILES.search(ANSI.sub("", raw)):
            continue
        out.append(line)
    return out


def location(text: str) -> str | None:
    """The deepest traceback line inside lms/ (``lms/loans/service.py:5``), or None."""
    found = None
    for raw in text.splitlines():
        match = LOCATION.match(clean(raw))
        if match and match.group("path").startswith("lms/"):
            found = f"{match.group('path')}:{match.group('line')}"
    return found


def clean(line: str) -> str:
    line = ANSI.sub("", line)
    line = LMS_PATH.sub(lambda m: m.group(1).replace("\\", "/"), line)
    line = ABS_PATH.sub(lambda m: m.group(1), line)
    line = ADDRESS.sub("0x…", line)
    return " ".join(line.split())


def clip(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS - 1] + "…"


# --- output ---------------------------------------------------------------------------------------------------------

def render(entries: list[tuple[str, tuple[str, ...]]]) -> str:
    """Header, merged blocks within the limits, and a last line for the cases that did not fit."""
    shown = entries[:MAX_TESTS]
    groups: dict[tuple[str, ...], list[str]] = {}
    for case, lines in shown:
        groups.setdefault(lines, []).append(case)
    blocks = sorted(((cases, lines) for lines, cases in groups.items()), key=lambda block: block[0][0])
    out = [HEADER]
    listed = 0
    for cases, lines in blocks:
        block = [clip("- " + ", ".join(cases)), *(f"  {line}" for line in lines[:MAX_LINES_PER_TEST - 1])]
        rest = len(entries) - listed - len(cases)
        if len(out) + len(block) + (1 if rest else 0) > MAX_LINES:
            break
        out += block
        listed += len(cases)
    if listed < len(entries):
        out.append(MORE.format(n=len(entries) - listed))
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the W2 feedback of one round.")
    parser.add_argument("--tests-before", required=True, type=Path)
    parser.add_argument("--tests-after", required=True, type=Path)
    parser.add_argument("--repeat", action="append", default=[], type=Path)
    parser.add_argument("--log-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        text = format_feedback(args.tests_before, args.tests_after, args.repeat, args.log_dir)
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
