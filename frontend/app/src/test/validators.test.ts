import { describe, it, expect } from 'vitest';
import {
  ProjectsListSchema,
  PrincipalSchema,
  WorkItemSchema,
  CapabilitySchema,
  CapabilityEvaluationSchema,
  OrgUnitSchema,
  AgentIdentitySchema,
  OrganizationStructureSchema,
} from '../domain/validators';

describe('Defensive Schema Validation', () => {
  it('validates valid projects array correctly', () => {
    const raw = [
      { id: 'proj-1', name: 'Alpha Project', state: 'ACTIVE' },
      { id: 'proj-2', name: 'Beta Project', description: 'Test project' },
    ];
    const parsed = ProjectsListSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data).toHaveLength(2);
      expect(parsed.data[0].name).toBe('Alpha Project');
    }
  });

  it('rejects corrupted projects array', () => {
    const raw = [{ invalid_field: 123 }];
    const parsed = ProjectsListSchema.safeParse(raw);
    expect(parsed.success).toBe(false);
  });

  it('validates principal credentials response', () => {
    const raw = {
      principal_id: 'agent-1234',
      kind: 'AGENT',
      enabled: true,
    };
    const parsed = PrincipalSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.kind).toBe('AGENT');
    }
  });

  it('preserves work item lifecycle status string exactly as received from backend', () => {
    const raw = {
      id: 'task-01',
      title: 'Fix issue',
      status: 'in_review',
    };
    const parsed = WorkItemSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.status).toBe('in_review');
    }
  });

  it('preserves unrecognized work item status without mutating to INBOX', () => {
    const raw = {
      id: 'task-02',
      title: 'Unrecognized stage',
      status: 'UNKNOWN_CUSTOM_STAGE',
    };
    const parsed = WorkItemSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.status).toBe('UNKNOWN_CUSTOM_STAGE');
    }
  });

  it('validates capability versions and enforces execution_authorized is false by default', () => {
    const raw = {
      capability_id: 'tool-test',
      version: '1.0.0',
      capability_type: 'agent_skill',
      status: 'ACTIVE',
      created_at: '2026-10-25T00:00:00Z',
    };
    const parsed = CapabilitySchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.execution_authorized).toBe(false);
    }
  });

  it('accepts the persisted object shape for capability compatibility metadata', () => {
    const raw = {
      capability_id: 'capability-with-runtime',
      version: '1.0.0',
      capability_type: 'agent_skill',
      status: 'ACTIVE',
      compatibility: { runtime: 'python>=3.12', platforms: ['linux'] },
      created_at: '2026-10-25T00:00:00Z',
    };
    const parsed = CapabilitySchema.safeParse(raw);
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(parsed.data.compatibility).toEqual(raw.compatibility);
  });

  it('validates capability evaluations record', () => {
    const raw = {
      task_id: 'task-100',
      details: { check: 'passed' },
      created_at: '2026-10-25T08:00:00Z',
      task_title: 'Evaluation Task',
    };
    const parsed = CapabilityEvaluationSchema.safeParse(raw);
    expect(parsed.success).toBe(true);
  });

  it('validates OrgUnitSchema and AgentIdentitySchema correctly', () => {
    const rawUnit = {
      id: 'unit-arch',
      name: 'Arquitectura de Sistemas',
      code: 'ARCH',
      parentId: null,
      leadRole: 'Arquitecto Jefe',
      leadAgentId: 'agent-1',
      description: 'Diseño de protocolos',
      standingCount: 2,
      ephemeralCount: 1,
      activeProjectsCount: 1,
    };
    const unitParsed = OrgUnitSchema.safeParse(rawUnit);
    expect(unitParsed.success).toBe(true);

    const rawAgent = {
      id: 'agent-1',
      name: 'Agente Prueba',
      type: 'STANDING',
      roleTitle: 'Desarrollador',
      unitId: 'unit-arch',
      capabilities: [
        { id: 'c1', name: 'TypeScript', level: 'CERTIFIED', verified: true },
      ],
      heartbeatStatus: 'HEALTHY',
      lastHeartbeatAt: '2026-10-25T10:00:00Z',
      status: 'IDLE',
      currentAssignments: [],
      authorityBoundary: 'Solo lectura',
    };
    const agentParsed = AgentIdentitySchema.safeParse(rawAgent);
    expect(agentParsed.success).toBe(true);

    const rawOrg = {
      units: [unitParsed.data],
      agents: [agentParsed.data],
      totalStandingAgents: 1,
      totalEphemeralAgents: 0,
      activeAssignmentsCount: 0,
    };
    const orgParsed = OrganizationStructureSchema.safeParse(rawOrg);
    expect(orgParsed.success).toBe(true);

    const invalidAgent = {
      id: 'agent-bad',
      type: 'INVALID_TYPE',
    };
    const badParsed = AgentIdentitySchema.safeParse(invalidAgent);
    expect(badParsed.success).toBe(false);
  });
});
