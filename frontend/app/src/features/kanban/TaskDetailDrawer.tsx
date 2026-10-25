import React from 'react';
import type { TaskItem } from '../../domain/models';
import { BOARD_STAGE_LABELS } from '../../domain/models';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Card';

export interface TaskDetailDrawerProps {
  task: TaskItem | null;
  onClose: () => void;
}

export const TaskDetailDrawer: React.FC<TaskDetailDrawerProps> = ({ task, onClose }) => {
  if (!task) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-drawer-title"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '540px',
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Badge variant="neutral">
                {BOARD_STAGE_LABELS[task.status] || task.status}
              </Badge>
              <span style={{ fontSize: '12px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                {task.id}
              </span>
            </div>
            <h2 id="task-drawer-title" style={{ fontSize: '18px', fontWeight: 700 }}>
              {task.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar panel de tarea"
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '16px',
              color: 'var(--text-muted)',
            }}
          >
            ✕
          </button>
        </div>

        {/* Criterios de Aceptación */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
            Criterios de Aceptación
          </h3>
          {task.acceptanceCriteria && task.acceptanceCriteria.length > 0 ? (
            <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              {task.acceptanceCriteria.map((c, i) => (
                <li key={i} style={{ marginBottom: '4px' }}>
                  {c}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No se han definido criterios formales en el contrato de la tarea.
            </p>
          )}
        </div>

        {/* Ejecuciones */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
            Registro de Ejecuciones
          </h3>
          {task.executions && task.executions.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {task.executions.map((exec) => (
                <div
                  key={exec.id}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-muted)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong style={{ fontFamily: 'monospace' }}>{exec.id}</strong>
                    <span>Estado: {exec.status}</span>
                  </div>
                  {exec.worker_id && (
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>
                      Worker: {exec.worker_id} · Intentos: {exec.attempts}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Sin ejecuciones registradas en cola.
            </p>
          )}
        </div>

        {/* Revisiones y Auditoría */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
            Revisiones de Auditoría
          </h3>
          {task.reviews && task.reviews.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {task.reviews.map((rev) => (
                <div
                  key={rev.id}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-muted)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Auditor: {rev.reviewer_id}</span>
                    <strong style={{ color: 'var(--accent)' }}>{rev.decision}</strong>
                  </div>
                  {rev.candidate_sha && (
                    <div style={{ fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: '2px' }}>
                      SHA: {rev.candidate_sha}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Sin dictámenes de revisión registrados.
            </p>
          )}
        </div>

        {/* Patch Proposal Diff Security Boundary Notice */}
        <div
          style={{
            marginTop: 'auto',
            padding: '12px',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--bg-muted)',
            border: '1px dashed var(--border-strong)',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}
        >
          <strong>Frontera de Seguridad:</strong> La inspección del diff completo de patch proposals
          está restringida al rol AUDITOR durante revisión activa (HTTP 403). La sesión de lectura no solicita
          este endpoint privilegiado para evitar accesos no autorizados.
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        </div>
      </div>
    </div>
  );
};
