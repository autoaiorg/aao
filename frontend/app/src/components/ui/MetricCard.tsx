import React from 'react';
import { Card } from './Card';

export interface MetricCardProps {
  title: string;
  value?: number | string | null;
  statusLabel?: string;
  isUnavailable?: boolean;
  unavailableReason?: string;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  statusLabel,
  isUnavailable,
  unavailableReason,
  subtitle,
  icon,
}) => {
  return (
    <Card elevation="sm" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: 'var(--text-muted)',
          fontSize: '13px',
          fontWeight: 500,
        }}
      >
        <span>{title}</span>
        {icon && <span style={{ opacity: 0.8 }}>{icon}</span>}
      </div>

      <div style={{ margin: '4px 0' }}>
        {isUnavailable ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '14px', fontStyle: 'italic' }}>
            {unavailableReason || 'No disponible'}
          </div>
        ) : value !== undefined && value !== null ? (
          <div
            style={{
              fontSize: '28px',
              fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.1,
            }}
          >
            {value}
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>—</div>
        )}
      </div>

      {(subtitle || statusLabel) && (
        <div
          style={{
            fontSize: '12px',
            color: 'var(--text-secondary)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {subtitle && <span>{subtitle}</span>}
          {statusLabel && (
            <span style={{ fontWeight: 600, color: 'var(--accent)' }}>{statusLabel}</span>
          )}
        </div>
      )}
    </Card>
  );
};
