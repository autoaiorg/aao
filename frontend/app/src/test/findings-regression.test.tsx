/**
 * Regression Test Suite for Review Findings 1, 2, 3, and 4
 * Spec: Review of PR #99 findings by the CEO
 *
 * 1. P0 — Identidad CEO: No synthetic fabrication; real backend check on /v1/mandates.
 * 2. P0 — Aislamiento de sesiones: Key strengthening, sessionId rotation, abortAll() and cache purges.
 * 3. P1 — Estados desconocidos: Elimination of silent mutation to INBOX; exact semantic preservation.
 * 4. P1 — Accesibilidad: Semantic buttons replacing clickable divs; keyboard Escape handlers.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import React from 'react';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { AuthProvider, useAuth } from '../auth/AuthContext';
import { KanbanView } from '../features/kanban/KanbanView';
import { CeoDashboard } from '../features/dashboard/CeoDashboard';
import { TaskDetailDrawer } from '../features/kanban/TaskDetailDrawer';
import type { ProjectBoard, CeoOverview, ProjectSummary } from '../domain/models';

describe('P0 Finding 1: Identidad CEO y Verificación Real', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('rejects CEO identity request if token is missing without fabricating synthetic identity', async () => {
    const adapter = new HttpAaoLiveAdapter({
      getToken: () => null,
      getAuthRole: () => 'CEO',
    });

    const res = await adapter.getCurrentPrincipal();
    expect(res.kind).toBe('forbidden');
    if (res.kind === 'forbidden') {
      expect(res.reason).toContain('Credencial no suministrada');
    }
  });

  it('tests X-CEO-Token against /v1/mandates and rejects when backend returns HTTP 403', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 403,
      ok: false,
      statusText: 'Forbidden',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'invalid-ceo-token',
      getAuthRole: () => 'CEO',
    });

    const res = await adapter.getCurrentPrincipal();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/v1/mandates'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-CEO-Token': 'invalid-ceo-token',
        }),
      })
    );

    expect(res.kind).toBe('forbidden');
    if (res.kind === 'forbidden') {
      expect(res.reason).toContain('Autenticación no comprobada');
    }
  });

  it('marks CEO bearer as unavailable when backend returns HTTP 503', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 503,
      ok: false,
      statusText: 'Service Unavailable',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'valid-looking-token',
      getAuthRole: () => 'CEO',
    });

    const res = await adapter.getCurrentPrincipal();
    expect(res.kind).toBe('unavailable');
    if (res.kind === 'unavailable') {
      expect(res.reason).toContain('HTTP 503');
    }
  });

  it('marks CEO as verified only when backend verifies token on /v1/mandates with HTTP 200', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [{ id: 'm-1', title: 'Mandato 1', status: 'ACTIVE' }],
    } as Response);

    const adapter = new HttpAaoLiveAdapter({
      getToken: () => 'verified-ceo-bearer',
      getAuthRole: () => 'CEO',
    });

    const res = await adapter.getCurrentPrincipal();
    expect(res.kind).toBe('ready');
    if (res.kind === 'ready') {
      expect(res.data.kind).toBe('CEO');
      expect(res.data.verificationStatus).toBe('verified');
      expect(res.data.authMethod).toContain('GET /v1/mandates');
    }
  });
});

describe('P0 Finding 2: Aislamiento de Sesiones y Rotación de Identificador', () => {
  it('rotates sessionId on login and logout using cryptographic UUID entropy', () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    const initialSessionId = result.current.sessionId;
    expect(initialSessionId).toBeDefined();
    expect(typeof initialSessionId).toBe('string');
    expect(initialSessionId.length).toBeGreaterThan(15);

    act(() => {
      result.current.setCredentials('token-session-1', 'AGENT', 'agent-a');
    });

    const loginSessionId = result.current.sessionId;
    expect(loginSessionId).not.toBe(initialSessionId);
    expect(loginSessionId.length).toBeGreaterThan(15);

    act(() => {
      result.current.setCredentials('token-session-2', 'AGENT', 'agent-b');
    });

    const switchSessionId = result.current.sessionId;
    expect(switchSessionId).not.toBe(loginSessionId);

    act(() => {
      result.current.logout();
    });

    const logoutSessionId = result.current.sessionId;
    expect(logoutSessionId).not.toBe(switchSessionId);
  });

  it('throws an explicit error if Web Crypto API is completely unavailable without pseudo-random fallback', () => {
    const originalCrypto = globalThis.crypto;
    try {
      // @ts-expect-error forcing undefined crypto for testing security boundary
      delete globalThis.crypto;

      expect(() => {
        renderHook(() => useAuth(), {
          wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
        });
      }).toThrow(/CRITICAL SECURITY ERROR: Web Crypto API is unavailable/);
    } finally {
      globalThis.crypto = originalCrypto;
    }
  });

  it('HttpAaoLiveAdapter.abortAll() triggers abortion on in-flight requests', async () => {
    let capturedSignal: AbortSignal | undefined;
    vi.spyOn(global, 'fetch').mockImplementation((_url, options) => {
      const signal = options?.signal as AbortSignal;
      capturedSignal = signal;
      return new Promise((_, reject) => {
        if (signal?.aborted) {
          reject(new DOMException('The operation was aborted', 'AbortError'));
        } else {
          signal?.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted', 'AbortError'));
          });
        }
      });
    });

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'valid-bearer-token' });
    // Fire a request without awaiting it
    const promise = adapter.getProjectBoard('proj-hang');

    expect(capturedSignal).toBeDefined();
    expect(capturedSignal?.aborted).toBe(false);

    // Call abortAll()
    adapter.abortAll();

    expect(capturedSignal?.aborted).toBe(true);

    const result = await promise;
    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.code).toBe('TIMEOUT');
    }
  });

  it('handles delayed HTTP responses during credential switch without cross-session contamination', async () => {
    let sessionAAborted = false;

    vi.spyOn(global, 'fetch').mockImplementation((_url, options) => {
      const signal = options?.signal as AbortSignal;
      const headers = options?.headers as Record<string, string>;

      if (headers?.['X-Agent-Token'] === 'token-session-a') {
        return new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            sessionAAborted = true;
            reject(new DOMException('Session A was aborted', 'AbortError'));
          });
        });
      }

      // Session B responds immediately
      return Promise.resolve({
        status: 200,
        ok: true,
        json: async () => [{ id: 'proj-session-b', name: 'Project Session B', state: 'ACTIVE' }],
      } as Response);
    });

    let currentToken = 'token-session-a';
    const adapter = new HttpAaoLiveAdapter({
      getToken: () => currentToken,
      getAuthRole: () => 'AGENT',
    });

    // 1. Session A starts an async request (delayed in flight)
    const sessionAPromise = adapter.listProjects();

    // 2. Before Session A resolves, credentials switch to Session B
    currentToken = 'token-session-b';
    adapter.abortAll(); // Aborts all Session A requests

    expect(sessionAAborted).toBe(true);

    // 3. Session B makes its own request
    const sessionBResult = await adapter.listProjects();
    expect(sessionBResult.kind).toBe('ready');
    if (sessionBResult.kind === 'ready') {
      expect(sessionBResult.data[0].id).toBe('proj-session-b');
    }

    // 4. Session A finishes with error/abort without affecting Session B
    const sessionAResult = await sessionAPromise;
    expect(sessionAResult.kind).toBe('error');
  });

  it('handles delayed HTTP responses during logout: aborts active queries and keeps storage empty', async () => {
    let capturedSignal: AbortSignal | undefined;
    vi.spyOn(global, 'fetch').mockImplementation((_url, options) => {
      capturedSignal = options?.signal as AbortSignal;
      return new Promise((_, reject) => {
        capturedSignal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted by logout', 'AbortError'));
        });
      });
    });

    let token: string | null = 'test-token-to-logout';
    const adapter = new HttpAaoLiveAdapter({
      getToken: () => token,
      getAuthRole: () => 'AGENT',
    });

    const pendingPromise = adapter.listProjects();
    expect(capturedSignal?.aborted).toBe(false);

    // Logout occurs
    token = null;
    adapter.abortAll();

    expect(capturedSignal?.aborted).toBe(true);
    const result = await pendingPromise;
    expect(result.kind).toBe('error');

    // Memory-only check: verify storage is untouched
    expect(localStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
  });

  it('guarantees ZERO network calls before a valid session is established', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const unauthenticatedAdapter = new HttpAaoLiveAdapter({
      getToken: () => null,
      getAuthRole: () => 'AGENT',
      requireAuth: true,
    });

    // None of these should execute fetch
    const p1 = await unauthenticatedAdapter.getCurrentPrincipal();
    const p2 = await unauthenticatedAdapter.listProjects();
    const p3 = await unauthenticatedAdapter.getProjectBoard('proj-x');
    const p4 = await unauthenticatedAdapter.getProjectCapabilities('proj-x');
    const p5 = await unauthenticatedAdapter.getProjectEvaluations('proj-x');
    const p6 = await unauthenticatedAdapter.getCeoOverview('proj-x');

    expect(p1.kind).toBe('forbidden');
    expect(p2.kind).toBe('forbidden');
    expect(p3.kind).toBe('forbidden');
    expect(p4.kind).toBe('forbidden');
    expect(p5.kind).toBe('forbidden');
    expect(p6.projects.kind).toBe('forbidden');

    // 0 network requests dispatched!
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('P1 Finding 3: Integridad Semántica y Eliminación de Mutación a INBOX', () => {
  it('does NOT silently mutate unrecognized statuses to INBOX; preserves exact status string', async () => {
    const mockTasks = [
      { id: 'task-1', title: 'Normal Inbox', status: 'INBOX' },
      { id: 'task-2', title: 'Normal In Review', status: 'IN_REVIEW' },
      { id: 'task-3', title: 'Archived Task', status: 'ARCHIVED' },
      { id: 'task-4', title: 'Custom Stage Task', status: 'BLOCKED_EXTERNAL' },
    ];

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => mockTasks,
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.getProjectBoard('test-proj');

    expect(res.kind).toBe('ready');
    if (res.kind === 'ready') {
      const board = res.data;

      // INBOX should ONLY have task-1, NEVER task-3 or task-4
      expect(board.stages.INBOX).toHaveLength(1);
      expect(board.stages.INBOX[0].id).toBe('task-1');

      // Unrecognized tasks are preserved in unrecognizedItems with their exact raw status
      expect(board.unrecognizedItems).toHaveLength(2);

      const archivedTask = board.unrecognizedItems.find((t) => t.id === 'task-3');
      expect(archivedTask?.status).toBe('ARCHIVED');
      expect(archivedTask?.isUnrecognizedStatus).toBe(true);

      const blockedTask = board.unrecognizedItems.find((t) => t.id === 'task-4');
      expect(blockedTask?.status).toBe('BLOCKED_EXTERNAL');
      expect(blockedTask?.isUnrecognizedStatus).toBe(true);
    }
  });

  it('renders unrecognized items in dedicated column with warning banner in KanbanView', () => {
    const boardWithUnrecognized: ProjectBoard = {
      projectId: 'proj-with-unrecognized',
      projectName: 'Proyecto con Estados Extra',
      totalCount: 2,
      stages: {
        INBOX: [{ id: 'task-inbox', title: 'Tarea Canónica', status: 'INBOX' }],
        READY: [],
        IN_PROGRESS: [],
        IN_REVIEW: [],
        VERIFIED: [],
        DONE: [],
      },
      unrecognizedItems: [
        { id: 'task-custom', title: 'Tarea No Canónica', status: 'PENDING_VENDOR', isUnrecognizedStatus: true },
      ],
      items: [],
    };

    render(
      <KanbanView
        boardState={{ kind: 'ready', origin: 'live', data: boardWithUnrecognized, fetchedAt: '' }}
        selectedProjectId="proj-with-unrecognized"
        projectName="Proyecto con Estados Extra"
        onRefresh={() => {}}
      />
    );

    // Warning banner is rendered
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Se detectaron 1 tarea\(s\) con estados no reconocidos/i)).toBeInTheDocument();

    // Dedicated column rendered
    expect(screen.getByText('Estado No Reconocido')).toBeInTheDocument();
    expect(screen.getByText('PENDING_VENDOR')).toBeInTheDocument();
  });
});

describe('P1 Finding 4: Accesibilidad y Elementos Semánticos', () => {
  it('renders project list items in CeoDashboard as semantic button elements with aria-pressed', () => {
    const mockProjects: ProjectSummary[] = [
      { id: 'p-1', name: 'Alpha Project', status: 'ACTIVE' },
      { id: 'p-2', name: 'Beta Project', status: 'ACTIVE' },
    ];

    const overview: CeoOverview = {
      projects: { kind: 'ready', origin: 'live', data: mockProjects, fetchedAt: '' },
      work: { kind: 'empty', origin: 'live', fetchedAt: '' },
      governance: { kind: 'empty', origin: 'live', fetchedAt: '' },
      operations: { kind: 'empty', origin: 'live', fetchedAt: '' },
      alerts: { kind: 'empty', origin: 'live', fetchedAt: '' },
      decisions: { kind: 'empty', origin: 'live', fetchedAt: '' },
    };

    const onSelectProject = vi.fn();
    render(
      <CeoDashboard
        overview={overview}
        projects={mockProjects}
        selectedProjectId="p-1"
        onSelectProject={onSelectProject}
        onNavigateTo={() => {}}
      />
    );

    const buttons = screen.getAllByRole('button');
    const projectBtn = buttons.find((btn) => btn.textContent?.includes('Alpha Project'));

    expect(projectBtn).toBeDefined();
    expect(projectBtn?.tagName.toLowerCase()).toBe('button');
    expect(projectBtn).toHaveAttribute('aria-pressed', 'true');

    if (projectBtn) {
      fireEvent.click(projectBtn);
      expect(onSelectProject).toHaveBeenCalledWith('p-1');
    }
  });

  it('renders Kanban task cards as semantic button elements with aria-haspopup and aria-label', () => {
    const board: ProjectBoard = {
      projectId: 'p-kanban',
      totalCount: 1,
      stages: {
        INBOX: [{ id: 'task-sem-1', title: 'Accesible Task Card', status: 'INBOX' }],
        READY: [],
        IN_PROGRESS: [],
        IN_REVIEW: [],
        VERIFIED: [],
        DONE: [],
      },
      unrecognizedItems: [],
      items: [],
    };

    render(
      <KanbanView
        boardState={{ kind: 'ready', origin: 'live', data: board, fetchedAt: '' }}
        selectedProjectId="p-kanban"
        onRefresh={() => {}}
      />
    );

    const taskButton = screen.getByRole('button', {
      name: /Ver detalles de la tarea task-sem-1: Accesible Task Card/i,
    });

    expect(taskButton).toBeInTheDocument();
    expect(taskButton.tagName.toLowerCase()).toBe('button');
    expect(taskButton).toHaveAttribute('aria-haspopup', 'dialog');
  });

  it('closes TaskDetailDrawer upon pressing Escape key', () => {
    const onClose = vi.fn();
    const task = { id: 'task-esc', title: 'Escape Test', status: 'INBOX' };

    render(<TaskDetailDrawer task={task} onClose={onClose} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
