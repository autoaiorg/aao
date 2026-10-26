import type { DataState } from '../../domain/models';

export interface ProjectConversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectConversationMessage {
  id: string;
  sender: 'CEO' | 'AAO';
  message_kind?: 'CHAT' | 'WORK_GROUP_RESULT';
  body: string;
  related_work_id: string | null;
  work_status: string | null;
  latest_execution: {
    id: string;
    status: string;
    backend: string | null;
    provider: string | null;
    model: string | null;
  } | null;
  provider?: string | null;
  model?: string | null;
  turn_status?: 'PENDING' | 'COMPLETED' | 'FAILED' | null;
  turn_error_code?: string | null;
  turn_idempotency_key?: string | null;
  turn_lease_expires_at?: string | null;
  created_at: string;
}

export interface ConversationWorkRequestInput {
  title: string;
  description: string;
  acceptance_criteria: string[];
  due_date?: string | null;
}

export interface ConversationWorkRequestResult {
  id: string;
  status: string;
  created: boolean;
}

export interface ConversationWorkGroupInput extends ConversationWorkRequestInput {
  idempotency_key: string;
  based_on_message_ids?: string[];
  tasks: Array<{
    key: string;
    title: string;
    description: string;
    acceptance_criteria: string[];
    due_date?: string | null;
    depends_on: string[];
    required_competencies?: string[];
    assigned_principal_id?: string | null;
  }>;
}

export interface AssignableAgent {
  principal_id: string;
  display_name: string;
  competencies: string[];
}

export interface ConversationWorkGroupResult {
  id: string;
  project_id: string;
  conversation_id: string;
  parent_work_id: string;
  status: string;
  created: boolean;
  tasks: Array<{ id: string; title: string; status: string; required_competencies?: string[]; depends_on: string[] }>;
}

export interface ConversationWorkGroupProposal {
  proposal: Omit<ConversationWorkGroupInput, 'idempotency_key'>;
  based_on_message_ids: string[];
  provider: string;
  model: string;
  persisted_as_work: false;
}

export interface WorkGroupConsolidation {
  id: string;
  summary: string;
  source_sha256: string;
  idempotency_key: string;
  created_by: string;
  created_at: string;
}

export interface WorkGroupPartialReport {
  id: string;
  report_kind: 'PARTIAL' | 'CONFLICT_REVIEW';
  summary: string;
  source_sha256: string;
  idempotency_key: string;
  created_by: string;
  created_at: string;
}

export interface ProjectWorkGroup {
  id: string;
  conversation_id: string;
  parent_work_id: string;
  title: string;
  parent_status: string;
  source_sha256: string;
  consolidation_ready: boolean;
  children: Array<{
    work_id: string;
    status: string;
    assigned_principal_id: string | null;
    required_competencies?: string[];
    dispatch_block?: { principal_id: string | null; reason: string; created_at: string } | null;
    evidence: unknown;
    dependencies: Array<{ work_id: string; status: string }>;
    executions: Array<{ id: string; status: string; worker_id: string | null; result_sha256: string | null }>;
    reviews: Array<{ id: string; decision: string; candidate_sha: string | null; evidence: unknown }>;
  }>;
  consolidation: WorkGroupConsolidation | null;
  partial_reports: WorkGroupPartialReport[];
}

export interface WorkGroupConsolidationResult extends WorkGroupConsolidation {
  project_id: string;
  work_group_id: string;
  parent_work_id: string;
  source_snapshot: { children: ProjectWorkGroup['children'] };
  created: boolean;
}

export interface AaoConversationPort {
  listAssignableAgents(projectId: string): Promise<DataState<AssignableAgent[]>>;
  listProjectConversations(projectId: string): Promise<DataState<ProjectConversation[]>>;
  listConversationMessages(projectId: string, conversationId: string): Promise<DataState<ProjectConversationMessage[]>>;
  createProjectConversation(projectId: string, title: string): Promise<DataState<Pick<ProjectConversation, 'id' | 'project_id' | 'title'>>>;
  appendCEOConversationMessage(projectId: string, conversationId: string, body: string): Promise<DataState<ProjectConversationMessage>>;
  streamCEOConversationTurn(
    projectId: string,
    conversationId: string,
    body: string,
    idempotencyKey: string,
    onDelta: (delta: string) => void,
  ): Promise<DataState<{ message_id: string }>>;
  createWorkRequestFromMessage(
    projectId: string,
    conversationId: string,
    messageId: string,
    input: ConversationWorkRequestInput,
  ): Promise<DataState<ConversationWorkRequestResult>>;
  createWorkRequestFromConversation(
    projectId: string,
    conversationId: string,
    input: ConversationWorkRequestInput,
  ): Promise<DataState<ConversationWorkRequestResult>>;
  createWorkGroupFromConversation(
    projectId: string,
    conversationId: string,
    input: ConversationWorkGroupInput,
  ): Promise<DataState<ConversationWorkGroupResult>>;
  proposeWorkGroupFromConversation(
    projectId: string,
    conversationId: string,
  ): Promise<DataState<ConversationWorkGroupProposal>>;
  listProjectWorkGroups(projectId: string): Promise<DataState<ProjectWorkGroup[]>>;
  assignWorkGroupChild(workId: string, principalId: string): Promise<DataState<{ work_id: string; principal_id: string; assigned_by: string; grants_created: false }>>;
  confirmWorkGroupConsolidation(
    projectId: string,
    groupId: string,
    input: { idempotency_key: string; expected_source_sha256: string; summary: string },
  ): Promise<DataState<WorkGroupConsolidationResult>>;
  createWorkGroupPartialReport(
    projectId: string,
    groupId: string,
    input: { idempotency_key: string; expected_source_sha256: string; report_kind: 'PARTIAL' | 'CONFLICT_REVIEW'; summary: string },
  ): Promise<DataState<WorkGroupPartialReport & { created: boolean; final: false }>>;
}
