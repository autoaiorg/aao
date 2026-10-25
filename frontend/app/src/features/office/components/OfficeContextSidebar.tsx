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

  return (
    <aside
      aria-label="Panel contextual de departamento y agentes"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        backgroundColor: 'var(--bg-surface, #0f172a)',
        border: '1px solid var(--border-subtle, #334155)',
        borderRadius: '16px',
        padding: '20px',
        minHeight: '520px',
      }}
    >
      {/* 1. Department Overview Header */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: roomConfig.color,
              color: '#ffffff',
              fontSize: '11px',
              fontWeight: 700,
            }}
          >
            {roomConfig.code}
          </span>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
            {roomAgents.length} agentes {isDemo ? 'simulados' : 'registrados'}
          </span>
        </div>

        <h3 style={{ margin: '4px 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#f8fafc' }}>
          {unit?.name || roomConfig.name}
        </h3>

        <div style={{ fontSize: '12px', color: '#38bdf8', fontWeight: 600, marginBottom: '8px' }}>
          Responsable: {unit?.leadRole || 'Líder de Unidad'}
        </div>

        <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: '#94a3b8', lineHeight: 1.5 }}>
          {unit?.description || 'Departamento operativo de la organización digital autónoma.'}
        </p>

        {/* Cross-navigation shortcuts */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            disabled={!onNavigate}
            onClick={() => onNavigate?.('organization')}
            style={{
              flex: 1,
              padding: '7px 10px',
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#1e293b',
              color: '#f8fafc',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
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
              padding: '7px 10px',
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#1e293b',
              color: '#f8fafc',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
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
              padding: '7px 10px',
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#1e293b',
              color: '#f8fafc',
              fontSize: '11px',
              fontWeight: 600,
              cursor: onNavigate ? 'pointer' : 'not-allowed',
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
            gap: '12px',
            padding: '16px',
            backgroundColor: '#0a1628',
            border: '1px solid #38bdf8',
            borderRadius: '12px',
            boxShadow: '0 0 16px rgba(56, 189, 248, 0.15)',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <span
                  style={{
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: activeAgent.type === 'STANDING' ? '#1e40af' : '#0891b2',
                    color: '#ffffff',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  {activeAgent.type === 'STANDING' ? 'Plantilla Fija' : 'Agente Efímero'}
                </span>
                <span
                  style={{
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor:
                      activeAgent.heartbeatStatus === 'HEALTHY'
                        ? '#064e3b'
                        : activeAgent.heartbeatStatus === 'STALE'
                        ? '#713f12'
                        : '#334155',
                    color:
                      activeAgent.heartbeatStatus === 'HEALTHY'
                        ? '#34d399'
                        : activeAgent.heartbeatStatus === 'STALE'
                        ? '#fef08a'
                        : '#cbd5e1',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  {activeAgent.heartbeatStatus}
                </span>
              </div>
              <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
                {activeAgent.name}
              </h4>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>{activeAgent.roleTitle}</div>
            </div>

            <button
              type="button"
              onClick={() => onSelectAgent(null)}
              aria-label="Cerrar ficha de agente"
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
                fontSize: '16px',
                padding: '2px 6px',
              }}
            >
              ✕
            </button>
          </div>

          {/* Telemetry info */}
          <div
            style={{
              padding: '8px 10px',
              backgroundColor: '#1e293b',
              borderRadius: '6px',
              fontSize: '11px',
              color: '#cbd5e1',
              lineHeight: 1.4,
            }}
          >
            <div>
              <strong style={{ color: '#f8fafc' }}>Latido comprobado: </strong>
              <span>
                {activeAgent.lastHeartbeatAt
                  ? new Date(activeAgent.lastHeartbeatAt).toLocaleTimeString()
                  : 'Sin registro comprobable'}
              </span>
            </div>
            <div style={{ color: '#94a3b8', fontSize: '10px', marginTop: '2px' }}>
              {isDemo
                ? 'Telemetría simulada localmente en modo demostración.'
                : 'En LIVE, la ausencia de latido indica que el agente no está conectado.'}
            </div>
          </div>

          {/* Authority Boundary */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '2px' }}>
              Límite de Autoridad:
            </div>
            <div style={{ fontSize: '12px', color: '#e2e8f0', lineHeight: 1.4 }}>
              {activeAgent.authorityBoundary}
            </div>
          </div>

          {/* Capabilities */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '4px' }}>
              Capacidades ({activeAgent.capabilities.length}):
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              {activeAgent.capabilities.map((c) => (
                <span
                  key={c.id}
                  style={{
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    color: c.level === 'CERTIFIED' ? '#34d399' : '#e2e8f0',
                    fontSize: '10px',
                  }}
                >
                  {c.name} {c.verified ? '✓' : ''}
                </span>
              ))}
            </div>
          </div>

          {/* Assignments */}
          {activeAgent.currentAssignments.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '4px' }}>
                Asignación Activa:
              </div>
              {activeAgent.currentAssignments.map((asg) => (
                <div
                  key={asg.id}
                  style={{
                    padding: '8px',
                    backgroundColor: '#1e293b',
                    borderRadius: '6px',
                    border: '1px solid #334155',
                    fontSize: '11px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '2px',
                  }}
                >
                  <strong style={{ color: '#38bdf8' }}>{asg.projectName}</strong>
                  {asg.taskTitle && <span style={{ color: '#f8fafc' }}>{asg.taskTitle}</span>}
                  {asg.leaseExpiresAt && (
                    <span style={{ fontSize: '10px', color: '#94a3b8' }}>
                      Lease hasta: {new Date(asg.leaseExpiresAt).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* 3. Room Agents List */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1' }}>
              Agentes en este departamento ({roomAgents.length})
            </span>
          </div>

          {roomAgents.length === 0 ? (
            <div
              style={{
                padding: '16px',
                textAlign: 'center',
                backgroundColor: '#0a1628',
                borderRadius: '8px',
                border: '1px dashed #334155',
                fontSize: '12px',
                color: '#94a3b8',
              }}
            >
              No hay agentes asignados a este departamento.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '280px', overflowY: 'auto' }}>
              {roomAgents.map((agent) => {
                let dotColor = '#64748b';
                if (agent.heartbeatStatus === 'HEALTHY') dotColor = '#22c55e';
                else if (agent.heartbeatStatus === 'STALE') dotColor = '#eab308';
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
                      borderRadius: '8px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
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
                        }}
                        aria-hidden="true"
                      />
                      <div>
                        <div style={{ fontWeight: 600 }}>{agent.name}</div>
                        <div style={{ fontSize: '11px', color: '#94a3b8' }}>{agent.roleTitle}</div>
                      </div>
                    </div>
                    <span style={{ fontSize: '11px', color: '#38bdf8' }}>Ficha →</span>
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
