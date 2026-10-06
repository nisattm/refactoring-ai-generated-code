# Metrics

| Folder | Content |
| --- | --- |
| `baseline/` | Measurements of the `v0-ai-baseline` tag |
| `sprints/` | End-of-sprint measurements, one subfolder per sprint (`sprint-1/`, ...) |
| `final/` | Final measurements and the before/after comparison |

## Tracked metrics

| Category | Metric | Tool |
| --- | --- | --- |
| Complexity | Cyclomatic complexity, cognitive complexity | CK, PMD, SonarQube |
| Size and maintainability | LOC/SLOC, Halstead volume and difficulty, Maintainability Index | multimetric |
| Object-oriented design | WMC, CBO, LCOM, DIT | CK |
| Smells and debt | Code smell count, duplication rate, technical debt | DesigniteJava, CPD, SonarQube |
| Tests | Branch coverage, mutation score, behavior changes | JaCoCo, PIT, ApprovalTests, jqwik |
| Performance | Execution time | JMH |
| Process | Applied refactorings | RefactoringMiner |

Before and after values are always measured with the same tool and version.
