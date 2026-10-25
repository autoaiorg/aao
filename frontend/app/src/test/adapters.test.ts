import { describe, it, expect, vi, beforeEach } from 'vitest';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { MockAaoDemoAdapter } from '../data/adapters/demo/MockAaoDemoAdapter';

describe('HttpAaoLiveAdapter Contract & Error Handling', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('handles 200 OK with valid projects list', async () => {
    const mockProjects = [
      { id: 'proj-1', name: 'Project One', state: 'ACTIVE', description: 'Desc 1' },
    ];

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => mockProjects,
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.listProjects();

    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') {
      expect(result.origin).toBe('live');
      expect(result.data).toHaveLength(1);
      expect(result.data[0].id).toBe('proj-1');
    }
  });

  it('handles empty projects response as empty DataState, not error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [],
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.listProjects();

    expect(result.kind).toBe('empty');
    if (result.kind === 'empty') {
      expect(result.origin).toBe('live');
    }
  });

  it('handles 401 unauthorized: triggers onUnauthorized and returns forbidden', async () => {
    const onUnauthorized = vi.fn();
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 401,
      ok: false,
      statusText: 'Unauthorized',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      onUnauthorized,
      getToken: () => 'expired-token',
    });
    const result = await adapter.getCurrentPrincipal();

    expect(onUnauthorized).toHaveBeenCalled();
    expect(result.kind).toBe('forbidden');
  });

  it('handles 403 forbidden: returns forbidden DataState without data leakage', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 403,
      ok: false,
      statusText: 'Forbidden',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.getProjectBoard('proj-restricted');

    expect(result.kind).toBe('forbidden');
    if (result.kind === 'forbidden') {
      expect(result.reason).toContain('HTTP 403');
    }
  });

  it('handles 404 not found: returns unavailable DataState with retryable: false', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 404,
      ok: false,
      statusText: 'Not Found',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.getProjectBoard('proj-missing');

    expect(result.kind).toBe('unavailable');
    if (result.kind === 'unavailable') {
      expect(result.retryable).toBe(false);
    }
  });

  it('handles 500 server error: returns error DataState with retryable: true', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 500,
      ok: false,
      statusText: 'Internal Server Error',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.getProjectBoard('proj-crash');

    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.retryable).toBe(true);
      expect(result.code).toBe('HTTP_500');
    }
  });

  it('handles malformed JSON structure: returns schema validation error with retryable: false', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [{ invalid_field_only: true }],
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-mock-token' });
    const result = await adapter.listProjects();

    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.code).toBe('SCHEMA_VALIDATION_ERROR');
      expect(result.retryable).toBe(false);
    }
  });

  it('strictly prevents unauthenticated queries: returns forbidden without calling fetch if token is absent', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const adapter = new HttpAaoLiveAdapter({ requireAuth: true }); // getToken returns null

    const projectsResult = await adapter.listProjects();
    expect(projectsResult.kind).toBe('forbidden');

    const boardResult = await adapter.getProjectBoard('proj-1');
    expect(boardResult.kind).toBe('forbidden');

    const principalResult = await adapter.getCurrentPrincipal();
    expect(principalResult.kind).toBe('forbidden');

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('injects X-Agent-Token header when agent token is present', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [],
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'test-agent-secret-token',
      getAuthRole: () => 'AGENT',
    });

    await adapter.listProjects();

    expect(fetchSpy).toHaveBeenCalled();
    const requestHeaders = (fetchSpy.mock.calls[0][1]?.headers as Record<string, string>) || {};
    expect(requestHeaders['X-Agent-Token']).toBe('test-agent-secret-token');
    expect(requestHeaders['X-CEO-Token']).toBeUndefined();
  });

  it('injects X-CEO-Token header when CEO role is selected', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [],
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'test-ceo-secret-bearer',
      getAuthRole: () => 'CEO',
    });

    await adapter.listProjects();

    expect(fetchSpy).toHaveBeenCalled();
    const requestHeaders = (fetchSpy.mock.calls[0][1]?.headers as Record<string, string>) || {};
    expect(requestHeaders['X-CEO-Token']).toBe('test-ceo-secret-bearer');
    expect(requestHeaders['X-Agent-Token']).toBeUndefined();
  });
});

describe('MockAaoDemoAdapter Fixtures Isolation', () => {
  it('returns demo origin for all responses', async () => {
    const demo = new MockAaoDemoAdapter(0);

    const principal = await demo.getCurrentPrincipal();
    expect(principal.kind).toBe('ready');
    if (principal.kind === 'ready') {
      expect(principal.origin).toBe('demo');
      expect(principal.data.principal_id).toContain('demo');
    }

    const projects = await demo.listProjects();
    expect(projects.kind).toBe('ready');
    if (projects.kind === 'ready') {
      expect(projects.origin).toBe('demo');
      expect(projects.data.length).toBeGreaterThan(0);
      expect(projects.data[0].id).toContain('demo');
    }

    const board = await demo.getProjectBoard('demo-proj-orion');
    expect(board.kind).toBe('ready');
    if (board.kind === 'ready') {
      expect(board.origin).toBe('demo');
      expect(board.data.totalCount).toBeGreaterThan(0);
    }
  });
});
