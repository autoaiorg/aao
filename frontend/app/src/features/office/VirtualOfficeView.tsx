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
        gap: '20px',
      }}
    >
      {/* 1. Header with Status Banner */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h2 style={{ margin: '0 0 4px 0', fontSize: '22px', fontWeight: 700, color: 'var(--text-primary, #f8fafc)' }}>
              Oficina Virtual 3D · AAO
            </h2>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary, #94a3b8)' }}>
              Entorno espacial tridimensional para la inspección visual de departamentos, puestos y telemetría de agentes.
            </p>
          </div>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              style={{
                padding: '8px 14px',
                borderRadius: '8px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#f8fafc',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              ↻ Actualizar
            </button>
          )}
        </div>

        {/* Status Callout Banner */}
        <div
          role="status"
          style={{
            padding: '10px 16px',
            borderRadius: '8px',
            backgroundColor: isDemo ? 'rgba(234, 179, 8, 0.12)' : data ? 'rgba(59, 130, 246, 0.12)' : 'rgba(100, 116, 139, 0.12)',
            border: isDemo ? '1px solid rgba(234, 179, 8, 0.3)' : data ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid rgba(100, 116, 139, 0.3)',
            color: isDemo ? '#fef08a' : data ? '#93c5fd' : '#cbd5e1',
            fontSize: '12px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <span aria-hidden="true">{isDemo ? '⚠' : data ? 'ℹ' : '🔒'}</span>
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
          gap: '20px',
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
