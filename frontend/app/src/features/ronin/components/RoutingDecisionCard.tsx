import React from 'react';
import type { ModelRoutingRecord } from '../modelProfile';

export interface RoutingDecisionCardProps {
  decision: ModelRoutingRecord;
}

export const RoutingDecisionCard: React.FC<RoutingDecisionCardProps> = ({ decision }) => {
  const hasRecommendation = Boolean(decision.capability_id);

  return (
    <div
      role="region"
      aria-label="Decisión consultiva de enrutamiento de modelo RONIN"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '12px',
        borderRadius: 'var(--radius-md, 6px)',
        backgroundColor: 'var(--bg-muted)',
        border: '1px solid var(--border-subtle)',
        fontSize: '12px',
      }}
    >
      {/* Header & Non-Authorization Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
            <span style={{ fontSize: '14px' }}>🧭</span>
            <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
              Recomendación del Router RONIN
            </strong>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Requisitos: Rol <code style={{ color: 'var(--text-primary)' }}>{decision.role}</code> · Seat{' '}
            <code style={{ color: 'var(--text-primary)' }}>{decision.seat}</code>
          </span>
        </div>

        {/* Fundamental Rule: execution_authorized: false */}
        <span
          style={{
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm, 4px)',
            backgroundColor: 'var(--status-warning-bg)',
            color: 'var(--status-warning-text)',
            border: '1px solid var(--status-warning-border)',
            fontSize: '10px',
            fontWeight: 700,
            textAlign: 'right',
          }}
          title="El router de modelos no otorga autorización de ejecución ni mutación de estado."
        >
          EJECUCIÓN NO AUTORIZADA (CONSULTIVO)
        </span>
      </div>

      {/* Contract Inconsistency Alert (CEO Requirement 5) */}
      {decision.hasContractInconsistency && (
        <div
          role="alert"
          style={{
            padding: '8px 10px',
            borderRadius: '4px',
            backgroundColor: 'var(--status-danger-bg, #fee2e2)',
            border: '1px solid var(--status-danger-border, #fca5a5)',
            color: 'var(--status-danger-text, #991b1b)',
            fontSize: '11px',
            fontWeight: 600,
            lineHeight: 1.4,
          }}
        >
          🛑 <strong>Inconsistencia de Contrato:</strong> {decision.contractInconsistencyReason}
        </div>
      )}

      {/* Recommended Capability or No-Recommendation Reason */}
      <div
        style={{
          padding: '8px 10px',
          borderRadius: 'var(--radius-sm, 4px)',
          backgroundColor: hasRecommendation ? 'var(--status-success-bg)' : 'var(--bg-surface)',
          border: hasRecommendation
            ? '1px solid var(--status-success-border)'
            : '1px dashed var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>
            {hasRecommendation ? 'Capacidad recomendada:' : 'Resultado del análisis:'}
          </span>
          {decision.budget_left_usd !== null && (
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Presupuesto remanente: <strong>${decision.budget_left_usd} USD</strong>
            </span>
          )}
        </div>

        {hasRecommendation ? (
          <div>
            <strong
              style={{
                fontSize: '13px',
                color: 'var(--status-success-text)',
                fontFamily: 'monospace',
              }}
            >
              {decision.capability_id}@{decision.version}
            </strong>
          </div>
        ) : (
          <div style={{ color: 'var(--status-warning-text)', fontWeight: 600 }}>
            Sin recomendación unívoca (empate o falta de candidatos elegibles). Decisión del PM/CEO requerida.
          </div>
        )}

        {decision.reasons && decision.reasons.length > 0 && (
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            <strong>Fundamento:</strong> {decision.reasons.join(', ')}
          </div>
        )}
      </div>

      {/* Activated Backends */}
      {decision.activated_backends && decision.activated_backends.length > 0 && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Backends verificados activos en nodo:{' '}
          <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>
            {decision.activated_backends.join(', ')}
          </span>
        </div>
      )}

      {/* Rejected Alternatives */}
      {decision.rejected && decision.rejected.length > 0 && (
        <div style={{ marginTop: '4px' }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
            Candidatos Evaluados y Motivos de Descarte ({decision.rejected.length}):
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {decision.rejected.map((rej, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '3px 6px',
                  borderRadius: 'var(--radius-sm, 4px)',
                  backgroundColor: 'var(--bg-surface)',
                  fontSize: '10px',
                }}
              >
                <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)', fontWeight: 500 }}>
                  {rej.candidate}
                </span>
                <span style={{ color: 'var(--status-warning-text)', fontStyle: 'italic' }}>
                  {rej.reason}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {decision.created_at && (
        <div style={{ fontSize: '10px', color: 'var(--text-muted)', textAlign: 'right' }}>
          Fecha de cálculo: {new Date(decision.created_at).toLocaleString('es-ES')}
        </div>
      )}
    </div>
  );
};
