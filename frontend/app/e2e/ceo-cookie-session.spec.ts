import { expect, test } from '@playwright/test';

test('Secure HttpOnly __Host CEO cookie is accepted on localhost HTTP and inaccessible to page JS', async ({ page }) => {
  let receivedCookie = '';
  await page.route('**/v1/auth/ceo/session/csrf', (route) => route.fulfill({ status: 401, body: 'unauthorized' }));
  await page.route('**/v1/auth/ceo/session', (route) => route.fulfill({
    status: 200,
    headers: { 'Set-Cookie': '__Host-aao_ceo_session=test-only; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=43200' },
    contentType: 'application/json',
    body: JSON.stringify({ authenticated: true, csrf_token: 'c'.repeat(48), expires_in_seconds: 43200 }),
  }));
  await page.route('**/v1/auth/ping', async (route) => {
    receivedCookie = route.request().headers().cookie || '';
    await route.fulfill({ status: 200, body: 'ok' });
  });

  await page.goto('http://localhost:4173');
  await page.evaluate(() => fetch('/v1/auth/ceo/session', { method: 'POST' }));
  expect(await page.evaluate(() => document.cookie)).not.toContain('__Host-aao_ceo_session');
  await page.evaluate(() => fetch('/v1/auth/ping'));
  expect(receivedCookie).toContain('__Host-aao_ceo_session=test-only');
});
