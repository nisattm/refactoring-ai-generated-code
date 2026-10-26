---
name: Code smell
about: Report a code smell or technical debt item found in the codebase
title: "[Smell] <smell type> in <ClassName>"
labels: code-smell
---

## Smell type
<!-- ID and name from docs/smell-catalog.md, e.g. S02 God Class -->

## Location
<!-- Task, file and function/class, e.g. dataset/complex/library/loans.py: LoanService.borrow -->

## Detected by
<!-- PyExamine / DPy / Radon / complexipy / Ruff / Pylint / Vulture / jscpd / Test / Rubric review -->

## Evidence
<!-- Metric values or tool output, e.g. CC = 18, 120 lines, duplicated in 3 places -->

## Proposed refactoring
<!-- Technique from Fowler's catalog, e.g. Extract Method, Replace Conditional with Polymorphism -->

## Severity
<!-- Critical / High / Medium / Low -->

## Behavior lock
- [ ] Characterization tests exist for the affected code
