import { describe, it, expect, vi } from 'vitest';
import * as THREE from 'three';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { VirtualOfficeView } from '../features/office/VirtualOfficeView';
import { Office2DPlan } from '../features/office/components/Office2DPlan';
import { ThreeOfficeScene } from '../features/office/engine/ThreeOfficeScene';
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

  it('does not show the live capability catalogue in DEMO even when a read port is supplied', () => {
    render(<VirtualOfficeView organization={readyDemoState} conversationSessionId="demo-session"
      capabilityReadPort={{ getProjectCapabilities: vi.fn() }} />);

    expect(screen.queryByRole('heading', { name: 'Capacidades registradas' })).not.toBeInTheDocument();
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

describe('ThreeOfficeScene Engine Direct Regression Tests (Defects 1 & 2)', () => {
  const createMockRenderer = () =>
    ({
      setSize: vi.fn(),
      setPixelRatio: vi.fn(),
      render: vi.fn(),
      domElement: document.createElement('canvas'),
      shadowMap: { enabled: false, type: 0 },
      dispose: vi.fn(),
    } as unknown as THREE.WebGLRenderer);

  it('Defect 1: updateAgents() removes obsolete agent references from interactiveMeshes to prevent memory leaks and raycast accumulation', () => {
    const container = document.createElement('div');
    const scene = new ThreeOfficeScene(container, {
      renderer: createMockRenderer(),
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    // Initially, interactiveMeshes contains the 6 room platforms
    expect(scene.getInteractiveMeshesCount()).toBe(6);

    // First agent update with DEMO_AGENTS
    scene.updateAgents(DEMO_AGENTS);
    const countAfterFirstUpdate = scene.getInteractiveMeshesCount();
    expect(countAfterFirstUpdate).toBeGreaterThan(6);

    // Second agent update with DEMO_AGENTS (must NOT accumulate or leak old meshes)
    scene.updateAgents(DEMO_AGENTS);
    expect(scene.getInteractiveMeshesCount()).toBe(countAfterFirstUpdate);

    // Third agent update with empty array: should cleanly revert to exactly 6 room platforms
    scene.updateAgents([]);
    expect(scene.getInteractiveMeshesCount()).toBe(6);

    scene.dispose();
  });

  it('Defect 2: stepAnimation() strictly animates EPHEMERAL crystal agents and leaves STANDING agent geometry stationary', () => {
    const container = document.createElement('div');
    const scene = new ThreeOfficeScene(container, {
      renderer: createMockRenderer(),
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    scene.updateAgents(DEMO_AGENTS);

    // Identify a standing agent (e.g. Asistente de Presidencia / CEO Chair)
    const standingAgent = DEMO_AGENTS.find((a) => a.type === 'STANDING');
    expect(standingAgent).toBeDefined();

    // Identify an ephemeral agent (e.g. Sincronizador de Documentación / Doc Bot)
    const ephemeralAgent = DEMO_AGENTS.find((a) => a.type === 'EPHEMERAL');
    expect(ephemeralAgent).toBeDefined();

    const standingGroup = scene.getAgentMeshGroup(standingAgent!.id);
    const ephemeralGroup = scene.getAgentMeshGroup(ephemeralAgent!.id);
    expect(standingGroup).toBeDefined();
    expect(ephemeralGroup).toBeDefined();

    // Initial positions of children[1]:
    // Standing: pedestal at y = 0.06, rotation.y = 0
    expect(standingGroup!.children[1].position.y).toBeCloseTo(0.06);
    expect(standingGroup!.children[1].rotation.y).toBe(0);

    // Ephemeral: floating crystal initial y = 0.58
    expect(ephemeralGroup!.children[1].position.y).toBeCloseTo(0.58);
    expect(ephemeralGroup!.children[1].rotation.y).toBe(0);

    // Execute animation step at t = 1000ms
    scene.stepAnimation(1000);

    // STANDING agent geometry must remain strictly unchanged
    expect(standingGroup!.children[1].position.y).toBeCloseTo(0.06);
    expect(standingGroup!.children[1].rotation.y).toBe(0);

    // EPHEMERAL agent crystal geometry MUST have rotated and bobbed
    expect(ephemeralGroup!.children[1].rotation.y).toBeCloseTo(1000 * 0.002 * 0.5);
    expect(ephemeralGroup!.children[1].position.y).not.toBe(0.58);

    scene.dispose();
  });

  it('F4.7: smart zoom smoothly focuses onto selected department (14.5) and resetCamera() restores overview (24)', () => {
    const container = document.createElement('div');
    const scene = new ThreeOfficeScene(container, {
      renderer: createMockRenderer(),
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    // Default overview state
    expect(scene.getDesiredDistance()).toBe(24);
    expect(scene.getDesiredTarget().x).toBe(0);
    expect(scene.getDesiredTarget().z).toBe(0);

    // Select EXEC room -> camera focuses at distance 14.5 on EXEC coords (-6, -4)
    scene.selectRoom('unit-exec');
    expect(scene.getDesiredDistance()).toBe(14.5);
    expect(scene.getDesiredTarget().x).toBe(-6);
    expect(scene.getDesiredTarget().z).toBe(-4);

    // Reset camera -> camera returns to overview at distance 24
    scene.resetCamera();
    expect(scene.getDesiredDistance()).toBe(24);
    expect(scene.getDesiredTarget().x).toBe(0);
    expect(scene.getDesiredTarget().z).toBe(0);

    // Zoom clamping boundaries: minDistance 8, maxDistance 38
    scene.zoomCamera(0.1); // extreme zoom-in
    expect(scene.getDesiredDistance()).toBeGreaterThanOrEqual(8);

    scene.zoomCamera(10.0); // extreme zoom-out
    expect(scene.getDesiredDistance()).toBeLessThanOrEqual(38);

    scene.dispose();
  });

  it('cleans up DOM canvas elements on dispose and cleans container on instantiation, preventing double-mount canvas accumulation', () => {
    const container = document.createElement('div');
    const mockRenderer1 = createMockRenderer();
    const scene1 = new ThreeOfficeScene(container, {
      renderer: mockRenderer1,
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    expect(container.querySelectorAll('canvas').length).toBe(1);

    // Simulate React StrictMode unmount: dispose removes the canvas from container
    scene1.dispose();
    expect(container.querySelectorAll('canvas').length).toBe(0);

    // Simulate React StrictMode second mount: exactly one canvas is appended
    const mockRenderer2 = createMockRenderer();
    const scene2 = new ThreeOfficeScene(container, {
      renderer: mockRenderer2,
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    expect(container.querySelectorAll('canvas').length).toBe(1);
    expect(container.firstChild).toBe(mockRenderer2.domElement);
    scene2.dispose();
    expect(container.querySelectorAll('canvas').length).toBe(0);

    // If an orphan element is present in the container prior to instantiation, constructor cleans it
    const orphanCanvas = document.createElement('canvas');
    container.appendChild(orphanCanvas);
    expect(container.querySelectorAll('canvas').length).toBe(1);

    const mockRenderer3 = createMockRenderer();
    const scene3 = new ThreeOfficeScene(container, {
      renderer: mockRenderer3,
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });
    expect(container.querySelectorAll('canvas').length).toBe(1);
    expect(container.firstChild).toBe(mockRenderer3.domElement);
    scene3.dispose();
    expect(container.querySelectorAll('canvas').length).toBe(0);
  });

  it('F4.7: agent stress distribution scales cleanly up to 100 agents without errors or leaking meshes', () => {
    const container = document.createElement('div');
    const scene = new ThreeOfficeScene(container, {
      renderer: createMockRenderer(),
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    const units = ['unit-exec', 'unit-gov', 'unit-audit', 'unit-arch', 'unit-eng', 'unit-ops'];

    // Generate 50 synthetic agents
    const agents50 = Array.from({ length: 50 }, (_, i) => ({
      id: `stress-agent-${i}`,
      name: `Stress Agent ${i}`,
      type: (i % 2 === 0 ? 'STANDING' : 'EPHEMERAL') as 'STANDING' | 'EPHEMERAL',
      roleTitle: `Role ${i}`,
      unitId: units[i % units.length],
      capabilities: [],
      heartbeatStatus: 'HEALTHY' as const,
      lastHeartbeatAt: new Date().toISOString(),
      status: 'IDLE' as const,
      currentAssignments: [],
      authorityBoundary: 'Stress test boundary',
    }));

    scene.updateAgents(agents50);
    // Meshes cleanly added for 50 agents
    const count50 = scene.getInteractiveMeshesCount();
    expect(count50).toBeGreaterThan(50);

    // Scale up to 100 agents
    const agents100 = Array.from({ length: 100 }, (_, i) => ({
      id: `stress-agent-${i}`,
      name: `Stress Agent ${i}`,
      type: (i % 2 === 0 ? 'STANDING' : 'EPHEMERAL') as 'STANDING' | 'EPHEMERAL',
      roleTitle: `Role ${i}`,
      unitId: units[i % units.length],
      capabilities: [],
      heartbeatStatus: 'HEALTHY' as const,
      lastHeartbeatAt: new Date().toISOString(),
      status: 'IDLE' as const,
      currentAssignments: [],
      authorityBoundary: 'Stress test boundary',
    }));

    scene.updateAgents(agents100);
    const count100 = scene.getInteractiveMeshesCount();
    expect(count100).toBeGreaterThan(count50);

    // Calling updateAgents again with same 100 agents must not accumulate or leak
    scene.updateAgents(agents100);
    expect(scene.getInteractiveMeshesCount()).toBe(count100);

    // Clean reset to 0 agents restores exactly 6 room platforms
    scene.updateAgents([]);
    expect(scene.getInteractiveMeshesCount()).toBe(6);

    scene.dispose();
  });
});

describe('Phase F4.7: UI Contrast, Design Tokens & Operational Indicators', () => {
  it('renders live organizational units from the API and keeps the fixed 3D template demo-only', () => {
    const liveUnit = {
      ...DEMO_ORG_UNITS[0],
      id: 'unit-live-custom',
      code: 'CUSTOM',
      name: 'Unidad dinámica live',
      description: 'Unidad persistida recibida del backend.',
      leadRole: 'Responsable persistido',
      leadAgentId: null,
      standingCount: 0,
      ephemeralCount: 0,
      activeProjectsCount: 0,
    };
    const liveState: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      data: {
        units: [liveUnit],
        agents: [],
        totalStandingAgents: 0,
        totalEphemeralAgents: 0,
        activeAssignmentsCount: 0,
      },
      fetchedAt: new Date().toISOString(),
    };

    render(<VirtualOfficeView organization={liveState} />);

    expect(screen.getByRole('button', { name: '[CUSTOM] Unidad dinámica live' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: 'Unidad dinámica live' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /\[GOV\]/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Vista 3D \(WebGL\)/i })).toBeDisabled();
  });

  it('renders "Vista General" reset button and triggers camera reset callback', () => {
    const readyDemoState: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'demo',
      data: DEMO_ORG_STRUCTURE,
      fetchedAt: new Date().toISOString(),
    };

    render(<VirtualOfficeView organization={readyDemoState} />);

    const resetBtn = screen.getByRole('button', { name: /Restablecer posición de cámara y centrar oficina|Vista General/i });
    expect(resetBtn).toBeInTheDocument();
    fireEvent.click(resetBtn);
  });

  it('renders operational indicators row and distinguishes execution from presence', () => {
    const stateWithExecutingAgent: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      data: {
        units: DEMO_ORG_UNITS,
        agents: [
          {
            id: 'agent-executing-1',
            name: 'Codex Real Worker',
            type: 'STANDING',
            roleTitle: 'Desarrollador de Núcleo',
            unitId: 'unit-eng',
            capabilities: [],
            heartbeatStatus: 'UNKNOWN', // No fake heartbeat
            lastHeartbeatAt: null,
            status: 'BUSY',
            operationalState: 'EJECUTANDO',
            currentAssignments: [
              {
                id: 'asg-1',
                projectId: 'p1',
                projectName: 'Project 1',
                taskId: 't1',
                taskTitle: 'Build Security Core',
                assignedAt: '2026-10-25T12:00:00Z',
                status: 'ACTIVE',
              },
            ],
            authorityBoundary: 'Limitado a backend.',
            lastEvidenceAt: '2026-10-25T12:00:00Z',
            evidenceDescription: 'Ejecución registrada en tarea t1.',
          },
        ],
        totalStandingAgents: 1,
        totalEphemeralAgents: 0,
        activeAssignmentsCount: 1,
      },
      fetchedAt: new Date().toISOString(),
    };

    const onNavigate = vi.fn();
    render(<VirtualOfficeView organization={stateWithExecutingAgent} onNavigate={onNavigate} />);

    // Select ENG department
    const engBtn = screen.getByRole('button', { name: /\[ENG\] Ingeniería/i });
    fireEvent.click(engBtn);

    // Department summary counters in sidebar
    expect(screen.getByText('Registrados')).toBeInTheDocument();
    expect(screen.getByText('Conectados')).toBeInTheDocument();
    expect(screen.getByText('Ejecutando')).toBeInTheDocument();

    // Select the worker
    const workerBtn = screen.getAllByRole('button', { name: /Codex Real Worker/i })[0];
    fireEvent.click(workerBtn);

    // Verify presence vs execution badges
    expect(screen.getByText(/○ Telemetría Desconocida/i)).toBeInTheDocument();
    expect(screen.getByText(/⚡ Ejecutando Tarea/i)).toBeInTheDocument();
    expect(screen.getByText(/Build Security Core/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir tablero de este proyecto' }));
    expect(onNavigate).toHaveBeenCalledWith('kanban', 'p1');
  });

  it('renders unknown department and unknown agent type truthfully without fabricating affiliations', () => {
    const stateWithUnassignedAgent: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      data: {
        units: DEMO_ORG_UNITS,
        agents: [
          {
            id: 'worker-unknown-dept',
            name: 'Anonymous Worker',
            type: 'UNKNOWN',
            roleTitle: 'Agente Operativo Registrado',
            unitId: 'unit-unassigned',
            capabilities: [],
            heartbeatStatus: 'UNKNOWN',
            lastHeartbeatAt: null,
            status: 'IDLE',
            operationalState: 'REGISTRADO',
            currentAssignments: [
              {
                id: 'asg-old-1',
                projectId: 'p1',
                projectName: 'Legacy Project',
                taskId: 't9',
                taskTitle: 'Historical Task',
                assignedAt: '2026-10-20T10:00:00Z',
                status: 'COMPLETED', // Historical assignment
              },
            ],
            authorityBoundary: 'Sin concesión activa.',
            lastEvidenceAt: '2026-10-20T10:00:00Z',
            evidenceDescription: 'Tarea histórica completada en registro.',
          },
        ],
        totalStandingAgents: 0,
        totalEphemeralAgents: 0,
        totalUnknownAgents: 1,
        activeAssignmentsCount: 0,
      },
      fetchedAt: new Date().toISOString(),
    };

    render(<VirtualOfficeView organization={stateWithUnassignedAgent} />);

    // Switch to 2D Plan
    const toolbar = screen.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
    const plan2dBtn = within(toolbar).getByRole('button', { name: /Plano 2D Accesible/i });
    fireEvent.click(plan2dBtn);

    // Verify "Departamento desconocido" card appears
    expect(screen.getByRole('heading', { level: 4, name: /«Departamento desconocido»/i })).toBeInTheDocument();

    // Select the unknown agent button
    const agentBtn = screen.getByRole('button', { name: /Anonymous Worker/i });
    fireEvent.click(agentBtn);

    // Verify Inspector displays truth: "Tipo Desconocido", "«Departamento desconocido»", and historical assignment
    expect(screen.getByText('Tipo Desconocido')).toBeInTheDocument();
    expect(screen.getAllByText('«Departamento desconocido»').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Sin adscripción departamental canónica confirmada en el núcleo.')).toBeInTheDocument();
    expect(screen.getByText(/HISTÓRICO REGISTRADO/i)).toBeInTheDocument();
    expect(screen.getByText(/Sin capacidades certificadas/i)).toBeInTheDocument();
  });

  it('truthfully displays unknown execution vigency and project grants in inspector', () => {
    const stateWithVigencyUnknown: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      data: {
        units: DEMO_ORG_UNITS,
        agents: [
          {
            id: 'worker-lease-unknown',
            name: 'Unverified Vigency Worker',
            type: 'UNKNOWN',
            roleTitle: 'Agente Operativo Registrado',
            unitId: 'unit-unassigned',
            capabilities: [],
            grants: [
              {
                projectId: 'proj-sec',
                permission: 'project.read',
                active: true,
                expiresAt: '2026-10-26T00:00:00Z',
              },
            ],
            heartbeatStatus: 'UNKNOWN',
            lastHeartbeatAt: null,
            status: 'UNKNOWN',
            operationalState: 'DESCONOCIDO',
            currentAssignments: [
              {
                id: 'asg-unknown-vigency',
                projectId: 'proj-sec',
                projectName: 'Security Vault',
                taskId: 'task-sec-1',
                taskTitle: 'Audit cryptographic key store',
                assignedAt: '2026-10-25T18:00:00Z',
                leaseExpiresAt: null,
                status: 'UNKNOWN',
              },
            ],
            authorityBoundary: 'Delimitado por el mandato del proyecto Security Vault.',
            lastEvidenceAt: '2026-10-25T18:00:00Z',
            evidenceDescription: 'Registro de ejecución con vigencia desconocida (sin lease acreditado).',
          },
        ],
        totalStandingAgents: 0,
        totalEphemeralAgents: 0,
        totalUnknownAgents: 1,
        activeAssignmentsCount: 0,
      },
      fetchedAt: new Date().toISOString(),
    };

    render(<VirtualOfficeView organization={stateWithVigencyUnknown} />);

    // Switch to 2D Plan
    const toolbar = screen.getByRole('toolbar', { name: /Barra de herramientas de la Oficina Virtual/i });
    const plan2dBtn = within(toolbar).getByRole('button', { name: /Plano 2D Accesible/i });
    fireEvent.click(plan2dBtn);

    // Click on the agent button
    const agentBtn = screen.getByRole('button', { name: /Unverified Vigency Worker/i });
    fireEvent.click(agentBtn);

    // Verify Inspector displays Vigencia Desconocida and Grants
    expect(screen.getByText(/⚠️ Vigencia Desconocida \(Sin lease acreditado\)/i)).toBeInTheDocument();
    expect(screen.getByText(/VIGENCIA DESCONOCIDA \(SIN LEASE\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Concesiones y Permisos de Proyecto/i)).toBeInTheDocument();
    expect(screen.getByText(/project\.read/i)).toBeInTheDocument();
  });
});
