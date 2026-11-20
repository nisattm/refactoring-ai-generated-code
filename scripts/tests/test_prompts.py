"""Checks of the Week 5 prompts in experiments/prompts/ (ADR 004: prompts, W1, W4, W5)."""

from __future__ import annotations

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
