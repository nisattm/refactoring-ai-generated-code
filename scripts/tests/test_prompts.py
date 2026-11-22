"""Checks of the prompts in experiments/prompts/ (ADR 004: prompts, W1, W4, W5; Week 6: Multi-Agent prompts)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "experiments" / "prompts"
sys.path.insert(0, str(REPO / "experiments"))
import common  # noqa: E402

BEHAVIOR = ("Do not change the externally visible behavior of the code (REST API and the fixed service interface); "
            "only improve its structure. Do not modify tests.")
MAIN = ["single.md", "iterative-round-1.md", "iterative-round-n.md"]
# Quality hints, smell names and metric words that must never appear (ADR 004, prompts; approaches.md)
FORBIDDEN = ["clean", "maintainab", "readab", "quality", "complex", "duplicat", "smell", "metric", "cyclomatic",
             "cognitive", "coupling", "cohesion", "long method", "god class", "magic number", "dead code", "nesting",
             "best practice", "simplif", "solid", "dry", "pep", "lint", "ruff", "radon", "pylint", "jscpd"]


def read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_round_1_is_byte_identical_to_single():
    assert (PROMPTS / "single.md").read_bytes() == (PROMPTS / "iterative-round-1.md").read_bytes()


@pytest.mark.parametrize("name", MAIN)
def test_fixed_parts(name):
    text = read(name)
    assert BEHAVIOR in text
    assert common.DONE_MARKER in text
    assert "only files inside lms/" in text


@pytest.mark.parametrize("name", MAIN + ["reverted.md", "accepted.md"])
def test_no_quality_hints(name):
    words = re.findall(r"[a-z]+(?: [a-z]+)?", read(name).lower().replace(BEHAVIOR.lower(), ""))
    text = " ".join(words)
    found = [w for w in FORBIDDEN if re.search(rf"\b{re.escape(w)}", text)]
    assert not found, f"{name} contains {found}"


@pytest.mark.parametrize("name", MAIN)
def test_only_known_placeholders(name):
    for placeholder in re.findall(r"\{[a-z_]+\}", read(name)):
        assert placeholder in common.PLACEHOLDERS


def test_single_and_round_1_have_no_placeholders():
    assert not re.search(r"\{[a-z_]+\}", read("single.md"))


def test_round_n_has_every_placeholder():
    text = read("iterative-round-n.md")
    assert all(p in text for p in common.PLACEHOLDERS)


def test_fixed_sentences_are_neutral_and_one_line():
    reverted = common.fixed_sentence(PROMPTS, "reverted.md", "x")
    accepted = common.fixed_sentence(PROMPTS, "accepted.md", "x")
    assert reverted == "Your previous changes were reverted. Read the files again before you continue."
    assert accepted == "Your previous changes were kept."
    for sentence in (reverted, accepted):
        assert "\n" not in sentence and "because" not in sentence.lower()


def test_round_n_filled_like_the_engine_leaves_no_placeholder():
    text = common.fill_prompt(read("iterative-round-n.md"), round=2, max_rounds=common.MAX_CALLS,
                              feedback="T-X-01-a\n  AssertionError", reverted="Your previous changes were reverted.")
    assert not re.search(r"\{[a-z_]+\}", text)
    assert f"review 2 of at most {common.MAX_CALLS}" in text


# --- Multi-Agent prompts (Week 6, experiments/prompts/multiagent/) ------------------------------------------------
import run_multiagent  # noqa: E402

MULTI = PROMPTS / "multiagent"
ROLE_FILES = [f"{role}.md" for role in run_multiagent.ROLES]
INTRO = read("single.md").split("\n\n")[0]


def read_multi(name: str) -> str:
    return (MULTI / name).read_text(encoding="utf-8")


def test_multiagent_files_are_the_roles_and_the_orchestrator():
    assert sorted(p.name for p in MULTI.iterdir()) == sorted(ROLE_FILES + ["orchestrator.md"])


@pytest.mark.parametrize("name", ROLE_FILES + ["orchestrator.md"])
def test_multiagent_same_task_and_rules_as_single(name):
    text = read_multi(name)
    assert text.count(INTRO) == 1
    assert BEHAVIOR in text


@pytest.mark.parametrize("name", ["orchestrator.md", "refactoring.md"])
def test_multiagent_only_lms_is_changed(name):
    assert "Change only files inside lms/." in read_multi(name)


@pytest.mark.parametrize("name", ["analyzer.md", "reviewer.md"])
def test_multiagent_read_only_roles_change_nothing(name):
    assert "Do not change any file." in read_multi(name)


@pytest.mark.parametrize("name", ROLE_FILES + ["orchestrator.md"])
def test_multiagent_no_quality_hints(name):
    words = re.findall(r"[a-z]+(?: [a-z]+)?", read_multi(name).lower().replace(BEHAVIOR.lower(), ""))
    text = " ".join(words)
    found = [w for w in FORBIDDEN if re.search(rf"\b{re.escape(w)}", text)]
    assert not found, f"{name} contains {found}"


def test_multiagent_orchestrator_placeholders():
    text = read_multi("orchestrator.md")
    assert sorted(set(re.findall(r"\{[a-z_]+\}", text))) == sorted(common.MULTIAGENT_PLACEHOLDERS)
    assert common.DONE_MARKER in text
    for role in run_multiagent.ROLES:
        assert role in text


@pytest.mark.parametrize("name", ROLE_FILES)
def test_multiagent_roles_have_no_placeholders(name):
    assert not re.search(r"\{[a-z_]+\}", read_multi(name))


def test_multiagent_orchestrator_filled_like_the_engine():
    command = run_multiagent.TEST_COMMAND
    text = common.fill_prompt(read_multi("orchestrator.md"), test_command=command,
                              max_refactoring_calls=run_multiagent.MAX_REFACTORING_CALLS,
                              max_test_runs=run_multiagent.MAX_TEST_RUNS)
    assert not re.search(r"\{[a-z_]+\}", text)
    assert f"\n{command}\n" in text
    assert f"at most {run_multiagent.MAX_REFACTORING_CALLS} times" in text


def test_multiagent_roles_load_like_the_engine():
    agents = json.loads(run_multiagent.agents_json(MULTI))
    assert sorted(agents) == sorted(run_multiagent.ROLES)
    for role, agent in agents.items():
        assert agent["description"] and "\n" not in agent["description"]
        assert agent["prompt"].startswith(INTRO)
        assert "---" not in agent["prompt"]
