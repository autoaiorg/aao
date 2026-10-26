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
  it('projects persisted due dates from the canonical board, orders them and opens the canonical work item', async () => {
    const board: ProjectBoard = {
      projectId: 'project-a', totalCount: 3, stages: {} as ProjectBoard['stages'], unrecognizedItems: [], items: [
        { id: 'later', title: 'Más tarde', status: 'INBOX', dueDate: '2026-12-10' },
        { id: 'undated', title: 'Sin fecha', status: 'INBOX' },
        { id: 'soon', title: 'Próximo', status: 'INBOX', dueDate: '2026-11-01' },
      ],
    };
    const getBoard = vi.fn().mockResolvedValue(ready(board));
    const onOpenWork = renderCalendar(getBoard);

    const soon = await screen.findByRole('button', { name: /Próximo/ });
    const datedList = screen.getByRole('list', { name: 'Trabajos con fecha objetivo' });
    expect(Array.from(datedList.querySelectorAll('.office-calendar__item-title')).map((item) => item.textContent))
      .toEqual(['Próximo', 'Más tarde']);
    expect(screen.queryByRole('button', { name: /Sin fecha/ })).not.toBeInTheDocument();
    expect(getBoard).toHaveBeenCalledWith('project-a');
    fireEvent.click(soon);
    expect(onOpenWork).toHaveBeenCalledWith('project-a', 'soon');
    expect(screen.getByText(/No programa ni inicia ejecuciones/)).toBeInTheDocument();
    expect(screen.queryByText('Sin fecha')).not.toBeInTheDocument();
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
