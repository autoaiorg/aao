import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  title: 'Resultados del proyecto', parent_status: 'INBOX', source_sha256: 'a'.repeat(64),
  consolidation_ready: false,
  children: [{
    work_id: '44444444-4444-4444-8444-444444444444', status: 'IN_PROGRESS', assigned_principal_id: null, evidence: [],
    executions: [{ id: '55555555-5555-4555-8555-555555555555', status: 'RUNNING', worker_id: 'agent-a', result_sha256: null }], reviews: [],
  }],
  consolidation: null,
};

function setup(groups: ProjectWorkGroup[]) {
  const port = {
    listAssignableAgents: vi.fn().mockResolvedValue(ready([
      { principal_id: 'agent-a', display_name: 'Agente A' },
      { principal_id: 'agent-b', display_name: 'Agente B' },
    ])),
    listProjectWorkGroups: vi.fn().mockResolvedValue(ready(groups)),
    assignWorkGroupChild: vi.fn().mockResolvedValue(ready({ work_id: group.children[0].work_id, principal_id: 'agent-a', assigned_by: 'ceo', grants_created: false as const })),
    confirmWorkGroupConsolidation: vi.fn().mockResolvedValue(ready({ ...group, project_id: 'project-active', work_group_id: group.id, source_snapshot: { children: group.children }, summary: 'Resultado consolidado', idempotency_key: '66666666-6666-4666-8666-666666666666', created_by: 'ceo', created_at: '2026-10-26T00:00:00Z', created: true })),
  } as unknown as AaoConversationPort;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeWorkGroupPanel projects={projects} port={port} sessionId="session-a" onOpenBoard={vi.fn()} /></QueryClientProvider>);
  return port;
}

describe('office work group consolidation', () => {
  it('shows persisted child status and keeps consolidation unavailable until all children are DONE', async () => {
    const port = setup([group]);
    expect(await screen.findByText('IN_PROGRESS')).toBeInTheDocument();
    expect(screen.getByText(/1 ejecuciones · 0 revisiones/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar consolidación' })).toBeDisabled();
    expect(port.confirmWorkGroupConsolidation).not.toHaveBeenCalled();
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
});
