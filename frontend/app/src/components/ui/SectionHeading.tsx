import React from 'react';
import type { EvidenceRef } from '../../domain/models';

export interface EvidenceLinkProps {
  evidence: EvidenceRef;
  className?: string;
}

export const EvidenceLink: React.FC<EvidenceLinkProps> = ({ evidence, className = '' }) => {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 8px',
        fontSize: '11px',
        fontFamily: 'monospace',
        backgroundColor: 'var(--bg-muted)',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-subtle)',
      }}
      className={`aao-evidence-link ${className}`}
    >
      <span style={{ color: 'var(--text-muted)' }}>evidencia:</span>
      <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{evidence.source}</span>
      {evidence.exactSha && (
        <span style={{ color: 'var(--accent)' }}>
          #{evidence.exactSha.slice(0, 7)}
        </span>
      )}
    </div>
  );
};

export interface PermissionNoticeProps {
  message?: string;
}

export const PermissionNotice: React.FC<PermissionNoticeProps> = ({
  message = 'Esta vista observa el estado del sistema según las credenciales suministradas; no otorga autoridad de ejecución ni promueve cambios.',
}) => {
  return (
    <div
      role="note"
      style={{
        backgroundColor: 'var(--bg-muted)',
        borderLeft: '3px solid var(--accent)',
        padding: '8px 12px',
        fontSize: '12px',
        color: 'var(--text-secondary)',
        borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
      }}
    >
      <strong>Límite de Autoridad:</strong> {message}
    </div>
  );
};

export interface SectionHeadingProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export const SectionHeading: React.FC<SectionHeadingProps> = ({ title, subtitle, action }) => {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: '16px',
        flexWrap: 'wrap',
        gap: '8px',
      }}
    >
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
          {title}
        </h2>
        {subtitle && (
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
};

export const Skeleton: React.FC<{ height?: string; width?: string; borderRadius?: string }> = ({
  height = '20px',
  width = '100%',
  borderRadius = 'var(--radius-sm)',
}) => {
  return (
    <div
      style={{
        height,
        width,
        borderRadius,
        backgroundColor: 'var(--bg-muted)',
        animation: 'pulse 1.5s infinite ease-in-out',
      }}
    />
  );
};
