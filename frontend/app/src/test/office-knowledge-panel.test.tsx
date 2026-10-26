import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OfficeKnowledgePanel } from '../features/office/components/OfficeKnowledgePanel';
import type { DataState, KnowledgeSourceRecord, ProjectSummary } from '../domain/models';

describe('OfficeKnowledgePanel', () => {
  const projects: DataState<ProjectSummary[]> = {
    kind: 'ready', origin: 'live', fetchedAt: '2026-10-26T00:00:00Z',
    data: [{ id: 'project-1', name: 'Proyecto real', status: 'ACTIVE' }],
  };
  const index: DataState<KnowledgeSourceRecord[]> = {
    kind: 'ready', origin: 'live', fetchedAt: '2026-10-26T00:00:00Z',
    data: [
      { workId: 'work-1', projectId: 'project-1', projectName: 'Proyecto real', title: 'Actualizar motor', status: 'DONE', evidenceReferences: ['sha256:work-evidence-ref'],
        reviews: [{ id: 'review-1', reviewerId: 'auditor', decision: 'APPROVE', evidenceReferences: ['sha256:review-evidence-ref'], createdAt: '2026-10-26T00:00:00Z' }] },
      { workId: 'work-2', projectId: 'project-2', projectName: 'Otro proyecto', title: 'Revisar contratos', status: 'IN_REVIEW', evidenceReferences: [], reviews: [] },
    ],
  };

  it('renders canonical records and navigates to the selected work item', async () => {
    const onOpenBoard = vi.fn();
    const port = { getKnowledgeSourceIndex: vi.fn().mockResolvedValue(index) };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      <OfficeKnowledgePanel projects={projects} port={port} sessionId="ceo-session" onOpenBoard={onOpenBoard} />
    </QueryClientProvider>);

    expect(await screen.findByText('Actualizar motor')).toBeInTheDocument();
    expect(screen.getByText(/1 referencias de trabajo · 1 revisiones · ID work-1/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Referencias canónicas \(2\)/));
    expect(screen.getByText('sha256:work-evidence-ref')).toBeInTheDocument();
    expect(screen.getByText('sha256:review-evidence-ref')).toBeInTheDocument();
    expect(screen.queryByText('private patch data')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Actualizar motor/ }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-1', 'work-1');
    fireEvent.change(screen.getByRole('textbox', { name: 'Buscar en índice corporativo' }), { target: { value: 'Otro proyecto' } });
    expect(screen.getByText('Revisar contratos')).toBeInTheDocument();
    expect(screen.queryByText('Actualizar motor')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Revisar contratos/ }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-2', 'work-2');
    await waitFor(() => expect(port.getKnowledgeSourceIndex).toHaveBeenCalled());
  });
});
