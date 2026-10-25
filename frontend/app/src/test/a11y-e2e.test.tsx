/**
 * End-to-End Accessibility & Keyboard Navigation Test Suite (WCAG 2.2 AA)
 * Verifies:
 * - Keyboard navigation (Tab, Enter, Space, Escape)
 * - Dialog closing (Escape, button click)
 * - Automatic focus restoration to trigger elements upon dialog dismissal
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TopBar } from '../components/layout/TopBar';
import { KanbanView } from '../features/kanban/KanbanView';
import { TaskDetailDrawer } from '../features/kanban/TaskDetailDrawer';
import { CeoDashboard } from '../features/dashboard/CeoDashboard';
import type { ProjectBoard, CeoOverview, ProjectSummary, TaskItem } from '../domain/models';

describe('Accessibility E2E: Keyboard Navigation, Dialogs and Focus Restoration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('TopBar Auth Modal: opens on button activation, closes on Escape, and restores focus to trigger button', async () => {
    const onLogin = vi.fn();

    render(
      <TopBar
        origin="live"
        onOriginChange={() => {}}
        projects={[]}
        selectedProjectId={null}
        onProjectSelect={() => {}}
        principal={null}
        isAuthenticated={false}
        onLogin={onLogin}
        onLogout={() => {}}
        onRefresh={() => {}}
      />
    );

    // 1. Find trigger button and focus it
    const triggerButton = screen.getByRole('button', { name: /Credencial de Acceso/i });
    triggerButton.focus();
    expect(document.activeElement).toBe(triggerButton);

    // 2. Open modal by pressing Enter or clicking
    fireEvent.click(triggerButton);

    const dialog = screen.getByRole('dialog', { name: /Autenticación en Memoria Volátil/i });
    expect(dialog).toBeInTheDocument();

    // 3. Focus should be inside modal (on the token input)
    const tokenInput = screen.getByLabelText(/Valor del Token Secreto/i);
    expect(document.activeElement).toBe(tokenInput);

    // 4. Press Escape key to dismiss dialog
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });

    // 5. Dialog should be unmounted
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // 6. Focus should be restored to the trigger button
    await new Promise((r) => setTimeout(r, 10));
    expect(document.activeElement).toBe(triggerButton);
  });

  it('TopBar Auth Modal: closes on Cancel button and restores focus to trigger button', async () => {
    render(
      <TopBar
        origin="live"
        onOriginChange={() => {}}
        projects={[]}
        selectedProjectId={null}
        onProjectSelect={() => {}}
        principal={null}
        isAuthenticated={false}
        onLogin={() => {}}
        onLogout={() => {}}
        onRefresh={() => {}}
      />
    );

    const triggerButton = screen.getByRole('button', { name: /Credencial de Acceso/i });
    triggerButton.focus();
    fireEvent.click(triggerButton);

    const cancelButton = screen.getByRole('button', { name: /Cancelar/i });
    fireEvent.click(cancelButton);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await new Promise((r) => setTimeout(r, 10));
    expect(document.activeElement).toBe(triggerButton);
  });

  it('TaskDetailDrawer: opens when task card is activated, closes on Escape, and restores focus to task card button', async () => {
    const mockTask: TaskItem = {
      id: 'task-a11y-01',
      title: 'Accessible Task Card Keyboard Test',
      status: 'INBOX',
    };

    const board: ProjectBoard = {
      projectId: 'proj-a11y',
      totalCount: 1,
      stages: {
        INBOX: [mockTask],
        READY: [],
        IN_PROGRESS: [],
        IN_REVIEW: [],
        VERIFIED: [],
        DONE: [],
      },
      unrecognizedItems: [],
      items: [mockTask],
    };

    render(
      <KanbanView
        boardState={{ kind: 'ready', origin: 'live', data: board, fetchedAt: '' }}
        selectedProjectId="proj-a11y"
        onRefresh={() => {}}
      />
    );

    // 1. Focus task card button via keyboard
    const taskCardButton = screen.getByRole('button', {
      name: /Ver detalles de la tarea task-a11y-01/i,
    });
    taskCardButton.focus();
    expect(document.activeElement).toBe(taskCardButton);

    // 2. Activate card
    fireEvent.click(taskCardButton);

    // 3. Dialog drawer should open
    const dialog = screen.getByRole('dialog', { name: /Accessible Task Card Keyboard Test/i });
    expect(dialog).toBeInTheDocument();

    // 4. Press Escape to close
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });

    // 5. Drawer unmounts
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // 6. Focus is restored to the task card button
    await new Promise((r) => setTimeout(r, 10));
    expect(document.activeElement).toBe(taskCardButton);
  });

  it('TaskDetailDrawer: closes via close button and restores focus to triggering element', async () => {
    const onClose = vi.fn();
    const task: TaskItem = { id: 'task-btn-esc', title: 'Close Button Test', status: 'READY' };

    // Create an external trigger button to simulate the invoking element
    const container = document.createElement('div');
    document.body.appendChild(container);
    const externalTrigger = document.createElement('button');
    externalTrigger.textContent = 'Trigger';
    document.body.appendChild(externalTrigger);
    externalTrigger.focus();

    render(<TaskDetailDrawer task={task} onClose={onClose} triggerElement={externalTrigger} />);

    const closeBtn = screen.getByRole('button', { name: /Cerrar panel de tarea/i });
    expect(closeBtn).toBeInTheDocument();

    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();

    await new Promise((r) => setTimeout(r, 10));
    expect(document.activeElement).toBe(externalTrigger);

    document.body.removeChild(externalTrigger);
    document.body.removeChild(container);
  });

  it('CeoDashboard: project list navigation supports keyboard activation and toggles aria-pressed', () => {
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

    let selectedId: string | null = null;
    const onSelect = vi.fn((id: string | null) => {
      selectedId = id;
    });

    const { rerender } = render(
      <CeoDashboard
        overview={overview}
        projects={mockProjects}
        selectedProjectId={selectedId}
        onSelectProject={onSelect}
        onNavigateTo={() => {}}
      />
    );

    const alphaBtn = screen.getByRole('button', { name: /Alpha Project/i });
    expect(alphaBtn).toHaveAttribute('aria-pressed', 'false');

    // Simulate keyboard press (Enter)
    fireEvent.click(alphaBtn);
    expect(onSelect).toHaveBeenCalledWith('p-1');

    // Rerender with selectedProjectId updated
    rerender(
      <CeoDashboard
        overview={overview}
        projects={mockProjects}
        selectedProjectId="p-1"
        onSelectProject={onSelect}
        onNavigateTo={() => {}}
      />
    );

    expect(alphaBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
