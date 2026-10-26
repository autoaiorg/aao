import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeWorkGroupPanel } from '../features/office/components/OfficeWorkGroupPanel';
import type { AaoConversationPort, ProjectWorkGroup } from '../data/ports/AaoConversationPort';
import type { DataState, ProjectSummary } from '../domain/models';

const projects: DataState<ProjectSummary[]> = { kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
  { id: 'project-active', name: 'Proyecto activo', status: 'ACTIVE' },
] };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });
const group: ProjectWorkGroup = {
  id: '11111111-1111-4111-8111-111111111111',
  conversation_id: '22222222-2222-4222-8222-222222222222',
  parent_work_id: '33333333-3333-4333-8333-333333333333',
  title: 'Resultados del proyecto', parent_status: 'INBOX', acceptance_criteria: ['completado'], acceptance: null, source_sha256: 'a'.repeat(64),
  consolidation_ready: false,
  children: [{
    work_id: '44444444-4444-4444-8444-444444444444', status: 'IN_PROGRESS', assigned_principal_id: null, evidence: [], dependencies: [],
    executions: [{ id: '55555555-5555-4555-8555-555555555555', status: 'RUNNING', worker_id: 'agent-a', result_sha256: null }], reviews: [],
  }],
  consolidation: null,
  partial_reports: [],
};

function setup(groups: ProjectWorkGroup[], isCeoSession = true) {
  const port = {
    listAssignableAgents: vi.fn().mockResolvedValue(ready([
      { principal_id: 'agent-a', display_name: 'Agente A' },
      { principal_id: 'agent-b', display_name: 'Agente B' },
    ])),
    listProjectWorkGroups: vi.fn().mockResolvedValue(ready(groups)),
    assignWorkGroupChild: vi.fn().mockResolvedValue(ready({ work_id: group.children[0].work_id, principal_id: 'agent-a', assigned_by: 'ceo', grants_created: false as const })),
    confirmWorkGroupConsolidation: vi.fn().mockResolvedValue(ready({ ...group, project_id: 'project-active', work_group_id: group.id, source_snapshot: { children: group.children }, summary: 'Resultado consolidado', idempotency_key: '66666666-6666-4666-8666-666666666666', created_by: 'ceo', created_at: '2026-10-26T00:00:00Z', created: true })),
    confirmWorkGroupAcceptance: vi.fn().mockResolvedValue(ready({
      work_group_id: group.id, parent_work_id: group.parent_work_id, source_sha256: 'a'.repeat(64),
      accepted_criteria: group.acceptance_criteria, acceptance_statement: 'Aceptado', created_by: 'ceo',
      created_at: '2026-10-26T00:00:00Z', created: true,
    })),
    createWorkGroupPartialReport: vi.fn().mockResolvedValue(ready({ id: '77777777-7777-4777-8777-777777777777', report_kind: 'PARTIAL', summary: 'Informe CEO', source_sha256: 'a'.repeat(64), idempotency_key: '88888888-8888-4888-8888-888888888888', created_by: 'ceo', created_at: '2026-10-26T00:00:00Z', created: true, final: false as const })),
  } as unknown as AaoConversationPort;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeWorkGroupPanel projects={projects} port={port} sessionId="session-a" isCeoSession={isCeoSession} onOpenBoard={vi.fn()} /></QueryClientProvider>);
  return port;
}

describe('office work group consolidation', () => {
  it('shows persisted child status and keeps consolidation unavailable until all children are DONE', async () => {
    const port = setup([group]);
    expect(await screen.findByText('IN_PROGRESS')).toBeInTheDocument();
    expect(screen.getByText(/1 ejecuciones · 0 revisiones/)).toBeInTheDocument();
    expect(screen.getByText(/Trabajo aún no completado: IN_PROGRESS/)).toBeInTheDocument();
    expect(screen.getByText(/Ejecución 55555555 · RUNNING · actor agent-a · sin resultado persistido/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar consolidación' })).toBeDisabled();
    expect(port.confirmWorkGroupConsolidation).not.toHaveBeenCalled();
  });

  it('shows dependency status from the backend projection', async () => {
    const dependent = {
      ...group,
      children: [{
        ...group.children[0],
        dependencies: [{ work_id: '99999999-9999-4999-8999-999999999999', status: 'IN_REVIEW' }],
      }],
    };
    setup([dependent]);
    expect(await screen.findByText(/Prerequisito 99999999 · IN_REVIEW/)).toBeInTheDocument();
  });

  it('shows the latest persisted dispatch block for a child', async () => {
    const blockedGroup = { ...group, children: [{
      ...group.children[0],
      dispatch_block: {
        principal_id: 'agent-a',
        reason: 'A capability evaluation is required before dispatch',
        created_at: '2026-10-26T12:55:00Z',
      },
    }] };
    setup([blockedGroup]);
    expect(await screen.findByText(/Despacho bloqueado por agent-a: A capability evaluation is required before dispatch/)).toBeInTheDocument();
  });

  it('refreshes the canonical group projection while the office view remains open', async () => {
    vi.useFakeTimers();
    try {
      const port = setup([group]);
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(port.listProjectWorkGroups).toHaveBeenCalledTimes(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });
      expect(port.listProjectWorkGroups).toHaveBeenCalledTimes(2);
      expect(screen.getByText(/se actualiza cada 15 segundos/i)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('surfaces failed execution and rejected review without treating the child as completed', async () => {
    const partialGroup = { ...group, children: [{
      ...group.children[0],
      executions: [{ ...group.children[0].executions[0], status: 'FAILED', result_sha256: 'b'.repeat(64) }],
      reviews: [{ id: '66666666-6666-4666-8666-666666666666', decision: 'REJECT', candidate_sha: 'c'.repeat(40), evidence: [] }],
    }] };
    setup([partialGroup]);
    expect(await screen.findByText(/Ejecución 55555555 · FAILED · actor agent-a · resultado SHA-256 bbbbbbbbbbbb/)).toBeInTheDocument();
    expect(screen.getByText(/Revisión 66666666 · REJECT · candidato cccccccccccc · requiere atención/)).toBeInTheDocument();
    expect(screen.getByText(/Hay revisiones rechazadas en el estado persistido/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar consolidación' })).toBeDisabled();
  });

  it('submits CEO summary against the currently displayed source hash', async () => {
    const readyGroup = { ...group, consolidation_ready: true, children: [{ ...group.children[0], status: 'DONE' }] };
    const port = setup([readyGroup]);
    await screen.findByText('DONE');
    fireEvent.change(screen.getByLabelText('Síntesis CEO (persistente)'), { target: { value: 'He revisado el resultado y la evidencia.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar consolidación' }));
    await waitFor(() => expect(port.confirmWorkGroupConsolidation).toHaveBeenCalledWith('project-active', group.id, {
      idempotency_key: expect.any(String), expected_source_sha256: 'a'.repeat(64), summary: 'He revisado el resultado y la evidencia.',
    }));
    expect(await screen.findByText(/Consolidación CEO guardada/)).toBeInTheDocument();
  });

  it('records product acceptance only after a current consolidation and exact criteria', async () => {
    const readyGroup: ProjectWorkGroup = {
      ...group, consolidation_ready: true, children: [{ ...group.children[0], status: 'DONE', executions: [] }],
      consolidation: {
        id: '66666666-6666-4666-8666-666666666666', summary: 'Consolidado', source_sha256: 'a'.repeat(64),
        idempotency_key: '77777777-7777-4777-8777-777777777777', created_by: 'ceo', created_at: '2026-10-26T00:00:00Z',
      },
    };
    const port = setup([readyGroup]);
    await screen.findByText('DONE');
    expect(screen.getByText(/Criterios confirmados: completado/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Registra la decisión explícita de aceptación del resultado…'), { target: { value: 'Cumple el criterio acordado.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aceptar resultado de producto' }));
    await waitFor(() => expect(port.confirmWorkGroupAcceptance).toHaveBeenCalledWith('project-active', group.id, {
      idempotency_key: expect.any(String), expected_source_sha256: 'a'.repeat(64),
      accepted_criteria: ['completado'], acceptance_statement: 'Cumple el criterio acordado.',
    }));
    expect(await screen.findByText(/Aceptación de producto registrada por el CEO/)).toBeInTheDocument();
  });

  it('assigns a child only to an agent returned by the backend and refreshes the projection', async () => {
    const assignableGroup = { ...group, children: [{ ...group.children[0], executions: [] }] };
    const port = setup([assignableGroup]);
    await screen.findByText('IN_PROGRESS');
    fireEvent.change(screen.getByLabelText('Asignar responsable'), { target: { value: 'agent-a' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar' }));
    await waitFor(() => expect(port.assignWorkGroupChild).toHaveBeenCalledWith(group.children[0].work_id, 'agent-a'));
    expect(await screen.findByText(/No se han creado grants/)).toBeInTheDocument();
    expect(port.listAssignableAgents).toHaveBeenCalledWith('project-active');
  });

  it('lets a PM use assignment without exposing CEO-only report, consolidation, or acceptance controls', async () => {
    const assignableGroup = { ...group, children: [{ ...group.children[0], executions: [] }] };
    const port = setup([assignableGroup], false);
    await screen.findByText('IN_PROGRESS');
    expect(screen.getByLabelText('Asignar responsable')).toBeInTheDocument();
    expect(screen.queryByLabelText('Registrar observación no final')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Síntesis CEO (persistente)')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Aceptación de producto CEO')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Asignar responsable'), { target: { value: 'agent-b' } });
    fireEvent.click(screen.getByRole('button', { name: 'Asignar' }));
    await waitFor(() => expect(port.assignWorkGroupChild).toHaveBeenCalledWith(group.children[0].work_id, 'agent-b'));
  });

  it('records an explicitly non-final CEO report against the displayed source hash', async () => {
    const port = setup([group]);
    await screen.findByText('IN_PROGRESS');
    fireEvent.change(screen.getByLabelText('Registrar observación no final'), { target: { value: 'Revisión de conflicto' } });
    fireEvent.change(screen.getByPlaceholderText(/Registra una observación CEO/), { target: { value: 'Una tarea está pendiente.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar informe no final' }));
    await waitFor(() => expect(port.createWorkGroupPartialReport).toHaveBeenCalledWith('project-active', group.id, {
      idempotency_key: expect.any(String), expected_source_sha256: 'a'.repeat(64),
      report_kind: 'PARTIAL', summary: 'Una tarea está pendiente.',
    }));
    expect(await screen.findByText(/Informe no final guardado/)).toBeInTheDocument();
  });
});
