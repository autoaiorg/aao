import React, { useState, useMemo, useRef, useEffect } from 'react';
import type { VirtualOfficeViewProps, OfficeHudTabId, OfficeCameraPreset, OfficeRoomConfig } from './types';
import type { AgentIdentity } from '../../domain/models';
import { OfficeToolbar } from './components/OfficeToolbar';
import { Office3DCanvas, type WebGLCanvasHandle } from './components/Office3DCanvas';
import { Office2DPlan } from './components/Office2DPlan';
import { OfficeContextSidebar } from './components/OfficeContextSidebar';
import { AgentDetailDrawer } from '../organization/AgentDetailDrawer';
import { OfficeWorkRequestPanel } from './components/OfficeWorkRequestPanel';
import { OfficeConversationPanel } from './components/OfficeConversationPanel';
import { OfficeWorkGroupPanel } from './components/OfficeWorkGroupPanel';
import { OfficeCapabilityCatalogPanel } from './components/OfficeCapabilityCatalogPanel';
import { OfficeActivityPanel } from './components/OfficeActivityPanel';
import { OfficeKnowledgePanel } from './components/OfficeKnowledgePanel';
import { OfficeRoutinesPanel } from './components/OfficeRoutinesPanel';
import { OfficeCalendarPanel } from './components/OfficeCalendarPanel';
import { OfficeTopRibbon } from './components/OfficeTopRibbon';
import { OfficeLeftRosterDock } from './components/OfficeLeftRosterDock';
import { OfficeRadarMinimap } from './components/OfficeRadarMinimap';
import {
  OfficeBottomTacticalDeck,
  type HudModuleDescriptor,
} from './components/OfficeBottomTacticalDeck';
import { buildCorporateCampusLayout } from './liveOfficeLayout';
import { buildOfficeWorldPlan, resolveLocalNpcPositions } from './officeWorldRuntime';
import {
  filterOperationalAgents,
  isInteractiveOrEditableElement,
  useOfficeHudState,
} from './useOfficeHudState';
import {
  buildEnterpriseProjection,
  type EnterpriseEntitySelection,
} from './v3/enterpriseProjection';
import { useSpatialWindowManager } from './v3/useSpatialWindowManager';
import { SpatialWindowManager } from './v3/SpatialWindowManager';
import { OrganizationExplorerPanel } from './v3/OrganizationExplorerPanel';
import { OrganizationConstitutionCenter } from './v3/OrganizationConstitutionCenter';
import { EnterpriseEntityInspector } from './v3/EnterpriseEntityInspector';
import { SpatialWorkflowsPanel } from './v3/SpatialWorkflowsPanel';
import { OperationalTimelinePanel } from './v3/OperationalTimelinePanel';
import './components/office-game-hud.css';

export const VirtualOfficeView: React.FC<VirtualOfficeViewProps> = ({
  organization,
  projects = { kind: 'unavailable', reason: 'Lista de proyectos no disponible.', retryable: true },
  alertsState,
  decisionsState,
  canCreateWorkRequest = false,
  conversationPort,
  workGroupPort,
  isCeoSession = false,
  capabilityReadPort,
  capabilityFeedbackPort,
  activityReadPort,
  knowledgeReadPort,
  calendarReadPort,
  routinePort,
  officeWorldPort,
  conversationSessionId,
  canManageOrganization = false,
  onSaveUnit,
  onSaveProfile,
  onCreateWorkRequest,
  onNavigate,
  onRefresh,
}) => {
  const data = organization.kind === 'ready' ? organization.data : null;
  const isDemo = organization.kind === 'ready' && organization.origin === 'demo';

  const rawUnits = useMemo(() => data?.units || [], [data]);
  const rawAgents = useMemo(() => data?.agents || [], [data]);
  const previousLayoutRef = useRef<{ isDemo: boolean; rooms: OfficeRoomConfig[] } | null>(null);
  const campusLayout = useMemo(() => {
    const previousRooms = previousLayoutRef.current?.isDemo === isDemo
      ? previousLayoutRef.current.rooms
      : [];
    const layout = buildCorporateCampusLayout(rawUnits, rawAgents, { isDemo, previousRooms });
    previousLayoutRef.current = { isDemo, rooms: layout.rooms };
    return layout;
  }, [rawUnits, rawAgents, isDemo]);
  const units = campusLayout.effectiveUnits;
  const allAgents = campusLayout.normalizedAgents;
  const roomConfigs = campusLayout.rooms;
  // Scene geometry must follow the selected source exactly. In particular, an empty
  // LIVE organization is an empty set of enterprise zones, not a reason to borrow
  // the synthetic DEMO roster. The renderer owns the source-neutral building shell.
  const sceneRooms = roomConfigs;
  const liveStatusMessage = isDemo
    ? 'DEMO · SIMULACIÓN 3D ACTIVA · Todos los departamentos, agentes y asignaciones son sintéticos y no representan datos de producción.'
    : data && campusLayout.diagnostics.canonicalUnitsCount === 0
    ? `LIVE · SIN DEPARTAMENTOS DECLARADOS · ${campusLayout.diagnostics.totalAgentsCount} identidades recibidas; ${campusLayout.diagnostics.unassignedAgentsCount} sin adscripción. Se muestra solo la arquitectura base, sin departamentos ni actividad simulados.`
    : data && campusLayout.diagnostics.totalAgentsCount === 0
    ? 'LIVE · ESTRUCTURA PERSISTIDA SIN IDENTIDADES DE AGENTE · La oficina no representa trabajadores ni actividad hasta recibir datos verificables.'
    : data
    ? `LIVE · ESTRUCTURA PERSISTIDA · Plano 2D y escena 3D derivados de las unidades y agentes recibidos del backend. La geometría es una representación visual; estado y actividad solo reflejan evidencia proyectada. ${
        data.coverage
          ? data.coverage.notes ||
            (data.coverage.isPartial
              ? `Cobertura parcial (${data.coverage.failedProjects} errores en ${data.coverage.totalProjects} proyectos).`
              : `Cobertura completa (${data.coverage.inspectedProjects}/${data.coverage.totalProjects} proyectos).`)
          : 'La presencia operativa está condicionada a telemetría verificada en tiempo real.'
      }`
    : organization.kind === 'empty'
    ? 'LIVE · RESPUESTA VACÍA · El servicio respondió sin una estructura organizativa disponible; esto no equivale a un error de conexión.'
    : organization.kind === 'forbidden'
    ? 'LIVE · ACCESO DENEGADO · La estructura no puede mostrarse con la autorización actual.'
    : organization.kind === 'error'
    ? `LIVE · ERROR DE CARGA · ${organization.message}`
    : organization.kind === 'unavailable'
    ? `SIN CONEXIÓN AL NÚCLEO EN LIVE (F3/F4) · ${organization.reason} La vista no utiliza datos DEMO como respaldo.`
    : organization.kind === 'ready'
    ? 'LIVE · ESTRUCTURA PERSISTIDA · La vista representa exclusivamente los datos recibidos; no incorpora datos DEMO como respaldo.'
    : 'LIVE · ESTADO NO DISPONIBLE · La vista no utiliza datos DEMO como respaldo.';

  // Compute which LIVE operational modules are available
  const availableTabs = useMemo<OfficeHudTabId[]>(() => {
    if (isDemo) return [];
    const tabs: OfficeHudTabId[] = [];
    if (canCreateWorkRequest && onCreateWorkRequest) tabs.push('work-request');
    if (conversationPort && conversationSessionId) tabs.push('comms');
    if (activityReadPort && conversationSessionId) tabs.push('activity');
    if ((workGroupPort || conversationPort) && conversationSessionId) tabs.push('work-groups');
    if (capabilityReadPort && conversationSessionId) tabs.push('capabilities');
    if (routinePort && conversationSessionId) tabs.push('routines');
    if (calendarReadPort && conversationSessionId) tabs.push('calendar');
    if (knowledgeReadPort && conversationSessionId) tabs.push('knowledge');
    return tabs;
  }, [
    isDemo,
    canCreateWorkRequest,
    onCreateWorkRequest,
    conversationPort,
    conversationSessionId,
    activityReadPort,
    workGroupPort,
    capabilityReadPort,
    routinePort,
    calendarReadPort,
    knowledgeReadPort,
  ]);

  const hud = useOfficeHudState({
    initialViewMode: '3d',
    availableTabs,
    agents: allAgents,
  });

  const {
    layoutMode,
    setLayoutMode,
    activeBottomTab,
    setActiveBottomTab,
    detachedTab,
    setDetachedTab,
    bottomDeckState,
    setBottomDeckState,
    bottomDeckHeightPx,
    setBottomDeckHeightPx,
    cameraPreset,
    setCameraPreset,
    isRosterOpen,
    setIsRosterOpen,
    rosterWidthPx,
    setRosterWidthPx,
    isInspectorOpen,
    setIsInspectorOpen,
    isMinimapOpen,
    setIsMinimapOpen,
    autoSyncContext,
    setAutoSyncContext,
    qualityProfile,
    setQualityProfile,
    isToolbarCollapsed,
    setIsToolbarCollapsed,
    panelOrder,
    moveTabOrder,
    viewMode,
    setViewMode,
    selectedRoomId,
    setSelectedRoomId,
    selectRoom,
    selectedAgentId,
    selectAgent,
    contextProjectId,
    zenMode,
    setZenMode,
    followAgent,
    setFollowAgent,
    cameraState,
    setCameraState,
    searchQuery,
    setSearchQuery,
    typeFilter,
    setTypeFilter,
    reducedMotion,
    setReducedMotion,
  } = hud;

  const [drawerAgent, setDrawerAgent] = useState<AgentIdentity | null>(null);
  const [userToggledDeck, setUserToggledDeck] = useState(false);
  const initialUnitSelectionDone = useRef(false);
  const initialViewModeChosen = useRef(true);
  const canvas3DRef = useRef<WebGLCanvasHandle>(null);
  const officeWorldPlan = useMemo(() => data ? buildOfficeWorldPlan({
    agents: allAgents,
    rooms: roomConfigs,
    navigation: campusLayout.navGraph,
  }) : null, [data, allAgents, roomConfigs, campusLayout.navGraph]);

  useEffect(() => {
    if (!officeWorldPlan) {
      canvas3DRef.current?.syncWorldActors([]);
      return;
    }
    let cancelled = false;
    let running = false;
    const sync = async () => {
      if (cancelled || running) return;
      running = true;
      try {
        if (isDemo) {
          canvas3DRef.current?.syncWorldActors(resolveLocalNpcPositions(officeWorldPlan));
          return;
        }
        if (!officeWorldPort) return;
        if (isCeoSession) {
          const published = await officeWorldPort.publishPlan(officeWorldPlan);
          if (cancelled || !published.ok) return;
        }
        const positions = await officeWorldPort.getPositions();
        if (!cancelled && positions && positions.every((position) => position.map_revision === officeWorldPlan.map_revision)) {
          canvas3DRef.current?.syncWorldActors(positions);
        }
      } finally {
        running = false;
      }
    };
    void sync();
    const timer = window.setInterval(() => void sync(), 2500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [officeWorldPlan, isDemo, isCeoSession, officeWorldPort]);

  const effectiveBottomDeckState =
    !userToggledDeck && projects.kind === 'unavailable' ? 'minimized' : bottomDeckState;

  useEffect(() => {
    const isDerivedUnassignedUnit =
      selectedRoomId === 'unit-unassigned' &&
      allAgents.some((agent) => agent.unitId === 'unit-unassigned' || !units.some((unit) => unit.id === agent.unitId));
    if (
      units.length &&
      (!initialUnitSelectionDone.current ||
        (!isDerivedUnassignedUnit && !units.some((unit) => unit.id === selectedRoomId)))
    ) {
      initialUnitSelectionDone.current = true;
      const firstAssignedUnit = units.find((unit) => unit.id !== 'unit-unassigned');
      setSelectedRoomId(firstAssignedUnit?.id || units[0].id);
    }
  }, [allAgents, selectedRoomId, units, setSelectedRoomId]);

  // Filtered agents by search and type
  const filteredAgents = useMemo(() => {
    return allAgents.filter((agent) => {
      if (typeFilter !== 'ALL' && agent.type !== typeFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = agent.name.toLowerCase().includes(q);
        const matchesRole = agent.roleTitle.toLowerCase().includes(q);
        const matchesCap = agent.capabilities.some((c) => c.name.toLowerCase().includes(q));
        if (!matchesName && !matchesRole && !matchesCap) return false;
      }
      return true;
    });
  }, [allAgents, typeFilter, searchQuery]);
  // Keep the renderer input independent of roster search/type filters. Passing a
  // keystroke-filtered array into ThreeOfficeScene rebuilt every avatar and
  // route on each query change; filtering is a presentation concern for the HUD.
  const sceneAgents = useMemo(() => filterOperationalAgents(allAgents), [allAgents]);
  // Revoked identities remain available to the top-level historical count and
  // detail/history views, but should not occupy the live office or rosters.
  const operationalAgents = useMemo(() => filterOperationalAgents(filteredAgents), [filteredAgents]);

  // Prioritize contextProjectId in projects list when autoSyncContext is enabled
  const contextualizedProjects = useMemo(() => {
    if (!autoSyncContext || !contextProjectId || projects.kind !== 'ready') return projects;
    const exists = projects.data.some((p) => p.id === contextProjectId);
    if (!exists) return projects;
    const target = projects.data.find((p) => p.id === contextProjectId)!;
    const rest = projects.data.filter((p) => p.id !== contextProjectId);
    return {
      ...projects,
      data: [target, ...rest],
    };
  }, [autoSyncContext, contextProjectId, projects]);

  // Build HUD modules list
  const hudModules = useMemo<HudModuleDescriptor[]>(() => {
    if (isDemo) return [];
    const list: HudModuleDescriptor[] = [];

    if (canCreateWorkRequest && onCreateWorkRequest) {
      list.push({
        id: 'work-request',
        label: 'Misiones CEO',
        icon: '⚡',
        shortcutKey: '1',
        node: (
          <OfficeWorkRequestPanel
            projects={contextualizedProjects}
            onCreate={onCreateWorkRequest}
            onOpenBoard={(projectId) => onNavigate?.('kanban', projectId)}
          />
        ),
      });
    }

    if (conversationPort && conversationSessionId) {
      list.push({
        id: 'comms',
        label: 'Comms',
        icon: '💬',
        shortcutKey: '2',
        node: (
          <OfficeConversationPanel
            projects={contextualizedProjects}
            port={conversationPort}
            sessionId={conversationSessionId}
            onOpenBoard={(projectId, workId) => onNavigate?.('kanban', projectId, workId)}
          />
        ),
      });
    }

    if (activityReadPort && conversationSessionId) {
      list.push({
        id: 'activity',
        label: 'Telemetría',
        icon: '📜',
        shortcutKey: '3',
        node: (
          <OfficeActivityPanel
            projects={contextualizedProjects}
            port={activityReadPort}
            sessionId={conversationSessionId}
            onOpenBoard={(projectId, workId) => onNavigate?.('kanban', projectId, workId)}
          />
        ),
      });
    }

    if ((workGroupPort || conversationPort) && conversationSessionId) {
      list.push({
        id: 'work-groups',
        label: 'Escuadras',
        icon: '👥',
        shortcutKey: '4',
        node: (
          <OfficeWorkGroupPanel
            projects={contextualizedProjects}
            port={workGroupPort || conversationPort!}
            sessionId={conversationSessionId}
            isCeoSession={isCeoSession}
            onOpenBoard={(projectId) => onNavigate?.('kanban', projectId)}
          />
        ),
      });
    }

    if (capabilityReadPort && conversationSessionId) {
      list.push({
        id: 'capabilities',
        label: 'Capacidades',
        icon: '🧩',
        shortcutKey: '5',
        node: (
          <OfficeCapabilityCatalogPanel
            projects={contextualizedProjects}
            port={capabilityReadPort}
            feedbackPort={capabilityFeedbackPort}
            sessionId={conversationSessionId}
          />
        ),
      });
    }

    if (routinePort && conversationSessionId) {
      list.push({
        id: 'routines',
        label: 'Rutinas',
        icon: '⚙️',
        shortcutKey: '6',
        node: (
          <OfficeRoutinesPanel
            projects={contextualizedProjects}
            port={routinePort}
            sessionId={conversationSessionId}
            isCeoSession={isCeoSession}
          />
        ),
      });
    }

    if (calendarReadPort && conversationSessionId) {
      list.push({
        id: 'calendar',
        label: 'Agenda',
        icon: '📅',
        shortcutKey: '7',
        node: (
          <OfficeCalendarPanel
            projects={contextualizedProjects}
            port={calendarReadPort}
            sessionId={conversationSessionId}
            onOpenWork={(projectId, workId) => onNavigate?.('kanban', projectId, workId)}
          />
        ),
      });
    }

    if (knowledgeReadPort && conversationSessionId) {
      list.push({
        id: 'knowledge',
        label: 'Conocimiento',
        icon: '🧠',
        shortcutKey: '8',
        node: (
          <OfficeKnowledgePanel
            projects={contextualizedProjects}
            port={knowledgeReadPort}
            sessionId={conversationSessionId}
            onOpenBoard={(projectId, workId) => onNavigate?.('kanban', projectId, workId)}
          />
        ),
      });
    }

    return list;
  }, [
    isDemo,
    canCreateWorkRequest,
    onCreateWorkRequest,
    contextualizedProjects,
    onNavigate,
    conversationPort,
    conversationSessionId,
    activityReadPort,
    workGroupPort,
    isCeoSession,
    capabilityReadPort,
    capabilityFeedbackPort,
    routinePort,
    calendarReadPort,
    knowledgeReadPort,
  ]);

  // Safe Keyboard Shortcuts (Z for Zen, Space only outside interactive/editable controls, 1-8 for tabs, Escape)
  useEffect(() => {
    if (layoutMode !== 'hud') return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === 'Escape') {
        if (drawerAgent) {
          setDrawerAgent(null);
          return;
        }
        if (zenMode) {
          setZenMode(false);
          return;
        }
        if (detachedTab) {
          setDetachedTab(null);
          return;
        }
        if (bottomDeckState === 'maximized') {
          setBottomDeckState('docked');
          return;
        }
        return;
      }

      // Do not intercept keys when typing in inputs, textareas, selects, or focused buttons/links
      if (isInteractiveOrEditableElement(e.target)) {
        return;
      }

      if (e.key === 'z' || e.key === 'Z') {
        e.preventDefault();
        setZenMode((prev) => !prev);
        return;
      }

      if (e.key === ' ') {
        e.preventDefault();
        setZenMode((prev) => !prev);
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        canvas3DRef.current?.pan(0, -1.8);
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        canvas3DRef.current?.pan(0, 1.8);
        return;
      }

      // Number hotkeys 1-8 for Bottom Tactical Deck modules
      if (e.key >= '1' && e.key <= '8') {
        const index = Number(e.key) - 1;
        const orderedIds = panelOrder.filter((id) => hudModules.some((m) => m.id === id));
        const targetId = orderedIds[index] || hudModules[index]?.id;
        if (targetId) {
          e.preventDefault();
          setZenMode(false);
          setActiveBottomTab(targetId);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    layoutMode,
    drawerAgent,
    zenMode,
    detachedTab,
    bottomDeckState,
    panelOrder,
    hudModules,
    setZenMode,
    setDetachedTab,
    setBottomDeckState,
    setActiveBottomTab,
  ]);

  // Derive Critical Alerts & Pending CEO/Audit Decisions (Improvement #3: visible even in Zen Mode)
  const criticalAlerts = useMemo(() => {
    const items = alertsState?.kind === 'ready' ? alertsState.data : [];
    return items.filter((a) => a.severity === 'critical' || a.severity === 'high');
  }, [alertsState]);

  const pendingCeoDecisions = useMemo(() => {
    const items = decisionsState?.kind === 'ready' ? decisionsState.data : [];
    return items.filter(
      (d) =>
        d.category === 'ceo_pending' ||
        d.category === 'auditor_pending' ||
        d.category === 'policy_blocked'
    );
  }, [decisionsState]);

  const executionBlockAlertsCount = useMemo(() => {
    return allAgents.filter((a) =>
      a.executionHistory?.some(
        (ex) => ex.isBudgetExceeded || ex.isNoProgressRetry || Boolean(ex.alert)
      )
    ).length;
  }, [allAgents]);

  const hasCriticalGovernanceSignal =
    criticalAlerts.length > 0 || pendingCeoDecisions.length > 0 || executionBlockAlertsCount > 0;

  const handleSelectCameraPreset = (preset: OfficeCameraPreset) => {
    setCameraPreset(preset);
    canvas3DRef.current?.setPreset(preset);
  };

  const selectedAgentObj = useMemo(
    () => allAgents.find((a) => a.id === selectedAgentId) || null,
    [allAgents, selectedAgentId]
  );

  // V3 Enterprise Projection & Multi-Window Spatial Desktop State
  const projectsList = useMemo(
    () => (projects.kind === 'ready' ? projects.data : []),
    [projects]
  );
  const alertsList = useMemo(
    () => (alertsState?.kind === 'ready' ? alertsState.data : []),
    [alertsState]
  );
  const decisionsList = useMemo(
    () => (decisionsState?.kind === 'ready' ? decisionsState.data : []),
    [decisionsState]
  );
  const historicalCount =
    data?.historicalAgentCount ?? (filteredAgents.length - operationalAgents.length);

  const enterpriseProjection = useMemo(
    () =>
      buildEnterpriseProjection({
        origin: isDemo ? 'demo' : 'live',
        persistedUnits: rawUnits,
        effectiveUnits: units,
        rooms: sceneRooms,
        agents: operationalAgents,
        historicalAgentCount: historicalCount,
        coverage: data?.coverage,
        diagnostics: campusLayout.diagnostics,
        projects: projectsList,
        alerts: alertsList,
        decisions: decisionsList,
      }),
    [
      isDemo,
      rawUnits,
      units,
      sceneRooms,
      operationalAgents,
      historicalCount,
      data?.coverage,
      campusLayout.diagnostics,
      projectsList,
      alertsList,
      decisionsList,
    ]
  );

  const spatialWindows = useSpatialWindowManager();
  const [selectedEnterpriseEntity, setSelectedEnterpriseEntity] =
    useState<EnterpriseEntitySelection>(() => ({
      kind: 'department',
      id: selectedRoomId || 'unit-exec',
    }));

  const handleSelectEnterpriseEntity = (selection: EnterpriseEntitySelection) => {
    setSelectedEnterpriseEntity(selection);
    if (selection.kind === 'department') {
      selectRoom(selection.id);
    } else if (selection.kind === 'agent') {
      selectAgent(selection.id);
    } else if (selection.kind === 'workstation') {
      const ws = enterpriseProjection.workstations.find((w) => w.id === selection.id);
      if (ws) {
        selectRoom(ws.unitId);
        if (ws.technicalIdentityId) {
          selectAgent(ws.technicalIdentityId);
        }
      }
    }
    spatialWindows.openWindow('entity-inspector');
  };

  // =========================================================================
  // CLASSIC MODE (Preserves traditional stacked layout 100%)
  // =========================================================================
  if (layoutMode === 'classic') {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-5, 20px)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2, 8px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <h2 style={{ margin: '0 0 4px 0', fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
                Oficina Virtual 3D · AAO
              </h2>
              <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
                Entorno espacial tridimensional para inspeccionar departamentos, agentes y su actividad persistida. En LIVE, estructura y proyectos se actualizan cada 15 segundos mientras la oficina está abierta.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                type="button"
                onClick={() => setLayoutMode('hud')}
                style={{
                  padding: '8px 14px',
                  borderRadius: 'var(--radius-md, 8px)',
                  border: '1px solid var(--accent)',
                  backgroundColor: 'var(--accent-light)',
                  color: 'var(--accent)',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                🎮 Cambiar a HUD Videojuego
              </button>
              {onRefresh && (
                <button
                  type="button"
                  onClick={onRefresh}
                  style={{
                    padding: '8px 14px',
                    borderRadius: 'var(--radius-md, 8px)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  ↻ Actualizar
                </button>
              )}
            </div>
          </div>

          <div
            role="status"
            style={{
              padding: '12px 16px',
              borderRadius: 'var(--radius-md, 8px)',
              backgroundColor: isDemo
                ? 'var(--status-demo-bg)'
                : data
                ? 'var(--status-info-bg)'
                : 'var(--status-warning-bg)',
              border: isDemo
                ? '1px solid var(--status-demo-border)'
                : data
                ? '1px solid var(--status-info-border)'
                : '1px solid var(--status-warning-border)',
              color: isDemo
                ? 'var(--status-demo-text)'
                : data
                ? 'var(--status-info-text)'
                : 'var(--status-warning-text)',
              fontSize: '12px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              lineHeight: 1.45,
            }}
          >
            <span aria-hidden="true" style={{ fontSize: '15px' }}>
              {isDemo ? '⚠' : data ? 'ℹ' : '🔒'}
            </span>
            <span>{liveStatusMessage}</span>
          </div>
        </div>

        <OfficeToolbar
          viewMode={viewMode}
          onViewModeChange={(mode) => {
            initialViewModeChosen.current = true;
            setViewMode(mode);
          }}
          selectedRoomId={selectedRoomId}
          units={units}
          onSelectRoom={selectRoom}
          onRotateCamera={(deg) => canvas3DRef.current?.rotate(deg)}
          onZoomCamera={(factor) => canvas3DRef.current?.zoom(factor)}
          onResetCamera={() => canvas3DRef.current?.reset()}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          typeFilter={typeFilter}
          onTypeFilterChange={setTypeFilter}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={() => setReducedMotion((prev) => !prev)}
          isDemo={isDemo}
          allow3D={true}
        />

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) 340px',
            gap: 'var(--space-5, 20px)',
            alignItems: 'start',
          }}
        >
          <div>
            {viewMode === '3d' ? (
              <Office3DCanvas
                ref={canvas3DRef}
                agents={sceneAgents}
                rooms={sceneRooms}
                demoFurniture={isDemo}
                selectedRoomId={selectedRoomId}
                selectedAgentId={selectedAgentId}
                onSelectRoom={selectRoom}
                onSelectAgent={selectAgent}
                onFallbackTo2D={() => setViewMode('2d')}
                onCameraChange={setCameraState}
                reducedMotion={reducedMotion}
                qualityProfile={qualityProfile}
                followAgent={followAgent}
              />
            ) : (
              <Office2DPlan
                units={units}
                agents={operationalAgents}
                selectedRoomId={selectedRoomId}
                selectedAgentId={selectedAgentId}
                onSelectRoom={selectRoom}
                onSelectAgent={selectAgent}
                isDemo={isDemo}
              />
            )}
          </div>

          <OfficeContextSidebar
            selectedRoomId={selectedRoomId}
            selectedAgentId={selectedAgentId}
            units={units}
            agents={operationalAgents}
            onSelectAgent={selectAgent}
            onNavigate={onNavigate}
            onOpenAgentDetail={(agent) => setDrawerAgent(agent)}
            isDemo={isDemo}
            attributionDiagnostics={campusLayout.diagnostics}
          />
        </div>

        {hudModules.map((mod) => (
          <React.Fragment key={mod.id}>{mod.node}</React.Fragment>
        ))}

        <AgentDetailDrawer agent={drawerAgent} onClose={() => setDrawerAgent(null)} />
      </div>
    );
  }

  // =========================================================================
  // VIDEO GAME SPATIAL HUD MODE (Default)
  // =========================================================================
  return (
    <div className="aao-game-stage" data-testid="office-game-stage">
      {/* 1. Primary Full-Viewport 3D / 2D Spatial Stage */}
      <div className="aao-game-stage__viewport">
        {viewMode === '3d' ? (
          <Office3DCanvas
            ref={canvas3DRef}
            agents={sceneAgents}
            rooms={sceneRooms}
            demoFurniture={isDemo}
            selectedRoomId={selectedRoomId}
            selectedAgentId={selectedAgentId}
            onSelectRoom={selectRoom}
            onSelectAgent={selectAgent}
            onFallbackTo2D={() => setViewMode('2d')}
            onCameraChange={setCameraState}
            reducedMotion={reducedMotion}
            fullViewport={true}
            qualityProfile={qualityProfile}
            followAgent={followAgent}
          />
        ) : (
          <div style={{ padding: '16px', paddingTop: zenMode ? '16px' : '116px', paddingBottom: '240px' }}>
            <Office2DPlan
              units={units}
              agents={operationalAgents}
              selectedRoomId={selectedRoomId}
              selectedAgentId={selectedAgentId}
              onSelectRoom={selectRoom}
              onSelectAgent={selectAgent}
              isDemo={isDemo}
            />
          </div>
        )}
      </div>

      {/* 2. Zen Mode Critical Alert Beacon & Exit Control (Improvement #3) */}
      {zenMode && (
        <div className="aao-hud-zen-overlay" role="region" aria-label="Controles y alertas críticas en Modo Zen">
          <button
            type="button"
            onClick={() => setZenMode(false)}
            className="aao-hud-btn aao-hud-glass"
            aria-label="Salir de Modo Zen y restaurar paneles HUD"
          >
            🧘 Salir de Modo Zen [Z / Esc]
          </button>

          {hasCriticalGovernanceSignal && (
            <div
              role="alert"
              aria-live="assertive"
              className="aao-hud-critical-beacon"
            >
              <span aria-hidden="true">🚨</span>
              <div>
                <div style={{ fontWeight: 800 }}>
                  Atención prioritaria requerida (Modo Zen)
                </div>
                <div style={{ fontSize: '11px', fontWeight: 500 }}>
                  {criticalAlerts.length > 0 && `${criticalAlerts.length} alerta(s) crítica(s) · `}
                  {pendingCeoDecisions.length > 0 && `${pendingCeoDecisions.length} decisión(es) CEO/Auditoría · `}
                  {executionBlockAlertsCount > 0 && `${executionBlockAlertsCount} bloqueo(s) de ejecución`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {criticalAlerts.length > 0 && onNavigate && (
                  <button
                    type="button"
                    className="aao-hud-btn"
                    onClick={() => onNavigate('alerts')}
                  >
                    Ver Alertas
                  </button>
                )}
                {pendingCeoDecisions.length > 0 && onNavigate && (
                  <button
                    type="button"
                    className="aao-hud-btn"
                    onClick={() => onNavigate('decisions')}
                  >
                    Ver Decisiones
                  </button>
                )}
                <button
                  type="button"
                  className="aao-hud-btn"
                  onClick={() => setZenMode(false)}
                >
                  Abrir HUD
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3. Top HUD Ribbon (Hidden in Zen Mode) */}
      {!zenMode && (
        <OfficeTopRibbon
          isDemo={isDemo}
          liveStatusMessage={liveStatusMessage}
          hasLiveStructure={Boolean(data)}
          units={units}
          agents={operationalAgents}
          historicalAgentCount={data?.historicalAgentCount ?? (filteredAgents.length - operationalAgents.length)}
          selectedRoomId={selectedRoomId}
          selectedAgentId={selectedAgentId}
          onSelectRoom={selectRoom}
          viewMode={viewMode}
          onViewModeChange={(mode) => {
            initialViewModeChosen.current = true;
            setViewMode(mode);
          }}
          allow3D={true}
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          cameraPreset={cameraPreset}
          onSelectCameraPreset={handleSelectCameraPreset}
          onRotateCamera={(deg) => canvas3DRef.current?.rotate(deg)}
          onZoomCamera={(factor) => canvas3DRef.current?.zoom(factor)}
          onResetCamera={() => canvas3DRef.current?.reset()}
          reducedMotion={reducedMotion}
          onToggleReducedMotion={() => setReducedMotion((prev) => !prev)}
          zenMode={zenMode}
          onToggleZenMode={() => setZenMode((prev) => !prev)}
          onRefresh={onRefresh}
          criticalAlerts={criticalAlerts}
          pendingCeoDecisions={pendingCeoDecisions}
          onOpenAlerts={onNavigate ? () => onNavigate('alerts') : undefined}
          onOpenDecisions={onNavigate ? () => onNavigate('decisions') : undefined}
          onOpenOrganization={onNavigate ? () => onNavigate('organization') : undefined}
          attributionDiagnostics={campusLayout.diagnostics}
          qualityProfile={qualityProfile}
          onQualityProfileChange={setQualityProfile}
          followAgent={followAgent}
          onToggleFollowAgent={() => setFollowAgent((prev) => !prev)}
          isToolbarCollapsed={isToolbarCollapsed}
          onToggleToolbarCollapsed={() => setIsToolbarCollapsed((prev) => !prev)}
        />
      )}

      {/* 4. Middle HUD Layer: Left Roster + Minimap | Detached Window | Right Inspector */}
      {!zenMode && (
        <div className="aao-hud-middle-layer">
          {/* Left Column: Sector/Agent Roster + 2D Radar Minimap */}
          <div className="aao-hud-left-column">
            <OfficeLeftRosterDock
              isOpen={isRosterOpen}
              onToggleOpen={() => setIsRosterOpen((prev) => !prev)}
              widthPx={rosterWidthPx}
              onWidthChange={setRosterWidthPx}
              units={units}
              agents={operationalAgents}
              selectedRoomId={selectedRoomId}
              selectedAgentId={selectedAgentId}
              onSelectRoom={selectRoom}
              onSelectAgent={selectAgent}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              typeFilter={typeFilter}
              onTypeFilterChange={setTypeFilter}
              autoSyncContext={autoSyncContext}
              onToggleAutoSyncContext={setAutoSyncContext}
              contextProjectId={contextProjectId}
            />

            <OfficeRadarMinimap
              isOpen={isMinimapOpen}
              onToggleOpen={() => setIsMinimapOpen((prev) => !prev)}
              rooms={roomConfigs}
              agents={operationalAgents}
              selectedRoomId={selectedRoomId}
              selectedAgentId={selectedAgentId}
              cameraState={cameraState}
              onSelectRoom={selectRoom}
              onSelectAgent={(id) => selectAgent(id)}
            />
          </div>

          {/* Right Column: Collapsible Target Inspector */}
          <div className="aao-hud-right-column">
            <div className="aao-hud-inspector-wrapper aao-hud-glass">
              <div className="aao-hud-inspector-wrapper__header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span aria-hidden="true">🎯</span>
                  <strong style={{ fontSize: '12px', color: '#f8fafc' }}>
                    INSPECTOR TÁCTICO
                  </strong>
                </div>
                <button
                  type="button"
                  className="aao-hud-btn"
                  style={{ padding: '2px 8px', fontSize: '11px' }}
                  aria-expanded={isInspectorOpen}
                  aria-label={isInspectorOpen ? 'Comprimir inspector táctico' : 'Expandir inspector táctico'}
                  onClick={() => setIsInspectorOpen((prev) => !prev)}
                >
                  {isInspectorOpen ? '▼ Comprimir' : '▲ Expandir'}
                </button>
              </div>

              <div
                className="aao-hud-inspector-wrapper__scroll"
                style={{ display: isInspectorOpen ? 'block' : 'none' }}
              >
                <OfficeContextSidebar
                  selectedRoomId={selectedRoomId}
                  selectedAgentId={selectedAgentId}
                  units={units}
                  agents={operationalAgents}
                  onSelectAgent={selectAgent}
                  onNavigate={onNavigate}
                  onOpenAgentDetail={(agent) => setDrawerAgent(agent)}
                  isDemo={isDemo}
                  attributionDiagnostics={campusLayout.diagnostics}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 4B. V3 Multi-Application Spatial Window Manager (Hidden in Zen Mode) */}
      {!zenMode && (
        <SpatialWindowManager
          windows={spatialWindows.windows}
          onToggleWindow={spatialWindows.toggleWindow}
          onCloseWindow={spatialWindows.closeWindow}
          onFocusWindow={spatialWindows.focusWindow}
          onToggleMinimizeWindow={spatialWindows.toggleMinimizeWindow}
          onToggleMaximizeWindow={spatialWindows.toggleMaximizeWindow}
          onSelectAtrium={() =>
            handleSelectEnterpriseEntity({ kind: 'atrium', id: 'atrium-central' })
          }
          requiresConstitution={enterpriseProjection.atrium.requiresConstitution}
          windowNodes={{
            'organization-explorer': (
              <OrganizationExplorerPanel
                units={units}
                agents={operationalAgents}
                projects={projectsList}
                alerts={alertsList}
                projection={enterpriseProjection}
                selectedEntity={selectedEnterpriseEntity}
                onSelectEntity={handleSelectEnterpriseEntity}
                onOpenConstitutionCenter={() =>
                  spatialWindows.openWindow('constitution-center')
                }
              />
            ),
            'constitution-center': (
              <OrganizationConstitutionCenter
                persistedUnits={rawUnits}
                agents={operationalAgents}
                historicalAgentCount={historicalCount}
                unassignedAgentsCount={campusLayout.diagnostics.unassignedAgentsCount}
                registeredProfilesCount={campusLayout.diagnostics.resolvedAgentsCount}
                isDemo={isDemo}
                canManageOrganization={canManageOrganization}
                onSaveUnit={onSaveUnit}
                onSaveProfile={onSaveProfile}
                onRefresh={onRefresh}
              />
            ),
            'entity-inspector': (
              <EnterpriseEntityInspector
                selection={selectedEnterpriseEntity}
                units={units}
                agents={operationalAgents}
                projects={projectsList}
                alerts={alertsList}
                decisions={decisionsList}
                projection={enterpriseProjection}
                isDemo={isDemo}
                canManageOrganization={canManageOrganization}
                onSelectEntity={handleSelectEnterpriseEntity}
                onOpenConstitutionCenter={() =>
                  spatialWindows.openWindow('constitution-center')
                }
                onOpenAgentDetail={(agent) => setDrawerAgent(agent)}
                onNavigate={onNavigate}
              />
            ),
            'spatial-workflows': (
              <SpatialWorkflowsPanel
                projects={projectsList}
                projection={enterpriseProjection}
                onSelectEntity={handleSelectEnterpriseEntity}
                onNavigate={onNavigate}
              />
            ),
            'operational-timeline': (
              <OperationalTimelinePanel
                projection={enterpriseProjection}
                fetchedAt={organization.kind === 'ready' ? organization.fetchedAt : undefined}
                onSelectEntity={handleSelectEnterpriseEntity}
              />
            ),
          }}
        />
      )}

      {/* 5. Bottom HUD Tactical Deck (Hidden in Zen Mode) */}
      {!zenMode && (
        <OfficeBottomTacticalDeck
          modules={hudModules}
          panelOrder={panelOrder}
          activeTab={activeBottomTab}
          detachedTab={detachedTab}
          deckState={effectiveBottomDeckState}
          deckHeightPx={bottomDeckHeightPx}
          contextProjectId={contextProjectId}
          selectedAgentName={selectedAgentObj?.name || null}
          onSelectTab={(tab) => {
            setUserToggledDeck(true);
            setActiveBottomTab(tab);
          }}
          onSetDetachedTab={setDetachedTab}
          onSetDeckState={(state) => {
            setUserToggledDeck(true);
            setBottomDeckState(state);
          }}
          onSetDeckHeightPx={setBottomDeckHeightPx}
          onMoveTabOrder={moveTabOrder}
        />
      )}

      {/* Enriched Agent Drawer */}
      <AgentDetailDrawer agent={drawerAgent} onClose={() => setDrawerAgent(null)} />
    </div>
  );
};
