import { useState, useCallback, useEffect } from 'react';

export type SpatialWindowId =
  | 'organization-explorer'
  | 'constitution-center'
  | 'entity-inspector'
  | 'spatial-workflows'
  | 'operational-timeline';

export interface SpatialWindowState {
  id: SpatialWindowId;
  title: string;
  icon: string;
  isOpen: boolean;
  isMinimized: boolean;
  isMaximized: boolean;
  zIndex: number;
}

const STORAGE_KEY = 'aao_office_v3_spatial_windows_v1';

const DEFAULT_WINDOWS: Record<SpatialWindowId, SpatialWindowState> = {
  'organization-explorer': {
    id: 'organization-explorer',
    title: 'Explorador Organizativo y Puestos',
    icon: '🏛️',
    isOpen: false,
    isMinimized: false,
    isMaximized: false,
    zIndex: 31,
  },
  'constitution-center': {
    id: 'constitution-center',
    title: 'Centro de Constitución Organizativa',
    icon: '⚖️',
    isOpen: false,
    isMinimized: false,
    isMaximized: false,
    zIndex: 32,
  },
  'entity-inspector': {
    id: 'entity-inspector',
    title: 'Inspector de Entidades y Gobierno Contextual',
    icon: '🔎',
    isOpen: false,
    isMinimized: false,
    isMaximized: false,
    zIndex: 33,
  },
  'spatial-workflows': {
    id: 'spatial-workflows',
    title: 'Flujo de Trabajo Espacial y Dependencias',
    icon: '🔗',
    isOpen: false,
    isMinimized: false,
    isMaximized: false,
    zIndex: 34,
  },
  'operational-timeline': {
    id: 'operational-timeline',
    title: 'Observabilidad y Cronología Operativa',
    icon: '⏱️',
    isOpen: false,
    isMinimized: false,
    isMaximized: false,
    zIndex: 35,
  },
};

function loadInitialWindows(): Record<SpatialWindowId, SpatialWindowState> {
  if (typeof window === 'undefined') return DEFAULT_WINDOWS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_WINDOWS;
    const parsed = JSON.parse(raw) as Partial<Record<SpatialWindowId, Partial<SpatialWindowState>>>;
    const merged = { ...DEFAULT_WINDOWS };
    (Object.keys(DEFAULT_WINDOWS) as SpatialWindowId[]).forEach((id) => {
      const saved = parsed[id];
      if (saved && typeof saved === 'object') {
        merged[id] = {
          ...DEFAULT_WINDOWS[id],
          isOpen: Boolean(saved.isOpen),
          isMinimized: Boolean(saved.isMinimized),
          isMaximized: Boolean(saved.isMaximized),
          zIndex: typeof saved.zIndex === 'number' ? saved.zIndex : DEFAULT_WINDOWS[id].zIndex,
        };
      }
    });
    return merged;
  } catch {
    return DEFAULT_WINDOWS;
  }
}

export function useSpatialWindowManager() {
  const [windows, setWindows] = useState<Record<SpatialWindowId, SpatialWindowState>>(loadInitialWindows);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(windows));
    } catch {
      // Ignore storage quota errors
    }
  }, [windows]);

  const openWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => {
      const maxZ = Math.max(...Object.values(prev).map((w) => w.zIndex), 30);
      return {
        ...prev,
        [id]: {
          ...prev[id],
          isOpen: true,
          isMinimized: false,
          zIndex: maxZ + 1,
        },
      };
    });
  }, []);

  const closeWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        isOpen: false,
        isMinimized: false,
        isMaximized: false,
      },
    }));
  }, []);

  const toggleWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => {
      const current = prev[id];
      const maxZ = Math.max(...Object.values(prev).map((w) => w.zIndex), 30);
      if (current.isOpen && !current.isMinimized) {
        return {
          ...prev,
          [id]: {
            ...current,
            isOpen: false,
          },
        };
      }
      return {
        ...prev,
        [id]: {
          ...current,
          isOpen: true,
          isMinimized: false,
          zIndex: maxZ + 1,
        },
      };
    });
  }, []);

  const focusWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => {
      const current = prev[id];
      if (!current.isOpen) return prev;
      const maxZ = Math.max(...Object.values(prev).map((w) => w.zIndex), 30);
      if (current.zIndex === maxZ && !current.isMinimized) return prev;
      return {
        ...prev,
        [id]: {
          ...current,
          isMinimized: false,
          zIndex: maxZ + 1,
        },
      };
    });
  }, []);

  const toggleMinimizeWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => {
      const current = prev[id];
      const maxZ = Math.max(...Object.values(prev).map((w) => w.zIndex), 30);
      const nextMinimized = !current.isMinimized;
      return {
        ...prev,
        [id]: {
          ...current,
          isMinimized: nextMinimized,
          isMaximized: nextMinimized ? false : current.isMaximized,
          zIndex: nextMinimized ? current.zIndex : maxZ + 1,
        },
      };
    });
  }, []);

  const toggleMaximizeWindow = useCallback((id: SpatialWindowId) => {
    setWindows((prev) => {
      const current = prev[id];
      const maxZ = Math.max(...Object.values(prev).map((w) => w.zIndex), 30);
      return {
        ...prev,
        [id]: {
          ...current,
          isMinimized: false,
          isMaximized: !current.isMaximized,
          zIndex: maxZ + 1,
        },
      };
    });
  }, []);

  const closeAllWindows = useCallback(() => {
    setWindows((prev) => {
      const next = { ...prev };
      (Object.keys(next) as SpatialWindowId[]).forEach((id) => {
        next[id] = { ...next[id], isOpen: false, isMinimized: false, isMaximized: false };
      });
      return next;
    });
  }, []);

  return {
    windows,
    openWindow,
    closeWindow,
    toggleWindow,
    focusWindow,
    toggleMinimizeWindow,
    toggleMaximizeWindow,
    closeAllWindows,
  };
}
