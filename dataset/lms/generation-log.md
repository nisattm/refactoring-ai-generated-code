# Generation Log

One row per Claude Code call during generation ([`prompts/README.md`](prompts/README.md#generation-log-format-generation-logmd)). Not started yet.

Test counts after steps 0–8 include failures of rules that need a later module (for example, after step 4 the loan rules that need reservations). They are noted in the Notes column and are not counted as defects ([`prompts/README.md`](prompts/README.md#reading-intermediate-test-results)).

| Step | Date | Claude Code / model / effort | Prompt | Session id | Input tok | Output tok | Cache read / write | Equivalent cost | Duration (API / wall) | Files / lines added | SLOC after | App starts / tests (feedback, held-out) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
