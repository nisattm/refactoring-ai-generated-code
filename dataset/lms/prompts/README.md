# Generation Plan (proposal, 30 October 2026)

How the LMS is generated with Claude Code from [`../requirements.md`](../requirements.md). Status: **approved** (31 October 2026). The generation pilot (steps 0–1) checks the command, the tests and the cost log before step 2.

## Rules

| Rule | Detail |
| --- | --- |
| Model and tool | Claude Code (version pinned in the Docker image), model `claude-sonnet-5-5`, fixed effort and thinking setting ([`../../../docs/approaches.md`](../../../docs/approaches.md)) |
| Environment | Fresh container per step from the pinned image; working copy `dataset/lms/generated/` mounted; nothing else from the repository is visible (no tests, no `dataset/README.md`, no docs) |
| Input | `requirements.md` copied into the working copy as `REQUIREMENTS.md` (not `CLAUDE.md`, which Claude Code would load automatically) and the step prompt below |
| Prompts | Only what to build and the order. **No quality hints** (no "clean", "maintainable", "well structured", no smell names, no design advice). Identical wording pattern for every step |
| Tools allowed | Read, write and edit files; any shell command inside the container (`Bash`). Other tools (WebFetch, WebSearch, …) are denied. The boundary is the container: it sees only the working copy and is removed after every step |
| Hands off | Generated code is never edited by hand ([`../../README.md`](../../README.md#generation-rules)) |
| Integration errors | If a step breaks earlier behavior or the app does not start, the fix is an additional prompt (`step-NN-fix-M.md`), logged and counted in the generation cost |
| Logging | Every call: JSON result through `scripts/cost.py`, plus a row in `../generation-log.md` |
| Baseline | After the last step the code is committed and tagged `v0-ai-baseline`; this is the starting code of every experiment |

## Steps

Modules are generated in dependency order. Each step implements whole sections of the requirements; later steps may extend earlier code.

| Step | Sections of `REQUIREMENTS.md` | Modules | Est. lines |
| --- | --- | --- | --- |
| 0 | 1–5 (scope, constraints, common rules, fixed interface, Core) and the calendar endpoints | 1, part of 14 | 2,500 |
| 1 | 6 (Identity and access) with its endpoints | 2, part of 14 | 3,000 |
| — | **Generation pilot ends here** (~5,000 lines): run the tests, check the cost log and how much of the 5-hour window a step uses; then continue with step 2. The refactoring pilot is in Week 5 | | |
| 2 | 17 (branches only: LIB-BR-01 – 04), 7 (Members) | 11 (part), 3 | 3,500 |
| 3 | 8 (Catalog) | 4 | 4,000 |
| 4 | 9 (Loans and returns), 11 (Fines and payments) | 5, 7 | 7,000 |
| 5 | 10 (Reservations), rest of 17 (transfers) | 6, 11 | 5,000 |
| 6 | 14 (Notifications), 19.1 (Audit log), 13 and 20.2 (events) | 8, 13 (part) | 3,000 |
| 7 | 15 (Search), 16 (Reports) | 9, 10 | 5,000 |
| 8 | 18 (Purchasing), 19.2–19.4 and 22 (import, export, formats) | 12, 13 | 4,000 |
| 9 | 20 (API layer): completeness check of every endpoint and error format; 21 (scenarios) | 14 | 2,500 |

Line estimates come from the module table in [`../../README.md`](../../README.md); they are not given to the model. The final size is measured, not steered: if the code ends below 30,000 lines, we report the real size; we do not ask for more code.

## Command

Every step runs with the same command from the repository root, in a bash shell (Linux, macOS, or Git Bash / WSL on Windows). The prompt is read and the JSON result is written on the host, so the container sees only the working copy. Once before step 0:

```bash
mkdir -p dataset/lms/generated results/generation
cp dataset/lms/requirements.md dataset/lms/generated/REQUIREMENTS.md
```

Each step (`NN` = `00` … `09`):

```bash
docker run --rm --env-file .env -v "${PWD}/dataset/lms/generated:/work" -w /work refactoring-env \
  claude -p "$(cat dataset/lms/prompts/step-NN.md)" \
  --model claude-sonnet-5-5 \
  --output-format json \
  --effort high \
  --permission-mode dontAsk \
  --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash" \
  > results/generation/step-NN.json
```

| Part | Why |
| --- | --- |
| `--env-file .env` | Pro login: the long-lived token `CLAUDE_CODE_OAUTH_TOKEN` from `.env` (never committed). Verified in a clean container with `check-claude` ([`../../../docs/environment.md`](../../../docs/environment.md#4a-claude-code-with-the-pro-subscription-once-per-person)) |
| `-p`, `--output-format json` | Non-interactive run; the JSON result feeds `scripts/cost.py` |
| `--permission-mode dontAsk` | Only reads and the listed tools run; anything that would ask is denied, so no call waits for a person and every step has the same permissions |
| `--effort high` | Fixed effort level, written explicitly because the JSON result does not record it and the default can change between Claude Code versions |
| `--allowedTools` | Exactly the tools of the "Tools allowed" rule. A bare `Bash` allows every shell command. A narrow list (`Bash(python *)`, `Bash(mkdir *)`, …) was tried in the pilot and in the first permission check: compound commands were denied, and after one denial the model stopped running anything and wrote the code blind. Argument patterns are fragile (Claude Code documentation, permission rules), and they add no protection because `python` can already do anything. A redirect to a file outside the working copy (e.g. `> /tmp/x`) can still be denied; such denials are reported, not fixed. A package missing from the image is caught by the app-start check in a fresh container. The network is open (the API needs it); the tests are not in the container and no prompt names the repository |

Checked against the Claude Code documentation (permission modes, permission rules) on 2026-10-30. Effort: `high` for every step, fixed in the command (chosen after the pilot, which ran at the default); thinking stays at the default of the pinned version. The setting of the refactoring runs is chosen in the Week 5 pilot ([`../../../docs/approaches.md`](../../../docs/approaches.md#model-and-thinking-settings)). The Claude Code version is pinned in the image.

Windows PowerShell is not used for this command: `$(cat …)` is bash syntax, and in Windows PowerShell 5.1 the `>` redirection writes UTF-16, which `scripts/cost.py` cannot read as UTF-8.

## Permission check before step 00

The pilot (tag `pilot-steps-00-01`) showed that the first allow list blocked every attempt of the model to run its code (`python3`, compound commands). A second, wider list (`python3`, `mkdir`, `cd`, `pip3`) failed the first permission check (`results/check/check-permissions.json`): `mkdir -p x && cd x && python3 -c "print('a')"` was denied, and the model then assumed that Bash was not allowed and did not try the other commands. The allow list is therefore a bare `Bash`. Before step 00, the command is checked once in an empty folder with this prompt, written to `results/check/check-permissions-bash.json` and logged with `stage=check`, `run_id=check-permissions-bash`:

```text
Run these five shell commands one after another and report for each whether it ran: (1) python3 -c "print('a')"; (2) mkdir -p x && python3 -c "print('b')"; (3) mkdir -p y && cd y && python3 -c "print('c')"; (4) a python3 heredoc: python3 - <<'EOF' with the line print('d') and EOF; (5) for i in 1 2; do python3 -c "print($i)"; done
```

Expected: all five run and `permission_denials` is empty. If one is denied, generation does not start before the command is fixed.

## Test results in the repository

`scripts/run_tests.py` writes JUnit XML and pytest logs next to the JSON summaries. Only `feedback.json`, `heldout.json` and `run.json` are committed (failed case IDs and counts); `*.junit.xml` and `*.log` are ignored and can be recreated by running the tests on the same code.

## Reading intermediate test results

Steps follow the dependency order, but some rules of an earlier step depend on a later one. After step 4 (loans, fees) some loan tests are expected to fail because reservations come in step 5: LIB-LOAN-05 step 6 (`on_hold` copies), `BOOK_RESERVED` in LIB-LOAN-07 and LIB-LOAN-12. The same holds for other cases that need a later module. Intermediate pass counts are therefore not a quality signal; only the results after step 9 count. Such expected failures are noted in the generation log.

## Prompt template

Every step prompt has the same three parts; only the section list changes. Files: `step-00.md` … `step-09.md`.

```text
REQUIREMENTS.md in this folder specifies a Library Management System.

Implement step <N>: sections <list> of REQUIREMENTS.md.
<Steps 1–9 only:> The code of the earlier steps is already in this folder. Keep all behavior required by earlier sections.

Follow REQUIREMENTS.md exactly, including names, paths, fields, status codes and error codes. Where a later section is needed by this step, implement only what this step needs; it will be completed in its own step.
```

## Generation log format (`../generation-log.md`)

| Column | Content |
| --- | --- |
| Step | `00` … `09`, or `NN-fix-M` |
| Date | Local date and time of the call |
| Claude Code version, model, effort | From the JSON result and the image |
| Prompt file | `prompts/step-NN.md` |
| Session id | From the JSON result |
| Input, output, cache tokens; equivalent cost | From `scripts/cost.py` |
| Duration | API and wall time |
| Files changed, lines added | `git diff --stat` of the step |
| SLOC after step | Radon SLOC of `lms/` |
| App starts / tests | Whether `create_app` starts; feedback and held-out pass counts (our runner, never shown to the model during generation) |
| Notes | Integration errors, retries, usage-limit waits |

## Decisions (2026-10-31)

- **Fresh session per step.** Every step is a new `claude -p` call in a new container (no `--resume`); the code in the folder is the only memory.
- **The model may write its own tests.** The prompts say nothing about tests either way. Tests the model writes stay in the generated code, are not run by our runner and are excluded from the metrics, like ours.
