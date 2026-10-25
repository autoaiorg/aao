import React from 'react';
import type { DecisionSummary, DataState } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { DataStatePanel } from '../../components/ui/DataStatePanel';
import { Badge } from '../../components/ui/Card';

export interface DecisionsViewProps {
  decisionsState: DataState<DecisionSummary[]>;
  onRefresh: () => void;
}

export const DecisionsView: React.FC<DecisionsViewProps> = ({ decisionsState, onRefresh }) => {
  const categoryLabels: Record<DecisionSummary['category'], { label: string; variant: 'warning' | 'info' | 'error' | 'neutral' }> = {
    ceo_pending: { label: 'Pendiente de Decisión del CEO', variant: 'warning' },
    auditor_pending: { label: 'Pendiente de Auditoría', variant: 'info' },
    policy_blocked: { label: 'Bloqueado por Política', variant: 'error' },
    informational: { label: 'Informativo', variant: 'neutral' },
    unknown: { label: 'Estado No Certificado', variant: 'neutral' },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Centro de Decisiones"
          subtitle="Modo consultivo: registro transparente de decisiones, revisiones y propuestas de gobierno"
        />
        <PermissionNotice message="Esta vista es exclusivamente informativa. La aprobación de mandatos, activación de niveles R2/R3 o promociones son decisiones reservadas al CEO o sujetas a auditoría formal." />
      </div>

      <DataStatePanel
        state={decisionsState}
        onRetry={onRefresh}
        title="Decisiones y Propuestas"
        renderReady={(decisions) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {decisions.map((dec) => {
              const meta = categoryLabels[dec.category] || categoryLabels.unknown;
              return (
                <Card key={dec.id} elevation="sm">
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: '8px',
                      flexWrap: 'wrap',
                      gap: '8px',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <Badge variant={meta.variant}>{meta.label}</Badge>
                        <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                          ID: {dec.id}
                        </span>
                      </div>
                      <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {dec.title}
                      </h3>
                    </div>

                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {new Date(dec.createdAt).toLocaleString('es-ES')}
                    </div>
                  </div>

                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {dec.description}
                  </p>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: '12px',
                      paddingTop: '8px',
                      borderTop: '1px solid var(--border-subtle)',
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    <span>
                      Sujeto / Recurso: <strong style={{ fontFamily: 'monospace' }}>{dec.subjectId}</strong>
                    </span>
                    {dec.proposedBy && <span>Propuesto por: {dec.proposedBy}</span>}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      />
    </div>
  );
};
