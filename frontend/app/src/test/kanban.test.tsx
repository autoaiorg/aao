import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { KanbanView } from '../features/kanban/KanbanView';
import type { ProjectBoard, DataState } from '../domain/models';

describe('KanbanView Six Canonical Lifecycle States', () => {
  const mockBoard: ProjectBoard = {
    projectId: 'test-proj',
    projectName: 'Proyecto de Prueba',
    totalCount: 3,
    unrecognizedItems: [],
    stages: {
      INBOX: [{ id: 'task-1', title: 'Tarea Entrada', status: 'INBOX' }],
      READY: [{ id: 'task-2', title: 'Tarea Preparada', status: 'READY' }],
      IN_PROGRESS: [{ id: 'task-3', title: 'Tarea En Curso', status: 'IN_PROGRESS' }],
      IN_REVIEW: [],
      VERIFIED: [],
      DONE: [],
    },
    items: [],
  };

  const boardState: DataState<ProjectBoard> = {
    kind: 'ready',
    origin: 'live',
    data: mockBoard,
    fetchedAt: new Date().toISOString(),
  };

  it('renders all six lifecycle columns with Spanish labels', () => {
    render(
      <KanbanView
        boardState={boardState}
        selectedProjectId="test-proj"
        projectName="Proyecto de Prueba"
        onRefresh={() => {}}
      />
    );

    expect(screen.getByText('Entrada')).toBeInTheDocument();
    expect(screen.getByText('Preparado')).toBeInTheDocument();
    expect(screen.getByText('En curso')).toBeInTheDocument();
    expect(screen.getByText('Revisión')).toBeInTheDocument();
    expect(screen.getByText('Verificado')).toBeInTheDocument();
    expect(screen.getByText('Completado')).toBeInTheDocument();
  });

  it('renders task cards and opens detail drawer upon click', () => {
    render(
      <KanbanView
        boardState={boardState}
        selectedProjectId="test-proj"
        projectName="Proyecto de Prueba"
        onRefresh={() => {}}
      />
    );

    const taskCard = screen.getByText('Tarea Entrada');
    expect(taskCard).toBeInTheDocument();

    fireEvent.click(taskCard);

    // Detail drawer should open with title and security note
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Frontera de Seguridad/i)).toBeInTheDocument();
  });

  it('opens a task from a matching persisted work event', () => {
    const consumed = vi.fn();
    render(<KanbanView boardState={boardState} selectedProjectId="test-proj" onRefresh={() => {}}
      focusWorkId="task-2" onFocusWorkConsumed={consumed} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(screen.getByRole('dialog')).getByText('Tarea Preparada')).toBeInTheDocument();
    expect(consumed).toHaveBeenCalled();
  });

  it('prompts user to select a project if none is active', () => {
    render(
      <KanbanView
        boardState={{ kind: 'empty', origin: 'live', fetchedAt: '' }}
        selectedProjectId={null}
        onRefresh={() => {}}
      />
    );

    expect(screen.getByText('Seleccione un proyecto específico')).toBeInTheDocument();
  });
});
