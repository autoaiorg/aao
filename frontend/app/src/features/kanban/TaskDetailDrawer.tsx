import React from 'react';
import type { TaskItem } from '../../domain/models';
import { BOARD_STAGE_LABELS } from '../../domain/models';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Card';
import { parseRunSummary, type RunExecutionSummary } from '../ronin/modelProfile';
import { ExecutionTimeline } from '../ronin/components/ExecutionTimeline';
import { RoutingDecisionCard } from '../ronin/components/RoutingDecisionCard';

/** Reads the fields the backend records for an agent run; re-exports pure parser for backwards compatibility. */
export function runSummary(result: unknown): RunExecutionSummary {
  return parseRunSummary(result);
}

const PR_STATE_LABELS: Record<string, string> = {
  OPEN: 'Abierta',
  CLOSED_UNMERGED: 'Cerrada sin fusionar',
  MERGED: 'Fusionada',
};

export interface TaskDetailDrawerProps {
  task: TaskItem | null;
  onClose: () => void;
  triggerElement?: HTMLElement | null;
}

export const TaskDetailDrawer: React.FC<TaskDetailDrawerProps> = ({
  task,
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
    if (!task) return;
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
  }, [task, triggerElement, handleClose]);

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
      onClick={handleClose}
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
                {(BOARD_STAGE_LABELS as Record<string, string>)[task.status] || task.status}
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
            ref={closeButtonRef}
            type="button"
            onClick={handleClose}
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

        {/* RONIN Routing Decisions (if recorded) */}
        {task.routingDecisions && task.routingDecisions.length > 0 && (
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
              Enrutamiento de Modelos RONIN (Recomendación)
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {task.routingDecisions.map((decision, idx) => (
                <RoutingDecisionCard key={decision.id || idx} decision={decision} />
              ))}
            </div>
          </div>
        )}

        {/* Cronología de Intentos y Ejecuciones */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
            Cronología de Intentos y Ejecuciones ({task.executions?.length || 0})
          </h3>
          <ExecutionTimeline executions={task.executions} />
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

        {/* Pull requests (resultado publicado) */}
        <div>
          <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Pull Requests</h3>
          {task.pullRequests && task.pullRequests.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {task.pullRequests.map((pr) => (
                <div
                  key={pr.pr_number}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-muted)',
                    fontSize: '12px',
                  }}
                >
                  <a href={pr.pr_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
                    PR #{pr.pr_number}
                  </a>
                  {pr.state && (
                    <span style={{ marginLeft: '8px', color: 'var(--text-secondary)' }}>
                      {PR_STATE_LABELS[pr.state] ?? pr.state}
                    </span>
                  )}
                  {pr.merge_commit_sha && (
                    <div style={{ fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Merge: {pr.merge_commit_sha}
                    </div>
                  )}
                  <div style={{ fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: '2px' }}>
                    SHA: {pr.candidate_sha}
                  </div>
                  {pr.publisher && (
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>Publicada por: {pr.publisher}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Sin pull request publicada.
            </p>
          )}
        </div>

        {task.resolution && (
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>Resuelta fuera del ciclo del agente</h3>
            <div
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--bg-muted)',
                fontSize: '12px',
                color: 'var(--text-secondary)',
              }}
            >
              <div>
                Cerrada por: {task.resolution.resolved_by} · PR #{task.resolution.pr_number}
              </div>
              <div style={{ fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: '2px' }}>
                Merge: {task.resolution.merge_commit_sha}
              </div>
              <div style={{ marginTop: '4px' }}>{task.resolution.reason}</div>
            </div>
          </div>
        )}

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
