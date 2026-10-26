import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeActivityPanel } from '../features/office/components/OfficeActivityPanel';
import type { AaoReadPort } from '../data/ports/AaoReadPort';
import type { ActivityEvent, DataState, ProjectSummary } from '../domain/models';

const projects: DataState<ProjectSummary[]> = { kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
  { id: 'project-a', name: 'Proyecto A', status: 'ACTIVE' },
  { id: 'project-b', name: 'Proyecto B', status: 'ACTIVE' },
] };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });
const events: ActivityEvent[] = [{
  id: 'event-1', subject_id: 'work-123', kind: 'work.requested', details: { owner: 'ceo' }, created_at: '2026-10-26T00:00:00Z',
}, {
  id: 'event-2', subject_id: 'execution-234', kind: 'execution.claimed', details: { token: 'must-not-render' }, created_at: '2026-10-26T00:01:00Z',
}, {
  id: 'event-3', subject_id: 'work-345', kind: 'work.dispatch_blocked',
  details: { reason: 'A capability evaluation selecting a registered version is required', secret: 'must-not-render' },
  created_at: '2026-10-26T00:02:00Z',
}, {
  id: 'event-4', subject_id: 'work-456', kind: 'work.execution_quarantined',
  details: {
    execution_id: 'execution-456',
    next_action: 'An independent auditor must review evidence before disposition; do not retry automatically.',
    secret: 'must-not-render',
  },
  created_at: '2026-10-26T00:03:00Z',
}];

function renderPanel(getProjectActivity: AaoReadPort['getProjectActivity'], onOpenBoard = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeActivityPanel projects={projects}
    port={{ getProjectActivity }} sessionId="session-a" onOpenBoard={onOpenBoard} /></QueryClientProvider>);
  return onOpenBoard;
}

describe('office persisted activity panel', () => {
  it('shows backend event kind, subject and time without rendering opaque event details', async () => {
    const getActivity = vi.fn().mockResolvedValue(ready(events));
    const onOpenBoard = renderPanel(getActivity);

    expect(await screen.findByText('Trabajo · work.requested')).toBeInTheDocument();
    expect(screen.getByText('Ejecución · execution.claimed')).toBeInTheDocument();
    expect(screen.getByText('Bloqueo de despacho · work.dispatch_blocked')).toBeInTheDocument();
    expect(screen.getByText('Lease expirada · ejecución en cuarentena · work.execution_quarantined')).toBeInTheDocument();
    expect(screen.getByText('An independent auditor must review evidence before disposition; do not retry automatically.')).toBeInTheDocument();
    expect(screen.getByText('A capability evaluation selecting a registered version is required')).toBeInTheDocument();
    expect(screen.getByText('work-123')).toBeInTheDocument();
    expect(screen.queryByText('must-not-render')).not.toBeInTheDocument();
    expect(getActivity).toHaveBeenCalledWith('project-a');
    fireEvent.click(screen.getByRole('button', { name: /Trabajo · work\.requested/ }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-a', 'work-123');
    fireEvent.click(screen.getByRole('button', { name: /Ejecución · execution\.claimed/ }));
    expect(onOpenBoard).toHaveBeenLastCalledWith('project-a', undefined);
    expect(screen.getByText(/no una señal de presencia del agente/)).toBeInTheDocument();
  });

  it('loads events for the selected project from the canonical read port', async () => {
    const getActivity = vi.fn().mockResolvedValue(ready([]));
    renderPanel(getActivity);
    expect(await screen.findByText('No hay actividad registrada en este proyecto.')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Proyecto de actividad' }), { target: { value: 'project-b' } });
    await waitFor(() => expect(getActivity).toHaveBeenCalledWith('project-b'));
  });
});
