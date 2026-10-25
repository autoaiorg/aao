import React from 'react';
import type { AgentIdentity, OrgUnit } from '../../../domain/models';
import { OFFICE_ROOMS } from '../types';

export interface OfficeContextSidebarProps {
  selectedRoomId: string;
  selectedAgentId: string | null;
  units: OrgUnit[];
  agents: AgentIdentity[];
  onSelectAgent: (agentId: string | null) => void;
  onNavigate?: (target: 'organization' | 'kanban' | 'projects') => void;
  isDemo?: boolean;
}

export const OfficeContextSidebar: React.FC<OfficeContextSidebarProps> = ({
  selectedRoomId,
  selectedAgentId,
  units,
  agents,
  onSelectAgent,
  onNavigate,
  isDemo = false,
}) => {
  const roomConfig = OFFICE_ROOMS.find((r) => r.id === selectedRoomId) || OFFICE_ROOMS[0];
  const unit = units.find((u) => u.id === selectedRoomId);
  const roomAgents = agents.filter((a) => a.unitId === selectedRoomId);
  const activeAgent = roomAgents.find((a) => a.id === selectedAgentId) || agents.find((a) => a.id === selectedAgentId);

  // Derived metrics for room
  const executingAgentsCount = roomAgents.filter(
    (a) => a.currentAssignments.some((asg) => asg.status === 'ACTIVE' && asg.taskId)
  ).length;
  const connectedAgentsCount = roomAgents.filter((a) => a.heartbeatStatus === 'HEALTHY').length;

  return (
    <aside
      aria-label="Panel contextual de departamento y agentes"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4, 16px)',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg, 16px)',
        padding: 'var(--space-4, 18px)',
        minHeight: '520px',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      {/* 1. Department Overview Header */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: 'var(--radius-sm, 4px)',
              backgroundColor: roomConfig.color,
              color: '#ffffff',
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '0.5px',
            }}
          >
            {roomConfig.code}
          </span>
          <span
            style={{
              fontSize: '11px',
              color: 'var(--text-muted)',
              fontWeight: 500,
            }}
          >
            {isDemo ? (
              <span style={{ color: 'var(--status-warning-text)', fontWeight: 600 }}>
                [DEMO] {roomAgents.length} simulados
              </span>
            ) : (
              <span>{roomAgents.length} registrados</span>
            )}
          </span>
        </div>

        <h3
          style={{
            margin: '2px 0 0 0',
            fontSize: '17px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            lineHeight: 1.3,
          }}
        >
          {unit?.name || roomConfig.name}
        </h3>

        <div style={{ fontSize: '12px', color: 'var(--accent)', fontWeight: 600 }}>
          Responsable: {unit?.leadRole || 'Líder de Unidad'}
        </div>

        <p
          style={{
            margin: '0',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
          }}
        >
          {unit?.description || 'Departamento operativo de la organización digital autónoma.'}
        </p>

        {/* Operational Indicators Row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '6px',
            marginTop: '4px',
            padding: '8px 10px',
            backgroundColor: 'var(--bg-muted)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md, 8px)',
            textAlign: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {roomAgents.length}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 500 }}>
              Registrados
            </div>
          </div>
          <div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--status-success-text)' }}>
              {connectedAgentsCount}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 500 }}>
              Conectados
            </div>
          </div>
          <div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--accent)' }}>
              {executingAgentsCount}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 500 }}>
              Ejecutando
            </div>
          </div>
        </div>

        {/* Cross-navigation shortcuts */}
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
          <button
            type="button"
            disabled={!onNavigate}
            onClick={() => onNavigate?.('organization')}
            style={{
              flex: 1,
              padding: '7px 8px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-muted)',
              color: 'var(--text-primary)',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
              opacity: onNavigate ? 1 : 0.6,
            }}
          >
            🏢 Ver Organigrama
          </button>
          <button
            type="button"
            disabled={!onNavigate}
            onClick={() => onNavigate?.('kanban')}
            style={{
              flex: 1,
              padding: '7px 8px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-muted)',
              color: 'var(--text-primary)',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
              opacity: onNavigate ? 1 : 0.6,
            }}
          >
            📋 Ver Tablero
          </button>
          <button
            type="button"
            disabled={!onNavigate}
            onClick={() => onNavigate?.('projects')}
            style={{
              flex: 1,
              padding: '7px 8px',
              borderRadius: 'var(--radius-md, 6px)',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-muted)',
              color: 'var(--text-primary)',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
              opacity: onNavigate ? 1 : 0.6,
            }}
          >
            📁 Proyectos
          </button>
        </div>
      </div>

      {/* 2. Active Agent Detailed Inspector (if selected) */}
      {activeAgent ? (
        <div
          role="region"
          aria-label={`Ficha técnica de ${activeAgent.name}`}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3, 12px)',
            padding: 'var(--space-4, 16px)',
            backgroundColor: 'var(--bg-muted)',
            border: '2px solid var(--accent)',
            borderRadius: 'var(--radius-lg, 12px)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          {/* Inspector Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
            <div>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                <span
                  style={{
                    padding: '2px 7px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor: activeAgent.type === 'STANDING' ? 'var(--accent)' : 'var(--stage-in-review)',
                    color: 'var(--text-inverse)',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  {activeAgent.type === 'STANDING' ? 'Plantilla Fija' : 'Agente Efímero'}
                </span>

                {/* Heartbeat Badge */}
                <span
                  style={{
                    padding: '2px 7px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor:
                      activeAgent.heartbeatStatus === 'HEALTHY'
                        ? 'var(--status-success-bg)'
                        : activeAgent.heartbeatStatus === 'STALE'
                        ? 'var(--status-warning-bg)'
                        : 'var(--bg-subtle)',
                    color:
                      activeAgent.heartbeatStatus === 'HEALTHY'
                        ? 'var(--status-success-text)'
                        : activeAgent.heartbeatStatus === 'STALE'
                        ? 'var(--status-warning-text)'
                        : 'var(--text-secondary)',
                    border:
                      activeAgent.heartbeatStatus === 'HEALTHY'
                        ? '1px solid var(--status-success-border)'
                        : activeAgent.heartbeatStatus === 'STALE'
                        ? '1px solid var(--status-warning-border)'
                        : '1px solid var(--border-subtle)',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  {activeAgent.heartbeatStatus === 'HEALTHY'
                    ? '● Conectado'
                    : activeAgent.heartbeatStatus === 'STALE'
                    ? '▲ Latido Vencido'
                    : '○ Telemetría Desconocida'}
                </span>

                {/* Operational Execution Badge */}
                {activeAgent.currentAssignments.some((asg) => asg.status === 'ACTIVE' && asg.taskId) ? (
                  <span
                    style={{
                      padding: '2px 7px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--status-info-bg)',
                      color: 'var(--status-info-text)',
                      border: '1px solid var(--status-info-border)',
                      fontSize: '10px',
                      fontWeight: 700,
                    }}
                  >
                    ⚡ Ejecutando Tarea
                  </span>
                ) : activeAgent.currentAssignments.length > 0 ? (
                  <span
                    style={{
                      padding: '2px 7px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-secondary)',
                      fontSize: '10px',
                      fontWeight: 600,
                    }}
                  >
                    📋 Asignado
                  </span>
                ) : (
                  <span
                    style={{
                      padding: '2px 7px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-muted)',
                      fontSize: '10px',
                      fontWeight: 600,
                    }}
                  >
                    📁 Registrado (En espera)
                  </span>
                )}

                {/* DEMO Tag */}
                {(isDemo || activeAgent.isSyntheticDemo) && (
                  <span
                    style={{
                      padding: '2px 6px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--status-demo-bg)',
                      color: 'var(--status-demo-text)',
                      border: '1px solid var(--status-demo-border)',
                      fontSize: '10px',
                      fontWeight: 700,
                    }}
                  >
                    DEMO SIMULADO
                  </span>
                )}
              </div>

              <h4
                style={{
                  margin: '2px 0 2px 0',
                  fontSize: '15px',
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  lineHeight: 1.3,
                }}
              >
                {activeAgent.name}
              </h4>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {activeAgent.roleTitle}
              </div>
            </div>

            <button
              type="button"
              onClick={() => onSelectAgent(null)}
              aria-label="Cerrar ficha de agente"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: '18px',
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm, 4px)',
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>

          {/* Telemetry & Evidence Info */}
          <div
            style={{
              padding: '9px 12px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md, 8px)',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              lineHeight: 1.45,
            }}
          >
            <div>
              <strong style={{ color: 'var(--text-primary)' }}>Comprobación de presencia: </strong>
              <span>
                {activeAgent.lastHeartbeatAt
                  ? new Date(activeAgent.lastHeartbeatAt).toLocaleTimeString()
                  : 'Sin latido en tiempo real comprobado'}
              </span>
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginTop: '3px' }}>
              {isDemo
                ? 'Telemetría generada sintéticamente en modo DEMO.'
                : 'En LIVE, la presencia se restringe a telemetría verificada sin inferir actividad.'}
            </div>
          </div>

          {/* Authority Boundary */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '3px' }}>
              Límite de Autoridad:
            </div>
            <div
              style={{
                fontSize: '12px',
                color: 'var(--text-primary)',
                lineHeight: 1.45,
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md, 6px)',
                padding: '8px 10px',
              }}
            >
              {activeAgent.authorityBoundary}
            </div>
          </div>

          {/* Capabilities */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
              Capacidades Certificadas ({activeAgent.capabilities.length}):
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
              {activeAgent.capabilities.map((c) => (
                <span
                  key={c.id}
                  style={{
                    padding: '3px 8px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    backgroundColor:
                      c.level === 'CERTIFIED' ? 'var(--status-success-bg)' : 'var(--bg-surface)',
                    border:
                      c.level === 'CERTIFIED'
                        ? '1px solid var(--status-success-border)'
                        : '1px solid var(--border-subtle)',
                    color:
                      c.level === 'CERTIFIED' ? 'var(--status-success-text)' : 'var(--text-primary)',
                    fontSize: '10px',
                    fontWeight: 500,
                  }}
                >
                  {c.name} {c.verified ? '✓' : ''}
                </span>
              ))}
            </div>
          </div>

          {/* Active Assignments */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
              Asignación Operativa:
            </div>
            {activeAgent.currentAssignments.length === 0 ? (
              <div
                style={{
                  padding: '8px 10px',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: 'var(--radius-md, 6px)',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                }}
              >
                Sin tareas asignadas en este momento.
              </div>
            ) : (
              activeAgent.currentAssignments.map((asg) => (
                <div
                  key={asg.id}
                  style={{
                    padding: '10px 12px',
                    backgroundColor: 'var(--bg-surface)',
                    borderRadius: 'var(--radius-md, 6px)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '11px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '3px',
                  }}
                >
                  <strong style={{ color: 'var(--accent)', fontSize: '12px' }}>{asg.projectName}</strong>
                  {asg.taskTitle && <span style={{ color: 'var(--text-primary)' }}>{asg.taskTitle}</span>}
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    <span>Asignado: {new Date(asg.assignedAt).toLocaleDateString()}</span>
                    {asg.leaseExpiresAt && (
                      <span>Lease: {new Date(asg.leaseExpiresAt).toLocaleTimeString()}</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ) : (
        /* 3. Room Agents List */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Agentes en este departamento ({roomAgents.length})
            </span>
          </div>

          {roomAgents.length === 0 ? (
            <div
              style={{
                padding: '18px 12px',
                textAlign: 'center',
                backgroundColor: 'var(--bg-muted)',
                borderRadius: 'var(--radius-md, 8px)',
                border: '1px dashed var(--border-subtle)',
                fontSize: '12px',
                color: 'var(--text-muted)',
              }}
            >
              No hay agentes asignados a este departamento.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '280px', overflowY: 'auto' }}>
              {roomAgents.map((agent) => {
                let dotColor = '#64748b'; // UNKNOWN
                if (agent.heartbeatStatus === 'HEALTHY') dotColor = '#10b981';
                else if (agent.heartbeatStatus === 'STALE') dotColor = '#f59e0b';
                else if (agent.heartbeatStatus === 'UNAVAILABLE') dotColor = '#ef4444';

                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => onSelectAgent(agent.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md, 8px)',
                      backgroundColor: 'var(--bg-muted)',
                      border: '1px solid var(--border-subtle)',
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
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{agent.roleTitle}</div>
                      </div>
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--accent)', fontWeight: 600, flexShrink: 0 }}>
                      Ficha →
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </aside>
  );
};
