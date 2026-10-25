import { describe, it, expect, vi, beforeEach } from 'vitest';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { MockAaoDemoAdapter } from '../data/adapters/demo/MockAaoDemoAdapter';

const ok = (body: unknown) => ({ status: 200, ok: true, json: async () => body }) as Response;

describe('Self Development cycle data (board pull requests and activity)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('maps pull_requests from the board onto the task', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      ok([
        {
          id: 'w1', title: 'T', status: 'VERIFIED', acceptance_criteria: ['c'],
          executions: [{ id: 'e1', status: 'SUCCEEDED', attempts: 1, created_at: '2026-10-25T10:00:00Z',
            result: { candidate_sha: 'a'.repeat(40), check: { check_id: 'core-unit', conclusion: 'success', exit_code: 0 } } }],
          reviews: [],
          pull_requests: [{ pr_number: 104, pr_url: 'https://github.com/autoaiorg/aao/pull/104', candidate_sha: 'a'.repeat(40) }],
        },
      ])
    );
    const result = await new HttpAaoLiveAdapter({ getToken: () => 't' }).getProjectBoard('p1');
    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') {
      const task = result.data.stages.VERIFIED[0];
      expect(task.pullRequests?.[0].pr_number).toBe(104);
      expect(task.executions?.[0].status).toBe('SUCCEEDED');
    }
  });

  it('reads the project activity feed from the live API', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      ok([{ id: 'ev1', subject_id: 'w1', kind: 'work.pr_opened', details: { pr_number: 104 }, created_at: '2026-10-25T10:40:00Z' }])
    );
    const result = await new HttpAaoLiveAdapter({ getToken: () => 't' }).getProjectActivity('p1');
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/v1/projects/p1/activity');
    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') expect(result.data[0].kind).toBe('work.pr_opened');
  });

  it('rejects a malformed activity response instead of showing it', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(ok([{ kind: 'x' }]));
    const result = await new HttpAaoLiveAdapter({ getToken: () => 't' }).getProjectActivity('p1');
    expect(result.kind).toBe('error');
  });

  it('demo mode does not fabricate activity', async () => {
    const result = await new MockAaoDemoAdapter().getProjectActivity('demo-proj-orion');
    expect(result.kind).toBe('unavailable');
  });
});
