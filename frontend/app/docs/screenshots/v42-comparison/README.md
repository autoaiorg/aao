# Office V4.2 / V4.3 Visual Realism & Navigation Evidence

All captures use the browser-driven `e2e/screenshots.spec.ts` flow executed in a real Chromium browser environment (1600x1000 desktop viewport):

- `01-office-3d-overview.png`: General overview of the continuous corporate campus with ACESFilmic tone mapping, soft PCF contact shadows, and naturalistic lighting.
- `02-office-3d-department-eng.png`: Zoomed perspective of Engineering neighborhood with procedural wood grain desks, ultrawide monitors with syntax-highlighted IDE code, and ergonomic chairs.
- `03-office-agent-inspector.png`: Focused agent inspection showing contextual agent details, assignment metadata, and telemetry status.
- `04-office-2d-plan.png`: Accessible 2D campus plan verifying WCAG 2.2 AA non-WebGL fallback.
- `office-overview-neighborhood-floors.png`: Campus floor slab with fine stone aggregate and soft acoustic carpet neighborhood finishes.
- `office-audit-neighborhood.png`: Dedicated audit enclave with manifestation bands and open acoustic baffles.
- `office-operational-department-close.png`: Workstation close-up with seated typing kinematics (hands on keyboard, attentive posture).
- `office-agent-selection-view.png`: WebGL viewport close-up verifying close inspection distance (<= 3.5m).
- `office-tactical-hud-deck.png`: Full tactical video-game HUD layout including bottom deck, 2D radar minimap, left sector roster dock, and top ribbon.
- `office-reception-arrival.png`: Main entrance and reception lobby arrival perspective showing desk, canopy, and articulated receptionist NPC.
- `office-topdown-tactical.png`: Top-down tactical overview framing the entire campus structure and circulation network.

### Visual Quality & Architectural Realism Improvements
1. **PBR Color Management & Tone Mapping**: Integrated `ACESFilmicToneMapping` with exposure 1.0 and SRGB output space, preventing color burn-out and preserving highlight contrast.
2. **Contact Shadows & Directional Light**: Configured directional light with `normalBias: 0.02`, `bias: -0.0004`, and `radius: 2.0` for soft architectural shadows without acne.
3. **Procedural Materials**: Added procedural wood grain for desks/tables, procedural acoustic weave for carpets, and standby terminal display for unassigned bays.
4. **Articulated Humanoid Ambient NPCs**: Receptionist, copy-room courier, and runner NPCs upgraded to full articulated humanoid character rigs with professional corporate attire, eliminating toy-like capsule geometry.
5. **Camera Presets & Navigation**: Added 'reception' viewpoint, 'top-down' tactical preset, and tuned 'agent-focus' for close-up ergonomic inspection.
