import React from 'react';
import type { TaskExecutionRecord } from '../../../domain/models';
import { parseRunSummary } from '../modelProfile';

export interface ExecutionTimelineProps {
  executions: TaskExecutionRecord[] | undefined;
  compact?: boolean;
}

export const ExecutionTimeline: React.FC<ExecutionTimelineProps> = ({ executions }) => {
  if (!executions || executions.length === 0) {
    return (
      <div
        style={{
          padding: '10px 12px',
          backgroundColor: 'var(--bg-surface)',
          border: '1px dashed var(--border-subtle)',
          borderRadius: 'var(--radius-md, 6px)',
          fontSize: '11px',
          color: 'var(--text-muted)',
          fontStyle: 'italic',
        }}
      >
        Sin intentos de ejecución registrados en cola.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {executions.map((exec, idx) => {
        const run = parseRunSummary(exec.result);
        const attemptNum = exec.attempts || idx + 1;
        const isRunning = exec.status === 'RUNNING';
        const isSucceeded = exec.status === 'SUCCEEDED';
        const isFailed = exec.status === 'FAILED';

        const statusBg = isSucceeded
          ? 'var(--status-success-bg)'
          : isRunning
          ? 'var(--status-info-bg)'
          : isFailed
          ? 'var(--status-danger-bg, #fee2e2)'
          : 'var(--bg-muted)';

        const statusColor = isSucceeded
          ? 'var(--status-success-text)'
          : isRunning
          ? 'var(--status-info-text)'
          : isFailed
          ? 'var(--status-danger-text, #991b1b)'
          : 'var(--text-secondary)';

        const statusBorder = isSucceeded
          ? '1px solid var(--status-success-border)'
          : isRunning
          ? '1px solid var(--status-info-border)'
          : isFailed
          ? '1px solid var(--status-danger-border, #fca5a5)'
          : '1px solid var(--border-subtle)';

        return (
          <div
            key={exec.id || idx}
            style={{
              padding: '10px 12px',
              borderRadius: 'var(--radius-md, 6px)',
              backgroundColor: 'var(--bg-surface)',
              border: isRunning ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
              fontSize: '11px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            {/* Attempt Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span
                  style={{
                    padding: '1px 5px',
                    borderRadius: '3px',
                    backgroundColor: 'var(--bg-muted)',
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    fontWeight: 700,
                  }}
                >
                  Intento #{attemptNum}
                </span>
                <strong style={{ fontFamily: 'monospace', color: 'var(--text-primary)', fontSize: '11px' }}>
                  {exec.id}
                </strong>
              </div>

              <span
                style={{
                  fontSize: '9px',
                  fontWeight: 700,
                  padding: '1px 6px',
                  borderRadius: '3px',
                  backgroundColor: statusBg,
                  color: statusColor,
                  border: statusBorder,
                }}
              >
                {exec.status}
              </span>
            </div>

            {/* Worker & Lease Timestamp */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                color: 'var(--text-secondary)',
                fontSize: '10px',
              }}
            >
              <span>{exec.worker_id ? `Worker: ${exec.worker_id}` : 'Worker no asignado'}</span>
              <span>
                {exec.created_at ? new Date(exec.created_at).toLocaleString('es-ES') : 'Sin marca de inicio'}
              </span>
            </div>

            {/* Selected Capability & Sourcing */}
            {run.selection && (
              <div style={{ fontSize: '11px', color: 'var(--text-primary)', marginTop: '2px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Capacidad: </span>
                <strong>{run.selection}</strong>
              </div>
            )}

            {/* Observed Model Identity (RONIN I1) */}
            {run.agent && (
              <div style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Ejecutor: </span>
                <span style={{ fontFamily: 'monospace' }}>{run.agent}</span>
              </div>
            )}

            {/* Candidate SHA */}
            {run.candidate && (
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                Candidato: <span style={{ color: 'var(--text-primary)' }}>{run.candidate}</span>
              </div>
            )}

            {/* Verification / Tests Outcome */}
            {run.check && (
              <div
                style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '3px',
                  backgroundColor: 'var(--bg-muted)',
                  color: 'var(--text-secondary)',
                  display: 'inline-block',
                  width: 'fit-content',
                }}
              >
                🧪 {run.check}
              </div>
            )}

            {/* Lease Vigency Info if Available */}
            {exec.lease_expires_at && (
              <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                Lease acreditado hasta: {new Date(exec.lease_expires_at).toLocaleTimeString('es-ES')}
              </div>
            )}

            {/* RONIN I2 No Progress Block Alert */}
            {run.is_no_progress_retry && (
              <div
                style={{
                  marginTop: '4px',
                  padding: '6px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'var(--status-warning-bg)',
                  border: '1px solid var(--status-warning-border)',
                  color: 'var(--status-warning-text)',
                  fontSize: '10px',
                  fontWeight: 600,
                }}
              >
                🛑 <strong>Detención por falta de progreso (RONIN I2):</strong> Dos intentos consecutivos generaron
                un resultado idéntico sin avance. Se requiere decisión del PM o resolución del CEO.
              </div>
            )}

            {/* RONIN I5 Budget Exceeded Block Alert */}
            {run.is_budget_exceeded && (
              <div
                style={{
                  marginTop: '4px',
                  padding: '6px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'var(--status-danger-bg, #fee2e2)',
                  border: '1px solid var(--status-danger-border, #fca5a5)',
                  color: 'var(--status-danger-text, #991b1b)',
                  fontSize: '10px',
                  fontWeight: 600,
                }}
              >
                💰 <strong>Bloqueo de Presupuesto Diario:</strong> Intento rechazado por exceder el presupuesto diario
                disponible. Resolución reservada al CEO (competencia <code>budget.exceed</code>).
              </div>
            )}

            {/* General Error (if not already captured) */}
            {run.error && !run.is_no_progress_retry && !run.is_budget_exceeded && (
              <div
                style={{
                  marginTop: '2px',
                  fontSize: '10px',
                  color: 'var(--status-danger-text, #991b1b)',
                  fontFamily: 'monospace',
                }}
              >
                Error: {run.error}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
