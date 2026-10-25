import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OfficeWorkRequestPanel } from '../features/office/components/OfficeWorkRequestPanel';
import { VirtualOfficeView } from '../features/office/VirtualOfficeView';
import type { DataState, OrganizationStructure, ProjectSummary } from '../domain/models';
import type { CreatedWorkRequest } from '../data/ports/AaoWorkCommandPort';
import { DEMO_ORG_STRUCTURE } from '../data/adapters/demo/fixtures';

const projects: DataState<ProjectSummary[]> = {
  kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
    { id: 'project-a', name: 'Proyecto activo', status: 'ACTIVE' },
    { id: 'project-paused', name: 'Proyecto pausado', status: 'PAUSED' },
  ],
};

describe('office CEO work requests', () => {
  it('sends a request to the selected active project and exposes the canonical work ID', async () => {
    const onCreate = vi.fn().mockResolvedValue({
      kind: 'ready', origin: 'live', fetchedAt: 'now',
      data: { id: '00000000-0000-4000-8000-000000000001', status: 'INBOX' },
    } satisfies DataState<CreatedWorkRequest>);
    const onOpenBoard = vi.fn();
    render(<OfficeWorkRequestPanel projects={projects} onCreate={onCreate} onOpenBoard={onOpenBoard} />);

    fireEvent.change(screen.getByLabelText('Proyecto activo'), { target: { value: 'project-a' } });
    fireEvent.change(screen.getByLabelText('Solicitud'), { target: { value: 'Añadir informe' } });
    fireEvent.change(screen.getByLabelText('Contexto'), { target: { value: 'Usar datos persistentes' } });
    fireEvent.change(screen.getByLabelText('Criterios de aceptación'), { target: { value: 'Debe aparecer en el tablero\nTests verdes' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar en Entrada' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('project-a', {
      title: 'Añadir informe', description: 'Usar datos persistentes',
      acceptance_criteria: ['Debe aparecer en el tablero', 'Tests verdes'],
    }));
    expect(screen.getByText(/00000000-0000-4000-8000-000000000001/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir tablero' }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-a');
    expect(screen.queryByRole('option', { name: 'Proyecto pausado' })).not.toBeInTheDocument();
  });

  it('keeps the request composer out of demo and non-CEO views', () => {
    const demo: DataState<OrganizationStructure> = {
      kind: 'ready', origin: 'demo', data: DEMO_ORG_STRUCTURE, fetchedAt: 'now',
    };
    const create = vi.fn();
    const { rerender } = render(<VirtualOfficeView
      organization={demo} projects={projects} canCreateWorkRequest onCreateWorkRequest={create}
    />);
    expect(screen.queryByRole('heading', { name: 'Dirigir trabajo a un proyecto' })).not.toBeInTheDocument();

    const live: DataState<OrganizationStructure> = {
      kind: 'ready', origin: 'live', data: { ...DEMO_ORG_STRUCTURE, units: [], agents: [] }, fetchedAt: 'now',
    };
    rerender(<VirtualOfficeView organization={live} projects={projects} />);
    expect(screen.queryByRole('heading', { name: 'Dirigir trabajo a un proyecto' })).not.toBeInTheDocument();
    rerender(<VirtualOfficeView organization={live} projects={projects} canCreateWorkRequest onCreateWorkRequest={create} />);
    expect(screen.getByRole('heading', { name: 'Dirigir trabajo a un proyecto' })).toBeInTheDocument();
  });
});
