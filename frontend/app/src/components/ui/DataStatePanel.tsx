import React from 'react';
import type { DataState } from '../../domain/models';
import { Card } from './Card';
import { Button } from './Button';

export interface DataStatePanelProps<T> {
  state: DataState<T>;
  onRetry?: () => void;
  renderReady: (data: T) => React.ReactNode;
  renderEmpty?: () => React.ReactNode;
  title?: string;
}

export function DataStatePanel<T>({
  state,
  onRetry,
  renderReady,
  renderEmpty,
  title,
}: DataStatePanelProps<T>) {
  if (state.kind === 'ready') {
    return <>{renderReady(state.data)}</>;
  }

  if (state.kind === 'empty') {
    if (renderEmpty) {
      return <>{renderEmpty()}</>;
    }
    return (
      <Card elevation="none" style={{ textAlign: 'center', padding: '32px 16px' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
          No se encontraron registros para mostrar.
        </p>
      </Card>
    );
  }

  if (state.kind === 'unavailable') {
    return (
      <Card
        elevation="none"
        style={{
          backgroundColor: 'var(--bg-muted)',
          border: '1px dashed var(--border-strong)',
          padding: '24px',
          textAlign: 'center',
        }}
      >
        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
          {title ? `${title} — ` : ''}Dato no disponible en esta fase
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '500px', margin: '0 auto' }}>
          {state.reason}
        </p>
        {state.retryable && onRetry && (
          <div style={{ marginTop: '12px' }}>
            <Button size="sm" variant="outline" onClick={onRetry}>
              Reintentar comprobación
            </Button>
          </div>
        )}
      </Card>
    );
  }

  if (state.kind === 'forbidden') {
    return (
      <Card
        elevation="none"
        style={{
          backgroundColor: 'var(--status-warning-bg)',
          border: '1px solid var(--status-warning-border)',
          padding: '20px',
        }}
      >
        <div style={{ fontWeight: 600, color: 'var(--status-warning-text)', marginBottom: '4px' }}>
          Acceso no autorizado (HTTP 403)
        </div>
        <p style={{ color: 'var(--status-warning-text)', fontSize: '13px' }}>{state.reason}</p>
      </Card>
    );
  }

  // Error state
  return (
    <Card
      elevation="none"
      style={{
        backgroundColor: 'var(--status-error-bg)',
        border: '1px solid var(--status-error-border)',
        padding: '20px',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--status-error-text)', marginBottom: '4px' }}>
        Error al cargar datos {state.code ? `(${state.code})` : ''}
      </div>
      <p style={{ color: 'var(--status-error-text)', fontSize: '13px', marginBottom: '12px' }}>
        {state.message}
      </p>
      {state.retryable && onRetry && (
        <Button size="sm" variant="danger" onClick={onRetry}>
          Reintentar
        </Button>
      )}
    </Card>
  );
}
