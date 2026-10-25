import React from 'react';
import type { CeoOverview, ProjectSummary } from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { MetricCard } from '../../components/ui/MetricCard';
import { StateDistribution } from '../../components/ui/StateDistribution';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { Button } from '../../components/ui/Button';

export interface CeoDashboardProps {
  overview: CeoOverview;
  projects: ProjectSummary[];
  selectedProjectId: string | null;
  onSelectProject: (id: string | null) => void;
  onNavigateTo: (route: 'projects' | 'kanban' | 'decisions' | 'audit' | 'operations') => void;
}

export const CeoDashboard: React.FC<CeoDashboardProps> = ({
  overview,
  projects,
  selectedProjectId,
  onSelectProject,
  onNavigateTo,
}) => {
  const currentProject = projects.find((p) => p.id === selectedProjectId);

  // Compute work metric values defensively
  const workData = overview.work.kind === 'ready' ? overview.work.data : null;
  const isWorkUnavailable = overview.work.kind === 'unavailable';
  const workUnavailableReason =
    overview.work.kind === 'unavailable' ? overview.work.reason : undefined;

  const projectsCount =
    overview.projects.kind === 'ready' ? overview.projects.data.length : undefined;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Banner / Heading */}
      <div>
        <SectionHeading
          title="Centro de Mando del CEO"
          subtitle={
            selectedProjectId && currentProject
              ? `Visualización enfocada en el proyecto: ${currentProject.name}`
              : 'Vista global consolidada de la organización digital y sus proyectos'
          }
          action={
            selectedProjectId ? (
              <Button size="sm" variant="outline" onClick={() => onSelectProject(null)}>
                Restablecer a vista global
              </Button>
            ) : undefined
          }
        />
        <PermissionNotice message="La interfaz observa el estado del sistema según las credenciales suministradas; no otorga autoridad de ejecución, promoción ni firma de mandatos." />
      </div>

      {/* 4 Metric Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '16px',
        }}
      >
        <MetricCard
          title="Cartera de Proyectos"
          value={projectsCount}
          subtitle={projectsCount !== undefined ? `${projectsCount} activos/visibles` : undefined}
          isUnavailable={overview.projects.kind === 'unavailable'}
          unavailableReason={
            overview.projects.kind === 'unavailable' ? overview.projects.reason : undefined
          }
        />

        <MetricCard
          title="Total de Tareas"
          value={workData ? workData.totalTasks : undefined}
          subtitle={
            workData
              ? `${workData.byStage.IN_PROGRESS} en curso`
              : selectedProjectId
              ? undefined
              : 'Seleccione un proyecto para desglose'
          }
          isUnavailable={isWorkUnavailable}
          unavailableReason={workUnavailableReason}
        />

        <MetricCard
          title="Tareas en Revisión"
          value={workData ? workData.inReviewCount : undefined}
          subtitle={workData ? 'Pendientes de auditoría técnica' : undefined}
          isUnavailable={isWorkUnavailable}
          unavailableReason={workUnavailableReason}
        />

        <MetricCard
          title="Salud de Servicios"
          value={
            overview.operations.kind === 'ready'
              ? overview.operations.data.serviceHealth === 'healthy'
                ? 'Operativo'
                : 'Degradado'
              : undefined
          }
          statusLabel={
            overview.operations.kind === 'ready' && overview.operations.data.readyStatus
              ? 'Conectado'
              : undefined
          }
          isUnavailable={overview.operations.kind === 'unavailable'}
          unavailableReason={
            overview.operations.kind === 'unavailable' ? overview.operations.reason : undefined
          }
        />
      </div>

      {/* Main 2-column Dashboard Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))',
          gap: '24px',
        }}
      >
        {/* Left Column: Projects & Work Distribution */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Work by State Card */}
          <Card elevation="sm">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Distribución de Trabajo por Estado</h3>
              <Button size="sm" variant="ghost" onClick={() => onNavigateTo('kanban')}>
                Ver Tablero →
              </Button>
            </div>

            {overview.work.kind === 'ready' ? (
              <StateDistribution
                distribution={overview.work.data.byStage}
                totalCount={overview.work.data.totalTasks}
              />
            ) : overview.work.kind === 'unavailable' ? (
              <div
                style={{
                  padding: '24px',
                  backgroundColor: 'var(--bg-muted)',
                  borderRadius: 'var(--radius-md)',
                  textAlign: 'center',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}
              >
                <p><strong>Desglose no disponible</strong></p>
                <p style={{ marginTop: '4px' }}>{overview.work.reason}</p>
                {projects.length > 0 && !selectedProjectId && (
                  <div style={{ marginTop: '12px' }}>
                    <Button size="sm" variant="outline" onClick={() => onSelectProject(projects[0].id)}>
                      Ver distribución de {projects[0].name}
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                Sin datos de trabajo registrados.
              </p>
            )}
          </Card>

          {/* Projects Portfolio Card */}
          <Card elevation="sm">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Cartera de Proyectos</h3>
              <Button size="sm" variant="ghost" onClick={() => onNavigateTo('projects')}>
                Ver Todos →
              </Button>
            </div>

            {projects.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                No hay proyectos disponibles con las credenciales actuales.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {projects.map((p) => (
                  <div
                    key={p.id}
                    onClick={() => onSelectProject(p.id)}
                    style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor:
                        selectedProjectId === p.id ? 'var(--bg-muted)' : 'var(--bg-app)',
                      border:
                        selectedProjectId === p.id
                          ? '1px solid var(--border-focus)'
                          : '1px solid var(--border-subtle)',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                        {p.name}
                      </div>
                      {p.description && (
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {p.description}
                        </div>
                      )}
                    </div>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        fontWeight: 600,
                      }}
                    >
                      {p.status || 'ACTIVO'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Governance, Decisions & Alerts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Governance & Audit Status */}
          <Card elevation="sm">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Estado de Gobernanza y Certificación</h3>
              <Button size="sm" variant="ghost" onClick={() => onNavigateTo('audit')}>
                Detalles de Auditoría →
              </Button>
            </div>

            {overview.governance.kind === 'ready' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontWeight: 600 }}>Certificación:</span>
                  <span style={{ color: overview.governance.data.certified ? 'var(--status-success-text)' : 'var(--text-muted)' }}>
                    {overview.governance.data.certified ? 'CERTIFICADO' : 'NO CERTIFICADO / EN PROCESO'}
                  </span>
                </div>
                {overview.governance.data.classification && (
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    Clasificación: Nivel R {overview.governance.data.classification.rLevel} · Garantía {overview.governance.data.classification.assuranceLevel}
                  </div>
                )}
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {overview.governance.data.notes}
                </p>
              </div>
            ) : (
              <div
                style={{
                  padding: '16px',
                  backgroundColor: 'var(--bg-muted)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}
              >
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  Sin contrato API certificado
                </div>
                <p>
                  El backend no expone un servicio de certificación de auditoría independiente en esta fase. No se afirma conformidad sin evidencia verificada.
                </p>
              </div>
            )}
          </Card>

          {/* Decisions & Alerts Panel (Honest Consultative Mode) */}
          <Card elevation="sm">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Centro de Decisiones y Alertas</h3>
              <Button size="sm" variant="ghost" onClick={() => onNavigateTo('decisions')}>
                Ver Decisiones →
              </Button>
            </div>

            {overview.decisions.kind === 'ready' && overview.decisions.data.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {overview.decisions.data.map((d) => (
                  <div
                    key={d.id}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: 'var(--bg-app)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '13px',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{d.title}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      {d.description}
                    </div>
                  </div>
                ))}
              </div>
            ) : overview.decisions.kind === 'unavailable' ? (
              <div
                style={{
                  padding: '16px',
                  backgroundColor: 'var(--bg-muted)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}
              >
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  Modo consultivo sin alertas activas
                </div>
                <p>
                  {overview.decisions.reason ||
                    'No existen endpoints de mutación o votación ejecutiva en esta fase; los eventos de trabajo se consultan de manera transparente.'}
                </p>
              </div>
            ) : (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                No hay decisiones pendientes registradas.
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
