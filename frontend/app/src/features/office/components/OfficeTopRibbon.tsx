import React from 'react';
import type {
  AgentIdentity,
  AlertSummary,
  DecisionSummary,
  OrganizationCoverage,
  OrgUnit,
} from '../../../domain/models';
import {
  OFFICE_ROOMS,
  type OfficeCameraPreset,
  type OfficeLayoutMode,
  type OfficeViewMode,
} from '../types';
import { deriveAgentOperationalCategory } from '../useOfficeHudState';

export interface OfficeTopRibbonProps {
  isDemo: boolean;
  hasLiveStructure: boolean;
  coverage?: OrganizationCoverage;
  units: OrgUnit[];
  agents: AgentIdentity[];
  selectedRoomId: string;
  onSelectRoom: (roomId: string) => void;
  viewMode: OfficeViewMode;
  onViewModeChange: (mode: OfficeViewMode) => void;
  allow3D: boolean;
  layoutMode: OfficeLayoutMode;
  onLayoutModeChange: (mode: OfficeLayoutMode) => void;
  cameraPreset: OfficeCameraPreset;
  onSelectCameraPreset: (preset: OfficeCameraPreset) => void;
  onRotateCamera: (deg: number) => void;
  onZoomCamera: (factor: number) => void;
  onResetCamera: () => void;
  reducedMotion: boolean;
  onToggleReducedMotion: () => void;
  zenMode: boolean;
  onToggleZenMode: () => void;
  onRefresh?: () => void;
  criticalAlerts: AlertSummary[];
  pendingCeoDecisions: DecisionSummary[];
  onOpenAlerts?: () => void;
  onOpenDecisions?: () => void;
}

export const OfficeTopRibbon: React.FC<OfficeTopRibbonProps> = ({
  isDemo,
  hasLiveStructure,
  coverage,
  units,
  agents,
  selectedRoomId,
  viewMode,
  onViewModeChange,
  allow3D,
  layoutMode,
  onLayoutModeChange,
  cameraPreset,
  onSelectCameraPreset,
  onRotateCamera,
  onZoomCamera,
  onResetCamera,
  reducedMotion,
  onToggleReducedMotion,
  zenMode,
  onToggleZenMode,
  onRefresh,
  criticalAlerts,
  pendingCeoDecisions,
  onOpenAlerts,
  onOpenDecisions,
}) => {
  const canOpen3D = isDemo || allow3D;
  const activeUnit = units.find((u) => u.id === selectedRoomId);
  const activeRoomVisual = OFFICE_ROOMS.find((r) => r.id === selectedRoomId);

  // Operational state breakdown (truthful backend classification)
  const stateCounts = React.useMemo(() => {
    const counts = {
      ACTIVO: 0,
      INACTIVO: 0,
      BLOQUEADO: 0,
      PENDIENTE: 0,
      DESCONOCIDO: 0,
      DESCONECTADO: 0,
    };
    for (const agent of agents) {
      const { category } = deriveAgentOperationalCategory(agent);
      counts[category] += 1;
    }
    return counts;
  }, [agents]);

  return (
    <header className="aao-hud-top-ribbon aao-hud-glass" aria-label="Cabecera táctica de la Oficina Virtual">
      {/* Row 1: Title, Status Pills, Operational Telemetry & Layout/Zen Controls */}
      <div className="aao-hud-top-ribbon__row">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f8fafc', letterSpacing: '0.2px' }}>
            Oficina Virtual 3D · AAO
          </h2>

          <span className={`aao-hud-pill ${isDemo ? 'aao-hud-pill--demo' : hasLiveStructure ? 'aao-hud-pill--live' : 'aao-hud-pill--warning'}`}>
            <span aria-hidden="true">{isDemo ? '⚠' : hasLiveStructure ? '●' : '🔒'}</span>
            <span>{isDemo ? 'DEMO · SIMULACIÓN' : hasLiveStructure ? 'LIVE · PERSISTIDO' : 'LIVE · SIN NÚCLEO'}</span>
          </span>

          <span className="aao-hud-pill" title="Sector departamental seleccionado">
            <strong style={{ color: activeRoomVisual?.accentColor || '#38bdf8' }}>
              [{activeUnit?.code || activeRoomVisual?.code || 'DESC'}]
            </strong>
            <span>{activeUnit?.name || activeRoomVisual?.name || '«Departamento desconocido»'}</span>
          </span>

          {/* Truthful Operational States Breakdown */}
          <div
            role="group"
            aria-label="Resumen de estados operativos de agentes"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}
          >
            <span className="aao-hud-pill" title="Agentes con ejecución activa y lease vigente">
              ⚡ Activos: <strong>{stateCounts.ACTIVO}</strong>
            </span>
            {stateCounts.BLOQUEADO > 0 && (
              <span className="aao-hud-pill aao-hud-pill--critical" title="Agentes con alerta de bloqueo o presupuesto">
                ⛔ Bloqueados: <strong>{stateCounts.BLOQUEADO}</strong>
              </span>
            )}
            {stateCounts.PENDIENTE > 0 && (
              <span className="aao-hud-pill aao-hud-pill--warning" title="Agentes con asignación pendiente o vigencia desconocida">
                ⏳ Pendientes: <strong>{stateCounts.PENDIENTE}</strong>
              </span>
            )}
            <span className="aao-hud-pill" title="Agentes inactivos / en espera">
              ⏸ Inactivos: <strong>{stateCounts.INACTIVO}</strong>
            </span>
            {stateCounts.DESCONOCIDO > 0 && (
              <span className="aao-hud-pill" title="Agentes sin telemetría de presencia verificada">
                ○ Desconocidos: <strong>{stateCounts.DESCONOCIDO}</strong>
              </span>
            )}
            {stateCounts.DESCONECTADO > 0 && (
              <span className="aao-hud-pill" title="Agentes desconectados o fuera de servicio">
                🔌 Desconectados: <strong>{stateCounts.DESCONECTADO}</strong>
              </span>
            )}
          </div>
        </div>

        {/* Right: Critical Alerts, Layout Switcher, Zen Mode & Refresh */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {criticalAlerts.length > 0 && (
            <button
              type="button"
              onClick={onOpenAlerts}
              className="aao-hud-btn"
              style={{
                background: 'rgba(127, 29, 29, 0.92)',
                borderColor: '#f87171',
                color: '#fef2f2',
              }}
              aria-label={`Alertas críticas activas: ${criticalAlerts.length}`}
            >
              🚨 {criticalAlerts.length} Alerta{criticalAlerts.length === 1 ? '' : 's'} Crítica{criticalAlerts.length === 1 ? '' : 's'}
            </button>
          )}

          {pendingCeoDecisions.length > 0 && (
            <button
              type="button"
              onClick={onOpenDecisions}
              className="aao-hud-btn"
              style={{
                background: 'rgba(120, 53, 15, 0.92)',
                borderColor: '#f59e0b',
                color: '#fef3c7',
              }}
              aria-label={`Decisiones reservadas al CEO pendientes: ${pendingCeoDecisions.length}`}
            >
              ⚖️ {pendingCeoDecisions.length} Decisión{pendingCeoDecisions.length === 1 ? '' : 'es'} CEO
            </button>
          )}

          <button
            type="button"
            className={`aao-hud-btn ${layoutMode === 'hud' ? 'aao-hud-btn--active' : ''}`}
            aria-pressed={layoutMode === 'hud'}
            onClick={() => onLayoutModeChange(layoutMode === 'hud' ? 'classic' : 'hud')}
            title="Alternar entre Modo Videojuego (HUD 3D) y Modo Clásico (Tarjetas apiladas)"
          >
            {layoutMode === 'hud' ? '🎮 HUD Videojuego' : '📋 Vista Clásica'}
          </button>

          <button
            type="button"
            className={`aao-hud-btn ${zenMode ? 'aao-hud-btn--active' : ''}`}
            aria-pressed={zenMode}
            onClick={onToggleZenMode}
            title="Ocultar o mostrar paneles del HUD (Atajo: tecla Z)"
          >
            🧘 Modo Zen [Z]
          </button>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="aao-hud-btn"
              aria-label="Actualizar datos de la oficina"
            >
              ↻ Actualizar
            </button>
          )}
        </div>
      </div>

      {/* Row 2: Honest Status Banner (WCAG 2.2 AA & Veracity Contract) */}
      <div
        role="status"
        style={{
          padding: '6px 12px',
          borderRadius: 'var(--radius-md, 6px)',
          backgroundColor: isDemo
            ? 'rgba(124, 45, 18, 0.75)'
            : hasLiveStructure
            ? 'rgba(12, 74, 110, 0.75)'
            : 'rgba(120, 53, 15, 0.78)',
          border: isDemo
            ? '1px solid #f97316'
            : hasLiveStructure
            ? '1px solid #38bdf8'
            : '1px solid #f59e0b',
          color: '#f8fafc',
          fontSize: '11px',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          lineHeight: 1.35,
        }}
      >
        <span aria-hidden="true">{isDemo ? '⚠' : hasLiveStructure ? 'ℹ' : '🔒'}</span>
        <span>
          {isDemo
            ? 'DEMO · SIMULACIÓN 3D ACTIVA · Todos los departamentos, agentes y asignaciones son sintéticos y no representan datos de producción.'
            : hasLiveStructure
            ? `LIVE · ESTRUCTURA PERSISTIDA · Plano 2D y escena 3D derivados de las unidades y agentes recibidos del backend. La geometría es una representación visual; estado y actividad solo reflejan evidencia proyectada. ${
                coverage
                  ? coverage.notes ||
                    (coverage.isPartial
                      ? `Cobertura parcial (${coverage.failedProjects} errores en ${coverage.totalProjects} proyectos).`
                      : `Cobertura completa (${coverage.inspectedProjects}/${coverage.totalProjects} proyectos).`)
                  : 'La presencia operativa está condicionada a telemetría verificada en tiempo real.'
              }`
            : 'SIN CONEXIÓN AL NÚCLEO EN LIVE (F3/F4) · No hay estructura operativa disponible. DEMO, si se selecciona, se identifica por separado como simulación.'}
        </span>
      </div>

      {/* Row 3: Camera & Viewport Toolbar */}
      <div
        role="toolbar"
        aria-label="Barra de herramientas de la Oficina Virtual"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '8px',
          paddingTop: '4px',
          borderTop: '1px solid rgba(148, 163, 184, 0.2)',
        }}
      >
        {/* View Mode Switcher */}
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <button
            type="button"
            aria-pressed={viewMode === '3d'}
            onClick={() => onViewModeChange('3d')}
            disabled={!canOpen3D}
            className={`aao-hud-btn ${viewMode === '3d' ? 'aao-hud-btn--active' : ''}`}
            title={!canOpen3D ? 'La vista 3D requiere unidades organizativas recibidas del backend.' : undefined}
          >
            <span aria-hidden="true">🌐</span> Vista 3D (WebGL)
          </button>
          <button
            type="button"
            aria-pressed={viewMode === '2d'}
            onClick={() => onViewModeChange('2d')}
            className={`aao-hud-btn ${viewMode === '2d' ? 'aao-hud-btn--active' : ''}`}
          >
            <span aria-hidden="true">🗺️</span> Plano 2D Accesible
          </button>
        </div>

        {/* 3D Camera Controls & Presets */}
        {viewMode === '3d' && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => {
                onSelectCameraPreset('overview');
                onResetCamera();
              }}
              aria-label="Restablecer posición de cámara y centrar oficina"
              className={`aao-hud-btn ${cameraPreset === 'overview' ? 'aao-hud-btn--active' : ''}`}
            >
              <span aria-hidden="true">⟲</span> Vista General
            </button>
            <button
              type="button"
              onClick={() => onSelectCameraPreset('isometric')}
              className={`aao-hud-btn ${cameraPreset === 'isometric' ? 'aao-hud-btn--active' : ''}`}
              aria-label="Cámara isométrica"
            >
              📐 Isométrica
            </button>
            <button
              type="button"
              onClick={() => onSelectCameraPreset('top-down')}
              className={`aao-hud-btn ${cameraPreset === 'top-down' ? 'aao-hud-btn--active' : ''}`}
              aria-label="Cámara cenital"
            >
              🦅 Cenital
            </button>
            <button
              type="button"
              onClick={() => onSelectCameraPreset('agent-focus')}
              className={`aao-hud-btn ${cameraPreset === 'agent-focus' ? 'aao-hud-btn--active' : ''}`}
              aria-label="Enfocar cámara en selección"
            >
              🎯 Enfoque
            </button>

            <span style={{ opacity: 0.35, padding: '0 2px' }}>|</span>

            <button
              type="button"
              onClick={() => onRotateCamera(-25)}
              aria-label="Rotar cámara a la izquierda"
              className="aao-hud-btn"
            >
              ↶ Rotar
            </button>
            <button
              type="button"
              onClick={() => onRotateCamera(25)}
              aria-label="Rotar cámara a la derecha"
              className="aao-hud-btn"
            >
              Rotar ↷
            </button>
            <button
              type="button"
              onClick={() => onZoomCamera(0.85)}
              aria-label="Acercar zoom"
              className="aao-hud-btn"
            >
              + Zoom
            </button>
            <button
              type="button"
              onClick={() => onZoomCamera(1.15)}
              aria-label="Alejar zoom"
              className="aao-hud-btn"
            >
              − Zoom
            </button>
          </div>
        )}

        {/* Reduced Motion Toggle */}
        <div>
          <button
            type="button"
            aria-pressed={reducedMotion}
            onClick={onToggleReducedMotion}
            className="aao-hud-btn"
          >
            {reducedMotion ? '⚡ Movimiento Reducido (Activo)' : '🏃 Animación Estándar'}
          </button>
        </div>
      </div>
    </header>
  );
};
