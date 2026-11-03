import React from 'react';
import type { ProjectSummary } from '../../../domain/models';
import type {
  EnterpriseEntitySelection,
  EnterpriseProjection,
} from './enterpriseProjection';

export interface SpatialWorkflowsPanelProps {
  projects: ProjectSummary[];
  projection: EnterpriseProjection;
  onSelectEntity: (selection: EnterpriseEntitySelection) => void;
  onNavigate?: (
    target: 'organization' | 'kanban' | 'projects' | 'decisions' | 'alerts' | 'audit',
    projectId?: string,
    workId?: string
  ) => void;
}

export const SpatialWorkflowsPanel: React.FC<SpatialWorkflowsPanelProps> = ({
  projects,
  projection,
  onSelectEntity,
  onNavigate,
}) => {
  return (
    <div
      data-testid="spatial-workflows-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        color: '#e2e8f0',
        fontSize: '12px',
      }}
    >
      <div>
        <strong style={{ fontSize: '14px', color: '#f8fafc', display: 'block' }}>
          🔗 Flujo de Trabajo Espacial e Interdependencias Departamentales
        </strong>
        <span style={{ color: '#94a3b8', fontSize: '11px' }}>
          Relaciona proyectos, encargos activos, bloqueos y departamentos participantes a partir del estado persistido.
        </span>
      </div>

      {projection.workflowLinks.length === 0 ? (
        <div
          style={{
            padding: '12px',
            borderRadius: '8px',
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(148, 163, 184, 0.2)',
            color: '#94a3b8',
          }}
        >
          No hay proyectos ni flujos interdepartamentales registrados en la proyección actual.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {projection.workflowLinks.map((wf) => {
            const proj = projects.find((p) => p.id === wf.projectId);
            const statusColor =
              wf.status === 'BLOCKED'
                ? '#fca5a5'
                : wf.status === 'ACTIVE'
                ? '#6ee7b7'
                : '#94a3b8';

            return (
              <div
                key={wf.id}
                data-testid={`workflow-card-${wf.projectId}`}
                style={{
                  padding: '10px 12px',
                  borderRadius: '10px',
                  background: 'rgba(15, 23, 42, 0.84)',
                  border:
                    wf.status === 'BLOCKED'
                      ? '1px solid rgba(248, 113, 113, 0.45)'
                      : '1px solid rgba(148, 163, 184, 0.22)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <div>
                    <strong style={{ color: '#f8fafc', fontSize: '13px' }}>
                      📁 {wf.projectName} (<code>{wf.projectId}</code>)
                    </strong>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                      Departamentos conectados:{' '}
                      {wf.participatingUnitCodes.length > 0
                        ? wf.participatingUnitCodes.join(' ↔ ')
                        : 'Ningún departamento con asignación activa'}
                    </div>
                  </div>
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: '999px',
                      fontSize: '10px',
                      fontWeight: 800,
                      color: statusColor,
                      border: '1px solid currentColor',
                    }}
                  >
                    {wf.status}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '11px', color: '#cbd5e1' }}>
                  <span>⚡ Tareas activas: <strong>{wf.activeTasksCount}</strong></span>
                  <span>⛔ Bloqueos: <strong style={{ color: wf.blockedTasksCount > 0 ? '#fca5a5' : 'inherit' }}>{wf.blockedTasksCount}</strong></span>
                  <span>⚖️ Decisiones pendientes: <strong>{wf.pendingDecisionsCount}</strong></span>
                  {proj?.taskCounts?.DONE !== undefined && (
                    <span>📊 Completadas: <strong>{proj.taskCounts.DONE}</strong></span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '2px' }}>
                  <button
                    type="button"
                    onClick={() => onSelectEntity({ kind: 'project', id: wf.projectId })}
                    className="aao-hud-btn"
                    style={{ padding: '3px 8px', fontSize: '10px' }}
                  >
                    Inspeccionar Proyecto
                  </button>
                  {wf.participatingUnitIds.map((uid, idx) => (
                    <button
                      key={uid}
                      type="button"
                      onClick={() => onSelectEntity({ kind: 'department', id: uid })}
                      className="aao-hud-btn"
                      style={{ padding: '3px 8px', fontSize: '10px' }}
                    >
                      Enfocar Dpto [{wf.participatingUnitCodes[idx] || uid}]
                    </button>
                  ))}
                  {onNavigate && (
                    <button
                      type="button"
                      onClick={() => onNavigate('kanban', wf.projectId)}
                      className="aao-hud-btn"
                      style={{ padding: '3px 8px', fontSize: '10px', color: '#7dd3fc' }}
                    >
                      Abrir Tablero Kanban
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
