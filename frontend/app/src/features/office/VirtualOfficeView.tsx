import React, { useState, useMemo, useRef, useEffect } from 'react';
import type { VirtualOfficeViewProps, OfficeHudTabId, OfficeCameraPreset } from './types';
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
import { OFFICE_ROOMS } from './types';
import { buildCorporateCampusLayout } from './liveOfficeLayout';
import {
  filterOperationalAgents,
  isInteractiveOrEditableElement,
  useOfficeHudState,
} from './useOfficeHudState';
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
  conversationSessionId,
  onCreateWorkRequest,
  onNavigate,
  onRefresh,
}) => {
  const data = organization.kind === 'ready' ? organization.data : null;
  const isDemo = organization.kind === 'ready' && organization.origin === 'demo';

  const rawUnits = useMemo(() => data?.units || [], [data]);
  const rawAgents = useMemo(() => data?.agents || [], [data]);
  const campusLayout = useMemo(
    () => buildCorporateCampusLayout(rawUnits, rawAgents, { isDemo }),
    [rawUnits, rawAgents, isDemo]
  );
  const units = campusLayout.effectiveUnits;
  const allAgents = campusLayout.normalizedAgents;
  const roomConfigs = campusLayout.rooms;
  const sceneRooms = useMemo(
    () => (isDemo || roomConfigs.length === 0 ? OFFICE_ROOMS : roomConfigs),
    [isDemo, roomConfigs]
  );

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
            <span>
              {isDemo
                ? 'DEMO · SIMULACIÓN 3D ACTIVA · Todos los departamentos, agentes y asignaciones son sintéticos y no representan datos de producción.'
                : data
                ? `LIVE · ESTRUCTURA PERSISTIDA · Plano 2D y escena 3D derivados de las unidades y agentes recibidos del backend. La geometría es una representación visual; estado y actividad solo reflejan evidencia proyectada. ${
                    data.coverage
                      ? data.coverage.notes ||
                        (data.coverage.isPartial
                          ? `Cobertura parcial (${data.coverage.failedProjects} errores en ${data.coverage.totalProjects} proyectos).`
                          : `Cobertura completa (${data.coverage.inspectedProjects}/${data.coverage.totalProjects} proyectos).`)
                      : 'La presencia operativa está condicionada a telemetría verificada en tiempo real.'
                  }`
                : 'SIN CONEXIÓN AL NÚCLEO EN LIVE (F3/F4) · No hay estructura operativa disponible. DEMO, si se selecciona, se identifica por separado como simulación.'}
            </span>
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
                agents={operationalAgents}
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
            agents={operationalAgents}
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
          hasLiveStructure={Boolean(data)}
          coverage={data?.coverage}
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
