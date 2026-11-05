# Office V4.2 visual comparison

Both captures use the browser-driven `e2e/screenshots.spec.ts` F4.7 overview flow at the same viewport and default camera framing.

- `office-overview-before.png`: repository screenshot from the pre-envelope revision `1a06313b1239306328b658f65c0e62eb348e112d`.
- `office-overview-after.png`: fresh real-browser capture with the envelope/facade and aligned navigation-entry changes in the current V4.2 worktree. The test passed after capture.

Current browser captures also include the soft neighborhood floor finish, the selected Audit neighborhood, and a zoomed operational Engineering neighborhood. `office-agent-selection-view.png` contains only the WebGL viewport (not application chrome), captured after selecting an Engineering agent and using wheel zoom. It is still a department-scale image and does **not** prove a sufficiently detailed working-posture close-up.

Still missing: an Agora/conversation view, a close-up proving an agent's working posture, a LIVE-empty/unconstituted capture, a top-down view, and browser-driven organization cases for one/three/eight agents plus add/remove/reorganization.

`office-audit-neighborhood.png` is captured separately by the browser screenshot test so the acoustic treatment can be inspected independently from the overall view.
