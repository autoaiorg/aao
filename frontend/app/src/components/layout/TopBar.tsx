import React, { useState } from 'react';
import type { DataOrigin, ProjectSummary, PrincipalSummary } from '../../domain/models';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Card';
import { OriginBadge, FreshnessIndicator } from '../ui/OriginBadge';

export interface TopBarProps {
  origin: DataOrigin;
  onOriginChange: (newOrigin: DataOrigin) => void;
  projects: ProjectSummary[];
  selectedProjectId: string | null;
  onProjectSelect: (projectId: string | null) => void;
  principal: PrincipalSummary | null;
  isAuthenticated: boolean;
  onLogin: (token: string, role: 'AGENT' | 'CEO') => void;
  onLogout: () => void;
  fetchedAt?: string;
  isFetching?: boolean;
  onRefresh: () => void;
  onToggleSidebar?: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  origin,
  onOriginChange,
  projects,
  selectedProjectId,
  onProjectSelect,
  principal,
  isAuthenticated,
  onLogin,
  onLogout,
  fetchedAt,
  isFetching,
  onRefresh,
  onToggleSidebar,
}) => {
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [inputToken, setInputToken] = useState('');
  const [selectedRole, setSelectedRole] = useState<'AGENT' | 'CEO'>('AGENT');

  const handleLoginSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputToken.trim()) return;
    onLogin(inputToken.trim(), selectedRole);
    setInputToken('');
    setShowLoginModal(false);
  };

  return (
    <header
      style={{
        height: 'var(--header-height)',
        backgroundColor: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label="Alternar menú lateral"
            style={{
              padding: '6px',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
            }}
          >
            ☰
          </button>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '6px',
              backgroundColor: 'var(--primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-inverse)',
              fontWeight: 800,
              fontSize: '14px',
            }}
          >
            A
          </div>
          <span style={{ fontWeight: 700, fontSize: '16px', color: 'var(--text-primary)' }}>
            AAO
          </span>
          <span
            style={{
              fontSize: '12px',
              color: 'var(--text-muted)',
              borderLeft: '1px solid var(--border-strong)',
              paddingLeft: '8px',
            }}
          >
            Centro de Mando
          </span>
        </div>

        {/* Project Selector */}
        <div style={{ marginLeft: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label htmlFor="topbar-project-select" className="sr-only">
            Seleccionar Proyecto
          </label>
          <select
            id="topbar-project-select"
            value={selectedProjectId || ''}
            onChange={(e) => onProjectSelect(e.target.value || null)}
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-strong)',
              backgroundColor: 'var(--bg-app)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              maxWidth: '220px',
            }}
          >
            <option value="">Todos los proyectos (Ámbito global)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Environment toggle */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            backgroundColor: 'var(--bg-muted)',
            padding: '2px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <button
            type="button"
            onClick={() => onOriginChange('live')}
            style={{
              padding: '4px 8px',
              fontSize: '12px',
              borderRadius: 'var(--radius-sm)',
              fontWeight: origin === 'live' ? 700 : 400,
              backgroundColor: origin === 'live' ? 'var(--bg-surface)' : 'transparent',
              color: origin === 'live' ? 'var(--text-primary)' : 'var(--text-secondary)',
              boxShadow: origin === 'live' ? 'var(--shadow-sm)' : 'none',
            }}
          >
            LIVE
          </button>
          <button
            type="button"
            onClick={() => onOriginChange('demo')}
            style={{
              padding: '4px 8px',
              fontSize: '12px',
              borderRadius: 'var(--radius-sm)',
              fontWeight: origin === 'demo' ? 700 : 400,
              backgroundColor: origin === 'demo' ? 'var(--status-demo-bg)' : 'transparent',
              color: origin === 'demo' ? 'var(--status-demo-text)' : 'var(--text-secondary)',
              boxShadow: origin === 'demo' ? 'var(--shadow-sm)' : 'none',
            }}
          >
            DEMO
          </button>
        </div>

        <OriginBadge origin={origin} />

        <FreshnessIndicator
          fetchedAt={fetchedAt}
          isFetching={isFetching}
          onRefresh={onRefresh}
        />

        {/* Identity & Session */}
        {isAuthenticated && principal ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Badge variant="neutral" size="md">
              <span style={{ fontFamily: 'monospace' }}>
                {principal.kind}: {principal.principal_id.slice(0, 14)}...
              </span>
            </Badge>
            <Button size="sm" variant="ghost" onClick={onLogout} title="Cerrar sesión en memoria">
              Desconectar
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setShowLoginModal(true)}>
            Credencial de Acceso
          </Button>
        )}
      </div>

      {/* Volatile Auth Modal */}
      {showLoginModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="auth-modal-title"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-surface)',
              padding: '24px',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '440px',
              width: '90%',
              boxShadow: 'var(--shadow-lg)',
              border: '1px solid var(--border-strong)',
            }}
          >
            <h3 id="auth-modal-title" style={{ fontSize: '18px', marginBottom: '8px' }}>
              Autenticación en Memoria Volátil
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              El token se retiene exclusivamente en la memoria de esta pestaña y nunca se persiste en disco, almacenamiento local ni cookies.
            </p>

            <form onSubmit={handleLoginSubmit}>
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}>
                  Tipo de Credencial
                </label>
                <div style={{ display: 'flex', gap: '16px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                    <input
                      type="radio"
                      name="role"
                      value="AGENT"
                      checked={selectedRole === 'AGENT'}
                      onChange={() => setSelectedRole('AGENT')}
                    />
                    AGENT (Token individual X-Agent-Token)
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                    <input
                      type="radio"
                      name="role"
                      value="CEO"
                      checked={selectedRole === 'CEO'}
                      onChange={() => setSelectedRole('CEO')}
                    />
                    CEO (Bearer de desarrollo X-CEO-Token)
                  </label>
                </div>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label htmlFor="auth-token-input" style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}>
                  Valor del Token Secreto
                </label>
                <input
                  id="auth-token-input"
                  type="password"
                  value={inputToken}
                  onChange={(e) => setInputToken(e.target.value)}
                  placeholder="Introduzca su token..."
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-strong)',
                    backgroundColor: 'var(--bg-app)',
                    color: 'var(--text-primary)',
                  }}
                  autoFocus
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <Button type="button" variant="ghost" onClick={() => setShowLoginModal(false)}>
                  Cancelar
                </Button>
                <Button type="submit" variant="primary">
                  Autenticar en Memoria
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
};
