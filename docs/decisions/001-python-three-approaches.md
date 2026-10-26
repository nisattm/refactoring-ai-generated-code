# 001 – Switch to Python and a three-approach comparison

**Date:** 2026-10-26
**Status:** Accepted

## Context

The first plan generated a Java/Spring Boot course tracking API with LLM agents and refactored it with IDE tools. In October 2026 the instructor provided an 8-week plan: Claude generates Python code for tasks of three complexity levels and a Library Management System, and three LLM refactoring approaches (Single LLM, Iterative LLM, Multi-Agent) are compared on quality, behavior preservation, performance and cost.

## Decision

- Follow the instructor's 8-week plan ([`../plan.md`](../plan.md)).
- Language: Python. Model: Claude, the same version throughout.
- Approach rules as in [`../approaches.md`](../approaches.md) (to be finalized in the metrics meeting).
- Metrics extended after the instructor's feedback of 26 October 2026 ([`../metrics.md`](../metrics.md)).
- Java/Spring Boot material moved to [`../../archive/java-spring-plan/`](../../archive/java-spring-plan/).

## Consequences

- The Java API contract, prompts and the generated P1 code are no longer used.
- Tools change from the Java ecosystem (DesigniteJava, PMD, JUnit, JMH) to the Python ecosystem (PyExamine, DPy, Radon, Ruff, pytest, pyperf).
