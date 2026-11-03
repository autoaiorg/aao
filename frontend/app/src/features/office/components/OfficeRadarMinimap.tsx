import React from 'react';
import type { AgentIdentity } from '../../../domain/models';
import type { CameraViewState, OfficeRoomConfig } from '../types';
import { deriveAgentOperationalCategory } from '../useOfficeHudState';

export interface OfficeRadarMinimapProps {
  isOpen: boolean;
  onToggleOpen: () => void;
  rooms: OfficeRoomConfig[];
  agents: AgentIdentity[];
  selectedRoomId: string;
  selectedAgentId: string | null;
  cameraState: CameraViewState;
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
}

const WORLD_SPAN_X = 20; // -10 to +10
const WORLD_SPAN_Z = 14; // -7 to +7
const MAP_WIDTH = 200;
const MAP_HEIGHT = 128;

function worldToMap(x: number, z: number): { mx: number; my: number } {
  const mx = ((x + WORLD_SPAN_X / 2) / WORLD_SPAN_X) * MAP_WIDTH;
  const my = ((z + WORLD_SPAN_Z / 2) / WORLD_SPAN_Z) * MAP_HEIGHT;
  return {
    mx: Math.max(8, Math.min(MAP_WIDTH - 8, mx)),
    my: Math.max(8, Math.min(MAP_HEIGHT - 8, my)),
  };
}

export const OfficeRadarMinimap: React.FC<OfficeRadarMinimapProps> = ({
  isOpen,
  onToggleOpen,
  rooms,
  agents,
  selectedRoomId,
  selectedAgentId,
  cameraState,
  onSelectRoom,
}) => {
  const camTarget = worldToMap(cameraState.targetX, cameraState.targetZ);

  return (
    <section
      aria-label="Minimapa radar táctico 2D"
      className="aao-hud-minimap aao-hud-glass"
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span aria-hidden="true">🧭</span>
          <strong style={{ fontSize: '11px', color: '#f8fafc', letterSpacing: '0.4px' }}>
            RADAR TÁCTICO
          </strong>
        </div>
        <button
          type="button"
          className="aao-hud-btn"
          style={{ padding: '2px 7px', fontSize: '10px' }}
          aria-expanded={isOpen}
          aria-label={isOpen ? 'Comprimir minimapa radar' : 'Expandir minimapa radar'}
          onClick={onToggleOpen}
        >
          {isOpen ? '−' : '+'}
        </button>
      </div>

      {isOpen && (
        <div
          style={{
            position: 'relative',
            width: `${MAP_WIDTH}px`,
            height: `${MAP_HEIGHT}px`,
            borderRadius: '8px',
            background: 'radial-gradient(circle at center, rgba(14, 116, 144, 0.22) 0%, rgba(2, 6, 23, 0.92) 100%)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            overflow: 'hidden',
          }}
        >
          {/* SVG Camera Frustum & Grid Lines */}
          <svg
            width={MAP_WIDTH}
            height={MAP_HEIGHT}
            viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
            aria-hidden="true"
          >
            <line x1={MAP_WIDTH / 2} y1={0} x2={MAP_WIDTH / 2} y2={MAP_HEIGHT} stroke="rgba(56, 189, 248, 0.14)" strokeDasharray="3 3" />
            <line x1={0} y1={MAP_HEIGHT / 2} x2={MAP_WIDTH} y2={MAP_HEIGHT / 2} stroke="rgba(56, 189, 248, 0.14)" strokeDasharray="3 3" />

            {/* Camera View Cone */}
            <g transform={`translate(${camTarget.mx}, ${camTarget.my}) rotate(${-cameraState.angle})`}>
              <polygon
                points="0,0 -20,34 20,34"
                fill="rgba(56, 189, 248, 0.18)"
                stroke="rgba(56, 189, 248, 0.55)"
                strokeWidth="1"
              />
              <circle cx="0" cy="0" r="2.5" fill="#38bdf8" />
            </g>
          </svg>

          {/* Interactive Sector Pads */}
          {rooms.map((room) => {
            const pos = worldToMap(room.x, room.z);
            const isSelected = room.id === selectedRoomId;
            const roomAgents = agents.filter((a) => a.unitId === room.id);
            return (
              <button
                key={room.id}
                type="button"
                onClick={() => onSelectRoom(room.id)}
                aria-label={`Enfocar radar en sector ${room.code}`}
                title={`${room.name} (${roomAgents.length} agentes)`}
                style={{
                  position: 'absolute',
                  left: `${pos.mx - 22}px`,
                  top: `${pos.my - 14}px`,
                  width: '44px',
                  height: '28px',
                  borderRadius: '4px',
                  background: isSelected ? 'rgba(2, 132, 199, 0.5)' : 'rgba(15, 23, 42, 0.82)',
                  border: isSelected ? `2px solid ${room.accentColor}` : `1px solid ${room.accentColor}`,
                  color: '#f8fafc',
                  fontSize: '9px',
                  fontWeight: 700,
                  padding: '2px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '2px',
                }}
              >
                <span>{room.code}</span>
                {/* Agent blip dots */}
                <span style={{ display: 'flex', gap: '2px' }}>
                  {roomAgents.slice(0, 5).map((agent) => {
                    const op = deriveAgentOperationalCategory(agent);
                    const dotColor =
                      agent.id === selectedAgentId
                        ? '#ffffff'
                        : op.category === 'ACTIVO'
                        ? '#10b981'
                        : op.category === 'BLOQUEADO'
                        ? '#ef4444'
                        : op.category === 'PENDIENTE'
                        ? '#f59e0b'
                        : '#94a3b8';
                    return (
                      <span
                        key={agent.id}
                        style={{
                          width: '4px',
                          height: '4px',
                          borderRadius: '999px',
                          backgroundColor: dotColor,
                          display: 'inline-block',
                        }}
                      />
                    );
                  })}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
};
