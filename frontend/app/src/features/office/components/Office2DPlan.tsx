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
        gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))',
        gap: 'var(--space-4, 16px)',
        padding: 'var(--space-4, 18px)',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg, 16px)',
        minHeight: '520px',
        alignContent: 'start',
        boxShadow: 'var(--shadow-sm)',
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
              backgroundColor: isSelected ? 'var(--accent-light)' : 'var(--bg-muted)',
              border: isSelected ? `2px solid ${room.accentColor}` : '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: 'var(--space-4, 16px)',
              gap: 'var(--space-3, 12px)',
              transition: 'all 0.2s ease',
              boxShadow: isSelected ? 'var(--shadow-md)' : 'var(--shadow-sm)',
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
                gap: '8px',
              }}
            >
              <div>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor: room.color,
                    color: '#ffffff',
                    fontSize: '11px',
                    fontWeight: 700,
                    marginBottom: '4px',
                  }}
                >
                  {room.code}
                </span>
                <h4
                  style={{
                    margin: '3px 0 2px 0',
                    fontSize: '15px',
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                    lineHeight: 1.3,
                  }}
                >
                  {unit?.name || room.name}
                </h4>
                <div style={{ fontSize: '12px', color: 'var(--accent)', fontWeight: 600 }}>
                  {unit?.leadRole || 'Responsable de unidad'}
                </div>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: 'var(--radius-full, 9999px)',
                  backgroundColor: 'var(--bg-surface)',
                  color: isSelected ? 'var(--accent)' : 'var(--text-secondary)',
                  border: '1px solid var(--border-subtle)',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
              >
                {roomAgents.length} {isDemo ? 'simulados' : 'registrados'}
              </span>
            </button>

            {/* Room description */}
            <p
              style={{
                margin: 0,
                fontSize: '12px',
                color: 'var(--text-secondary)',
                lineHeight: 1.45,
              }}
            >
              {unit?.description || 'Departamento operativo de AAO.'}
            </p>

            {/* Agents inside this room */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
              <div
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                Plantilla en sala:
              </div>

              {roomAgents.length === 0 ? (
                <div
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    fontStyle: 'italic',
                    padding: '6px 0',
                  }}
                >
                  Sin agentes asignados
                </div>
              ) : (
                roomAgents.map((agent) => {
                  let dotColor = '#64748b'; // UNKNOWN
                  if (agent.heartbeatStatus === 'HEALTHY') dotColor = '#10b981';
                  else if (agent.heartbeatStatus === 'STALE') dotColor = '#f59e0b';
                  else if (agent.heartbeatStatus === 'UNAVAILABLE') dotColor = '#ef4444';

                  const isAgentSelected = selectedAgentId === agent.id;

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
                        padding: '7px 10px',
                        borderRadius: 'var(--radius-md, 6px)',
                        backgroundColor: isAgentSelected ? 'var(--accent-light)' : 'var(--bg-surface)',
                        border: isAgentSelected
                          ? '2px solid var(--accent)'
                          : '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontSize: '12px',
                        transition: 'all 0.15s ease',
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
                        <span style={{ fontWeight: isAgentSelected ? 700 : 500, color: 'var(--text-primary)' }}>
                          {agent.name}
                        </span>
                      </div>
                      <span
                        style={{
                          fontSize: '10px',
                          color: 'var(--text-muted)',
                          padding: '1px 6px',
                          borderRadius: 'var(--radius-sm, 4px)',
                          backgroundColor: 'var(--bg-muted)',
                          border: '1px solid var(--border-subtle)',
                          fontWeight: 500,
                        }}
                      >
                        {agent.type === 'STANDING'
                          ? 'Fijo'
                          : agent.type === 'EPHEMERAL'
                          ? 'Efímero'
                          : 'Desconocido'}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        );
      })}

      {/* Unassigned / Unknown Department Room Card */}
      {(() => {
        const unassignedAgents = agents.filter(
          (a) =>
            a.unitId === 'unit-unassigned' ||
            a.unitId === 'unit-unknown' ||
            !OFFICE_ROOMS.some((r) => r.id === a.unitId)
        );
        if (unassignedAgents.length === 0) return null;
        const isSelected = selectedRoomId === 'unit-unassigned';
        return (
          <div
            key="unit-unassigned"
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: isSelected ? 'var(--accent-light)' : 'var(--bg-muted)',
              border: isSelected ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: 'var(--space-4, 16px)',
              gap: 'var(--space-3, 12px)',
              transition: 'all 0.2s ease',
              boxShadow: isSelected ? 'var(--shadow-md)' : 'var(--shadow-sm)',
            }}
          >
            <button
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelectRoom('unit-unassigned')}
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
                gap: '8px',
              }}
            >
              <div>
                <span
                  style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor: 'var(--text-muted)',
                    color: '#ffffff',
                    fontSize: '11px',
                    fontWeight: 700,
                    marginBottom: '4px',
                  }}
                >
                  DESC
                </span>
                <h4
                  style={{
                    margin: '3px 0 2px 0',
                    fontSize: '15px',
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                    lineHeight: 1.3,
                  }}
                >
                  «Departamento desconocido»
                </h4>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                  Sin adscripción departamental confirmada
                </div>
              </div>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: 'var(--radius-full, 9999px)',
                  backgroundColor: 'var(--bg-surface)',
                  color: isSelected ? 'var(--accent)' : 'var(--text-secondary)',
                  border: '1px solid var(--border-subtle)',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
              >
                {unassignedAgents.length} {isDemo ? 'simulados' : 'registrados'}
              </span>
            </button>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {unassignedAgents.map((agent) => {
                const isAgentSelected = selectedAgentId === agent.id;
                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => {
                      onSelectRoom('unit-unassigned');
                      onSelectAgent(agent.id);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      borderRadius: 'var(--radius-md, 6px)',
                      border: isAgentSelected ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                      backgroundColor: 'var(--bg-surface)',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {agent.name}
                    </span>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                      {agent.type === 'STANDING'
                        ? 'Fijo'
                        : agent.type === 'EPHEMERAL'
                        ? 'Efímero'
                        : 'Desconocido'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })()}
    </div>
  );
};
