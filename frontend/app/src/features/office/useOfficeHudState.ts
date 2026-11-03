import { useState, useCallback, useEffect, useMemo } from 'react';
import type { AgentIdentity } from '../../domain/models';
import type {
  CameraViewState,
  OfficeBottomDeckState,
  OfficeCameraPreset,
  OfficeHudTabId,
  OfficeLayoutMode,
  OfficeViewMode,
  OperationalStateCategory,
} from './types';

export const HUD_PREFS_STORAGE_KEY = 'aao.office.hud.prefs.v1';

export const DEFAULT_PANEL_ORDER: readonly OfficeHudTabId[] = [
  'work-request',
  'comms',
  'activity',
  'work-groups',
  'capabilities',
  'routines',
  'calendar',
  'knowledge',
] as const;

export interface PersistedHudPreferences {
  layoutMode: OfficeLayoutMode;
  activeBottomTab: OfficeHudTabId;
  detachedTab: OfficeHudTabId | null;
  bottomDeckState: OfficeBottomDeckState;
  bottomDeckHeightPx: number;
  cameraPreset: OfficeCameraPreset;
  isRosterOpen: boolean;
  rosterWidthPx: number;
  isInspectorOpen: boolean;
  isMinimapOpen: boolean;
  autoSyncContext: boolean;
  panelOrder: OfficeHudTabId[];
}

const DEFAULT_PREFERENCES: PersistedHudPreferences = {
  layoutMode: 'hud',
  activeBottomTab: 'work-request',
  detachedTab: null,
  bottomDeckState: 'docked',
  bottomDeckHeightPx: 360,
  cameraPreset: 'overview',
  isRosterOpen: true,
  rosterWidthPx: 270,
  isInspectorOpen: true,
  isMinimapOpen: true,
  autoSyncContext: true,
  panelOrder: [...DEFAULT_PANEL_ORDER],
};

function isValidTabId(val: unknown): val is OfficeHudTabId {
  return typeof val === 'string' && (DEFAULT_PANEL_ORDER as readonly string[]).includes(val);
}

export function loadPersistedHudPreferences(): PersistedHudPreferences {
  if (typeof window === 'undefined' || !window.localStorage) {
    return { ...DEFAULT_PREFERENCES, panelOrder: [...DEFAULT_PANEL_ORDER] };
  }
  try {
    const raw = window.localStorage.getItem(HUD_PREFS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES, panelOrder: [...DEFAULT_PANEL_ORDER] };
    const parsed = JSON.parse(raw) as Partial<PersistedHudPreferences>;

    const layoutMode: OfficeLayoutMode =
      parsed.layoutMode === 'classic' || parsed.layoutMode === 'hud' ? parsed.layoutMode : 'hud';
    const activeBottomTab: OfficeHudTabId = isValidTabId(parsed.activeBottomTab)
      ? parsed.activeBottomTab
      : 'work-request';
    const detachedTab: OfficeHudTabId | null = isValidTabId(parsed.detachedTab) ? parsed.detachedTab : null;
    const bottomDeckState: OfficeBottomDeckState =
      parsed.bottomDeckState === 'minimized' ||
      parsed.bottomDeckState === 'docked' ||
      parsed.bottomDeckState === 'maximized'
        ? parsed.bottomDeckState
        : 'docked';
    const bottomDeckHeightPx =
      typeof parsed.bottomDeckHeightPx === 'number' && Number.isFinite(parsed.bottomDeckHeightPx)
        ? Math.max(180, Math.min(720, Math.round(parsed.bottomDeckHeightPx)))
        : 360;
    const cameraPreset: OfficeCameraPreset =
      parsed.cameraPreset === 'overview' ||
      parsed.cameraPreset === 'isometric' ||
      parsed.cameraPreset === 'top-down' ||
      parsed.cameraPreset === 'agent-focus'
        ? parsed.cameraPreset
        : 'overview';
    const isRosterOpen = typeof parsed.isRosterOpen === 'boolean' ? parsed.isRosterOpen : true;
    const rosterWidthPx =
      typeof parsed.rosterWidthPx === 'number' && Number.isFinite(parsed.rosterWidthPx)
        ? Math.max(200, Math.min(420, Math.round(parsed.rosterWidthPx)))
        : 270;
    const isInspectorOpen = typeof parsed.isInspectorOpen === 'boolean' ? parsed.isInspectorOpen : true;
    const isMinimapOpen = typeof parsed.isMinimapOpen === 'boolean' ? parsed.isMinimapOpen : true;
    const autoSyncContext = typeof parsed.autoSyncContext === 'boolean' ? parsed.autoSyncContext : true;

    let panelOrder: OfficeHudTabId[] = [...DEFAULT_PANEL_ORDER];
    if (Array.isArray(parsed.panelOrder)) {
      const validCustom = parsed.panelOrder.filter(isValidTabId);
      const unique = Array.from(new Set([...validCustom, ...DEFAULT_PANEL_ORDER]));
      if (unique.length === DEFAULT_PANEL_ORDER.length) {
        panelOrder = unique;
      }
    }

    return {
      layoutMode,
      activeBottomTab,
      detachedTab,
      bottomDeckState,
      bottomDeckHeightPx,
      cameraPreset,
      isRosterOpen,
      rosterWidthPx,
      isInspectorOpen,
      isMinimapOpen,
      autoSyncContext,
      panelOrder,
    };
  } catch {
    return { ...DEFAULT_PREFERENCES, panelOrder: [...DEFAULT_PANEL_ORDER] };
  }
}

export function savePersistedHudPreferences(prefs: PersistedHudPreferences): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.setItem(HUD_PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore storage quota or private-mode errors
  }
}

/**
 * Classifies an agent's operational state strictly from backend evidence.
 * Never fabricates activity or heartbeats in LIVE mode.
 */
export function deriveAgentOperationalCategory(agent: AgentIdentity): {
  category: OperationalStateCategory;
  label: string;
  reason: string;
} {
  const hasBlockingExecution = Boolean(
    agent.executionHistory?.some(
      (exec) => exec.isBudgetExceeded || exec.isNoProgressRetry || Boolean(exec.alert) || Boolean(exec.error)
    )
  );
  if (hasBlockingExecution) {
    return {
      category: 'BLOQUEADO',
      label: 'Bloqueado',
      reason: 'Alerta de ejecución registrada (presupuesto, bucle sin progreso o error).',
    };
  }

  const hasActiveAssignment = agent.currentAssignments.some((asg) => asg.status === 'ACTIVE' && Boolean(asg.taskId));
  if (agent.status === 'BUSY' && hasActiveAssignment) {
    return {
      category: 'ACTIVO',
      label: 'Activo (Ejecutando)',
      reason: 'Ejecución en curso con lease vigente acreditado.',
    };
  }

  const hasPendingOrUnknownVigency = agent.currentAssignments.some((asg) => asg.status === 'UNKNOWN');
  if (hasPendingOrUnknownVigency || agent.operationalState === 'ASIGNADO') {
    return {
      category: 'PENDIENTE',
      label: 'Pendiente / Sin lease',
      reason: 'Asignación observada pendiente de lease vigente o confirmación de despacho.',
    };
  }

  if (
    agent.status === 'OFFLINE' ||
    agent.status === 'DECOMMISSIONED' ||
    agent.heartbeatStatus === 'UNAVAILABLE' ||
    agent.operationalState === 'NO_DISPONIBLE'
  ) {
    return {
      category: 'DESCONECTADO',
      label: 'Desconectado',
      reason: 'Sin conexión operativa o dado de baja en el registro.',
    };
  }

  if (
    agent.status === 'IDLE' &&
    (agent.heartbeatStatus === 'HEALTHY' ||
      agent.operationalState === 'REGISTRADO' ||
      agent.operationalState === 'CONECTADO' ||
      agent.operationalState === 'INACTIVO')
  ) {
    return {
      category: 'INACTIVO',
      label: 'Inactivo (En espera)',
      reason: 'Registrado sin tarea en ejecución activa en este instante.',
    };
  }

  return {
    category: 'DESCONOCIDO',
    label: 'Desconocido',
    reason: 'Sin telemetría de presencia ni lease de ejecución verificable en el backend.',
  };
}

/**
 * Checks if a keyboard event target is an interactive or editable element
 * so global HUD hotkeys never interfere with typing, forms, or button activation.
 */
export function isInteractiveOrEditableElement(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toUpperCase();
  if (
    tagName === 'INPUT' ||
    tagName === 'TEXTAREA' ||
    tagName === 'SELECT' ||
    tagName === 'BUTTON' ||
    tagName === 'A' ||
    target.isContentEditable
  ) {
    return true;
  }
  const role = target.getAttribute('role');
  if (
    role &&
    ['textbox', 'combobox', 'searchbox', 'button', 'link', 'menuitem', 'tab', 'slider', 'spinbutton'].includes(role)
  ) {
    return true;
  }
  if (target.closest('input, textarea, select, button, a, [contenteditable="true"]')) {
    return true;
  }
  return false;
}

export interface UseOfficeHudStateOptions {
  initialViewMode: OfficeViewMode;
  availableTabs: OfficeHudTabId[];
  agents: AgentIdentity[];
}

export function useOfficeHudState({ initialViewMode, availableTabs, agents }: UseOfficeHudStateOptions) {
  const [prefs, setPrefs] = useState<PersistedHudPreferences>(() => loadPersistedHudPreferences());
  const [viewMode, setViewMode] = useState<OfficeViewMode>(initialViewMode);
  const [selectedRoomId, setSelectedRoomId] = useState<string>('unit-unassigned');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [contextProjectId, setContextProjectId] = useState<string | null>(null);
  const [zenMode, setZenMode] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'STANDING' | 'EPHEMERAL'>('ALL');
  const [reducedMotion, setReducedMotion] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }
    return false;
  });

  const [cameraState, setCameraState] = useState<CameraViewState>({
    angle: 35,
    elevation: 42,
    distance: 24,
    targetX: 0,
    targetZ: 0,
  });

  // Persist preferences whenever they change
  useEffect(() => {
    savePersistedHudPreferences(prefs);
  }, [prefs]);

  // Listen to prefers-reduced-motion media query
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const listener = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, []);

  // Ensure activeBottomTab is valid within availableTabs when availableTabs is non-empty
  const effectiveActiveTab: OfficeHudTabId | null = useMemo(() => {
    if (availableTabs.length === 0) return null;
    if (availableTabs.includes(prefs.activeBottomTab)) {
      return prefs.activeBottomTab;
    }
    const orderedAvailable = prefs.panelOrder.filter((id) => availableTabs.includes(id));
    return orderedAvailable[0] || availableTabs[0];
  }, [availableTabs, prefs.activeBottomTab, prefs.panelOrder]);

  const effectiveDetachedTab: OfficeHudTabId | null = useMemo(() => {
    if (!prefs.detachedTab || !availableTabs.includes(prefs.detachedTab)) return null;
    if (prefs.detachedTab === effectiveActiveTab) return null;
    return prefs.detachedTab;
  }, [availableTabs, effectiveActiveTab, prefs.detachedTab]);

  const setLayoutMode = useCallback((layoutMode: OfficeLayoutMode) => {
    setPrefs((prev) => ({ ...prev, layoutMode }));
  }, []);

  const setActiveBottomTab = useCallback((tab: OfficeHudTabId) => {
    setPrefs((prev) => ({
      ...prev,
      activeBottomTab: tab,
      bottomDeckState: prev.bottomDeckState === 'minimized' ? 'docked' : prev.bottomDeckState,
    }));
  }, []);

  const setDetachedTab = useCallback((tab: OfficeHudTabId | null) => {
    setPrefs((prev) => ({ ...prev, detachedTab: tab }));
  }, []);

  const setBottomDeckState = useCallback((bottomDeckState: OfficeBottomDeckState) => {
    setPrefs((prev) => ({ ...prev, bottomDeckState }));
  }, []);

  const setBottomDeckHeightPx = useCallback((height: number) => {
    const clamped = Math.max(180, Math.min(720, Math.round(height)));
    setPrefs((prev) => ({
      ...prev,
      bottomDeckHeightPx: clamped,
      bottomDeckState: prev.bottomDeckState === 'minimized' ? 'docked' : prev.bottomDeckState,
    }));
  }, []);

  const setCameraPreset = useCallback((cameraPreset: OfficeCameraPreset) => {
    setPrefs((prev) => ({ ...prev, cameraPreset }));
  }, []);

  const setIsRosterOpen = useCallback((isRosterOpen: boolean | ((prev: boolean) => boolean)) => {
    setPrefs((prev) => ({
      ...prev,
      isRosterOpen: typeof isRosterOpen === 'function' ? isRosterOpen(prev.isRosterOpen) : isRosterOpen,
    }));
  }, []);

  const setRosterWidthPx = useCallback((width: number) => {
    const clamped = Math.max(200, Math.min(420, Math.round(width)));
    setPrefs((prev) => ({ ...prev, rosterWidthPx: clamped }));
  }, []);

  const setIsInspectorOpen = useCallback((isInspectorOpen: boolean | ((prev: boolean) => boolean)) => {
    setPrefs((prev) => ({
      ...prev,
      isInspectorOpen: typeof isInspectorOpen === 'function' ? isInspectorOpen(prev.isInspectorOpen) : isInspectorOpen,
    }));
  }, []);

  const setIsMinimapOpen = useCallback((isMinimapOpen: boolean | ((prev: boolean) => boolean)) => {
    setPrefs((prev) => ({
      ...prev,
      isMinimapOpen: typeof isMinimapOpen === 'function' ? isMinimapOpen(prev.isMinimapOpen) : isMinimapOpen,
    }));
  }, []);

  const setAutoSyncContext = useCallback((autoSyncContext: boolean) => {
    setPrefs((prev) => ({ ...prev, autoSyncContext }));
  }, []);

  const moveTabOrder = useCallback((tabId: OfficeHudTabId, direction: 'left' | 'right') => {
    setPrefs((prev) => {
      const order = [...prev.panelOrder];
      const idx = order.indexOf(tabId);
      if (idx === -1) return prev;
      const targetIdx = direction === 'left' ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= order.length) return prev;
      const temp = order[idx];
      order[idx] = order[targetIdx];
      order[targetIdx] = temp;
      return { ...prev, panelOrder: order };
    });
  }, []);

  const resetHudPreferences = useCallback(() => {
    setPrefs({ ...DEFAULT_PREFERENCES, panelOrder: [...DEFAULT_PANEL_ORDER] });
    setZenMode(false);
  }, []);

  // Centralized room selection
  const selectRoom = useCallback((roomId: string) => {
    setSelectedRoomId(roomId);
    setSelectedAgentId(null);
  }, []);

  // Centralized agent selection with operational context sync (Improvement #1)
  const selectAgent = useCallback(
    (agentId: string | null) => {
      setSelectedAgentId(agentId);
      if (agentId) {
        setPrefs((prev) => ({ ...prev, isInspectorOpen: true }));
        const agent = agents.find((a) => a.id === agentId);
        if (agent) {
          if (agent.unitId && agent.unitId !== selectedRoomId) {
            setSelectedRoomId(agent.unitId);
          }
          if (prefs.autoSyncContext) {
            const activeAssignment =
              agent.currentAssignments.find((asg) => asg.status === 'ACTIVE') || agent.currentAssignments[0];
            const execProject = agent.executionHistory?.[0]?.projectId;
            const grantProject = agent.grants?.find((g) => g.active)?.projectId;
            const resolvedProjectId = activeAssignment?.projectId || execProject || grantProject || null;
            if (resolvedProjectId) {
              setContextProjectId(resolvedProjectId);
            }
          }
        }
      }
    },
    [agents, prefs.autoSyncContext, selectedRoomId]
  );

  return {
    // Persistent HUD preferences
    layoutMode: prefs.layoutMode,
    setLayoutMode,
    activeBottomTab: effectiveActiveTab,
    setActiveBottomTab,
    detachedTab: effectiveDetachedTab,
    setDetachedTab,
    bottomDeckState: prefs.bottomDeckState,
    setBottomDeckState,
    bottomDeckHeightPx: prefs.bottomDeckHeightPx,
    setBottomDeckHeightPx,
    cameraPreset: prefs.cameraPreset,
    setCameraPreset,
    isRosterOpen: prefs.isRosterOpen,
    setIsRosterOpen,
    rosterWidthPx: prefs.rosterWidthPx,
    setRosterWidthPx,
    isInspectorOpen: prefs.isInspectorOpen,
    setIsInspectorOpen,
    isMinimapOpen: prefs.isMinimapOpen,
    setIsMinimapOpen,
    autoSyncContext: prefs.autoSyncContext,
    setAutoSyncContext,
    panelOrder: prefs.panelOrder,
    moveTabOrder,
    resetHudPreferences,

    // Live interactive state
    viewMode,
    setViewMode,
    selectedRoomId,
    setSelectedRoomId,
    selectRoom,
    selectedAgentId,
    setSelectedAgentId,
    selectAgent,
    contextProjectId,
    setContextProjectId,
    zenMode,
    setZenMode,
    cameraState,
    setCameraState,
    searchQuery,
    setSearchQuery,
    typeFilter,
    setTypeFilter,
    reducedMotion,
    setReducedMotion,
  };
}
