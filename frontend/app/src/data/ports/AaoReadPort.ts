/**
 * AAO Read Port Interface
 * Decouples frontend domain and UI from live HTTP vs demo synthetic fixtures.
 */

import type {
  PrincipalSummary,
  ProjectSummary,
  ProjectBoard,
  CapabilitySummary,
  EvaluationSummary,
  CeoOverview,
  OrganizationStructure,
  AgentIdentity,
  DataState,
  ActivityEvent,
} from '../../domain/models';

export interface AaoReadPort {
  getCurrentPrincipal(): Promise<DataState<PrincipalSummary>>;
  listProjects(): Promise<DataState<ProjectSummary[]>>;
  getProjectBoard(projectId: string): Promise<DataState<ProjectBoard>>;
  getProjectCapabilities(projectId: string): Promise<DataState<CapabilitySummary[]>>;
  getProjectEvaluations(projectId: string): Promise<DataState<EvaluationSummary[]>>;
  getProjectActivity(projectId: string): Promise<DataState<ActivityEvent[]>>;
  getCeoOverview(projectId?: string): Promise<CeoOverview>;
  // Phase F3: Organization & Agent Structure
  getOrganizationStructure(): Promise<DataState<OrganizationStructure>>;
  getAgentDetails(agentId: string): Promise<DataState<AgentIdentity>>;
}
