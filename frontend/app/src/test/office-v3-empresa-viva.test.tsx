import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { VirtualOfficeView } from '../features/office/VirtualOfficeView';
import {
  buildEnterpriseProjection,
  validateConstitutionProposal,
} from '../features/office/v3/enterpriseProjection';
import { buildCorporateCampusLayout } from '../features/office/liveOfficeLayout';
import type {
  AgentIdentity,
  DataState,
  OrgUnit,
  OrganizationStructure,
  ProjectSummary,
} from '../domain/models';

const sampleUnits: OrgUnit[] = [
  {
    id: 'unit-eng',
    code: 'ENG',
    name: 'Ingeniería e Implementación',
    parentId: null,
    leadRole: 'Lead Engineer',
    leadAgentId: 'agent-eng-1',
    description: 'Construcción de software gobernado.',
    standingCount: 1,
    ephemeralCount: 0,
    activeProjectsCount: 1,
  },
];

const sampleAgents: AgentIdentity[] = [
  {
    id: 'agent-eng-1',
    name: 'Builder Alpha',
    type: 'STANDING',
    roleTitle: 'Senior Systems Engineer',
    managerId: 'ceo-1',
    competencies: ['typescript', 'postgres'],
    unitId: 'unit-eng',
    unitName: 'Ingeniería e Implementación',
    capabilities: [{ id: 'cap-1', name: 'Coding', level: 'CERTIFIED', verified: true }],
    grants: [{ projectId: 'proj-aao', permission: 'work:execute', active: true }],
    heartbeatStatus: 'HEALTHY',
    lastHeartbeatAt: '2026-11-03T16:00:00Z',
    status: 'BUSY',
    credentialStatus: 'ENABLED',
    operationalState: 'EJECUTANDO',
    currentAssignments: [
      {
        id: 'asg-1',
        taskId: 'work-101',
        taskTitle: 'Implementar inspector de puestos',
        projectId: 'proj-aao',
        projectName: 'AAO Core Platform',
        status: 'ACTIVE',
        assignedAt: '2026-11-03T15:30:00Z',
      },
    ],
    executionHistory: [
      {
        id: 'sess-live-99',
        taskId: 'work-101',
        taskTitle: 'Implementar inspector de puestos',
        projectId: 'proj-aao',
        projectName: 'AAO Core Platform',
        createdAt: '2026-11-03T15:45:00Z',
        status: 'SUCCEEDED',
        attempts: 1,
        provider: 'anthropic',
        model: 'claude-3-7-sonnet',
        backendVersion: 'aao-core-0.9',
        costEstimateUsd: 0.0425,
      },
    ],
    authorityBoundary: 'Subordinado a Auditoría y CEO',
  },
];

const sampleProjects: ProjectSummary[] = [
  {
    id: 'proj-aao',
    name: 'AAO Core Platform',
    status: 'ACTIVE',
    taskCounts: {
      IN_PROGRESS: 1,
      READY: 2,
      DONE: 5,
    },
  },
];

describe('AAO Frontend V3 — Empresa Viva (Proyección, Puestos, Constitución y Multiventana)', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('separa explícitamente Puesto Organizativo, Identidad Técnica, Perfil, Asignación, Sesión y Modelo LLM', () => {
    const campus = buildCorporateCampusLayout(sampleUnits, sampleAgents, { isDemo: false });
    const projection = buildEnterpriseProjection({
      origin: 'live',
      persistedUnits: sampleUnits,
      effectiveUnits: campus.effectiveUnits,
      rooms: campus.rooms,
      agents: campus.normalizedAgents,
      historicalAgentCount: 7,
      diagnostics: campus.diagnostics,
      projects: sampleProjects,
      alerts: [],
      decisions: [],
    });

    // Debe haber puestos ocupados y vacantes en Ingeniería
    const occupiedSlot = projection.workstations.find((w) => w.occupancyState === 'OCCUPIED_ACTIVE');
    const vacantSlot = projection.workstations.find((w) => w.occupancyState === 'VACANT');

    expect(occupiedSlot).toBeDefined();
    expect(occupiedSlot?.unitId).toBe('unit-eng');
    expect(occupiedSlot?.technicalIdentityId).toBe('agent-eng-1');
    expect(occupiedSlot?.profileRoleTitle).toBe('Senior Systems Engineer');
    expect(occupiedSlot?.activeWorkId).toBe('work-101');
    expect(occupiedSlot?.activeSessionId).toBe('sess-live-99');
    expect(occupiedSlot?.llmProvider).toBe('anthropic');
    expect(occupiedSlot?.llmModel).toBe('claude-3-7-sonnet');

    expect(vacantSlot).toBeDefined();
    expect(vacantSlot?.technicalIdentityId).toBeNull();
    expect(vacantSlot?.activeWorkId).toBeNull();

    // Mesa de reunión no inventa reuniones con un solo agente trabajando
    expect(projection.meetingTables[0].hasVerifiedMeeting).toBe(false);
    expect(projection.meetingTables[0].governanceNote).toContain(
      'La proximidad visual de avatares nunca constituye una reunión empresarial'
    );
  });

  it('valida ciclos jerárquicos, autogestión y existencia de unidad padre en propuestas organizativas', () => {
    const cycleReport = validateConstitutionProposal({
      persistedUnits: [],
      draftUnits: [
        {
          draftId: 'd1',
          id: 'unit-a',
          code: 'A',
          name: 'Unidad A',
          parent_id: 'unit-b',
          lead_principal_id: null,
          leadRole: 'Lead A',
          description: '',
          enabled: true,
        },
        {
          draftId: 'd2',
          id: 'unit-b',
          code: 'B',
          name: 'Unidad B',
          parent_id: 'unit-a',
          lead_principal_id: null,
          leadRole: 'Lead B',
          description: '',
          enabled: true,
        },
      ],
      draftProfiles: [
        {
          draftId: 'p1',
          principal_id: 'worker-1',
          display_name: 'Worker 1',
          unit_id: 'unit-a',
          role_title: 'Engineer',
          manager_principal_id: 'worker-1',
          enabled: true,
        },
      ],
      canManageOrganization: true,
      isDemo: false,
    });

    expect(cycleReport.isValidForSubmission).toBe(false);
    expect(cycleReport.errors.some((e) => e.code === 'HIERARCHY_CYCLE')).toBe(true);
    expect(cycleReport.errors.some((e) => e.code === 'SELF_MANAGER_PROFILE')).toBe(true);
  });

  it('muestra el diagnóstico real 0 / 0 / 7 en el Centro de Constitución Organizativa y ejecuta PUT autorizados en sesión CEO LIVE', async () => {
    const emptyLiveOrg: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      fetchedAt: '2026-11-03T16:10:00Z',
      data: {
        units: [],
        agents: [],
        totalStandingAgents: 0,
        totalEphemeralAgents: 0,
        totalUnknownAgents: 0,
        historicalAgentCount: 7,
        activeAssignmentsCount: 0,
      },
    };

    const onSaveUnit = vi.fn().mockResolvedValue({
      kind: 'ready',
      origin: 'live',
      fetchedAt: '2026-11-03T16:11:00Z',
      data: sampleUnits[0],
    });
    const onSaveProfile = vi.fn().mockResolvedValue({
      kind: 'ready',
      origin: 'live',
      fetchedAt: '2026-11-03T16:11:00Z',
      data: sampleAgents[0],
    });
    const onRefresh = vi.fn();

    render(
      <VirtualOfficeView
        organization={emptyLiveOrg}
        projects={{ kind: 'ready', origin: 'live', fetchedAt: '2026-11-03T16:10:00Z', data: sampleProjects }}
        canManageOrganization={true}
        onSaveUnit={onSaveUnit}
        onSaveProfile={onSaveProfile}
        onRefresh={onRefresh}
      />
    );

    // Abrir simultáneamente el Centro de Constitución Organizativa y el Explorador
    fireEvent.click(screen.getByTestId('launcher-btn-constitution-center'));
    fireEvent.click(screen.getByTestId('launcher-btn-organization-explorer'));

    expect(screen.getByTestId('spatial-window-constitution-center')).toBeVisible();
    expect(screen.getByTestId('spatial-window-organization-explorer')).toBeVisible();

    // Comprobar contadores 0 / 0 / 7 del Paso 1
    expect(screen.getByTestId('counter-declared-units')).toHaveTextContent('0');
    expect(screen.getByTestId('counter-registered-profiles')).toHaveTextContent('0');
    expect(screen.getByTestId('counter-historical-principals')).toHaveTextContent('7');

    // Preparar una unidad en borrador local (Paso 2)
    fireEvent.change(screen.getByLabelText('ID de unidad propuesta'), {
      target: { value: 'unit-eng' },
    });
    fireEvent.change(screen.getByLabelText('Código de unidad propuesta'), {
      target: { value: 'ENG' },
    });
    fireEvent.change(screen.getByLabelText('Nombre de unidad propuesta'), {
      target: { value: 'Ingeniería e Implementación' },
    });
    fireEvent.change(screen.getByLabelText('Rol responsable de unidad propuesta'), {
      target: { value: 'Lead Engineer' },
    });
    fireEvent.click(screen.getByText('Añadir unidad al borrador'));

    expect(screen.getByTestId('constitution-staged-proposal')).toHaveTextContent('Ingeniería e Implementación');

    // Ejecutar Paso 4 (Registrar en backend) y Paso 5 (Refrescar desde GET /v1/organization)
    const submitBtn = screen.getByTestId('constitution-submit-btn');
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(onSaveUnit).toHaveBeenCalledTimes(1);
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });
  });

  it('permite inspeccionar Puestos, Mesas de Reunión, Atrio Central, Flujos Espaciales y Cronología preservando estado entre ventanas', () => {
    const liveOrgWithAgent: DataState<OrganizationStructure> = {
      kind: 'ready',
      origin: 'live',
      fetchedAt: '2026-11-03T16:20:00Z',
      data: {
        units: sampleUnits,
        agents: sampleAgents,
        totalStandingAgents: 1,
        totalEphemeralAgents: 0,
        totalUnknownAgents: 0,
        historicalAgentCount: 7,
        activeAssignmentsCount: 1,
      },
    };

    render(
      <VirtualOfficeView
        organization={liveOrgWithAgent}
        projects={{ kind: 'ready', origin: 'live', fetchedAt: '2026-11-03T16:20:00Z', data: sampleProjects }}
        canManageOrganization={false}
      />
    );

    // 1. Inspeccionar Atrio Central desde la barra espacial V3
    fireEvent.click(screen.getByText('🏛️ Atrio Central'));
    expect(screen.getByTestId('entity-inspector-atrium')).toHaveTextContent(
      'Atrio Central Corporativo · Centro de Mando AAO'
    );

    // 2. Abrir Explorador Organizativo y seleccionar un Puesto de Trabajo (Workstation)
    fireEvent.click(screen.getByTestId('launcher-btn-organization-explorer'));
    const wsCard = screen.getByTestId('workstation-card-ws-unit-eng-1');
    expect(wsCard).toHaveTextContent('OCUPADO · EJECUTANDO');
    fireEvent.click(screen.getAllByText('Ver Puesto')[0]);

    const wsInspector = screen.getByTestId('entity-inspector-workstation');
    expect(wsInspector).toHaveTextContent('1. Puesto Organizativo (Workstation)');
    expect(wsInspector).toHaveTextContent('2. Identidad Técnica (Principal)');
    expect(wsInspector).toHaveTextContent('3. Perfil Organizativo (organization_profiles)');
    expect(wsInspector).toHaveTextContent('4. Asignación de Trabajo (work_items)');
    expect(wsInspector).toHaveTextContent('5. Sesión Ejecutora (Lease)');
    expect(wsInspector).toHaveTextContent('6. Modelo LLM / Runtime (Observado)');
    expect(wsInspector).toHaveTextContent('claude-3-7-sonnet');

    // 3. Abrir Flujos Espaciales y Cronología simultáneamente
    fireEvent.click(screen.getByTestId('launcher-btn-spatial-workflows'));
    fireEvent.click(screen.getByTestId('launcher-btn-operational-timeline'));
    expect(screen.getByTestId('spatial-workflows-panel')).toHaveTextContent('AAO Core Platform');
    expect(screen.getByTestId('operational-timeline-panel')).toHaveTextContent('$0.0425 USD');
  });
});
