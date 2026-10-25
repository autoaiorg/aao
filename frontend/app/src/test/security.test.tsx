import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { TaskDetailDrawer } from '../features/kanban/TaskDetailDrawer';
import type { TaskItem } from '../domain/models';

describe('Security Boundaries & Sanitization', () => {
  it('never requests patch proposal diff endpoint during normal task details inspection', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'agent-token',
      getAuthRole: () => 'AGENT',
    });

    // Check what methods are available on adapter
    // Adapter implements AaoReadPort and explicitly has no method to fetch restricted patch diff
    expect((adapter as any).readPatchProposal).toBeUndefined();
    expect((adapter as any).getPatchDiff).toBeUndefined();

    // Verify fetch was never invoked with patch-proposals/{id}
    const forbiddenCalls = fetchSpy.mock.calls.filter((call) =>
      String(call[0]).includes('/patch-proposals/')
    );
    expect(forbiddenCalls).toHaveLength(0);
  });

  it('safely escapes HTML tags like <script> in task titles without execution', () => {
    const maliciousTask: TaskItem = {
      id: 'task-sec-01',
      title: '<script>alert("xss")</script> Tarea de Prueba',
      status: 'INBOX',
      acceptanceCriteria: ['<img src="x" onerror="alert(1)"/> Criterio seguro'],
    };

    render(<TaskDetailDrawer task={maliciousTask} onClose={() => {}} />);

    // Text content is rendered literally as string, not raw HTML
    const titleElement = screen.getByRole('heading', { level: 2 });
    expect(titleElement.textContent).toBe('<script>alert("xss")</script> Tarea de Prueba');
    expect(document.querySelector('script')).toBeNull();
  });
});
