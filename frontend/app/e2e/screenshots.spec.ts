import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';

test('Capture real screenshots of F4.7 and F4.8 Office', async ({ page }) => {
  // This capture exercises WebGL scene initialization and post-selection camera
  // interaction; its real-browser cost exceeds Playwright's 30s default here.
  test.setTimeout(90_000);
  // Match a usable desktop viewport so the actual WebGL area, not just the HUD,
  // occupies a meaningful portion of the evidence frame.
  await page.setViewportSize({ width: 1600, height: 1000 });
  const screenshotsDir = path.resolve(process.cwd(), 'docs/screenshots');
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
    const zoomIn = toolbar.getByRole('button', { name: 'Acercar zoom' });
    for (let step = 0; step < 3; step += 1) await zoomIn.click({ force: true });
    await page.waitForTimeout(1200);
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-operational-department-close.png'),
      fullPage: false,
    });
    // Capture a genuine browser close-up of the selected agent, not just the
    // surrounding department. Keep this separate so posture and label
    // occlusion can be reviewed at the scale where they are easiest to spot.
    for (let step = 0; step < 16; step += 1) {
      if (!(await zoomIn.isVisible()) || !(await zoomIn.isEnabled())) break;
      try {
        await zoomIn.click({ force: true, timeout: 2_000, noWaitAfter: true });
      } catch {
        // Browser screenshot evidence is more useful than failing because React
        // is still settling after an earlier camera event; retain the closest
        // successfully reached framing and capture it below.
        break;
      }
    }
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(v42EvidenceDir, 'office-agent-working-close.png'),
      fullPage: false,
    });
  }

  // Capture 4: Accessible 2D Plan
  const plan2dBtn = toolbar.getByRole('button', { name: /Plano 2D Accesible/i });
  await plan2dBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(screenshotsDir, '04-office-2d-plan.png'), fullPage: false });
});
