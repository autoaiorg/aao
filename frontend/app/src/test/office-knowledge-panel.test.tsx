import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OfficeKnowledgePanel } from '../features/office/components/OfficeKnowledgePanel';
import type { DataState, ProjectBoard, ProjectSummary } from '../domain/models';

describe('OfficeKnowledgePanel', () => {
  const projects: DataState<ProjectSummary[]> = {
    kind: 'ready', origin: 'live', fetchedAt: '2026-10-26T00:00:00Z',
    data: [{ id: 'project-1', name: 'Proyecto real', status: 'ACTIVE' }],
  };
  const board: DataState<ProjectBoard> = {
    kind: 'ready', origin: 'live', fetchedAt: '2026-10-26T00:00:00Z',
    data: {
      projectId: 'project-1', totalCount: 1, unrecognizedItems: [],
      items: [{ id: 'work-1', title: 'Actualizar motor', status: 'DONE', evidence: ['evidence-ref'],
        executions: [{ id: 'execution-1', status: 'SUCCEEDED', attempts: 1, created_at: '2026-10-26T00:00:00Z' }],
        reviews: [{ id: 'review-1', work_id: 'work-1', reviewer_id: 'auditor', decision: 'APPROVE', created_at: '2026-10-26T00:00:00Z' }],
        acceptanceCriteria: ['Pruebas verdes'] }],
      stages: { INBOX: [], READY: [], IN_PROGRESS: [], IN_REVIEW: [], VERIFIED: [], DONE: [] },
    },
  };

  it('renders canonical records and navigates to the selected work item', async () => {
    const onOpenBoard = vi.fn();
    const port = { getProjectBoard: vi.fn().mockResolvedValue(board) };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}>
      <OfficeKnowledgePanel projects={projects} port={port} sessionId="ceo-session" onOpenBoard={onOpenBoard} />
    </QueryClientProvider>);

    expect(await screen.findByText('Actualizar motor')).toBeInTheDocument();
    expect(screen.getByText(/1 referencias de evidencia · 1 ejecuciones · 1 revisiones/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Actualizar motor/ }));
    expect(onOpenBoard).toHaveBeenCalledWith('project-1', 'work-1');
    await waitFor(() => expect(port.getProjectBoard).toHaveBeenCalledWith('project-1'));
  });
});
