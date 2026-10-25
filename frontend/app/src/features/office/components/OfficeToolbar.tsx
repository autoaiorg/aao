import React from 'react';
import { OFFICE_ROOMS, type OfficeViewMode } from '../types';

export interface OfficeToolbarProps {
  viewMode: OfficeViewMode;
  onViewModeChange: (mode: OfficeViewMode) => void;
  selectedRoomId: string;
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
}

export const OfficeToolbar: React.FC<OfficeToolbarProps> = ({
  viewMode,
  onViewModeChange,
  selectedRoomId,
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
}) => {
  return (
    <div
      role="toolbar"
      aria-label="Barra de herramientas de la Oficina Virtual"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '14px 16px',
        backgroundColor: 'var(--bg-surface, #0f172a)',
        border: '1px solid var(--border-subtle, #334155)',
        borderRadius: '12px',
      }}
    >
      {/* Row 1: Mode Toggle & Camera controls */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
        {/* View Mode Toggle */}
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            aria-pressed={viewMode === '3d'}
            onClick={() => onViewModeChange('3d')}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: viewMode === '3d' ? '1px solid #38bdf8' : '1px solid #334155',
              backgroundColor: viewMode === '3d' ? '#0369a1' : '#1e293b',
              color: '#ffffff',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🌐</span> Vista 3D (WebGL)
          </button>
          <button
            type="button"
            aria-pressed={viewMode === '2d'}
            onClick={() => onViewModeChange('2d')}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: viewMode === '2d' ? '1px solid #38bdf8' : '1px solid #334155',
              backgroundColor: viewMode === '2d' ? '#0369a1' : '#1e293b',
              color: '#ffffff',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🗺️</span> Plano 2D Accesible
          </button>
        </div>

        {/* 3D Camera Controls */}
        {viewMode === '3d' && (
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => onRotateCamera?.(-25)}
              aria-label="Rotar cámara a la izquierda"
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#cbd5e1',
                fontSize: '12px',
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
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#cbd5e1',
                fontSize: '12px',
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
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#cbd5e1',
                fontSize: '12px',
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
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#cbd5e1',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              − Zoom
            </button>
            <button
              type="button"
              onClick={() => onResetCamera?.()}
              aria-label="Restablecer posición de cámara"
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid #475569',
                backgroundColor: '#0f172a',
                color: '#38bdf8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Restablecer
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
              padding: '6px 10px',
              borderRadius: '6px',
              border: reducedMotion ? '1px solid #eab308' : '1px solid #334155',
              backgroundColor: reducedMotion ? '#713f12' : '#1e293b',
              color: reducedMotion ? '#fef08a' : '#94a3b8',
              fontSize: '11px',
              cursor: 'pointer',
            }}
          >
            {reducedMotion ? '⚡ Movimiento Reducido (Activo)' : '🏃 Animación Estándar'}
          </button>
        </div>
      </div>

      {/* Row 2: Department Quick Select Chips & Filters */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '10px', alignItems: 'center', borderTop: '1px solid #1e293b', paddingTop: '10px' }}>
        {/* Department Chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600, marginRight: '4px' }}>
            Departamentos:
          </span>
          {OFFICE_ROOMS.map((room) => {
            const isSelected = selectedRoomId === room.id;
            return (
              <button
                key={room.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => onSelectRoom(room.id)}
                style={{
                  padding: '5px 10px',
                  borderRadius: '6px',
                  border: isSelected ? `2px solid ${room.accentColor}` : '1px solid #334155',
                  backgroundColor: isSelected ? '#1e3a8a' : '#1e293b',
                  color: isSelected ? '#ffffff' : '#cbd5e1',
                  fontSize: '12px',
                  fontWeight: isSelected ? 600 : 500,
                  cursor: 'pointer',
                }}
              >
                [{room.code}] {room.name.split(' ')[0]}
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
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#0a1628',
              color: '#f8fafc',
              fontSize: '12px',
              width: '180px',
            }}
          />

          <select
            value={typeFilter}
            onChange={(e) => onTypeFilterChange(e.target.value as 'ALL' | 'STANDING' | 'EPHEMERAL')}
            aria-label="Filtrar por tipo de agente"
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#0a1628',
              color: '#f8fafc',
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
