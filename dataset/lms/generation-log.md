# Generation Log

One row per Claude Code call during generation ([`prompts/README.md`](prompts/README.md#generation-log-format-generation-logmd)).

Test counts after steps 0–8 include failures of rules that need a later module (for example, after step 4 the loan rules that need reservations). They are noted in the Notes column and are not counted as defects ([`prompts/README.md`](prompts/README.md#reading-intermediate-test-results)).

| Step | Date | Claude Code / model / effort | Prompt | Session id | Input tok | Output tok | Cache read / write | Equivalent cost | Duration (API / wall) | Files / lines added | SLOC after | App starts / tests (feedback, held-out) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00 | 2026-10-31 15:29 (+03:00) | 2.1.308 / claude-sonnet-5-5 / default | `prompts/step-00.md` | 6ecd758d-f897-43c4-b141-1ed98e567887 | 10 | 19,870 | 172,028 / 45,595 | 0.3983 USD | 100.9 s / 107 s | 27 / +521 | 363 | yes / feedback 19/282, held-out 15/239 | 1 permission denial: one long compound Bash command (`mkdir`, `cd`, `for`, heredocs, `python3 -I`) did not match `Bash(python *)`; the model could not run or test anything and wrote all files with the file tools. No hidden files; the model wrote no tests. First `run_tests.py` call used a relative `--out` and was invalid (exit 3: junit files landed in the tests folder, no test file content changed); repeated with an absolute `--out` (exit 1, hashes unchanged). 1,619 thinking tokens |
