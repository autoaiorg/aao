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

describe('HttpAaoLiveAdapter F3 & F4.8 Live Aggregation Handling (Negative Regressions & Verifiable Evidence)', () => {
  it('strictly rejects heuristics: does NOT infer departments or types from worker_id strings and maps to unknown unit', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

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
            grants: [],
          }),
        } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return {
          status: 200,
          ok: true,
          json: async () => [{ id: 'proj-1', name: 'Project Orion', state: 'ACTIVE' }],
        } as Response;
      }
      if (u.includes('/board')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            {
              id: 'task-101',
              title: 'Task with workers',
              status: 'READY',
              executions: [
                {
                  id: 'exec-hist-1',
                  status: 'ASSIGNED',
                  worker_id: 'worker-eng-codex', // Has 'eng' in name, but MUST NOT be assigned to unit-eng!
                  attempts: 1,
                  created_at: '2026-10-25T12:00:00Z',
                },
                {
                  id: 'exec-hist-2',
                  status: 'ASSIGNED',
                  worker_id: 'subagent-ops-sentinel', // Has 'ops' and 'subagent', but MUST NOT be unit-ops or EPHEMERAL!
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
      // 1. Point 1 Negative Check: workers with 'eng' and 'ops' MUST NOT be mapped to unit-eng or unit-ops
      const codex = org.data.agents.find((a) => a.id === 'worker-eng-codex');
      expect(codex).toBeDefined();
      expect(codex?.unitId).toBe('unit-unassigned');
      expect(codex?.unitName).toBe('Departamento desconocido');

      const sentinel = org.data.agents.find((a) => a.id === 'subagent-ops-sentinel');
      expect(sentinel).toBeDefined();
      expect(sentinel?.unitId).toBe('unit-unassigned');
      expect(sentinel?.unitName).toBe('Departamento desconocido');

      // 2. Point 3 Negative Check: type must be UNKNOWN, not inferred from 'worker' or 'subagent'
      expect(codex?.type).toBe('UNKNOWN');
      expect(sentinel?.type).toBe('UNKNOWN');

      // 3. Point 4 Negative Check: leadAgentId must be null for all units
      for (const unit of org.data.units) {
        expect(unit.leadAgentId).toBeNull();
      }

      // 4. CEO Point 3 (PR #122 review): CEO principal MUST NOT be deduced to unit-exec or STANDING
      const ceo = org.data.agents.find((a) => a.id === 'ceo-user');
      expect(ceo).toBeDefined();
      expect(ceo?.unitId).toBe('unit-unassigned');
      expect(ceo?.unitName).toBe('Departamento desconocido');
      expect(ceo?.type).toBe('UNKNOWN');
      expect(ceo?.roleTitle).toContain('CEO');
      expect(ceo?.lastEvidenceAt).toBeNull();
    }
  });

  it('strictly validates execution vigency: no fixed 5-minute window; requires backend accredited active lease', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/v1/principals/me')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return {
          status: 200,
          ok: true,
          json: async () => [{ id: 'proj-1', name: 'Project Orion', state: 'ACTIVE' }],
        } as Response;
      }
      if (u.includes('/board')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            {
              id: 'task-no-lease',
              title: 'Task marked IN_PROGRESS with recent execution but NO lease accredited',
              status: 'IN_PROGRESS',
              executions: [
                {
                  id: 'exec-no-lease-1',
                  status: 'RUNNING',
                  worker_id: 'worker-no-lease',
                  attempts: 1,
                  created_at: new Date(Date.now() - 30 * 1000).toISOString(), // 30s ago, but NO lease_expires_at!
                },
              ],
            },
            {
              id: 'task-active-lease',
              title: 'Task executing with valid accredited lease',
              status: 'IN_PROGRESS',
              executions: [
                {
                  id: 'exec-lease-active',
                  status: 'RUNNING',
                  worker_id: 'worker-active-lease',
                  attempts: 1,
                  created_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
                  lease_expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(), // Valid unexpired lease
                },
              ],
            },
            {
              id: 'task-expired-lease',
              title: 'Task with expired lease',
              status: 'IN_PROGRESS',
              executions: [
                {
                  id: 'exec-lease-expired',
                  status: 'RUNNING',
                  worker_id: 'worker-expired-lease',
                  attempts: 1,
                  created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
                  lease_expires_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // Expired lease
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
      // 1. Worker with RUNNING status but NO lease accredited: must be UNKNOWN vigency, NOT EJECUTANDO
      const workerNoLease = org.data.agents.find((a) => a.id === 'worker-no-lease');
      expect(workerNoLease).toBeDefined();
      expect(workerNoLease?.operationalState).toBe('DESCONOCIDO');
      expect(workerNoLease?.status).toBe('UNKNOWN');
      expect(workerNoLease?.currentAssignments[0].status).toBe('UNKNOWN');

      // 2. Worker with RUNNING status and accredited unexpired lease: IS EJECUTANDO and ACTIVE
      const workerActiveLease = org.data.agents.find((a) => a.id === 'worker-active-lease');
      expect(workerActiveLease).toBeDefined();
      expect(workerActiveLease?.operationalState).toBe('EJECUTANDO');
      expect(workerActiveLease?.status).toBe('BUSY');
      expect(workerActiveLease?.currentAssignments[0].status).toBe('ACTIVE');

      // 3. Worker with RUNNING status but expired lease: must be EXPIRED assignment
      const workerExpiredLease = org.data.agents.find((a) => a.id === 'worker-expired-lease');
      expect(workerExpiredLease).toBeDefined();
      expect(workerExpiredLease?.currentAssignments[0].status).toBe('EXPIRED');

      // 4. Only accredited active assignments count in activeAssignmentsCount
      expect(org.data.activeAssignmentsCount).toBe(1);
    }
  });

  it('strictly separates project grants from technical capabilities: grants do NOT produce certified capabilities', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/v1/principals/me/grants')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            {
              project_id: 'p1',
              capability: 'project.read',
              active: true,
              expires_at: '2026-10-26T00:00:00Z',
            },
            {
              project_id: 'p1',
              capability: 'work.claim',
              active: true,
              expires_at: null,
            },
          ],
        } as Response;
      }
      if (u.includes('/v1/principals/me')) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            principal_id: 'agent-grantee',
            kind: 'AGENT',
            auth_method: 'token',
            enabled: true,
            grants: [
              {
                project_id: 'p1',
                capability: 'project.read',
                active: true,
                expires_at: '2026-10-26T00:00:00Z',
              },
              {
                project_id: 'p1',
                capability: 'work.claim',
                active: true,
                expires_at: null,
              },
            ],
          }),
        } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return { status: 200, ok: true, json: async () => [{ id: 'p1', name: 'P1' }] } as Response;
      }
      if (u.includes('/board')) {
        return { status: 200, ok: true, json: async () => [] } as Response;
      }
      return { status: 404, ok: false, json: async () => ({}) } as Response;
    });

    const org = await live.getOrganizationStructure();
    expect(org.kind).toBe('ready');
    if (org.kind === 'ready') {
      const agent = org.data.agents.find((a) => a.id === 'agent-grantee');
      expect(agent).toBeDefined();
      // CEO Point 2: grants MUST NOT be translated to capabilities as CERTIFIED!
      expect(agent?.capabilities).toEqual([]);
      // Must be recorded in grants as permissions
      expect(agent?.grants).toBeDefined();
      expect(agent?.grants?.length).toBe(2);
      expect(agent?.grants?.[0].permission).toBe('project.read');
      expect(agent?.grants?.[0].active).toBe(true);
      expect(agent?.grants?.[1].permission).toBe('work.claim');
    }
  });

  it('strictly separates reviews from certifications: task reviews do NOT grant certified capabilities', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization') || u.includes('/v1/principals/me')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return { status: 200, ok: true, json: async () => [{ id: 'p1', name: 'P1' }] } as Response;
      }
      if (u.includes('/board')) {
        return {
          status: 200,
          ok: true,
          json: async () => [
            {
              id: 'task-reviewed',
              title: 'Security audit candidate',
              status: 'VERIFIED',
              reviews: [
                {
                  id: 'rev-1',
                  work_id: 'task-reviewed',
                  reviewer_id: 'auditor-independent-ronin',
                  decision: 'APPROVED',
                  created_at: '2026-10-25T14:30:00Z',
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
      const reviewer = org.data.agents.find((a) => a.id === 'auditor-independent-ronin');
      expect(reviewer).toBeDefined();
      // CEO Point 5: MUST NOT have synthetic CERTIFIED capabilities
      expect(reviewer?.capabilities).toEqual([]);
      expect(reviewer?.unitId).toBe('unit-unassigned');
      expect(reviewer?.type).toBe('UNKNOWN');
      expect(reviewer?.lastEvidenceAt).toBe('2026-10-25T14:30:00Z');
      expect(reviewer?.evidenceDescription).toContain('No constituye certificación formal');
    }
  });

  it('inspects all projects without a silent 10-project limit and records coverage completeness', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });

    // Generate 15 projects
    const mockProjects = Array.from({ length: 15 }, (_, i) => ({
      id: `proj-${i}`,
      name: `Project ${i}`,
    }));

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization') || u.includes('/v1/principals/me')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return { status: 200, ok: true, json: async () => mockProjects } as Response;
      }
      if (u.includes('/proj-14/board')) {
        // Project 14 board fails with 500 error
        return { status: 500, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/board')) {
        return { status: 200, ok: true, json: async () => [] } as Response;
      }
      return { status: 404, ok: false, json: async () => ({}) } as Response;
    });

    const org = await live.getOrganizationStructure();
    expect(org.kind).toBe('ready');
    if (org.kind === 'ready') {
      expect(org.data.coverage).toBeDefined();
      expect(org.data.coverage?.totalProjects).toBe(15);
      expect(org.data.coverage?.inspectedProjects).toBe(14);
      expect(org.data.coverage?.failedProjects).toBe(1);
      expect(org.data.coverage?.isPartial).toBe(true);
      expect(org.data.coverage?.notes).toContain('Cobertura parcial: 1 de 15 proyectos no pudieron ser consultados');
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
      // CEO Point 3: Must NOT deduce unit-exec or STANDING
      expect(details.data.unitId).toBe('unit-unassigned');
      expect(details.data.type).toBe('UNKNOWN');
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
