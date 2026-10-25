import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  elevation?: 'none' | 'sm' | 'md';
}

export const Card: React.FC<CardProps> = ({
  children,
  elevation = 'sm',
  className = '',
  style,
  ...props
}) => {
  const shadow =
    elevation === 'none' ? 'none' : elevation === 'md' ? 'var(--shadow-md)' : 'var(--shadow-sm)';

  const cardStyle: React.CSSProperties = {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    boxShadow: shadow,
    padding: 'var(--space-5)',
    ...style,
  };

  return (
    <div style={cardStyle} className={`aao-card ${className}`} {...props}>
      {children}
    </div>
  );
};

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'neutral' | 'success' | 'warning' | 'error' | 'info' | 'demo';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  className = '',
}) => {
  const variantStyles: Record<string, React.CSSProperties> = {
    neutral: {
      backgroundColor: 'var(--bg-muted)',
      color: 'var(--text-secondary)',
      borderColor: 'var(--border-subtle)',
    },
    success: {
      backgroundColor: 'var(--status-success-bg)',
      color: 'var(--status-success-text)',
      borderColor: 'var(--status-success-border)',
    },
    warning: {
      backgroundColor: 'var(--status-warning-bg)',
      color: 'var(--status-warning-text)',
      borderColor: 'var(--status-warning-border)',
    },
    error: {
      backgroundColor: 'var(--status-error-bg)',
      color: 'var(--status-error-text)',
      borderColor: 'var(--status-error-border)',
    },
    info: {
      backgroundColor: 'var(--status-info-bg)',
      color: 'var(--status-info-text)',
      borderColor: 'var(--status-info-border)',
    },
    demo: {
      backgroundColor: 'var(--status-demo-bg)',
      color: 'var(--status-demo-text)',
      borderColor: 'var(--status-demo-border)',
      fontWeight: 700,
    },
  };

  const badgeStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: size === 'sm' ? '2px 6px' : '3px 8px',
    fontSize: size === 'sm' ? '11px' : '12px',
    borderRadius: 'var(--radius-full)',
    border: '1px solid transparent',
    lineHeight: 1.2,
    fontWeight: 500,
    ...variantStyles[variant],
  };

  return (
    <span style={badgeStyle} className={`aao-badge ${className}`}>
      {children}
    </span>
  );
};
