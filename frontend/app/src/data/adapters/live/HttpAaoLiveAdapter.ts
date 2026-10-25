/**
 * HTTP Live Adapter for AAO Backend
 * Spec: AAO-FE-ARCH-2026-10-25 Section 6
 *
 * Implements AaoReadPort over live HTTP endpoints.
 * Handles timeouts, network errors, HTTP 401/403/404/5xx, defensive Zod parsing,
 * and memory-only token authentication.
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
  BoardStage,
  TaskItem,
} from '../../../domain/models';
import {
  ProjectsListSchema,
  PrincipalSchema,
  GrantSchema,
  CapabilitySchema,
  CapabilityEvaluationSchema,
} from '../../../domain/validators';
import { z } from 'zod';

export interface HttpLiveAdapterConfig {
  baseUrl?: string;
  timeoutMs?: number;
  getToken?: () => string | null;
  getAuthRole?: () => 'AGENT' | 'CEO';
  onUnauthorized?: () => void;
}

export class HttpAaoLiveAdapter implements AaoReadPort {
  private baseUrl: string;
  private timeoutMs: number;
  private getToken: () => string | null;
  private getAuthRole: () => 'AGENT' | 'CEO';
  private onUnauthorized?: () => void;

  constructor(config: HttpLiveAdapterConfig = {}) {
    this.baseUrl = config.baseUrl ?? '';
    this.timeoutMs = config.timeoutMs ?? 10000;
    this.getToken = config.getToken ?? (() => null);
    this.getAuthRole = config.getAuthRole ?? (() => 'AGENT');
    this.onUnauthorized = config.onUnauthorized;
  }

  private async request<T>(
    endpoint: string,
    schema?: z.ZodType<T>,
    options: RequestInit = {}
  ): Promise<DataState<T>> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    const token = this.getToken();
    if (token) {
      const role = this.getAuthRole();
      if (role === 'CEO') {
        headers['X-CEO-Token'] = token;
      } else {
        headers['X-Agent-Token'] = token;
      }
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers,
        signal: controller.signal,
      });

      if (response.status === 401) {
        if (this.onUnauthorized) {
          this.onUnauthorized();
        }
        return {
          kind: 'forbidden',
          reason: 'Credencial no autorizada o expirada (HTTP 401). Sesión reiniciada.',
        };
      }

      if (response.status === 403) {
        return {
          kind: 'forbidden',
          reason: 'Permisos insuficientes para acceder a este recurso (HTTP 403).',
        };
      }

      if (response.status === 404) {
        return {
          kind: 'unavailable',
          reason: 'Recurso no encontrado en el servidor (HTTP 404).',
          retryable: false,
        };
      }

      if (!response.ok) {
        return {
          kind: 'error',
          code: `HTTP_${response.status}`,
          message: `El servidor respondió con error ${response.status}: ${response.statusText}`,
          retryable: response.status >= 500,
        };
      }

      const rawJson: unknown = await response.json();

      if (schema) {
        const parseResult = schema.safeParse(rawJson);
        if (!parseResult.success) {
          return {
            kind: 'error',
            code: 'SCHEMA_VALIDATION_ERROR',
            message: `Respuesta del backend no cumple el contrato: ${parseResult.error.message}`,
            retryable: false,
          };
        }
        return {
          kind: 'ready',
          origin: 'live',
          data: parseResult.data,
          fetchedAt: new Date().toISOString(),
        };
      }

      return {
        kind: 'ready',
        origin: 'live',
        data: rawJson as T,
        fetchedAt: new Date().toISOString(),
      };
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return {
          kind: 'error',
          code: 'TIMEOUT',
          message: `La solicitud a ${endpoint} excedió el tiempo límite (${this.timeoutMs}ms)`,
          retryable: true,
        };
      }

      return {
        kind: 'error',
        code: 'NETWORK_ERROR',
        message: err instanceof Error ? err.message : 'Error de conexión de red',
        retryable: true,
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async getCurrentPrincipal(): Promise<DataState<PrincipalSummary>> {
    const role = this.getAuthRole();
    if (role === 'CEO') {
      return {
        kind: 'ready',
        origin: 'live',
        data: {
          principal_id: 'ceo',
          kind: 'CEO',
          enabled: true,
        },
        fetchedAt: new Date().toISOString(),
      };
    }

    const principalResult = await this.request('/v1/principals/me', PrincipalSchema);
    if (principalResult.kind !== 'ready') {
      return principalResult;
    }

    // Try to fetch grants as well if principal is active
    const grantsResult = await this.request('/v1/principals/me/grants', z.array(GrantSchema));
    const grants = grantsResult.kind === 'ready' ? grantsResult.data : [];

    return {
      kind: 'ready',
      origin: 'live',
      data: {
        principal_id: principalResult.data.principal_id,
        kind: principalResult.data.kind,
        enabled: principalResult.data.enabled,
        grants: grants.map((g: z.infer<typeof GrantSchema>) => ({
          project_id: g.project_id,
          capability: g.capability,
          expires_at: g.expires_at || null,
          active: g.active,
        })),
      },
      fetchedAt: new Date().toISOString(),
    };
  }

  async listProjects(): Promise<DataState<ProjectSummary[]>> {
    const result = await this.request('/v1/projects', ProjectsListSchema);
    if (result.kind !== 'ready') {
      return result;
    }

    if (result.data.length === 0) {
      return {
        kind: 'empty',
        origin: 'live',
        fetchedAt: new Date().toISOString(),
      };
    }

    const mapped: ProjectSummary[] = result.data.map((p: z.infer<typeof ProjectsListSchema>[number]) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      status: p.state || p.status || 'ACTIVE',
      mandateId: p.mandate_id,
    }));

    return {
      kind: 'ready',
      origin: 'live',
      data: mapped,
      fetchedAt: new Date().toISOString(),
    };
  }

  async getProjectBoard(projectId: string): Promise<DataState<ProjectBoard>> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    const headers: Record<string, string> = { Accept: 'application/json' };
    const token = this.getToken();
    if (token) {
      const role = this.getAuthRole();
      if (role === 'CEO') {
        headers['X-CEO-Token'] = token;
      } else {
        headers['X-Agent-Token'] = token;
      }
    }

    try {
      const response = await fetch(`${this.baseUrl}/v1/projects/${encodeURIComponent(projectId)}/board`, {
        headers,
        signal: controller.signal,
      });

      if (response.status === 401) {
        if (this.onUnauthorized) this.onUnauthorized();
        return {
          kind: 'forbidden',
          reason: 'Credencial no autorizada o revocada (HTTP 401).',
        };
      }
      if (response.status === 403) {
        return {
          kind: 'forbidden',
          reason: 'No tiene permiso project.read para consultar este tablero (HTTP 403).',
        };
      }
      if (response.status === 404) {
        return {
          kind: 'unavailable',
          reason: `El proyecto "${projectId}" no existe o no está registrado (HTTP 404).`,
          retryable: false,
        };
      }
      if (!response.ok) {
        return {
          kind: 'error',
          code: `HTTP_${response.status}`,
          message: `Error al obtener tablero: HTTP ${response.status}`,
          retryable: response.status >= 500,
        };
      }

      const rawJson = (await response.json()) as unknown;
      if (!Array.isArray(rawJson)) {
        return {
          kind: 'error',
          code: 'INVALID_BOARD_FORMAT',
          message: 'La respuesta de tablero no es una lista válida de tareas',
          retryable: false,
        };
      }

      const stagesMap: Record<BoardStage, TaskItem[]> = {
        INBOX: [],
        READY: [],
        IN_PROGRESS: [],
        IN_REVIEW: [],
        VERIFIED: [],
        DONE: [],
      };

      const allItems: TaskItem[] = [];

      for (const rawItem of rawJson) {
        if (typeof rawItem !== 'object' || rawItem === null) continue;
        const itemObj = rawItem as Record<string, unknown>;
        const id = String(itemObj.id || '');
        const title = String(itemObj.title || 'Sin título');
        const rawStatus = String(itemObj.status || 'INBOX').toUpperCase();
        const status: BoardStage = [
          'INBOX',
          'READY',
          'IN_PROGRESS',
          'IN_REVIEW',
          'VERIFIED',
          'DONE',
        ].includes(rawStatus)
          ? (rawStatus as BoardStage)
          : 'INBOX';

        const taskItem: TaskItem = {
          id,
          title,
          status,
          acceptanceCriteria: Array.isArray(itemObj.acceptance_criteria)
            ? (itemObj.acceptance_criteria as string[])
            : [],
          evidence: Array.isArray(itemObj.evidence) ? itemObj.evidence : [],
          executions: Array.isArray(itemObj.executions)
            ? (itemObj.executions as TaskItem['executions'])
            : [],
          reviews: Array.isArray(itemObj.reviews)
            ? (itemObj.reviews as TaskItem['reviews'])
            : [],
        };

        stagesMap[status].push(taskItem);
        allItems.push(taskItem);
      }

      return {
        kind: 'ready',
        origin: 'live',
        data: {
          projectId,
          items: allItems,
          stages: stagesMap,
          totalCount: allItems.length,
        },
        fetchedAt: new Date().toISOString(),
      };
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return {
          kind: 'error',
          code: 'TIMEOUT',
          message: 'Tiempo de espera agotado al consultar el tablero',
          retryable: true,
        };
      }
      return {
        kind: 'error',
        code: 'NETWORK_ERROR',
        message: err instanceof Error ? err.message : 'Error de red al consultar el tablero',
        retryable: true,
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async getProjectCapabilities(projectId: string): Promise<DataState<CapabilitySummary[]>> {
    const res = await this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/capabilities`,
      z.array(CapabilitySchema)
    );
    if (res.kind !== 'ready') return res;

    if (res.data.length === 0) {
      return { kind: 'empty', origin: 'live', fetchedAt: new Date().toISOString() };
    }

    return {
      kind: 'ready',
      origin: 'live',
      data: res.data.map((c: z.infer<typeof CapabilitySchema>) => ({
        capability_id: c.capability_id,
        version: c.version,
        capability_type: c.capability_type,
        status: c.status,
        provenance: c.provenance,
        contract: c.contract,
        required_permissions: c.required_permissions,
        risks: c.risks,
        dependencies: c.dependencies,
        tests: c.tests,
        compatibility: c.compatibility,
        evidence: c.evidence,
        created_by: c.created_by,
        created_at: c.created_at,
        execution_authorized: false, // Invariant: listing grants no execution authority
      })),
      fetchedAt: new Date().toISOString(),
    };
  }

  async getProjectEvaluations(projectId: string): Promise<DataState<EvaluationSummary[]>> {
    const res = await this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/capability-evaluations`,
      z.array(CapabilityEvaluationSchema)
    );
    if (res.kind !== 'ready') return res;

    if (res.data.length === 0) {
      return { kind: 'empty', origin: 'live', fetchedAt: new Date().toISOString() };
    }

    return {
      kind: 'ready',
      origin: 'live',
      data: res.data.map((e: z.infer<typeof CapabilityEvaluationSchema>) => ({
        task_id: e.task_id,
        details: e.details,
        created_at: e.created_at,
        task_title: e.task_title,
      })),
      fetchedAt: new Date().toISOString(),
    };
  }

  async getCeoOverview(projectId?: string): Promise<CeoOverview> {
    const now = new Date().toISOString();

    // 1. Projects
    const projectsState = await this.listProjects();

    // 2. Health check via /health
    let operationsState: DataState<CeoOverview['operations'] extends DataState<infer U> ? U : never>;
    try {
      const healthRes = await fetch(`${this.baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
      if (healthRes.ok) {
        operationsState = {
          kind: 'ready',
          origin: 'live',
          data: {
            serviceHealth: 'healthy',
            readyStatus: true,
            checkedAt: now,
            message: 'Servicio FastAPI conectado y respondiendo en el origen actual.',
          },
          fetchedAt: now,
        };
      } else {
        operationsState = {
          kind: 'ready',
          origin: 'live',
          data: {
            serviceHealth: 'degraded',
            readyStatus: false,
            checkedAt: now,
            message: `Endpoint de salud reportó HTTP ${healthRes.status}.`,
          },
          fetchedAt: now,
        };
      }
    } catch {
      operationsState = {
        kind: 'unavailable',
        reason: 'No se pudo contactar el endpoint /health del backend.',
        retryable: true,
      };
    }

    // 3. Work Summary: based on project board if selected, or unavailable if none
    let workState: CeoOverview['work'];
    if (projectId) {
      const boardState = await this.getProjectBoard(projectId);
      if (boardState.kind === 'ready') {
        const board = boardState.data;
        const byStage: Record<BoardStage, number> = {
          INBOX: board.stages.INBOX.length,
          READY: board.stages.READY.length,
          IN_PROGRESS: board.stages.IN_PROGRESS.length,
          IN_REVIEW: board.stages.IN_REVIEW.length,
          VERIFIED: board.stages.VERIFIED.length,
          DONE: board.stages.DONE.length,
        };
        workState = {
          kind: 'ready',
          origin: 'live',
          data: {
            totalTasks: board.totalCount,
            byStage,
            inReviewCount: byStage.IN_REVIEW,
            blockedCount: 0,
          },
          fetchedAt: now,
        };
      } else if (boardState.kind === 'empty') {
        workState = {
          kind: 'empty',
          origin: 'live',
          fetchedAt: now,
        };
      } else {
        workState = {
          kind: boardState.kind,
          reason: 'reason' in boardState ? boardState.reason : 'No disponible',
          retryable: 'retryable' in boardState ? boardState.retryable : false,
        } as CeoOverview['work'];
      }
    } else {
      workState = {
        kind: 'unavailable',
        reason: 'Seleccione un proyecto específico para calcular la distribución real de tareas del tablero.',
        retryable: false,
      };
    }

    // 4. Governance: No certified independent governance contract endpoint exists yet in this phase
    const governanceState: CeoOverview['governance'] = {
      kind: 'unavailable',
      reason: 'Sin contrato API certificado de auditoría y gobernanza independiente en esta fase (F1-F2).',
      retryable: false,
    };

    // 5. Alerts: No alerts endpoint exists in backend
    const alertsState: CeoOverview['alerts'] = {
      kind: 'unavailable',
      reason: 'Sin contrato de alertas en tiempo real expuesto en la API.',
      retryable: false,
    };

    // 6. Decisions: Consultative only, no direct decision API exists
    const decisionsState: CeoOverview['decisions'] = {
      kind: 'unavailable',
      reason: 'El centro de decisiones opera en modo consultivo; no existe endpoint de mutación o votación en esta fase.',
      retryable: false,
    };

    return {
      projects: projectsState,
      work: workState,
      governance: governanceState,
      operations: operationsState,
      alerts: alertsState,
      decisions: decisionsState,
    };
  }
}
