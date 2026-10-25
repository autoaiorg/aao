import React from 'react';
import type { DataOrigin } from '../../domain/models';

export interface BannerAlertProps {
  origin: DataOrigin;
  isOffline?: boolean;
}

export const BannerAlert: React.FC<BannerAlertProps> = ({ origin, isOffline }) => {
  return (
    <div>
      {origin === 'demo' && (
        <div
          role="status"
          aria-live="polite"
          style={{
            backgroundColor: 'var(--status-demo-bg)',
            color: 'var(--status-demo-text)',
            borderBottom: '2px solid var(--status-demo-border)',
            padding: '8px 16px',
            textAlign: 'center',
            fontSize: '13px',
            fontWeight: 700,
            letterSpacing: '0.5px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
          }}
        >
          <span>⚠ DEMO · DATOS SIMULADOS · SIN CONEXIÓN AL NÚCLEO</span>
          <span style={{ fontWeight: 400, fontSize: '12px' }}>
            (Las tareas, agentes y evidencias mostradas son ficticias y no reflejan el estado de producción de AAO)
          </span>
        </div>
      )}

      {isOffline && (
        <div
          role="alert"
          style={{
            backgroundColor: 'var(--status-error-bg)',
            color: 'var(--status-error-text)',
            borderBottom: '1px solid var(--status-error-border)',
            padding: '6px 16px',
            textAlign: 'center',
            fontSize: '12px',
            fontWeight: 600,
          }}
        >
          Sin conexión de red con el backend. Los datos mostrados pueden estar desactualizados.
        </div>
      )}
    </div>
  );
};
