# 005 – Week 6: Multi-Agent runs

**Date:** 2026-11-22
**Status:** Proposed (draft for Nisa's approval). Decisions M1–M7 were proposed with the Multi-Agent engine (package A, PR #140) and completed with the results of the Multi-Agent setup check K1–K7 (package B, PR #145; engine changes in PR #146).

## Context

Week 6 builds the Multi-Agent system: an Analyzer, a Refactoring agent and a Reviewer, the flow between them, and test feedback for corrections ([`../plan.md`](../plan.md)). [`../approaches.md`](../approaches.md) fixed the frame on 29 October 2026: one `claude -p` session whose main conversation only orchestrates and calls three Claude Code subagents, the same fix budget as Iterative (1 refactoring + at most 2 Reviewer returns) and the same test feedback as Iterative (fairness rule).

Inherited from [`004`](004-week5-single-iterative.md) and not changed here: the starting code, the baseline, the success rule, W1 (keep the best round), W2 (the feedback text of `experiments/feedback.py`), W3 (what the model sees), W6 (a run cut by the usage limit is discarded), W7 (5 runs per approach, 8 if the budget allows), W10 (failed and invalid runs) and the rule for invalid runs of the ADR 004 addendum (kept, repeated under a new run ID).

The engine `experiments/run_multiagent.py` and the test command `experiments/feedback_tests.py` were merged before this record and refer to it as "ADR 005 draft M1–M7"; the prompts in `experiments/prompts/multiagent/` were merged in PR #149. This record is the reference they point to.

## Decision

### Rules of the runs

| ID | Topic | Decision |
| --- | --- | --- |
| M1 | Definition of the roles | The three roles are custom subagents given on the command line with `--agents` (a JSON object built by the engine from `experiments/prompts/multiagent/{analyzer,refactoring,reviewer}.md`): description, prompt, tools and `"model": "claude-sonnet-5-5"` for each. No agent file is placed in the model's folder. The orchestrator is the main conversation; its prompt is `orchestrator.md`. |
| M2 | Roles and tools | Analyzer: `Read`, `Glob`, `Grep`. Refactoring: `Read`, `Glob`, `Grep`, `Edit`, `Write`. Reviewer: `Read`, `Glob`, `Grep`. The orchestrator gets `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash` and `Agent`: `Edit`/`Write` must be offered to the session so that the Refactoring subagent can use them, but an edit by the orchestrator itself makes the run invalid. Only the three roles may be called; a subagent may not start another subagent. |
| M3 | Test command and snapshots | The only shell command allowed is `python /engine/experiments/feedback_tests.py` (`--allowedTools "Bash(<command>)"`). Every run of it keeps a snapshot of the model's `lms/`, runs the feedback tests in a copy of the starting project with only `lms/` replaced (W3), repeats new failures twice (D18) and prints the W2 text of `feedback.py`, exactly what Iterative gets, or a fixed sentence. The fixed sentences ("All feedback tests that passed at the start still pass.", the budget sentence, "The feedback tests could not be run.") are neutral and were approved by package C with the prompts (PR #149). |
| M4 | Hidden folders | The tests, the starting project, the baseline, the engine and the configuration of the test command are mounted read-only (`/exp-tests`, `/exp-start`, `/exp-baseline`, `/engine`, `/exp-config`; snapshots in `/exp-state`) and closed with `--disallowedTools` rules for `Read`, `Glob`, `Grep`, `Edit` and `Write` (`Tool(//<folder>/**)`). The model works only in `/work` (its `lms/`, `requirements.txt`, `INTERFACE.md`), as in Single and Iterative. |
| M5 | Budget and checks from the stream | At most **3 Refactoring calls** (1 + at most 2 Reviewer returns) and **3 runs of the test command**; the orchestrator prompt states both. After the call the engine counts from the stream (`parent_tool_use_id`): subagent calls per role, test runs, the tools of each role. More than 3 Refactoring calls or 3 test runs, another subagent type, a subagent started by a subagent, an edit by the orchestrator or a read-only role, or a role using a tool outside its list makes the run invalid. The test command itself prints a fixed sentence and runs nothing after its third run. |
| M6 | Rounds and best round (W1) | Every snapshot whose `lms/` differs from the one before is a round, and the end of the call is one more round if the model changed `lms/` after the last test run. Each round is measured with the feedback tests against the best round so far (`round_accepted`, ADR 003) and the best is kept; the final measurement of the best round, round 1 and the last round is the one of Iterative. Tags `exp/multiagent/<run>/r<k>`. Round 1 of Multi-Agent is **not** a Single sample: its prompt is not `single.md`. |
| M7 | Records | `run.json` (roles, budget, test command, subagent calls, test runs, blocked attempts, where each round came from), one row in `runs.csv`, the cost log (stage `multi-agent`) and the feedback text each snapshot returned (`rounds/r<k>/feedback.txt`). A usage-limit cut: see addendum point 4 (pause and continue, PR #159, #160). |

### Setup check K1–K7

Source: `results/check/week5/flags.md`, section "Multi-Agent (K1–K7)", 22 November 2026 (package B, Claude Code 2.1.308, `claude-sonnet-5-5`). Decisions on the findings: package A (Fatima), applied in PR #146.

| # | Finding | Decision |
| --- | --- | --- |
| K1 | With `--safe-mode` the custom subagents are not loaded, neither from `--agents` nor from `.claude/agents/`; the call to `analyzer` fails. Without it they load. The subagent tool is listed as `Task` in the init event but called `Agent`. | **Multi-Agent runs without `--safe-mode`**; Single and Iterative keep it. The protection comes from the empty `CLAUDE_CONFIG_DIR` of every run, a check before the call that the model's folder has nothing Claude Code would load (`.claude/`, hidden files, `CLAUDE.md`, `AGENTS.md`), and the stream check of W9: a model-written `CLAUDE.md`, `AGENTS.md` or hidden file makes the run invalid. The init check expects `Task`; `--tools` and `--allowedTools` use `Agent`. |
| K2 | A subagent's `tools` list is enforced: the Analyzer could not edit. | M2 relies on it. |
| K3 | `Bash` is limited to the test command; other commands are denied. | M3. |
| K4 | `Read`, `Glob` and `Grep` on the hidden folders are denied, also for a subagent; the subagent's denials appear in the main `permission_denials`. | M4. |
| K5 | `"model": "claude-sonnet-5-5"` in `--agents` is accepted; `modelUsage` lists only Sonnet 5.5; `total_cost_usd` is the sum of `modelUsage`. The orchestrator and the subagents share one `modelUsage` entry. | The subagent fields of M1 are verified. The cost of a run is reported as a whole; a share per role is **not** available. |
| K6 | A built-in subagent (`general-purpose`) runs if it is not denied (K6), and read-only shell commands inside `/work` (`cat`, `find`, …) run without a denial (K6b). `--disallowedTools "Agent(general-purpose)"` blocks it, but the denial is not in `permission_denials`; it is only in the `tool_result` of the `Agent` call (K6c). | **The built-in subagent types are denied** (`Agent(general-purpose)`, `Agent(Explore)`, `Agent(Plan)`, `Agent(statusline-setup)`, `Agent(claude)`), and the denial is read from the `tool_result`; the prompt names only the three roles. Shell commands that ran without a denial are judged by the list rule of addendum point 5 (PR #161). |
| K7 | The test command ran 150 s without a timeout with `BASH_DEFAULT_TIMEOUT_MS` = `BASH_MAX_TIMEOUT_MS` = 3,600,000. | The Bash timeout is raised to one hour for Multi-Agent runs: the feedback set of the final code takes about 22.5 minutes alone (pilot summary, W13). |

**Denied tool calls (completes W10 for Multi-Agent).** In Single and Iterative every denied call makes the run invalid (W9). In Multi-Agent the setup is meant to block some attempts, so a denial is judged by what was denied:

- **Counted, the run stays valid:** another shell command, a read or write outside `/work`, a built-in subagent type. They are recorded as `blocked` in `run.json` and `runs.csv`.
- **Invalid (broken setup, repeated):** a denial of something the roles need: the test command, a read or write inside `/work`, a call of one of the three roles. A role call that returns an error (for example "not found", K1) is also invalid.

### Prompts (package C)

Files in `experiments/prompts/multiagent/` (PR #149): `orchestrator.md` and one file per role with a `---` / `description: …` / `---` header that the engine reads.

- Every file starts with the first paragraph of `single.md` and contains the fixed behavior sentence verbatim, as in ADR 004. The orchestrator also has the task sentences of `single.md` and the end marker `REFACTORING_DONE`.
- Placeholders only in `orchestrator.md`: `{test_command}`, `{max_refactoring_calls}`, `{max_test_runs}`. The role files have none.
- Flow in the orchestrator prompt: Analyzer → Refactoring → test command → Reviewer; back to Refactoring when the test command reports failing tests or the Reviewer rejects, with the Reviewer's reasons and the test output unchanged. The test command is run exactly as given and no other shell command is run.
- The Reviewer writes APPROVE or REJECT on the first line. The engine does not read it; it is kept for the analysis.
- No quality hint, smell name, metric, threshold or test name; checked by `scripts/tests/test_prompts.py`.
- **The Reviewer does not see the starting code.** M4 hides the starting project, so the Reviewer judges from the Refactoring report, the test output and the current `lms/`. This answers the open question of `approaches.md` ("Does the Reviewer see the original code?"). *(To confirm with Nisa: the plan does not say it; it follows from M4.)*

## Correction of `approaches.md`

Two statements written before the engine and the setup check are corrected in the same PR as this record: the roles are not "defined in the clean project copy" but given with `--agents` (M1, K1), and the subagent fields are no longer "verified in the pilot" but decided with K5.

## Alternatives considered

- Three separate `claude -p` sessions instead of subagents: rejected on 29 October 2026 (`approaches.md`); the instructor's notes name subagents.
- Agent files in `.claude/agents/` of the model's folder: not loaded with `--safe-mode` either (K1c), and they would be files the model can read and change.
- Keeping `--safe-mode` for Multi-Agent: not possible, the roles are not loaded (K1).
- Making every denied call invalid, as in Single and Iterative: rejected by package A (PR #146); in Multi-Agent the setup is meant to block attempts (K3, K4, K6), and such an attempt does not break the run.

## Consequences

- `approaches.md` (role definition, open question on subagent fields) is changed in the same PR as this record.
- Multi-Agent differs from Single and Iterative in one setting, `--safe-mode`; this is reported as a threat to validity together with the checks that replace it.
- The cost of the roles cannot be separated (K5); only the cost of the whole run is compared between the approaches.
- The results of the Multi-Agent pilot and the lock rule of W13 for Multi-Agent are recorded in the addendum below.

## Addendum (2026-11-22, completed 2026-11-24): Multi-Agent pilot

Source: `results/experiments/pilot/runs.csv` and the `run.json` of each run in `results/experiments/pilot/multiagent/` (package B, PR #152). Both runs on the pilot code `ce03f54` (modules 1–14) with the pilot baseline `results/baseline/trial/pilot-ce03f54-v2`.

1. **`pilot-m01` is invalid; the cause was in the engine (fixed in PR #151).** The orchestrator tried `Glob` with the pattern `/engine/**/*` and no path. The deny rule (M4) blocked it, as intended, but the engine judged a `Glob` only by its path, took the missing path as `/work` and counted the denial as a needed call (broken setup, K6 rule above). Since PR #151 a `Glob` is also judged by its pattern, and relative paths are resolved against `/work`, so such an attempt is counted as `blocked` and the run stays valid. Following the rule of the ADR 004 addendum, the run is kept in `runs.csv` (`valid=false`) and was repeated as `pilot-m01b`. The call itself ended normally after 1,677 s with 1 Analyzer, 2 Refactoring and 2 Reviewer calls and 2 test runs; its rounds were not measured.
2. **`pilot-m01b`: valid, outcome `no_improvement`.** One call of 733 s; the run took 1,293 s (about 22 minutes) in total. The orchestrator used each role once (Analyzer, Refactoring, Reviewer) and ran the test command once; nothing was blocked. The test command found no regression, so the feedback was the fixed sentence "All feedback tests that passed at the start still pass." The one round was not kept: mean CC, mean Cognitive and MI improved, duplication stayed the same, but the smell count rose from 83 to 87, so the best result is the starting code (ADR 003, `round_accepted`).
3. **The run lock is held during the Multi-Agent call.** The ADR 004 addendum (point 1) releases the lock during the Claude call from Week 6 on, and the engine does so for Single and Iterative (PR #153). Multi-Agent is the exception: its feedback tests run inside the call (M3), so releasing the lock would let them overlap with the tests or measurements of another run. The engine keeps the lock for the whole Multi-Agent call (`hold_lock`).
4. **Scale trial on the final code: one Multi-Agent run does not fit in one 5-hour window of a Pro account.** `scale-m01` (`v0-ai-baseline`, 30,260 SLOC, Işıl's account `exp-1`, 2026-11-22 18:35–19:02; records in `results/experiments/scale/`, PR #154) started at 9 % of the 5-hour window; the orchestrator call was cut by the usage limit after 1,618.5 s (window 100 %, weekly 49 %, 13.20 $ list price, 2 subagents started) and the run was discarded (`discarded_limit`, rule W6). On the pilot code a run used 24 % (`pilot-m01b`, 733 s call; 0 % → 24 %) and 51 % (`pilot-m01`, 1,677 s call; 1 % → 52 %). All values are read from the last `rate_limit_event` of each call.

   **Pause and continue (PR #159, #160).** When `scale-m01` ran, W6 discarded a cut run and the engine had no resume. Since PR #159 and #160 the Multi-Agent engine keeps a cut run (`limit_cut`), waits until the 5-hour window reopens (`resetsAt` + 5 minutes, run lock released) and continues the same session with the same settings and the fixed sentence "The session was interrupted by a usage limit. Continue the task from where you stopped."; at most 3 pauses and 24 hours of waiting in total, no waiting for the weekly limit, no other account. It can also be continued by hand (`--resume-run`). The roles and the budget (M5) are checked over all calls. Single and Iterative still discard a cut run (W6). The fixed sentence is neutral (no quality hint, smell name or metric; package C). This changes W6 for Multi-Agent only, and it has not been tried on a real cut run (the window rule was checked only against the record of `scale-m01`; a weekly cut is not verified).

   Open, for Nisa's decision before the real runs: (a) a Max account for the experiment runs, with the same model and settings; (b) all three approaches on the pilot code `ce03f54`; (c) a smaller budget or effort, not recommended because Single and Iterative ran with `high`; (d) pause and continue as above, which gives Multi-Agent more than one 5-hour window while Single and Iterative get one. All three approaches must run on the same code.
5. **Shell rule (decisions of 24 November 2026, PR #161).** Read-only shell commands (`find`, `wc`, `ls`, `cat`, `head`, `tail`, `sort`, `grep`, `uniq`, and `xargs` with one of them) never make a run invalid, in any role or approach; they are counted per role and written to `run.json`. A command that writes, deletes or is not on the list still makes the run invalid. This replaces the earlier rule of the engine (a run was invalid only if a command that can change files ran). Both decisions were taken before the metrics of the run that raised them (`m01c`) were seen; that run is not in the repository yet. `--rejudge-run` judges a run that ended invalid again from its recorded streams, without calling Claude, keeps both decisions in `run.json` and adds a new row to `runs.csv` that points to the old one (the old row is kept, rule 2 of the ADR 004 addendum).
6. **Compaction window (PR #159).** Every Claude Code call of all three approaches now runs with `CLAUDE_CODE_AUTO_COMPACT_WINDOW` = 200,000 tokens (run option `--compact-window`, recorded in `run.json`), because the largest context in `scale-m01` reached 661,170 tokens. The pilot runs above ran without this setting. For Nisa: the same value in every real run of the three approaches.
