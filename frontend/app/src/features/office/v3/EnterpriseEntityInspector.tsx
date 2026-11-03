import React from 'react';
import type {
  AgentIdentity,
  AlertSummary,
  DecisionSummary,
  OrgUnit,
  ProjectSummary,
} from '../../../domain/models';
import type {
  EnterpriseEntitySelection,
  EnterpriseProjection,
} from './enterpriseProjection';

export interface EnterpriseEntityInspectorProps {
  selection: EnterpriseEntitySelection;
  units: OrgUnit[];
  agents: AgentIdentity[];
  projects: ProjectSummary[];
  alerts: AlertSummary[];
  decisions: DecisionSummary[];
  projection: EnterpriseProjection;
  isDemo: boolean;
  canManageOrganization: boolean;
  onSelectEntity: (selection: EnterpriseEntitySelection) => void;
  onOpenConstitutionCenter: () => void;
  onOpenAgentDetail?: (agent: AgentIdentity) => void;
  onNavigate?: (
    target: 'organization' | 'kanban' | 'projects' | 'decisions' | 'alerts' | 'audit',
    projectId?: string,
    workId?: string
  ) => void;
}

export const EnterpriseEntityInspector: React.FC<EnterpriseEntityInspectorProps> = ({
  selection,
  units,
  agents,
  projects,
  alerts,
  decisions,
  projection,
  isDemo,
  canManageOrganization,
  onSelectEntity,
  onOpenConstitutionCenter,
  onOpenAgentDetail,
  onNavigate,
}) => {
  const provenanceBadge = (
    <span
      style={{
        padding: '2px 8px',
        borderRadius: '999px',
        fontSize: '10px',
        fontWeight: 800,
        background: isDemo ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)',
        color: isDemo ? '#fcd34d' : '#6ee7b7',
        border: '1px solid currentColor',
      }}
    >
      {isDemo ? 'DEMO · SINTÉTICO' : 'LIVE · PERSISTIDO'}
    </span>
  );

  // 1. ATRIUM CENTRAL
  if (selection.kind === 'atrium') {
    const { atrium } = projection;
    return (
      <div
        data-testid="entity-inspector-atrium"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Atrio Central (0, 0)
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              🏛️ {atrium.label}
            </h4>
          </div>
          {provenanceBadge}
        </div>

        <p style={{ margin: 0, color: '#cbd5e1', lineHeight: 1.5 }}>{atrium.constitutionSummaryText}</p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: '8px' }}>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Unidades declaradas</div>
            <strong style={{ fontSize: '15px', color: '#f8fafc' }}>{atrium.declaredUnitsCount}</strong>
          </div>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Puestos ocupados / vacantes</div>
            <strong style={{ fontSize: '15px', color: '#38bdf8' }}>
              {atrium.occupiedWorkstationsCount} / {atrium.vacantWorkstationsCount}
            </strong>
          </div>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Proyectos activos / bloqueados</div>
            <strong style={{ fontSize: '15px', color: '#a7f3d0' }}>
              {atrium.activeProjectsCount} / {atrium.blockedProjectsCount}
            </strong>
          </div>
          <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Decisiones CEO / Alertas</div>
            <strong style={{ fontSize: '15px', color: '#fcd34d' }}>
              {atrium.pendingCeoDecisionsCount} / {atrium.criticalAlertsCount}
            </strong>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={onOpenConstitutionCenter}
            className="aao-hud-btn"
            style={{ padding: '6px 12px', fontSize: '11px', fontWeight: 700, color: '#7dd3fc' }}
          >
            ⚖️ Abrir Centro de Constitución Organizativa
          </button>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate('decisions')}
              className="aao-hud-btn"
              style={{ padding: '6px 12px', fontSize: '11px' }}
            >
              Ver Decisiones Reservadas ({atrium.pendingCeoDecisionsCount})
            </button>
          )}
        </div>
      </div>
    );
  }

  // 2. WORKSTATION (PUESTO DE TRABAJO)
  if (selection.kind === 'workstation') {
    const ws = projection.workstations.find((w) => w.id === selection.id) || projection.workstations[0];
    if (!ws) {
      return <div>Puesto de trabajo no encontrado.</div>;
    }
    const occupant = ws.technicalIdentityId
      ? agents.find((a) => a.id === ws.technicalIdentityId) || null
      : null;

    return (
      <div
        data-testid="entity-inspector-workstation"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Puesto Organizativo ({ws.id})
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              💺 Puesto #{ws.slotIndex} · {ws.positionTitle}
            </h4>
          </div>
          {provenanceBadge}
        </div>

        {/* 6 Separated Layers per Section 5.2 & 7.2 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
            <div style={{ fontSize: '10px', color: '#7dd3fc', fontWeight: 700, textTransform: 'uppercase' }}>
              1. Puesto Organizativo (Workstation)
            </div>
            <div>Departamento: <strong>[{ws.unitCode}] {ws.unitName}</strong></div>
            <div>Estado del puesto: <strong>{ws.occupancyState}</strong></div>
            <div>Coordenadas 3D: <code>({ws.worldPosition.x}, {ws.worldPosition.z})</code></div>
          </div>

          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.25)' }}>
            <div style={{ fontSize: '10px', color: '#a7f3d0', fontWeight: 700, textTransform: 'uppercase' }}>
              2. Identidad Técnica (Principal)
            </div>
            {ws.technicalIdentityId ? (
              <>
                <div>Principal ID: <code>{ws.technicalIdentityId}</code></div>
                <div>Nombre: <strong>{ws.assignedAgentName}</strong></div>
                <div>Credencial: <strong>{ws.credentialStatus || 'ENABLED'}</strong></div>
              </>
            ) : (
              <div style={{ color: '#94a3b8' }}>Puesto vacante — sin identidad técnica asignada.</div>
            )}
          </div>

          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.25)' }}>
            <div style={{ fontSize: '10px', color: '#c4b5fd', fontWeight: 700, textTransform: 'uppercase' }}>
              3. Perfil Organizativo (organization_profiles)
            </div>
            <div>Rol declarado: <strong>{ws.profileRoleTitle || 'Sin perfil registrado'}</strong></div>
            <div>Responsable jerárquico: <strong>{ws.managerId || 'No declarado'}</strong></div>
            <div>
              Competencias:{' '}
              {ws.competencies.length > 0 ? ws.competencies.join(', ') : 'Sin competencias declaradas'}
            </div>
          </div>

          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.25)' }}>
            <div style={{ fontSize: '10px', color: '#fcd34d', fontWeight: 700, textTransform: 'uppercase' }}>
              4. Asignación de Trabajo (work_items)
            </div>
            {ws.activeWorkId ? (
              <>
                <div>Encargo: <strong>{ws.activeWorkTitle}</strong> (<code>{ws.activeWorkId}</code>)</div>
                <div>Proyecto: <code>{ws.activeProjectId}</code> · Estado: <strong>{ws.activeWorkState}</strong></div>
              </>
            ) : (
              <div style={{ color: '#94a3b8' }}>Sin encargo activo asignado a este puesto.</div>
            )}
          </div>

          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.25)' }}>
            <div style={{ fontSize: '10px', color: '#6ee7b7', fontWeight: 700, textTransform: 'uppercase' }}>
              5. Sesión Ejecutora (Lease)
            </div>
            <div>Sesión activa: <code>{ws.activeSessionId || 'Ninguna'}</code></div>
            <div>Lease: <strong>{ws.leaseState || 'SIN LEASE ACTIVO'}</strong></div>
            <div>Heartbeat: <strong>{ws.heartbeatStatus || 'N/A'}</strong></div>
          </div>

          <div style={{ padding: '9px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.25)' }}>
            <div style={{ fontSize: '10px', color: '#f9a8d4', fontWeight: 700, textTransform: 'uppercase' }}>
              6. Modelo LLM / Runtime (Observado)
            </div>
            {ws.llmProvider || ws.llmModel ? (
              <>
                <div>Proveedor / Modelo: <strong>{[ws.llmProvider, ws.llmModel].filter(Boolean).join(' · ')}</strong></div>
                <div>Versión runtime: <code>{ws.backendVersion || 'No registrada'}</code></div>
              </>
            ) : (
              <div style={{ color: '#94a3b8' }}>
                Sin modelo LLM registrado en ejecuciones recientes (el modelo nunca sustituye la identidad del agente).
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => onSelectEntity({ kind: 'department', id: ws.unitId })}
            className="aao-hud-btn"
            style={{ padding: '5px 10px', fontSize: '11px' }}
          >
            Ir al Departamento [{ws.unitCode}]
          </button>
          {occupant && (
            <button
              type="button"
              onClick={() => onSelectEntity({ kind: 'agent', id: occupant.id })}
              className="aao-hud-btn"
              style={{ padding: '5px 10px', fontSize: '11px' }}
            >
              Inspeccionar Agente {occupant.name}
            </button>
          )}
          <button
            type="button"
            onClick={onOpenConstitutionCenter}
            className="aao-hud-btn"
            style={{ padding: '5px 10px', fontSize: '11px', color: '#7dd3fc' }}
          >
            ⚖️ Gestionar Adscripción de Puesto
          </button>
        </div>
      </div>
    );
  }

  // 3. MEETING TABLE
  if (selection.kind === 'meeting-table') {
    const table =
      projection.meetingTables.find((t) => t.id === selection.id) || projection.meetingTables[0];
    if (!table) return <div>Mesa de reunión no encontrada.</div>;

    return (
      <div
        data-testid="entity-inspector-meeting-table"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Mesa de Reunión ({table.id})
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              🤝 {table.label}
            </h4>
          </div>
          {provenanceBadge}
        </div>

        <div
          style={{
            padding: '10px 12px',
            borderRadius: '8px',
            background: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
          }}
        >
          <strong>Regla de Gobierno Visual:</strong> {table.governanceNote}
        </div>

        {table.activeCoordinations.length === 0 ? (
          <div style={{ color: '#94a3b8' }}>
            Actualmente hay <strong>0</strong> coordinaciones multiparte registradas en esta mesa.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {table.activeCoordinations.map((coord) => (
              <div
                key={coord.id}
                style={{
                  padding: '8px 10px',
                  borderRadius: '8px',
                  background: 'rgba(2, 6, 23, 0.65)',
                  border: '1px solid rgba(16, 185, 129, 0.35)',
                }}
              >
                <div>
                  <strong>{coord.title}</strong> (<code>{coord.workId}</code> · Proyecto <code>{coord.projectId}</code>)
                </div>
                <div style={{ fontSize: '11px', color: '#a7f3d0' }}>
                  Participantes acreditados: {coord.participantNames.join(', ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // 4. AGENT
  if (selection.kind === 'agent') {
    const agent = agents.find((a) => a.id === selection.id) || agents[0];
    if (!agent) return <div>Agente no encontrado en la proyección actual.</div>;
    const workstation = projection.workstations.find((w) => w.technicalIdentityId === agent.id);

    return (
      <div
        data-testid="entity-inspector-agent"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Agente ({agent.id})
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              👤 {agent.name} · {agent.roleTitle}
            </h4>
          </div>
          {provenanceBadge}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '8px' }}>
          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Adscripción y Puesto</div>
            <div>Unidad: <strong>{agent.unitName || agent.unitId}</strong></div>
            <div>
              Puesto asignado:{' '}
              {workstation ? (
                <button
                  type="button"
                  onClick={() => onSelectEntity({ kind: 'workstation', id: workstation.id })}
                  style={{ background: 'none', border: 'none', padding: 0, color: '#38bdf8', cursor: 'pointer', fontWeight: 700 }}
                >
                  Puesto #{workstation.slotIndex} ({workstation.id})
                </button>
              ) : (
                'Sin puesto'
              )}
            </div>
          </div>

          <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>Gobierno Contextual y Autoridad</div>
            <div>Límite: <strong>{agent.authorityBoundary}</strong></div>
            <div>Grants de proyecto: <strong>{agent.grants?.length || 0}</strong></div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {onOpenAgentDetail && (
            <button
              type="button"
              onClick={() => onOpenAgentDetail(agent)}
              className="aao-hud-btn"
              style={{ padding: '5px 10px', fontSize: '11px', fontWeight: 700 }}
            >
              Abrir Expediente Completo del Agente
            </button>
          )}
          <button
            type="button"
            onClick={onOpenConstitutionCenter}
            className="aao-hud-btn"
            style={{ padding: '5px 10px', fontSize: '11px', color: '#7dd3fc' }}
          >
            ⚖️ Modificar Perfil Organizativo
          </button>
        </div>
      </div>
    );
  }

  // 5. PROJECT
  if (selection.kind === 'project') {
    const project = projects.find((p) => p.id === selection.id) || projects[0];
    if (!project) return <div>Proyecto no encontrado.</div>;
    const wf = projection.workflowLinks.find((w) => w.projectId === project.id);

    return (
      <div
        data-testid="entity-inspector-project"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Proyecto ({project.id})
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              📁 {project.name}
            </h4>
          </div>
          {provenanceBadge}
        </div>
        <div>
          Estado: <strong>{(project.status || wf?.status || 'ACTIVE').toUpperCase()}</strong> · En curso:{' '}
          <strong>{wf?.activeTasksCount ?? project.taskCounts?.IN_PROGRESS ?? 0}</strong> · Bloqueados:{' '}
          <strong>{wf?.blockedTasksCount ?? 0}</strong> · Decisiones pendientes:{' '}
          <strong>{wf?.pendingDecisionsCount ?? 0}</strong>
        </div>
        {wf && (
          <div>
            Departamentos participantes:{' '}
            <strong>
              {wf.participatingUnitCodes.length > 0
                ? wf.participatingUnitCodes.join(', ')
                : 'Sin departamentos asignados'}
            </strong>
          </div>
        )}
        {onNavigate && (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              onClick={() => onNavigate('kanban', project.id)}
              className="aao-hud-btn"
              style={{ padding: '5px 10px', fontSize: '11px', fontWeight: 700 }}
            >
              Abrir Tablero Kanban del Proyecto
            </button>
          </div>
        )}
      </div>
    );
  }

  // 6. ALERT
  if (selection.kind === 'alert') {
    const alert = alerts.find((a) => a.id === selection.id) || alerts[0];
    if (!alert) return <div>Alerta no encontrada.</div>;
    return (
      <div
        data-testid="entity-inspector-alert"
        style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontSize: '10px', color: '#fca5a5', fontWeight: 800, textTransform: 'uppercase' }}>
              Entidad Espacial · Alerta / Bloqueo ({alert.severity})
            </span>
            <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
              🚨 {alert.title}
            </h4>
          </div>
          {provenanceBadge}
        </div>
        <p style={{ margin: 0, color: '#fecaca' }}>{alert.description}</p>
        <div style={{ fontSize: '11px', color: '#94a3b8' }}>
          Origen: <code>{alert.source}</code> · Detectada: <code>{alert.timestamp}</code>
        </div>
      </div>
    );
  }

  // 7. DEPARTMENT (Default)
  const unit = units.find((u) => u.id === selection.id) || units[0];
  if (!unit) return <div>Departamento no disponible.</div>;
  const unitWorkstations = projection.workstations.filter((w) => w.unitId === unit.id);
  const unitAgents = agents.filter((a) => a.unitId === unit.id);
  const unitDecisions = decisions.filter((d) =>
    unitAgents.some((a) => a.currentAssignments.some((asg) => asg.projectId === d.subjectId))
  );

  return (
    <div
      data-testid="entity-inspector-department"
      style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e8f0', fontSize: '12px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <div>
          <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 800, textTransform: 'uppercase' }}>
            Entidad Espacial · Departamento ({unit.id})
          </span>
          <h4 style={{ margin: '2px 0 0 0', fontSize: '15px', color: '#f8fafc' }}>
            🏢 [{unit.code}] {unit.name}
          </h4>
        </div>
        {provenanceBadge}
      </div>

      <p style={{ margin: 0, color: '#cbd5e1' }}>{unit.description}</p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '8px' }}>
        <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8' }}>Responsable y Jerarquía</div>
          <div>Rol líder: <strong>{unit.leadRole}</strong></div>
          <div>Unidad superior: <strong>{unit.parentId || 'Raíz corporativa'}</strong></div>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8' }}>Capacidad de Puestos</div>
          <div>Puestos totales: <strong>{unitWorkstations.length}</strong></div>
          <div>
            Ocupados: <strong>{unitWorkstations.filter((w) => w.occupancyState !== 'VACANT').length}</strong> · Vacantes:{' '}
            <strong>{unitWorkstations.filter((w) => w.occupancyState === 'VACANT').length}</strong>
          </div>
        </div>
        <div style={{ padding: '8px 10px', borderRadius: '8px', background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(148, 163, 184, 0.2)' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8' }}>Gobierno Contextual</div>
          <div>Autoridad edición: <strong>{canManageOrganization && !isDemo ? 'CEO LIVE' : 'Solo lectura'}</strong></div>
          <div>Decisiones vinculadas: <strong>{unitDecisions.length}</strong></div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        {unitWorkstations.map((ws) => (
          <button
            key={ws.id}
            type="button"
            onClick={() => onSelectEntity({ kind: 'workstation', id: ws.id })}
            className="aao-hud-btn"
            style={{ padding: '4px 8px', fontSize: '10px' }}
          >
            💺 Puesto #{ws.slotIndex} ({ws.assignedAgentName || 'Vacante'})
          </button>
        ))}
      </div>
    </div>
  );
};
