import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import type { VirtualOfficeViewProps, OfficeViewMode } from './types';
import { OfficeToolbar } from './components/OfficeToolbar';
import { Office3DCanvas, type WebGLCanvasHandle } from './components/Office3DCanvas';
import { Office2DPlan } from './components/Office2DPlan';
import { OfficeContextSidebar } from './components/OfficeContextSidebar';

export const VirtualOfficeView: React.FC<VirtualOfficeViewProps> = ({
  organization,
  onNavigate,
  onRefresh,
}) => {
  const [viewMode, setViewMode] = useState<OfficeViewMode>('3d');
  const [selectedRoomId, setSelectedRoomId] = useState<string>('unit-exec');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'STANDING' | 'EPHEMERAL'>('ALL');
  const [reducedMotion, setReducedMotion] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }
    return false;
  });

  const canvas3DRef = useRef<WebGLCanvasHandle>(null);

  // Detect media query changes for reduced motion
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const listener = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, []);

  const data = organization.kind === 'ready' ? organization.data : null;
  const isDemo = organization.kind === 'ready' && organization.origin === 'demo';

  const units = useMemo(() => data?.units || [], [data]);
  const allAgents = useMemo(() => data?.agents || [], [data]);

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

  const handleSelectRoom = useCallback((roomId: string) => {
    setSelectedRoomId(roomId);
    setSelectedAgentId(null);
  }, []);

  const handleSelectAgent = useCallback(
    (agentId: string | null) => {
      setSelectedAgentId(agentId);
      if (agentId) {
        const agent = allAgents.find((a) => a.id === agentId);
        if (agent && agent.unitId !== selectedRoomId) {
          setSelectedRoomId(agent.unitId);
        }
      }
    },
    [allAgents, selectedRoomId]
  );

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-5, 20px)',
      }}
    >
      {/* 1. Header with Status Banner */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2, 8px)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2 style={{ margin: '0 0 4px 0', fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Oficina Virtual 3D · AAO
            </h2>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)' }}>
              Entorno espacial tridimensional para la inspección visual de departamentos, puestos y telemetría de agentes.
            </p>
          </div>

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

        {/* Status Callout Banner with WCAG 2.2 AA Contrast */}
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
              ? 'LIVE · ESTRUCTURA RECIBIDA · La presencia operativa está condicionada a telemetría verificada en tiempo real.'
              : 'SIN CONEXIÓN AL NÚCLEO EN LIVE (F3/F4) · Los edificios son ilustrativos. Conmute a DEMO para explorar la escena 3D.'}
          </span>
        </div>
      </div>

      {/* 2. Unified Toolbar (Mode, Camera, Search, Filter) */}
      <OfficeToolbar
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        selectedRoomId={selectedRoomId}
        onSelectRoom={handleSelectRoom}
        onRotateCamera={(deg) => canvas3DRef.current?.rotate(deg)}
        onZoomCamera={(factor) => canvas3DRef.current?.zoom(factor)}
        onResetCamera={() => canvas3DRef.current?.reset()}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        reducedMotion={reducedMotion}
        onToggleReducedMotion={() => setReducedMotion((prev) => !prev)}
      />

      {/* 3. Main Workspace Grid: (3D WebGL Canvas OR 2D Plan) + Context Inspector Sidebar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 340px',
          gap: 'var(--space-5, 20px)',
          alignItems: 'start',
        }}
      >
        {/* Left: Spatial Viewport */}
        <div>
          {viewMode === '3d' ? (
            <Office3DCanvas
              ref={canvas3DRef}
              agents={filteredAgents}
              selectedRoomId={selectedRoomId}
              selectedAgentId={selectedAgentId}
              onSelectRoom={handleSelectRoom}
              onSelectAgent={handleSelectAgent}
              onFallbackTo2D={() => setViewMode('2d')}
              reducedMotion={reducedMotion}
            />
          ) : (
            <Office2DPlan
              units={units}
              agents={filteredAgents}
              selectedRoomId={selectedRoomId}
              selectedAgentId={selectedAgentId}
              onSelectRoom={handleSelectRoom}
              onSelectAgent={handleSelectAgent}
              isDemo={isDemo}
            />
          )}
        </div>

        {/* Right: Contextual Inspector Sidebar */}
        <OfficeContextSidebar
          selectedRoomId={selectedRoomId}
          selectedAgentId={selectedAgentId}
          units={units}
          agents={filteredAgents}
          onSelectAgent={handleSelectAgent}
          onNavigate={onNavigate}
          isDemo={isDemo}
        />
      </div>
    </div>
  );
};
