# Generation Log

Every interaction with the LLMs that produced the codebases is recorded here, so that the origin of the code is documented and the process can be reproduced.

The full procedure (prompt order, allowed follow-up messages, acceptance check, copying, tags) is in [`../prompts/README.md`](../prompts/README.md). Follow it exactly.

## Folder layout

One folder per model, one subfolder per step:

```
generation-log/
  claude/
    README.md        generation metadata and summary table
    P1/
      01-prompt.md
      01-response.md
      02-followup.md
      02-response.md
      notes.md
    P2/ P3/ P4/ DT1/ DT2/
  gpt/
  gemini/
```

## `<model>/README.md` template

```markdown
# Generation Log – <Model>

| Field | Value |
| --- | --- |
| Operator | |
| Tool and version | |
| Model name shown by the tool | |
| Plan | |
| Mode | agent / chat |
| Start date | |
| End date | |

## Summary

| Step | Rounds | Follow-ups used (F1–F4) | Acceptance check | Tag | Observed issues |
| --- | --- | --- | --- | --- | --- |
| P1 | | | | `<model>-P1` | |
| P2 | | | | `<model>-P2` | |
| P3 | | | | `<model>-P3` | |
| P4 | | | | `<model>-P4` | |
| DT1 | | | | `<model>-DT1` | |
| DT2 | | | | `<model>-DT2` | |
```

## `notes.md` template

```markdown
# <Model> – <Step>

- Date:
- Time spent (minutes):
- Follow-ups used: (e.g. F1 ×2, F4 ×1)
- Acceptance check: `mvn -q package` pass/fail · `spring-boot:run` pass/fail · Swagger lists all endpoints yes/no
- Files created or changed by the agent:

## Observed issues

Business logic errors or missing validation noticed during the check. Do not report these back to the LLM.
```

Size and duplication are measured later from the tags by the measurement owner, so they are not recorded here.
