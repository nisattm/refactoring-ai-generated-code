# Generation Log

Every interaction with the LLM that produced the codebase is recorded here, so that the origin of the code is documented and the process can be reproduced.

## Generation protocol

1. Fix the tool and model; record their names and the date.
2. Use the requirements in [`../requirements.md`](../requirements.md).
3. Generate one feature per session.
4. Keep prompts neutral; never ask for messy or deliberately poor code.
5. Do not clean up code by hand. When something does not work, only the error message is given back to the LLM.
6. Record every revision round, and note SLOC and duplication rate after each round.
7. Tag the final generated version as `v0-ai-baseline`.

## Generation metadata

| Field | Value |
| --- | --- |
| Tool | |
| Model | |
| Date | |

## File naming

```
feature-1-management/
  01-prompt.md
  01-response.md
  02-error.md
  02-response.md
feature-2-absence/
  ...
```

## Revision growth

| Feature | Round | SLOC | Duplication (%) | Notes |
| --- | --- | --- | --- | --- |
| | | | | |
