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

  it('provides structured organization and segregated agent roster in demo mode', async () => {
    const demo = new MockAaoDemoAdapter(0);
    const org = await demo.getOrganizationStructure();

    expect(org.kind).toBe('ready');
    if (org.kind === 'ready') {
      expect(org.origin).toBe('demo');
      expect(org.data.units.length).toBeGreaterThan(0);
      expect(org.data.agents.length).toBeGreaterThan(0);
      expect(org.data.totalStandingAgents).toBeGreaterThan(0);
      expect(org.data.totalEphemeralAgents).toBeGreaterThan(0);

      // Verify segregation: standing agents vs ephemeral agents
      const standing = org.data.agents.filter((a) => a.type === 'STANDING');
      const ephemeral = org.data.agents.filter((a) => a.type === 'EPHEMERAL');
      expect(standing.length).toBe(org.data.totalStandingAgents);
      expect(ephemeral.length).toBe(org.data.totalEphemeralAgents);

      // Verify realistic heartbeat presence without fabricating active heartbeats on unavailable agents
      const unavailable = org.data.agents.filter((a) => a.heartbeatStatus === 'UNAVAILABLE');
      expect(unavailable.length).toBeGreaterThan(0);
      for (const a of unavailable) {
        expect(a.lastHeartbeatAt).toBeNull();
      }
    }
  });

  it('retrieves detailed agent info or returns error when agent is not found', async () => {
    const demo = new MockAaoDemoAdapter(0);

    const found = await demo.getAgentDetails('agent-demo-fe-specialist');
    expect(found.kind).toBe('ready');
    if (found.kind === 'ready') {
      expect(found.data.name).toContain('Antigravity');
      expect(found.data.authorityBoundary).toContain('frontend/app/');
    }

    const missing = await demo.getAgentDetails('agent-nonexistent');
    expect(missing.kind).toBe('error');
    if (missing.kind === 'error') {
      expect(missing.code).toBe('AGENT_NOT_FOUND');
    }
  });
});

describe('HttpAaoLiveAdapter F3 & F4.8 Live Aggregation Handling', () => {
  it('progressively aggregates live organization from projects and boards when /v1/organization is absent', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    // Mock fetch for /v1/organization (404), /v1/projects (200), /v1/principals/me (200), /v1/projects/proj-1/board (200)
    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/v1/principals/me')) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            principal_id: 'ceo-user',
            kind: 'CEO',
            auth_method: 'token',
            enabled: true,
            grants: [{ project_id: 'proj-1', capability: 'MANDATE_APPROVE', expires_at: null, active: true }],
          }),
        } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            { id: 'proj-1', name: 'Project Orion', state: 'ACTIVE' },
          ],
        } as Response;
      }
      if (u.includes('/board')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            {
              id: 'task-101',
              title: 'Implement Core Security',
              status: 'IN_PROGRESS',
              executions: [
                {
                  id: 'exec-1',
                  status: 'RUNNING',
                  worker_id: 'worker-eng-codex',
                  attempts: 1,
                  created_at: '2026-10-25T12:00:00Z',
                },
              ],
            },
          ],
        } as Response;
      }
      return { status: 404, ok: false, json: async () => ({}) } as Response;
    });

    const org = await live.getOrganizationStructure();

    expect(org.kind).toBe('ready');
    if (org.kind === 'ready') {
      expect(org.origin).toBe('live');
      expect(org.data.units).toHaveLength(6);
      expect(org.data.agents.length).toBeGreaterThanOrEqual(2);

      // Verify CEO agent mapped to EXEC
      const ceoAgent = org.data.agents.find((a) => a.id === 'ceo-user');
      expect(ceoAgent).toBeDefined();
      expect(ceoAgent?.unitId).toBe('unit-exec');
      expect(ceoAgent?.heartbeatStatus).toBe('UNKNOWN'); // Fail-closed: no fake heartbeat

      // Verify Codex worker mapped to ENG with EJECUTANDO operational state
      const codexAgent = org.data.agents.find((a) => a.id === 'worker-eng-codex');
      expect(codexAgent).toBeDefined();
      expect(codexAgent?.unitId).toBe('unit-eng');
      expect(codexAgent?.operationalState).toBe('EJECUTANDO');
      expect(codexAgent?.heartbeatStatus).toBe('UNKNOWN');
      expect(codexAgent?.currentAssignments).toHaveLength(1);
    }
  });

  it('retrieves agent details from live aggregated roster or returns unavailable if not found', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization') || u.includes('/v1/agents/')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/v1/principals/me')) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            principal_id: 'ceo-user',
            kind: 'CEO',
            auth_method: 'token',
            enabled: true,
            grants: [],
          }),
        } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return { status: 200, ok: true, json: async () => [] } as Response;
      }
      return { status: 404, ok: false, json: async () => ({}) } as Response;
    });

    // Found agent
    const details = await live.getAgentDetails('ceo-user');
    expect(details.kind).toBe('ready');
    if (details.kind === 'ready') {
      expect(details.data.id).toBe('ceo-user');
      expect(details.data.unitId).toBe('unit-exec');
    }

    // Missing agent
    const missing = await live.getAgentDetails('non-existent-agent');
    expect(missing.kind).toBe('unavailable');
    if (missing.kind === 'unavailable') {
      expect(missing.reason).toContain('no fue localizado');
      expect(missing.retryable).toBe(false);
    }
  });
});
