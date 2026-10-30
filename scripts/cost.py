"""Cost log for Claude Code runs.

Every ``claude -p ... --output-format json`` call of the experiment returns one
JSON result. This module turns that result into one row of
``metrics/cost-log.csv`` and checks that the run is valid (no error, only the
fixed model). Column definitions: ``docs/cost-tracking.md``.

Command line (inside the container, from the repository root)::

    python scripts/cost.py log result.json --task lms --stage single \
        --run-id lms-single-r1 --repetition 1

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MODEL = "claude-sonnet-5-5"  # decision of 29 October: one model for all runs
DEFAULT_LOG = Path(__file__).resolve().parents[1] / "metrics" / "cost-log.csv"

# USD per 1 million tokens, list prices.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (checked on PRICE_DATE).
# Claude Code's own total_cost_usd uses list prices too ("costBasis": "list"); with this
# table usd_recomputed matched total_cost_usd exactly on docker/claude-sample.json.
PRICE_DATE = "2026-10-29"
PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-5-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_write_5m": 2.50,
        "cache_write_1h": 4.00,
        "cache_read": 0.10,
    },
}

STAGES = {"check", "pilot", "generation", "single", "iterative", "multi-agent"}

COLUMNS = [
    # Required by the Week 3 task file
    "date", "task", "stage", "model", "input_tokens", "output_tokens",
    "usd", "duration_s", "note",
    # Experiment design
    "run_id", "repetition", "round", "role",
    # Tokens (all models and subagents of the call, from modelUsage)
    "cache_write_tokens", "cache_write_1h_tokens", "cache_read_tokens",
    "thinking_tokens", "total_input_tokens",
    # Cost, time and run facts
    "usd_recomputed", "api_duration_s", "num_turns", "subagents_spawned",
    "models_used", "valid", "session_id",
    # Filled by the runner
    "accepted", "tool_s", "wait_s",
    # Environment
    "claude_code_version", "price_date",
]


def _num(obj: Any, key: str) -> int | float:
    value = obj.get(key) if isinstance(obj, Mapping) else None
    return value if isinstance(value, (int, float)) else 0


def usd(tokens: Mapping[str, Any], model: str = MODEL) -> float:
    """Cost in USD from token counts, with the price table above.

    ``tokens`` keys: ``input``, ``output``, ``cache_write_5m``,
    ``cache_write_1h``, ``cache_read`` (missing keys count as 0).
    """
    if model not in PRICES:
        raise KeyError(f"No price for model {model!r}; add it to PRICES")
    p = PRICES[model]
    total = sum(_num(tokens, k) * p[k] for k in p)
    return round(total / 1_000_000, 7)


def summarize(result: Mapping[str, Any], expected_model: str = MODEL) -> dict[str, Any]:
    """Token, cost and validity summary of one Claude Code JSON result."""
    model_usage = result.get("modelUsage") or {}
    models = sorted(model_usage)

    def total(key: str) -> int:
        return sum(_num(m, key) for m in model_usage.values())

    inp, out = total("inputTokens"), total("outputTokens")
    cache_write, cache_read = total("cacheCreationInputTokens"), total("cacheReadInputTokens")

    # 5-minute / 1-hour split exists only in the top-level usage block. Use it when it
    # covers all cache writes; otherwise treat writes as 1-hour (what Claude Code used).
    usage = result.get("usage") or {}
    split = usage.get("cache_creation") or {}
    write_1h, write_5m = _num(split, "ephemeral_1h_input_tokens"), _num(split, "ephemeral_5m_input_tokens")
    split_known = write_1h + write_5m == cache_write and _num(usage, "cache_creation_input_tokens") == cache_write
    if not split_known:
        write_1h, write_5m = cache_write, 0

    problems = []
    if result.get("is_error") or result.get("subtype") != "success":
        status = result.get("api_error_status")
        problems.append("call returned an error" + (f" (HTTP {status})" if status else "")
                        + (f": {result.get('result')}" if result.get("is_error") and result.get("result") else ""))
    if not models:
        problems.append("no modelUsage: model cannot be checked")
    other = [m for m in models if m != expected_model]
    if other:
        problems.append(f"other model used: {', '.join(other)}")

    cost = result.get("total_cost_usd")
    recomputed = usd({"input": inp, "output": out, "cache_write_5m": write_5m,
                      "cache_write_1h": write_1h, "cache_read": cache_read},
                     expected_model) if expected_model in PRICES else ""
    stats = result.get("subagent_stats") or {}
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_write_tokens": cache_write,
        "cache_write_1h_tokens": write_1h if split_known else "",
        "cache_read_tokens": cache_read,
        "thinking_tokens": total("thinkingTokens"),
        "total_input_tokens": inp + cache_write + cache_read,
        "usd": cost if isinstance(cost, (int, float)) else "",
        "usd_recomputed": recomputed,
        "duration_s": round(_num(result, "duration_ms") / 1000, 3),
        "api_duration_s": round(_num(result, "duration_api_ms") / 1000, 3),
        "num_turns": _num(result, "num_turns"),
        "subagents_spawned": _num(stats, "spawned"),
        "models_used": ";".join(models),
        "valid": "false" if problems else "true",
        "session_id": result.get("session_id", ""),
        "note": "; ".join(problems),
    }


def append_row(path: str | Path, **fields: Any) -> dict[str, Any]:
    """Append one row to the cost log and return it. Unknown columns raise an error."""
    unknown = set(fields) - set(COLUMNS)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")
    if fields.get("stage") not in STAGES:
        raise ValueError(f"stage must be one of {sorted(STAGES)}")

    row = {col: "" for col in COLUMNS}
    row["date"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    row["price_date"] = PRICE_DATE
    row.update({k: v for k, v in fields.items() if v is not None})

    path = Path(path)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return row


def log_result(path: str | Path, result: Mapping[str, Any], *, task: str, stage: str,
               model: str = MODEL, note: str = "", **extra: Any) -> dict[str, Any]:
    """Log one Claude Code JSON result. Returns the written row."""
    summary = summarize(result, model)
    summary["note"] = "; ".join(x for x in (summary["note"], note) if x)
    return append_row(path, task=task, stage=stage, model=model, **summary, **extra)


def claude_version() -> str:
    exe = shutil.which("claude")
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip().split(" ")[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log one Claude Code JSON result to the cost log.")
    sub = parser.add_subparsers(dest="command", required=True)
    log = sub.add_parser("log", help="append one result (exit code 2 if the run is invalid)")
    log.add_argument("result", type=Path, help="JSON written by claude -p --output-format json")
    log.add_argument("--log", type=Path, default=DEFAULT_LOG, help="cost log CSV")
    log.add_argument("--task", default="lms")
    log.add_argument("--stage", required=True, choices=sorted(STAGES))
    log.add_argument("--model", default=MODEL)
    for name in ("run-id", "role", "accepted", "note", "claude-code-version"):
        log.add_argument(f"--{name}")
    for name in ("repetition", "round"):
        log.add_argument(f"--{name}", type=int)
    for name in ("tool-s", "wait-s"):
        log.add_argument(f"--{name}", type=float)
    args = parser.parse_args(argv)

    result = json.loads(args.result.read_text(encoding="utf-8"))
    row = log_result(
        args.log, result, task=args.task, stage=args.stage, model=args.model,
        note=args.note or "", run_id=args.run_id, repetition=args.repetition,
        round=args.round, role=args.role, accepted=args.accepted,
        tool_s=args.tool_s, wait_s=args.wait_s,
        claude_code_version=args.claude_code_version or claude_version(),
    )
    print(f"logged: {row['total_input_tokens']} input + {row['output_tokens']} output tokens, "
          f"{row['usd']} USD, {row['duration_s']} s, valid={row['valid']}")
    if row["valid"] != "true":
        print(f"INVALID RUN: {row['note']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
