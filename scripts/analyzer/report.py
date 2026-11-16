"""CSV and JSON output with the versioned schema (ADR 003, D14, D25): sorted rows, 4 decimals, UTF-8."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from . import SCHEMA_VERSION

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"


def load_schema() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if schema["schema_version"] != SCHEMA_VERSION:
        raise ValueError("schema.json and SCHEMA_VERSION differ")
    return schema


def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_csv(out: Path, name: str, rows: list[dict], label: str, schema: dict) -> None:
    specs = schema["files"][name]["columns"]
    columns = [c["name"] for c in specs]
    is_float = {c["name"] for c in specs if c["type"] == "float"}
    with (out / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            row = {"run_label": label, "schema_version": SCHEMA_VERSION, **row}
            unknown = set(row) - set(columns)
            if unknown:
                raise ValueError(f"{name}: columns not in schema.json: {sorted(unknown)}")
            # a float column always has 4 decimals, also where a tool gave the integer 0
            writer.writerow([fmt(float(row[c]) if c in is_float and row.get(c) is not None else row.get(c))
                             for c in columns])


def round_floats(value, digits: int = 4):
    """Floats of a nested structure rounded for ``summary.json``."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, digits) for v in value]
    return value


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(round_floats(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flatten(prefix: str, value) -> list[tuple[str, object]]:
    """Scalars of a nested dict as (``a.b``, value) pairs, for project.csv."""
    if isinstance(value, dict):
        return [item for k in sorted(value) for item in flatten(f"{prefix}.{k}" if prefix else str(k), value[k])]
    if isinstance(value, (list, tuple)):
        return [(prefix, len(value))]
    return [(prefix, value)]
