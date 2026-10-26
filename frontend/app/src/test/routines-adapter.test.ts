import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';

const id = 'a1a1a1a1-1111-4111-8111-a1a1a1a1a1a1';
const routine = { id, template: { title: 'Revisar resultados', description: '', acceptance_criteria: ['Informe verificable'] },
  interval_seconds: 3600, next_run_at: '2026-10-27T10:00:00Z', enabled: true, authorized_by: 'ceo',
  created_at: '2026-10-26T10:00:00Z', execution_authorized: false };
const input = { idempotency_key: id, ...routine.template, interval_seconds: 3600, first_run_at: routine.next_run_at };
const adapter = (role: 'CEO' | 'AGENT' = 'CEO') => new HttpAaoLiveAdapter({
  getAuthRole: () => role, getCeoCookieSession: () => role === 'CEO', getCsrfToken: () => 'test-csrf', requireAuth: true,
});
afterEach(() => vi.unstubAllGlobals());

describe('persistent routines HTTP contract', () => {
  it('reads canonical routines with cookie credentials and validates the response', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify([routine])));
    vi.stubGlobal('fetch', fetcher);
    const result = await adapter().listRoutines('project/a');
    expect(result.kind).toBe('ready');
    expect(fetcher).toHaveBeenCalledWith('/v1/projects/project%2Fa/routines', expect.objectContaining({ credentials: 'include' }));
  });
  it('rejects malformed data rather than inventing enabled state or execution authority', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{ ...routine, enabled: 'true', execution_authorized: true }]))));
    expect((await adapter().listRoutines(id)).kind).toBe('error');
  });
  it('uses the shared CEO cookie/CSRF path for authorization and pause', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id, created: true })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id, enabled: false })));
    vi.stubGlobal('fetch', fetcher);
    expect((await adapter().createRoutine(id, input)).kind).toBe('ready');
    expect((await adapter().setRoutineEnabled(id, id, false)).kind).toBe('ready');
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify(input), headers: { 'X-AAO-CSRF': 'test-csrf' } });
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: 'PATCH', body: JSON.stringify({ enabled: false }) });
  });
  it('does not send mutation requests for an agent session', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    expect((await adapter('AGENT').createRoutine(id, input)).kind).toBe('forbidden');
    expect((await adapter('AGENT').setRoutineEnabled(id, id, false)).kind).toBe('forbidden');
    expect(fetcher).not.toHaveBeenCalled();
  });
});
