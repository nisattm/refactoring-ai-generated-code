"""Checks the LMS test conventions (dataset/lms/tests/README.md) for every module that has a
case table: each case has exactly one test in the set the split rule gives it, the test name
matches the case ID, the first docstring line starts with the case ID, and no test is missing
from the table."""

import ast
import re
from collections import Counter
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2] / "dataset" / "lms" / "tests"
CASE_RE = re.compile(r"^T-([A-Z0-9]+)-(\d{2})-([a-z])$")
SETS = {"feedback": "feedback", "held-out": "heldout", "heldout": "heldout"}


def _rows(md: Path) -> list[dict]:
    rows = []
    for line in md.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].startswith("T-"):
            rows.append(dict(zip(("id", "req", "type", "input", "expected", "set"), cells, strict=True)))
    return rows


def _tests(path: Path) -> dict[str, str]:
    """Test function name → first docstring line."""
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: (ast.get_docstring(node) or "").splitlines()[0] if ast.get_docstring(node) else ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _expected_set(case_id: str, counts: Counter) -> str:
    area, num, letter = CASE_RE.match(case_id).groups()
    if counts[(area, num)] == 1:
        return "feedback" if int(num) % 2 else "heldout"
    return "feedback" if (ord(letter) - ord("a")) % 2 == 0 else "heldout"


def _modules():
    return sorted(p.stem for p in (TESTS / "cases").glob("*.md")) if (TESTS / "cases").is_dir() else []


def test_case_tables_match_test_files():
    problems = []
    for module in _modules():
        rows = [r for r in _rows(TESTS / "cases" / f"{module}.md") if r["set"].lower() in SETS]
        tests = {s: _tests(TESTS / s / f"test_{module}.py") for s in ("feedback", "heldout")}
        ids = [r["id"] for r in rows]
        problems += [f"{module}: duplicate case {i}" for i, n in Counter(ids).items() if n > 1]
        regular = [i for i in ids if CASE_RE.match(i)]
        counts = Counter(CASE_RE.match(i).groups()[:2] for i in regular)
        for row in rows:
            cid, where = row["id"], SETS[row["set"].lower()]
            name = "test_" + cid.lower().replace("-", "_")
            if CASE_RE.match(cid) and where != _expected_set(cid, counts):
                problems.append(f"{module}: {cid} is in {where}, split rule says {_expected_set(cid, counts)}")
            if name not in tests[where]:
                problems.append(f"{module}: {cid} has no {name} in {where}/test_{module}.py")
            elif re.split(r"[\s(:]", tests[where][name], maxsplit=1)[0] != cid:
                problems.append(f"{module}: first docstring line of {name} is {tests[where][name]!r}")
            if name in tests["heldout" if where == "feedback" else "feedback"]:
                problems.append(f"{module}: {name} is in both sets")
        listed = {"test_" + i.lower().replace("-", "_") for i in ids}
        for s, found in tests.items():
            problems += [f"{module}: {s}/test_{module}.py:{n} is not in the case table" for n in found if n not in listed]
    assert not problems, "\n".join(problems)


def test_letters_have_no_gaps():
    problems = []
    for module in _modules():
        letters: dict[tuple[str, str], list[str]] = {}
        for row in _rows(TESTS / "cases" / f"{module}.md"):
            m = CASE_RE.match(row["id"])
            if m:
                letters.setdefault(m.groups()[:2], []).append(m.group(3))
        for key, found in letters.items():
            if sorted(found) != [chr(ord("a") + i) for i in range(len(found))]:
                problems.append(f"{module}: T-{key[0]}-{key[1]} letters {sorted(found)}")
    assert not problems, "\n".join(problems)
