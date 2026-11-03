import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VirtualOfficeView } from '../features/office/VirtualOfficeView';
import { ThreeOfficeScene } from '../features/office/engine/ThreeOfficeScene';
import {
  computeAdaptiveLabelStates,
  deriveLabelLodTier,
  planOfficeLifePlacements,
  projectAgentOperationalActivity,
  sampleWaypointRoute,
} from '../features/office/engine/officeLifeEngine';
import { buildCorporateCampusLayout } from '../features/office/liveOfficeLayout';
import { OFFICE_ROOMS } from '../features/office/types';
import {
  deriveAgentOperationalCategory,
  filterOperationalAgents,
  HUD_PREFS_STORAGE_KEY,
  loadPersistedHudPreferences,
} from '../features/office/useOfficeHudState';
import type {
  AgentIdentity,
  AlertSummary,
  DataState,
  DecisionSummary,
  OrganizationStructure,
  ProjectSummary,
} from '../domain/models';
import { DEMO_AGENTS, DEMO_ORG_UNITS } from '../data/adapters/demo/fixtures';

const liveProjects: DataState<ProjectSummary[]> = {
  kind: 'ready',
  origin: 'live',
  fetchedAt: '2026-11-03T11:00:00Z',
  data: [
    { id: 'proj-alpha', name: 'Proyecto Alpha', status: 'ACTIVE' },
    { id: 'proj-beta', name: 'Proyecto Beta', status: 'ACTIVE' },
  ],
};

const liveOrgWithAgents: DataState<OrganizationStructure> = {
  kind: 'ready',
  origin: 'live',
  fetchedAt: '2026-11-03T11:00:00Z',
  data: {
    units: DEMO_ORG_UNITS,
    agents: [
      {
        id: 'agent-active-1',
        name: 'Implementador Alpha',
        type: 'STANDING',
        roleTitle: 'Ingeniero Principal',
        unitId: 'unit-eng',
        capabilities: [{ id: 'cap-1', name: 'TypeScript', level: 'CERTIFIED', verified: true }],
        heartbeatStatus: 'HEALTHY',
        lastHeartbeatAt: '2026-11-03T11:00:00Z',
        status: 'BUSY',
        operationalState: 'EJECUTANDO',
        currentAssignments: [
          {
            id: 'asg-alpha',
            projectId: 'proj-beta',
            projectName: 'Proyecto Beta',
            taskId: 'work-beta-1',
            taskTitle: 'Implementar HUD 3D',
            assignedAt: '2026-11-03T10:50:00Z',
            status: 'ACTIVE',
          },
        ],
        authorityBoundary: 'Limitado a frontend.',
      },
      {
        id: 'agent-blocked-1',
        name: 'Worker Presupuesto Excedido',
        type: 'EPHEMERAL',
        roleTitle: 'Worker Efímero',
        unitId: 'unit-ops',
        capabilities: [],
        heartbeatStatus: 'UNKNOWN',
        lastHeartbeatAt: null,
        status: 'IDLE',
        operationalState: 'REGISTRADO',
        currentAssignments: [],
        executionHistory: [
          {
            id: 'exec-blocked',
            taskId: 'work-ops-9',
            taskTitle: 'Despliegue',
            projectId: 'proj-alpha',
            projectName: 'Proyecto Alpha',
            status: 'FAILED',
            attempts: 2,
            createdAt: '2026-11-03T10:00:00Z',
            isBudgetExceeded: true,
            alert: 'budget.exceed',
          },
        ],
        authorityBoundary: 'Sin concesión activa.',
      },
    ],
    totalStandingAgents: 1,
    totalEphemeralAgents: 1,
    activeAssignmentsCount: 1,
  },
};

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('Video Game Spatial HUD & 3D Office Prioritization', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('renders in HUD Video Game mode by default and switches cleanly to Classic mode and back', () => {
    renderWithQueryClient(<VirtualOfficeView organization={liveOrgWithAgents} projects={liveProjects} />);

    expect(screen.getByTestId('office-game-stage')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Minimapa radar táctico 2D/i })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Muelle táctico de departamentos y plantilla/i })).toBeInTheDocument();

    // Switch to Classic mode
    const modeBtn = screen.getByRole('button', { name: /HUD Videojuego/i });
    fireEvent.click(modeBtn);

    expect(screen.queryByTestId('office-game-stage')).not.toBeInTheDocument();
    const returnHudBtn = screen.getByRole('button', { name: /Cambiar a HUD Videojuego/i });
    expect(returnHudBtn).toBeInTheDocument();

    // Switch back to HUD mode
    fireEvent.click(returnHudBtn);
    expect(screen.getByTestId('office-game-stage')).toBeInTheDocument();
  });

  it('keeps revoked principals out of live roster and unknown counts while retaining a historical count', () => {
    const revoked: AgentIdentity = {
      ...DEMO_AGENTS[0],
      id: 'revoked-agent',
      name: 'Revoked Agent',
      credentialStatus: 'DISABLED',
      status: 'UNKNOWN',
      currentAssignments: [],
    };
    const organization: DataState<OrganizationStructure> = {
      ...liveOrgWithAgents,
      data: { ...liveOrgWithAgents.data, agents: [revoked] },
    };
    renderWithQueryClient(<VirtualOfficeView organization={organization} projects={liveProjects} />);

    expect(screen.queryByText('Revoked Agent')).not.toBeInTheDocument();
    expect(screen.queryByText(/Desconocidos:/)).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Resumen de estados operativos de agentes' })).toHaveTextContent('Históricos: 1');
  });

  it('synchronizes department selection across the 2D Radar Minimap, Roster Dock, and Tactical Inspector', () => {
    renderWithQueryClient(<VirtualOfficeView organization={liveOrgWithAgents} projects={liveProjects} />);

    const minimap = screen.getByRole('region', { name: /Minimapa radar táctico 2D/i });
    const opsRadarBtn = within(minimap).getByRole('button', { name: /Enfocar radar en sector OPS/i });
    fireEvent.click(opsRadarBtn);

    // Inspector updates to show Operaciones de Infraestructura
    const inspector = screen.getByRole('complementary', { name: /Panel contextual de departamento y agentes/i });
    expect(within(inspector).getByRole('heading', { level: 3, name: /Operaciones de Infraestructura/i })).toBeInTheDocument();
  });

  it('auto-syncs operational project context when selecting an agent in the office (Improvement #1)', () => {
    renderWithQueryClient(
      <VirtualOfficeView
        organization={liveOrgWithAgents}
        projects={liveProjects}
        canCreateWorkRequest
        onCreateWorkRequest={vi.fn()}
      />
    );

    // Select ENG department where Implementador Alpha works on proj-beta
    fireEvent.click(screen.getByRole('button', { name: /\[ENG\] Ingeniería/i }));

    // Select Implementador Alpha in the sidebar
    fireEvent.click(screen.getByRole('button', { name: /Implementador Alpha/i }));

    // Context badge in Roster and Bottom Tactical Deck reflects proj-beta and agent name
    expect(screen.getAllByText(/proj-beta/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/🎯 Implementador Alpha · Proyecto: proj-beta/i)).toBeInTheDocument();
  });

  it('preserves module state across tab switches and supports detaching a secondary window for real multitasking (Improvement #2)', async () => {
    const getActivity = vi.fn().mockResolvedValue({
      kind: 'ready',
      origin: 'live',
      fetchedAt: 'now',
      data: [],
    });
    const getCapabilities = vi.fn().mockResolvedValue({
      kind: 'ready',
      origin: 'live',
      fetchedAt: 'now',
      data: [],
    });

    renderWithQueryClient(
      <VirtualOfficeView
        organization={liveOrgWithAgents}
        projects={liveProjects}
        canCreateWorkRequest
        onCreateWorkRequest={vi.fn()}
        activityReadPort={{ getProjectActivity: getActivity }}
        capabilityReadPort={{ getProjectCapabilities: getCapabilities }}
        conversationSessionId="ceo-session-1"
      />
    );

    // Type a draft title in the Work Request panel (Misiones CEO tab)
    const requestInput = screen.getByLabelText('Solicitud') as HTMLInputElement;
    fireEvent.change(requestInput, { target: { value: 'Borrador de misión persistente en pestaña' } });
    expect(requestInput.value).toBe('Borrador de misión persistente en pestaña');

    // Switch to Telemetría tab
    const telemetryTab = screen.getByRole('tab', { name: /Telemetría/i });
    fireEvent.click(telemetryTab);
    expect(screen.getByRole('heading', { name: 'Actividad registrada' })).toBeInTheDocument();

    // Switch back to Misiones CEO tab -> draft input is still preserved!
    const missionsTab = screen.getByRole('tab', { name: /Misiones CEO/i });
    fireEvent.click(missionsTab);
    expect((screen.getByLabelText('Solicitud') as HTMLInputElement).value).toBe(
      'Borrador de misión persistente en pestaña'
    );

    // Detach Misiones CEO into a secondary window so two panels are visible simultaneously
    const detachBtn = screen.getByRole('button', { name: /Desacoplar Misiones CEO en ventana secundaria/i });
    fireEvent.click(detachBtn);

    const detachedWindow = screen.getByRole('region', { name: /Ventana secundaria desacoplada: Misiones CEO/i });
    expect(detachedWindow).toBeInTheDocument();
    expect(within(detachedWindow).getByLabelText('Solicitud')).toHaveValue('Borrador de misión persistente en pestaña');

    // Re-attach the secondary window
    const closeDetachedBtn = within(detachedWindow).getByRole('button', { name: /Cerrar ventana desacoplada/i });
    fireEvent.click(closeDetachedBtn);
    expect(screen.queryByRole('region', { name: /Ventana secundaria desacoplada/i })).not.toBeInTheDocument();
  });

  it('supports resizing, minimizing, maximizing, and reordering tabs in the Bottom Tactical Deck', () => {
    renderWithQueryClient(
      <VirtualOfficeView
        organization={liveOrgWithAgents}
        projects={liveProjects}
        canCreateWorkRequest
        onCreateWorkRequest={vi.fn()}
        activityReadPort={{ getProjectActivity: vi.fn().mockResolvedValue({ kind: 'ready', origin: 'live', fetchedAt: 'now', data: [] }) }}
        conversationSessionId="ceo-session-1"
      />
    );

    const deck = screen.getByRole('region', { name: /Consola táctica inferior/i });
    expect(deck).toHaveStyle({ height: '360px' });

    // Resize via accessible range slider
    const slider = screen.getByLabelText('Redimensionar altura de consola');
    fireEvent.change(slider, { target: { value: '480' } });
    expect(deck).toHaveStyle({ height: '480px' });

    // Minimize
    fireEvent.click(screen.getByRole('button', { name: /Minimizar consola táctica/i }));
    expect(deck).toHaveStyle({ height: '46px' });

    // Maximize
    fireEvent.click(screen.getByRole('button', { name: /Maximizar consola táctica/i }));
    expect(deck).toHaveStyle({ height: '76vh' });

    // Dock back to custom height (480px)
    fireEvent.click(screen.getByRole('button', { name: /Acoplar consola táctica/i }));
    expect(deck).toHaveStyle({ height: '480px' });

    // Reorder active tab to the right and check persistence
    fireEvent.click(screen.getByRole('button', { name: /Mover pestaña Misiones CEO a la derecha/i }));
    const savedPrefs = loadPersistedHudPreferences();
    expect(savedPrefs.panelOrder.indexOf('work-request')).toBeGreaterThan(0);
    expect(savedPrefs.bottomDeckHeightPx).toBe(480);
  });

  it('handles keyboard shortcuts safely without interfering with text inputs or buttons', () => {
    renderWithQueryClient(
      <VirtualOfficeView
        organization={liveOrgWithAgents}
        projects={liveProjects}
        canCreateWorkRequest
        onCreateWorkRequest={vi.fn()}
        onRefresh={vi.fn()}
      />
    );

    // Typing 'z' or Space inside the search input must NOT trigger Zen Mode
    const searchInput = screen.getByPlaceholderText(/Buscar agente o capacidad.../i);
    fireEvent.keyDown(searchInput, { key: 'z' });
    fireEvent.keyDown(searchInput, { key: ' ' });
    expect(screen.queryByRole('button', { name: /Salir de Modo Zen/i })).not.toBeInTheDocument();

    // Pressing Space on a focused button must NOT trigger Zen Mode
    const refreshBtn = screen.getByRole('button', { name: /Actualizar datos de la oficina/i });
    fireEvent.keyDown(refreshBtn, { key: ' ' });
    expect(screen.queryByRole('button', { name: /Salir de Modo Zen/i })).not.toBeInTheDocument();

    // Pressing 'z' on the document body toggles Zen Mode ON
    fireEvent.keyDown(document.body, { key: 'z' });
    expect(screen.getByRole('button', { name: /Salir de Modo Zen/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Consola táctica inferior/i })).not.toBeInTheDocument();

    // Pressing Escape exits Zen Mode
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: /Salir de Modo Zen/i })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Consola táctica inferior/i })).toBeInTheDocument();
  });

  it('keeps critical alerts, audit vetoes, and reserved CEO decisions accessible in Zen Mode (Improvement #3)', () => {
    const criticalAlertsState: DataState<AlertSummary[]> = {
      kind: 'ready',
      origin: 'live',
      fetchedAt: 'now',
      data: [
        {
          id: 'alert-crit-1',
          title: 'Veto de auditoría pendiente de resolución',
          severity: 'critical',
          source: 'governance-ledger',
          confidence: 'verified',
          timestamp: '2026-11-03T11:00:00Z',
          description: 'Marca de veto detectada.',
        },
      ],
    };

    const ceoDecisionsState: DataState<DecisionSummary[]> = {
      kind: 'ready',
      origin: 'live',
      fetchedAt: 'now',
      data: [
        {
          id: 'dec-ceo-1',
          title: 'Aprobación de presupuesto diario',
          category: 'ceo_pending',
          subjectId: 'proj-alpha',
          createdAt: '2026-11-03T11:00:00Z',
          description: 'Reservado al CEO.',
        },
      ],
    };

    const onNavigate = vi.fn();

    renderWithQueryClient(
      <VirtualOfficeView
        organization={liveOrgWithAgents}
        projects={liveProjects}
        alertsState={criticalAlertsState}
        decisionsState={ceoDecisionsState}
        onNavigate={onNavigate}
      />
    );

    // Enter Zen Mode
    fireEvent.keyDown(document.body, { key: 'z' });

    // Ordinary HUD is hidden, but critical governance alert beacon remains visible and interactive!
    const alertBeacon = screen.getByRole('alert');
    expect(alertBeacon).toBeInTheDocument();
    expect(within(alertBeacon).getByText(/Atención prioritaria requerida \(Modo Zen\)/i)).toBeInTheDocument();
    expect(within(alertBeacon).getByText(/1 alerta\(s\) crítica\(s\)/i)).toBeInTheDocument();
    expect(within(alertBeacon).getByText(/1 decisión\(es\) CEO\/Auditoría/i)).toBeInTheDocument();

    fireEvent.click(within(alertBeacon).getByRole('button', { name: 'Ver Alertas' }));
    expect(onNavigate).toHaveBeenCalledWith('alerts');

    fireEvent.click(within(alertBeacon).getByRole('button', { name: 'Ver Decisiones' }));
    expect(onNavigate).toHaveBeenCalledWith('decisions');
  });

  it('classifies operational states truthfully without inventing activity and recovers from corrupted localStorage', () => {
    window.localStorage.setItem(HUD_PREFS_STORAGE_KEY, '{corrupted-json');
    const recovered = loadPersistedHudPreferences();
    expect(recovered.layoutMode).toBe('hud');
    expect(recovered.bottomDeckState).toBe('docked');

    expect(deriveAgentOperationalCategory(liveOrgWithAgents.data.agents[0]).category).toBe('ACTIVO');
    expect(deriveAgentOperationalCategory(liveOrgWithAgents.data.agents[1]).category).toBe('BLOQUEADO');

    const revokedAgent: AgentIdentity = {
      ...DEMO_AGENTS[0],
      credentialStatus: 'DISABLED',
      status: 'UNKNOWN',
      currentAssignments: [],
    };
    expect(deriveAgentOperationalCategory(revokedAgent)).toMatchObject({
      category: 'HISTORICO',
      label: 'Histórico · credencial revocada',
    });
    expect(filterOperationalAgents([revokedAgent, liveOrgWithAgents.data.agents[0]])).toEqual([
      liveOrgWithAgents.data.agents[0],
    ]);

    const disconnectedAgent: AgentIdentity = {
      ...DEMO_AGENTS[0],
      status: 'OFFLINE',
      heartbeatStatus: 'UNAVAILABLE',
      currentAssignments: [],
    };
    expect(deriveAgentOperationalCategory(disconnectedAgent).category).toBe('DESCONECTADO');
  });

  it('supports 3D camera presets and synchronizes camera state callbacks for the Radar Minimap', () => {
    const container = document.createElement('div');
    const onCameraChange = vi.fn();
    const mockRenderer = {
      setSize: vi.fn(),
      setPixelRatio: vi.fn(),
      render: vi.fn(),
      domElement: document.createElement('canvas'),
      shadowMap: { enabled: false, type: 0 },
      dispose: vi.fn(),
    } as unknown as THREE.WebGLRenderer;

    const scene = new ThreeOfficeScene(container, {
      renderer: mockRenderer,
      reducedMotion: true,
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
        onCameraChange,
      },
    });

    scene.setCameraPreset('isometric');
    expect(scene.getCameraState().angle).toBe(45);
    expect(scene.getCameraState().distance).toBe(20);
    expect(onCameraChange).toHaveBeenCalledWith(expect.objectContaining({ angle: 45, distance: 20 }));

    scene.setCameraPreset('top-down');
    expect(scene.getCameraState().elevation).toBe(78);

    scene.setCameraPreset('overview');
    expect(scene.getCameraState().distance).toBe(24);

    scene.dispose();
  });

  it('keeps 3D WebGL active by default and auto-minimizes the bottom deck when unauthenticated in LIVE mode', () => {
    renderWithQueryClient(
      <VirtualOfficeView
        organization={{
          kind: 'unavailable',
          reason: 'Sin estructura persistida.',
          retryable: false,
        }}
        projects={{
          kind: 'unavailable',
          reason: 'Lista de proyectos no disponible.',
          retryable: true,
        }}
        activityReadPort={{ getProjectActivity: vi.fn() }}
        conversationSessionId="session-unauth"
      />
    );

    const view3DBtn = screen.getByRole('button', { name: /Vista 3D \(WebGL\)/i });
    expect(view3DBtn).toBeEnabled();
    expect(view3DBtn).toHaveAttribute('aria-pressed', 'true');

    // Bottom deck starts minimized (46px) so it does not cover the 3D scene before authentication
    const bottomDeck = screen.getByRole('region', { name: /Consola táctica inferior/i });
    expect(bottomDeck).toHaveStyle({ height: '46px' });
  });

  it('projects operational activity strictly from verifiable evidence, expiring leases, and explicit coordination in LIVE vs DEMO', () => {
    const nowMs = Date.parse('2026-11-03T12:00:00Z');

    // 1. Active work with valid lease -> TYPING_DEV / TYPING_AUDIT / TYPING_DOCS
    const activeAuditAgent: AgentIdentity = {
      ...DEMO_AGENTS[0],
      id: 'agent-audit-live-1',
      isSyntheticDemo: false,
      unitId: 'unit-audit',
      roleTitle: 'Auditor SAST',
      status: 'BUSY',
      operationalState: 'EJECUTANDO',
      heartbeatStatus: 'HEALTHY',
      currentAssignments: [
        {
          id: 'asg-audit-1',
          projectId: 'proj-alpha',
          projectName: 'Proyecto Alpha',
          taskId: 'work-audit-1',
          taskTitle: 'Auditoría de seguridad y verificación SAST',
          assignedAt: '2026-11-03T11:30:00Z',
          leaseExpiresAt: '2026-11-03T12:30:00Z',
          status: 'ACTIVE',
        },
      ],
    };

    const projectedActiveAudit = projectAgentOperationalActivity(
      activeAuditAgent,
      [activeAuditAgent],
      { isDemo: false, nowMs }
    );
    expect(projectedActiveAudit.kind).toBe('TYPING_AUDIT');
    expect(projectedActiveAudit.provenance).toBe('LIVE_VERIFIED_EVIDENCE');
    expect(projectedActiveAudit.isLeaseExpired).toBe(false);

    // 2. Expired lease -> immediately stops typing and transitions to UNKNOWN_NEUTRAL
    const expiredLeaseAgent: AgentIdentity = {
      ...activeAuditAgent,
      currentAssignments: [
        {
          ...activeAuditAgent.currentAssignments[0],
          leaseExpiresAt: '2026-11-03T11:55:00Z', // 5 minutes before nowMs
        },
      ],
    };

    const projectedExpired = projectAgentOperationalActivity(
      expiredLeaseAgent,
      [expiredLeaseAgent],
      { isDemo: false, nowMs }
    );
    expect(projectedExpired.kind).toBe('UNKNOWN_NEUTRAL');
    expect(projectedExpired.provenance).toBe('NEUTRAL_NO_EVIDENCE');
    expect(projectedExpired.isLeaseExpired).toBe(true);

    // 3. Belonging to unit-audit without active work must NOT attribute auditing
    const idleAuditAgent: AgentIdentity = {
      ...activeAuditAgent,
      status: 'IDLE',
      operationalState: 'REGISTRADO',
      currentAssignments: [],
    };
    const projectedIdleAudit = projectAgentOperationalActivity(
      idleAuditAgent,
      [idleAuditAgent],
      { isDemo: false, nowMs, ambientWalkEnabled: false }
    );
    expect(projectedIdleAudit.kind).toBe('IDLE_DESK');
    expect(projectedIdleAudit.provenance).toBe('LIVE_VERIFIED_EVIDENCE');

    // 4. Sharing a projectId in LIVE without explicit coordination evidence must NOT attribute CONVERSING
    const peerA: AgentIdentity = {
      ...activeAuditAgent,
      id: 'agent-peer-a',
      unitId: 'unit-eng',
      roleTitle: 'Ingeniero Backend',
      capabilities: [{ id: 'cap-ts', name: 'TypeScript', level: 'CERTIFIED', verified: true }],
      currentAssignments: [
        {
          id: 'asg-peer-a',
          projectId: 'proj-shared',
          projectName: 'Proyecto Compartido',
          taskId: 'task-a',
          taskTitle: 'Implementar API REST',
          assignedAt: '2026-11-03T11:30:00Z',
          status: 'ACTIVE',
        },
      ],
    };
    const peerB: AgentIdentity = {
      ...peerA,
      id: 'agent-peer-b',
      name: 'Ingeniera Beta',
      currentAssignments: [
        {
          id: 'asg-peer-b',
          projectId: 'proj-shared',
          projectName: 'Proyecto Compartido',
          taskId: 'task-b',
          taskTitle: 'Documentar arquitectura y normativa',
          assignedAt: '2026-11-03T11:30:00Z',
          status: 'ACTIVE',
        },
      ],
    };

    const livePeerAWithoutCoord = projectAgentOperationalActivity(
      peerA,
      [peerA, peerB],
      { isDemo: false, nowMs }
    );
    const livePeerBWithoutCoord = projectAgentOperationalActivity(
      peerB,
      [peerA, peerB],
      { isDemo: false, nowMs }
    );
    expect(livePeerAWithoutCoord.kind).toBe('TYPING_DEV');
    expect(livePeerBWithoutCoord.kind).toBe('TYPING_DOCS');

    // With explicit coordination evidence in LIVE, CONVERSING is attributed with LIVE_VERIFIED_EVIDENCE
    const livePeerAWithCoord = projectAgentOperationalActivity(
      peerA,
      [peerA, peerB],
      {
        isDemo: false,
        nowMs,
        activeCoordinationAgentIds: new Set(['agent-peer-a', 'agent-peer-b']),
      }
    );
    expect(livePeerAWithCoord.kind).toBe('CONVERSING');
    expect(livePeerAWithCoord.provenance).toBe('LIVE_VERIFIED_EVIDENCE');
    expect(livePeerAWithCoord.conversationPartnerId).toBe('agent-peer-b');
  });

  it('maintains stable workstation slots across LLM/session changes, avoids collisions, and computes deterministic corridor routes', () => {
    const nowMs = Date.parse('2026-11-03T12:00:00Z');
    const placements1 = planOfficeLifePlacements(DEMO_AGENTS, OFFICE_ROOMS, {
      isDemo: true,
      nowMs,
    });

    // Simulate LLM model/role/session rotation on the same agent IDs
    const rotatedAgents: AgentIdentity[] = DEMO_AGENTS.map((a) => ({
      ...a,
      roleTitle: `${a.roleTitle} (Claude-3.7-Sonnet Session #99)`,
      lastHeartbeatAt: '2026-11-03T12:05:00Z',
    }));

    const placements2 = planOfficeLifePlacements(rotatedAgents, OFFICE_ROOMS, {
      isDemo: true,
      nowMs,
    });

    for (const agent of DEMO_AGENTS) {
      const p1 = placements1.get(agent.id)!;
      const p2 = placements2.get(agent.id)!;
      expect(p1).toBeDefined();
      expect(p2).toBeDefined();
      // Same physical workstation slot index and coordinates regardless of session/LLM metadata
      expect(p1.workstationSlot.slotIndex).toBe(p2.workstationSlot.slotIndex);
      expect(p1.workstationSlot.chairWorldX).toBeCloseTo(p2.workstationSlot.chairWorldX, 5);
      expect(p1.workstationSlot.chairWorldZ).toBeCloseTo(p2.workstationSlot.chairWorldZ, 5);
    }

    // Verify zero collisions among seated agents in the same room
    const byRoomSlot = new Set<string>();
    for (const p of placements1.values()) {
      const key = `${p.unitId}#${p.workstationSlot.slotIndex}`;
      expect(byRoomSlot.has(key)).toBe(false);
      byRoomSlot.add(key);
    }

    // Verify smooth corridor waypoint route sampling
    const walkingAgent = Array.from(placements1.values()).find(
      (p) => p.waypoints && p.waypoints.length >= 2
    );
    expect(walkingAgent).toBeDefined();
    const sampleStart = sampleWaypointRoute(walkingAgent!.waypoints, 0, 0);
    const sampleMid = sampleWaypointRoute(walkingAgent!.waypoints, 2500, 0);
    expect(Number.isFinite(sampleStart.x)).toBe(true);
    expect(Number.isFinite(sampleMid.z)).toBe(true);
    expect(
      Math.hypot(sampleMid.x - sampleStart.x, sampleMid.z - sampleStart.z)
    ).toBeGreaterThan(0.1);
  });

  it('articulates 3D character rigs during typing/walking/conversing, interpolates transitions smoothly, and recovers from WebGL context loss', () => {
    const container = document.createElement('div');
    const canvas = document.createElement('canvas');
    const mockRenderer = {
      setSize: vi.fn(),
      setPixelRatio: vi.fn(),
      render: vi.fn(),
      domElement: canvas,
      shadowMap: { enabled: false, type: 0 },
      dispose: vi.fn(),
    } as unknown as THREE.WebGLRenderer;

    const scene = new ThreeOfficeScene(container, {
      renderer: mockRenderer,
      reducedMotion: false,
      demoFurniture: true,
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });

    scene.updateAgents(DEMO_AGENTS);

    // Semantic parts are exposed for every agent while keeping group.children[1] backward-compatible
    const engAgent = DEMO_AGENTS.find((a) => a.type === 'STANDING' && a.status === 'BUSY')!;
    const parts = scene.getAgentSemanticParts(engAgent.id);
    expect(parts).toBeDefined();
    expect(parts!.leftArm).toBeInstanceOf(THREE.Object3D);
    expect(parts!.rightArm).toBeInstanceOf(THREE.Object3D);
    expect(parts!.leftLeg).toBeInstanceOf(THREE.Object3D);
    expect(parts!.rightLeg).toBeInstanceOf(THREE.Object3D);

    const group = scene.getAgentMeshGroup(engAgent.id)!;
    // Standing pedestal at children[1] (and parts.primaryGeometry) stays stationary (Defect 2 compatibility)
    expect(group.children[1].position.y).toBeCloseTo(0.06, 5);
    expect(parts!.primaryGeometry.position.y).toBeCloseTo(0.06, 5);
    scene.stepAnimation(600);
    expect(group.children[1].position.y).toBeCloseTo(0.06, 5);
    expect(parts!.primaryGeometry.position.y).toBeCloseTo(0.06, 5);
    // Character rig arms articulate while typing (raised over keyboard around -0.82 ± 0.22 rad)
    expect(parts!.leftArm!.rotation.x).toBeLessThan(-0.5);
    expect(parts!.rightArm!.rotation.x).toBeLessThan(-0.5);

    // WebGL context lost and restored events are handled cleanly without throwing
    expect(scene.isContextLost()).toBe(false);
    const lostEvent = new Event('webglcontextlost', { cancelable: true });
    canvas.dispatchEvent(lostEvent);
    expect(scene.isContextLost()).toBe(true);

    const restoredEvent = new Event('webglcontextrestored');
    canvas.dispatchEvent(restoredEvent);
    expect(scene.isContextLost()).toBe(false);

    scene.dispose();
  });

  it('Phase 3 (Iteración 2): adapts 3D label LOD by camera distance and resolves screen-space overlaps for 7+ clustered agents', () => {
    expect(deriveLabelLodTier(24)).toBe('overview');
    expect(deriveLabelLodTier(14.5)).toBe('department');
    expect(deriveLabelLodTier(9.5)).toBe('agent');

    // Create 7 unassigned agents in the Holding Wing (`unit-unassigned`)
    const sevenUnassigned: AgentIdentity[] = Array.from({ length: 7 }, (_, i) => ({
      id: `aao-selfdev-worker-${i}`,
      name: `aao-selfdev-worker-${i}`,
      type: 'UNKNOWN',
      roleTitle: 'Principal observado en ejecución',
      unitId: 'unit-unassigned',
      capabilities: [],
      heartbeatStatus: 'UNKNOWN',
      lastHeartbeatAt: null,
      status: 'UNKNOWN',
      operationalState: 'DESCONOCIDO',
      credentialStatus: 'DISABLED',
      currentAssignments: [],
      authorityBoundary: 'Sin concesión activa.',
    }));

    const campus = buildCorporateCampusLayout(
      [
        {
          id: 'unit-unassigned',
          code: 'UNKNOWN',
          name: 'Adscripción desconocida',
          parentId: null,
          leadRole: 'Sin asignar / Desconocido',
          leadAgentId: null,
          description: '',
          standingCount: 0,
          ephemeralCount: 0,
          activeProjectsCount: 0,
        },
      ],
      sevenUnassigned,
      { isDemo: false }
    );

    const placements = planOfficeLifePlacements(sevenUnassigned, campus.rooms, {
      isDemo: false,
      nowMs: Date.parse('2026-11-03T12:00:00Z'),
    });

    // Verify all 7 agents in unit-unassigned get distinct workstation slots (zero chair collisions)
    const slotIndices = new Set(Array.from(placements.values()).map((p) => p.workstationSlot.slotIndex));
    expect(slotIndices.size).toBe(7);

    const placementMap = new Map(
      sevenUnassigned.map((agent) => {
        const p = placements.get(agent.id)!;
        return [
          agent.id,
          {
            // Simulate all 7 agents projecting to the same world/screen spot for worst-case overlap
            x: 0,
            z: 5.6,
            activity: p.activity,
          },
        ] as const;
      })
    );

    // 1. In OVERVIEW mode (distance 24) with agent 0 selected: only selected agent label is visible
    const overviewLabels = computeAdaptiveLabelStates({
      rooms: campus.rooms,
      agents: sevenUnassigned,
      placements: placementMap,
      cameraDistance: 24,
      cameraAngleDeg: 35,
      cameraTargetX: 0,
      cameraTargetZ: 0,
      selectedRoomId: 'unit-unassigned',
      selectedAgentId: 'aao-selfdev-worker-0',
    });
    expect(overviewLabels.lodTier).toBe('overview');
    expect(overviewLabels.departments.get('unit-unassigned')?.visible).toBe(true);
    expect(overviewLabels.agents.get('aao-selfdev-worker-0')?.visible).toBe(true);
    expect(overviewLabels.agents.get('aao-selfdev-worker-1')?.visible).toBe(false);

    // 2. In AGENT mode (distance 9.5) with identical world coords: de-overlapping nudges yOffset and suppresses excess
    const closeLabels = computeAdaptiveLabelStates({
      rooms: campus.rooms,
      agents: sevenUnassigned,
      placements: placementMap,
      cameraDistance: 9.5,
      cameraAngleDeg: 35,
      cameraTargetX: 0,
      cameraTargetZ: 5.6,
      selectedRoomId: 'unit-unassigned',
      selectedAgentId: 'aao-selfdev-worker-0',
    });
    expect(closeLabels.lodTier).toBe('agent');
    const states = Array.from(closeLabels.agents.values());
    const visibleStates = states.filter((s) => s.visible);
    const suppressedStates = states.filter((s) => s.suppressedByOverlap);
    // At exact screen-space collision, 3 vertical offset tiers fit (1.24, 1.62, 1.98) and the rest are suppressed
    expect(visibleStates.length).toBe(3);
    expect(suppressedStates.length).toBe(4);
    const uniqueYOffsets = new Set(visibleStates.map((s) => s.yOffset));
    expect(uniqueYOffsets.size).toBe(3);
  });

  it('Phase 1 & 4 (Iteración 2): displays LIVE organizational attribution diagnostics, opens Organization shortcut, and compacts HUD toolbar', () => {
    const liveUnassignedState: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      fetchedAt: '2026-11-03T12:00:00Z',
      data: {
        units: [
          {
            id: 'unit-unassigned',
            code: 'UNKNOWN',
            name: 'Adscripción desconocida',
            parentId: null,
            leadRole: 'Sin asignar / Desconocido',
            leadAgentId: null,
            description: 'Agentes observados sin unidad organizativa.',
            standingCount: 0,
            ephemeralCount: 0,
            activeProjectsCount: 0,
          },
        ],
        agents: [
          {
            id: 'aao-selfdev-d60cd366b26d',
            name: 'aao-selfdev-d60cd366b26d',
            type: 'UNKNOWN',
            roleTitle: 'Principal observado en ejecución',
            unitId: 'unit-unassigned',
            capabilities: [],
            heartbeatStatus: 'UNKNOWN',
            lastHeartbeatAt: null,
            status: 'UNKNOWN',
            operationalState: 'DESCONOCIDO',
            credentialStatus: 'ENABLED',
            currentAssignments: [],
            authorityBoundary: 'Sin concesión activa.',
            evidenceDescription: 'Identidad derivada de ejecuciones persistidas.',
          },
        ],
        totalStandingAgents: 0,
        totalEphemeralAgents: 0,
        totalUnknownAgents: 1,
        activeAssignmentsCount: 0,
      },
    };

    const onNavigate = vi.fn();
    renderWithQueryClient(
      <VirtualOfficeView organization={liveUnassignedState} projects={liveProjects} onNavigate={onNavigate} />
    );

    // Diagnostic pill is visible in the compact top ribbon
    const diagPillBtn = screen.getByRole('button', { name: /0 unidades declaradas · 1 sin adscripción/i });
    expect(diagPillBtn).toBeInTheDocument();

    // Open diagnostic popover and click "Declarar unidades en Organización"
    fireEvent.click(diagPillBtn);
    const diagRegion = screen.getByRole('region', { name: /Diagnóstico de adscripción organizativa en LIVE/i });
    expect(diagRegion).toBeInTheDocument();

    const declareBtn = within(diagRegion).getByRole('button', { name: /Declarar unidades en Organización/i });
    fireEvent.click(declareBtn);
    expect(onNavigate).toHaveBeenCalledWith('organization');

    // Toggle secondary toolbar collapse and verify persistence
    const controlsToggleBtn = screen.getByRole('button', { name: /Controles/i });
    fireEvent.click(controlsToggleBtn);
    expect(loadPersistedHudPreferences().isToolbarCollapsed).toBe(true);
    fireEvent.click(controlsToggleBtn);
    expect(loadPersistedHudPreferences().isToolbarCollapsed).toBe(false);
  });

  it('Phase 5 & 6 (Iteración 2): supports dynamic campus framing, agent follow mode, camera panning, quality profiles, and records performance benchmarks across empty, small, and dense scenarios', () => {
    const container = document.createElement('div');
    const mockRenderer = {
      setSize: vi.fn(),
      setPixelRatio: vi.fn(),
      render: vi.fn(),
      domElement: document.createElement('canvas'),
      shadowMap: { enabled: false, type: 0 },
      dispose: vi.fn(),
    } as unknown as THREE.WebGLRenderer;

    // 1. Empty scenario (0 agents, 6 rooms)
    const scene = new ThreeOfficeScene(container, {
      renderer: mockRenderer,
      reducedMotion: false,
      qualityProfile: 'balanced',
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });
    scene.updateAgents([]);
    scene.stepAnimation(100);
    const emptyPerf = scene.getPerformanceMetrics();
    expect(emptyPerf.agentsCount).toBe(0);
    expect(emptyPerf.roomsCount).toBe(6);
    expect(emptyPerf.qualityProfile).toBe('balanced');
    expect(emptyPerf.lastFrameTimeMs).toBeLessThan(50);

    // 2. Small scenario (8 DEMO agents, 6 rooms) + Agent Follow & Panning
    scene.updateAgents(DEMO_AGENTS);
    scene.stepAnimation(200);
    const smallPerf = scene.getPerformanceMetrics();
    expect(smallPerf.agentsCount).toBe(DEMO_AGENTS.length);
    expect(smallPerf.interactiveMeshesCount).toBeGreaterThan(6);
    expect(smallPerf.lastFrameTimeMs).toBeLessThan(50);

    // Select an agent and enable follow mode
    const targetAgent = DEMO_AGENTS[0];
    scene.selectAgent(targetAgent.id);
    scene.setFollowAgent(true);
    expect(scene.isFollowingAgent()).toBe(true);
    scene.stepAnimation(400);

    // Manual camera pan cancels follow mode and shifts target coordinates
    const prevTarget = scene.getDesiredTarget();
    scene.panCamera(2.0, -1.5);
    expect(scene.isFollowingAgent()).toBe(false);
    expect(scene.getDesiredTarget().x).not.toBeCloseTo(prevTarget.x, 3);

    // Switch quality profiles (low -> high -> balanced)
    scene.setQualityProfile('low');
    expect(scene.getQualityProfile()).toBe('low');
    expect(mockRenderer.shadowMap.enabled).toBe(false);

    scene.setQualityProfile('high');
    expect(scene.getQualityProfile()).toBe('high');
    expect(mockRenderer.shadowMap.enabled).toBe(true);

    scene.dispose();

    // 3. High-density scenario (36 synthetic agents across 12 canonical departments)
    const twelveUnits = Array.from({ length: 12 }, (_, i) => ({
      id: `unit-dense-${i}`,
      code: `D${i + 1}`,
      name: `Departamento Escalado ${i + 1}`,
      parentId: i >= 6 ? `unit-dense-${i - 6}` : null,
      leadRole: 'Lead',
      leadAgentId: null,
      description: '',
      standingCount: 2,
      ephemeralCount: 1,
      activeProjectsCount: 1,
    }));
    const thirtySixAgents: AgentIdentity[] = Array.from({ length: 36 }, (_, i) => ({
      id: `dense-agent-${i}`,
      name: `Agente Escalado ${i}`,
      type: i % 3 === 0 ? 'EPHEMERAL' : 'STANDING',
      roleTitle: i % 2 === 0 ? 'Ingeniero Backend' : 'Auditor SAST',
      unitId: twelveUnits[i % twelveUnits.length].id,
      capabilities: [],
      heartbeatStatus: 'HEALTHY',
      lastHeartbeatAt: '2026-11-03T12:00:00Z',
      status: i % 2 === 0 ? 'BUSY' : 'IDLE',
      operationalState: i % 2 === 0 ? 'EJECUTANDO' : 'REGISTRADO',
      currentAssignments:
        i % 2 === 0
          ? [
              {
                id: `asg-dense-${i}`,
                projectId: 'proj-alpha',
                projectName: 'Proyecto Alpha',
                taskId: `task-${i}`,
                taskTitle: 'Desarrollo de módulo crítico',
                assignedAt: '2026-11-03T11:30:00Z',
                status: 'ACTIVE',
              },
            ]
          : [],
      authorityBoundary: 'Estándar',
    }));

    const denseCampus = buildCorporateCampusLayout(twelveUnits, thirtySixAgents, { isDemo: false });
    expect(denseCampus.rooms.length).toBe(12);
    expect(denseCampus.bounds.recommendedOverviewDistance).toBeGreaterThan(24);

    const denseScene = new ThreeOfficeScene(container, {
      renderer: mockRenderer,
      reducedMotion: false,
      rooms: denseCampus.rooms,
      qualityProfile: 'balanced',
      callbacks: {
        onSelectRoom: vi.fn(),
        onSelectAgent: vi.fn(),
        onHoverObject: vi.fn(),
      },
    });
    denseScene.updateAgents(denseCampus.normalizedAgents);
    denseScene.stepAnimation(500);
    const densePerf = denseScene.getPerformanceMetrics();
    expect(densePerf.roomsCount).toBe(12);
    expect(densePerf.agentsCount).toBe(36);
    expect(densePerf.lastFrameTimeMs).toBeLessThan(50);

    denseScene.dispose();
  });
});
