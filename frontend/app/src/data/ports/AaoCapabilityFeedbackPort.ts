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
  reviewed_by: string | null;
  reviewed_at: string | null;
  applied: boolean;
  applied_capability_version: string | null;
  applied_by: string | null;
  applied_at: string | null;
}

export interface CapabilityFeedbackInput {
  capability_id: string;
  version: string;
  correction: string;
  work_id?: string | null;
  evidence: string[];
}

export interface CapabilityFeedbackVersionInput {
  version: string;
  provenance: Record<string, unknown>;
  contract: Record<string, unknown>;
  required_permissions: string[];
  risks: string[];
  dependencies: string[];
  tests: string[];
  compatibility: Record<string, unknown>;
  evidence: string[];
}

export interface AaoCapabilityFeedbackPort {
  listCapabilityFeedback(projectId: string): Promise<DataState<CapabilityFeedbackProposal[]>>;
  proposeCapabilityFeedback(projectId: string, input: CapabilityFeedbackInput): Promise<DataState<Pick<CapabilityFeedbackProposal, 'id' | 'capability_id' | 'version' | 'work_id' | 'status' | 'applied'>>>;
  reviewCapabilityFeedback(projectId: string, proposalId: string, status: 'accepted' | 'rejected'): Promise<DataState<Pick<CapabilityFeedbackProposal, 'id' | 'status' | 'reviewed_by' | 'reviewed_at' | 'applied'>>>;
  registerFeedbackCapabilityVersion(projectId: string, proposalId: string, input: CapabilityFeedbackVersionInput): Promise<DataState<{
    id: string; capability_id: string; source_version: string; version: string; status: 'registered_local';
    applied: true; execution_authorized: false;
  }>>;
}
