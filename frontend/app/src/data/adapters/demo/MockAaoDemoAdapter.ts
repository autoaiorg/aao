/**
 * Mock Demo Adapter
 * Returns synthetic fixtures for demonstration mode.
 * Strictly decoupled from real live data and backend credentials.
 */

import type { AaoReadPort } from '../../ports/AaoReadPort';
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
} from '../../../domain/models';
import {
  DEMO_PROJECTS,
  DEMO_PRINCIPAL,
  DEMO_BOARD_ORION,
  DEMO_CAPABILITIES_ORION,
  DEMO_EVALUATIONS_ORION,
  DEMO_CEO_OVERVIEW,
  DEMO_ORG_STRUCTURE,
  DEMO_AGENTS,
} from './fixtures';

export class MockAaoDemoAdapter implements AaoReadPort {
  private artificialDelayMs: number;

  constructor(artificialDelayMs = 50) {
    this.artificialDelayMs = artificialDelayMs;
  }

  private async delay(): Promise<void> {
    if (this.artificialDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.artificialDelayMs));
    }
  }

  async getCurrentPrincipal(): Promise<DataState<PrincipalSummary>> {
    await this.delay();
    return {
      kind: 'ready',
      origin: 'demo',
      data: DEMO_PRINCIPAL,
      fetchedAt: new Date().toISOString(),
    };
  }

  async listProjects(): Promise<DataState<ProjectSummary[]>> {
    await this.delay();
    return {
      kind: 'ready',
      origin: 'demo',
      data: DEMO_PROJECTS,
      fetchedAt: new Date().toISOString(),
    };
  }

  async getProjectBoard(projectId: string): Promise<DataState<ProjectBoard>> {
    await this.delay();
    if (projectId === 'demo-proj-orion') {
      return {
        kind: 'ready',
        origin: 'demo',
        data: DEMO_BOARD_ORION,
        fetchedAt: new Date().toISOString(),
      };
    }

    // Generic fallback board for other demo projects
    const proj = DEMO_PROJECTS.find((p) => p.id === projectId);
    const board: ProjectBoard = {
      projectId,
      projectName: proj?.name || `Proyecto Demo (${projectId})`,
      totalCount: 0,
      unrecognizedItems: [],
      stages: {
        INBOX: [],
        READY: [],
        IN_PROGRESS: [],
        IN_REVIEW: [],
        VERIFIED: [],
        DONE: [],
      },
      items: [],
    };

    return {
      kind: 'ready',
      origin: 'demo',
      data: board,
      fetchedAt: new Date().toISOString(),
    };
  }

  async getProjectCapabilities(projectId: string): Promise<DataState<CapabilitySummary[]>> {
    await this.delay();
    if (projectId === 'demo-proj-orion') {
      return {
        kind: 'ready',
        origin: 'demo',
        data: DEMO_CAPABILITIES_ORION,
        fetchedAt: new Date().toISOString(),
      };
    }
    return {
      kind: 'empty',
      origin: 'demo',
      fetchedAt: new Date().toISOString(),
    };
  }

  async getProjectEvaluations(projectId: string): Promise<DataState<EvaluationSummary[]>> {
    await this.delay();
    if (projectId === 'demo-proj-orion') {
      return {
        kind: 'ready',
        origin: 'demo',
        data: DEMO_EVALUATIONS_ORION,
        fetchedAt: new Date().toISOString(),
      };
    }
    return {
      kind: 'empty',
      origin: 'demo',
      fetchedAt: new Date().toISOString(),
    };
  }

  async getCeoOverview(_projectId?: string): Promise<CeoOverview> {
    await this.delay();
    return DEMO_CEO_OVERVIEW;
  }

  // Phase F3: Organization and Agent Structure
  async getOrganizationStructure(): Promise<DataState<OrganizationStructure>> {
    await this.delay();
    return {
      kind: 'ready',
      origin: 'demo',
      data: DEMO_ORG_STRUCTURE,
      fetchedAt: new Date().toISOString(),
    };
  }

  async getAgentDetails(agentId: string): Promise<DataState<AgentIdentity>> {
    await this.delay();
    const agent = DEMO_AGENTS.find((a) => a.id === agentId);
    if (!agent) {
      return {
        kind: 'error',
        code: 'AGENT_NOT_FOUND',
        message: `El agente con identificador ${agentId} no existe en la estructura organizativa simulada.`,
        retryable: false,
      };
    }
    return {
      kind: 'ready',
      origin: 'demo',
      data: agent,
      fetchedAt: new Date().toISOString(),
    };
  }
}
