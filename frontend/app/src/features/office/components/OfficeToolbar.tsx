import React from 'react';
import type { OrgUnit } from '../../../domain/models';
import { OFFICE_ROOMS, type OfficeViewMode } from '../types';

export interface OfficeToolbarProps {
  viewMode: OfficeViewMode;
  onViewModeChange: (mode: OfficeViewMode) => void;
  selectedRoomId: string;
  units: OrgUnit[];
  onSelectRoom: (roomId: string) => void;
  onRotateCamera?: (degrees: number) => void;
  onZoomCamera?: (factor: number) => void;
  onResetCamera?: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  typeFilter: 'ALL' | 'STANDING' | 'EPHEMERAL';
  onTypeFilterChange: (filter: 'ALL' | 'STANDING' | 'EPHEMERAL') => void;
  reducedMotion: boolean;
  onToggleReducedMotion: () => void;
  isDemo?: boolean;
  allow3D?: boolean;
}

export const OfficeToolbar: React.FC<OfficeToolbarProps> = ({
  viewMode,
  onViewModeChange,
  selectedRoomId,
  units,
  onSelectRoom,
  onRotateCamera,
  onZoomCamera,
  onResetCamera,
  searchQuery,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  reducedMotion,
  onToggleReducedMotion,
  isDemo = false,
  allow3D = false,
}) => {
  const canOpen3D = isDemo || allow3D;
  return (
    <div
      role="toolbar"
      aria-label="Barra de herramientas de la Oficina Virtual"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3, 12px)',
        padding: 'var(--space-4, 16px)',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg, 12px)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      {/* Row 1: Mode Toggle, Camera Controls & Accessibility */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          gap: 'var(--space-3, 12px)',
          alignItems: 'center',
        }}
      >
        {/* View Mode Switcher */}
        <div style={{ display: 'flex', gap: 'var(--space-2, 8px)' }}>
          <button
            type="button"
            aria-pressed={viewMode === '3d'}
            onClick={() => onViewModeChange('3d')}
            disabled={!canOpen3D}
            title={!canOpen3D ? 'La vista 3D requiere unidades organizativas recibidas del backend.' : undefined}
            style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-md, 8px)',
              border: viewMode === '3d' ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
              backgroundColor: viewMode === '3d' ? 'var(--accent)' : 'var(--bg-muted)',
              color: viewMode === '3d' ? 'var(--text-inverse)' : 'var(--text-primary)',
              fontWeight: 600,
              fontSize: '13px',
              cursor: canOpen3D ? 'pointer' : 'not-allowed',
              opacity: canOpen3D ? 1 : 0.55,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.15s ease',
            }}
          >
            <span aria-hidden="true">🌐</span> Vista 3D (WebGL)
          </button>
          <button
            type="button"
            aria-pressed={viewMode === '2d'}
            onClick={() => onViewModeChange('2d')}
            style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-md, 8px)',
              border: viewMode === '2d' ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
              backgroundColor: viewMode === '2d' ? 'var(--accent)' : 'var(--bg-muted)',
              color: viewMode === '2d' ? 'var(--text-inverse)' : 'var(--text-primary)',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.15s ease',
            }}
          >
            <span aria-hidden="true">🗺️</span> Plano 2D Accesible
          </button>
        </div>

        {/* 3D Camera Controls */}
        {viewMode === '3d' && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => onRotateCamera?.(-25)}
              aria-label="Rotar cámara a la izquierda"
              style={{
                padding: '6px 12px',
                borderRadius: 'var(--radius-md, 6px)',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-muted)',
                color: 'var(--text-primary)',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              ↶ Rotar
            </button>
            <button
              type="button"
              onClick={() => onRotateCamera?.(25)}
              aria-label="Rotar cámara a la derecha"
              style={{
                padding: '6px 12px',
                borderRadius: 'var(--radius-md, 6px)',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-muted)',
                color: 'var(--text-primary)',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Rotar ↷
            </button>
            <button
              type="button"
              onClick={() => onZoomCamera?.(0.85)}
              aria-label="Acercar zoom"
              style={{
                padding: '6px 12px',
                borderRadius: 'var(--radius-md, 6px)',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-muted)',
                color: 'var(--text-primary)',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              + Zoom
            </button>
            <button
              type="button"
              onClick={() => onZoomCamera?.(1.15)}
              aria-label="Alejar zoom"
              style={{
                padding: '6px 12px',
                borderRadius: 'var(--radius-md, 6px)',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-muted)',
                color: 'var(--text-primary)',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              − Zoom
            </button>
            <button
              type="button"
              onClick={() => onResetCamera?.()}
              aria-label="Restablecer posición de cámara y centrar oficina"
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius-md, 6px)',
                border: '1px solid var(--accent)',
                backgroundColor: 'var(--accent-light)',
                color: 'var(--accent)',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span aria-hidden="true">⟲</span> Vista General
            </button>
          </div>
        )}

        {/* Motion Accessibility Toggle */}
        <div>
          <button
            type="button"
            aria-pressed={reducedMotion}
            onClick={onToggleReducedMotion}
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius-md, 6px)',
              border: reducedMotion
                ? '1px solid var(--status-warning-border)'
                : '1px solid var(--border-subtle)',
              backgroundColor: reducedMotion
                ? 'var(--status-warning-bg)'
                : 'var(--bg-muted)',
              color: reducedMotion
                ? 'var(--status-warning-text)'
                : 'var(--text-secondary)',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {reducedMotion ? '⚡ Movimiento Reducido (Activo)' : '🏃 Animación Estándar'}
          </button>
        </div>
      </div>

      {/* Row 2: Department Quick Select Chips & Filters */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          gap: 'var(--space-3, 10px)',
          alignItems: 'center',
          borderTop: '1px solid var(--border-subtle)',
          paddingTop: 'var(--space-3, 10px)',
        }}
      >
        {/* Department Chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, marginRight: '4px' }}>
            Departamentos:
          </span>
          {units.map((unit, index) => {
            const visual = OFFICE_ROOMS.find((room) => room.id === unit.id) || OFFICE_ROOMS[index % OFFICE_ROOMS.length];
            const isSelected = selectedRoomId === unit.id;
            return (
              <button
                key={unit.id}
                type="button"
                aria-label={`[${unit.code}] ${unit.name}`}
                aria-pressed={isSelected}
                onClick={() => onSelectRoom(unit.id)}
                style={{
                  padding: '5px 11px',
                  borderRadius: 'var(--radius-md, 6px)',
                  border: isSelected ? `2px solid ${visual?.accentColor || '#64748b'}` : '1px solid var(--border-subtle)',
                  backgroundColor: isSelected ? 'var(--accent-light)' : 'var(--bg-muted)',
                  color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontSize: '12px',
                  fontWeight: isSelected ? 700 : 500,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <strong style={{ color: visual?.accentColor || '#64748b', marginRight: '4px' }}>[{unit.code}]</strong>
                <span>{unit.name}</span>
              </button>
            );
          })}
        </div>

        {/* Search & Agent Type Filter */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Buscar agente o capacidad..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Buscar agentes en la oficina"
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid var(--border-strong)',
              backgroundColor: 'var(--bg-app)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              width: '190px',
            }}
          />

          <select
            value={typeFilter}
            onChange={(e) => onTypeFilterChange(e.target.value as 'ALL' | 'STANDING' | 'EPHEMERAL')}
            aria-label="Filtrar por tipo de agente"
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid var(--border-strong)',
              backgroundColor: 'var(--bg-app)',
              color: 'var(--text-primary)',
              fontSize: '12px',
            }}
          >
            <option value="ALL">Todos los agentes</option>
            <option value="STANDING">Solo Plantilla Fija</option>
            <option value="EPHEMERAL">Solo Temporales</option>
          </select>
        </div>
      </div>
    </div>
  );
};
