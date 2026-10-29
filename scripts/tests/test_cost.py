import copy
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cost

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "docker" / "claude-sample.json").read_text(encoding="utf-8"))
M = "claude-sonnet-5-5"


def test_price_table_reproduces_claude_code_cost():
    # Real result from check-claude (29 Oct 2026): our list prices give Claude Code's own estimate
    s = cost.summarize(SAMPLE)
    assert s["usd_recomputed"] == pytest.approx(SAMPLE["total_cost_usd"], abs=1e-7)


def test_summarize_sample():
    s = cost.summarize(SAMPLE)
    assert s["input_tokens"] == 2
    assert s["output_tokens"] == 4
    assert s["cache_write_tokens"] == 5456
    assert s["cache_write_1h_tokens"] == 5456
    assert s["cache_read_tokens"] == 11227
    assert s["total_input_tokens"] == 2 + 5456 + 11227
    assert s["duration_s"] == 2.3
    assert s["api_duration_s"] == 1.465
    assert s["models_used"] == M
    assert s["valid"] == "true"
    assert s["note"] == ""


def test_usd_plain():
    assert cost.usd({"input": 1_000_000, "output": 1_000_000}) == 12.0
    assert cost.usd({"cache_write_5m": 1_000_000, "cache_write_1h": 1_000_000,
                     "cache_read": 1_000_000}) == pytest.approx(6.6)


def test_unknown_model_price_raises():
    with pytest.raises(KeyError):
        cost.usd({"input": 1}, "unknown-model")


def test_error_result_is_invalid():
    bad = copy.deepcopy(SAMPLE)
    bad.update(is_error=True, subtype="success", api_error_status=401, modelUsage={})
    s = cost.summarize(bad)
    assert s["valid"] == "false"
    assert "HTTP 401" in s["note"]
    assert "no modelUsage" in s["note"]


def test_other_model_makes_run_invalid():
    mixed = copy.deepcopy(SAMPLE)
    mixed["modelUsage"]["claude-haiku-5-5"] = {"inputTokens": 10, "outputTokens": 5}
    s = cost.summarize(mixed)
    assert s["valid"] == "false"
    assert "claude-haiku-5-5" in s["note"]
    assert s["input_tokens"] == 12           # tokens of all models are summed


def test_missing_split_counts_writes_as_1h():
    r = copy.deepcopy(SAMPLE)
    r["modelUsage"][M]["cacheCreationInputTokens"] = 6000   # e.g. subagent writes not in usage
    s = cost.summarize(r)
    assert s["cache_write_1h_tokens"] == ""
    assert s["usd_recomputed"] == pytest.approx(cost.usd(
        {"input": 2, "output": 4, "cache_write_1h": 6000, "cache_read": 11227}))


def test_log_result_and_header(tmp_path):
    log = tmp_path / "cost-log.csv"
    cost.log_result(log, SAMPLE, task="lms", stage="check", run_id="check-1", note="first")
    cost.log_result(log, SAMPLE, task="lms", stage="single", repetition=1)
    rows = list(csv.DictReader(log.open(encoding="utf-8")))
    assert len(rows) == 2
    assert list(rows[0]) == cost.COLUMNS
    assert rows[0]["note"] == "first"
    assert rows[0]["price_date"] == cost.PRICE_DATE
    assert rows[1]["valid"] == "true"


def test_append_row_rejects_unknown_column_and_stage(tmp_path):
    log = tmp_path / "cost-log.csv"
    with pytest.raises(ValueError):
        cost.append_row(log, stage="single", tokens=5)
    with pytest.raises(ValueError):
        cost.append_row(log, stage="refactor")


def test_cli_exit_code(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(SAMPLE), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**SAMPLE, "is_error": True}), encoding="utf-8")
    log = tmp_path / "log.csv"
    args = ["log", "--log", str(log), "--stage", "check", "--claude-code-version", "2.1.308"]
    assert cost.main([*args[:1], str(good), *args[1:]]) == 0
    assert cost.main([*args[:1], str(bad), *args[1:]]) == 2
    rows = list(csv.DictReader(log.open(encoding="utf-8")))
    assert [r["valid"] for r in rows] == ["true", "false"]   # invalid runs are logged too
    assert rows[0]["claude_code_version"] == "2.1.308"


def test_template_header_matches_columns():
    header = (ROOT / "metrics" / "cost-log.csv").read_text(encoding="utf-8").strip().split(",")
    assert header == cost.COLUMNS
