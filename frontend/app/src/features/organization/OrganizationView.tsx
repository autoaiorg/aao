import React, { useState, useMemo } from 'react';
import type {
  DataState,
  OrganizationStructure,
  AgentIdentity,
  AgentType,
  AgentHeartbeatStatus,
} from '../../domain/models';
import { Card, Badge } from '../../components/ui/Card';
import { SectionHeading } from '../../components/ui/SectionHeading';
import { MetricCard } from '../../components/ui/MetricCard';
import { DataStatePanel } from '../../components/ui/DataStatePanel';
import { Button } from '../../components/ui/Button';
import { AgentDetailDrawer } from './AgentDetailDrawer';

export interface OrganizationViewProps {
  orgState: DataState<OrganizationStructure>;
  onRefresh?: () => void;
}

export type OrgSubTab = 'organigrama' | 'agents' | 'matrix';

export const OrganizationView: React.FC<OrganizationViewProps> = ({
  orgState,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<OrgSubTab>('organigrama');
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | AgentType>('ALL');
  const [heartbeatFilter, setHeartbeatFilter] = useState<'ALL' | AgentHeartbeatStatus>('ALL');
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);

  // Drawer state
  const [selectedAgent, setSelectedAgent] = useState<AgentIdentity | null>(null);
  const [triggerEl, setTriggerEl] = useState<HTMLElement | null>(null);

  const handleOpenAgentDrawer = (agent: AgentIdentity, e: React.MouseEvent<HTMLElement>) => {
    setTriggerEl(e.currentTarget);
    setSelectedAgent(agent);
  };

  const handleCloseAgentDrawer = () => {
    setSelectedAgent(null);
  };

  const agents = orgState.kind === 'ready' ? orgState.data.agents : [];
  const units = orgState.kind === 'ready' ? orgState.data.units : [];
  const totalStandingAgents = orgState.kind === 'ready' ? orgState.data.totalStandingAgents : 0;
  const totalEphemeralAgents = orgState.kind === 'ready' ? orgState.data.totalEphemeralAgents : 0;
  const activeAssignmentsCount = orgState.kind === 'ready' ? orgState.data.activeAssignmentsCount : 0;

  // Filtered agents - Hook called unconditionally before any early returns
  const filteredAgents = useMemo(() => {
    return agents.filter((agent) => {
      // Type filter
      if (typeFilter !== 'ALL' && agent.type !== typeFilter) return false;
      // Heartbeat filter
      if (heartbeatFilter !== 'ALL' && agent.heartbeatStatus !== heartbeatFilter) return false;
      // Unit filter
      if (selectedUnitId && agent.unitId !== selectedUnitId) return false;
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = agent.name.toLowerCase().includes(q);
        const matchesRole = agent.roleTitle.toLowerCase().includes(q);
        const matchesUnit = (agent.unitName || '').toLowerCase().includes(q);
        const matchesCap = agent.capabilities.some((c) => c.name.toLowerCase().includes(q));
        if (!matchesName && !matchesRole && !matchesUnit && !matchesCap) return false;
      }
      return true;
    });
  }, [agents, typeFilter, heartbeatFilter, selectedUnitId, searchQuery]);

  // Early return after all hooks have been invoked
  if (orgState.kind !== 'ready') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <SectionHeading
          title="Organización y Estructura de Agentes"
          subtitle="Fase F3 · Jerarquía de unidades organizativas, puestos de responsabilidad y plantilla"
        />
        <DataStatePanel
          state={orgState}
          onRetry={onRefresh}
          renderReady={() => null}
        />
      </div>
    );
  }

  // Telemetry counts
  const healthyCount = agents.filter((a) => a.heartbeatStatus === 'HEALTHY').length;
  const staleCount = agents.filter((a) => a.heartbeatStatus === 'STALE').length;
  const unavailableOrUnknownCount = agents.filter(
    (a) => a.heartbeatStatus === 'UNAVAILABLE' || a.heartbeatStatus === 'UNKNOWN'
  ).length;

  // Hierarchy builder
  const rootUnits = units.filter((u) => u.parentId === null);
  const getChildUnits = (parentId: string) => units.filter((u) => u.parentId === parentId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Header */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <SectionHeading
              title="Organización y Estructura de Agentes"
              subtitle="Fase F3 · Jerarquías de supervisión, puestos de responsabilidad, agentes de plantilla fija y efímeros"
            />
          </div>
          {onRefresh && (
            <Button variant="secondary" onClick={onRefresh} style={{ height: '36px' }}>
              Actualizar
            </Button>
          )}
        </div>
      </div>

      {/* Metrics Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '16px',
        }}
      >
        <MetricCard
          title="Unidades Organizativas"
          value={units.length}
          subtitle="Departamentos y direcciones registradas"
        />
        <MetricCard
          title="Plantilla Fija (Standing)"
          value={totalStandingAgents}
          subtitle="Agentes persistentes de plantilla"
        />
        <MetricCard
          title="Agentes Efímeros (Temporales)"
          value={totalEphemeralAgents}
          subtitle="Agentes delegados por tarea o evaluador"
        />
        <MetricCard
          title="Asignaciones Activas"
          value={activeAssignmentsCount}
          subtitle="Proyectos y tareas en ejecución"
        />
        <MetricCard
          title="Telemetría Verificada"
          value={`${healthyCount}/${agents.length}`}
          subtitle={`${staleCount} desactualizados, ${unavailableOrUnknownCount} sin telemetría`}
        />
      </div>

      {/* Subnavigation Tabs */}
      <div
        role="tablist"
        aria-label="Vistas de la estructura organizativa"
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '8px',
        }}
      >
        <button
          role="tab"
          aria-selected={activeTab === 'organigrama'}
          aria-controls="panel-organigrama"
          id="tab-organigrama"
          onClick={() => setActiveTab('organigrama')}
          style={{
            padding: '8px 16px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: activeTab === 'organigrama' ? 600 : 500,
            backgroundColor: activeTab === 'organigrama' ? 'var(--primary-color)' : 'transparent',
            color: activeTab === 'organigrama' ? '#ffffff' : 'var(--text-secondary)',
          }}
        >
          Organigrama y Jerarquías
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'agents'}
          aria-controls="panel-agents"
          id="tab-agents"
          onClick={() => setActiveTab('agents')}
          style={{
            padding: '8px 16px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: activeTab === 'agents' ? 600 : 500,
            backgroundColor: activeTab === 'agents' ? 'var(--primary-color)' : 'transparent',
            color: activeTab === 'agents' ? '#ffffff' : 'var(--text-secondary)',
          }}
        >
          Plantilla y Agentes ({agents.length})
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'matrix'}
          aria-controls="panel-matrix"
          id="tab-matrix"
          onClick={() => setActiveTab('matrix')}
          style={{
            padding: '8px 16px',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: activeTab === 'matrix' ? 600 : 500,
            backgroundColor: activeTab === 'matrix' ? 'var(--primary-color)' : 'transparent',
            color: activeTab === 'matrix' ? '#ffffff' : 'var(--text-secondary)',
          }}
        >
          Puestos y Capacidades
        </button>
      </div>

      {/* Tab 1: Organigrama y Jerarquías */}
      {activeTab === 'organigrama' && (
        <div
          id="panel-organigrama"
          role="tabpanel"
          aria-labelledby="tab-organigrama"
          style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
        >
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--bg-muted)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              fontSize: '13px',
              color: 'var(--text-secondary)',
            }}
          >
            <strong>Árbol de Reporte y Líneas de Supervisión:</strong> Representación formal de las unidades directivas y dependencias técnicas. Seleccione una unidad para inspeccionar su dotación de agentes de plantilla y temporales.
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {rootUnits.map((root) => {
              const children = getChildUnits(root.id);
              return (
                <div key={root.id} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Root Unit Card */}
                  <div
                    style={{
                      borderLeft: '4px solid var(--primary-color)',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: 'var(--bg-surface)',
                      boxShadow: 'var(--shadow-sm)',
                      padding: '16px 20px',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <Badge variant="info">{root.code}</Badge>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-primary)' }}>
                            NIVEL EJECUTIVO / RAÍZ
                          </span>
                        </div>
                        <h3 style={{ fontSize: '17px', fontWeight: 700, margin: '2px 0 6px 0' }}>{root.name}</h3>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 8px 0', maxWidth: '750px' }}>
                          {root.description}
                        </p>
                        <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                          <strong>Puesto Responsable: </strong>
                          <span>{root.leadRole}</span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <div style={{ textAlign: 'right', fontSize: '12px', color: 'var(--text-secondary)' }}>
                          <div>Plantilla: <strong>{root.standingCount}</strong></div>
                          <div>Efímeros: <strong>{root.ephemeralCount}</strong></div>
                          <div>Proyectos: <strong>{root.activeProjectsCount}</strong></div>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setSelectedUnitId(root.id);
                            setActiveTab('agents');
                          }}
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                        >
                          Ver Agentes
                        </Button>
                      </div>
                    </div>
                  </div>

                  {/* Children Sub-units Grid */}
                  {children.length > 0 && (
                    <div
                      style={{
                        paddingLeft: '24px',
                        borderLeft: '2px dashed var(--border-focus)',
                        marginLeft: '16px',
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                        gap: '16px',
                      }}
                    >
                      {children.map((child) => {
                        const grandChildren = getChildUnits(child.id);
                        return (
                          <div
                            key={child.id}
                            style={{
                              backgroundColor: 'var(--bg-surface)',
                              border: '1px solid var(--border-subtle)',
                              borderRadius: 'var(--radius-md)',
                              padding: '16px',
                              display: 'flex',
                              flexDirection: 'column',
                              justifyContent: 'space-between',
                              gap: '12px',
                            }}
                          >
                            <div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                <Badge variant="neutral">{child.code}</Badge>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                  Supervisado por: {root.code}
                                </span>
                              </div>
                              <h4 style={{ fontSize: '15px', fontWeight: 600, margin: '2px 0 6px 0' }}>
                                {child.name}
                              </h4>
                              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '0 0 10px 0', lineHeight: 1.4 }}>
                                {child.description}
                              </p>
                              <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>
                                <strong>Líder de Área: </strong>{child.leadRole}
                              </div>
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                <span>{child.standingCount} fijos</span> · <span>{child.ephemeralCount} efímeros</span>
                              </div>
                              <Button
                                variant="secondary"
                                onClick={() => {
                                  setSelectedUnitId(child.id);
                                  setActiveTab('agents');
                                }}
                                style={{ fontSize: '11px', padding: '4px 10px' }}
                              >
                                Ver Agentes
                              </Button>
                            </div>

                            {/* Grandchildren sub-units (e.g. ENG under ARCH) */}
                            {grandChildren.length > 0 && (
                              <div style={{ marginTop: '8px', paddingLeft: '12px', borderLeft: '2px dotted var(--border-focus)' }}>
                                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                                  Sub-unidades operativas:
                                </div>
                                {grandChildren.map((gc) => (
                                  <div
                                    key={gc.id}
                                    style={{
                                      padding: '8px',
                                      backgroundColor: 'var(--bg-muted)',
                                      borderRadius: 'var(--radius-sm)',
                                      marginBottom: '6px',
                                      fontSize: '12px',
                                    }}
                                  >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <strong style={{ color: 'var(--text-primary)' }}>{gc.name}</strong>
                                      <Badge variant="neutral">{gc.code}</Badge>
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                                      {gc.leadRole} · {gc.standingCount} fijos, {gc.ephemeralCount} temporales
                                    </div>
                                    <div style={{ marginTop: '6px', textAlign: 'right' }}>
                                      <Button
                                        variant="secondary"
                                        onClick={() => {
                                          setSelectedUnitId(gc.id);
                                          setActiveTab('agents');
                                        }}
                                        style={{ fontSize: '10px', padding: '2px 8px' }}
                                      >
                                        Ver dotación ({gc.standingCount + gc.ephemeralCount})
                                      </Button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 2: Plantilla y Agentes */}
      {activeTab === 'agents' && (
        <div
          id="panel-agents"
          role="tabpanel"
          aria-labelledby="tab-agents"
          style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
        >
          {/* Filter Bar */}
          <Card elevation="none" style={{ padding: '16px', backgroundColor: 'var(--bg-surface)' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px', alignItems: 'flex-end' }}>
              {/* Search text */}
              <div style={{ flex: '1 1 240px' }}>
                <label
                  htmlFor="agent-search-input"
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Buscar agente o capacidad:
                </label>
                <input
                  id="agent-search-input"
                  type="text"
                  placeholder="Ej. Claude, Antigravity, React, Parche..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    fontSize: '13px',
                  }}
                />
              </div>

              {/* Type Filter */}
              <div>
                <label
                  htmlFor="agent-type-filter"
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Tipo de Agente:
                </label>
                <select
                  id="agent-type-filter"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as 'ALL' | AgentType)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    fontSize: '13px',
                  }}
                >
                  <option value="ALL">Todos los tipos</option>
                  <option value="STANDING">Plantilla Fija (Standing)</option>
                  <option value="EPHEMERAL">Agentes Efímeros (Temporales)</option>
                </select>
              </div>

              {/* Heartbeat Filter */}
              <div>
                <label
                  htmlFor="agent-heartbeat-filter"
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Estado de Telemetría:
                </label>
                <select
                  id="agent-heartbeat-filter"
                  value={heartbeatFilter}
                  onChange={(e) => setHeartbeatFilter(e.target.value as 'ALL' | AgentHeartbeatStatus)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    fontSize: '13px',
                  }}
                >
                  <option value="ALL">Cualquier telemetría</option>
                  <option value="HEALTHY">Activa / Saludable (Healthy)</option>
                  <option value="STALE">Desactualizada (Stale)</option>
                  <option value="UNKNOWN">Sin Telemetría (Unknown)</option>
                  <option value="UNAVAILABLE">No Disponible (Unavailable)</option>
                </select>
              </div>

              {/* Unit Filter */}
              <div>
                <label
                  htmlFor="agent-unit-filter"
                  style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Unidad:
                </label>
                <select
                  id="agent-unit-filter"
                  value={selectedUnitId || ''}
                  onChange={(e) => setSelectedUnitId(e.target.value || null)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    fontSize: '13px',
                  }}
                >
                  <option value="">Todas las unidades</option>
                  {units.map((u) => (
                    <option key={u.id} value={u.id}>
                      [{u.code}] {u.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Clear filters */}
              {(searchQuery || typeFilter !== 'ALL' || heartbeatFilter !== 'ALL' || selectedUnitId) && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSearchQuery('');
                    setTypeFilter('ALL');
                    setHeartbeatFilter('ALL');
                    setSelectedUnitId(null);
                  }}
                  style={{ fontSize: '12px', padding: '8px 12px' }}
                >
                  Limpiar filtros
                </Button>
              )}
            </div>
          </Card>

          {/* Result Count */}
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Mostrando <strong>{filteredAgents.length}</strong> de <strong>{agents.length}</strong> agentes registrados
          </div>

          {/* Agents Grid */}
          {filteredAgents.length === 0 ? (
            <Card elevation="none" style={{ textAlign: 'center', padding: '36px', backgroundColor: 'var(--bg-muted)' }}>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>
                No se encontraron agentes que coincidan con los filtros seleccionados.
              </p>
            </Card>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                gap: '16px',
              }}
            >
              {filteredAgents.map((agent) => {
                return (
                  <Card
                    key={agent.id}
                    elevation="sm"
                    style={{
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '12px',
                    }}
                  >
                    <div>
                      {/* Top Badges */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <Badge variant={agent.type === 'STANDING' ? 'info' : 'warning'}>
                          {agent.type === 'STANDING' ? 'Plantilla Fija' : 'Efímero'}
                        </Badge>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span
                            style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              backgroundColor:
                                agent.heartbeatStatus === 'HEALTHY'
                                  ? 'var(--color-success)'
                                  : agent.heartbeatStatus === 'STALE'
                                  ? 'var(--color-warning)'
                                  : agent.heartbeatStatus === 'UNAVAILABLE'
                                  ? 'var(--color-error)'
                                  : 'var(--text-muted)',
                            }}
                            aria-hidden="true"
                          />
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                            {agent.heartbeatStatus}
                          </span>
                        </div>
                      </div>

                      {/* Agent Name & Role */}
                      <h4 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 4px 0' }}>{agent.name}</h4>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                        {agent.roleTitle} · <strong>{agent.unitName || agent.unitId}</strong>
                      </div>

                      {/* Capabilities Preview */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px' }}>
                        {agent.capabilities.slice(0, 3).map((cap) => (
                          <span
                            key={cap.id}
                            style={{
                              fontSize: '11px',
                              padding: '2px 6px',
                              borderRadius: 'var(--radius-sm)',
                              backgroundColor: 'var(--bg-muted)',
                              color: 'var(--text-primary)',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            {cap.name}
                          </span>
                        ))}
                        {agent.capabilities.length > 3 && (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            +{agent.capabilities.length - 3} más
                          </span>
                        )}
                      </div>

                      {/* Active assignment banner */}
                      {agent.currentAssignments.length > 0 ? (
                        <div
                          style={{
                            fontSize: '11px',
                            padding: '6px 8px',
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'rgba(59, 130, 246, 0.08)',
                            color: 'var(--color-primary)',
                            border: '1px solid rgba(59, 130, 246, 0.2)',
                          }}
                        >
                          Asignado: {agent.currentAssignments[0].projectName}
                        </div>
                      ) : (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Sin asignación activa (Disponible)
                        </div>
                      )}
                    </div>

                    <div style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', textAlign: 'right' }}>
                      <Button
                        variant="secondary"
                        onClick={(e) => handleOpenAgentDrawer(agent, e)}
                        aria-label={`Ver ficha técnica de ${agent.name}`}
                        style={{ fontSize: '12px', padding: '6px 12px', width: '100%' }}
                      >
                        Ver Ficha Técnica
                      </Button>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Puestos y Capacidades */}
      {activeTab === 'matrix' && (
        <div
          id="panel-matrix"
          role="tabpanel"
          aria-labelledby="tab-matrix"
          style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
        >
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--bg-muted)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              fontSize: '13px',
              color: 'var(--text-secondary)',
            }}
          >
            <strong>Matriz de Puestos y Capacidades:</strong> Mapeo exhaustivo de unidades, responsabilidades y competencias verificadas. Solo lectura conforme al modelo de observabilidad de AAO.
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '13px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <thead>
                <tr style={{ backgroundColor: 'var(--bg-muted)', borderBottom: '1px solid var(--border-subtle)', textAlign: 'left' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Unidad</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Puesto / Rol</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Tipo de Asignación</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Capacidades Auditadas</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Telemetría</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Acción</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => (
                  <tr
                    key={agent.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                    }}
                  >
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{ fontWeight: 600 }}>{agent.unitName || agent.unitId}</span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 500 }}>{agent.name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{agent.roleTitle}</div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <Badge variant={agent.type === 'STANDING' ? 'info' : 'warning'}>
                        {agent.type === 'STANDING' ? 'Plantilla Fija' : 'Temporal'}
                      </Badge>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {agent.capabilities.map((c) => (
                          <Badge key={c.id} variant={c.level === 'CERTIFIED' ? 'success' : 'neutral'}>
                            {c.name}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          color:
                            agent.heartbeatStatus === 'HEALTHY'
                              ? 'var(--color-success)'
                              : agent.heartbeatStatus === 'STALE'
                              ? 'var(--color-warning)'
                              : 'var(--text-muted)',
                        }}
                      >
                        {agent.heartbeatStatus}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <Button
                        variant="secondary"
                        onClick={(e) => handleOpenAgentDrawer(agent, e)}
                        style={{ fontSize: '11px', padding: '4px 8px' }}
                      >
                        Ficha
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detail Drawer */}
      <AgentDetailDrawer
        agent={selectedAgent}
        onClose={handleCloseAgentDrawer}
        triggerElement={triggerEl}
      />
    </div>
  );
};
