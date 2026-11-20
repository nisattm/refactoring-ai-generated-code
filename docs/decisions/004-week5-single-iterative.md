# 004 – Week 5: Single and Iterative LLM runs

**Date:** 2026-11-20
**Status:** Proposed (draft for Nisa's approval). Decisions W1–W16 were agreed on 2026-11-17; the clarifications marked **(clarified 2026-11-20)** were found while writing this record and approved in the review of the draft; W9, W10 and W16 were completed with the results of the setup check (package B).

## Context

Week 5 builds the Single LLM and Iterative LLM systems, their standard prompts and the rules that keep the behavior of the code, and pilots both approaches ([`../plan.md`](../plan.md)). The Week 5 plan of 17 November (Nisa) was reviewed by five independent reviewers and discussed in two rounds; its decisions W1–W16 are recorded here. The work is split into four packages that do not wait for each other: A engine (Fatima), B setup check and pilot (Işıl), C decisions, prompts and feedback (Aslınur), D characterization tests (Şevval, issue #115). The packages only rely on the contracts in "Interfaces between packages" below.

Inherited from Week 4 and not changed here: the starting code `v0-ai-baseline` = `3bd1412` (30,260 SLOC, 29 modules), its frozen measurement `results/baseline/final/v0-ai-baseline/`, the analyzer, `compare.py`, `run_tests.py` and the success rule of [`003`](003-analyzer-and-success-rule.md) (D17–D21). The pilot code is `ce03f54` (6,449 SLOC, modules 1–14).

The engine of package A (`experiments/`, PR #125) was merged before this record and already refers to W1–W16; this record is the reference it points to.

## Decision

### Rules of the runs

| ID | Topic | Decision |
| --- | --- | --- |
| W1 | "Keep the best round" | The rule of ADR 003 stays: a rejected round is undone and the best accepted round is kept. For Iterative three results are reported: the **selected best round (primary)**, the last round and round 1. Round 1 uses the same prompt as Single, so it also counts as an additional Single sample. In Week 6 the same outer rule is applied to Multi-Agent. Selecting the best round is reported as a threat to validity. |
| W2 | Feedback between rounds | Test ID and a short error message: **at most 6 lines per test, 60 lines in total, 15 tests**. Only regressions confirmed in two repetitions (D18). The output is sorted and cleaned (temporary paths and lines of our test files removed, identical errors merged) and comes from one shared script, `experiments/feedback.py`. **Metrics are never shown.** This replaces the decision of 16 November that the model sees only the IDs of the failing tests (see "Correction of `approaches.md`"). |
| W3 | What the model sees | Its folder contains only `lms/`, `requirements.txt` and `INTERFACE.md` (sections 1–4 of the requirements, verbatim). Not present: the full requirements, `web/`, the model's own tests, `WEB_INTERFACE.md`, our tests. Tests always run in the starting project with only `lms/` replaced. Changes outside `lms/` are undone and counted. |
| W4 | Stopping (Iterative) | After call 1 at least one "re-evaluate" call is required; **at most 4 calls**. The run stops when the last call left no regression and the model wrote `REFACTORING_DONE`, or when **3 rounds changed code**. A call that changes nothing in `lms/` is not a round. |
| W5 | Rejected round | The next prompt gets a fixed, neutral sentence: the previous changes were reverted, read the files again. The reason is not given. An accepted round also gets a fixed sentence. The exact texts are approved with the prompt PR (package C). |
| W6 | Usage-limit cut | Single: the run is discarded and done again. Iterative: the last round is restored and the interrupted prompt is sent again with another account, **only if** the setup check verified that another account can continue the session; otherwise the run is discarded. The lost cost is kept in its own column. A run starts only when the account's 5-hour window is at most 10 % used. |
| W7 | Repetitions | At least **5 runs per approach** (8 if the budget allows). Four runs cannot give statistical significance. |
| W8 | Pilot | On `ce03f54`: 2 Single runs and 1 Iterative run (its round 1 measured in full); on the final code one Single "scale trial" that is not counted. Recorded: time, tokens, share of the usage window, files changed and read, rejection reasons, length of the feedback text. |
| W9 | Claude Code settings | `--tools Read,Edit,Write,Glob,Grep`, `--disallowedTools Task Agent`, `--safe-mode`, `--permission-mode dontAsk`, `--output-format stream-json --verbose`, background tasks off, one session folder per run, stdin from `/dev/null`. **(setup check)** Also `--allowedTools Read Edit Write Glob Grep`: in `dontAsk` mode `--tools` only offers the tools, and a tool that is not also allowed is denied. After every call: 0 subagents, the tool list is exactly these five, `permission_denials` is empty, no `Edit`/`Write` to `CLAUDE.md`, `AGENTS.md` or a hidden file anywhere, taken from the stream (so a file written and removed in the same call is caught: `--safe-mode` does not stop it, and a resumed call follows `CLAUDE.md`), the expected version and credential source. Such a run is invalid (W10); the file is not deleted silently. Source: `results/check/week5/flags.md` (package B). |
| W10 | Outcomes | **Failed** (caused by the model, not repeated): regression, API change, code that does not load, a metric that cannot be measured, a test set that times out again after one repetition. **Invalid** (infrastructure, repeated): wrong model, version or image, a subagent started, test files changed, a denied tool call, a model-written `CLAUDE.md`/`AGENTS.md`/hidden file, a call error or timeout. Counts are reported per approach. |
| W11 | API check | The exact OpenAPI hash (D21) decides. For every rejection the normalized difference is also recorded: descriptions only, schema names only (for example a moved class), or a real API change. |
| W12 | Storing the code | Every round and the end of every run is a tag `exp/<approach>/<run>/r<k>` on a commit on top of the start ref in which only `lms/` differs. Expected growth of the repository 6–40 MB. Tags are protected by a ruleset. **(clarified 2026-11-20)** The commit sits on the start ref of the run: `v0-ai-baseline` for the experiments, `ce03f54` for the pilot. |
| W13 | Run lock | In Week 5 `.run.lock` is held for the whole run. The pilot measures the duration of the feedback tests with and without a parallel Claude call; if it does not change, the lock is released during the Claude call from Week 6 on. |
| W14 | Accounts | An account used for development is not used for experiments at the same time. The order of the runs (approach, account, time) is fixed in advance and shuffled. |
| W15 | Starting measurements | The pilot code is measured again with the current analyzer (`results/baseline/trial/pilot-ce03f54-v2/`). When the characterization tests exist, the final code is measured again into a new folder (`results/baseline/final/v0-ai-baseline-ct/`); the frozen measurement stays as it is. The real experiments are compared with the new folder, the pilot with the pilot measurement. |
| W16 | Cost | **Verified by the setup check:** `total_cost_usd` and the `modelUsage` tokens are cumulative in a resumed session. The cost log and `runs.csv` hold each call's share (this total minus the previous total of the same session); the cumulative values stay in `run.json`. The `rate_limit_event` of every call is kept in `run.json`. One row per run in `results/experiments/runs.csv` (input of the Week 7 statistics). |

The success rule of ADR 003 does not change: a run is successful if no test that passed at the start fails, no primary metric is worse, at least one improved and the OpenAPI schema is unchanged.

### Prompts (package C)

Files in `experiments/prompts/`: `single.md`, `iterative-round-1.md`, `iterative-round-n.md`, and optionally `reverted.md` and `accepted.md` for the fixed sentences of W5.

- Every prompt contains the fixed behavior sentence verbatim: *"Do not change the externally visible behavior of the code (REST API and the fixed service interface); only improve its structure. Do not modify tests."*
- Scope: only `lms/`. The end marker is `REFACTORING_DONE`.
- No quality hint, no smell name and no metric word. The analyzer output is never shown to the model ([`../approaches.md`](../approaches.md), decision of 16 November: the approaches stay equal and the study measures what the model finds itself).
- **(clarified 2026-11-20) `iterative-round-1.md` is byte-identical to `single.md` and has no placeholders.** W1 counts round 1 as a Single sample, and the engine does not fill placeholders in `single.md`; a round number in round 1 would make the two prompts differ. The round information is therefore only in `iterative-round-n.md`. The engine is not changed.
- **(clarified 2026-11-20) `{max_rounds}` is 4.** The package C task said "round k / at most 3", but the engine fills `{round}` with the number of the call (2–4) and `{max_rounds}` with the call limit of W4 (`MAX_CALLS` = 4); with 3, "round 4 of at most 3" could appear. The prompt therefore says "review {round} of at most {max_rounds}". The limit of 3 code-changing rounds is enforced by the engine and is not announced to the model.

### Feedback (W2, package C)

- Only **confirmed regressions** are shown: a feedback case that passed at the start and is `failed`, `error`, `skipped` or `missing` after the round, and that does not pass in either of the two repetitions (D18, ADR 003 addendum point 5).
- Not shown: held-out cases, metrics, cases that already failed at the start (for example T-INV-20-a), flaky cases of the baseline (`flaky.txt`), regressions that passed in a repetition, and the OpenAPI result.
- **Consequence (accepted by design):** a round rejected only because a primary metric got worse or because the OpenAPI schema changed gets an empty feedback text; the model only sees the fixed "reverted" sentence. The pilot records how often this happens (W8, rejection reasons).

## Interfaces between packages

Written on day 1; a change needs the approval of the owner and of Nisa.

| From | To | Contract |
| --- | --- | --- |
| C (Aslınur) | A (Fatima) | `python experiments/make_interface.py --requirements <path> --out <path>`: writes sections 1–4 of the requirements document verbatim; exit code not 0 on any error. |
| C (Aslınur) | A (Fatima) | Prompt files `experiments/prompts/single.md`, `iterative-round-1.md`, `iterative-round-n.md` (optional `reverted.md`, `accepted.md`). Placeholders: `{round}`, `{max_rounds}`, `{feedback}`, `{reverted}`. The engine only fills the placeholders and never changes the text. |
| C (Aslınur) | A (Fatima); Multi-Agent in Week 6 | `experiments/feedback.py`: `format_feedback(tests_before_csv, tests_after_csv, repeat_csvs, log_dir) -> str`. Only regressions confirmed in two repetitions; empty text if there is none; the same input always gives the same output. **(clarified 2026-11-20)** The engine passes the baseline `tests.csv` (both sets) as `tests_before_csv`, the feedback-only `tests.csv` of the round as `tests_after_csv`, the `tests.csv` of the repetitions (0–2 files) and the round's test folder as `log_dir`. Cases missing from `tests_after_csv` because they belong to the held-out set are not regressions; the flaky list is read from `flaky.txt` next to `tests_before_csv` if it exists. |
| B (Işıl) | A (Fatima) | `results/check/week5/flags.md`: the verified settings (flags, environment variables, JSON fields to check) and the answer to "does continuing on another account work". The engine defaults are updated from it. |
| A (Fatima) | B (Işıl) | `python experiments/run_single.py --start-ref <ref> --baseline <folder> --tests-modules <range> --account <label> --run-id <id>`; `run_iterative.py` with the same options. Output `results/experiments/<approach>/<run>/run.json` and one row in `runs.csv`. |
| D (Şevval) | everyone | New tests are added next to the existing ones; new starting measurement `results/baseline/final/v0-ai-baseline-ct/`. The real experiments are compared with it, the pilot with the pilot measurement. |

The existing tools (`analyze.py`, `compare.py`, `run_tests.py`, `cost.py`, `measure_baseline.sh`) are used with their Week 4 contract ([`../analyzer.md`](../analyzer.md)); a missing feature is added in a small, separate PR.

## Correction of `approaches.md`

`approaches.md` contradicted itself: the fairness section says the feedback is "failing test name and error message, at most N lines", while the open-questions table (decision of 16 November) says the model "only gets the IDs of the failing feedback tests". W2 settles it: **test ID and a short error message**, with the limits of W2 (N = 6 lines per test, 60 in total, 15 tests). The table row is corrected in the same PR as this record.

## Note for the generation log

In generation steps 25 and 26 Claude Code started 6 and 8 subagents on its own (all Sonnet 5.5, all completed); all other steps used 0 (the discarded first attempt of step 25, `step-25-invalid-1`, used 7). The generation was allowed to do this; W9 prevents it in the refactoring runs. The note is added to `dataset/lms/generation-log.md` in the same PR as this record.

## Alternatives considered

- Feedback with test IDs only (decision of 16 November): replaced by W2 on 2026-11-17. *(Rationale not written in the plan; to confirm with Nisa: with W3 the model cannot read the full requirements, so an ID alone gives it little to act on.)*
- Showing the analyzer output or naming smells in the prompt: rejected; the approaches would no longer measure what the model finds itself.
- Fewer than 5 runs per approach: rejected (W7).
- Continuing a cut Iterative run on another account without a verified setup check: rejected (W6).

## Consequences

- `approaches.md` (feedback format W2 in three places, Iterative stopping rule W4, link to this record) and `generation-log.md` (subagent note) are changed in the same PR as this record; the prompts, `make_interface.py` and `feedback.py` with `scripts/tests/test_feedback.py` follow in separate PRs (package C).
- After the pilot an addendum records the post-pilot decisions: number of repetitions, line limits of W2, lock rule of W13, limit-cut rule.
- W9, W10 and W16 contain the results of the setup check of 20 November (`--allowedTools`, denied calls, model-written `CLAUDE.md`, cumulative cost). The engine changes for them are made in package A's setup-check-fixes PR, not in this record's PR.
- Still open in the setup check: the deliberate limit cut and continuing on another account (W6). Until the second is verified, a cut Iterative run is discarded.
