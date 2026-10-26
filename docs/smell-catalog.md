# Python Code Smell Catalog

Smells we look for in Claude-generated Python code, how we detect them, and where they come from. Categories follow the taxonomy of Jerzyk & Madeyski (2023). Observed counts are added in Week 4.

## Survey of the GitHub `code-smell` topic

[github.com/topics/code-smell](https://github.com/topics/code-smell) lists 22 repositories (20 reviewed on 26 October 2026).

- **Catalogs.** The most complete is [Luzkan/smells](https://github.com/Luzkan/smells), backed by a peer-reviewed publication: Jerzyk & Madeyski (2023, Springer), 56 smells and a three-dimensional taxonomy (Obstruction, Expanse, Occurrence). We use its categories.
- **Python detectors.** python-code-smell-detector, long-parameter-list, nikui (hotspots from Git churn + static analysis + LLM), codevista, CodeRefactor-Pilot. All small (0–11 stars) without peer-reviewed evaluation; not used as primary measurement tools.
- **Linters for AI-generated code.** vibecop ("deterministic AI-code linter", 22 detectors) and stopslop show that AI-generated code is starting to be treated as its own smell category; vibecop can be tried as an extra detector in the pilot.
- **Decision.** Primary detectors are the peer-reviewed PyExamine and DPy (MSR 2025) plus Ruff and Pylint rules; the GitHub catalogs are a source of definitions and categories.

## Catalog

| ID | Smell | Category (Jerzyk & Madeyski) | Level | Detection |
| --- | --- | --- | --- | --- |
| S01 | Long Method | Bloaters | Code | PyExamine (line threshold); Ruff PLR0915 |
| S02 | Large Class / God Class | Bloaters | Design | PyExamine (NOM, WMC); DPy |
| S03 | Long Parameter List | Bloaters | Code | PyExamine; Ruff PLR0913 |
| S04 | Data Clumps | Bloaters | Code | PyExamine |
| S05 | Primitive Obsession | Bloaters | Code | PyExamine |
| S06 | Duplicate Code | Dispensables | Code | jscpd; PyExamine |
| S07 | Dead Code | Dispensables | Code | Vulture; PyExamine; Ruff F401, F841 |
| S08 | Speculative Generality | Dispensables | Design | PyExamine |
| S09 | Complex Conditional | Obfuscators | Code | PyExamine; Ruff PLR0916, SIM |
| S10 | Deep Nesting | Obfuscators | Code | Pylint R1702; complexipy |
| S11 | Magic Number | Lexical Abusers | Code | Ruff PLR2004 |
| S12 | Feature Envy | Couplers | Design | PyExamine |
| S13 | Message Chains | Couplers | Design | PyExamine |
| S14 | Shotgun Surgery | Change Preventers | Design | PyExamine |
| S15 | Divergent Change | Change Preventers | Design | PyExamine |
| S16 | Temporary Field | Object-Oriented Abusers | Design | PyExamine |
| S17 | Deficient Encapsulation | Object-Oriented Abusers | Design | DPy |
| S18 | Cyclic / Hub-like Dependency | Couplers | Architecture | PyExamine; DPy |
| S19 | Swallowed / broad exception | Functional Abusers* | Logic | Ruff S110, BLE001; Pylint W0718 |
| S20 | Mutable default argument | Functional Abusers* | Logic (Python) | Ruff B006 |
| S21 | Inconsistent / redundant return | Obfuscators* | Logic | Pylint R1710; Ruff RET |

\* Not in the catalog directly; the category is our assignment.

## Logic smells

Code that compiles and may pass the tests but is illogical. Detectable by tools: unreachable code (Pylint W0101), unused variables and imports (Ruff F841, F401), simplifiable conditions (Ruff SIM), repeated checks of the same condition, inconsistent return values (Pylint R1710), swallowed exceptions (Ruff S110), mutable default arguments (Ruff B006). Their total is the "logic smell count" metric. Logic problems the tools miss are captured by the rubric in [`metrics.md`](metrics.md#design-and-logic-rubric).

## Observed smells (from Week 4)

| ID | Smell | Task | Location | Detected by | Value | Approach that fixed it |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Sources

- M. Jerzyk, L. Madeyski. Code Smells: A Comprehensive Online Catalog and Taxonomy. In: Developments in Information and Knowledge Management Systems for Business Applications, Springer, 2023, pp. 543–576. doi:10.1007/978-3-031-25695-0_24 · [luzkan.github.io/smells](https://luzkan.github.io/smells/)
- K. Shivashankar, A. Martini. PyExamine: A Comprehensive, Un-Opinionated Smell Detection Tool for Python. MSR 2025. arXiv:2501.18327
- A. Boloori, T. Sharma. DPy: Code Smells Detection Tool for Python. MSR 2025 Data and Tool Showcase Track
- M. Fowler. Refactoring: Improving the Design of Existing Code, 2nd ed., Addison-Wesley, 2018
