# Model choice pilot (5 November 2026)

**Question:** Does Haiku 5.5 write clearly more code than Sonnet 5.5 for the same requirements, and does that code pass the tests? Asked because the generated LMS has 6,449 SLOC and the instructor asks for at least 30,000.

**Setup:** steps 00–02 of the LMS generation, same prompts, requirements, command, allow list and tests as the Sonnet generation ([`../../dataset/lms/prompts/README.md`](../../dataset/lms/prompts/README.md)); only the model and the effort change. Fresh container and session per step. Code, per-step results and the full log ([`log.md`](log.md)) are on tag `model-pilot` (branch `pilot/model-choice`); the generated code is not merged into `main`. Cost rows: `metrics/cost-log.csv`, `stage=pilot`, `run_id` `model-pilot-*`, and the Haiku check `check-haiku` ([`../check/check-haiku.json`](../check/check-haiku.json)).

Decision rules, agreed before the runs: (1) the app starts after every step and after step 02 feedback ≥ 62/282 and held-out ≥ 49/239 (80 % of Sonnet); (2) SLOC after step 02 ≥ 2,670 (1.5 × Sonnet); (3) Haiku is chosen only if both hold; (4) CC and duplication are reported, not used for the decision.

| | A: Sonnet 5.5 high | B: Haiku 5.5 medium | C: Haiku 5.5 high |
| --- | --- | --- | --- |
| SLOC after step 00 / 01 / 02 | 637 / 1,144 / 1,780 | 302 / 898 / 1,483 | 401 / 1,128 / 1,925 |
| Feedback after step 02 | 78/282 | 77/282 | 77/282 |
| Held-out after step 02 | 61/239 | 61/239 | 61/239 |
| App starts (every step) | yes | yes | yes |
| Average CC after step 02 (radon) | 2.19 | 2.52 | 2.27 |
| Duplication after step 02 (jscpd) | 0.00 % | 2.24 % | 0.77 % |
| Equivalent cost, 3 steps | 2.1411 USD | 0.4210 USD | 0.8869 USD |
| Wall time, 3 steps | 755 s | 730 s | 1,226 s |
| Permission denials | 0 | 0 | 0 |

A is the existing generation (tests of #57/#58); its CC and duplication were measured on `b48955e` with the same commands. Wall times of B and C include container start.

**Result:** rule 1 holds for B and C, rule 2 fails for both (B 0.83 ×, C 1.08 × Sonnet). Generation stays with **Sonnet 5.5, effort high**. Size depends on the scope of the requirements, not on the model; reaching the required 30,000 SLOC needs a larger specification.

**Findings (not part of the decision):** B and C fail the same test cases; both break `T-MEM-13-b` in step 02 (`GET /api/v1/members/me` returns `403` instead of `404 NOT_FOUND` for a librarian without a member). Haiku's `usd_recomputed` is empty because `scripts/cost.py` has no Haiku price; `usd` is Claude Code's own value. The model of B ran `ruff` in the container (`.ruff_cache`, ignored).
