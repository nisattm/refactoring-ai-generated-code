# Week 5 — Pilot baseline re-measured (W15, Package B)

Date: 2026-11-20 · Run by: Işıl · Docker image `refactoring-env`

```
scripts/measure_baseline.sh --label pilot-ce03f54-v2 --code-ref ce03f54 --modules 1-14
```

Result: `results/baseline/trial/pilot-ce03f54-v2/` — `valid=True`, 436 s. The old measurement `pilot-ce03f54` (16 November) is left as it is.

## Checks

| Check | Expected | Result |
|---|---|---|
| Code content hash, old vs new | same | ✅ same: `ef1c8f40ecd5b27bb1480ea1f6f4cad16e77dbaf18206c724f726b7b3369a3d1` |
| Primary metrics, old vs new | — | identical: mean CC 2.6795, mean Cognitive 1.8578, MI 45.8653, duplication 0.809 %, smells 83 |
| Tests | — | feedback 282/282, held-out 239/239, flaky 0 |
| Self-compare `round_accepted` | true | ✅ true |
| Self-compare `run_successful` | false (nothing improved) | ✅ false; all five primary metrics `same` |

The old folder has no `functions.csv` (older analyzer), so `compare.py` cannot use it; the new folder is the one to pass as `--baseline` for the pilot.

Self-compare command (code of `ce03f54` exported with `git archive` to a temporary folder for the OpenAPI hash):

```
B=results/baseline/trial/pilot-ce03f54-v2
python scripts/compare.py --before $B --after $B --tests-before $B/tests.csv --tests-after $B/tests.csv \
  --flaky $B/flaky.txt --before-code /code --after-code /code --out results/check/week5/self-compare
```

Output: `self-compare/compare.json`, `self-compare/compare.csv`.
