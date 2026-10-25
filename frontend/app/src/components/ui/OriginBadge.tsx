import React from 'react';
import { Badge } from './Card';
import type { DataOrigin } from '../../domain/models';

export interface OriginBadgeProps {
  origin: DataOrigin;
  className?: string;
}

export const OriginBadge: React.FC<OriginBadgeProps> = ({ origin, className = '' }) => {
  if (origin === 'demo') {
    return (
      <Badge variant="demo" size="md" className={className}>
        DEMO · SIMULADO
      </Badge>
    );
  }

  return (
    <Badge variant="info" size="md" className={className}>
      LIVE · AUTORIZADO
    </Badge>
  );
};

export interface FreshnessIndicatorProps {
  fetchedAt?: string;
  isFetching?: boolean;
  onRefresh?: () => void;
  className?: string;
}

export const FreshnessIndicator: React.FC<FreshnessIndicatorProps> = ({
  fetchedAt,
  isFetching,
  onRefresh,
  className = '',
}) => {
  const formattedTime = fetchedAt
    ? new Date(fetchedAt).toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : 'No disponible';

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '12px',
        color: 'var(--text-secondary)',
      }}
      className={`aao-freshness ${className}`}
    >
      <span>
        Actualizado: <strong>{formattedTime}</strong>
      </span>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={isFetching}
          aria-label="Actualizar datos"
          style={{
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-muted)',
            cursor: isFetching ? 'wait' : 'pointer',
            fontSize: '11px',
          }}
        >
          {isFetching ? 'Cargando...' : '↻ Actualizar'}
        </button>
      )}
    </div>
  );
};
