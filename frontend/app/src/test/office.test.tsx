import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { VirtualOfficeView } from '../features/office/VirtualOfficeView';
import { Office2DPlan } from '../features/office/components/Office2DPlan';
import type { DataState, OrganizationStructure } from '../domain/models';
import { DEMO_ORG_STRUCTURE, DEMO_AGENTS, DEMO_ORG_UNITS } from '../data/adapters/demo/fixtures';

describe('Phase F4: VirtualOfficeView & 3D Office Experience', () => {
  const readyDemoState: DataState<OrganizationStructure> = {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_ORG_STRUCTURE,
    fetchedAt: new Date().toISOString(),
  };

  const unavailableLiveState: DataState<OrganizationStructure> = {
    kind: 'unavailable',
    reason:
      'El núcleo canónico de AAO no expone aún endpoints públicos para la estructura organizativa ni la telemetría de agentes (F3/F4).',
    retryable: false,
  };

  it('renders honest callout in LIVE when backend F4 endpoints are absent', () => {
    render(<VirtualOfficeView organization={unavailableLiveState} />);

    expect(screen.getByText(/Oficina Virtual 3D · AAO/i)).toBeInTheDocument();
    expect(
      screen.getByText(/SIN CONEXIÓN AL NÚCLEO EN LIVE \(F3\/F4\)/i)
    ).toBeInTheDocument();
  });

  it('renders DEMO simulation banner in demo mode with active 3D controls', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    expect(
      screen.getByText(/DEMO · SIMULACIÓN 3D ACTIVA · Todos los departamentos, agentes y asignaciones son sintéticos/i)
    ).toBeInTheDocument();

    const toolbar = screen.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });

    // Mode buttons in toolbar
    expect(within(toolbar).getByRole('button', { name: /Vista 3D \(WebGL\)/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /Plano 2D Accesible/i })).toBeInTheDocument();
  });

  it('toggles between 3D viewport and 2D accessible blueprint map', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    const toolbar = screen.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
    const plan2dBtn = within(toolbar).getByRole('button', { name: /Plano 2D Accesible/i });
    fireEvent.click(plan2dBtn);

    // 2D plan region is now active
    expect(screen.getByRole('region', { name: /Plano 2D accesible de la oficina de AAO/i })).toBeInTheDocument();

    // Switch back to 3D
    const view3dBtn = within(toolbar).getByRole('button', { name: /Vista 3D \(WebGL\)/i });
    fireEvent.click(view3dBtn);

    expect(screen.queryByRole('region', { name: /Plano 2D accesible de la oficina de AAO/i })).not.toBeInTheDocument();
  });

  it('selects department via department chips and updates sidebar context', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    // Click on [AUDIT] chip
    const auditBtn = screen.getByRole('button', { name: /\[AUDIT\] Auditoría/i });
    fireEvent.click(auditBtn);

    // Sidebar updates to show Auditoría Independiente
    expect(screen.getByRole('heading', { level: 3, name: /Auditoría Independiente/i })).toBeInTheDocument();
  });

  it('selects agent and displays complete contextual inspector with capabilities and authority boundary', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    // Find agent button in sidebar
    const agentBtn = screen.getByRole('button', { name: /Asistente de Presidencia/i });
    fireEvent.click(agentBtn);

    // Contextual inspector region appears
    const inspector = screen.getByRole('region', { name: /Ficha técnica de Asistente de Presidencia/i });
    expect(inspector).toBeInTheDocument();
    expect(screen.getByText(/Supervisión consultiva. No auto-aprueba mandatos/i)).toBeInTheDocument();
    expect(screen.getByText(/Recepción y emisión de mandatos ejecutivos/i)).toBeInTheDocument();

    // Close button dismisses inspector
    const closeBtn = screen.getByRole('button', { name: /Cerrar ficha de agente/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('region', { name: /Ficha técnica de Asistente de Presidencia/i })).not.toBeInTheDocument();
  });

  it('filters agents in the office using search input and type filter', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    // Search input
    const searchInput = screen.getByPlaceholderText(/Buscar agente o capacidad.../i);
    fireEvent.change(searchInput, { target: { value: 'Antigravity' } });

    // Switch to 2D plan to easily verify rendered agents across rooms
    const toolbar = screen.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
    const plan2dBtn = within(toolbar).getByRole('button', { name: /Plano 2D Accesible/i });
    fireEvent.click(plan2dBtn);

    expect(screen.getByText(/Especialista en Frontend y Accesibilidad \(Antigravity\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/Asistente de Presidencia/i)).not.toBeInTheDocument();

    // Filter by type
    const typeSelect = screen.getByLabelText(/Filtrar por tipo de agente/i);
    fireEvent.change(typeSelect, { target: { value: 'EPHEMERAL' } });

    // Antigravity is STANDING so it is filtered out
    expect(screen.queryByText(/Especialista en Frontend y Accesibilidad/i)).not.toBeInTheDocument();
  });

  it('triggers onNavigate shortcuts for cross-view integration', () => {
    const onNavigate = vi.fn();
    render(<VirtualOfficeView organization={readyDemoState} onNavigate={onNavigate} />);

    const orgShortcut = screen.getByRole('button', { name: /Ver Organigrama/i });
    fireEvent.click(orgShortcut);
    expect(onNavigate).toHaveBeenCalledWith('organization');

    const kanbanShortcut = screen.getByRole('button', { name: /Ver Tablero/i });
    fireEvent.click(kanbanShortcut);
    expect(onNavigate).toHaveBeenCalledWith('kanban');

    const projectsShortcut = screen.getByRole('button', { name: /Proyectos/i });
    fireEvent.click(projectsShortcut);
    expect(onNavigate).toHaveBeenCalledWith('projects');
  });

  it('toggles reduced motion accessibility mode', () => {
    render(<VirtualOfficeView organization={readyDemoState} />);

    const motionBtn = screen.getByRole('button', { name: /Animación Estándar|Movimiento Reducido/i });
    fireEvent.click(motionBtn);

    expect(screen.getByText(/Movimiento Reducido \(Activo\)/i)).toBeInTheDocument();
  });
});

describe('Office2DPlan Component Direct Test', () => {
  it('renders all 6 departments and handles room and agent selection', () => {
    const onSelectRoom = vi.fn();
    const onSelectAgent = vi.fn();

    render(
      <Office2DPlan
        units={DEMO_ORG_UNITS}
        agents={DEMO_AGENTS}
        selectedRoomId="unit-exec"
        selectedAgentId={null}
        onSelectRoom={onSelectRoom}
        onSelectAgent={onSelectAgent}
        isDemo={true}
      />
    );

    // 6 departments rendered as headings
    expect(screen.getByRole('heading', { level: 4, name: /Dirección Ejecutiva/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: /Gobernanza Constitucional/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: /Auditoría Independiente/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: /Arquitectura de Sistemas/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: /Ingeniería de Software/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: /Operaciones de Infraestructura/i })).toBeInTheDocument();

    // Select department
    const govBtn = screen.getByRole('button', { name: /Gobernanza Constitucional/i });
    fireEvent.click(govBtn);
    expect(onSelectRoom).toHaveBeenCalledWith('unit-gov');
  });
});
