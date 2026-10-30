"""Generate cases/<module>.md and feedback/heldout test files from one case list.

Usage: python gen.py <cases_module.py> <tests_dir>
The cases module defines MODULE (file stem), TITLE, HEADER (test file imports) and CASES:
a list of dicts with id, req, type, input, expected, code (None for static cases).
"""
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path


def split_set(case, counts):
    if case["type"] == "Static" or case["code"] is None:
        return "static"
    cid = case["id"]
    m = re.fullmatch(r"T-([A-Z0-9]+)-(\d+)-([a-z])", cid)
    if m:
        num = int(m.group(2))
        letter = m.group(3)
        if counts[case["req"]] == 1:
            return "feedback" if num % 2 == 1 else "heldout"
        return "feedback" if (ord(letter) - ord("a")) % 2 == 0 else "heldout"
    m = re.fullmatch(r"T-(?:E2E|P)-(\d+)", cid)
    if m:
        return "feedback" if int(m.group(1)) % 2 == 1 else "heldout"
    raise ValueError(f"bad case id {cid}")


LABELS = {"heldout": "held-out"}  # set name as written in the case tables


def main(spec_path, tests_dir):
    spec = importlib.util.spec_from_file_location("cases_spec", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = mod.CASES
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case id"
    counts = defaultdict(int)
    for c in cases:
        if c["type"] != "Static" and c["code"] is not None:
            counts[c["req"]] += 1
    for c in cases:
        c["set"] = split_set(c, counts)
    tests_dir = Path(tests_dir)
    rows = ["| ID | Requirement | Type | Input | Expected | Set |", "| --- | --- | --- | --- | --- | --- |"]
    for c in cases:
        rows.append(f"| {c['id']} | {c['req']} | {c['type']} | {c['input']} | {c['expected']} | {LABELS.get(c['set'], c['set'])} |")
    by_set = defaultdict(int)
    for c in cases:
        by_set[c["set"]] += 1
    reqs = sorted({c["req"] for c in cases})
    md = [f"# Test cases: {mod.TITLE}", "",
          f"Generated from one case list; {len(cases)} cases for {len(reqs)} requirements "
          f"(feedback {by_set['feedback']}, held-out {by_set['heldout']}, static {by_set['static']}). "
          "Split rule: [`../README.md`](../README.md#feedback--held-out-split).", "", *rows, ""]
    (tests_dir / "cases").mkdir(parents=True, exist_ok=True)
    (tests_dir / "cases" / f"{mod.MODULE}.md").write_text("\n".join(md), encoding="utf-8")
    for set_name in ("feedback", "heldout"):
        body = [f'"""{set_name.capitalize()} tests: {mod.TITLE}. Generated from cases/{mod.MODULE}.md."""', mod.HEADER.strip(), ""]
        for c in cases:
            if c["set"] != set_name:
                continue
            fn = "test_" + c["id"].lower().replace("-", "_")
            code = c["code"].strip("\n")
            code = re.sub(r"^def TEST\(", f"def {fn}(", code, count=1, flags=re.M)
            assert code.startswith(f"def {fn}("), c["id"]
            lines = code.split("\n")
            exp = c["expected"].replace("`", "").replace('\\"', "'").replace('"', "'")
            doc = f'    """{c["id"]} ({c["req"]}): {exp}"""'
            lines.insert(1, doc)
            body.append("")
            body.extend(lines)
            body.append("")
        d = tests_dir / set_name
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").touch()
        (d / f"test_{mod.MODULE}.py").write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    print(mod.MODULE, len(cases), dict(by_set), "requirements:", len(reqs))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
