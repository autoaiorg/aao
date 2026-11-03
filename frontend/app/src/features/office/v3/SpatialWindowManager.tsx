import React from 'react';
import type { SpatialWindowId, SpatialWindowState } from './useSpatialWindowManager';

export interface SpatialWindowManagerProps {
  windows: Record<SpatialWindowId, SpatialWindowState>;
  onToggleWindow: (id: SpatialWindowId) => void;
  onCloseWindow: (id: SpatialWindowId) => void;
  onFocusWindow: (id: SpatialWindowId) => void;
  onToggleMinimizeWindow: (id: SpatialWindowId) => void;
  onToggleMaximizeWindow: (id: SpatialWindowId) => void;
  onSelectAtrium: () => void;
  requiresConstitution?: boolean;
  windowNodes: Record<SpatialWindowId, React.ReactNode>;
}

const WINDOW_POSITIONS: Record<SpatialWindowId, { top: string; left: string; width: string }> = {
  'organization-explorer': { top: '96px', left: '290px', width: 'min(640px, 52vw)' },
  'constitution-center': { top: '112px', left: '340px', width: 'min(720px, 58vw)' },
  'entity-inspector': { top: '128px', left: '390px', width: 'min(620px, 50vw)' },
  'spatial-workflows': { top: '144px', left: '320px', width: 'min(600px, 48vw)' },
  'operational-timeline': { top: '160px', left: '360px', width: 'min(620px, 50vw)' },
};

const ORDERED_WINDOW_IDS: SpatialWindowId[] = [
  'organization-explorer',
  'constitution-center',
  'entity-inspector',
  'spatial-workflows',
  'operational-timeline',
];

export const SpatialWindowManager: React.FC<SpatialWindowManagerProps> = ({
  windows,
  onToggleWindow,
  onCloseWindow,
  onFocusWindow,
  onToggleMinimizeWindow,
  onToggleMaximizeWindow,
  onSelectAtrium,
  requiresConstitution = false,
  windowNodes,
}) => {
  return (
    <>
      {/* V3 Enterprise Spatial Launcher Bar */}
      <div
        role="toolbar"
        aria-label="Escritorio Espacial Multiaplicación Empresa Viva"
        data-testid="v3-spatial-launcher-bar"
        style={{
          position: 'fixed',
          top: 'calc(var(--header-height, 48px) + 52px)',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 28,
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '5px 10px',
          borderRadius: '999px',
          background: 'rgba(10, 22, 40, 0.88)',
          backdropFilter: 'blur(14px)',
          border: '1px solid rgba(56, 189, 248, 0.35)',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
          maxWidth: '94vw',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          onClick={onSelectAtrium}
          className="aao-hud-btn"
          style={{ padding: '3px 9px', fontSize: '11px', fontWeight: 700 }}
        >
          🏛️ Atrio Central
        </button>

        {ORDERED_WINDOW_IDS.map((id) => {
          const win = windows[id];
          const isConstitution = id === 'constitution-center';
          return (
            <button
              key={id}
              type="button"
              data-testid={`launcher-btn-${id}`}
              aria-pressed={win.isOpen && !win.isMinimized}
              onClick={() => onToggleWindow(id)}
              className="aao-hud-btn"
              style={{
                padding: '3px 9px',
                fontSize: '11px',
                fontWeight: 700,
                background:
                  win.isOpen && !win.isMinimized
                    ? '#0284c7'
                    : isConstitution && requiresConstitution
                    ? 'rgba(245, 158, 11, 0.22)'
                    : undefined,
                color:
                  win.isOpen && !win.isMinimized
                    ? '#f8fafc'
                    : isConstitution && requiresConstitution
                    ? '#fcd34d'
                    : undefined,
                borderColor:
                  isConstitution && requiresConstitution ? 'rgba(245, 158, 11, 0.55)' : undefined,
              }}
            >
              <span aria-hidden="true">{win.icon}</span>{' '}
              {id === 'organization-explorer'
                ? 'Organización y Puestos'
                : id === 'constitution-center'
                ? 'Constitución Organizativa'
                : id === 'entity-inspector'
                ? 'Entidad y Gobierno'
                : id === 'spatial-workflows'
                ? 'Flujos Espaciales'
                : 'Cronología'}
              {win.isOpen && win.isMinimized ? ' (Min)' : ''}
            </button>
          );
        })}
      </div>

      {/* Simultaneous Multi-Window Layer (Preserves mounted children state while open or minimized) */}
      {ORDERED_WINDOW_IDS.map((id) => {
        const win = windows[id];
        if (!win.isOpen) return null;
        const pos = WINDOW_POSITIONS[id];
        return (
          <section
            key={id}
            role="dialog"
            aria-label={win.title}
            data-testid={`spatial-window-${id}`}
            onMouseDown={() => onFocusWindow(id)}
            style={{
              display: 'flex',
              position: 'fixed',
              top: win.isMaximized ? 'calc(var(--header-height, 48px) + 56px)' : pos.top,
              left: win.isMaximized ? '16px' : pos.left,
              width: win.isMaximized ? 'calc(100vw - 32px)' : pos.width,
              maxHeight: win.isMinimized
                ? '40px'
                : win.isMaximized
                ? 'calc(100vh - var(--header-height, 48px) - 72px)'
                : 'min(68vh, 620px)',
              zIndex: win.zIndex,
              flexDirection: 'column',
              background: 'rgba(10, 22, 40, 0.94)',
              backdropFilter: 'blur(18px)',
              border: '1px solid rgba(56, 189, 248, 0.42)',
              borderRadius: '12px',
              boxShadow: '0 20px 44px rgba(0, 0, 0, 0.72)',
              overflow: 'hidden',
            }}
          >
            {/* Window Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '7px 12px',
                background: 'rgba(15, 23, 42, 0.98)',
                borderBottom: win.isMinimized ? 'none' : '1px solid rgba(56, 189, 248, 0.25)',
                flexShrink: 0,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span aria-hidden="true">{win.icon}</span>
                <strong style={{ fontSize: '12px', color: '#f8fafc' }}>{win.title}</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <button
                  type="button"
                  aria-label={`Minimizar ventana ${win.title}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleMinimizeWindow(id);
                  }}
                  className="aao-hud-btn"
                  style={{ padding: '2px 7px', fontSize: '10px' }}
                >
                  {win.isMinimized ? 'Restaurar' : '─'}
                </button>
                <button
                  type="button"
                  aria-label={`Maximizar ventana ${win.title}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleMaximizeWindow(id);
                  }}
                  className="aao-hud-btn"
                  style={{ padding: '2px 7px', fontSize: '10px' }}
                >
                  {win.isMaximized ? '▫' : '⤢'}
                </button>
                <button
                  type="button"
                  aria-label={`Cerrar ventana ${win.title}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onCloseWindow(id);
                  }}
                  className="aao-hud-btn"
                  style={{
                    padding: '2px 7px',
                    fontSize: '10px',
                    color: '#fecaca',
                    borderColor: 'rgba(248, 113, 113, 0.45)',
                  }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Window Body (kept mounted when minimized using display: none so form state is preserved) */}
            <div
              style={{
                display: win.isMinimized ? 'none' : 'block',
                flex: 1,
                overflowY: 'auto',
                padding: '12px 14px',
              }}
            >
              {windowNodes[id]}
            </div>
          </section>
        );
      })}
    </>
  );
};
