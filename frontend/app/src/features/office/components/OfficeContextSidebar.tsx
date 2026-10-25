import React from 'react';
import type { AgentIdentity, OrgUnit } from '../../../domain/models';
import { OFFICE_ROOMS } from '../types';

export interface OfficeContextSidebarProps {
  selectedRoomId: string;
  selectedAgentId: string | null;
  units: OrgUnit[];
  agents: AgentIdentity[];
  onSelectAgent: (agentId: string | null) => void;
  onNavigate?: (target: 'organization' | 'kanban' | 'projects', projectId?: string) => void;
  onOpenAgentDetail?: (agent: AgentIdentity) => void;
  isDemo?: boolean;
}

export const OfficeContextSidebar: React.FC<OfficeContextSidebarProps> = ({
  selectedRoomId,
  selectedAgentId,
  units,
  agents,
  onSelectAgent,
  onNavigate,
  onOpenAgentDetail,
  isDemo = false,
}) => {
  const isUnassignedRoom = selectedRoomId === 'unit-unassigned';
  const roomConfig =
    OFFICE_ROOMS.find((r) => r.id === selectedRoomId) ||
    (isUnassignedRoom
      ? {
          id: 'unit-unassigned',
          code: 'DESC',
          name: '«Departamento desconocido»',
          x: 0,
          z: 0,
          width: 4,
          depth: 4,
          color: '#64748b',
          accentColor: '#94a3b8',
        }
      : undefined);

  const unit =
    units.find((u) => u.id === selectedRoomId) ||
    (isUnassignedRoom
      ? {
          id: 'unit-unassigned',
          name: '«Departamento desconocido»',
          code: 'DESC',
          parentId: null,
          leadRole: 'Sin asignar / Desconocido',
          leadAgentId: null,
          description: 'Sin adscripción departamental canónica confirmada en el núcleo.',
          standingCount: 0,
          ephemeralCount: 0,
          activeProjectsCount: 0,
        }
      : undefined);
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
              backgroundColor: roomConfig?.color || '#334155',
              color: '#ffffff',
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '0.5px',
            }}
          >
            {unit?.code || roomConfig?.code || 'ORG'}
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
          {unit?.name || roomConfig?.name || 'Unidad no disponible'}
        </h3>

        <div style={{ fontSize: '12px', color: 'var(--accent)', fontWeight: 600 }}>
          {unit?.leadAgentId
            ? `Responsable: ${agents.find((agent) => agent.id === unit.leadAgentId)?.name || unit.leadAgentId} · ${unit.leadRole}`
            : `Responsable: ${unit?.leadRole || 'No declarado'}`}
        </div>

        <p
          style={{
            margin: '0',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
          }}
        >
          {unit?.description ||
            (isUnassignedRoom
              ? 'Sin adscripción departamental canónica confirmada en el núcleo.'
              : 'Sin descripción organizativa declarada.')}
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
                    backgroundColor:
                      activeAgent.type === 'STANDING'
                        ? 'var(--accent)'
                        : activeAgent.type === 'EPHEMERAL'
                        ? 'var(--stage-in-review)'
                        : 'var(--text-muted)',
                    color: 'var(--text-inverse)',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  {activeAgent.type === 'STANDING'
                    ? 'Plantilla Fija'
                    : activeAgent.type === 'EPHEMERAL'
                    ? 'Agente Efímero'
                    : 'Tipo Desconocido'}
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
                {activeAgent.operationalState === 'EJECUTANDO' ? (
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
                    ⚡ Ejecutando Tarea (Lease vigente)
                  </span>
                ) : activeAgent.operationalState === 'DESCONOCIDO' ? (
                  <span
                    style={{
                      padding: '2px 7px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--status-warning-bg)',
                      color: 'var(--status-warning-text)',
                      border: '1px solid var(--status-warning-border)',
                      fontSize: '10px',
                      fontWeight: 700,
                    }}
                  >
                    ⚠️ Vigencia Desconocida (Sin lease acreditado)
                  </span>
                ) : activeAgent.operationalState === 'ASIGNADO' ? (
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
                    📋 Asignado (Sin ejecución activa confirmada)
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
                    📁 Registrado (Sin actividad vigente)
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

          {/* Evidencia y Procedencia */}
          <div
            style={{
              padding: '8px 10px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md, 6px)',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              lineHeight: 1.45,
            }}
          >
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '2px' }}>
              Procedencia y Evidencia:
            </div>
            <div>{activeAgent.evidenceDescription || 'Sin evidencia adicional registrada en el núcleo.'}</div>
            <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--text-muted)' }}>
              {activeAgent.lastEvidenceAt
                ? `Marca temporal de evidencia en núcleo: ${new Date(activeAgent.lastEvidenceAt).toLocaleString()}`
                : 'Sin marca temporal de evidencia registrada (lastEvidenceAt: null)'}
            </div>
          </div>

          {/* Project Grants / Concessions */}
          {activeAgent.grants && activeAgent.grants.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
                Concesiones y Permisos de Proyecto ({activeAgent.grants.length}):
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {activeAgent.grants.map((g, idx) => (
                  <div
                    key={`grant-${idx}`}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '10px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      🔑 {g.permission}{' '}
                      <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>({g.projectId})</span>
                    </span>
                    <span
                      style={{
                        padding: '1px 5px',
                        borderRadius: '3px',
                        backgroundColor: g.active ? 'var(--status-success-bg)' : 'var(--bg-muted)',
                        color: g.active ? 'var(--status-success-text)' : 'var(--text-muted)',
                        fontWeight: 600,
                      }}
                    >
                      {g.active ? 'Activo' : 'Inactivo'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Capabilities */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
              Capacidades Técnicas Registradas ({activeAgent.capabilities.length}):
            </div>
            {activeAgent.capabilities.length === 0 ? (
              <div
                style={{
                  padding: '6px 10px',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: 'var(--radius-md, 6px)',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                }}
              >
                Sin capacidades certificadas ni declaradas formalmente.
              </div>
            ) : (
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
            )}
          </div>

          {/* Active vs Historical Assignments */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
              Trabajo y Asignaciones:
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
                Sin tareas asignadas ni registros históricos en este momento.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {activeAgent.currentAssignments.map((asg) => {
                  const isActive = asg.status === 'ACTIVE';
                  const isUnknown = asg.status === 'UNKNOWN';
                  const isExpired = asg.status === 'EXPIRED';
                  return (
                    <div
                      key={asg.id}
                      style={{
                        padding: '10px 12px',
                        backgroundColor: 'var(--bg-surface)',
                        borderRadius: 'var(--radius-md, 6px)',
                        border: isActive
                          ? '1px solid var(--accent)'
                          : isUnknown
                          ? '1px solid var(--status-warning-border)'
                          : '1px solid var(--border-subtle)',
                        fontSize: '11px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '3px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong
                          style={{
                            color: isActive
                              ? 'var(--accent)'
                              : isUnknown
                              ? 'var(--status-warning-text)'
                              : 'var(--text-primary)',
                            fontSize: '12px',
                          }}
                        >
                          {asg.projectName}
                        </strong>
                        <span
                          style={{
                            fontSize: '9px',
                            fontWeight: 700,
                            padding: '1px 5px',
                            borderRadius: '3px',
                            backgroundColor: isActive
                              ? 'var(--status-info-bg)'
                              : isUnknown
                              ? 'var(--status-warning-bg)'
                              : isExpired
                              ? 'var(--status-danger-bg, #fee2e2)'
                              : 'var(--bg-muted)',
                            color: isActive
                              ? 'var(--status-info-text)'
                              : isUnknown
                              ? 'var(--status-warning-text)'
                              : isExpired
                              ? 'var(--status-danger-text, #991b1b)'
                              : 'var(--text-muted)',
                            border: isActive
                              ? '1px solid var(--status-info-border)'
                              : isUnknown
                              ? '1px solid var(--status-warning-border)'
                              : isExpired
                              ? '1px solid var(--status-danger-border, #fca5a5)'
                              : '1px solid var(--border-subtle)',
                          }}
                        >
                          {isActive
                            ? 'EJECUCIÓN VIGENTE'
                            : isUnknown
                            ? 'VIGENCIA DESCONOCIDA (SIN LEASE)'
                            : isExpired
                            ? 'LEASE EXPIRADO'
                            : 'HISTÓRICO REGISTRADO'}
                        </span>
                      </div>
                      {asg.taskTitle && <span style={{ color: 'var(--text-primary)' }}>{asg.taskTitle}</span>}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: '10px',
                          color: 'var(--text-muted)',
                          marginTop: '2px',
                        }}
                      >
                        <span>
                          {asg.assignedAt
                            ? `Fecha registro: ${new Date(asg.assignedAt).toLocaleDateString()}`
                            : 'Sin marca temporal'}
                        </span>
                        {asg.leaseExpiresAt && (
                          <span>Lease: {new Date(asg.leaseExpiresAt).toLocaleTimeString()}</span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => onNavigate?.('kanban', asg.projectId)}
                        disabled={!onNavigate}
                        style={{
                          alignSelf: 'flex-start',
                          marginTop: '5px',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm, 4px)',
                          background: 'var(--bg-muted)',
                          color: 'var(--text-primary)',
                          padding: '4px 8px',
                          fontSize: '10px',
                          fontWeight: 600,
                          cursor: onNavigate ? 'pointer' : 'not-allowed',
                        }}
                      >
                        Abrir tablero de este proyecto
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* RONIN Execution & Model History (I1-I6) */}
          {activeAgent.executionHistory && activeAgent.executionHistory.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '5px' }}>
                Historial de Ejecuciones y Modelos RONIN ({activeAgent.executionHistory.length}):
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {activeAgent.executionHistory.map((exec) => (
                  <div
                    key={exec.id}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 'var(--radius-md, 6px)',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '11px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '3px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                        {exec.taskTitle}
                      </strong>
                      <span
                        style={{
                          fontSize: '9px',
                          fontWeight: 700,
                          padding: '1px 5px',
                          borderRadius: '3px',
                          backgroundColor:
                            exec.status === 'SUCCEEDED'
                              ? 'var(--status-success-bg)'
                              : exec.status === 'RUNNING'
                              ? 'var(--status-info-bg)'
                              : 'var(--bg-muted)',
                          color:
                            exec.status === 'SUCCEEDED'
                              ? 'var(--status-success-text)'
                              : exec.status === 'RUNNING'
                              ? 'var(--status-info-text)'
                              : 'var(--text-secondary)',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        {exec.status}
                      </span>
                    </div>

                    <div style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      <span>Intento #{exec.attempts}</span>
                      {exec.provider && (
                        <span>
                          🤖 <strong>{exec.provider}</strong> · {exec.model ?? 'modelo por defecto'}
                        </span>
                      )}
                      {exec.costEstimateUsd !== undefined && (
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
                          ~${exec.costEstimateUsd} USD
                        </span>
                      )}
                    </div>

                    {exec.capabilityId && (
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        Capacidad: {exec.capabilityId}@{exec.capabilityVersion ?? '?'} ({exec.backendSource === 'capability' ? 'por capacidad' : 'por entorno'})
                      </div>
                    )}

                    {exec.candidateSha && (
                      <div style={{ fontSize: '9px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                        SHA: {exec.candidateSha}
                      </div>
                    )}

                    {exec.check && (
                      <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                        🧪 {exec.check}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cross-navigation button */}
          {(onOpenAgentDetail || onNavigate) && (
            <button
              type="button"
              onClick={() => {
                if (onOpenAgentDetail && activeAgent) {
                  onOpenAgentDetail(activeAgent);
                } else if (onNavigate) {
                  onNavigate('organization');
                }
              }}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: 'var(--radius-md, 6px)',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--accent)',
                color: 'var(--accent)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                textAlign: 'center',
                marginTop: '4px',
              }}
            >
              👥 Ver Ficha Completa en Organización
            </button>
          )}
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
