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

  test('F3 Organization & Agent Structure: hierarchy, filtering, drawer Escape dismissal and focus restoration', async ({ page }) => {
    // 1. Navigate to "Organización" in LIVE mode
    const orgNav = page.getByRole('button', { name: 'Organización' });
    await expect(orgNav).toBeVisible();
    await orgNav.click();

    // 2. In LIVE mode, verify honest technical notice is shown (no fake endpoints fabricated)
    await expect(page.getByText(/Organización y Estructura de Agentes/i)).toBeVisible();
    await expect(page.getByText(/El núcleo canónico de AAO no expone aún endpoints/i)).toBeVisible();

    // 3. Switch to DEMO mode to load rich organizational structure
    const demoButton = page.getByRole('button', { name: /DEMO/i });
    await demoButton.click();
    await expect(page.getByText(/DEMO · DATOS SIMULADOS/i)).toBeVisible();

    // 4. Verify metrics row
    await expect(page.getByText('Unidades Organizativas')).toBeVisible();
    await expect(page.getByText('Plantilla Fija (Standing)')).toBeVisible();
    await expect(page.getByText('Agentes Efímeros (Temporales)')).toBeVisible();

    // 5. Verify Organigram shows executive and subordinate units
    await expect(page.getByText(/Dirección Ejecutiva y Secretaría General/i)).toBeVisible();
    await expect(page.getByText(/Arquitectura de Sistemas y Protocolos/i)).toBeVisible();

    // 6. Switch to "Plantilla y Agentes" tab
    const agentsTab = page.getByRole('tab', { name: /Plantilla y Agentes/i });
    await agentsTab.click();

    // 7. Verify search filtering
    const searchInput = page.locator('#agent-search-input');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('Antigravity');
    await expect(page.getByText(/Especialista en Frontend y Accesibilidad \(Antigravity\)/i)).toBeVisible();
    await expect(page.getByText(/Claude Core/i)).not.toBeVisible();

    // Clear search
    await searchInput.clear();
    await expect(page.getByText(/Claude Core/i)).toBeVisible();

    // 8. Open Agent Detail Drawer via keyboard
    const detailBtn = page.getByRole('button', {
      name: /Ver ficha técnica de Especialista en Frontend y Accesibilidad \(Antigravity\)/i,
    });
    await expect(detailBtn).toBeVisible();
    await detailBtn.focus();
    await expect(detailBtn).toBeFocused();
    await page.keyboard.press('Enter');

    // 9. Verify drawer dialog is open and accessible
    const drawerDialog = page.getByRole('dialog');
    await expect(drawerDialog).toBeVisible();
    await expect(page.getByText(/Límite Constitucional de Autoridad/i)).toBeVisible();
    await expect(page.getByText(/Confinado estrictamente a frontend\/app\//i)).toBeVisible();

    // 10. Press Escape key to dismiss drawer
    await page.keyboard.press('Escape');
    await expect(drawerDialog).not.toBeVisible();

    // 11. Focus restored to trigger button in real browser DOM
    await expect(detailBtn).toBeFocused();

    // 12. Switch to "Puestos y Capacidades" matrix tab
    const matrixTab = page.getByRole('tab', { name: /Puestos y Capacidades/i });
    await matrixTab.click();
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByText(/Matriz de Puestos y Capacidades:/i)).toBeVisible();
  });

  test('F4 Virtual Office 3D: WebGL / accessible 2D fallback, room & agent selection, sidebar inspection and cross-navigation', async ({ page }) => {
    // 1. Navigate to "Oficina Virtual" in LIVE mode
    const officeNav = page.getByRole('button', { name: 'Oficina Virtual' });
    await expect(officeNav).toBeVisible();
    await officeNav.click();

    // 2. In LIVE mode, verify honest technical notice is displayed
    await expect(page.getByRole('heading', { level: 2, name: /Oficina Virtual 3D · AAO/i })).toBeVisible();
    await expect(page.getByText(/SIN CONEXIÓN AL NÚCLEO EN LIVE \(F3\/F4\)/i)).toBeVisible();

    // 3. Switch to DEMO mode
    const demoButton = page.getByRole('button', { name: /DEMO/i });
    await demoButton.click();
    await expect(page.getByText(/DEMO · SIMULACIÓN 3D ACTIVA/i)).toBeVisible();

    // 4. Verify Toolbar is present
    const toolbar = page.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
    await expect(toolbar).toBeVisible();

    // 5. Check mode switcher buttons in toolbar
    const view3dBtn = toolbar.getByRole('button', { name: /Vista 3D \(WebGL\)/i });
    const plan2dBtn = toolbar.getByRole('button', { name: /Plano 2D Accesible/i });
    await expect(view3dBtn).toBeVisible();
    await expect(plan2dBtn).toBeVisible();

    // 6. Switch to 2D Plan
    await plan2dBtn.click();
    const plan2dRegion = page.getByRole('region', { name: /Plano 2D accesible de la oficina de AAO/i });
    await expect(plan2dRegion).toBeVisible();

    // Verify all 6 departments appear in 2D blueprint map
    await expect(page.getByRole('heading', { level: 4, name: /Dirección Ejecutiva/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 4, name: /Gobernanza Constitucional/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 4, name: /Auditoría Independiente/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 4, name: /Arquitectura de Sistemas/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 4, name: /Ingeniería de Software/i })).toBeVisible();
    await expect(page.getByRole('heading', { level: 4, name: /Operaciones de Infraestructura/i })).toBeVisible();

    // 7. Select department via toolbar chip
    const auditChip = toolbar.getByRole('button', { name: /\[AUDIT\] Auditoría/i });
    await auditChip.click();

    // 8. Verify contextual sidebar updates
    const sidebar = page.locator('aside');
    await expect(sidebar.getByRole('heading', { level: 3, name: /Auditoría Independiente y Verificación/i })).toBeVisible();

    // 9. Inspect agent in sidebar
    const agentButton = sidebar.getByRole('button', { name: /Auditor Independiente Principal/i });
    await expect(agentButton).toBeVisible();
    await agentButton.click();

    // Contextual inspector card appears
    const inspector = page.getByRole('region', { name: /Ficha técnica de Auditor Independiente Principal/i });
    await expect(inspector).toBeVisible();
    await expect(inspector.getByText(/Límite de Autoridad:/i)).toBeVisible();
    await expect(inspector.getByText(/Independencia funcional garantizada/i)).toBeVisible();

    // Close agent card
    await inspector.getByRole('button', { name: /Cerrar ficha de agente/i }).click();
    await expect(inspector).not.toBeVisible();

    // 10. Test cross-navigation shortcut ("Ver Organigrama")
    const orgShortcut = sidebar.getByRole('button', { name: /Ver Organigrama/i });
    await expect(orgShortcut).toBeVisible();
    await orgShortcut.click();

    // View changes to Organization
    await expect(page.getByRole('heading', { level: 2, name: /Organización y Estructura de Agentes/i })).toBeVisible();

    // 11. Navigate back to "Oficina Virtual", switch 2D -> 3D and verify single active canvas with no orphan leaks
    await officeNav.click();
    await expect(toolbar).toBeVisible();
    await view3dBtn.click();
    const canvasCount = await page.evaluate(() => document.querySelectorAll('canvas').length);
    expect(canvasCount).toBe(1);
    const canvasBox = await page.locator('canvas').boundingBox();
    expect(canvasBox).not.toBeNull();
    expect(canvasBox!.width).toBeGreaterThan(400);
    expect(canvasBox!.height).toBeGreaterThan(400);
  });
});
