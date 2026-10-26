import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeCalendarPanel } from '../features/office/components/OfficeCalendarPanel';
import type { AaoReadPort } from '../data/ports/AaoReadPort';
import type { DataState, ProjectBoard, ProjectSummary } from '../domain/models';

const projects: DataState<ProjectSummary[]> = { kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
  { id: 'project-a', name: 'Proyecto A', status: 'ACTIVE' },
  { id: 'project-paused', name: 'Proyecto pausado', status: 'PAUSED' },
] };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });

function renderCalendar(getProjectBoard: AaoReadPort['getProjectBoard'], onOpenWork = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeCalendarPanel projects={projects}
    port={{ getProjectBoard }} sessionId="ceo-session" onOpenWork={onOpenWork} /></QueryClientProvider>);
  return onOpenWork;
}

describe('LIVE office work calendar', () => {
  it('projects persisted due dates in the selected month and opens the canonical work item', async () => {
    const now = new Date();
    const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const nextMonthKey = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, '0')}`;
    const board: ProjectBoard = {
      projectId: 'project-a', totalCount: 4, stages: {} as ProjectBoard['stages'], unrecognizedItems: [], items: [
        { id: 'later', title: 'Más tarde', status: 'INBOX', dueDate: `${nextMonthKey}-10` },
        { id: 'undated', title: 'Sin fecha', status: 'INBOX' },
        { id: 'soon', title: 'Próximo', status: 'INBOX', dueDate: `${thisMonth}-10` },
        { id: 'also-soon', title: 'Otro trabajo', status: 'DONE', dueDate: `${thisMonth}-10` },
      ],
    };
    const getBoard = vi.fn().mockResolvedValue(ready(board));
    const onOpenWork = renderCalendar(getBoard);

    const soon = await screen.findByRole('button', { name: /Próximo/ });
    expect(screen.getByRole('table', { name: /Calendario de/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Otro trabajo/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Sin fecha/ })).not.toBeInTheDocument();
    expect(getBoard).toHaveBeenCalledWith('project-a');
    fireEvent.click(soon);
    expect(onOpenWork).toHaveBeenCalledWith('project-a', 'soon');
    expect(screen.getByText(/No programa ni inicia ejecuciones/)).toBeInTheDocument();
    expect(screen.queryByText('Sin fecha')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    expect(await screen.findByRole('button', { name: /Más tarde/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Próximo/ })).not.toBeInTheDocument();
  });

  it('has an explicit empty state when the project has no dated work', async () => {
    const board: ProjectBoard = {
      projectId: 'project-a', totalCount: 1, stages: {} as ProjectBoard['stages'], unrecognizedItems: [],
      items: [{ id: 'undated', title: 'Solicitud', status: 'INBOX' }],
    };
    renderCalendar(vi.fn().mockResolvedValue(ready(board)));
    expect(await screen.findByText(/No hay trabajos con fecha objetivo registrada/)).toBeInTheDocument();
  });
});
