import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { OrganizationView } from '../features/organization/OrganizationView';
import { AgentDetailDrawer } from '../features/organization/AgentDetailDrawer';
import type { DataState, OrganizationStructure, AgentIdentity } from '../domain/models';
import { DEMO_ORG_STRUCTURE, DEMO_AGENTS } from '../data/adapters/demo/fixtures';

describe('Phase F3: OrganizationView and Agent Structure', () => {
  const readyState: DataState<OrganizationStructure> = {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_ORG_STRUCTURE,
    fetchedAt: new Date().toISOString(),
  };

  const unavailableState: DataState<OrganizationStructure> = {
    kind: 'unavailable',
    reason:
      'El núcleo canónico de AAO no expone aún endpoints públicos para la estructura organizativa ni la telemetría de agentes (F3).',
    retryable: false,
  };

  it('renders unavailable state with honest technical disclaimer when backend API is absent', () => {
    render(<OrganizationView orgState={unavailableState} />);

    expect(screen.getByText(/Organización y Estructura de Agentes/i)).toBeInTheDocument();
    expect(
      screen.getByText(/El núcleo canónico de AAO no expone aún endpoints públicos/i)
    ).toBeInTheDocument();
  });

  it('does not infer availability from an empty assignment list', () => {
    const unknownAgent: AgentIdentity = {
      ...DEMO_AGENTS[0],
      id: 'unknown-agent',
      name: 'Agente sin actividad observada',
      status: 'UNKNOWN',
      heartbeatStatus: 'UNKNOWN',
      currentAssignments: [],
    };
    const liveState: DataState<OrganizationStructure> = {
      kind: 'ready', origin: 'live', fetchedAt: new Date().toISOString(),
      data: { ...DEMO_ORG_STRUCTURE, agents: [unknownAgent] },
    };

    const { rerender } = render(<OrganizationView orgState={liveState} />);
    fireEvent.click(screen.getByRole('tab', { name: /Plantilla y Agentes/i }));
    expect(screen.getByText(/Sin asignación activa observada · estado UNKNOWN/i)).toBeInTheDocument();
    expect(screen.queryByText('Sin asignación activa (Disponible)')).not.toBeInTheDocument();

    rerender(<AgentDetailDrawer agent={unknownAgent} onClose={() => {}} />);
    expect(screen.getByText(/Esto no confirma disponibilidad; estado: UNKNOWN; latido: UNKNOWN/i)).toBeInTheDocument();
    expect(screen.queryByText(/IDLE/)).not.toBeInTheDocument();
  });

  it('renders all metrics and organizational units in ready state', () => {
    render(<OrganizationView orgState={readyState} />);

    // Metric cards
    expect(screen.getByText('Unidades Organizativas')).toBeInTheDocument();
    expect(screen.getByText('Plantilla Fija (Standing)')).toBeInTheDocument();
    expect(screen.getByText('Agentes Efímeros (Temporales)')).toBeInTheDocument();
    expect(screen.getByText('Asignaciones Activas')).toBeInTheDocument();
    expect(screen.getByText('Telemetría Verificada')).toBeInTheDocument();

    // Organigram tab rendered by default
    expect(screen.getByText(/Dirección Ejecutiva y Secretaría General/i)).toBeInTheDocument();
    expect(screen.getByText(/Gobernanza Constitucional y Políticas/i)).toBeInTheDocument();
    expect(screen.getByText(/Arquitectura de Sistemas y Protocolos/i)).toBeInTheDocument();
  });

  it('shows organization persistence controls only when enabled for the CEO view', () => {
    const saveUnit = vi.fn().mockResolvedValue({ kind: 'ready', origin: 'live', data: {}, fetchedAt: 'now' });
    const saveProfile = vi.fn().mockResolvedValue({ kind: 'ready', origin: 'live', data: {}, fetchedAt: 'now' });
    const { rerender } = render(<OrganizationView orgState={readyState} />);
    expect(screen.queryByText('Gestión organizativa')).not.toBeInTheDocument();

    rerender(<OrganizationView orgState={readyState} canManageOrganization onSaveUnit={saveUnit} onSaveProfile={saveProfile} />);
    expect(screen.getByText(/no concede permisos ni cambia asignaciones/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardar unidad' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardar perfil' })).toBeInTheDocument();
    expect(document.querySelectorAll('.organization-management__form')).toHaveLength(2);
    expect(document.querySelector('.organization-management__forms')).toContainElement(
      screen.getByRole('button', { name: 'Guardar unidad' }).closest('form'),
    );
  });

  it('navigates to Plantilla y Agentes tab and segregates standing vs ephemeral agents', () => {
    render(<OrganizationView orgState={readyState} />);

    const agentsTab = screen.getByRole('tab', { name: /Plantilla y Agentes/i });
    fireEvent.click(agentsTab);

    expect(screen.getByLabelText(/Buscar agente o capacidad:/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tipo de Agente:/i)).toBeInTheDocument();

    // Standing agent should be visible
    expect(screen.getByText(/Especialista en Frontend y Accesibilidad \(Antigravity\)/i)).toBeInTheDocument();
    // Ephemeral agent should also be present
    expect(screen.getByText(/Worker de Parche W1 #104/i)).toBeInTheDocument();
  });

  it('filters agents by text search correctly', () => {
    render(<OrganizationView orgState={readyState} />);

    const agentsTab = screen.getByRole('tab', { name: /Plantilla y Agentes/i });
    fireEvent.click(agentsTab);

    const searchInput = screen.getByLabelText(/Buscar agente o capacidad:/i);
    fireEvent.change(searchInput, { target: { value: 'Claude' } });

    expect(screen.getByText(/Claude Core/i)).toBeInTheDocument();
    expect(screen.queryByText(/Antigravity/i)).not.toBeInTheDocument();
  });

  it('filters agents by agent type (STANDING vs EPHEMERAL)', () => {
    render(<OrganizationView orgState={readyState} />);

    const agentsTab = screen.getByRole('tab', { name: /Plantilla y Agentes/i });
    fireEvent.click(agentsTab);

    const typeSelect = screen.getByLabelText(/Tipo de Agente:/i);
    fireEvent.change(typeSelect, { target: { value: 'EPHEMERAL' } });

    // Ephemeral agents visible
    expect(screen.getByText(/Worker de Parche W1 #104/i)).toBeInTheDocument();
    // Standing agent excluded
    expect(screen.queryByText(/Lead Architect/i)).not.toBeInTheDocument();
  });

  it('displays honest heartbeat states without inventing presence for unavailable agents', () => {
    render(<OrganizationView orgState={readyState} />);

    const agentsTab = screen.getByRole('tab', { name: /Plantilla y Agentes/i });
    fireEvent.click(agentsTab);

    const heartbeatSelect = screen.getByLabelText(/Estado de Telemetría:/i);
    fireEvent.change(heartbeatSelect, { target: { value: 'UNAVAILABLE' } });

    expect(screen.getByText(/Escáner SAST de Vulnerabilidades/i)).toBeInTheDocument();
    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument();
  });

  it('opens AgentDetailDrawer, displays authority boundary and capabilities, and dismisses on Escape', () => {
    render(<OrganizationView orgState={readyState} />);

    const agentsTab = screen.getByRole('tab', { name: /Plantilla y Agentes/i });
    fireEvent.click(agentsTab);

    const detailButton = screen.getByRole('button', {
      name: /Ver ficha técnica de Especialista en Frontend y Accesibilidad \(Antigravity\)/i,
    });
    fireEvent.click(detailButton);

    // Drawer dialog
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText(/Límite Constitucional de Autoridad/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/Confinado estrictamente a frontend\/app\//i)).toBeInTheDocument();
    expect(within(dialog).getByText(/React 19, TypeScript estricto, Vite y SPA/i)).toBeInTheDocument();

    // Dismiss with Escape key
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('switches to Puestos y Capacidades matrix view and displays table rows', () => {
    render(<OrganizationView orgState={readyState} />);

    const matrixTab = screen.getByRole('tab', { name: /Puestos y Capacidades/i });
    fireEvent.click(matrixTab);

    expect(screen.getByText(/Matriz de Puestos y Capacidades:/i)).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getAllByRole('row').length).toBeGreaterThan(5);
  });
});

describe('AgentDetailDrawer Component Direct Test', () => {
  const agent: AgentIdentity = DEMO_AGENTS[0];

  it('renders agent details and calls onClose upon clicking close button', () => {
    const onClose = vi.fn();
    render(<AgentDetailDrawer agent={agent} onClose={onClose} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(agent.name)).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: /Cerrar ficha de agente/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('renders null when agent is null', () => {
    const { container } = render(<AgentDetailDrawer agent={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});
