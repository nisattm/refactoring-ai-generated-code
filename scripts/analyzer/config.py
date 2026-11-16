"""Fixed settings of the analyzer: the frozen smell list, rules, thresholds (ADR 003)."""

from __future__ import annotations

import sys

# Primary smells, one tool or rule each (ADR 003, D8). ``tool`` names the code that finds them.
FROZEN_SMELLS: list[dict[str, str]] = [
    {"id": "S01", "tool": "ast", "rule": "function longer than 45 lines, docstring excluded"},
    {"id": "S02", "tool": "ast", "rule": "plain class with more than 15 methods"},
    {"id": "S03", "tool": "ruff", "rule": "PLR0913"},
    {"id": "S07", "tool": "ruff", "rule": "F401, F841"},
    {"id": "S09", "tool": "ruff", "rule": "PLR0916 (preview run), SIM"},
    {"id": "S10", "tool": "pylint", "rule": "R1702"},
    {"id": "S11", "tool": "ruff", "rule": "PLR2004"},
    {"id": "S18", "tool": "ast", "rule": "import cycles (SCC > 1 at file level, function-level imports included)"},
    {"id": "S19", "tool": "ruff", "rule": "S110, BLE001"},
    {"id": "S20", "tool": "ruff", "rule": "B006"},
    {"id": "S21", "tool": "ruff", "rule": "RET"},
    {"id": "S22", "tool": "ast", "rule": "import outside the library list of LIB-TECH-02"},
    {"id": "S23", "tool": "ruff", "rule": "ANN401, PGH003, cast( calls"},
]
FROZEN_IDS = [s["id"] for s in FROZEN_SMELLS]
NOT_MEASURED = ["S04", "S05", "S08", "S12", "S13", "S14", "S15", "S16", "S17"]

LONG_FUNCTION_LINES = 45
LARGE_CLASS_METHODS = 15
CC_HIGH = 10          # "high" = Radon rank C or worse (CC above 10)
COGNITIVE_HIGH = 15
UNASSIGNED_INVALID_PCT = 5.0

# Ruff, stable run and the preview run that holds only PLR0916 (ADR 003, D10)
RUFF_STABLE_SELECT = "PLR0913,F401,F841,SIM,PLR2004,S110,BLE001,B006,RET,ANN401,PGH003"
RUFF_PREVIEW_SELECT = "PLR0916"
RUFF_COMMON = ["--isolated", "--ignore-noqa", "--no-cache", "--output-format", "json"]
RUFF_SMELL_RULES = {
    "PLR0913": "S03", "F401": "S07", "F841": "S07", "PLR0916": "S09", "PLR2004": "S11",
    "S110": "S19", "BLE001": "S19", "B006": "S20", "ANN401": "S23", "PGH003": "S23",
}
RUFF_SMELL_PREFIXES = {"SIM": "S09", "RET": "S21"}

# Pylint: only R1702 enters the smell total (S10); the others are information (ADR 003)
PYLINT_RULES = ("R1702", "W0718", "R1710", "W0101", "R0401")
PYLINT_SMELL_RULES = {"R1702": "S10"}

JSCPD_ARGS = ["--min-lines", "5", "--min-tokens", "50", "--mode", "mild", "--pattern", "**/*.py", "--no-gitignore"]
JSCPD_MUST_READ = 60   # files above this many (estimated) tokens must be read; 40-60 only warn
JSCPD_MAY_READ = 40

# Libraries allowed by LIB-TECH-02 (+ sub-packages of FastAPI and Pydantic that are imported once)
ALLOWED_THIRD_PARTY = {"fastapi", "starlette", "pydantic_core", "uvicorn", "pydantic", "sqlalchemy", "lms"}
STDLIB = set(sys.stdlib_module_names)

# Excluded from every metric (ADR 003, D1)
EXCLUDED_FILE_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")
EXCLUDED_DIRS = {"__pycache__", "web", "tests"}

ENUM_ROOTS = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"}
SCHEMA_ROOTS = {"BaseModel", "RootModel", "BaseSettings"}
ORM_ROOTS = {"DeclarativeBase", "DeclarativeBaseNoMeta", "MappedAsDataclass"}
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "api_route"}

SUPPRESSION_PATTERNS = {
    "noqa": r"#\s*noqa\b",
    "type_ignore": r"#\s*type:\s*ignore\b",
    "pylint_disable": r"#\s*pylint:\s*disable",
    "jscpd_ignore": r"jscpd:ignore",
}
