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
  created_at: string;
}

export interface ConversationWorkRequestInput {
  title: string;
  acceptance_criteria: string[];
}

export interface ConversationWorkRequestResult {
  id: string;
  status: string;
  created: boolean;
}

export interface AaoConversationPort {
  listProjectConversations(projectId: string): Promise<DataState<ProjectConversation[]>>;
  listConversationMessages(projectId: string, conversationId: string): Promise<DataState<ProjectConversationMessage[]>>;
  createProjectConversation(projectId: string, title: string): Promise<DataState<Pick<ProjectConversation, 'id' | 'project_id' | 'title'>>>;
  appendCEOConversationMessage(projectId: string, conversationId: string, body: string): Promise<DataState<ProjectConversationMessage>>;
  createWorkRequestFromMessage(
    projectId: string,
    conversationId: string,
    messageId: string,
    input: ConversationWorkRequestInput,
  ): Promise<DataState<ConversationWorkRequestResult>>;
}
