import type { DataState } from '../../domain/models';

export interface CEOWorkRequest {
  title: string;
  description: string;
  acceptance_criteria: string[];
  due_date?: string | null;
}

export interface CreatedWorkRequest {
  id: string;
  status: 'INBOX';
}

/** CEO direction is persisted as an unadmitted canonical work item. */
export interface AaoWorkCommandPort {
  createCEOWorkRequest(projectId: string, input: CEOWorkRequest): Promise<DataState<CreatedWorkRequest>>;
}
