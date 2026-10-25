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
  DataState,
} from '../../../domain/models';
import {
  DEMO_PROJECTS,
  DEMO_PRINCIPAL,
  DEMO_BOARD_ORION,
  DEMO_CAPABILITIES_ORION,
  DEMO_EVALUATIONS_ORION,
  DEMO_CEO_OVERVIEW,
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
}
