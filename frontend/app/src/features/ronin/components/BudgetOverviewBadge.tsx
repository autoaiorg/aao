import React from 'react';
import type { ProjectBudgetInfo } from '../modelProfile';

export interface BudgetOverviewBadgeProps {
  budgetInfo?: ProjectBudgetInfo | null;
  budgetLeftUsd?: number | null;
  costEstimateUsd?: number | null;
  isBlockedBudgetExceed?: boolean;
  isBudgetExceeded?: boolean;
}

export const BudgetOverviewBadge: React.FC<BudgetOverviewBadgeProps> = ({
  budgetInfo,
  budgetLeftUsd,
  costEstimateUsd,
  isBlockedBudgetExceed = false,
  isBudgetExceeded = false,
}) => {
  const effectiveBudgetLeft = budgetInfo?.budget_left_usd ?? budgetLeftUsd ?? null;
  const isBlocked = isBlockedBudgetExceed || isBudgetExceeded;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        padding: '10px 12px',
        borderRadius: 'var(--radius-md, 6px)',
        backgroundColor: isBlocked ? 'var(--status-danger-bg, #fee2e2)' : 'var(--bg-surface)',
        border: isBlocked
          ? '1px solid var(--status-danger-border, #fca5a5)'
          : '1px solid var(--border-subtle)',
        fontSize: '11px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>💰</span>
          <strong
            style={{
              fontSize: '12px',
              color: isBlocked ? 'var(--status-danger-text, #991b1b)' : 'var(--text-primary)',
            }}
          >
            Presupuesto y Costes RONIN (Ventana UTC)
          </strong>
        </div>

        {isBlocked && (
          <span
            style={{
              fontSize: '9px',
              fontWeight: 700,
              padding: '1px 6px',
              borderRadius: '3px',
              backgroundColor: 'var(--status-danger-bg, #fee2e2)',
              color: 'var(--status-danger-text, #991b1b)',
              border: '1px solid var(--status-danger-border, #fca5a5)',
            }}
          >
            BLOQUEO: budget.exceed
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px' }}>
        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Presupuesto Restante</span>
          <strong
            style={{
              fontSize: '12px',
              color:
                effectiveBudgetLeft === null
                  ? 'var(--text-muted)'
                  : effectiveBudgetLeft > 0
                  ? 'var(--status-success-text)'
                  : 'var(--status-danger-text, #991b1b)',
            }}
          >
            {effectiveBudgetLeft !== null ? (
              `$${effectiveBudgetLeft.toFixed(2)} USD`
            ) : (
              <span style={{ fontSize: '10px', fontStyle: 'italic', fontWeight: 500 }}>
                No disponible en tablero (requiere endpoint RFC)
              </span>
            )}
          </strong>
        </div>

        {costEstimateUsd !== null && costEstimateUsd !== undefined && (
          <div>
            <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Coste Estimado Intento</span>
            <strong style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
              ${costEstimateUsd.toFixed(2)} USD
            </strong>
          </div>
        )}

        <div>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', display: 'block' }}>Coste Real Medido</span>
          <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No disponible (telemetría de consumo pendiente)
          </span>
        </div>
      </div>

      {isBlocked && (
        <div
          style={{
            padding: '6px 8px',
            borderRadius: '4px',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--status-danger-border, #fca5a5)',
            color: 'var(--status-danger-text, #991b1b)',
            fontSize: '11px',
            fontWeight: 500,
          }}
        >
          ⚠️ <strong>Bloqueo Presupuestario:</strong> El coste estimado supera el saldo diario UTC disponible. La
          autorización de gasto adicional está reservada constitucionalmente al CEO (competencia <code>budget.exceed</code>).
        </div>
      )}

      <div style={{ fontSize: '9px', color: 'var(--text-muted)', fontStyle: 'italic', marginTop: '2px' }}>
        * Control presupuestario basado en estimación por intento en ventana diaria UTC. Concurrencia entre stagings
        simultáneos sujeta a carrera transaccional según análisis I5.
      </div>
    </div>
  );
};
