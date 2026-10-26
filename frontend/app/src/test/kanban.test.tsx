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
      INBOX: [{ id: 'task-1', title: 'Tarea Entrada', status: 'INBOX', priority: 'NORMAL' }],
      READY: [{ id: 'task-2', title: 'Tarea Preparada', status: 'READY', priority: 'NORMAL' }],
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

  it('exposes priority changes only when the caller provides CEO LIVE capability', () => {
    const savePriority = vi.fn().mockResolvedValue({ kind: 'ready', origin: 'live', data: {} });
    render(<KanbanView boardState={boardState} selectedProjectId="test-proj" onRefresh={() => {}}
      canManagePriority onSetPriority={savePriority} />);
    fireEvent.click(screen.getByText('Tarea Entrada'));
    expect(screen.getByLabelText('Cambiar prioridad')).toBeInTheDocument();
  });

  it('persists a selected priority through the injected backend command', async () => {
    const savePriority = vi.fn().mockResolvedValue({ kind: 'ready', origin: 'live', data: {} });
    render(<KanbanView boardState={boardState} selectedProjectId="test-proj" onRefresh={() => {}}
      canManagePriority onSetPriority={savePriority} />);
    fireEvent.click(screen.getByText('Tarea Entrada'));
    fireEvent.change(screen.getByLabelText('Cambiar prioridad'), { target: { value: 'HIGH' } });
    expect(savePriority).toHaveBeenCalledWith('task-1', 'HIGH');
    expect(await screen.findByText('Prioridad guardada en AAO.')).toBeInTheDocument();
  });

  it('keeps priority controls absent without CEO capability', () => {
    render(<KanbanView boardState={boardState} selectedProjectId="test-proj" onRefresh={() => {}} />);
    fireEvent.click(screen.getByText('Tarea Entrada'));
    expect(screen.queryByLabelText('Cambiar prioridad')).not.toBeInTheDocument();
  });

  it('disables priority mutation if the LIVE projection has no persisted value', () => {
    const missingPriorityBoard = { ...mockBoard, stages: { ...mockBoard.stages,
      INBOX: [{ id: 'task-missing', title: 'Prioridad no disponible', status: 'INBOX' }],
    } };
    render(<KanbanView boardState={{ ...boardState, data: missingPriorityBoard }} selectedProjectId="test-proj"
      onRefresh={() => {}} canManagePriority onSetPriority={vi.fn()} />);
    fireEvent.click(screen.getByText('Prioridad no disponible'));
    const priorityRegion = within(screen.getByRole('region', { name: 'Prioridad del trabajo' }));
    expect(priorityRegion.getByText('No disponible', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByLabelText('Cambiar prioridad')).toBeDisabled();
  });
});
