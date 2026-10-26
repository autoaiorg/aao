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

  it('loads the CEO-only canonical source index and maps only declared metadata', async () => {
    const fetch = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200, ok: true,
      json: async () => [{
        work_id: 'work-1', project_id: 'project-1', project_name: 'Project One',
        title: 'Persisted work', status: 'DONE', evidence_references: ['sha256:ref'],
        reviews: [{ id: 'review-1', reviewer_id: 'auditor', decision: 'APPROVE', created_at: '2026-10-26T00:00:00Z', evidence_references: [] }],
        result_json: { secret: 'must not be exposed' },
      }],
    } as Response);
    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO' });
    const result = await adapter.getKnowledgeSourceIndex();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/knowledge/index'), expect.objectContaining({ credentials: 'include' }));
    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') {
      expect(result.data[0]).toMatchObject({ workId: 'work-1', projectId: 'project-1', evidenceReferences: ['sha256:ref'] });
      expect(JSON.stringify(result.data)).not.toContain('must not be exposed');
    }
  });

  it('does not call the corporate index endpoint for an AGENT session', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await adapter.getKnowledgeSourceIndex()).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();
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

describe('HttpAaoLiveAdapter organization projection', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const projection = {
    units: [{
      id: 'unit-unassigned', name: 'Adscripción desconocida', code: 'UNKNOWN',
      parentId: null, leadRole: 'Desconocido', leadAgentId: null,
      description: 'Agrupación visual; no representa un departamento persistido.',
      standingCount: 0, ephemeralCount: 0, activeProjectsCount: 0,
    }],
    agents: [], totalStandingAgents: 0, totalEphemeralAgents: 0,
    totalUnknownAgents: 0, activeAssignmentsCount: 0,
    coverage: { totalProjects: 0, inspectedProjects: 0, failedProjects: 0, isPartial: false },
  };

  it('consumes the canonical persisted projection without frontend fan-out', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200, ok: true, json: async () => projection,
    } as Response);

    const result = await live.getOrganizationStructure();
    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') expect(result.data.agents).toEqual([]);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/organization'), expect.any(Object),
    );
  });

  it('does not call projects/boards or invent departments when the organization API is absent', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 404, ok: false, json: async () => ({}),
    } as Response);

    const result = await live.getOrganizationStructure();
    expect(result.kind).toBe('unavailable');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('preserves forbidden and schema-error states without falling back to another data source', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });
    const fetch = vi.spyOn(global, 'fetch');
    fetch.mockResolvedValueOnce({ status: 403, ok: false, json: async () => ({}) } as Response);
    expect((await live.getOrganizationStructure()).kind).toBe('forbidden');

    fetch.mockResolvedValueOnce({
      status: 200, ok: true, json: async () => ({ agents: 'invalid' }),
    } as Response);
    const invalid = await live.getOrganizationStructure();
    expect(invalid.kind).toBe('error');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('requires authentication and never issues a LIVE organization request without a token', async () => {
    const live = new HttpAaoLiveAdapter({ getToken: () => null, requireAuth: true });
    const fetch = vi.spyOn(global, 'fetch');
    expect((await live.getOrganizationStructure()).kind).toBe('unavailable');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('writes organizational metadata only with CEO session and leaves authorization to backend too', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const agentSession = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agentSession.putOrganizationProfile({
      principal_id: 'agent-a', display_name: 'Agent A', role_title: 'Engineer',
      unit_id: null, manager_principal_id: null, enabled: true,
    })).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ id: 'unit-rnd' }) } as Response);
    const ceoSession = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const saved = await ceoSession.putOrganizationUnit({
      id: 'unit-rnd', name: 'Research', code: 'RND', parent_id: null,
      lead_principal_id: null, enabled: true,
    });
    expect(saved.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/organization/units'), expect.objectContaining({
      method: 'PUT',
      headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
      body: JSON.stringify({ id: 'unit-rnd', name: 'Research', code: 'RND', parent_id: null, lead_principal_id: null, enabled: true }),
    }));
  });

  it('creates canonical work requests only from CEO session and sends no execution grant', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const agentSession = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agentSession.createCEOWorkRequest('project-1', {
      title: 'Should be blocked', description: '', acceptance_criteria: ['Never sent'],
    })).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    const workId = '00000000-0000-4000-8000-000000000001';
    fetch.mockResolvedValueOnce({
      status: 201, ok: true, json: async () => ({ id: workId, status: 'INBOX' }),
    } as Response);
    const ceoSession = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const input = { title: 'Improve project', description: 'Context', acceptance_criteria: ['Tested'] };
    const result = await ceoSession.createCEOWorkRequest('project/1', input);
    expect(result.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/projects/project%2F1/work-requests'), expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
      body: JSON.stringify(input),
    }));
  });

  it('converts a persisted conversation message only from CEO session', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const input = { title: 'Analyze run', description: 'Review the project discussion', acceptance_criteria: ['Evidence linked'] };
    const agent = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agent.createWorkRequestFromMessage('p', 'c', 'm', input)).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    const workId = '00000000-0000-4000-8000-000000000042';
    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ id: workId, status: 'INBOX', created: true }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const result = await ceo.createWorkRequestFromMessage('p/1', 'c/1', 'm/1', input);
    expect(result.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/projects/p%2F1/conversations/c%2F1/messages/m%2F1/work-request'), expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
      body: JSON.stringify(input),
    }));
  });

  it('creates a CEO-confirmed work request linked to the full conversation', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const input = { title: 'Analyze run', description: 'Synthesis reviewed by CEO', acceptance_criteria: ['Evidence linked'] };
    const agent = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agent.createWorkRequestFromConversation('p', 'c', input)).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    const workId = '00000000-0000-4000-8000-000000000043';
    fetch.mockResolvedValueOnce({ status: 201, ok: true, json: async () => ({ id: workId, status: 'INBOX', created: true }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const result = await ceo.createWorkRequestFromConversation('p/1', 'c/1', input);
    expect(result.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/projects/p%2F1/conversations/c%2F1/work-requests'), expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
      body: JSON.stringify(input),
    }));
  });

  it('requests a reviewable task proposal only from a CEO session', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const agent = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agent.proposeWorkGroupFromConversation('p', 'c')).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({
      proposal: {
        title: 'Plan', description: 'Agreed outcome', acceptance_criteria: ['Verified'],
        tasks: [{ key: 'inspect', title: 'Inspect', description: '', acceptance_criteria: ['Sources recorded'], depends_on: [] }],
      },
      based_on_message_ids: ['00000000-0000-4000-8000-000000000041'],
      provider: 'openai-compatible', model: 'test-model', persisted_as_work: false,
    }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const result = await ceo.proposeWorkGroupFromConversation('p/1', 'c/1');
    expect(result.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/projects/p%2F1/conversations/c%2F1/work-group-proposals'), expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token' }),
    }));
  });

  it('reads and confirms durable work-group consolidations only in a CEO session', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const agent = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agent.listProjectWorkGroups('p')).kind).toBe('forbidden');
    expect((await agent.confirmWorkGroupConsolidation('p', 'g', {
      idempotency_key: '00000000-0000-4000-8000-000000000051', expected_source_sha256: 'a'.repeat(64), summary: 'CEO reviewed',
    })).kind).toBe('forbidden');
    expect((await agent.createWorkGroupPartialReport('p', 'g', {
      idempotency_key: '00000000-0000-4000-8000-000000000051', expected_source_sha256: 'a'.repeat(64), report_kind: 'PARTIAL', summary: 'Not final',
    })).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => [] } as Response);
    fetch.mockResolvedValueOnce({ status: 201, ok: true, json: async () => ({
      id: '00000000-0000-4000-8000-000000000052', project_id: '00000000-0000-4000-8000-000000000053',
      work_group_id: '00000000-0000-4000-8000-000000000054', parent_work_id: '00000000-0000-4000-8000-000000000055',
      summary: 'CEO reviewed', source_sha256: 'a'.repeat(64), source_snapshot: { children: [] },
      idempotency_key: '00000000-0000-4000-8000-000000000051', created_by: 'ceo',
      created_at: '2026-10-26T00:00:00Z', created: true,
    }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    expect((await ceo.listProjectWorkGroups('project/1')).kind).toBe('ready');
    expect((await ceo.confirmWorkGroupConsolidation('project/1', 'group/1', {
      idempotency_key: '00000000-0000-4000-8000-000000000051', expected_source_sha256: 'a'.repeat(64), summary: 'CEO reviewed',
    })).kind).toBe('ready');
    expect(fetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/v1/projects/project%2F1/work-groups'), expect.objectContaining({
      headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token' }),
    }));
    expect(fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/v1/projects/project%2F1/work-groups/group%2F1/consolidation'), expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
    }));
  });

  it('records CEO partial reports through the canonical endpoint', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    fetch.mockResolvedValueOnce({ status: 201, ok: true, json: async () => ({
      id: '00000000-0000-4000-8000-000000000056', report_kind: 'PARTIAL', summary: 'One child pending',
      source_sha256: 'a'.repeat(64), source_snapshot: { children: [] },
      idempotency_key: '00000000-0000-4000-8000-000000000057', created_by: 'ceo',
      created_at: '2026-10-26T00:00:00Z', created: true, final: false,
    }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    const result = await ceo.createWorkGroupPartialReport('project/1', 'group/1', {
      idempotency_key: '00000000-0000-4000-8000-000000000057', expected_source_sha256: 'a'.repeat(64),
      report_kind: 'PARTIAL', summary: 'One child pending',
    });
    expect(result.kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/projects/project%2F1/work-groups/group%2F1/partial-reports'), expect.objectContaining({ method: 'POST' }));
  });

  it('assigns a work-group child only in a CEO session and uses the canonical assignment route', async () => {
    const fetch = vi.spyOn(global, 'fetch');
    const agent = new HttpAaoLiveAdapter({ getToken: () => 'agent-token', getAuthRole: () => 'AGENT' });
    expect((await agent.assignWorkGroupChild('work-id', 'agent-id')).kind).toBe('forbidden');
    expect(fetch).not.toHaveBeenCalled();

    fetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({
      work_id: '00000000-0000-4000-8000-000000000061', principal_id: 'agent-a', assigned_by: 'ceo', grants_created: false,
    }) } as Response);
    const ceo = new HttpAaoLiveAdapter({ getToken: () => 'ceo-token', getAuthRole: () => 'CEO', requireAuth: true });
    expect((await ceo.assignWorkGroupChild('00000000-0000-4000-8000-000000000061', 'agent-a')).kind).toBe('ready');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/work/00000000-0000-4000-8000-000000000061/assignment'), expect.objectContaining({
      method: 'PUT', headers: expect.objectContaining({ 'X-CEO-Token': 'ceo-token', 'Content-Type': 'application/json' }),
      body: JSON.stringify({ principal_id: 'agent-a' }),
    }));
  });
});
