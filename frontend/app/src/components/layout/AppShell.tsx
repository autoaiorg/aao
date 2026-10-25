import React, { useState } from 'react';
import type { DataOrigin, ProjectSummary, PrincipalSummary } from '../../domain/models';
import { BannerAlert } from './BannerAlert';
import { TopBar } from './TopBar';
import { SideNavigation, ActiveNavKey } from './SideNavigation';

export interface AppShellProps {
  origin: DataOrigin;
  onOriginChange: (newOrigin: DataOrigin) => void;
  projects: ProjectSummary[];
  selectedProjectId: string | null;
  onProjectSelect: (projectId: string | null) => void;
  principal: PrincipalSummary | null;
  isAuthenticated: boolean;
  onLogin: (token: string, role: 'AGENT' | 'CEO') => void | Promise<void>;
  onLogout: () => void | Promise<void>;
  activeNav: ActiveNavKey;
  onNavSelect: (nav: ActiveNavKey) => void;
  fetchedAt?: string;
  isFetching?: boolean;
  onRefresh: () => void;
  isOffline?: boolean;
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({
  origin,
  onOriginChange,
  projects,
  selectedProjectId,
  onProjectSelect,
  principal,
  isAuthenticated,
  onLogin,
  onLogout,
  activeNav,
  onNavSelect,
  fetchedAt,
  isFetching,
  onRefresh,
  isOffline,
  children,
}) => {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        backgroundColor: 'var(--bg-app)',
      }}
    >
      <BannerAlert origin={origin} isOffline={isOffline} />

      <TopBar
        origin={origin}
        onOriginChange={onOriginChange}
        projects={projects}
        selectedProjectId={selectedProjectId}
        onProjectSelect={onProjectSelect}
        principal={principal}
        isAuthenticated={isAuthenticated}
        onLogin={onLogin}
        onLogout={onLogout}
        fetchedAt={fetchedAt}
        isFetching={isFetching}
        onRefresh={onRefresh}
        onToggleSidebar={() => setMobileSidebarOpen((prev) => !prev)}
      />

      <div style={{ display: 'flex', flex: 1, position: 'relative' }}>
        <SideNavigation
          activeKey={activeNav}
          onSelect={onNavSelect}
          isOpen={mobileSidebarOpen}
          onClose={() => setMobileSidebarOpen(false)}
        />

        <main
          id="main-content"
          role="main"
          style={{
            flex: 1,
            padding: '24px 32px',
            maxWidth: '1600px',
            width: '100%',
            margin: '0 auto',
            overflowY: 'auto',
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
};
