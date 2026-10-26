import type { DataState } from '../../domain/models';

export interface CapabilityFeedbackProposal {
  id: string;
  capability_id: string;
  version: string;
  work_id: string | null;
  correction: string;
  evidence: string[];
  status: 'proposed' | 'accepted' | 'rejected';
  created_by: string;
  created_at: string;
  applied: false;
}

export interface CapabilityFeedbackInput {
  capability_id: string;
  version: string;
  correction: string;
  work_id?: string | null;
  evidence: string[];
}

export interface AaoCapabilityFeedbackPort {
  listCapabilityFeedback(projectId: string): Promise<DataState<CapabilityFeedbackProposal[]>>;
  proposeCapabilityFeedback(projectId: string, input: CapabilityFeedbackInput): Promise<DataState<Pick<CapabilityFeedbackProposal, 'id' | 'capability_id' | 'version' | 'work_id' | 'status' | 'applied'>>>;
}
