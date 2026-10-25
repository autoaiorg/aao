import React from 'react';
import type { AlertSummary, DataState } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { DataStatePanel } from '../../components/ui/DataStatePanel';
import { Badge } from '../../components/ui/Card';

export interface AlertsViewProps {
  alertsState: DataState<AlertSummary[]>;
  onRefresh: () => void;
}

export const AlertsView: React.FC<AlertsViewProps> = ({ alertsState, onRefresh }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <SectionHeading
          title="Alertas y Notificaciones de Sistema"
          subtitle="Monitoreo y avisos procedentes de los subsistemas y colas de trabajo"
        />
        <PermissionNotice message="Las alertas son informativas y no sustituyen comprobaciones de auditoría ni gates de integración." />
      </div>

      <DataStatePanel
        state={alertsState}
        onRetry={onRefresh}
        title="Alertas Activas"
        renderReady={(alerts) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {alerts.map((al) => (
              <Card key={al.id} elevation="sm">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: '6px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Badge
                      variant={
                        al.severity === 'critical' || al.severity === 'high'
                          ? 'error'
                          : al.severity === 'medium'
                          ? 'warning'
                          : 'info'
                      }
                    >
                      {al.severity.toUpperCase()}
                    </Badge>
                    <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                      {al.title}
                    </strong>
                  </div>

                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {new Date(al.timestamp).toLocaleTimeString('es-ES')}
                  </span>
                </div>

                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {al.description}
                </p>

                <div
                  style={{
                    display: 'flex',
                    gap: '16px',
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    marginTop: '8px',
                    paddingTop: '6px',
                    borderTop: '1px solid var(--border-subtle)',
                  }}
                >
                  <span>Origen: {al.source}</span>
                  <span>Confianza: {al.confidence}</span>
                </div>
              </Card>
            ))}
          </div>
        )}
      />
    </div>
  );
};
