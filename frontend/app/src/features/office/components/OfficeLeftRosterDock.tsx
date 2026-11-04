import React from 'react';
import type { AgentIdentity, OrgUnit } from '../../../domain/models';
import { OFFICE_ROOMS } from '../types';
import { deriveAgentOperationalCategory } from '../useOfficeHudState';

export interface OfficeLeftRosterDockProps {
  isOpen: boolean;
  onToggleOpen: () => void;
  widthPx: number;
  onWidthChange: (width: number) => void;
  units: OrgUnit[];
  agents: AgentIdentity[];
  selectedRoomId: string;
  selectedAgentId: string | null;
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string | null) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  typeFilter: 'ALL' | 'STANDING' | 'EPHEMERAL';
  onTypeFilterChange: (f: 'ALL' | 'STANDING' | 'EPHEMERAL') => void;
  autoSyncContext: boolean;
  onToggleAutoSyncContext: (enabled: boolean) => void;
  contextProjectId: string | null;
}

const CATEGORY_BADGE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  ACTIVO: { bg: 'rgba(6, 78, 59, 0.9)', border: '#10b981', text: '#a7f3d0' },
  BLOQUEADO: { bg: 'rgba(127, 29, 29, 0.9)', border: '#f87171', text: '#fecaca' },
  PENDIENTE: { bg: 'rgba(120, 53, 15, 0.9)', border: '#f59e0b', text: '#fde68a' },
  INACTIVO: { bg: 'rgba(30, 41, 59, 0.85)', border: '#64748b', text: '#cbd5e1' },
  DESCONOCIDO: { bg: 'rgba(15, 23, 42, 0.85)', border: '#475569', text: '#94a3b8' },
  DESCONECTADO: { bg: 'rgba(51, 65, 85, 0.7)', border: '#475569', text: '#94a3b8' },
  HISTORICO: { bg: 'rgba(30, 41, 59, 0.85)', border: '#64748b', text: '#cbd5e1' },
};

export const OfficeLeftRosterDock: React.FC<OfficeLeftRosterDockProps> = ({
  isOpen,
  onToggleOpen,
  widthPx,
  onWidthChange,
  units,
  agents,
  selectedRoomId,
  onSelectRoom,
  searchQuery,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  autoSyncContext,
  onToggleAutoSyncContext,
  contextProjectId,
}) => {
  return (
    <section
      aria-label="Muelle táctico de departamentos y plantilla"
      className={`aao-hud-roster aao-hud-glass ${isOpen ? 'is-open' : 'is-collapsed'}`}
      style={{
        width: isOpen ? `${widthPx}px` : '42px',
      }}
    >
      {/* Header with Collapse & Width Controls */}
      <div className="aao-hud-roster__header">
        {isOpen && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span aria-hidden="true">🛰️</span>
            <strong style={{ fontSize: '12px', color: '#f8fafc', letterSpacing: '0.3px' }}>
              SECTORES Y AGENTES
            </strong>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {isOpen && (
            <>
              <button
                type="button"
                className="aao-hud-btn"
                style={{ padding: '2px 6px', fontSize: '11px' }}
                onClick={() => onWidthChange(widthPx - 30)}
                aria-label="Estrechar panel de sectores"
                title="Estrechar panel"
              >
                −
              </button>
              <button
                type="button"
                className="aao-hud-btn"
                style={{ padding: '2px 6px', fontSize: '11px' }}
                onClick={() => onWidthChange(widthPx + 30)}
                aria-label="Ensanchar panel de sectores"
                title="Ensanchar panel"
              >
                +
              </button>
            </>
          )}
          <button
            type="button"
            className="aao-hud-btn"
            style={{ padding: '2px 8px', fontSize: '11px' }}
            aria-expanded={isOpen}
            aria-label={isOpen ? 'Comprimir muelle de sectores' : 'Expandir muelle de sectores'}
            onClick={onToggleOpen}
          >
            {isOpen ? '◀ Comprimir' : '☰'}
          </button>
        </div>
      </div>

      <div className="aao-hud-roster__body" style={{ display: isOpen ? 'flex' : 'none' }}>
        {/* Department Quick Chips (Always accessible for keyboard & tests) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase' }}>
            Departamentos ({units.length}):
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
            {units.map((unit, index) => {
              const visual =
                OFFICE_ROOMS.find((room) => room.id === unit.id) || OFFICE_ROOMS[index % OFFICE_ROOMS.length];
              const isSelected = selectedRoomId === unit.id;
              return (
                <button
                  key={unit.id}
                  type="button"
                  aria-label={`[${unit.code}] ${unit.name}`}
                  aria-pressed={isSelected}
                  onClick={() => onSelectRoom(unit.id)}
                  style={{
                    padding: '4px 9px',
                    borderRadius: 'var(--radius-md, 6px)',
                    border: isSelected
                      ? `2px solid ${visual?.accentColor || '#38bdf8'}`
                      : '1px solid rgba(148, 163, 184, 0.28)',
                    backgroundColor: isSelected ? 'rgba(2, 132, 199, 0.35)' : 'rgba(30, 41, 59, 0.75)',
                    color: '#f8fafc',
                    fontSize: '11px',
                    fontWeight: isSelected ? 700 : 500,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <strong style={{ color: visual?.accentColor || '#38bdf8', marginRight: '4px' }}>
                    [{unit.code}]
                  </strong>
                  <span>{isOpen ? unit.name : ''}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Search & Type Filter */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <input
            type="text"
            placeholder="Buscar agente o capacidad..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Buscar agentes en la oficina"
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              backgroundColor: 'rgba(15, 23, 42, 0.9)',
              color: '#f8fafc',
              fontSize: '12px',
              width: '100%',
            }}
          />

          <select
            value={typeFilter}
            onChange={(e) => onTypeFilterChange(e.target.value as 'ALL' | 'STANDING' | 'EPHEMERAL')}
            aria-label="Filtrar por tipo de agente"
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              backgroundColor: 'rgba(15, 23, 42, 0.9)',
              color: '#f8fafc',
              fontSize: '12px',
              width: '100%',
            }}
          >
            <option value="ALL">Todos los agentes</option>
            <option value="STANDING">Solo Plantilla Fija</option>
            <option value="EPHEMERAL">Solo Temporales</option>
          </select>
        </div>

        {/* Contextual Sync Toggle (Improvement #1) */}
        {isOpen && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              padding: '6px 8px',
              borderRadius: '6px',
              background: 'rgba(30, 41, 59, 0.65)',
              border: '1px solid rgba(56, 189, 248, 0.22)',
            }}
          >
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '11px',
                fontWeight: 600,
                color: '#e2e8f0',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={autoSyncContext}
                onChange={(e) => onToggleAutoSyncContext(e.target.checked)}
              />
              <span>Sincronizar consola con selección</span>
            </label>
            {contextProjectId && (
              <span style={{ fontSize: '10px', color: '#7dd3fc' }}>
                Contexto vinculado: <strong>{contextProjectId}</strong>
              </span>
            )}
          </div>
        )}

        {/* Operational Summary for Filtered Agents */}
        {isOpen && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase' }}>
              Estado de plantilla filtrada ({agents.length}):
            </span>
            {agents.length === 0 ? (
              <span style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic' }}>
                Sin agentes que coincidan con el filtro.
              </span>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '4px' }}>
                {(['ACTIVO', 'BLOQUEADO', 'PENDIENTE', 'INACTIVO', 'DESCONOCIDO', 'DESCONECTADO', 'HISTORICO'] as const).map(
                  (cat) => {
                    const count = agents.filter((a) => deriveAgentOperationalCategory(a).category === cat).length;
                    const styleBadge = CATEGORY_BADGE_COLORS[cat] || CATEGORY_BADGE_COLORS.DESCONOCIDO;
                    return (
                      <div
                        key={cat}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '4px 7px',
                          borderRadius: '6px',
                          backgroundColor: styleBadge.bg,
                          border: `1px solid ${styleBadge.border}`,
                          color: styleBadge.text,
                          fontSize: '10px',
                          fontWeight: 700,
                        }}
                      >
                        <span>{cat}</span>
                        <span>{count}</span>
                      </div>
                    );
                  }
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};
