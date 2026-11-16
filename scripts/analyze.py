"""Code Quality Analyzer entry point (ADR 003, docs/analyzer.md).

    python scripts/analyze.py --code <folder with lms/> --out <folder> [--label <name>] [--with-secondary]

Exit codes: 0 done · 2 usage error · 4 a tool did not run or its file set did not match.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyzer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
