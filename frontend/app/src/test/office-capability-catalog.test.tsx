import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { OfficeCapabilityCatalogPanel } from '../features/office/components/OfficeCapabilityCatalogPanel';
import type { AaoReadPort } from '../data/ports/AaoReadPort';
import type { CapabilitySummary, DataState, ProjectSummary } from '../domain/models';
import type { AaoCapabilityFeedbackPort, CapabilityFeedbackProposal } from '../data/ports/AaoCapabilityFeedbackPort';

const projects: DataState<ProjectSummary[]> = { kind: 'ready', origin: 'live', fetchedAt: 'now', data: [
  { id: 'project-a', name: 'Proyecto A', status: 'ACTIVE' },
  { id: 'project-b', name: 'Proyecto B', status: 'ACTIVE' },
  { id: 'project-closed', name: 'Proyecto cerrado', status: 'DONE' },
] };
const ready = <T,>(data: T): DataState<T> => ({ kind: 'ready', origin: 'live', fetchedAt: 'now', data });
const skill: CapabilitySummary = {
  capability_id: 'review-skill', version: '2', capability_type: 'agent_skill', status: 'evaluated',
  provenance: {}, contract: {}, created_by: 'agent-1', created_at: 'now', evidence: ['test:one'],
  execution_authorized: false,
};

function renderPanel(getProjectCapabilities: AaoReadPort['getProjectCapabilities'], feedbackPort: AaoCapabilityFeedbackPort = {
  listCapabilityFeedback: vi.fn().mockResolvedValue(ready([])),
  proposeCapabilityFeedback: vi.fn().mockResolvedValue(ready({ id: 'proposal-1', capability_id: 'review-skill', version: '2', work_id: null, status: 'proposed', applied: false as const })),
}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><OfficeCapabilityCatalogPanel projects={projects}
    port={{ getProjectCapabilities }} feedbackPort={feedbackPort} sessionId="session-a" /></QueryClientProvider>);
  return client;
}

describe('office capability catalog', () => {
  it('shows only persisted project capability versions and states execution is not authorized', async () => {
    const getCapabilities = vi.fn().mockResolvedValue(ready([skill]));
    renderPanel(getCapabilities);

    expect(await screen.findByText('review-skill')).toBeInTheDocument();
    expect(screen.getByText('Versión 2 · evaluated')).toBeInTheDocument();
    expect(screen.getByText(/Registrada por agent-1 · 1 referencias de evidencia/)).toBeInTheDocument();
    expect(screen.getAllByText('Autoriza ejecución: no')).toHaveLength(1);
    expect(getCapabilities).toHaveBeenCalledWith('project-a');
    expect(screen.queryByText('Proyecto cerrado')).not.toBeInTheDocument();
  });

  it('reloads the canonical catalog when project selection changes', async () => {
    const getCapabilities = vi.fn().mockImplementation(async (projectId: string) => ready(
      projectId === 'project-a' ? [skill] : [],
    ));
    renderPanel(getCapabilities);

    expect(await screen.findByText('review-skill')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Proyecto del catálogo de capacidades' }), {
      target: { value: 'project-b' },
    });
    expect(await screen.findByText('No hay capacidades registradas en este proyecto.')).toBeInTheDocument();
    await waitFor(() => expect(getCapabilities).toHaveBeenCalledWith('project-b'));
  });

  it('persists an evidence-linked proposal and renders it as unapplied', async () => {
    const saved: CapabilityFeedbackProposal = {
      id: 'proposal-1', capability_id: 'review-skill', version: '2', work_id: null,
      correction: 'Aclarar límite de revisión', evidence: ['work:abc'], status: 'proposed',
      created_by: 'ceo', created_at: 'now', applied: false,
    };
    const feedbackPort: AaoCapabilityFeedbackPort = {
      listCapabilityFeedback: vi.fn().mockResolvedValue(ready([saved])),
      proposeCapabilityFeedback: vi.fn().mockResolvedValue(ready({
        id: saved.id, capability_id: saved.capability_id, version: saved.version,
        work_id: null, status: 'proposed', applied: false,
      })),
    };
    renderPanel(vi.fn().mockResolvedValue(ready([skill])), feedbackPort);

    await screen.findByText('review-skill');
    fireEvent.change(screen.getByLabelText('Corrección observada'), { target: { value: saved.correction } });
    fireEvent.change(screen.getByLabelText('Referencias de evidencia (una por línea; exige trabajo o evidencia)'), { target: { value: 'work:abc' } });
    fireEvent.click(screen.getByRole('button', { name: 'Proponer corrección' }));

    await screen.findByText('Propuesta persistida; no se ha aplicado a la skill ni al catálogo.');
    expect(feedbackPort.proposeCapabilityFeedback).toHaveBeenCalledWith('project-a', {
      capability_id: 'review-skill', version: '2', correction: saved.correction, work_id: null, evidence: ['work:abc'],
    });
    expect(await screen.findByText(/aplicada: no/)).toBeInTheDocument();
    expect(feedbackPort.listCapabilityFeedback).toHaveBeenCalledWith('project-a');
  });

});
