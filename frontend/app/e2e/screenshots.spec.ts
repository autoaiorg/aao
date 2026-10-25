import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';

test('Capture real screenshots of F4.7 and F4.8 Office', async ({ page }) => {
  const screenshotsDir = path.resolve(process.cwd(), 'docs/screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  // 1. Load app in DEMO mode to showcase 3D office
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Switch to DEMO mode
  const demoButton = page.getByRole('button', { name: /DEMO/i });
  await demoButton.click();

  // Navigate to Oficina Virtual
  const officeNav = page.getByRole('button', { name: 'Oficina Virtual' });
  await officeNav.click();

  // Wait for 3D toolbar to appear
  const toolbar = page.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
  await toolbar.waitFor({ state: 'visible' });
  await page.waitForTimeout(1000);

  // Capture 1: General 3D Overview
  await page.screenshot({ path: path.join(screenshotsDir, '01-office-3d-overview.png'), fullPage: true });

  // Capture 2: Zoomed Department (ENG)
  const engChip = toolbar.getByRole('button', { name: /\[ENG\] Ingeniería/i });
  await engChip.click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(screenshotsDir, '02-office-3d-department-eng.png'), fullPage: true });

  // Capture 3: Agent Inspector
  const sidebar = page.locator('aside');
  const agentButton = sidebar.getByRole('button', { name: /Especialista en Frontend/i });
  if (await agentButton.isVisible()) {
    await agentButton.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotsDir, '03-office-agent-inspector.png'), fullPage: true });
  }

  // Capture 4: Accessible 2D Plan
  const plan2dBtn = toolbar.getByRole('button', { name: /Plano 2D Accesible/i });
  await plan2dBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(screenshotsDir, '04-office-2d-plan.png'), fullPage: true });
});
