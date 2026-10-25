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
  created_at: string;
}

export interface ConversationWorkRequestInput {
  title: string;
  description: string;
  acceptance_criteria: string[];
}

export interface ConversationWorkRequestResult {
  id: string;
  status: string;
  created: boolean;
}

export interface ConversationWorkGroupInput extends ConversationWorkRequestInput {
  idempotency_key: string;
  tasks: Array<{
    key: string;
    title: string;
    description: string;
    acceptance_criteria: string[];
    depends_on: string[];
  }>;
}

export interface ConversationWorkGroupResult {
  id: string;
  project_id: string;
  conversation_id: string;
  parent_work_id: string;
  status: string;
  created: boolean;
  tasks: Array<{ id: string; title: string; status: string; depends_on: string[] }>;
}

export interface ConversationWorkGroupProposal {
  proposal: Omit<ConversationWorkGroupInput, 'idempotency_key'>;
  based_on_message_ids: string[];
  provider: string;
  model: string;
  persisted_as_work: false;
}

export interface AaoConversationPort {
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
}
