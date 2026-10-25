import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CeoDashboard } from '../features/dashboard/CeoDashboard';
import type { CeoOverview, ProjectSummary } from '../domain/models';

describe('CeoDashboard Honest Metrics & State Reporting', () => {
  const mockProjects: ProjectSummary[] = [
    { id: 'proj-1', name: 'Proyecto Alpha', status: 'ACTIVE' },
    { id: 'proj-2', name: 'Proyecto Beta', status: 'ACTIVE' },
  ];

  const fullOverview: CeoOverview = {
    projects: {
      kind: 'ready',
      origin: 'live',
      data: mockProjects,
      fetchedAt: new Date().toISOString(),
    },
    work: {
      kind: 'ready',
      origin: 'live',
      data: {
        totalTasks: 12,
        byStage: {
          INBOX: 2,
          READY: 2,
          IN_PROGRESS: 3,
          IN_REVIEW: 2,
          VERIFIED: 1,
          DONE: 2,
        },
        inReviewCount: 2,
        blockedCount: 0,
      },
      fetchedAt: new Date().toISOString(),
    },
    governance: {
      kind: 'unavailable',
      reason: 'Sin contrato API certificado en esta fase',
      retryable: false,
    },
    operations: {
      kind: 'ready',
      origin: 'live',
      data: {
        serviceHealth: 'healthy',
        readyStatus: true,
        checkedAt: new Date().toISOString(),
        message: 'Servicio FastAPI operativo',
      },
      fetchedAt: new Date().toISOString(),
    },
    alerts: {
      kind: 'unavailable',
      reason: 'Sin contrato de alertas en tiempo real',
      retryable: false,
    },
    decisions: {
      kind: 'unavailable',
      reason: 'Modo consultivo sin endpoint de mutación',
      retryable: false,
    },
  };

  it('renders metric cards with real data for available endpoints', () => {
    render(
      <CeoDashboard
        overview={fullOverview}
        projects={mockProjects}
        selectedProjectId="proj-1"
        onSelectProject={() => {}}
        onNavigateTo={() => {}}
      />
    );

    // Projects metric
    expect(screen.getAllByText('Cartera de Proyectos')[0]).toBeInTheDocument();
    expect(screen.getByText('2 activos/visibles')).toBeInTheDocument();

    // Tasks metric
    expect(screen.getByText('Total de Tareas')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();

    // In Review metric
    expect(screen.getByText('Tareas en Revisión')).toBeInTheDocument();
    const matchesForTwo = screen.getAllByText('2');
    expect(matchesForTwo.length).toBeGreaterThanOrEqual(1);
  });

  it('displays explicit unavailable notice instead of misleading 0 for missing contracts', () => {
    const unavailableOverview: CeoOverview = {
      ...fullOverview,
      work: {
        kind: 'unavailable',
        reason: 'Seleccione un proyecto específico para calcular la distribución real',
        retryable: false,
      },
    };

    render(
      <CeoDashboard
        overview={unavailableOverview}
        projects={mockProjects}
        selectedProjectId={null}
        onSelectProject={() => {}}
        onNavigateTo={() => {}}
      />
    );

    // Does NOT render "0" as tasks count
    const unavailableMessages = screen.getAllByText(
      'Seleccione un proyecto específico para calcular la distribución real'
    );
    expect(unavailableMessages.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  it('reports governance status honestly as uncertified without inventing approval', () => {
    render(
      <CeoDashboard
        overview={fullOverview}
        projects={mockProjects}
        selectedProjectId="proj-1"
        onSelectProject={() => {}}
        onNavigateTo={() => {}}
      />
    );

    expect(screen.getByText('Sin contrato API certificado')).toBeInTheDocument();
    expect(
      screen.getByText(/El backend no expone un servicio de certificación de auditoría independiente/i)
    ).toBeInTheDocument();
  });
});
