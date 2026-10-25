/**
 * AAO Frontend Domain Models
 * Spec: AAO-FE-ARCH-2026-10-25 Section 5
 */

export type DataOrigin = 'live' | 'demo';
export type Availability = 'available' | 'unavailable' | 'forbidden' | 'error';
export type Confidence = 'verified' | 'reported' | 'proposed' | 'blocked' | 'unknown';

export type DataState<T> =
  | { kind: 'ready'; origin: DataOrigin; data: T; fetchedAt: string; evidence?: EvidenceRef[] }
  | { kind: 'empty'; origin: DataOrigin; fetchedAt: string }
  | { kind: 'unavailable'; reason: string; retryable: boolean }
  | { kind: 'forbidden'; reason: string }
  | { kind: 'error'; code: string; message: string; retryable: boolean };

export interface EvidenceRef {
  source: string;
  exactSha?: string;
  artifactId?: string;
  verifiedAt?: string;
  confidence?: Confidence;
}

export type BoardStage =
  | 'INBOX'
  | 'READY'
  | 'IN_PROGRESS'
  | 'IN_REVIEW'
  | 'VERIFIED'
  | 'DONE';

export const BOARD_STAGES: readonly BoardStage[] = [
  'INBOX',
  'READY',
  'IN_PROGRESS',
  'IN_REVIEW',
  'VERIFIED',
  'DONE',
] as const;

export const BOARD_STAGE_LABELS: Record<BoardStage, string> = {
  INBOX: 'Entrada',
  READY: 'Preparado',
  IN_PROGRESS: 'En curso',
  IN_REVIEW: 'Revisión',
  VERIFIED: 'Verificado',
  DONE: 'Completado',
};

export interface ProjectSummary {
  id: string;
  name: string;
  description?: string;
  status?: string;
  taskCounts?: Partial<Record<BoardStage, number>>;
  mandateId?: string;
}

export interface TaskExecutionRecord {
  id: string;
  status: string;
  worker_id?: string;
  attempts: number;
  created_at: string;
  lease_expires_at?: string | null;
  lease_token?: string | null;
  result?: unknown;
}

export interface TaskReviewRecord {
  id: string;
  work_id: string;
  reviewer_id: string;
  decision: string;
  candidate_sha?: string;
  evidence?: unknown;
  created_at: string;
}

/** A pull request published for a task (backend event work.pr_opened). */
export interface TaskPullRequest {
  pr_number: number;
  pr_url: string;
  candidate_sha: string;
  base_sha?: string;
  branch?: string;
  publisher?: string;
  pusher?: string;
  review_id?: string;
  created_at?: string;
  /** OPEN, CLOSED_UNMERGED or MERGED, derived by the backend from work.pr_closed / work.completed. */
  state?: string;
  merge_commit_sha?: string;
}

/** CEO closure of work completed outside the agent cycle (event work.resolved_outside_cycle). */
export interface TaskResolution {
  reason: string;
  pr_number: number;
  merge_commit_sha: string;
  resolved_by: string;
  created_at?: string;
}

/** One entry of GET /v1/projects/{id}/activity (audit events and execution journal). */
export interface ActivityEvent {
  id: string;
  subject_id: string;
  kind: string;
  details: unknown;
  created_at: string;
}

export interface TaskItem {
  id: string;
  title: string;
  status: string; // Preserves exact semantic status from backend without silent conversion
  rawStatus?: string;
  isUnrecognizedStatus?: boolean;
  acceptanceCriteria?: string[];
  evidence?: unknown[];
  executions?: TaskExecutionRecord[];
  reviews?: TaskReviewRecord[];
  pullRequests?: TaskPullRequest[];
  resolution?: TaskResolution | null;
  routingDecisions?: import('../features/ronin/modelProfile').ModelRoutingRecord[];
  authorId?: string;
  createdAt?: string;
}

export interface ProjectBoard {
  projectId: string;
  projectName?: string;
  items: TaskItem[];
  stages: Record<BoardStage, TaskItem[]>;
  unrecognizedItems: TaskItem[]; // Tasks with unrecognized/unanchored status outside canonical 6
  totalCount: number;
}

export interface WorkSummary {
  totalTasks: number;
  byStage: Record<BoardStage, number>;
  unrecognizedCount: number;
  activeWorkersCount?: number;
  inReviewCount: number;
  blockedCount: number;
}

export interface GovernanceClassification {
  rLevel: 'R0' | 'R1' | 'R2' | 'R3';
  assuranceLevel: 'A' | 'B' | 'C' | 'D';
}

export interface GovernanceSummary {
  certified: boolean;
  classification?: GovernanceClassification;
  evidenceRef?: EvidenceRef;
  pendingReviewsCount: number;
  lastAuditDate?: string;
  notes: string;
}

export interface OperationsSummary {
  serviceHealth: 'healthy' | 'degraded' | 'unavailable' | 'unknown';
  readyStatus: boolean;
  checkedAt: string;
  message: string;
}

export interface AlertSummary {
  id: string;
  title: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  source: string;
  confidence: Confidence;
  timestamp: string;
  description: string;
}

export interface DecisionSummary {
  id: string;
  title: string;
  category: 'ceo_pending' | 'auditor_pending' | 'policy_blocked' | 'informational' | 'unknown';
  subjectId: string;
  proposedBy?: string;
  createdAt: string;
  evidenceRef?: EvidenceRef;
  description: string;
}

export interface CapabilitySummary {
  capability_id: string;
  version: string;
  capability_type: string;
  status: string;
  provenance: unknown;
  contract: unknown;
  modelProfile?: import('../features/ronin/modelProfile').ModelProfile | null;
  required_permissions?: string[];
  risks?: string[];
  dependencies?: string[];
  tests?: string[];
  compatibility?: string[];
  evidence?: unknown;
  created_by?: string;
  created_at: string;
  execution_authorized: boolean;
}

export interface EvaluationSummary {
  task_id: string;
  details: unknown;
  created_at: string;
  task_title?: string;
}

export type PrincipalVerificationStatus =
  | 'verified'      // Backend HTTP verification passed with valid credential
  | 'declared'      // Role/identity declared by client without independent backend proof
  | 'rejected'      // Backend explicitly rejected credential (401/403)
  | 'unsupported';  // Backend does not expose an identity/verification endpoint for this role

export interface PrincipalSummary {
  principal_id: string;
  kind: 'AGENT' | 'AUDITOR' | 'CEO';
  enabled: boolean;
  verificationStatus: PrincipalVerificationStatus;
  authMethod: string;
  grants?: Array<{
    project_id: string;
    capability: string;
    expires_at: string | null;
    active: boolean;
  }>;
}

export interface CeoOverview {
  projects: DataState<ProjectSummary[]>;
  work: DataState<WorkSummary>;
  governance: DataState<GovernanceSummary>;
  operations: DataState<OperationsSummary>;
  alerts: DataState<AlertSummary[]>;
  decisions: DataState<DecisionSummary[]>;
}

// ---------------------------------------------------------------------------
// Phase F3: Organization and Agent Structure Models
// Spec: AAO-FE-ARCH-2026-10-25 Section 14 & Mandate AAO-CEO-F3-2026-10-25
// ---------------------------------------------------------------------------

export type AgentType = 'STANDING' | 'EPHEMERAL' | 'UNKNOWN';

export type AgentOperationalState =
  | 'REGISTRADO'
  | 'ASIGNADO'
  | 'CONECTADO'
  | 'EJECUTANDO'
  | 'INACTIVO'
  | 'DESCONOCIDO'
  | 'NO_DISPONIBLE';

export type AgentHeartbeatStatus =
  | 'HEALTHY'       // Recent verified heartbeat within lease/window
  | 'STALE'         // Heartbeat timestamp exceeded freshness window
  | 'UNKNOWN'       // Agent declared or registered, heartbeat endpoint unconfigured
  | 'UNAVAILABLE';   // Backend heartbeat provider unreachable or offline

export type AgentOperationalStatus =
  | 'IDLE'
  | 'BUSY'
  | 'PAUSED'
  | 'OFFLINE'
  | 'DECOMMISSIONED'
  | 'UNKNOWN';

export type CapabilityKind = 'PERMISSION' | 'DECLARED' | 'CERTIFIED';

export interface AgentCapability {
  id: string;
  name: string;
  level: 'BASIC' | 'ADVANCED' | 'CERTIFIED';
  verified: boolean;
  kind?: CapabilityKind;
}

export interface AgentGrant {
  projectId: string;
  permission: string;
  active: boolean;
  expiresAt?: string | null;
}

export interface AgentAssignment {
  id: string;
  projectId: string;
  projectName: string;
  taskId?: string;
  taskTitle?: string;
  assignedAt: string;
  leaseExpiresAt?: string | null;
  status: 'ACTIVE' | 'EXPIRED' | 'COMPLETED' | 'UNKNOWN';
}

export interface AgentExecutionRecord {
  id: string;
  taskId: string;
  taskTitle: string;
  projectId: string;
  projectName: string;
  status: string;
  attempts: number;
  createdAt: string;
  leaseExpiresAt?: string | null;
  workerId?: string;
  // RONIN evidence fields (I1-I6)
  provider?: string | null;
  model?: string | null;
  backendVersion?: string | null;
  capabilityId?: string | null;
  capabilityVersion?: string | null;
  backendSource?: string | null;
  costEstimateUsd?: number | null;
  candidateSha?: string | null;
  conclusion?: string | null;
  check?: string | null;
  checkDetails?: string | null;
  error?: string | null;
  alert?: string | null;
  isNoProgressRetry?: boolean;
  isBudgetExceeded?: boolean;
  rawResult?: unknown;
}

export interface AgentIdentity {
  id: string;
  name: string;
  type: AgentType;
  roleTitle: string;
  managerId?: string | null;
  unitId: string;
  unitName?: string;
  capabilities: AgentCapability[];
  grants?: AgentGrant[];
  heartbeatStatus: AgentHeartbeatStatus;
  lastHeartbeatAt: string | null;
  status: AgentOperationalStatus;
  operationalState?: AgentOperationalState;
  currentAssignments: AgentAssignment[];
  executionHistory?: AgentExecutionRecord[];
  authorityBoundary: string;
  isSyntheticDemo?: boolean;
  lastEvidenceAt?: string | null;
  evidenceDescription?: string;
}

export interface OrgUnit {
  id: string;
  name: string;
  code: string;
  parentId: string | null;
  leadRole: string;
  leadAgentId: string | null;
  description: string;
  standingCount: number;
  ephemeralCount: number;
  activeProjectsCount: number;
}

export interface OrganizationCoverage {
  totalProjects: number;
  inspectedProjects: number;
  failedProjects: number;
  isPartial: boolean;
  notes?: string;
}

export interface OrganizationStructure {
  units: OrgUnit[];
  agents: AgentIdentity[];
  totalStandingAgents: number;
  totalEphemeralAgents: number;
  totalUnknownAgents?: number;
  activeAssignmentsCount: number;
  coverage?: OrganizationCoverage;
}
