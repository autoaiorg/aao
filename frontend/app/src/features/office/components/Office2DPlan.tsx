import React from 'react';
import type { AgentIdentity, OrgUnit } from '../../../domain/models';
import { OFFICE_ROOMS } from '../types';

export interface Office2DPlanProps {
  units: OrgUnit[];
  agents: AgentIdentity[];
  selectedRoomId: string;
  selectedAgentId: string | null;
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
  isDemo?: boolean;
}

export const Office2DPlan: React.FC<Office2DPlanProps> = ({
  units,
  agents,
  selectedRoomId,
  selectedAgentId,
  onSelectRoom,
  onSelectAgent,
  isDemo = false,
}) => {
  return (
    <div
      role="region"
      aria-label="Plano 2D accesible de la oficina de AAO"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '16px',
        padding: '20px',
        backgroundColor: '#0a1628',
        border: '1px solid #1e293b',
        borderRadius: '16px',
        minHeight: '520px',
        alignContent: 'start',
      }}
    >
      {OFFICE_ROOMS.map((room) => {
        const unit = units.find((u) => u.id === room.id);
        const roomAgents = agents.filter((a) => a.unitId === room.id);
        const isSelected = selectedRoomId === room.id;

        return (
          <div
            key={room.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: isSelected ? 'rgba(30, 58, 138, 0.45)' : 'rgba(15, 23, 42, 0.75)',
              border: isSelected ? `2px solid ${room.accentColor}` : '1px solid #334155',
              borderRadius: '12px',
              padding: '16px',
              gap: '12px',
              transition: 'all 0.2s ease',
              boxShadow: isSelected ? `0 0 16px ${room.accentColor}33` : 'none',
            }}
          >
            {/* Header / Room Button */}
            <button
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelectRoom(room.id)}
              style={{
                background: 'transparent',
                border: 'none',
                textAlign: 'left',
                cursor: 'pointer',
                padding: 0,
                color: 'inherit',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
              }}
            >
              <div>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    backgroundColor: room.color,
                    color: '#ffffff',
                    fontSize: '11px',
                    fontWeight: 700,
                    marginBottom: '4px',
                  }}
                >
                  {room.code}
                </span>
                <h4 style={{ margin: '4px 0 2px 0', fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
                  {unit?.name || room.name}
                </h4>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  {unit?.leadRole || 'Responsable de unidad'}
                </div>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '12px',
                  backgroundColor: '#1e293b',
                  color: room.accentColor,
                  fontWeight: 600,
                }}
              >
                {roomAgents.length} {isDemo ? 'simulados' : 'registrados'}
              </span>
            </button>

            {/* Room description */}
            <p style={{ margin: 0, fontSize: '12px', color: '#cbd5e1', lineHeight: 1.4 }}>
              {unit?.description || 'Departamento operativo de AAO.'}
            </p>

            {/* Agents inside this room */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>
                Plantilla en sala:
              </div>
              {roomAgents.length === 0 ? (
                <div style={{ fontSize: '11px', color: '#64748b', fontStyle: 'italic' }}>
                  Sin agentes asignados actualmente
                </div>
              ) : (
                roomAgents.map((agent) => {
                  const isAgentSelected = selectedAgentId === agent.id;
                  let dotColor = '#64748b';
                  if (agent.heartbeatStatus === 'HEALTHY') dotColor = '#22c55e';
                  else if (agent.heartbeatStatus === 'STALE') dotColor = '#eab308';
                  else if (agent.heartbeatStatus === 'UNAVAILABLE') dotColor = '#ef4444';

                  return (
                    <button
                      key={agent.id}
                      type="button"
                      aria-pressed={isAgentSelected}
                      onClick={() => onSelectAgent(agent.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 10px',
                        borderRadius: '6px',
                        backgroundColor: isAgentSelected ? '#1e40af' : '#1e293b',
                        border: isAgentSelected ? '1px solid #60a5fa' : '1px solid #334155',
                        color: '#f8fafc',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontSize: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: dotColor,
                            flexShrink: 0,
                          }}
                          aria-hidden="true"
                        />
                        <span style={{ fontWeight: 500 }}>{agent.name}</span>
                      </div>
                      <span style={{ fontSize: '10px', color: '#94a3b8' }}>
                        {agent.type === 'STANDING' ? 'Fijo' : 'Efímero'}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
