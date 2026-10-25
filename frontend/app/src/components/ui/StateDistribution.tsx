import React from 'react';
import type { BoardStage } from '../../domain/models';
import { BOARD_STAGES, BOARD_STAGE_LABELS } from '../../domain/models';

export interface StateDistributionProps {
  distribution?: Record<BoardStage, number>;
  totalCount?: number;
  className?: string;
}

export const StateDistribution: React.FC<StateDistributionProps> = ({
  distribution,
  totalCount,
  className = '',
}) => {
  const counts = distribution || {
    INBOX: 0,
    READY: 0,
    IN_PROGRESS: 0,
    IN_REVIEW: 0,
    VERIFIED: 0,
    DONE: 0,
  };

  const total = totalCount ?? Object.values(counts).reduce((acc, n) => acc + n, 0);

  const stageColors: Record<BoardStage, string> = {
    INBOX: 'var(--stage-inbox)',
    READY: 'var(--stage-ready)',
    IN_PROGRESS: 'var(--stage-in-progress)',
    IN_REVIEW: 'var(--stage-in-review)',
    VERIFIED: 'var(--stage-verified)',
    DONE: 'var(--stage-done)',
  };

  return (
    <div className={`aao-state-distribution ${className}`} style={{ width: '100%' }}>
      {/* Visual multi-segment bar */}
      <div
        role="progressbar"
        aria-label="Distribución de tareas por estado de ciclo de vida"
        aria-valuenow={total}
        aria-valuemin={0}
        aria-valuemax={total}
        style={{
          display: 'flex',
          height: '10px',
          borderRadius: 'var(--radius-full)',
          overflow: 'hidden',
          backgroundColor: 'var(--bg-muted)',
          margin: '8px 0 16px 0',
        }}
      >
        {total === 0 ? (
          <div style={{ width: '100%', backgroundColor: 'var(--border-subtle)' }} />
        ) : (
          BOARD_STAGES.map((stage) => {
            const count = counts[stage] || 0;
            const pct = (count / total) * 100;
            if (pct <= 0) return null;
            return (
              <div
                key={stage}
                title={`${BOARD_STAGE_LABELS[stage]}: ${count} (${pct.toFixed(1)}%)`}
                style={{
                  width: `${pct}%`,
                  backgroundColor: stageColors[stage],
                  transition: 'width 0.3s ease',
                }}
              />
            );
          })
        )}
      </div>

      {/* Accessible Stage Breakdown Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
          gap: '8px',
          fontSize: '12px',
        }}
      >
        {BOARD_STAGES.map((stage) => {
          const count = counts[stage] || 0;
          return (
            <div
              key={stage}
              style={{
                display: 'flex',
                flexDirection: 'column',
                padding: '6px 8px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--bg-muted)',
                borderLeft: `4px solid ${stageColors[stage]}`,
              }}
            >
              <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                {BOARD_STAGE_LABELS[stage]}
              </span>
              <span
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  marginTop: '2px',
                }}
              >
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
