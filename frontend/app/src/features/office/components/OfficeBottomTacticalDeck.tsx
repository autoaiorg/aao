import React, { useRef } from 'react';
import type {
  OfficeBottomDeckState,
  OfficeHudTabId,
} from '../types';

export interface HudModuleDescriptor {
  id: OfficeHudTabId;
  label: string;
  icon: string;
  shortcutKey: string;
  node: React.ReactNode;
}

export interface OfficeBottomTacticalDeckProps {
  modules: HudModuleDescriptor[];
  panelOrder: OfficeHudTabId[];
  activeTab: OfficeHudTabId | null;
  detachedTab: OfficeHudTabId | null;
  deckState: OfficeBottomDeckState;
  deckHeightPx: number;
  contextProjectId: string | null;
  selectedAgentName: string | null;
  onSelectTab: (tab: OfficeHudTabId) => void;
  onSetDetachedTab: (tab: OfficeHudTabId | null) => void;
  onSetDeckState: (state: OfficeBottomDeckState) => void;
  onSetDeckHeightPx: (height: number) => void;
  onMoveTabOrder: (tab: OfficeHudTabId, direction: 'left' | 'right') => void;
}

export const OfficeBottomTacticalDeck: React.FC<OfficeBottomTacticalDeckProps> = ({
  modules,
  panelOrder,
  activeTab,
  detachedTab,
  deckState,
  deckHeightPx,
  contextProjectId,
  selectedAgentName,
  onSelectTab,
  onSetDetachedTab,
  onSetDeckState,
  onSetDeckHeightPx,
  onMoveTabOrder,
}) => {
  const dragStartY = useRef<number | null>(null);
  const dragStartHeight = useRef<number>(deckHeightPx);

  const orderedModules = React.useMemo(() => {
    const map = new Map(modules.map((m) => [m.id, m]));
    const result: HudModuleDescriptor[] = [];
    for (const id of panelOrder) {
      const mod = map.get(id);
      if (mod) result.push(mod);
    }
    for (const mod of modules) {
      if (!result.some((r) => r.id === mod.id)) {
        result.push(mod);
      }
    }
    return result;
  }, [modules, panelOrder]);

  if (orderedModules.length === 0) {
    return (
      <section
        aria-label="Consola táctica inferior"
        className="aao-hud-bottom-deck aao-hud-glass"
        style={{ height: '42px' }}
      >
        <div className="aao-hud-bottom-deck__bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#94a3b8' }}>
            <span aria-hidden="true">🎮</span>
            <span>
              Consola operativa en espera · Los módulos de ejecución, conversación y evidencias sólo se habilitan con puertos LIVE autenticados.
            </span>
          </div>
        </div>
      </section>
    );
  }

  const resolvedHeight =
    deckState === 'minimized'
      ? '46px'
      : deckState === 'maximized'
      ? '76vh'
      : `${deckHeightPx}px`;

  const handleResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragStartY.current = e.clientY;
    dragStartHeight.current = deckHeightPx;
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handleResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStartY.current === null) return;
    const deltaY = dragStartY.current - e.clientY;
    onSetDeckHeightPx(dragStartHeight.current + deltaY);
  };

  const handleResizePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStartY.current !== null) {
      dragStartY.current = null;
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const dockedModules = orderedModules.filter((m) => m.id !== detachedTab);
  const activeModule =
    dockedModules.find((m) => m.id === activeTab) || dockedModules[0] || orderedModules[0];

  return (
    <section
      aria-label="Consola táctica inferior"
      className="aao-hud-bottom-deck aao-hud-glass"
      style={{ height: resolvedHeight }}
    >
      {/* Drag Resize Handle */}
      {deckState !== 'minimized' && (
        <div
          className="aao-hud-bottom-deck__resize-handle"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Arrastrar para redimensionar la altura de la consola táctica"
          onPointerDown={handleResizePointerDown}
          onPointerMove={handleResizePointerMove}
          onPointerUp={handleResizePointerUp}
        />
      )}

      {/* Top Tab & Controls Bar */}
      <div className="aao-hud-bottom-deck__bar">
        {/* Module Tabs */}
        <div className="aao-hud-bottom-deck__tabs" role="tablist" aria-label="Módulos de la consola táctica">
          {orderedModules.map((mod, idx) => {
            const isDetached = detachedTab === mod.id;
            const isActive = !isDetached && activeModule?.id === mod.id && deckState !== 'minimized';
            return (
              <button
                key={mod.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => {
                  if (isDetached) {
                    onSetDetachedTab(null);
                    onSelectTab(mod.id);
                    return;
                  }
                  if (activeModule?.id === mod.id && deckState !== 'minimized') {
                    onSetDeckState('minimized');
                  } else {
                    onSelectTab(mod.id);
                  }
                }}
                className={`aao-hud-tab ${isActive ? 'aao-hud-tab--active' : ''} ${
                  isDetached ? 'aao-hud-tab--detached' : ''
                }`}
              >
                <span aria-hidden="true">{mod.icon}</span>
                <span>{mod.label}</span>
                <span className="aao-hud-tab__key" aria-hidden="true">
                  {idx + 1}
                </span>
              </button>
            );
          })}
        </div>

        {/* Context Badge + Reorder + Detach + Size Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {(selectedAgentName || contextProjectId) && (
            <span className="aao-hud-pill" title="Contexto operativo sincronizado con la selección 3D">
              🎯 {selectedAgentName || 'Sector'}
              {contextProjectId ? ` · Proyecto: ${contextProjectId}` : ''}
            </span>
          )}

          {activeModule && deckState !== 'minimized' && (
            <>
              <button
                type="button"
                className="aao-hud-btn"
                style={{ padding: '3px 7px', fontSize: '11px' }}
                onClick={() => onMoveTabOrder(activeModule.id, 'left')}
                aria-label={`Mover pestaña ${activeModule.label} a la izquierda`}
                title="Mover pestaña a la izquierda"
              >
                ◀
              </button>
              <button
                type="button"
                className="aao-hud-btn"
                style={{ padding: '3px 7px', fontSize: '11px' }}
                onClick={() => onMoveTabOrder(activeModule.id, 'right')}
                aria-label={`Mover pestaña ${activeModule.label} a la derecha`}
                title="Mover pestaña a la derecha"
              >
                ▶
              </button>

              {orderedModules.length > 1 && (
                <button
                  type="button"
                  className={`aao-hud-btn ${detachedTab === activeModule.id ? 'aao-hud-btn--active' : ''}`}
                  style={{ padding: '3px 9px', fontSize: '11px' }}
                  onClick={() => {
                    if (detachedTab === activeModule.id) {
                      onSetDetachedTab(null);
                    } else {
                      const nextPrimary = orderedModules.find((m) => m.id !== activeModule.id);
                      onSetDetachedTab(activeModule.id);
                      if (nextPrimary) onSelectTab(nextPrimary.id);
                    }
                  }}
                  aria-label={
                    detachedTab === activeModule.id
                      ? `Reacoplar ventana ${activeModule.label}`
                      : `Desacoplar ${activeModule.label} en ventana secundaria`
                  }
                >
                  ⧉ {detachedTab === activeModule.id ? 'Reacoplar' : 'Desacoplar ventana'}
                </button>
              )}

              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#cbd5e1' }}>
                <span className="sr-only">Altura de consola</span>
                <input
                  type="range"
                  min={180}
                  max={680}
                  step={20}
                  value={deckHeightPx}
                  aria-label="Redimensionar altura de consola"
                  onChange={(e) => onSetDeckHeightPx(Number(e.target.value))}
                  style={{ width: '64px', accentColor: '#38bdf8' }}
                />
              </label>
            </>
          )}

          <button
            type="button"
            className={`aao-hud-btn ${deckState === 'minimized' ? 'aao-hud-btn--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: '11px' }}
            aria-label="Minimizar consola táctica"
            onClick={() => onSetDeckState('minimized')}
          >
            ─ Minimizar
          </button>
          <button
            type="button"
            className={`aao-hud-btn ${deckState === 'docked' ? 'aao-hud-btn--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: '11px' }}
            aria-label="Acoplar consola táctica"
            onClick={() => onSetDeckState('docked')}
          >
            ▫ Acoplar
          </button>
          <button
            type="button"
            className={`aao-hud-btn ${deckState === 'maximized' ? 'aao-hud-btn--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: '11px' }}
            aria-label="Maximizar consola táctica"
            onClick={() => onSetDeckState(deckState === 'maximized' ? 'docked' : 'maximized')}
          >
            ⤢ Maximizar
          </button>
        </div>
      </div>

      {/* Persistent Module Bodies (kept in a single stable React list so state is preserved on tab switch & detach!) */}
      <div
        className="aao-hud-bottom-deck__content"
        style={{
          display: deckState === 'minimized' && !detachedTab ? 'none' : 'grid',
          gridTemplateColumns: detachedTab && deckState !== 'minimized' ? 'minmax(0, 1fr) minmax(0, 1fr)' : 'minmax(0, 1fr)',
          gap: '14px',
        }}
      >
        {orderedModules.map((mod) => {
          const isDetached = mod.id === detachedTab;
          const isCurrentDocked = !isDetached && activeModule?.id === mod.id && deckState !== 'minimized';
          const isVisible = isDetached || isCurrentDocked;

          return (
            <div
              key={mod.id}
              role={isDetached ? 'region' : 'tabpanel'}
              aria-label={isDetached ? `Ventana secundaria desacoplada: ${mod.label}` : `Módulo ${mod.label}`}
              className={isDetached ? 'aao-hud-detached-window' : undefined}
              style={{
                display: isVisible ? 'flex' : 'none',
                flexDirection: 'column',
                width: '100%',
              }}
            >
              {isDetached && (
                <div className="aao-hud-detached-window__header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 700 }}>
                    <span aria-hidden="true">{mod.icon}</span>
                    <span>{mod.label} (Ventana Desacoplada)</span>
                  </div>
                  <button
                    type="button"
                    className="aao-hud-btn"
                    style={{ padding: '2px 8px', fontSize: '11px' }}
                    aria-label={`Cerrar ventana desacoplada ${mod.label}`}
                    onClick={() => onSetDetachedTab(null)}
                  >
                    ✕ Reacoplar
                  </button>
                </div>
              )}
              <div className={isDetached ? 'aao-hud-detached-window__body' : undefined}>
                {mod.node}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
