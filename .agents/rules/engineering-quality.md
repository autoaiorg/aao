
# Engineering Quality Standards

## Objective

Produce complete, maintainable, production-oriented software.

## Mandatory behavior

- Inspect the existing codebase before modifying it.
- Identify existing architecture, conventions and dependencies.
- Prefer robust solutions over the shortest implementation.
- Implement real behavior, not demonstrations disguised as features.
- Preserve established architecture unless a change is justified.
- Use existing project abstractions when appropriate.
- Do not introduce unnecessary dependencies or abstractions.

## Implementation

- Handle expected error conditions and edge cases.
- Include input validation at trust boundaries.
- Separate responsibilities and maintain coherent interfaces.
- Avoid hardcoded mock data in production execution paths.
- Do not replace functional implementations with stubs.
- Do not silently remove existing features.
- Avoid broad exception handling that hides failures.
- Consider performance, security, accessibility and maintainability where relevant.

## Verification

- Define testable acceptance criteria.
- Add or update relevant automated tests.
- Run the available formatting, linting, type-checking and test commands.
- Execute the affected functionality where feasible.
- Inspect actual command results and application behavior.
- Fix discovered defects before reporting completion.
- Never claim a test passed without running it.

## Completion contract

Report:

1. What was implemented.
2. What files changed.
3. What verification was executed.
4. What passed or failed.
5. Remaining limitations and risks.

Never describe unimplemented or unverified functionality as complete.
