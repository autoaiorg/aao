import React, { useEffect, useRef, useState } from 'react';
import type { AgentIdentity } from '../../../domain/models';
import { ThreeOfficeScene } from '../engine/ThreeOfficeScene';

export interface Office3DCanvasProps {
  agents: AgentIdentity[];
  selectedRoomId: string;
  selectedAgentId: string | null;
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onFallbackTo2D: () => void;
  reducedMotion?: boolean;
}

export interface WebGLCanvasHandle {
  rotate: (degrees: number) => void;
  zoom: (factor: number) => void;
  reset: () => void;
}

function checkWebGLSupport(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    return !!gl;
  } catch {
    return false;
  }
}

export const Office3DCanvas = React.forwardRef<WebGLCanvasHandle, Office3DCanvasProps>(
  (
    {
      agents,
      selectedRoomId,
      selectedAgentId,
      onSelectRoom,
      onSelectAgent,
      onFallbackTo2D,
      reducedMotion = false,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const sceneRef = useRef<ThreeOfficeScene | null>(null);
    const [webglSupported] = useState(checkWebGLSupport);
    const [hoveredInfo, setHoveredInfo] = useState<{ type: 'room' | 'agent'; id: string } | null>(null);

    // Imperative controls exposed via ref
    React.useImperativeHandle(ref, () => ({
      rotate: (degrees: number) => {
        sceneRef.current?.rotateCamera(degrees);
      },
      zoom: (factor: number) => {
        sceneRef.current?.zoomCamera(factor);
      },
      reset: () => {
        sceneRef.current?.resetCamera();
      },
    }));

    // Initialize ThreeOfficeScene
    useEffect(() => {
      const container = containerRef.current;
      if (!container || !webglSupported) return;

      const scene = new ThreeOfficeScene(container, {
        reducedMotion,
        callbacks: {
          onSelectRoom: (roomId) => onSelectRoom(roomId),
          onSelectAgent: (agentId) => onSelectAgent(agentId),
          onHoverObject: (info) => setHoveredInfo(info),
        },
      });

      sceneRef.current = scene;
      scene.updateAgents(agents);
      scene.selectRoom(selectedRoomId, false);
      if (selectedAgentId) {
        scene.selectAgent(selectedAgentId);
      }

      const resizeObserver = new ResizeObserver(() => {
        scene.resize();
      });
      resizeObserver.observe(container);

      return () => {
        resizeObserver.disconnect();
        scene.dispose();
        sceneRef.current = null;
      };
    }, [webglSupported, reducedMotion]); // Re-create on webgl or motion changes

    // Update agents in existing scene
    useEffect(() => {
      sceneRef.current?.updateAgents(agents);
    }, [agents]);

    // Update room selection in existing scene
    useEffect(() => {
      sceneRef.current?.selectRoom(selectedRoomId);
    }, [selectedRoomId]);

    // Update agent selection in existing scene
    useEffect(() => {
      sceneRef.current?.selectAgent(selectedAgentId);
    }, [selectedAgentId]);

    if (!webglSupported) {
      return (
        <div
          role="region"
          aria-label="Aviso de aceleración gráfica no disponible"
          style={{
            minHeight: '480px',
            backgroundColor: 'var(--bg-muted, #0f172a)',
            border: '1px solid var(--border-subtle, #334155)',
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '32px',
            textAlign: 'center',
            gap: '16px',
          }}
        >
          <div style={{ fontSize: '32px' }} aria-hidden="true">🖥️</div>
          <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary, #f8fafc)' }}>
            Acelerador 3D WebGL no disponible en este dispositivo
          </h3>
          <p style={{ maxWidth: '500px', margin: 0, fontSize: '13px', color: 'var(--text-secondary, #94a3b8)', lineHeight: 1.5 }}>
            El entorno no dispone de contexto WebGL habilitado. Puede recorrer toda la organización, departamentos y agentes utilizando el plano 2D accesible equivalente.
          </p>
          <button
            type="button"
            onClick={onFallbackTo2D}
            style={{
              padding: '10px 18px',
              backgroundColor: 'var(--color-primary, #3b82f6)',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '13px',
            }}
          >
            Abrir Plano 2D Accesible
          </button>
        </div>
      );
    }

    return (
      <div
        style={{
          position: 'relative',
          width: '100%',
          minHeight: '520px',
          backgroundColor: '#0a1628',
          borderRadius: '16px',
          overflow: 'hidden',
          border: '1px solid #1e293b',
          boxShadow: 'var(--shadow-md, 0 4px 6px -1px rgba(0, 0, 0, 0.1))',
        }}
      >
        <div
          ref={containerRef}
          style={{ width: '100%', height: '520px', display: 'block', touchAction: 'none' }}
          tabIndex={0}
          role="region"
          aria-label="Vista 3D interactiva de la Oficina Virtual de AAO. Arrastre para rotar, rueda del ratón para zoom, y haga clic en un departamento o avatar para seleccionarlo."
        />

        {/* Hover hint badge */}
        {hoveredInfo && (
          <div
            style={{
              position: 'absolute',
              top: '12px',
              left: '12px',
              padding: '6px 12px',
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid #38bdf8',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 600,
              color: '#38bdf8',
              pointerEvents: 'none',
              backdropFilter: 'blur(4px)',
            }}
          >
            {hoveredInfo.type === 'agent' ? '👤 Agente detectado' : '🏢 Departamento detectado'} · Clic para seleccionar
          </div>
        )}

        {/* Navigation legend overlay */}
        <div
          style={{
            position: 'absolute',
            bottom: '12px',
            left: '12px',
            padding: '8px 12px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid #334155',
            borderRadius: '8px',
            fontSize: '11px',
            color: '#94a3b8',
            pointerEvents: 'none',
            lineHeight: 1.4,
          }}
        >
          <span>🖱️ Arrastrar para rotar</span> · <span>🔍 Scroll para zoom</span> · <span>🎯 Clic en sala o agente</span>
        </div>
      </div>
    );
  }
);

Office3DCanvas.displayName = 'Office3DCanvas';
