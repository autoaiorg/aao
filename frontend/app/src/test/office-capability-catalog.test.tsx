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
  provenance: {}, contract: { purpose: 'Review', compatible_roles: ['agent'], inputs: ['x'], outputs: ['y'], usage_limits: ['project'] }, created_by: 'agent-1', created_at: 'now', evidence: ['test:one'],
  execution_authorized: false,
};

function renderPanel(getProjectCapabilities: AaoReadPort['getProjectCapabilities'], feedbackPort: AaoCapabilityFeedbackPort = {
  listCapabilityFeedback: vi.fn().mockResolvedValue(ready([])),
  proposeCapabilityFeedback: vi.fn().mockResolvedValue(ready({ id: 'proposal-1', capability_id: 'review-skill', version: '2', work_id: null, status: 'proposed', applied: false as const })),
  reviewCapabilityFeedback: vi.fn().mockResolvedValue(ready({ id: 'proposal-1', status: 'accepted', reviewed_by: 'ceo', reviewed_at: '2026-10-26T00:00:00Z', applied: false as const })),
  registerFeedbackCapabilityVersion: vi.fn().mockResolvedValue(ready({ id: 'proposal-1', capability_id: 'review-skill', source_version: '2', version: '3', status: 'registered_local' as const, applied: true as const, execution_authorized: false as const })),
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
      created_by: 'ceo', created_at: 'now', reviewed_by: null, reviewed_at: null, applied: false,
      applied_capability_version: null, applied_by: null, applied_at: null,
    };
    const feedbackPort: AaoCapabilityFeedbackPort = {
      listCapabilityFeedback: vi.fn().mockResolvedValue(ready([saved])),
      proposeCapabilityFeedback: vi.fn().mockResolvedValue(ready({
        id: saved.id, capability_id: saved.capability_id, version: saved.version,
        work_id: null, status: 'proposed', applied: false,
      })),
      reviewCapabilityFeedback: vi.fn().mockResolvedValue(ready({ id: saved.id, status: 'accepted', reviewed_by: 'ceo', reviewed_at: 'now', applied: false })),
      registerFeedbackCapabilityVersion: vi.fn(),
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


  it('allows an explicit CEO decision, records its reviewer, and keeps the capability unapplied', async () => {
    const proposal: CapabilityFeedbackProposal = {
      id: 'proposal-2', capability_id: 'review-skill', version: '2', work_id: null,
      correction: 'Aclarar límite', evidence: ['sha256:proof'], status: 'proposed',
      created_by: 'ceo', created_at: 'now', reviewed_by: null, reviewed_at: null, applied: false,
      applied_capability_version: null, applied_by: null, applied_at: null,
    };
    let decision: CapabilityFeedbackProposal['status'] = 'proposed';
    const feedbackPort: AaoCapabilityFeedbackPort = {
      listCapabilityFeedback: vi.fn().mockImplementation(async () => ready([{
        ...proposal,
        status: decision,
        reviewed_by: decision === 'proposed' ? null : 'ceo',
        reviewed_at: decision === 'proposed' ? null : '2026-10-26T00:00:00Z',
      }])),
      proposeCapabilityFeedback: vi.fn(),
      registerFeedbackCapabilityVersion: vi.fn().mockResolvedValue(ready({ id: proposal.id, capability_id: proposal.capability_id, source_version: proposal.version, version: '3', status: 'registered_local' as const, applied: true as const, execution_authorized: false as const })),
      reviewCapabilityFeedback: vi.fn().mockImplementation(async (_projectId, proposalId, status) => {
        decision = status;
        return ready({ id: proposalId, status, reviewed_by: 'ceo', reviewed_at: '2026-10-26T00:00:00Z', applied: false as const });
      }),
    };
    renderPanel(vi.fn().mockResolvedValue(ready([skill])), feedbackPort);

    expect(await screen.findByText('review-skill · 2 · proposed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Aceptar propuesta' }));
    expect(await screen.findByText('Propuesta aceptada; no aplicada a ninguna capacidad.')).toBeInTheDocument();
    expect(await screen.findByText('review-skill · 2 · accepted')).toBeInTheDocument();
    expect(screen.getByText(/Revisada por ceo/)).toBeInTheDocument();
    expect(screen.getByText(/aplicada: no/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Rechazar propuesta' })).not.toBeInTheDocument();
    expect(feedbackPort.reviewCapabilityFeedback).toHaveBeenCalledWith('project-a', 'proposal-2', 'accepted');
    fireEvent.click(screen.getByRole('button', { name: 'Preparar nueva versión' }));
    fireEvent.change(screen.getByLabelText('Versión nueva'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Referencias de pruebas (una por línea)'), { target: { value: 'test:new' } });
    fireEvent.change(screen.getByLabelText('Referencias de evidencia (una por línea)'), { target: { value: 'sha256:new' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar versión revisada' }));
    await screen.findByText('Registrada versión 3 (registered_local); no autoriza ejecución.');
    expect(feedbackPort.registerFeedbackCapabilityVersion).toHaveBeenCalledWith('project-a', 'proposal-2', expect.objectContaining({
      version: '3', tests: ['test:new'], evidence: ['sha256:new'],
      contract: skill.contract,
    }));
  });

});
