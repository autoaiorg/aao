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

export interface TaskItem {
  id: string;
  title: string;
  status: BoardStage;
  acceptanceCriteria?: string[];
  evidence?: unknown[];
  executions?: TaskExecutionRecord[];
  reviews?: TaskReviewRecord[];
  authorId?: string;
  createdAt?: string;
}

export interface ProjectBoard {
  projectId: string;
  projectName?: string;
  items: TaskItem[];
  stages: Record<BoardStage, TaskItem[]>;
  totalCount: number;
}

export interface WorkSummary {
  totalTasks: number;
  byStage: Record<BoardStage, number>;
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

export interface PrincipalSummary {
  principal_id: string;
  kind: 'AGENT' | 'AUDITOR' | 'CEO';
  enabled: boolean;
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
