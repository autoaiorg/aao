
---
name: implementation
description: Implements complete software features with architecture analysis, acceptance tests, execution and verification. Use for non-trivial feature development and refactoring.
---

# Implementation Protocol

## Phase 1 — Discovery
Inspect the relevant code and dependencies.
Identify affected modules, existing patterns and risks.

## Phase 2 — Specification
Define observable acceptance criteria.
Identify normal behavior, edge cases and failure cases.
Distinguish requirements from assumptions.

## Phase 3 — Design
Choose an approach consistent with the existing architecture.
Identify contracts, data flows and integration points.

## Phase 4 — Implementation
Implement the complete agreed scope.
Do not substitute mocks or placeholders for required functionality.
Prefer cohesive, incremental changes.

## Phase 5 — Verification
Run relevant automated checks.
Exercise the feature through its real execution path.
Inspect errors, logs and actual outputs.
Fix defects and rerun affected tests.

## Phase 6 — Adversarial Review
Look for:
- Missing requirements
- Incorrect assumptions
- Hidden failures
- Regressions
- Performance issues
- Security risks
- Incomplete integrations

## Phase 7 — Delivery
Summarize implementation and evidence.
Clearly distinguish verified behavior from assumptions.
List remaining limitations.
