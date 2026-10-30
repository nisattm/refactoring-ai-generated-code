# Generation Plan (proposal, 30 October 2026)

How the LMS is generated with Claude Code from [`../requirements.md`](../requirements.md). Status: **proposal for team review**; the pilot (steps 0–1) tests it before the full generation.

## Rules

| Rule | Detail |
| --- | --- |
| Model and tool | Claude Code (version pinned in the Docker image), model `claude-sonnet-5-5`, fixed effort and thinking setting ([`../../../docs/approaches.md`](../../../docs/approaches.md)) |
| Environment | Fresh container per step from the pinned image; working copy `dataset/lms/generated/` mounted; nothing else from the repository is visible (no tests, no `dataset/README.md`, no docs) |
| Input | `requirements.md` copied into the working copy as `REQUIREMENTS.md` (not `CLAUDE.md`, which Claude Code would load automatically) and the step prompt below |
| Prompts | Only what to build and the order. **No quality hints** (no "clean", "maintainable", "well structured", no smell names, no design advice). Identical wording pattern for every step |
| Tools allowed | Read, write and edit files; run `python` and `pip install -r requirements.txt` inside the container. No network beyond the package index |
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
| — | **Pilot ends here** (~5,000 lines): run the tests, one refactoring with each approach, measure usage | | |
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

Every step runs with the same command inside its container, from `dataset/lms/generated/`:

```bash
claude -p "$(cat prompts/step-NN.md)" \
  --model claude-sonnet-5-5 \
  --output-format json \
  --permission-mode dontAsk \
  --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash(python *)" "Bash(pip install -r requirements.txt)" \
  > logs/step-NN.json
```

| Part | Why |
| --- | --- |
| `-p`, `--output-format json` | Non-interactive run; the JSON result feeds `scripts/cost.py` |
| `--permission-mode dontAsk` | Only reads and the listed tools run; anything that would ask is denied, so no call waits for a person and every step has the same permissions |
| `--allowedTools` | Exactly the tools of the "Tools allowed" rule. `Bash(python *)` matches any command that starts with `python`; a compound command (`&&`, `;`, `\|`) must match a rule in every part |

Checked against the Claude Code documentation (permission modes, permission rules) on 2026-10-30. **Not verified:** the flag for the effort and thinking setting; it is chosen in the pilot ([`../../../docs/approaches.md`](../../../docs/approaches.md#model-and-thinking-settings)) and added to the command before step 0. The Claude Code version is pinned in the image.

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

## Open questions for the team

- Whether the model may write its own tests during generation (they would be excluded from the metrics, like ours).
- Whether steps run in one Claude Code session (`--resume`) or a fresh session per step (proposal: fresh session, the code in the folder is the only memory).
