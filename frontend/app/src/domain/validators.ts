/**
 * Defensive runtime parsers using Zod
 * Ensures HTTP responses adhere strictly to contracts without trusting raw JSON.
 */

import { z } from 'zod';

export const BoardStageSchema = z.enum([
  'INBOX',
  'READY',
  'IN_PROGRESS',
  'IN_REVIEW',
  'VERIFIED',
  'DONE',
]);

export const ProjectSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
  state: z.string().optional(),
  status: z.string().optional(),
  mandate_id: z.string().optional(),
});

export const ProjectsListSchema = z.array(ProjectSummarySchema);

export const ExecutionRecordSchema = z.object({
  id: z.string(),
  status: z.string(),
  worker_id: z.string().optional(),
  attempts: z.number().default(0),
  created_at: z.string(),
  result: z.unknown().optional(),
});

export const ReviewRecordSchema = z.object({
  id: z.string(),
  work_id: z.string(),
  reviewer_id: z.string(),
  decision: z.string(),
  candidate_sha: z.string().optional(),
  evidence: z.unknown().optional(),
  created_at: z.string(),
});

// P1 Finding 3 Fix: Preserves exact status string from backend; NO silent mutation to INBOX!
export const WorkItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.string(), // Preserves exact string without silent conversion
  acceptance_criteria: z.array(z.string()).optional(),
  evidence: z.array(z.unknown()).optional(),
  executions: z.array(ExecutionRecordSchema).optional(),
  author_id: z.string().optional(),
  created_at: z.string().optional(),
});

export const ActivityEventSchema = z.object({
  id: z.string(),
  subject_id: z.string(),
  kind: z.string(),
  details: z.unknown(),
  created_at: z.string(),
});

export const PrincipalSchema = z.object({
  principal_id: z.string(),
  kind: z.enum(['AGENT', 'AUDITOR', 'CEO']),
  enabled: z.boolean(),
});

export const GrantSchema = z.object({
  principal_id: z.string().optional(),
  project_id: z.string(),
  capability: z.string(),
  expires_at: z.string().nullable().optional(),
  active: z.boolean().default(true),
});

export const CapabilitySchema = z.object({
  capability_id: z.string(),
  version: z.string(),
  capability_type: z.string(),
  status: z.string(),
  provenance: z.unknown().optional(),
  contract: z.unknown().optional(),
  required_permissions: z.array(z.string()).optional(),
  risks: z.array(z.string()).optional(),
  dependencies: z.array(z.string()).optional(),
  tests: z.array(z.string()).optional(),
  compatibility: z.array(z.string()).optional(),
  evidence: z.unknown().optional(),
  created_by: z.string().optional(),
  created_at: z.string(),
  execution_authorized: z.boolean().default(false),
});

export const CapabilityEvaluationSchema = z.object({
  task_id: z.string(),
  details: z.unknown().optional(),
  created_at: z.string(),
  task_title: z.string().optional(),
});

// Phase F3: Organization and Agent Structure Schemas
export const AgentTypeSchema = z.enum(['STANDING', 'EPHEMERAL', 'UNKNOWN']);

export const AgentHeartbeatStatusSchema = z.enum([
  'HEALTHY',
  'STALE',
  'UNKNOWN',
  'UNAVAILABLE',
]);

export const AgentOperationalStatusSchema = z.enum([
  'IDLE',
  'BUSY',
  'PAUSED',
  'OFFLINE',
  'DECOMMISSIONED',
  'UNKNOWN',
]);

export const AgentCapabilitySchema = z.object({
  id: z.string(),
  name: z.string(),
  level: z.enum(['BASIC', 'ADVANCED', 'CERTIFIED']),
  verified: z.boolean().default(false),
  kind: z.enum(['PERMISSION', 'DECLARED', 'CERTIFIED']).optional(),
});

export const AgentGrantSchema = z.object({
  projectId: z.string(),
  permission: z.string(),
  active: z.boolean(),
  expiresAt: z.string().nullable().optional(),
});

export const AgentAssignmentSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  projectName: z.string(),
  taskId: z.string().optional(),
  taskTitle: z.string().optional(),
  assignedAt: z.string(),
  leaseExpiresAt: z.string().nullable().optional(),
  status: z.enum(['ACTIVE', 'EXPIRED', 'COMPLETED', 'UNKNOWN']),
});

export const AgentOperationalStateSchema = z.enum([
  'REGISTRADO',
  'ASIGNADO',
  'CONECTADO',
  'EJECUTANDO',
  'INACTIVO',
  'DESCONOCIDO',
  'NO_DISPONIBLE',
]);

export const AgentIdentitySchema = z.object({
  id: z.string(),
  name: z.string(),
  type: AgentTypeSchema,
  roleTitle: z.string(),
  unitId: z.string(),
  unitName: z.string().optional(),
  capabilities: z.array(AgentCapabilitySchema).default([]),
  grants: z.array(AgentGrantSchema).optional(),
  heartbeatStatus: AgentHeartbeatStatusSchema,
  lastHeartbeatAt: z.string().nullable().default(null),
  status: AgentOperationalStatusSchema,
  operationalState: AgentOperationalStateSchema.optional(),
  currentAssignments: z.array(AgentAssignmentSchema).default([]),
  authorityBoundary: z.string(),
  isSyntheticDemo: z.boolean().optional(),
  lastEvidenceAt: z.string().nullable().optional(),
  evidenceDescription: z.string().optional(),
});

export const OrgUnitSchema = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  parentId: z.string().nullable(),
  leadRole: z.string(),
  leadAgentId: z.string().nullable(),
  description: z.string(),
  standingCount: z.number().default(0),
  ephemeralCount: z.number().default(0),
  activeProjectsCount: z.number().default(0),
});

export const OrganizationCoverageSchema = z.object({
  totalProjects: z.number(),
  inspectedProjects: z.number(),
  failedProjects: z.number(),
  isPartial: z.boolean(),
  notes: z.string().optional(),
});

export const OrganizationStructureSchema = z.object({
  units: z.array(OrgUnitSchema),
  agents: z.array(AgentIdentitySchema),
  totalStandingAgents: z.number().default(0),
  totalEphemeralAgents: z.number().default(0),
  totalUnknownAgents: z.number().default(0).optional(),
  activeAssignmentsCount: z.number().default(0),
  coverage: OrganizationCoverageSchema.optional(),
});
