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
  { key: 'dashboard', label: 'Resumen' },
  { key: 'projects', label: 'Proyectos' },
  { key: 'kanban', label: 'Trabajo / Tablero' },
  { key: 'organization', label: 'Organización', badge: 'F3', isPhaseFuture: true },
  { key: 'decisions', label: 'Decisiones' },
  { key: 'alerts', label: 'Alertas' },
  { key: 'audit', label: 'Auditoría' },
  { key: 'operations', label: 'Operaciones' },
  { key: 'office3d', label: 'Oficina Virtual', badge: 'F4', isPhaseFuture: true },
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
  isOpen = true,
  onClose,
}) => {
  return (
    <aside
      aria-label="Navegación principal de AAO"
      style={{
        width: 'var(--sidebar-width)',
        backgroundColor: 'var(--bg-surface)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        flexShrink: 0,
        height: 'calc(100vh - var(--header-height))',
        position: 'sticky',
        top: 'var(--header-height)',
        padding: '16px 12px',
      }}
      className={`aao-sidebar ${isOpen ? 'open' : 'closed'}`}
    >
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
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                    backgroundColor: isActive ? 'var(--bg-muted)' : 'transparent',
                    border: '1px solid transparent',
                    borderColor: isActive ? 'var(--border-subtle)' : 'transparent',
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

      {/* Footer information */}
      <div
        style={{
          padding: '12px',
          borderTop: '1px solid var(--border-subtle)',
          fontSize: '11px',
          color: 'var(--text-muted)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <div>
          <strong>AAO Control Center</strong>
        </div>
        <div>Fase F1-F2 · Solo Lectura</div>
        <div style={{ marginTop: '4px' }}>
          <a
            href="/"
            style={{ color: 'var(--accent)', textDecoration: 'none' }}
            title="Abrir la consola operativa anterior"
          >
            ← Consola Clásica (/)
          </a>
        </div>
      </div>
    </aside>
  );
};
