import React from 'react';
import type { AgentIdentity } from '../../domain/models';
import { Badge } from '../../components/ui/Card';

export interface AgentDetailDrawerProps {
  agent: AgentIdentity | null;
  onClose: () => void;
  triggerElement?: HTMLElement | null;
}

export const AgentDetailDrawer: React.FC<AgentDetailDrawerProps> = ({
  agent,
  onClose,
  triggerElement,
}) => {
  const closeButtonRef = React.useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedElement = React.useRef<HTMLElement | null>(null);

  const handleClose = React.useCallback(() => {
    onClose();
    setTimeout(() => {
      previouslyFocusedElement.current?.focus();
    }, 0);
  }, [onClose]);

  React.useEffect(() => {
    if (!agent) return;
    previouslyFocusedElement.current =
      triggerElement || (document.activeElement as HTMLElement | null);
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [agent, triggerElement, handleClose]);

  if (!agent) return null;

  const renderHeartbeatBadge = () => {
    switch (agent.heartbeatStatus) {
      case 'HEALTHY':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 600,
              backgroundColor: 'rgba(34, 197, 94, 0.12)',
              color: 'var(--color-success)',
              border: '1px solid rgba(34, 197, 94, 0.3)',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-success)',
              }}
              aria-hidden="true"
            />
            Telemetría Activa (Healthy)
          </span>
        );
      case 'STALE':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 600,
              backgroundColor: 'rgba(234, 179, 8, 0.12)',
              color: 'var(--color-warning)',
              border: '1px solid rgba(234, 179, 8, 0.3)',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-warning)',
              }}
              aria-hidden="true"
            />
            Señal Desactualizada (Stale)
          </span>
        );
      case 'UNKNOWN':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 600,
              backgroundColor: 'var(--bg-muted)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: 'var(--text-muted)',
              }}
              aria-hidden="true"
            />
            Telemetría No Configurada (Unknown)
          </span>
        );
      case 'UNAVAILABLE':
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 600,
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              color: 'var(--color-error)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-error)',
              }}
              aria-hidden="true"
            />
            Telemetría No Disponible (Unavailable)
          </span>
        );
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-drawer-title"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.45)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 100,
      }}
      onClick={handleClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          height: '100%',
          backgroundColor: 'var(--bg-surface)',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px',
          overflowY: 'auto',
          gap: '20px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <Badge variant={agent.type === 'STANDING' ? 'info' : 'warning'}>
                {agent.type === 'STANDING' ? 'Plantilla Fija' : 'Temporal (Efímero)'}
              </Badge>
              <Badge variant="neutral">{agent.status}</Badge>
              {renderHeartbeatBadge()}
            </div>
            <h2 id="agent-drawer-title" style={{ fontSize: '18px', fontWeight: 700, margin: '4px 0' }}>
              {agent.name}
            </h2>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {agent.roleTitle} · <span style={{ fontWeight: 600 }}>{agent.unitName || agent.unitId}</span>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            onClick={handleClose}
            aria-label="Cerrar ficha de agente"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontSize: '18px',
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
            }}
          >
            ✕
          </button>
        </div>

        {agent.isSyntheticDemo && (
          <div
            style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(234, 179, 8, 0.1)',
              border: '1px solid rgba(234, 179, 8, 0.3)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--color-warning)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span aria-hidden="true">ℹ️</span>
            <span>Entidad sintética de demostración arquitectónica F3. No representa agentes en producción.</span>
          </div>
        )}

        {/* Telemetry and Freshness details */}
        <div
          style={{
            padding: '12px 14px',
            backgroundColor: 'var(--bg-muted)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
            fontSize: '12px',
            lineHeight: 1.6,
          }}
        >
          <strong style={{ display: 'block', color: 'var(--text-primary)', marginBottom: '4px' }}>
            Auditoría de Actividad y Telemetría:
          </strong>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Identificador de agente: </span>
            <code style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>{agent.id}</code>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Último latido verificado (Heartbeat): </span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
              {agent.lastHeartbeatAt ? new Date(agent.lastHeartbeatAt).toLocaleString() : 'Sin registro de latido'}
            </span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '11px', color: 'var(--text-muted)' }}>
            Principio de honestidad técnica: nunca se deduce actividad o presencia sin un latido comprobado.
          </p>
        </div>

        {/* Authority Boundary */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
            Límite Constitucional de Autoridad
          </h3>
          <div
            style={{
              padding: '12px 14px',
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-focus)',
              fontSize: '13px',
              color: 'var(--text-primary)',
              lineHeight: 1.5,
            }}
          >
            {agent.authorityBoundary}
          </div>
        </div>

        {/* Project Grants */}
        {agent.grants && agent.grants.length > 0 && (
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
              Concesiones y Permisos de Proyecto ({agent.grants.length})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {agent.grants.map((g, idx) => (
                <div
                  key={`grant-${idx}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                    🔑 {g.permission} <span style={{ color: 'var(--text-muted)' }}>({g.projectId})</span>
                  </span>
                  <Badge variant={g.active ? 'success' : 'neutral'}>
                    {g.active ? 'Activo' : 'Inactivo'}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Capabilities */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
            Matriz de Capacidades Técnicas ({agent.capabilities.length})
          </h3>
          {agent.capabilities.length === 0 ? (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Sin capacidades registradas.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {agent.capabilities.map((cap) => (
                <div
                  key={cap.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{cap.name}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Badge variant={cap.level === 'CERTIFIED' ? 'success' : 'neutral'}>
                      {cap.level}
                    </Badge>
                    {cap.verified && (
                      <span
                        style={{ fontSize: '11px', color: 'var(--color-success)' }}
                        title="Capacidad auditada y verificada"
                      >
                        ✓ Verificada
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Active Assignments */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
            Asignaciones y Tareas Actuales ({agent.currentAssignments.length})
          </h3>
          {agent.currentAssignments.length === 0 ? (
            <div
              style={{
                padding: '16px',
                textAlign: 'center',
                backgroundColor: 'var(--bg-muted)',
                borderRadius: 'var(--radius-md)',
                border: '1px dashed var(--border-subtle)',
                fontSize: '13px',
                color: 'var(--text-secondary)',
              }}
            >
              Sin tareas asignadas en este momento. Agente en estado disponible / IDLE.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {agent.currentAssignments.map((asg) => (
                <div
                  key={asg.id}
                  style={{
                    padding: '12px',
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ color: 'var(--text-primary)', fontSize: '13px' }}>
                      {asg.projectName}
                    </strong>
                    <Badge variant={asg.status === 'ACTIVE' ? 'info' : 'neutral'}>{asg.status}</Badge>
                  </div>
                  {asg.taskTitle && (
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>
                      Tarea: <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{asg.taskTitle}</span>
                    </div>
                  )}
                  {asg.leaseExpiresAt && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                      Arrendamiento de concesión (Lease): Expira {new Date(asg.leaseExpiresAt).toLocaleTimeString()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
