import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
});

describe('CEO HttpOnly browser session adapter', () => {
  afterEach(() => vi.restoreAllMocks());

  it('exchanges the bearer once and returns only the in-memory CSRF token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      authenticated: true, csrf_token: 'c'.repeat(48), expires_in_seconds: 43200,
    }) as Response);
    const result = await new HttpAaoLiveAdapter().exchangeCeoBearerForSession('one-time-bearer');
    expect(result.kind).toBe('ready');
    expect(fetchMock).toHaveBeenCalledWith('/v1/auth/ceo/session', expect.objectContaining({
      method: 'POST', credentials: 'include', headers: expect.objectContaining({ 'X-CEO-Token': 'one-time-bearer' }),
    }));
  });

  it('sends cookie-authenticated requests with CSRF and without a bearer header', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      id: '00000000-0000-4000-8000-000000000001', sender: 'CEO', body: 'Test', related_work_id: null, created_at: 'now',
    }) as Response);
    const adapter = new HttpAaoLiveAdapter({
      requireAuth: true, getAuthRole: () => 'CEO', getCeoCookieSession: () => true,
      getCsrfToken: () => 'c'.repeat(48),
    });
    const result = await adapter.appendCEOConversationMessage('00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000003', 'Test');
    expect(result.kind).toBe('ready');
    const [, options] = fetchMock.mock.calls[0];
    expect(options?.credentials).toBe('include');
    expect(options?.headers).not.toHaveProperty('X-CEO-Token');
    expect(options?.headers).toHaveProperty('X-AAO-CSRF', 'c'.repeat(48));
  });

  it('allows the LIVE organization projection to use a restored CEO cookie session', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]) as Response);
    const adapter = new HttpAaoLiveAdapter({
      requireAuth: true, getAuthRole: () => 'CEO', getCeoCookieSession: () => true,
    });

    await adapter.getOrganizationStructure();

    expect(fetchMock).toHaveBeenCalledWith('/v1/organization', expect.objectContaining({ credentials: 'include' }));
  });

  it('allows CEO overview queries with a restored cookie session and no in-memory bearer', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]) as Response);
    const adapter = new HttpAaoLiveAdapter({
      requireAuth: true, getAuthRole: () => 'CEO', getCeoCookieSession: () => true,
    });

    const overview = await adapter.getCeoOverview();

    expect(overview.projects.kind).toBe('empty');
    expect(overview.projects.kind).not.toBe('forbidden');
    expect(fetchMock).toHaveBeenCalledWith('/v1/projects', expect.objectContaining({ credentials: 'include' }));
  });

  it('describes a restored CEO session as cookie-authenticated, not bearer-authenticated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]) as Response);
    const adapter = new HttpAaoLiveAdapter({
      requireAuth: true, getAuthRole: () => 'CEO', getCeoCookieSession: () => true,
    });

    const principal = await adapter.getCurrentPrincipal();

    expect(principal.kind).toBe('ready');
    if (principal.kind === 'ready') {
      expect(principal.data.principal_id).toContain('sesión de navegador');
      expect(principal.data.authMethod).toContain('Cookie de sesión');
    }
  });

  it('requests server-side revocation with the in-memory CSRF token', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ logged_out: true }) as Response);
    const result = await new HttpAaoLiveAdapter().revokeCeoBrowserSession('c'.repeat(48));
    expect(result.kind).toBe('ready');
    expect(fetchMock).toHaveBeenCalledWith('/v1/auth/ceo/logout', expect.objectContaining({
      method: 'POST', credentials: 'include', headers: expect.objectContaining({ 'X-AAO-CSRF': 'c'.repeat(48) }),
    }));
  });
});
