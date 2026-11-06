
# AAO Frontend Engineering Constitution

## Mission

Develop a production-quality frontend for Autonomous AI Organization.

AAO is an operational management system, not a demo,
game, conceptual mockup or decorative dashboard.

## Scope and ownership

- Work only within the authorized frontend scope.
- Do not modify backend, runtime or governance services.
- Follow existing API contracts.
- Do not invent backend capabilities.
- Preserve the classic Control Center.
- Work in the designated worktree and branch.
- Submit changes through a reviewable pull request.

## Engineering quality

- Inspect the existing implementation before making changes.
- Preserve established components and working behavior.
- Use strict TypeScript and explicit data contracts.
- Maintain separation of rendering, application state,
  domain logic and API communication.
- Implement loading, error, empty and recovery states.
- Do not introduce fake functionality or decorative controls.
- Do not claim completion without reproducible evidence.

## Operational truth

- LIVE data must originate from authorized backend responses.
- DEMO data must remain explicitly identifiable.
- Never represent simulated agent activity as real.
- Separate identity, role, assignment, session and LLM.
- Treat visual selection as distinct from execution authority.
- Enforce authorization through established backend contracts.
- Never infer permission from UI visibility.

## Spatial interface

- Use one coherent spatial coordinate system.
- Preserve camera, navigation and selection behavior.
- Separate spatial presentation from business state.
- Maintain the existing window and inspector systems.
- Implement adaptive labels and level of detail.
- Avoid decorative 3D objects without semantic purpose.

## Visual quality

Target: premium, realistic enterprise digital twin.

Avoid:

- Cartoon or toy-like appearance.
- Low-poly aesthetics as final design.
- Excessive neon and bloom.
- Generic sci-fi holograms.
- Random decorative elements.
- Unrealistic proportions and materials.
- Visually impressive but functionally empty features.

Prefer:

- Architectural coherence.
- Physically plausible lighting.
- Refined PBR materials.
- Clear visual hierarchy.
- Subtle motion.
- Legible information at multiple zoom levels.
- Consistent interaction feedback.

## Accessibility

Maintain a functional 2D alternative.
Target WCAG 2.2 AA.
Support keyboard navigation and reduced motion.

## Verification

For every substantial change:

1. Run frontend build and static checks.
2. Execute relevant automated tests.
3. Verify affected interaction flows.
4. Check API integration against real contracts.
5. Check performance regressions.
6. Capture visual evidence where applicable.
7. Verify existing features remain functional.
8. Report failures and limitations explicitly.

Never declare a feature production-ready solely
because it compiles or looks correct.

## Delivery

Provide:

- Modified files
- Requirements satisfied
- Tests and commands executed
- Actual results
- Screenshots or runtime evidence
- Known limitations
- Pull request for independent review
