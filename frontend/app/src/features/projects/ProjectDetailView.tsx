import React, { useState } from 'react';
import type {
  ProjectSummary,
  CapabilitySummary,
  EvaluationSummary,
  DataState,
  ActivityEvent,
} from '../../domain/models';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { SectionHeading, PermissionNotice } from '../../components/ui/SectionHeading';
import { DataStatePanel } from '../../components/ui/DataStatePanel';

export interface ProjectDetailViewProps {
  project: ProjectSummary;
  capabilitiesState: DataState<CapabilitySummary[]>;
  evaluationsState: DataState<EvaluationSummary[]>;
  activityState: DataState<ActivityEvent[]>;
  onBack: () => void;
  onOpenKanban: () => void;
  onRefresh: () => void;
}

export const ProjectDetailView: React.FC<ProjectDetailViewProps> = ({
  project,
  capabilitiesState,
  evaluationsState,
  activityState,
  onBack,
  onOpenKanban,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<'capabilities' | 'evaluations' | 'activity' | 'metadata'>(
    'capabilities'
  );
  const [filterType, setFilterType] = useState<string>('all');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header & Back */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Button size="sm" variant="outline" onClick={onBack}>
          ← Volver a Proyectos
        </Button>
      </div>

      <Card elevation="sm">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {project.name}
              </h2>
              <span
                style={{
                  fontSize: '12px',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-full)',
                  backgroundColor: 'var(--bg-muted)',
                  border: '1px solid var(--border-subtle)',
                  fontWeight: 600,
                }}
              >
                {project.status || 'ACTIVO'}
              </span>
            </div>
            <p
              style={{
                fontSize: '12px',
                fontFamily: 'monospace',
                color: 'var(--text-muted)',
                marginTop: '4px',
              }}
            >
              ID: {project.id} {project.mandateId ? `· Mandato: ${project.mandateId}` : ''}
            </p>
            {project.description && (
              <p
                style={{
                  fontSize: '14px',
                  color: 'var(--text-secondary)',
                  marginTop: '8px',
                  maxWidth: '800px',
                }}
              >
                {project.description}
              </p>
            )}
          </div>

          <Button size="md" variant="primary" onClick={onOpenKanban}>
            Ver Tablero de Trabajo (Kanban) →
          </Button>
        </div>
      </Card>

      <PermissionNotice message="El catálogo de capacidades muestra versiones registradas; su visualización no otorga autorización de ejecución automática." />

      {/* Tabs navigation */}
      <div
        role="tablist"
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '8px',
        }}
      >
        <button
          role="tab"
          aria-selected={activeTab === 'capabilities'}
          onClick={() => setActiveTab('capabilities')}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: activeTab === 'capabilities' ? 600 : 500,
            borderRadius: 'var(--radius-md)',
            backgroundColor: activeTab === 'capabilities' ? 'var(--bg-muted)' : 'transparent',
            color: activeTab === 'capabilities' ? 'var(--primary)' : 'var(--text-secondary)',
          }}
        >
          Habilidades y Capacidades
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'evaluations'}
          onClick={() => setActiveTab('evaluations')}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: activeTab === 'evaluations' ? 600 : 500,
            borderRadius: 'var(--radius-md)',
            backgroundColor: activeTab === 'evaluations' ? 'var(--bg-muted)' : 'transparent',
            color: activeTab === 'evaluations' ? 'var(--primary)' : 'var(--text-secondary)',
          }}
        >
          Evaluaciones de Capacidad
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'activity'}
          onClick={() => setActiveTab('activity')}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: activeTab === 'activity' ? 600 : 500,
            borderRadius: 'var(--radius-md)',
            backgroundColor: activeTab === 'activity' ? 'var(--bg-muted)' : 'transparent',
            color: activeTab === 'activity' ? 'var(--primary)' : 'var(--text-secondary)',
          }}
        >
          Actividad
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'metadata'}
          onClick={() => setActiveTab('metadata')}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            fontWeight: activeTab === 'metadata' ? 600 : 500,
            borderRadius: 'var(--radius-md)',
            backgroundColor: activeTab === 'metadata' ? 'var(--bg-muted)' : 'transparent',
            color: activeTab === 'metadata' ? 'var(--primary)' : 'var(--text-secondary)',
          }}
        >
          Metadatos del Proyecto
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'capabilities' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label htmlFor="filter-cap-type" style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                Tipo:
              </label>
              <select
                id="filter-cap-type"
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                style={{
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-strong)',
                  backgroundColor: 'var(--bg-surface)',
                  fontSize: '13px',
                }}
              >
                <option value="all">Todos los tipos</option>
                <option value="agent_skill">Habilidades de Agente (Skills)</option>
                <option value="cli_script">Scripts CLI</option>
                <option value="library">Bibliotecas</option>
                <option value="application_service">Servicios</option>
                <option value="agent">Agentes</option>
              </select>
            </div>
          </div>

          <DataStatePanel
            state={capabilitiesState}
            onRetry={onRefresh}
            title="Capacidades"
            renderReady={(capabilities) => {
              const filtered =
                filterType === 'all'
                  ? capabilities
                  : capabilities.filter((c) => c.capability_type === filterType);

              if (filtered.length === 0) {
                return (
                  <Card elevation="none" style={{ textAlign: 'center', padding: '32px' }}>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                      No se encontraron capacidades para el tipo seleccionado.
                    </p>
                  </Card>
                );
              }

              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {filtered.map((cap) => (
                    <Card key={`${cap.capability_id}-${cap.version}`} elevation="sm">
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          marginBottom: '8px',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                              {cap.capability_id}
                            </strong>
                            <span
                              style={{
                                fontSize: '11px',
                                padding: '1px 6px',
                                borderRadius: 'var(--radius-sm)',
                                backgroundColor: 'var(--bg-muted)',
                                fontFamily: 'monospace',
                              }}
                            >
                              v{cap.version}
                            </span>
                          </div>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                            Tipo: {cap.capability_type} · Estado: {cap.status}
                          </span>
                        </div>

                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: 'var(--status-warning-bg)',
                            color: 'var(--status-warning-text)',
                            border: '1px solid var(--status-warning-border)',
                            fontWeight: 600,
                          }}
                        >
                          Ejecución autorizada: no
                        </span>
                      </div>

                      {cap.risks && cap.risks.length > 0 && (
                        <div style={{ fontSize: '12px', color: 'var(--status-warning-text)', marginTop: '4px' }}>
                          <strong>Riesgos y límites:</strong> {cap.risks.join(', ')}
                        </div>
                      )}

                      {cap.tests && cap.tests.length > 0 && (
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                          <strong>Pruebas y evidencia:</strong> {cap.tests.join(', ')}
                        </div>
                      )}

                      {Boolean(cap.provenance) && (
                        <div
                          style={{
                            fontSize: '11px',
                            fontFamily: 'monospace',
                            color: 'var(--text-muted)',
                            marginTop: '6px',
                          }}
                        >
                          Procedencia: {JSON.stringify(cap.provenance)}
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              );
            }}
          />
        </div>
      )}

      {activeTab === 'evaluations' && (
        <DataStatePanel
          state={evaluationsState}
          onRetry={onRefresh}
          title="Evaluaciones de Capacidad"
          renderReady={(evaluations) => (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {evaluations.map((ev, idx) => (
                <Card key={idx} elevation="sm">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <strong style={{ fontSize: '14px' }}>
                      {ev.task_title || `Tarea: ${ev.task_id}`}
                    </strong>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {new Date(ev.created_at).toLocaleString('es-ES')}
                    </span>
                  </div>
                  <pre
                    style={{
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      backgroundColor: 'var(--bg-muted)',
                      padding: '8px',
                      borderRadius: 'var(--radius-sm)',
                      overflowX: 'auto',
                    }}
                  >
                    {JSON.stringify(ev.details, null, 2)}
                  </pre>
                </Card>
              ))}
            </div>
          )}
        />
      )}

      {activeTab === 'activity' && (
        <DataStatePanel
          state={activityState}
          onRetry={onRefresh}
          title="Actividad del proyecto"
          renderReady={(events) => (
            <ol aria-label="Actividad del proyecto" style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {events.map((ev) => (
                <li key={ev.id}>
                  <Card elevation="sm">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: '13px', fontFamily: 'monospace' }}>{ev.kind}</strong>
                      <time dateTime={ev.created_at} style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {new Date(ev.created_at).toLocaleString('es-ES')}
                      </time>
                    </div>
                    <div style={{ fontSize: '11px', fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: '2px' }}>
                      {ev.subject_id}
                    </div>
                    <pre
                      style={{
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        backgroundColor: 'var(--bg-muted)',
                        padding: '8px',
                        marginTop: '6px',
                        borderRadius: 'var(--radius-sm)',
                        overflowX: 'auto',
                      }}
                    >
                      {JSON.stringify(ev.details, null, 2)}
                    </pre>
                  </Card>
                </li>
              ))}
            </ol>
          )}
        />
      )}

      {activeTab === 'metadata' && (
        <Card elevation="sm">
          <SectionHeading title="Detalles del Contrato" />
          <dl
            style={{
              display: 'grid',
              gridTemplateColumns: '180px 1fr',
              gap: '8px 16px',
              fontSize: '13px',
            }}
          >
            <dt style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Identificador:</dt>
            <dd style={{ fontFamily: 'monospace' }}>{project.id}</dd>

            <dt style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Nombre canónico:</dt>
            <dd>{project.name}</dd>

            <dt style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Estado administrativo:</dt>
            <dd>{project.status || 'ACTIVO'}</dd>

            <dt style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Mandato vinculado:</dt>
            <dd style={{ fontFamily: 'monospace' }}>{project.mandateId || 'Sin mandato registrado'}</dd>
          </dl>
        </Card>
      )}
    </div>
  );
};
