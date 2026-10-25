import React, { useState, useMemo, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataOrigin, ProjectSummary, CeoOverview } from '../domain/models';
import { useAuth } from '../auth/AuthContext';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import { MockAaoDemoAdapter } from '../data/adapters/demo/MockAaoDemoAdapter';
import type { AaoReadPort } from '../data/ports/AaoReadPort';

import { AppShell } from '../components/layout/AppShell';
import type { ActiveNavKey } from '../components/layout/SideNavigation';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';

import { CeoDashboard } from '../features/dashboard/CeoDashboard';
import { ProjectsView } from '../features/projects/ProjectsView';
import { ProjectDetailView } from '../features/projects/ProjectDetailView';
import { KanbanView } from '../features/kanban/KanbanView';
import { DecisionsView } from '../features/decisions/DecisionsView';
import { AlertsView } from '../features/alerts/AlertsView';
import { AuditView } from '../features/audit/AuditView';
import { OperationsView } from '../features/operations/OperationsView';
import { OrganizationView } from '../features/organization/OrganizationView';
import { VirtualOfficeView } from '../features/future/VirtualOfficeView';
import { ViewSettingsView } from '../features/future/ViewSettingsView';

export const App: React.FC = () => {
  const queryClient = useQueryClient();
  const { token, role, isAuthenticated, sessionId, setCredentials, logout } = useAuth();

  const [origin, setOrigin] = useState<DataOrigin>('live');
  const [activeNav, setActiveNav] = useState<ActiveNavKey>('dashboard');
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [detailedProjectId, setDetailedProjectId] = useState<string | null>(null);
  const [staleTimeSeconds, setStaleTimeSeconds] = useState<number>(15);

  // Initialize Port Adapter depending on origin
  const port: AaoReadPort = useMemo(() => {
    if (origin === 'demo') {
      return new MockAaoDemoAdapter(40);
    }
    return new HttpAaoLiveAdapter({
      getToken: () => token,
      getAuthRole: () => role,
      requireAuth: true,
      onUnauthorized: () => {
        logout();
        queryClient.cancelQueries();
        queryClient.clear();
      },
    });
  }, [origin, token, role, logout, queryClient]);

  // P0 Finding 2: Switch origin cleanly with immediate cancellation of in-flight queries & cache purge
  const handleOriginChange = useCallback(
    (newOrigin: DataOrigin) => {
      if (newOrigin === origin) return;

      if (port instanceof HttpAaoLiveAdapter) {
        port.abortAll();
      }
      queryClient.cancelQueries();
      queryClient.clear();

      setSelectedProjectId(null);
      setDetailedProjectId(null);
      setOrigin(newOrigin);
    },
    [origin, port, queryClient]
  );

  const handleLogout = useCallback(() => {
    if (port instanceof HttpAaoLiveAdapter) {
      port.abortAll();
    }
    queryClient.cancelQueries();
    queryClient.clear();
    setSelectedProjectId(null);
    setDetailedProjectId(null);
    logout();
  }, [port, queryClient, logout]);

  // P0 Finding 2 & P0 Finding 4: Query keys bound to sessionId; queries suppressed in LIVE mode until valid session exists
  // Query: Principal
  const principalQuery = useQuery({
    queryKey: ['principal', origin, isAuthenticated, role, sessionId],
    queryFn: () => port.getCurrentPrincipal(),
    enabled: origin === 'demo' || isAuthenticated,
    staleTime: staleTimeSeconds * 1000,
  });

  // Query: Projects List
  const projectsQuery = useQuery({
    queryKey: ['projects', origin, isAuthenticated, sessionId],
    queryFn: () => port.listProjects(),
    enabled: origin === 'demo' || isAuthenticated,
    staleTime: staleTimeSeconds * 1000,
  });

  const projectsList: ProjectSummary[] = useMemo(() => {
    if (projectsQuery.data?.kind === 'ready') {
      return projectsQuery.data.data;
    }
    return [];
  }, [projectsQuery.data]);

  // Query: CEO Overview
  const overviewQuery = useQuery({
    queryKey: ['ceo-overview', origin, selectedProjectId, isAuthenticated, sessionId],
    queryFn: () => port.getCeoOverview(selectedProjectId || undefined),
    enabled: origin === 'demo' || isAuthenticated,
    staleTime: staleTimeSeconds * 1000,
  });

  // Query: Selected Project Board (for Kanban)
  const boardQuery = useQuery({
    queryKey: ['board', origin, selectedProjectId, isAuthenticated, sessionId],
    queryFn: () => {
      if (!selectedProjectId) {
        return Promise.resolve({
          kind: 'empty' as const,
          origin,
          fetchedAt: new Date().toISOString(),
        });
      }
      return port.getProjectBoard(selectedProjectId);
    },
    enabled: (origin === 'demo' || isAuthenticated) && !!selectedProjectId,
    staleTime: staleTimeSeconds * 1000,
  });

  // Query: Detailed Project Capabilities
  const capabilitiesQuery = useQuery({
    queryKey: ['capabilities', origin, detailedProjectId, isAuthenticated, sessionId],
    queryFn: () => {
      if (!detailedProjectId) {
        return Promise.resolve({
          kind: 'empty' as const,
          origin,
          fetchedAt: new Date().toISOString(),
        });
      }
      return port.getProjectCapabilities(detailedProjectId);
    },
    enabled: (origin === 'demo' || isAuthenticated) && !!detailedProjectId,
    staleTime: staleTimeSeconds * 1000,
  });

  // Query: Detailed Project Evaluations
  const evaluationsQuery = useQuery({
    queryKey: ['evaluations', origin, detailedProjectId, isAuthenticated, sessionId],
    queryFn: () => {
      if (!detailedProjectId) {
        return Promise.resolve({
          kind: 'empty' as const,
          origin,
          fetchedAt: new Date().toISOString(),
        });
      }
      return port.getProjectEvaluations(detailedProjectId);
    },
    enabled: (origin === 'demo' || isAuthenticated) && !!detailedProjectId,
    staleTime: staleTimeSeconds * 1000,
  });

  // Query: Organization Structure (Phase F3)
  const organizationQuery = useQuery({
    queryKey: ['organization', origin, isAuthenticated, sessionId],
    queryFn: () => port.getOrganizationStructure(),
    enabled: true,
    staleTime: staleTimeSeconds * 1000,
  });

  // Refresh handler
  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries();
  }, [queryClient]);

  const detailedProject = projectsList.find((p) => p.id === detailedProjectId);
  const selectedProject = projectsList.find((p) => p.id === selectedProjectId);

  const principalData =
    principalQuery.data?.kind === 'ready' ? principalQuery.data.data : null;

  const fallbackOverview: CeoOverview = useMemo(
    () => ({
      projects: { kind: 'empty', origin, fetchedAt: '' },
      work: { kind: 'empty', origin, fetchedAt: '' },
      governance: { kind: 'empty', origin, fetchedAt: '' },
      operations: { kind: 'empty', origin, fetchedAt: '' },
      alerts: { kind: 'empty', origin, fetchedAt: '' },
      decisions: { kind: 'empty', origin, fetchedAt: '' },
    }),
    [origin]
  );

  return (
    <AppShell
      origin={origin}
      onOriginChange={handleOriginChange}
      projects={projectsList}
      selectedProjectId={selectedProjectId}
      onProjectSelect={setSelectedProjectId}
      principal={principalData}
      isAuthenticated={isAuthenticated}
      onLogin={setCredentials}
      onLogout={handleLogout}
      activeNav={activeNav}
      onNavSelect={(nav) => {
        setDetailedProjectId(null);
        setActiveNav(nav);
      }}
      fetchedAt={overviewQuery.data?.projects.kind === 'ready' ? overviewQuery.data.projects.fetchedAt : undefined}
      isFetching={overviewQuery.isFetching || boardQuery.isFetching || organizationQuery.isFetching}
      onRefresh={handleRefresh}
    >
      <ErrorBoundary>
        {activeNav === 'dashboard' && (
          <>
            {origin === 'live' && !isAuthenticated && (
              <div
                role="status"
                aria-label="Aviso de sesión en espera de credencial"
                style={{
                  marginBottom: '16px',
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border-focus)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                }}
              >
                <span style={{ fontSize: '18px' }} aria-hidden="true">🔒</span>
                <div>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)', display: 'block' }}>
                    Sesión LIVE en espera de credencial
                  </strong>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    No se emiten consultas contra la API hasta autenticar la sesión en memoria volátil. Use el botón &quot;Credencial de Acceso&quot; superior.
                  </span>
                </div>
              </div>
            )}
            <CeoDashboard
              overview={overviewQuery.data || fallbackOverview}
              projects={projectsList}
              selectedProjectId={selectedProjectId}
              onSelectProject={setSelectedProjectId}
              onNavigateTo={(target) => {
                if (target === 'kanban') setActiveNav('kanban');
                else if (target === 'projects') setActiveNav('projects');
                else if (target === 'decisions') setActiveNav('decisions');
                else if (target === 'audit') setActiveNav('audit');
                else if (target === 'operations') setActiveNav('operations');
              }}
            />
          </>
        )}

        {activeNav === 'projects' && !detailedProjectId && (
          <ProjectsView
            projects={projectsList}
            selectedProjectId={selectedProjectId}
            onSelectProject={setSelectedProjectId}
            onViewDetails={(id) => setDetailedProjectId(id)}
          />
        )}

        {activeNav === 'projects' && detailedProjectId && detailedProject && (
          <ProjectDetailView
            project={detailedProject}
            capabilitiesState={capabilitiesQuery.data || { kind: 'empty', origin, fetchedAt: '' }}
            evaluationsState={evaluationsQuery.data || { kind: 'empty', origin, fetchedAt: '' }}
            onBack={() => setDetailedProjectId(null)}
            onOpenKanban={() => {
              setSelectedProjectId(detailedProjectId);
              setActiveNav('kanban');
            }}
            onRefresh={handleRefresh}
          />
        )}

        {activeNav === 'kanban' && (
          <KanbanView
            boardState={boardQuery.data || { kind: 'empty', origin, fetchedAt: '' }}
            selectedProjectId={selectedProjectId}
            projectName={selectedProject?.name}
            onRefresh={handleRefresh}
          />
        )}

        {activeNav === 'decisions' && (
          <DecisionsView
            decisionsState={
              overviewQuery.data?.decisions || {
                kind: 'unavailable',
                reason: 'Sin datos disponibles en esta vista',
                retryable: false,
              }
            }
            onRefresh={handleRefresh}
          />
        )}

        {activeNav === 'alerts' && (
          <AlertsView
            alertsState={
              overviewQuery.data?.alerts || {
                kind: 'unavailable',
                reason: 'Sin datos de alertas disponibles',
                retryable: false,
              }
            }
            onRefresh={handleRefresh}
          />
        )}

        {activeNav === 'audit' && <AuditView />}

        {activeNav === 'operations' && <OperationsView onRefreshAll={handleRefresh} />}

        {activeNav === 'organization' && (
          <OrganizationView
            orgState={
              organizationQuery.data || {
                kind: 'unavailable',
                reason:
                  'El núcleo canónico de AAO no expone aún endpoints públicos para la estructura organizativa ni la telemetría de agentes (F3).',
                retryable: false,
              }
            }
            onRefresh={handleRefresh}
          />
        )}

        {activeNav === 'office3d' && <VirtualOfficeView />}

        {activeNav === 'settings' && (
          <ViewSettingsView
            staleTimeSeconds={staleTimeSeconds}
            onStaleTimeChange={setStaleTimeSeconds}
            onClearCache={() => {
              queryClient.cancelQueries();
              queryClient.clear();
            }}
          />
        )}
      </ErrorBoundary>
    </AppShell>
  );
};
