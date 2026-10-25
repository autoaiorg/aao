import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({
  variant = 'secondary',
  size = 'md',
  className = '',
  disabled,
  children,
  ...props
}, ref) => {
  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { padding: '4px 8px', fontSize: '12px', minHeight: '32px' },
    md: { padding: '8px 14px', fontSize: '14px', minHeight: '38px' },
    lg: { padding: '10px 18px', fontSize: '16px', minHeight: '44px' },
  };

  const variantStyles: Record<string, React.CSSProperties> = {
    primary: {
      backgroundColor: 'var(--primary)',
      color: 'var(--text-inverse)',
      border: '1px solid transparent',
    },
    secondary: {
      backgroundColor: 'var(--bg-muted)',
      color: 'var(--text-primary)',
      border: '1px solid var(--border-strong)',
    },
    outline: {
      backgroundColor: 'transparent',
      color: 'var(--accent)',
      border: '1px solid var(--border-strong)',
    },
    danger: {
      backgroundColor: 'var(--status-error-bg)',
      color: 'var(--status-error-text)',
      border: '1px solid var(--status-error-border)',
    },
    ghost: {
      backgroundColor: 'transparent',
      color: 'var(--text-secondary)',
      border: '1px solid transparent',
    },
  };

  const style: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    borderRadius: 'var(--radius-md)',
    fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    transition: 'background-color 0.15s ease, opacity 0.15s ease',
    ...sizeStyles[size],
    ...variantStyles[variant],
  };

  return (
    <button ref={ref} disabled={disabled} style={style} className={`aao-button ${className}`} {...props}>
      {children}
    </button>
  );
});

Button.displayName = 'Button';
