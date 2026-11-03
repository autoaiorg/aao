import React from 'react';

export type ActiveNavKey =
  | 'dashboard'
  | 'projects'
  | 'kanban'
  | 'organization'
  | 'decisions'
  | 'alerts'
  | 'audit'
  | 'operations'
  | 'office3d'
  | 'settings';

export interface NavItem {
  key: ActiveNavKey;
  label: string;
  badge?: string;
  isPhaseFuture?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'office3d', label: 'Oficina Virtual 3D' },
  { key: 'dashboard', label: 'Resumen Ejecutivo' },
  { key: 'projects', label: 'Proyectos' },
  { key: 'kanban', label: 'Trabajo / Tablero' },
  { key: 'organization', label: 'Organización' },
  { key: 'decisions', label: 'Decisiones' },
  { key: 'alerts', label: 'Alertas' },
  { key: 'audit', label: 'Auditoría' },
  { key: 'operations', label: 'Operaciones' },
  { key: 'settings', label: 'Configuración' },
];

export interface SideNavigationProps {
  activeKey: ActiveNavKey;
  onSelect: (key: ActiveNavKey) => void;
  isOpen?: boolean;
  onClose?: () => void;
}

export const SideNavigation: React.FC<SideNavigationProps> = ({
  activeKey,
  onSelect,
  isOpen = false,
  onClose,
}) => {
  if (!isOpen) {
    return null;
  }

  return (
    <aside
      aria-label="Navegación principal de AAO"
      style={{
        position: 'fixed',
        top: 'calc(var(--header-height, 48px) + 8px)',
        left: '12px',
        zIndex: 65,
        width: '240px',
        maxHeight: 'calc(100vh - var(--header-height, 48px) - 24px)',
        backgroundColor: 'rgba(15, 23, 42, 0.94)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(56, 189, 248, 0.38)',
        borderRadius: 'var(--radius-lg, 12px)',
        boxShadow: '0 16px 36px -6px rgba(0, 0, 0, 0.75)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '12px',
        overflowY: 'auto',
      }}
      className="aao-sidebar open"
    >
      <div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '4px 6px 10px 6px',
            borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
            marginBottom: '8px',
          }}
        >
          <strong style={{ fontSize: '11px', color: '#38bdf8', letterSpacing: '0.6px', textTransform: 'uppercase' }}>
            🎮 Paneles del Sistema
          </strong>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar menú de paneles"
              style={{
                padding: '2px 7px',
                borderRadius: '4px',
                fontSize: '12px',
                color: '#cbd5e1',
                background: 'rgba(30, 41, 59, 0.8)',
                border: '1px solid rgba(148, 163, 184, 0.3)',
              }}
            >
              ✕
            </button>
          )}
        </div>

        <nav role="navigation">
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {NAV_ITEMS.map((item) => {
              const isActive = activeKey === item.key;
              return (
                <li key={item.key}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(item.key);
                      if (onClose) onClose();
                    }}
                    aria-current={isActive ? 'page' : undefined}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '13px',
                      fontWeight: isActive ? 700 : 500,
                      color: isActive ? '#ffffff' : 'var(--text-secondary)',
                      backgroundColor: isActive ? '#0284c7' : 'transparent',
                      border: '1px solid transparent',
                      borderColor: isActive ? '#7dd3fc' : 'transparent',
                      textAlign: 'left',
                      transition: 'background-color 0.15s ease, color 0.15s ease',
                    }}
                  >
                    <span>{item.label}</span>
                    {item.badge && (
                      <span
                        style={{
                          fontSize: '10px',
                          padding: '1px 5px',
                          borderRadius: 'var(--radius-full)',
                          backgroundColor: 'var(--bg-subtle)',
                          color: 'var(--text-muted)',
                          fontWeight: 600,
                        }}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>

      {/* Footer information */}
      <div
        style={{
          marginTop: '12px',
          paddingTop: '10px',
          borderTop: '1px solid var(--border-subtle)',
          fontSize: '11px',
          color: 'var(--text-muted)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <div>
          <strong style={{ color: '#e2e8f0' }}>AAO Spatial HUD</strong>
        </div>
        <div>Control Táctico 3D</div>
      </div>
    </aside>
  );
};
