import { test, expect } from '@playwright/test';

test.describe('Real Browser Functional & Accessibility Suite (Google Chrome)', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to production preview
    await page.goto('/');
  });

  test('TopBar Auth Modal: keyboard navigation, Escape dismissal and automatic focus restoration', async ({ page }) => {
    // 1. Locate "Credencial de Acceso" button
    const authButton = page.getByRole('button', { name: /Credencial de Acceso/i });
    await expect(authButton).toBeVisible();

    // Focus via keyboard and open via Enter key
    await authButton.focus();
    await page.keyboard.press('Enter');

    // 2. Dialog appears
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(page.getByText('Autenticación en Memoria Volátil')).toBeVisible();

    // 3. Focus should automatically be inside the token input
    const tokenInput = page.locator('#auth-token-input');
    await expect(tokenInput).toBeFocused();

    // 4. Press Escape key
    await page.keyboard.press('Escape');

    // 5. Dialog is closed
    await expect(dialog).not.toBeVisible();

    // 6. Focus is automatically restored to the trigger button in real browser DOM
    await expect(authButton).toBeFocused();

    // 7. Open again and test closing via Cancel button
    await authButton.click();
    await expect(dialog).toBeVisible();
    const cancelButton = page.getByRole('button', { name: /Cancelar/i });
    await cancelButton.click();
    await expect(dialog).not.toBeVisible();
    await expect(authButton).toBeFocused();
  });

  test('Kanban Drawer: keyboard activation, Escape dismissal and focus restoration to task card', async ({ page }) => {
    // 1. Switch to DEMO mode to load rich fixtures
    const demoButton = page.getByRole('button', { name: /DEMO/i });
    await demoButton.click();
    await expect(page.getByText(/DEMO · DATOS SIMULADOS/i)).toBeVisible();

    // 2. Select a project from topbar selector to populate Kanban
    const projectSelect = page.locator('#topbar-project-select');
    await expect(projectSelect).toBeVisible();
    await projectSelect.selectOption({ index: 1 });

    // 3. Navigate to Kanban tab via SideNavigation ("Trabajo / Tablero")
    const kanbanNav = page.getByRole('button', { name: /Trabajo \/ Tablero/i });
    await kanbanNav.click();

    // 4. Wait for task cards to be rendered
    const taskCard = page.locator('button[aria-haspopup="dialog"]').first();
    await expect(taskCard).toBeVisible();

    // 5. Focus the task card button using keyboard
    await taskCard.focus();
    await expect(taskCard).toBeFocused();

    // 6. Press Enter to open detail drawer
    await page.keyboard.press('Enter');

    // 7. Drawer dialog is visible
    const drawerDialog = page.getByRole('dialog');
    await expect(drawerDialog).toBeVisible();

    // 8. Press Escape to dismiss drawer
    await page.keyboard.press('Escape');

    // 9. Drawer is closed
    await expect(drawerDialog).not.toBeVisible();

    // 10. Focus is restored to the task card button in the real browser
    await expect(taskCard).toBeFocused();
  });

  test('Session isolation & volatile memory: zero storage leakage in real browser', async ({ page }) => {
    // 1. Verify initially in real browser window that localStorage and sessionStorage are completely clean
    const storageCheck1 = await page.evaluate(() => ({
      localLen: window.localStorage.length,
      sessionLen: window.sessionStorage.length,
      localToken: window.localStorage.getItem('token'),
      sessionToken: window.sessionStorage.getItem('token'),
    }));
    expect(storageCheck1.localLen).toBe(0);
    expect(storageCheck1.sessionLen).toBe(0);
    expect(storageCheck1.localToken).toBeNull();
    expect(storageCheck1.sessionToken).toBeNull();

    // 2. Open auth modal, enter credentials, and authenticate in memory
    const authButton = page.getByRole('button', { name: /Credencial de Acceso/i });
    await authButton.click();

    await page.locator('#auth-token-input').fill('volatile-e2e-secret-bearer');
    await page.getByRole('button', { name: /Autenticar en Memoria/i }).click();

    // 3. User is now authenticated in memory: "Desconectar" button appears
    const logoutBtn = page.getByRole('button', { name: /Desconectar/i });
    await expect(logoutBtn).toBeVisible();

    // 4. Verify storage is STILL completely clean (memory-only retention)
    const storageCheck2 = await page.evaluate(() => ({
      localLen: window.localStorage.length,
      sessionLen: window.sessionStorage.length,
      localToken: window.localStorage.getItem('token'),
      sessionToken: window.sessionStorage.getItem('token'),
    }));
    expect(storageCheck2.localLen).toBe(0);
    expect(storageCheck2.sessionLen).toBe(0);
    expect(storageCheck2.localToken).toBeNull();
    expect(storageCheck2.sessionToken).toBeNull();

    // 5. Click logout and toggle origins: ensure full cleanup and zero cross-origin/session contamination
    await logoutBtn.click();
    await expect(page.getByRole('button', { name: /Credencial de Acceso/i })).toBeVisible();

    // Toggle to DEMO and back to LIVE
    await page.getByRole('button', { name: /DEMO/i }).click();
    await expect(page.getByText(/DEMO · DATOS SIMULADOS/i)).toBeVisible();

    await page.getByRole('button', { name: /LIVE/i }).click();
    await expect(page.getByText(/Sesión LIVE en espera de credencial/i)).toBeVisible();

    // Verify final storage state is still strictly empty
    const storageCheck3 = await page.evaluate(() => ({
      localLen: window.localStorage.length,
      sessionLen: window.sessionStorage.length,
    }));
    expect(storageCheck3.localLen).toBe(0);
    expect(storageCheck3.sessionLen).toBe(0);
  });
});
