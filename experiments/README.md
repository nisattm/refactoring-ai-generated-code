# Experiment engine (Week 5, ADR 004)

Runs the Single and Iterative LLM refactoring experiments on a starting commit, measures every result with the Week 4
tools (`scripts/analyze.py`, `scripts/run_tests.py`, `scripts/compare.py`) and records cost and time.

| File | What it does |
| --- | --- |
| `run_single.py` | One Claude Code call → full measurement (feedback and held-out) → comparison with the starting code (W8) |
| `run_iterative.py` | Up to 4 calls in one session; after every call that changed `lms/`: feedback tests, the acceptance rule against the best round so far, revert of a rejected round; at the end the full measurement of the best round, round 1 and the last round (W1, W4, W5) |
| `common.py` | Workspace, measurement tree, the Claude Code call and its checks, run lock, tags, `run.json`, `runs.csv`, cost log |
| `measure.py` | The measurement of one round inside the Docker image (network off): analyzer, tests, the two repetitions of new failures (D18), `compare.py` with every argument, the kind of an API change (W11) |

Inputs from the other Week 5 packages: `make_interface.py`, `prompts/single.md`, `prompts/iterative-round-1.md`,
`prompts/iterative-round-n.md` (optional `prompts/reverted.md` and `prompts/accepted.md` for the fixed sentences of W5)
and `feedback.py` (Aslınur); the verified Claude Code settings in `results/check/week5/flags.md` (Işıl), which go into the
constants at the top of `common.py`.

## Running

From the repository root (Git Bash on Windows, macOS or Linux), with Docker running and the image built:

```bash
python experiments/run_single.py --start-ref ce03f54 --baseline results/baseline/trial/pilot-ce03f54-v2 \
  --tests-modules 1-14 --account exp-1 --run-id pilot-s01 --window-pct 4 --env-file .env

python experiments/run_iterative.py --start-ref ce03f54 --baseline results/baseline/trial/pilot-ce03f54-v2 \
  --tests-modules 1-14 --account exp-1 --run-id pilot-i01 --window-pct 4 --env-file .env
```

- `--window-pct` is the 5-hour window of the account from `/usage`; a run starts only at 10 % or less (W6).
- `--env-file` is passed to `docker run --env-file`; the engine never reads it. The token files of other accounts must
  not be committed (`.env` and `.env.*` are ignored).
- `--account` is a label only (W14: the experiment accounts are not the development accounts).
- `--baseline` must be the measurement of the start ref (its `summary.json` `code_sha`) with the same `--tests-modules`.
- `--dry-run` checks the inputs and prints the Claude Code command; `--help` lists all options.
- The run lock `.run.lock` is held for the whole run (W13); another run or `measure_baseline.sh` waits.

Exit codes: 0 valid run (any outcome) · 1 invalid run, repeat it (W10) · 2 usage error · 3 lock not free ·
5 usage-limit cut.

### Usage-limit cut (W6)

Single: the run is discarded (row with `discarded_limit`); start a new run with a new `--run-id`. Iterative: the state
is saved. If the setup check verified that another account can continue the session:

```bash
python experiments/run_iterative.py --resume-run --run-id pilot-i01 --account exp-2 --window-pct 3 \
  --account-switch-verified --env-file <token file of exp-2>
```

The last round is restored and the interrupted prompt is sent again in the same session. Otherwise
`--discard-run --run-id pilot-i01 --account exp-1` writes the row with `discarded_limit`. The cost of the cut call is in
`usd_lost`.

## What the model sees and what is measured (W3)

The model's folder holds `lms/`, `requirements.txt` and `INTERFACE.md` only (no tests, no `web/`, no full
requirements); its git history is kept outside it. Changes outside `lms/` are undone after every call and counted.
Every result is measured in a copy of the starting project in which only `lms/` is replaced.

The Claude Code call (W9): `--tools Read,Edit,Write,Glob,Grep --disallowedTools Task Agent --safe-mode
--permission-mode dontAsk --output-format stream-json --verbose`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, one
`CLAUDE_CONFIG_DIR` per run, stdin closed. After every call: no subagent, exactly these five tools, no new hidden file,
`CLAUDE.md` or `AGENTS.md`, the expected version and model, no API-key credential. A failed check makes the run invalid.

## Outcomes (W10)

| Outcome | Valid | Meaning |
| --- | --- | --- |
| `success` | yes | `compare.py` `run_successful` is true |
| `no_improvement` | yes | no regression, but no primary metric improved, one got worse, or (Iterative) no round was accepted |
| `no_change` | yes | the model changed nothing in `lms/` |
| `failed` | yes | caused by the model: regression, API change, code that does not load, a metric that cannot be measured, tests that time out again after one repetition |
| `invalid` | no | infrastructure: wrong tools, version or model, a subagent, a hidden file, test files changed, a call error; the run is repeated |
| `discarded_limit` | no | usage-limit cut (W6) |

## Output

`results/experiments/<approach>/<run-id>/run.json` (calls, rounds, decisions, code SHAs, image, version, account,
times, cost: raw value and difference per call, W16), one row per run in `results/experiments/runs.csv`, one row per
call in `metrics/cost-log.csv`, and the tag `exp/<approach>/<run-id>/r<k>` for every round (a commit on top of the
start ref in which only `dataset/lms/generated/lms` differs, W12). Push the tags with
`git push origin 'refs/tags/exp/*'`. The raw call logs and the detail CSVs are not committed (ADR 003 rule).

## Tests

`scripts/tests/test_experiments_*.py`: a fake Claude (`scripts/tests/fixtures/experiments/fake_claude.py`) that edits
files and prints a stream-json log, and a fake measurement step; they cover accept, reject and revert, regression
feedback, API change, subagent, limit cut (discard and resume), changes outside `lms/`, hidden files and the stop rules.
`measure.py` is tested with stub scripts; the real tools run in the pilot.
