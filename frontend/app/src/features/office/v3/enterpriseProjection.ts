import type {
  AgentIdentity,
  AlertSummary,
  DecisionSummary,
  OrgUnit,
  OrganizationCoverage,
  ProjectSummary,
} from '../../../domain/models';
import type {
  OrganizationAttributionDiagnostics,
} from '../liveOfficeLayout';
import type { OfficeRoomConfig } from '../types';
import type {
  OrganizationProfileCommand,
  OrganizationUnitCommand,
} from '../../../data/ports/AaoOrganizationCommandPort';

export type EnterpriseEntityKind =
  | 'department'
  | 'workstation'
  | 'agent'
  | 'meeting-table'
  | 'project'
  | 'atrium'
  | 'alert';

export interface EnterpriseEntitySelection {
  kind: EnterpriseEntityKind;
  id: string;
}

export type WorkstationOccupancyState =
  | 'OCCUPIED_ACTIVE'
  | 'OCCUPIED_IDLE'
  | 'ASSIGNED_NO_LEASE'
  | 'VACANT';

/**
 * Representa un Puesto Organizativo (Workstation) separado explícitamente de:
 * 1) Puesto organizativo (`slotId`, `positionTitle`, `unitId`)
 * 2) Identidad técnica del agente (`technicalIdentityId` / `principal_id`)
 * 3) Perfil organizativo (`profileRoleTitle`, `managerId`, `competencies`)
 * 4) Asignación actual (`activeWorkId`, `activeProjectId`)
 * 5) Sesión ejecutora (`activeSessionId`, `leaseState`, `heartbeatStatus`)
 * 6) Modelo LLM observado (`llmProvider`, `llmModel`, `backendVersion`)
 */
export interface WorkstationPositionSlot {
  id: string;
  unitId: string;
  unitCode: string;
  unitName: string;
  slotIndex: number;
  positionTitle: string;
  responsibilitySummary: string;
  occupancyState: WorkstationOccupancyState;
  /** Identidad técnica (`principal_id`) si el puesto está ocupado */
  technicalIdentityId: string | null;
  assignedAgentName: string | null;
  credentialStatus: 'ENABLED' | 'DISABLED' | null;
  /** Perfil organizativo (`organization_profiles`) */
  profileRoleTitle: string | null;
  managerId: string | null;
  competencies: string[];
  /** Asignación actual (`work_items` / `execution_queue`) */
  activeWorkId: string | null;
  activeWorkTitle: string | null;
  activeProjectId: string | null;
  activeWorkState: string | null;
  /** Sesión ejecutora (`lease`) */
  activeSessionId: string | null;
  leaseState: string | null;
  heartbeatStatus: string | null;
  lastHeartbeatAt: string | null;
  /** Modelo LLM observado en la última ejecución registrada (nunca confundido con la identidad) */
  llmProvider: string | null;
  llmModel: string | null;
  backendVersion: string | null;
  worldPosition: { x: number; z: number };
}

export interface MeetingCoordinationItem {
  id: string;
  projectId: string;
  workId: string;
  title: string;
  participantAgentIds: string[];
  participantNames: string[];
  evidenceKind: 'shared-work-item' | 'work-group-session';
}

export interface MeetingTableEntity {
  id: string;
  label: string;
  zoneName: string;
  worldPosition: { x: number; z: number };
  activeCoordinations: MeetingCoordinationItem[];
  hasVerifiedMeeting: boolean;
  governanceNote: string;
}

export interface CentralAtriumSummary {
  id: 'atrium-central';
  label: string;
  origin: 'live' | 'demo';
  declaredUnitsCount: number;
  registeredProfilesCount: number;
  activeAgentsCount: number;
  historicalAgentCount: number;
  unassignedAgentsCount: number;
  occupiedWorkstationsCount: number;
  vacantWorkstationsCount: number;
  activeProjectsCount: number;
  blockedProjectsCount: number;
  pendingCeoDecisionsCount: number;
  criticalAlertsCount: number;
  coverage?: OrganizationCoverage;
  requiresConstitution: boolean;
  constitutionSummaryText: string;
}

export interface SpatialDepartmentWorkflowLink {
  id: string;
  projectId: string;
  projectName: string;
  participatingUnitIds: string[];
  participatingUnitCodes: string[];
  activeTasksCount: number;
  blockedTasksCount: number;
  pendingDecisionsCount: number;
  status: 'ACTIVE' | 'BLOCKED' | 'IDLE';
}

export interface OperationalTimelineEntry {
  id: string;
  timestamp: string;
  category: 'EXECUTION' | 'ASSIGNMENT' | 'ALERT' | 'DECISION';
  title: string;
  detail: string;
  agentId: string | null;
  agentName: string | null;
  unitId: string | null;
  projectId: string | null;
  workId: string | null;
  modelLabel: string | null;
  costEstimateUsd: number | null;
  isBlocked: boolean;
  origin: 'live' | 'demo';
}

export interface ProposedUnitDraft extends OrganizationUnitCommand {
  draftId: string;
  leadRole: string;
  description: string;
}

export interface ProposedProfileDraft extends OrganizationProfileCommand {
  draftId: string;
}

export interface ConstitutionValidationIssue {
  severity: 'error' | 'warning';
  code:
    | 'MISSING_REQUIRED_FIELD'
    | 'SELF_PARENT_UNIT'
    | 'MISSING_PARENT_UNIT'
    | 'HIERARCHY_CYCLE'
    | 'SELF_MANAGER_PROFILE'
    | 'MISSING_PROFILE_UNIT'
    | 'AUTHORITY_REQUIRED'
    | 'DEMO_MODE_READONLY';
  message: string;
  targetId?: string;
}

export interface ConstitutionValidationReport {
  isValidForSubmission: boolean;
  canSubmitAuthorized: boolean;
  errors: ConstitutionValidationIssue[];
  warnings: ConstitutionValidationIssue[];
  constitutionalNotice: string;
}

export interface EnterpriseProjection {
  origin: 'live' | 'demo';
  atrium: CentralAtriumSummary;
  workstations: WorkstationPositionSlot[];
  meetingTables: MeetingTableEntity[];
  workflowLinks: SpatialDepartmentWorkflowLink[];
  timelineEntries: OperationalTimelineEntry[];
}

export function validateConstitutionProposal(params: {
  persistedUnits: OrgUnit[];
  draftUnits: ProposedUnitDraft[];
  draftProfiles: ProposedProfileDraft[];
  canManageOrganization: boolean;
  isDemo: boolean;
}): ConstitutionValidationReport {
  const { persistedUnits, draftUnits, draftProfiles, canManageOrganization, isDemo } = params;
  const errors: ConstitutionValidationIssue[] = [];
  const warnings: ConstitutionValidationIssue[] = [];

  if (isDemo) {
    warnings.push({
      severity: 'warning',
      code: 'DEMO_MODE_READONLY',
      message:
        'Modo DEMO activo: puedes preparar y validar propuestas organizativas en borrador local, pero el registro persistido solo se ejecuta en LIVE con sesión CEO.',
    });
  } else if (!canManageOrganization) {
    warnings.push({
      severity: 'warning',
      code: 'AUTHORITY_REQUIRED',
      message:
        'Se requiere sesión LIVE autenticada como CEO para ejecutar PUT /v1/organization/units y PUT /v1/organization/profiles.',
    });
  }

  // Combine persisted units + draft units to validate parent existence and cycles
  const parentByUnitId = new Map<string, string | null>();
  for (const u of persistedUnits) {
    if (u.id === 'unit-unassigned') continue;
    parentByUnitId.set(u.id, u.parentId || null);
  }
  for (const d of draftUnits) {
    const uid = d.id.trim();
    if (uid) {
      parentByUnitId.set(uid, d.parent_id?.trim() || null);
    }
  }

  for (const d of draftUnits) {
    const uid = d.id.trim();
    const code = d.code.trim();
    const name = d.name.trim();
    const leadRole = d.leadRole.trim();
    const parentId = d.parent_id?.trim() || null;

    if (!uid || !code || !name || !leadRole) {
      errors.push({
        severity: 'error',
        code: 'MISSING_REQUIRED_FIELD',
        targetId: d.draftId,
        message: `Unidad propuesta «${uid || name || 'sin identificador'}»: id, code, name y leadRole son obligatorios.`,
      });
      continue;
    }

    if (parentId && parentId === uid) {
      errors.push({
        severity: 'error',
        code: 'SELF_PARENT_UNIT',
        targetId: uid,
        message: `La unidad «${uid}» no puede declararse como su propia unidad padre.`,
      });
      continue;
    }

    if (parentId && !parentByUnitId.has(parentId)) {
      errors.push({
        severity: 'error',
        code: 'MISSING_PARENT_UNIT',
        targetId: uid,
        message: `La unidad padre «${parentId}» referenciada por «${uid}» no existe ni en el estado persistido ni en la propuesta actual.`,
      });
      continue;
    }

    // Cycle check walking up ancestors
    if (parentId) {
      const visited = new Set<string>([uid]);
      let cursor: string | null = parentId;
      while (cursor) {
        if (visited.has(cursor)) {
          errors.push({
            severity: 'error',
            code: 'HIERARCHY_CYCLE',
            targetId: uid,
            message: `Ciclo jerárquico detectado en la unidad «${uid}» a través de «${cursor}».`,
          });
          break;
        }
        visited.add(cursor);
        cursor = parentByUnitId.get(cursor) || null;
      }
    }
  }

  for (const p of draftProfiles) {
    const pid = p.principal_id.trim();
    const uid = (p.unit_id || '').trim();
    const roleTitle = p.role_title.trim();
    const managerId = p.manager_principal_id?.trim() || null;

    if (!pid || !uid || !roleTitle) {
      errors.push({
        severity: 'error',
        code: 'MISSING_REQUIRED_FIELD',
        targetId: p.draftId,
        message: `Perfil propuesto «${pid || 'sin principal'}»: principal_id, unit_id y role_title son obligatorios.`,
      });
      continue;
    }

    if (managerId && managerId === pid) {
      errors.push({
        severity: 'error',
        code: 'SELF_MANAGER_PROFILE',
        targetId: pid,
        message: `El principal «${pid}» no puede declararse como su propio responsable (manager_principal_id).`,
      });
    }

    if (!parentByUnitId.has(uid)) {
      errors.push({
        severity: 'error',
        code: 'MISSING_PROFILE_UNIT',
        targetId: pid,
        message: `El perfil de «${pid}» apunta a la unidad «${uid}», que no existe en las unidades persistidas ni en la propuesta.`,
      });
    }
  }

  const hasProposalItems = draftUnits.length > 0 || draftProfiles.length > 0;
  const isValidForSubmission = hasProposalItems && errors.length === 0;

  return {
    isValidForSubmission,
    canSubmitAuthorized: isValidForSubmission && canManageOrganization && !isDemo,
    errors,
    warnings,
    constitutionalNotice:
      'Constituir unidades o registrar perfiles organizativos no crea agentes técnicos, no habilita credenciales deshabilitadas ni otorga autorizaciones de proyecto (project_grants).',
  };
}

export function buildEnterpriseProjection(params: {
  origin: 'live' | 'demo';
  persistedUnits: OrgUnit[];
  effectiveUnits: OrgUnit[];
  rooms: OfficeRoomConfig[];
  agents: AgentIdentity[];
  historicalAgentCount: number;
  coverage?: OrganizationCoverage;
  diagnostics: OrganizationAttributionDiagnostics;
  projects: ProjectSummary[];
  alerts: AlertSummary[];
  decisions: DecisionSummary[];
}): EnterpriseProjection {
  const {
    origin,
    persistedUnits,
    effectiveUnits,
    rooms,
    agents,
    historicalAgentCount,
    coverage,
    diagnostics,
    projects,
    alerts,
    decisions,
  } = params;

  const declaredUnits = persistedUnits.filter((u) => u.id !== 'unit-unassigned');
  const workstations: WorkstationPositionSlot[] = [];

  for (const unit of effectiveUnits) {
    const room = rooms.find((r) => r.id === unit.id);
    const unitAgents = agents.filter((a) => a.unitId === unit.id);
    const capacity = Math.max(
      room?.workstationCapacity || 0,
      unitAgents.length,
      unit.id === 'unit-unassigned' ? Math.max(1, unitAgents.length) : 2
    );

    for (let idx = 0; idx < capacity; idx++) {
      const occupant = unitAgents[idx] || null;
      const activeAssignment =
        occupant?.currentAssignments.find((asg) => asg.status === 'ACTIVE') ||
        occupant?.currentAssignments[0] ||
        null;
      const latestExec = occupant?.executionHistory?.[0] || null;

      let occupancyState: WorkstationOccupancyState = 'VACANT';
      if (occupant) {
        if (
          occupant.operationalState === 'EJECUTANDO' ||
          occupant.status === 'BUSY' ||
          activeAssignment?.status === 'ACTIVE'
        ) {
          occupancyState = 'OCCUPIED_ACTIVE';
        } else if (activeAssignment) {
          occupancyState = 'ASSIGNED_NO_LEASE';
        } else {
          occupancyState = 'OCCUPIED_IDLE';
        }
      }

      const col = idx % 2 === 0 ? -1 : 1;
      const row = Math.floor(idx / 2);
      const wx = (room?.x ?? 0) + col * 1.25;
      const wz = (room?.z ?? 0) - 0.6 + row * 1.3;

      workstations.push({
        id: `ws-${unit.id}-${idx + 1}`,
        unitId: unit.id,
        unitCode: unit.code,
        unitName: unit.name,
        slotIndex: idx + 1,
        positionTitle:
          occupant?.roleTitle && occupant.roleTitle !== 'Sin perfil registrado'
            ? occupant.roleTitle
            : unit.id === 'unit-unassigned'
            ? `Puesto Temporal Sin Adscripción #${idx + 1}`
            : `Puesto de ${unit.name} #${idx + 1}`,
        responsibilitySummary:
          unit.description ||
          (unit.id === 'unit-unassigned'
            ? 'Puesto de contingencia para identidades sin perfil organizativo confirmado.'
            : `Puesto operativo adscrito a ${unit.name}.`),
        occupancyState,
        technicalIdentityId: occupant?.id || null,
        assignedAgentName: occupant?.name || null,
        credentialStatus: occupant?.credentialStatus || (occupant ? 'ENABLED' : null),
        profileRoleTitle: occupant?.roleTitle || null,
        managerId: occupant?.managerId || unit.leadAgentId || null,
        competencies: occupant?.competencies || [],
        activeWorkId: activeAssignment?.taskId || activeAssignment?.id || null,
        activeWorkTitle: activeAssignment?.taskTitle || activeAssignment?.projectName || null,
        activeProjectId: activeAssignment?.projectId || null,
        activeWorkState: activeAssignment?.status || null,
        activeSessionId: latestExec?.id || activeAssignment?.id || null,
        leaseState: activeAssignment?.status || null,
        heartbeatStatus: occupant?.heartbeatStatus || null,
        lastHeartbeatAt: occupant?.lastHeartbeatAt || null,
        llmProvider: latestExec?.provider || null,
        llmModel: latestExec?.model || null,
        backendVersion: latestExec?.backendVersion || null,
        worldPosition: { x: Number(wx.toFixed(2)), z: Number(wz.toFixed(2)) },
      });
    }
  }

  // Meeting tables: only show real shared work items across >= 2 agents
  const sharedWorkMap = new Map<
    string,
    {
      projectId: string;
      workId: string;
      title: string;
      agents: AgentIdentity[];
    }
  >();

  for (const agent of agents) {
    for (const asg of agent.currentAssignments) {
      const workId = asg.taskId || asg.id;
      const key = `${asg.projectId}::${workId}`;
      const existing = sharedWorkMap.get(key);
      if (existing) {
        if (!existing.agents.some((a) => a.id === agent.id)) {
          existing.agents.push(agent);
        }
      } else {
        sharedWorkMap.set(key, {
          projectId: asg.projectId,
          workId,
          title: asg.taskTitle || asg.projectName,
          agents: [agent],
        });
      }
    }
  }

  const verifiedCoordinations: MeetingCoordinationItem[] = [];
  for (const [key, item] of sharedWorkMap.entries()) {
    if (item.agents.length >= 2) {
      verifiedCoordinations.push({
        id: `coord-${key}`,
        projectId: item.projectId,
        workId: item.workId,
        title: item.title,
        participantAgentIds: item.agents.map((a) => a.id),
        participantNames: item.agents.map((a) => a.name),
        evidenceKind: 'shared-work-item',
      });
    }
  }

  const meetingTables: MeetingTableEntity[] = [
    {
      id: 'meeting-table-north',
      label: 'Mesa de Coordinación Interdepartamental Norte',
      zoneName: 'Atrio Corporativo · Sector Norte',
      worldPosition: { x: -2.9, z: 0 },
      activeCoordinations: verifiedCoordinations,
      hasVerifiedMeeting: verifiedCoordinations.length > 0,
      governanceNote:
        verifiedCoordinations.length > 0
          ? 'Coordinación acreditada por asignación compartida persistida en el backend.'
          : 'Sin reunión activa acreditada. La proximidad visual de avatares nunca constituye una reunión empresarial.',
    },
    {
      id: 'meeting-table-south',
      label: 'Mesa de Revisión y Gobernanza Sur',
      zoneName: 'Atrio Corporativo · Sector Sur',
      worldPosition: { x: 2.9, z: 0 },
      activeCoordinations: [],
      hasVerifiedMeeting: false,
      governanceNote:
        'Mesa disponible para sesiones de coordinación registradas. No se simulan reuniones sin evidencia persistida.',
    },
  ];

  // Spatial workflow links by project
  const workflowLinks: SpatialDepartmentWorkflowLink[] = projects.map((proj) => {
    const participatingUnits = new Set<string>();
    const participatingCodes = new Set<string>();
    let activeTasksCount = 0;
    let blockedTasksCount = 0;

    for (const agent of agents) {
      const matchesProject =
        agent.currentAssignments.some((asg) => asg.projectId === proj.id) ||
        agent.grants?.some((g) => g.projectId === proj.id);
      if (matchesProject) {
        participatingUnits.add(agent.unitId);
        const uObj = effectiveUnits.find((u) => u.id === agent.unitId);
        if (uObj) participatingCodes.add(uObj.code);
        activeTasksCount += agent.currentAssignments.filter((asg) => asg.projectId === proj.id).length;
      }
      blockedTasksCount += (agent.executionHistory || []).filter(
        (ex) =>
          ex.projectId === proj.id &&
          (ex.isBudgetExceeded || ex.isNoProgressRetry || Boolean(ex.error || ex.alert))
      ).length;
    }

    const inProgressFromCounts = proj.taskCounts?.IN_PROGRESS || 0;
    const pendingDecs = decisions.filter((d) => d.subjectId === proj.id).length;
    const status: 'ACTIVE' | 'BLOCKED' | 'IDLE' =
      blockedTasksCount > 0 || proj.status === 'BLOCKED'
        ? 'BLOCKED'
        : activeTasksCount > 0 || inProgressFromCounts > 0
        ? 'ACTIVE'
        : 'IDLE';

    return {
      id: `wf-${proj.id}`,
      projectId: proj.id,
      projectName: proj.name,
      participatingUnitIds: Array.from(participatingUnits),
      participatingUnitCodes: Array.from(participatingCodes),
      activeTasksCount: Math.max(activeTasksCount, inProgressFromCounts),
      blockedTasksCount,
      pendingDecisionsCount: pendingDecs,
      status,
    };
  });

  // Operational timeline entries (derived strictly from persisted records)
  const timelineEntries: OperationalTimelineEntry[] = [];

  for (const agent of agents) {
    for (const ex of agent.executionHistory || []) {
      const ts = ex.createdAt || agent.lastEvidenceAt || '';
      if (!ts) continue;
      timelineEntries.push({
        id: `tl-exec-${agent.id}-${ex.id}`,
        timestamp: ts,
        category: 'EXECUTION',
        title: `${agent.name} · Ejecución ${ex.id} (${ex.status})`,
        detail:
          ex.error ||
          ex.alert ||
          ex.checkDetails ||
          ex.conclusion ||
          `Tarea ${ex.taskTitle || ex.taskId} en proyecto ${ex.projectName || ex.projectId}`,
        agentId: agent.id,
        agentName: agent.name,
        unitId: agent.unitId,
        projectId: ex.projectId,
        workId: ex.taskId,
        modelLabel: [ex.provider, ex.model].filter(Boolean).join(' / ') || null,
        costEstimateUsd: typeof ex.costEstimateUsd === 'number' ? ex.costEstimateUsd : null,
        isBlocked: Boolean(ex.isBudgetExceeded || ex.isNoProgressRetry || ex.error || ex.alert),
        origin,
      });
    }

    for (const asg of agent.currentAssignments) {
      if (!asg.assignedAt) continue;
      const workId = asg.taskId || asg.id;
      timelineEntries.push({
        id: `tl-asg-${agent.id}-${workId}`,
        timestamp: asg.assignedAt,
        category: 'ASSIGNMENT',
        title: `${agent.name} · Encargo ${asg.status}: ${asg.taskTitle || asg.projectName}`,
        detail: `Proyecto ${asg.projectId} · Tarea ${workId}`,
        agentId: agent.id,
        agentName: agent.name,
        unitId: agent.unitId,
        projectId: asg.projectId,
        workId,
        modelLabel: null,
        costEstimateUsd: null,
        isBlocked: false,
        origin,
      });
    }
  }

  for (const alert of alerts) {
    timelineEntries.push({
      id: `tl-alert-${alert.id}`,
      timestamp: alert.timestamp || '',
      category: 'ALERT',
      title: `Alerta [${(alert.severity || 'info').toUpperCase()}]: ${alert.title}`,
      detail: alert.description || '',
      agentId: null,
      agentName: null,
      unitId: null,
      projectId: alert.source || null,
      workId: null,
      modelLabel: null,
      costEstimateUsd: null,
      isBlocked: alert.severity === 'critical' || alert.severity === 'high',
      origin,
    });
  }

  for (const dec of decisions) {
    timelineEntries.push({
      id: `tl-dec-${dec.id}`,
      timestamp: dec.createdAt || '',
      category: 'DECISION',
      title: `Decisión [${dec.category}]: ${dec.title}`,
      detail: dec.description || '',
      agentId: null,
      agentName: null,
      unitId: null,
      projectId: dec.subjectId || null,
      workId: dec.subjectId || null,
      modelLabel: null,
      costEstimateUsd: null,
      isBlocked: dec.category === 'policy_blocked' || dec.category === 'ceo_pending',
      origin,
    });
  }

  timelineEntries.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

  const occupiedWorkstationsCount = workstations.filter((w) => w.occupancyState !== 'VACANT').length;
  const vacantWorkstationsCount = workstations.filter((w) => w.occupancyState === 'VACANT').length;
  const resolvedCount = diagnostics.resolvedAgentsCount ?? 0;
  const unassignedCount = diagnostics.unassignedAgentsCount ?? 0;
  const requiresConstitution =
    origin === 'live' && (declaredUnits.length === 0 || unassignedCount > 0);

  const constitutionSummaryText =
    origin === 'demo'
      ? 'Simulación DEMO con organización canónica sintética.'
      : declaredUnits.length === 0
      ? `Organización LIVE pendiente de constitución: 0 unidades declaradas, ${resolvedCount} perfiles registrados y ${historicalAgentCount} principales históricos con credencial deshabilitada.`
      : unassignedCount > 0
      ? `Organización LIVE parcialmente constituida: ${declaredUnits.length} unidad(es) declarada(s), pero ${unassignedCount} agente(s) activo(s) carecen de perfil o unidad válida.`
      : `Organización LIVE constituida: ${declaredUnits.length} unidad(es) declarada(s) y ${resolvedCount} agente(s) adscrito(s).`;

  const atrium: CentralAtriumSummary = {
    id: 'atrium-central',
    label: 'Atrio Central Corporativo · Centro de Mando AAO',
    origin,
    declaredUnitsCount: declaredUnits.length,
    registeredProfilesCount: resolvedCount,
    activeAgentsCount: agents.length,
    historicalAgentCount,
    unassignedAgentsCount: unassignedCount,
    occupiedWorkstationsCount,
    vacantWorkstationsCount,
    activeProjectsCount: workflowLinks.filter((w) => w.status === 'ACTIVE').length || projects.length,
    blockedProjectsCount: workflowLinks.filter((w) => w.status === 'BLOCKED').length,
    pendingCeoDecisionsCount: decisions.filter(
      (d) =>
        d.category === 'ceo_pending' ||
        d.category === 'auditor_pending' ||
        d.category === 'policy_blocked'
    ).length,
    criticalAlertsCount: alerts.filter((a) => a.severity === 'critical' || a.severity === 'high').length,
    coverage,
    requiresConstitution,
    constitutionSummaryText,
  };

  return {
    origin,
    atrium,
    workstations,
    meetingTables,
    workflowLinks,
    timelineEntries,
  };
}
