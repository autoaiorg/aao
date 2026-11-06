import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';

test('Capture real screenshots of F4.7 and F4.8 Office', async ({ page }) => {
  // This capture exercises WebGL scene initialization, multi-view camera presets,
  // HUD transitions and post-selection camera interaction; give ample timeout for 8+ frames.
  test.setTimeout(150_000);
  // Match a usable desktop viewport so the actual WebGL area, not just the HUD,
  // occupies a meaningful portion of the evidence frame.
  await page.setViewportSize({ width: 1600, height: 1000 });
  const targetDir = path.resolve(process.cwd(), 'frontend/app/docs/screenshots');
  const screenshotsDir = fs.existsSync(targetDir) ? targetDir : path.resolve(process.cwd(), 'docs/screenshots');
  const v42EvidenceDir = path.join(screenshotsDir, 'v42-comparison');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }
  fs.mkdirSync(v42EvidenceDir, { recursive: true });

  // 1. Load app in DEMO mode to showcase 3D office
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Switch to DEMO mode
  const demoButton = page.getByRole('button', { name: /DEMO/i });
  await demoButton.click();

  // The system panels are behind the collapsible side navigation.
  await page.getByRole('button', { name: 'Alternar menú lateral' }).click();
  const officeNav = page.getByRole('button', { name: 'Oficina Virtual 3D' });
  await officeNav.click();

  // The legacy toolbar is available in classic layout; the tactical HUD hides it.
  const hudToggle = page.getByRole('button', { name: /HUD Videojuego/i });
  if (await hudToggle.isVisible()) await hudToggle.click();

  // Wait for 3D toolbar to appear
  const toolbar = page.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
  await toolbar.waitFor({ state: 'visible' });
  await page.waitForTimeout(1000);

  // Capture 1: General 3D Overview
  await page.screenshot({ path: path.join(screenshotsDir, '01-office-3d-overview.png'), fullPage: false });
  await page.screenshot({
    path: path.join(v42EvidenceDir, 'office-overview-neighborhood-floors.png'),
    fullPage: false,
  });

  // Capture the semantically selected Audit neighborhood separately from its sign.
  const auditChip = toolbar.getByRole('button', { name: /\[AUDIT\]/i });
  await auditChip.click({ force: true });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(v42EvidenceDir, 'office-audit-neighborhood.png'), fullPage: false });

  // Capture 2: Zoomed Department (ENG)
  const engChip = toolbar.getByRole('button', { name: /\[ENG\] Ingeniería/i });
  await engChip.click({ force: true });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(screenshotsDir, '02-office-3d-department-eng.png'), fullPage: false });

  // Capture 3: Agent Inspector
  const sidebar = page.locator('aside');
  const agentButton = sidebar.getByRole('button', { name: /Especialista en Frontend/i });
  if (await agentButton.isVisible()) {
    await agentButton.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotsDir, '03-office-agent-inspector.png'), fullPage: false });
    const officeCanvas = page.locator('canvas').first();
    const canvasBounds = await officeCanvas.boundingBox();
    if (!canvasBounds) throw new Error('3D office canvas has no visible bounds');
    const canvasCenter = {
      x: canvasBounds.x + canvasBounds.width / 2,
      y: canvasBounds.y + canvasBounds.height / 2,
    };
    await page.mouse.move(canvasCenter.x, canvasCenter.y);
    // Exercise the same wheel navigation users use, with a rendered frame
    // between inputs so the scene's eased camera can settle at close range.
    for (let step = 0; step < 16; step += 1) {
      await page.mouse.wheel(0, -120);
      await page.waitForTimeout(90);
    }
    const inspectionDistance = Number(await officeCanvas.getAttribute('data-camera-distance'));
    if (!Number.isFinite(inspectionDistance) || inspectionDistance > 3.5) {
      throw new Error(`Agent close-up did not reach the inspection distance (got ${inspectionDistance})`);
    }
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-operational-department-close.png'),
      fullPage: false,
    });
    // Capture a genuine browser close-up of the selected agent, not just the
    // surrounding department. Keep this separate so posture and label
    // occlusion can be reviewed at the scale where they are easiest to spot.
    await page.waitForTimeout(900);
    // Exclude application chrome from this close study: leave the same WebGL
    // viewport and camera framing intact, but use all captured pixels for the
    // avatar, desk and chair so posture can be inspected at useful scale.
    await officeCanvas.waitFor({ state: 'visible' });
    await officeCanvas.screenshot({
      path: path.join(v42EvidenceDir, 'office-agent-selection-view.png'),
      animations: 'disabled',
    });
  }

  // Capture 4: Accessible 2D Plan
  const plan2dBtn = toolbar.getByRole('button', { name: /Plano 2D Accesible/i });
  await plan2dBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(screenshotsDir, '04-office-2d-plan.png'), fullPage: false });

  // Switch back to 3D View to capture Top-Down and Tactical HUD evidence
  const view3dBtn = toolbar.getByRole('button', { name: /Vista 3D/i });
  await view3dBtn.click();
  await page.waitForTimeout(800);

  // Switch to Video Game HUD layout to exercise the full spatial interface
  const hudButton = page.getByRole('button', { name: /Cambiar a HUD Videojuego/i });
  if (await hudButton.isVisible()) {
    await hudButton.click();
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-tactical-hud-deck.png'),
      fullPage: false,
    });
  }

  // Expand controls drawer if collapsed
  const controlsDrawer = page.getByRole('button', { name: /Controles/i });
  if (await controlsDrawer.isVisible()) {
    const isExpanded = await controlsDrawer.getAttribute('aria-expanded');
    if (isExpanded === 'false') {
      await controlsDrawer.click();
      await page.waitForTimeout(400);
    }
  }

  // Exercise Reception camera preset if available in the top ribbon
  const receptionPresetBtn = page.getByRole('button', { name: /Recepción/i });
  if (await receptionPresetBtn.isVisible()) {
    await receptionPresetBtn.click();
    await page.waitForTimeout(1200);
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-reception-arrival.png'),
      fullPage: false,
    });
  }

  // Exercise Top-Down camera preset
  const topDownPresetBtn = page.getByRole('button', { name: /Cenital/i });
  if (await topDownPresetBtn.isVisible()) {
    await topDownPresetBtn.click();
    await page.waitForTimeout(1200);
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-topdown-tactical.png'),
      fullPage: false,
    });
  }
});
