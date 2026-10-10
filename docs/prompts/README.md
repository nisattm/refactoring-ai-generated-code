# Generation Protocol

Three LLMs generate the same application from the same prompts. The study is only valid if **the model is the only thing that differs** between the three codebases. Every rule below exists to protect that.

## 1. Who generates what

| Model | Tool (agent mode) | Generation workspace | Folder in the repo | Branch | Tag prefix | Operator |
| --- | --- | --- | --- | --- | --- | --- |
| Claude | Claude Code | `C:\gen\claude` (or `~/gen/claude`) | `codebases/claude/` | `generation/claude` | `claude-` | Işıl Gültekin |
| GPT | Codex (CLI or desktop app, local mode) | `C:\gen\gpt` (or `~/gen/gpt`) | `codebases/gpt/` | `generation/gpt` | `gpt-` | Nisa Atım |
| Gemini | Gemini CLI | `C:\gen\gemini` (or `~/gen/gemini`) | `codebases/gemini/` | `generation/gemini` | `gemini-` | Aslınur İlay Tekin |

**Codex note:** the Codex CLI and the Codex desktop app both work, as long as the task runs **locally** on the folder `C:\gen\gpt`. Do not use Codex cloud tasks (chatgpt.com/codex): they run against a GitHub repository, so the agent would see this repository.

**Why a separate workspace:** coding agents can read files above the folder they run in. If the code were generated inside this repository, the agent could read the full contract, later change requests and our refactoring documents, which would influence the code it writes. The agent therefore only ever runs in an empty folder **outside** the repository; after each round the files are copied into `codebases/<model>/` and committed.

## 2. Prompts and order

| Step | File | Content |
| --- | --- | --- |
| P1 | [`P1-students-courses.md`](P1-students-courses.md) | Project setup, students, courses |
| P2 | [`P2-absences.md`](P2-absences.md) | Absence records and absence status |
| P3 | [`P3-grades.md`](P3-grades.md) | Grades and grade calculation |
| P4 | [`P4-report.md`](P4-report.md) | Student report |
| DT1 | [`DT1-project-only-grading.md`](DT1-project-only-grading.md) | Change request: project-only grading |
| DT2 | [`DT2-per-course-absence-limit.md`](DT2-per-course-absence-limit.md) | Change request: per-course absence limit |

The prompts are derived from [`../api-contract.md`](../api-contract.md). Always send them in this order, each one in a **new session**.

## 3. Mode: agent (recommended) or chat

All three operators must use the **same mode**. Mixing modes makes the comparison invalid.

**Agent mode (recommended).** Claude Code, Codex CLI and Gemini CLI write files directly into the folder and read the existing code themselves in each new session. This is how AI coding assistants are used in practice today.

**Chat mode (fallback, only if an agent is not available for one of the models).** Then all three use the web chat:
- From P2 onward, attach **all** current project files (including `pom.xml`) to the new conversation.
- Append this sentence, unchanged, at the end of every prompt and every follow-up message:

  `Output every new or changed file in full, each preceded by its file path. Do not omit unchanged parts of a changed file.`

- Copy each file from the answer into the folder exactly as given. Copying is the only manual work allowed; do not change a single character.

## 4. Before you start (once)

1. Install the agent and sign in with your own subscription.
2. Write the following into `docs/generation-log/<model>/README.md`: tool name and version, the exact model name the tool shows, your plan, and the date. Use the tool's default settings; do not change model, temperature or reasoning settings during the study.
3. Create your branch from the latest `main` in your clone of this repository:

```
git checkout main
git pull
git checkout -b generation/<model>
```

4. Create the generation workspace: an **empty** folder outside the repository clone, for example `C:\gen\gpt`. Never put anything in it yourself: no README, no `.gitignore`, no instruction files such as `CLAUDE.md`, `AGENTS.md` or `GEMINI.md`. If the tool offers to create such a file (for example an "init" command), decline. If the tool requires a Git repository in the folder, run `git init` there; that is allowed.

## 5. Running one step

1. Open a **new** session of the agent **inside the generation workspace** (for example `cd C:\gen\gpt` and then start the tool).
2. Open the prompt file, copy **only the text between the two horizontal lines**, paste it as one message and send it.
3. Let the agent work. When it asks for permission to create or edit files, or to run `mvn` commands inside the folder, approve. Refuse anything outside the folder.
4. When it stops, run the acceptance check (section 7).
5. If the check fails, use the standard follow-up messages (section 6).
6. Record and commit (section 8).

## 6. Standard follow-up messages

Only these messages may be sent after a prompt. Copy them exactly. Never explain, hint, suggest a solution or comment on code quality.

| Code | When | Message |
| --- | --- | --- |
| F1 | `mvn package` or `mvn spring-boot:run` fails | `The build or startup fails with the following output. Fix it.` followed by the full error output |
| F2 | An endpoint listed in the prompt is missing from Swagger UI (allowed once per step) | `These endpoints from the requirements are missing: <list of method and path>. Implement them as specified.` |
| F3 | The agent asks you a question | `Use your best judgment and follow the requirements in my first message.` |
| F4 | The agent stops before finishing, or asks whether to continue | `Continue.` |

**Limit:** at most **5 follow-ups per step** in total. If the acceptance check still fails after 5, stop, record it as a generation failure in the log and tell the team on the issue. The team decides how to proceed; do not fix it yourself.

**Never feed back business logic errors.** If a status is calculated wrongly or a validation is missing, that is a finding of the study, not something to fix during generation. Note it in the log under "Observed issues" and move on.

## 7. Acceptance check after every step

Run inside the generation workspace:

1. `mvn -q package` finishes without errors. (If the LLM wrote its own tests and they fail, this counts as a failure → F1.)
2. `mvn spring-boot:run` starts the application.
3. `http://localhost:8080/swagger-ui.html` opens and lists every endpoint of the current step (see the endpoint summary in the contract, section 9).

That is all. Do not test business rules here.

## 8. Recording and committing

After **every** round (the prompt and each follow-up):

1. Save the conversation into `docs/generation-log/<model>/<step>/`:

```
docs/generation-log/gpt/P1/
  01-prompt.md     the exact message you sent
  01-response.md   the agent's full answer (copy the whole conversation text, including the list of files it changed)
  02-followup.md   F1–F4 message with the pasted error, if any
  02-response.md
  notes.md         acceptance check result, number of follow-ups, observed issues, time spent
```

2. Copy the code from the workspace into the repository, replacing the previous version completely (files the agent deleted must disappear too). Run from the root of your repository clone:

Windows (PowerShell):
```
robocopy C:\gen\gpt codebases\gpt /MIR /XD target .git .idea .vscode
```

macOS / Linux:
```
rsync -a --delete --exclude target --exclude .git --exclude .idea --exclude .vscode ~/gen/gpt/ codebases/gpt/
```

3. Commit everything (code and log) on your branch:

```
git add -A
git commit -m "gen(gpt): P1 round 1"
```

After the **last** round of a step, tag it and push:

```
git tag gpt-P1
git push origin generation/gpt --tags
```

Tags: `<model>-P1`, `<model>-P2`, `<model>-P3`, `<model>-P4`, `<model>-DT1`, `<model>-DT2`. The measurement owner uses these tags to measure growth step by step, so never move or delete a tag.

## 9. Forbidden

- Editing generated code by hand, including formatting, imports, renaming or "small fixes"
- Running IDE auto-format, auto-import or quick-fix on the generated code
- Sending anything other than the prompt files and F1–F4
- Telling the LLM about code quality, design, patterns, tests or refactoring
- Showing one model the output of another model
- Running the agent inside the repository clone, or pointing it to files in the repository
- Changing a prompt after any model has received it

## 10. After DT2

1. Fill in the summary table in `docs/generation-log/<model>/README.md`.
2. Open a pull request from `generation/<model>` to `main`, title `gen(<model>): generated codebase P1–DT2`, and link the generation issue.
3. When all three are merged, the team tags `main` as `v0-ai-baseline`.
