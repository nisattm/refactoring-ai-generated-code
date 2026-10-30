"""SHA-256 hashes of the test files (test protection, docs/testing.md).

A run is invalid if any test file changed, appeared or disappeared between the
hash taken before the run and the one taken after it.

    python scripts/test_hashes.py record dataset/lms/tests hashes.json
    python scripts/test_hashes.py verify dataset/lms/tests hashes.json   # exit 1 on a change

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Created by Python and pytest while running; not test files.
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".hypothesis"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file()
        and not IGNORED_DIRS.intersection(p.relative_to(root).parts)
        and p.suffix not in IGNORED_SUFFIXES
    )


def compute(root: str | Path) -> dict[str, str]:
    """Map of relative path (``/`` separators) → SHA-256 hex digest."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Test folder not found: {root}")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in _files(root)}


def compare(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    """Changed, added and removed files (empty lists when nothing changed)."""
    return {
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
    }


def is_unchanged(diff: dict[str, list[str]]) -> bool:
    return not any(diff.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("record", "verify"):
        p = sub.add_parser(name)
        p.add_argument("tests", type=Path, help="test folder, e.g. dataset/lms/tests")
        p.add_argument("hashes", type=Path, help="JSON file with the hashes")
    args = parser.parse_args(argv)

    current = compute(args.tests)
    if args.command == "record":
        args.hashes.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"recorded {len(current)} files")
        return 0

    diff = compare(json.loads(args.hashes.read_text(encoding="utf-8")), current)
    if is_unchanged(diff):
        print(f"OK: {len(current)} test files unchanged")
        return 0
    for kind, paths in diff.items():
        for path in paths:
            print(f"{kind.upper():8} {path}")
    print("TEST FILES CHANGED: the run is invalid", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
