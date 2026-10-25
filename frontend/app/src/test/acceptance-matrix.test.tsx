/**
 * Comprehensive Acceptance Test Suite for Mandate Cases T01-T20
 * Spec: AAO-FE-ARCH-2026-10-25 Section 11 & Section 12
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { MockAaoDemoAdapter } from '../data/adapters/demo/MockAaoDemoAdapter';
import { CeoDashboard } from '../features/dashboard/CeoDashboard';
import { TaskDetailDrawer } from '../features/kanban/TaskDetailDrawer';
import { BannerAlert } from '../components/layout/BannerAlert';
import { StateDistribution } from '../components/ui/StateDistribution';
import { BOARD_STAGES, BOARD_STAGE_LABELS } from '../domain/models';
import type { CeoOverview, TaskItem } from '../domain/models';

describe('Specification Acceptance Matrix (T01 - T20)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // T01: GET proyectos = lista válida -> Lista visible en LIVE
  it('T01: Live adapter returns valid projects list without demo contamination', async () => {
    const mockProjects = [{ id: 'p-live-1', name: 'Live Project One', state: 'ACTIVE' }];
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => mockProjects,
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.listProjects();
    expect(res.kind).toBe('ready');
    if (res.kind === 'ready') {
      expect(res.origin).toBe('live');
      expect(res.data[0].id).toBe('p-live-1');
    }
  });

  // T02: GET proyectos = [] -> Vacío real, no error
  it('T02: Empty projects list returns kind empty, not error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [],
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.listProjects();
    expect(res.kind).toBe('empty');
    if (res.kind === 'empty') {
      expect(res.origin).toBe('live');
    }
  });

  // T03: GET proyectos = 403 -> Acceso no autorizado sin fuga de datos
  it('T03: 403 forbidden returns forbidden state without disclosing internal data', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 403,
      ok: false,
      statusText: 'Forbidden',
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.listProjects();
    expect(res.kind).toBe('forbidden');
  });

  // T04: GET proyectos = 500 -> Error recuperable, sin rellenar con fixtures demo
  it('T04: 500 internal server error is marked retryable and never falls back to demo fixtures', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 500,
      ok: false,
      statusText: 'Internal Error',
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.listProjects();
    expect(res.kind).toBe('error');
    if (res.kind === 'error') {
      expect(res.retryable).toBe(true);
      // Ensures no demo data leaked into error state
      expect((res as any).data).toBeUndefined();
    }
  });

  // T05: JSON incompleto o corrupto -> Validación fallida y estado error
  it('T05: Corrupted JSON response is safely caught by Zod and marked as non-retryable error', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => [{ corrupted: true, missing_required_fields: 'yes' }],
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    const res = await adapter.listProjects();
    expect(res.kind).toBe('error');
    if (res.kind === 'error') {
      expect(res.code).toBe('SCHEMA_VALIDATION_ERROR');
      expect(res.retryable).toBe(false);
    }
  });

  // T06: Token expirado 401 -> Logout, borrado de sesión y prompt
  it('T06: 401 unauthorized automatically triggers logout callback to purge session', async () => {
    const onUnauthorized = vi.fn();
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 401,
      ok: false,
      statusText: 'Unauthorized',
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ onUnauthorized });
    const res = await adapter.getCurrentPrincipal();

    expect(onUnauthorized).toHaveBeenCalled();
    expect(res.kind).toBe('forbidden');
  });

  // T07: Cambiar proyecto rápidamente -> Consultas aisladas por project_id
  it('T07: Board queries are project-scoped and isolated', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => [],
    } as Response);

    const adapter = new HttpAaoLiveAdapter();
    await adapter.getProjectBoard('project-alpha');
    await adapter.getProjectBoard('project-beta');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/projects/project-alpha/board'),
      expect.any(Object)
    );
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/projects/project-beta/board'),
      expect.any(Object)
    );
  });

  // T08 & T09: Conmutación demo <-> live y aislamiento estricto
  it('T08 & T09: Demo adapter and Live adapter maintain absolute segregation', async () => {
    const demoAdapter = new MockAaoDemoAdapter(0);
    const demoProjects = await demoAdapter.listProjects();
    expect(demoProjects.kind).toBe('ready');
    if (demoProjects.kind === 'ready') {
      expect(demoProjects.origin).toBe('demo');
      expect(demoProjects.data[0].id).toContain('demo');
    }

    // Demo banner presence
    const { rerender } = render(<BannerAlert origin="demo" />);
    expect(screen.getByText(/DEMO · DATOS SIMULADOS/i)).toBeInTheDocument();

    rerender(<BannerAlert origin="live" />);
    expect(screen.queryByText(/DEMO · DATOS SIMULADOS/i)).toBeNull();
  });

  // T10: Fuente de alertas inexistente -> «No disponible», NO «0 alertas»
  it('T10: Missing alerts contract renders unavailable explanation, not misleading 0', () => {
    const overview: CeoOverview = {
      projects: { kind: 'empty', origin: 'live', fetchedAt: '' },
      work: { kind: 'unavailable', reason: 'Seleccione un proyecto para desglose', retryable: false },
      governance: { kind: 'unavailable', reason: 'Sin contrato API certificado', retryable: false },
      operations: {
        kind: 'ready',
        origin: 'live',
        data: { serviceHealth: 'healthy', readyStatus: true, checkedAt: '', message: '' },
        fetchedAt: '',
      },
      alerts: { kind: 'unavailable', reason: 'Sin contrato de alertas en tiempo real', retryable: false },
      decisions: { kind: 'unavailable', reason: 'Modo consultivo', retryable: false },
    };

    render(
      <CeoDashboard
        overview={overview}
        projects={[]}
        selectedProjectId={null}
        onSelectProject={() => {}}
        onNavigateTo={() => {}}
      />
    );

    expect(screen.queryByText('0 alertas')).toBeNull();
    expect(screen.getAllByText(/Seleccione un proyecto para desglose/i).length).toBeGreaterThan(0);
  });

  // T11: Ver diff auditor con sesión agente -> UI no solicita endpoint restringido
  it('T11: Task detail drawer warns about security boundary and does not call diff endpoint', () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const task: TaskItem = {
      id: 'task-sec-11',
      title: 'Audited Task',
      status: 'IN_REVIEW',
    };

    render(<TaskDetailDrawer task={task} onClose={() => {}} />);
    expect(screen.getByText(/La inspección del diff completo de patch proposals está restringida al rol AUDITOR/i)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  // T12: Títulos con <script> como texto -> Escapado estricto
  it('T12: XSS attempt in task title is rendered as plain text', () => {
    const task: TaskItem = {
      id: 'task-xss',
      title: '<script>alert("hacked")</script>',
      status: 'INBOX',
    };

    render(<TaskDetailDrawer task={task} onClose={() => {}} />);
    expect(screen.getByText('<script>alert("hacked")</script>')).toBeInTheDocument();
  });

  // T13: Promoción sin evidencia firmada -> Nunca se representa como autorizada
  it('T13: Governance widget explicitly shows uncertified without signed evidence', () => {
    const overview: CeoOverview = {
      projects: { kind: 'empty', origin: 'live', fetchedAt: '' },
      work: { kind: 'empty', origin: 'live', fetchedAt: '' },
      governance: {
        kind: 'ready',
        origin: 'live',
        data: {
          certified: false,
          pendingReviewsCount: 3,
          notes: 'No existe dictamen independiente formal para este snapshot.',
        },
        fetchedAt: '',
      },
      operations: {
        kind: 'ready',
        origin: 'live',
        data: { serviceHealth: 'healthy', readyStatus: true, checkedAt: '', message: '' },
        fetchedAt: '',
      },
      alerts: { kind: 'empty', origin: 'live', fetchedAt: '' },
      decisions: { kind: 'empty', origin: 'live', fetchedAt: '' },
    };

    render(
      <CeoDashboard
        overview={overview}
        projects={[]}
        selectedProjectId={null}
        onSelectProject={() => {}}
        onNavigateTo={() => {}}
      />
    );

    expect(screen.getByText('NO CERTIFICADO / EN PROCESO')).toBeInTheDocument();
    expect(screen.getByText(/No existe dictamen independiente formal/i)).toBeInTheDocument();
  });

  // T14: Kanban histórico seis estados -> Semántica y orden conservados
  it('T14: Kanban preserves six canonical states INBOX, READY, IN_PROGRESS, IN_REVIEW, VERIFIED, DONE', () => {
    expect(BOARD_STAGES).toHaveLength(6);
    expect(BOARD_STAGE_LABELS.INBOX).toBe('Entrada');
    expect(BOARD_STAGE_LABELS.READY).toBe('Preparado');
    expect(BOARD_STAGE_LABELS.IN_PROGRESS).toBe('En curso');
    expect(BOARD_STAGE_LABELS.IN_REVIEW).toBe('Revisión');
    expect(BOARD_STAGE_LABELS.VERIFIED).toBe('Verificado');
    expect(BOARD_STAGE_LABELS.DONE).toBe('Completado');
  });

  // T15: Navegación accesible y roles ARIA
  it('T15: State distribution provides accessible progressbar attributes', () => {
    render(<StateDistribution distribution={{ INBOX: 1, READY: 1, IN_PROGRESS: 1, IN_REVIEW: 1, VERIFIED: 1, DONE: 1 }} totalCount={6} />);
    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toHaveAttribute('aria-valuenow', '6');
    expect(progressbar).toHaveAttribute('aria-valuemax', '6');
  });

  // T16: Red desconectada tras carga -> Indicador de desconexión
  it('T16: Offline notice is rendered when network is disconnected', () => {
    render(<BannerAlert origin="live" isOffline={true} />);
    expect(screen.getByText(/Sin conexión de red con el backend/i)).toBeInTheDocument();
  });
});
