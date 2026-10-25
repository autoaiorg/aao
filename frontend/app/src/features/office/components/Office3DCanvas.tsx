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
    }, [webglSupported, reducedMotion]);

    // Update agents in existing scene
    useEffect(() => {
      sceneRef.current?.updateAgents(agents);
    }, [agents]);

    // Update room selection in existing scene
    useEffect(() => {
      sceneRef.current?.selectRoom(selectedRoomId);
    }, [selectedRoomId]);

    // Update active agent selection in existing scene
    useEffect(() => {
      sceneRef.current?.selectAgent(selectedAgentId);
    }, [selectedAgentId]);

    if (!webglSupported) {
      return (
        <div
          role="region"
          aria-label="Aviso de ausencia de WebGL"
          style={{
            minHeight: '520px',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg, 16px)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '32px 24px',
            textAlign: 'center',
            gap: '16px',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ fontSize: '36px' }} aria-hidden="true">
            🖥️
          </div>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Acelerador 3D WebGL no disponible en este dispositivo
          </h3>
          <p style={{ maxWidth: '500px', margin: 0, fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            El entorno no dispone de contexto WebGL habilitado. Puede recorrer toda la organización, departamentos y agentes utilizando el plano 2D accesible equivalente.
          </p>
          <button
            type="button"
            onClick={onFallbackTo2D}
            style={{
              padding: '10px 20px',
              backgroundColor: 'var(--accent)',
              color: 'var(--text-inverse)',
              border: 'none',
              borderRadius: 'var(--radius-md, 8px)',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '13px',
              boxShadow: 'var(--shadow-sm)',
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
          borderRadius: 'var(--radius-lg, 16px)',
          overflow: 'hidden',
          border: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-md)',
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
              backgroundColor: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-md, 8px)',
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--accent)',
              pointerEvents: 'none',
              backdropFilter: 'blur(6px)',
              boxShadow: 'var(--shadow-sm)',
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
            padding: '8px 14px',
            backgroundColor: 'rgba(15, 23, 42, 0.88)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md, 8px)',
            fontSize: '11px',
            color: '#e2e8f0',
            pointerEvents: 'none',
            lineHeight: 1.45,
            backdropFilter: 'blur(6px)',
          }}
        >
          <span>🖱️ Arrastrar para rotar</span> · <span>🔍 Scroll para zoom</span> · <span>🎯 Clic en sala o agente</span>
        </div>
      </div>
    );
  }
);

Office3DCanvas.displayName = 'Office3DCanvas';
