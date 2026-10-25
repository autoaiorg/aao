/**
 * HTTP Live Adapter for AAO Backend
 * Spec: AAO-FE-ARCH-2026-10-25 Section 6
 *
 * Implements AaoReadPort over live HTTP endpoints.
 * Handles timeouts, network errors, HTTP 401/403/404/5xx, defensive Zod parsing,
 * pending query abortion, and memory-only token authentication.
 *
 * Findings addressed:
 * - P0 (Finding 1): Real CEO credential verification against /v1/mandates (NO synthetic fabrication).
 * - P0 (Finding 2): In-flight query abortion via abortAll() and session-scoped request tracking.
 * - P1 (Finding 3): Elimination of silent conversion to INBOX; preserves exact raw status and routes unrecognized items to unrecognizedItems.
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
  AgentType,
  AgentOperationalStatus,
  AgentOperationalState,
  OrgUnit,
  DataState,
  BoardStage,
  TaskItem,
  TaskExecutionRecord,
  ActivityEvent,
} from '../../../domain/models';
import {
  ActivityEventSchema,
  ProjectsListSchema,
  PrincipalSchema,
  GrantSchema,
  CapabilitySchema,
  CapabilityEvaluationSchema,
  OrganizationStructureSchema,
  AgentIdentitySchema,
} from '../../../domain/validators';
import { z } from 'zod';

export interface HttpLiveAdapterConfig {
  baseUrl?: string;
  timeoutMs?: number;
  getToken?: () => string | null;
  getAuthRole?: () => 'AGENT' | 'CEO';
  onUnauthorized?: () => void;
  requireAuth?: boolean;
}

export class HttpAaoLiveAdapter implements AaoReadPort {
  private baseUrl: string;
  private timeoutMs: number;
  private getToken: () => string | null;
  private getAuthRole: () => 'AGENT' | 'CEO';
  private onUnauthorized?: () => void;
  private requireAuth: boolean;
  private activeControllers: Set<AbortController> = new Set();

  constructor(config: HttpLiveAdapterConfig = {}) {
    this.baseUrl = config.baseUrl ?? '';
    this.timeoutMs = config.timeoutMs ?? 10000;
    this.getToken = config.getToken ?? (() => null);
    this.getAuthRole = config.getAuthRole ?? (() => 'AGENT');
    this.onUnauthorized = config.onUnauthorized;
    this.requireAuth = config.requireAuth ?? false;
  }

  /**
   * P0 Finding 2: Aborts all in-flight HTTP requests immediately.
   * Invoked upon logout, credential change, or session switch.
   */
  public abortAll(): void {
    for (const controller of this.activeControllers) {
      try {
        controller.abort();
      } catch {
        // Ignored
      }
    }
    this.activeControllers.clear();
  }

  private async request<T>(
    endpoint: string,
    schema?: z.ZodType<T>,
    options: RequestInit = {}
  ): Promise<DataState<T>> {
    const controller = new AbortController();
    this.activeControllers.add(controller);

    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    const token = this.getToken();
    if (this.requireAuth && !token) {
      clearTimeout(timeoutId);
      this.activeControllers.delete(controller);
      return {
        kind: 'forbidden',
        reason: 'Credencial no suministrada en memoria. Se requiere autenticación antes de consultar el backend.',
      };
    }

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
          message: `La solicitud a ${endpoint} fue cancelada o excedió el tiempo límite (${this.timeoutMs}ms)`,
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
      this.activeControllers.delete(controller);
    }
  }

  /**
   * P0 Finding 1 Fix: Differentiates declared role, verified authentication, and effective authority.
   * For CEO role: tests X-CEO-Token against /v1/mandates to prove real authentication.
   * For AGENT role: tests X-Agent-Token against /v1/principals/me and /v1/principals/me/grants.
   * NO synthetic fabrication of CEO identity without backend verification!
   */
  async getCurrentPrincipal(): Promise<DataState<PrincipalSummary>> {
    const role = this.getAuthRole();
    const token = this.getToken();

    if (!token) {
      return {
        kind: 'forbidden',
        reason: 'Credencial no suministrada en memoria. Se requiere autenticación.',
      };
    }

    if (role === 'CEO') {
      const controller = new AbortController();
      this.activeControllers.add(controller);
      const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        // Attempt verification on CEO-only mandate endpoint to check if token is accepted
        const response = await fetch(`${this.baseUrl}/v1/mandates`, {
          headers: {
            'X-CEO-Token': token,
            Accept: 'application/json',
          },
          signal: controller.signal,
        });

        if (response.status === 401 || response.status === 403) {
          return {
            kind: 'forbidden',
            reason: 'Credencial de desarrollo CEO rechazada por el backend (HTTP 403). Autenticación no comprobada.',
          };
        }

        if (response.status === 503) {
          return {
            kind: 'unavailable',
            reason: 'Bearer de desarrollo CEO no disponible o no configurado en este entorno (HTTP 503).',
            retryable: false,
          };
        }

        if (!response.ok) {
          return {
            kind: 'error',
            code: `HTTP_${response.status}`,
            message: `Error al verificar credencial CEO: HTTP ${response.status}`,
            retryable: response.status >= 500,
          };
        }

        // Successfully verified against /v1/mandates
        return {
          kind: 'ready',
          origin: 'live',
          data: {
            principal_id: 'ceo (bearer de desarrollo verificado)',
            kind: 'CEO',
            enabled: true,
            verificationStatus: 'verified',
            authMethod: 'X-CEO-Token comprobado vía GET /v1/mandates',
          },
          fetchedAt: new Date().toISOString(),
        };
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return {
            kind: 'error',
            code: 'TIMEOUT',
            message: 'Tiempo de espera agotado al verificar credencial CEO',
            retryable: true,
          };
        }
        return {
          kind: 'error',
          code: 'NETWORK_ERROR',
          message: err instanceof Error ? err.message : 'Error de red al verificar credencial CEO',
          retryable: true,
        };
      } finally {
        clearTimeout(timeoutId);
        this.activeControllers.delete(controller);
      }
    }

    // AGENT role verification
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
        verificationStatus: 'verified',
        authMethod: 'X-Agent-Token verificado vía GET /v1/principals/me',
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

  /**
   * P1 Finding 3 Fix: Preserves exact semantic status of every received task.
   * Tasks with status outside canonical 6 stages are segregated into unrecognizedItems,
   * completely preventing silent conversion to INBOX!
   */
  async getProjectBoard(projectId: string): Promise<DataState<ProjectBoard>> {
    const controller = new AbortController();
    this.activeControllers.add(controller);
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    const headers: Record<string, string> = { Accept: 'application/json' };
    const token = this.getToken();
    if (this.requireAuth && !token) {
      clearTimeout(timeoutId);
      this.activeControllers.delete(controller);
      return {
        kind: 'forbidden',
        reason: 'Credencial no suministrada en memoria. Se requiere autenticación antes de consultar el backend.',
      };
    }

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

      const unrecognizedItems: TaskItem[] = [];
      const allItems: TaskItem[] = [];

      const canonicalStages: readonly string[] = [
        'INBOX',
        'READY',
        'IN_PROGRESS',
        'IN_REVIEW',
        'VERIFIED',
        'DONE',
      ];

      for (const rawItem of rawJson) {
        if (typeof rawItem !== 'object' || rawItem === null) continue;
        const itemObj = rawItem as Record<string, unknown>;
        const id = String(itemObj.id || '');
        const title = String(itemObj.title || 'Sin título');
        const rawStatus = String(itemObj.status || '');
        const normalizedUpper = rawStatus.toUpperCase();

        const isCanonical = canonicalStages.includes(normalizedUpper);
        const canonicalStage = isCanonical ? (normalizedUpper as BoardStage) : null;

        const taskItem: TaskItem = {
          id,
          title,
          status: rawStatus, // PRESERVES RAW SEMANTIC STATUS WITHOUT MUTATION
          rawStatus,
          isUnrecognizedStatus: !isCanonical,
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
          pullRequests: Array.isArray(itemObj.pull_requests)
            ? (itemObj.pull_requests as TaskItem['pullRequests'])
            : [],
          resolution:
            typeof itemObj.resolution === 'object' && itemObj.resolution !== null
              ? (itemObj.resolution as TaskItem['resolution'])
              : null,
        };

        if (canonicalStage) {
          stagesMap[canonicalStage].push(taskItem);
        } else {
          // P1 Finding 3: Do NOT push to INBOX! Retain in unrecognizedItems
          unrecognizedItems.push(taskItem);
        }

        allItems.push(taskItem);
      }

      return {
        kind: 'ready',
        origin: 'live',
        data: {
          projectId,
          items: allItems,
          stages: stagesMap,
          unrecognizedItems,
          totalCount: allItems.length,
        },
        fetchedAt: new Date().toISOString(),
      };
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return {
          kind: 'error',
          code: 'TIMEOUT',
          message: 'Tiempo de espera agotado o consulta cancelada al consultar el tablero',
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
      this.activeControllers.delete(controller);
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

  async getProjectActivity(projectId: string): Promise<DataState<ActivityEvent[]>> {
    const res = await this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/activity?limit=200`,
      z.array(ActivityEventSchema)
    );
    if (res.kind !== 'ready') return res;
    if (res.data.length === 0) {
      return { kind: 'empty', origin: 'live', fetchedAt: new Date().toISOString() };
    }
    return { kind: 'ready', origin: 'live', data: res.data, fetchedAt: new Date().toISOString() };
  }

  async getCeoOverview(projectId?: string): Promise<CeoOverview> {
    const now = new Date().toISOString();

    if (this.requireAuth && !this.getToken()) {
      return {
        projects: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
        work: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
        governance: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
        operations: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
        alerts: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
        decisions: { kind: 'forbidden', reason: 'Credencial no suministrada en memoria. Se requiere autenticación.' },
      };
    }

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
            unrecognizedCount: board.unrecognizedItems.length,
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

  // Phase F3 & F4.8: Organization and Agent Structure
  async getOrganizationStructure(): Promise<DataState<OrganizationStructure>> {
    const token = this.getToken();
    if (!token && this.requireAuth) {
      return {
        kind: 'unavailable',
        reason:
          'El núcleo canónico de AAO no expone aún endpoints canónicos para la estructura organizativa ni la telemetría de agentes (F3). Este módulo permanece en modo consulta y se conectará en cuanto la API incorpore /v1/organization.',
        retryable: false,
      };
    }

    // 1. Attempt canonical /v1/organization endpoint if exposed by backend
    try {
      const directResult = await this.request('/v1/organization', OrganizationStructureSchema);
      if (directResult.kind === 'ready') {
        return directResult;
      }
      if (directResult.kind === 'forbidden') {
        return directResult;
      }
    } catch {
      // Backend does not expose /v1/organization; proceed to progressive live aggregation
    }

    // 2. Progressive Layering: Aggregate real live agents and executions from projects & board
    const projectsResult = await this.listProjects();
    if (projectsResult.kind === 'forbidden') {
      return projectsResult;
    }
    if (projectsResult.kind === 'unavailable') {
      return {
        kind: 'unavailable',
        reason:
          'El núcleo canónico de AAO no expone aún endpoints canónicos para la estructura organizativa ni la telemetría de agentes (F3). Este módulo permanece en modo consulta y se conectará en cuanto la API incorpore /v1/organization.',
        retryable: false,
      };
    }
    if (projectsResult.kind === 'error') {
      if (projectsResult.code.startsWith('HTTP_401')) {
        return {
          kind: 'forbidden',
          reason: 'No autorizado para consultar la estructura organizativa en vivo (HTTP 401).',
        };
      }
      return projectsResult;
    }

    // Constitutional Units Definition (without synthetic department leads)
    const units: OrgUnit[] = [
      {
        id: 'unit-exec',
        name: 'Dirección Ejecutiva y Secretaría General',
        code: 'EXEC',
        parentId: null,
        leadRole: 'CEO / Presidencia Ejecutiva',
        leadAgentId: null,
        description: 'Coordinación estratégica, reservas de decisión constitucionales y supervisión global de los mandatos.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-gov',
        name: 'Gobernanza Constitucional y Políticas',
        code: 'GOV',
        parentId: 'unit-exec',
        leadRole: 'Director de Cumplimiento Normativo',
        leadAgentId: null,
        description: 'Garantía de cumplimiento de mandatos, separación de poderes y validación de políticas de delegación.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-audit',
        name: 'Auditoría Independiente y Verificación',
        code: 'AUDIT',
        parentId: 'unit-exec',
        leadRole: 'Auditor Principal de Seguridad',
        leadAgentId: null,
        description: 'Verificación adversarial independiente de parches, atestación criptográfica y control de promociones.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-arch',
        name: 'Arquitectura de Sistemas y Protocolos',
        code: 'ARCH',
        parentId: 'unit-exec',
        leadRole: 'Arquitecto Jefe de Sistemas',
        leadAgentId: null,
        description: 'Diseño de especificaciones, protocolos de consenso, contratos tipados y topología de servicios.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-eng',
        name: 'Ingeniería de Software e Implementación',
        code: 'ENG',
        parentId: 'unit-arch',
        leadRole: 'Director de Implementación Técnica',
        leadAgentId: null,
        description: 'Desarrollo de módulos del núcleo, interfaces de usuario, librerías de cliente y pipelines de entrega.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-ops',
        name: 'Operaciones de Infraestructura y Resiliencia',
        code: 'OPS',
        parentId: 'unit-exec',
        leadRole: 'Responsable de Operaciones y Nodos',
        leadAgentId: null,
        description: 'Monitorización de servicios, balanceo de carga, telemetría de agentes y planes de contingencia.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
      {
        id: 'unit-unassigned',
        name: 'Departamento no asignado / Desconocido',
        code: 'DESC',
        parentId: null,
        leadRole: 'Sin asignar',
        leadAgentId: null,
        description: 'Agentes o trabajadores sin adscripción departamental canónica confirmada en el núcleo.',
        standingCount: 0,
        ephemeralCount: 0,
        activeProjectsCount: 0,
      },
    ];

    const agentMap = new Map<string, AgentIdentity>();

    // 3. Register current verified principal if available (CANONICAL ASSIGNMENT)
    try {
      const principalResult = await this.getCurrentPrincipal();
      if (principalResult.kind === 'ready') {
        const p = principalResult.data;
        // CEO Point 3: No deduzcas adscripción departamental ni tipo STANDING únicamente del rol CEO/AUDITOR.
        // Conserva el rol autenticado, pero marca los demás atributos como desconocidos sin datos organizativos canónicos.
        const unitId = 'unit-unassigned';
        const unitName = 'Departamento desconocido';
        const agentType: AgentType = 'UNKNOWN';
        const roleTitle =
          p.kind === 'CEO'
            ? 'CEO (Rol autenticado)'
            : p.kind === 'AUDITOR'
            ? 'Auditor (Rol autenticado)'
            : 'Principal Registrado';
        const agentName =
          p.kind === 'CEO'
            ? 'CEO (Identidad Autenticada)'
            : p.kind === 'AUDITOR'
            ? `Auditor (${p.principal_id})`
            : p.principal_id;

        // CEO Point 2: No traduzcas automáticamente concesiones grants en capacidades CERTIFIED.
        // Diferencia permisos, capacidades declaradas y certificaciones.
        const grants = (p.grants || []).map((g) => ({
          projectId: g.project_id,
          permission: g.capability,
          active: g.active,
          expiresAt: g.expires_at || null,
        }));

        agentMap.set(p.principal_id, {
          id: p.principal_id,
          name: agentName,
          type: agentType,
          roleTitle,
          unitId,
          unitName,
          capabilities: [], // Grants are project permissions, NOT technical certifications!
          grants,
          heartbeatStatus: 'UNKNOWN',
          lastHeartbeatAt: null,
          status: 'UNKNOWN',
          operationalState: 'REGISTRADO',
          currentAssignments: [],
          authorityBoundary:
            p.kind === 'CEO'
              ? 'Rol autenticado de CEO en el núcleo. Delimitación organizativa y adscripción departamental pendientes de datos canónicos.'
              : 'Rol autenticado de Auditor en el núcleo. Delimitación organizativa y adscripción departamental pendientes de datos canónicos.',
          isSyntheticDemo: false,
          evidenceDescription: 'Credencial activa verificada mediante endpoint /v1/principals/me.',
          lastEvidenceAt: null, // No fabricar marcas temporales sintéticas
        });
      }
    } catch {
      // Ignore principal fetch failures if optional
    }

    // 4. Inspect ALL projects and boards to extract active workers and real executions
    let inspectedProjectsCount = 0;
    let failedProjectsCount = 0;
    const totalProjectsCount = projectsResult.kind === 'ready' ? projectsResult.data.length : 0;
    const nowMs = Date.now();

    if (projectsResult.kind === 'ready') {
      for (const project of projectsResult.data) {
        try {
          const boardResult = await this.getProjectBoard(project.id);
          if (boardResult.kind === 'ready') {
            inspectedProjectsCount++;
            for (const task of boardResult.data.items) {
              if (task.executions && task.executions.length > 0) {
                for (const exec of task.executions) {
                  if (!exec.worker_id) continue;
                  const workerId = exec.worker_id;

                  // CEO Requirement 1 & 3:
                  // No deducir departamentos de worker_id. Utilizar «Departamento desconocido».
                  // No deducir STANDING o EPHEMERAL de cadenas. Representar como 'UNKNOWN'.
                  const targetUnitId = 'unit-unassigned';
                  const targetUnitName = 'Departamento desconocido';
                  const targetAgentType: AgentType = 'UNKNOWN';

                  // CEO Requirement 1 (PR #122 Review):
                  // No utilices execution.created_at y una ventana fija de cinco minutos como prueba suficiente de ejecución activa.
                  // Requiere estado RUNNING y lease vigente acreditados por el backend (lease_expires_at > now).
                  // En ausencia de esa evidencia, representa vigencia desconocida (UNKNOWN).
                  const execRecord = exec as TaskExecutionRecord;
                  const hasLeaseAttr =
                    execRecord.lease_expires_at !== undefined && execRecord.lease_expires_at !== null;
                  const leaseExpiresMs = hasLeaseAttr ? new Date(execRecord.lease_expires_at!).getTime() : NaN;
                  const isLeaseActive = !isNaN(leaseExpiresMs) && leaseExpiresMs > nowMs;
                  const isLeaseExpired = !isNaN(leaseExpiresMs) && leaseExpiresMs <= nowMs;

                  let assignmentStatus: 'ACTIVE' | 'EXPIRED' | 'COMPLETED' | 'UNKNOWN';
                  let vigencyState: 'ACTIVE' | 'EXPIRED' | 'UNKNOWN' | 'COMPLETED';

                  if (exec.status === 'RUNNING' && Boolean(exec.id)) {
                    if (isLeaseActive) {
                      assignmentStatus = 'ACTIVE';
                      vigencyState = 'ACTIVE';
                    } else if (isLeaseExpired) {
                      assignmentStatus = 'EXPIRED';
                      vigencyState = 'EXPIRED';
                    } else {
                      // Backend does not accredit a valid lease: vigency is strictly UNKNOWN
                      assignmentStatus = 'UNKNOWN';
                      vigencyState = 'UNKNOWN';
                    }
                  } else {
                    assignmentStatus = 'COMPLETED';
                    vigencyState = 'COMPLETED';
                  }

                  let agent = agentMap.get(workerId);
                  if (!agent) {
                    const agentStatus: AgentOperationalStatus =
                      vigencyState === 'ACTIVE' ? 'BUSY' : vigencyState === 'UNKNOWN' ? 'UNKNOWN' : 'IDLE';
                    const opState: AgentOperationalState =
                      vigencyState === 'ACTIVE'
                        ? 'EJECUTANDO'
                        : vigencyState === 'UNKNOWN'
                        ? 'DESCONOCIDO'
                        : 'REGISTRADO';

                    agent = {
                      id: workerId,
                      name: workerId,
                      type: targetAgentType,
                      roleTitle: 'Agente Operativo Registrado',
                      unitId: targetUnitId,
                      unitName: targetUnitName,
                      capabilities: [],
                      heartbeatStatus: 'UNKNOWN',
                      lastHeartbeatAt: null,
                      status: agentStatus,
                      operationalState: opState,
                      currentAssignments: [],
                      authorityBoundary: `Delimitado por el mandato del proyecto ${project.name || project.id}.`,
                      isSyntheticDemo: false,
                      evidenceDescription:
                        vigencyState === 'ACTIVE'
                          ? `Ejecución activa con lease vigente hasta ${execRecord.lease_expires_at} en tarea ${task.id} (${task.title}).`
                          : vigencyState === 'UNKNOWN'
                          ? `Registro de ejecución en tarea ${task.id} (${task.title}) con estado ${exec.status}. Vigencia desconocida: backend no acredita lease vigente.`
                          : `Registro histórico de ejecución en tarea ${task.id} (${task.title}). Estado: ${exec.status}.`,
                      lastEvidenceAt: exec.created_at || null, // lastEvidenceAt preserva marca del núcleo, nunca new Date()
                    };
                    agentMap.set(workerId, agent);
                  } else {
                    if (vigencyState === 'ACTIVE') {
                      agent.status = 'BUSY';
                      agent.operationalState = 'EJECUTANDO';
                    } else if (vigencyState === 'UNKNOWN' && agent.operationalState !== 'EJECUTANDO') {
                      agent.status = 'UNKNOWN';
                      agent.operationalState = 'DESCONOCIDO';
                    }
                    if (exec.created_at && (!agent.lastEvidenceAt || exec.created_at > agent.lastEvidenceAt)) {
                      agent.lastEvidenceAt = exec.created_at;
                    }
                  }

                  if (!agent.currentAssignments.some((a) => a.taskId === task.id)) {
                    agent.currentAssignments.push({
                      id: `asg-${task.id}-${workerId}`,
                      projectId: project.id,
                      projectName: project.name || project.id,
                      taskId: task.id,
                      taskTitle: task.title,
                      assignedAt: exec.created_at || task.createdAt || '',
                      leaseExpiresAt: execRecord.lease_expires_at || null,
                      status: assignmentStatus,
                    });
                  }
                }
              }

              // CEO Requirement 5:
              // No marcar capacidades como certificadas por haber encontrado una revisión.
              if (task.reviews && task.reviews.length > 0) {
                for (const rev of task.reviews) {
                  if (!rev.reviewer_id) continue;
                  const revId = rev.reviewer_id;
                  let revAgent = agentMap.get(revId);
                  if (!revAgent) {
                    revAgent = {
                      id: revId,
                      name: revId,
                      type: 'UNKNOWN',
                      roleTitle: 'Revisor de Tarea Registrado',
                      unitId: 'unit-unassigned',
                      unitName: 'Departamento desconocido',
                      capabilities: [], // NO capacidades certificadas sintéticas
                      heartbeatStatus: 'UNKNOWN',
                      lastHeartbeatAt: null,
                      status: 'IDLE',
                      operationalState: 'REGISTRADO',
                      currentAssignments: [],
                      authorityBoundary: 'Revisión técnica de candidatos en el tablero de trabajo.',
                      isSyntheticDemo: false,
                      evidenceDescription: `Revisión registrada en tarea ${task.id} (${rev.decision}). No constituye certificación formal de capacidades.`,
                      lastEvidenceAt: rev.created_at || null,
                    };
                    agentMap.set(revId, revAgent);
                  }
                }
              }
            }
          } else {
            failedProjectsCount++;
          }
        } catch {
          failedProjectsCount++;
        }
      }
    }

    const agents = Array.from(agentMap.values());

    // Update unit counts
    for (const unit of units) {
      const unitAgents = agents.filter((a) => a.unitId === unit.id);
      unit.standingCount = unitAgents.filter((a) => a.type === 'STANDING').length;
      unit.ephemeralCount = unitAgents.filter((a) => a.type === 'EPHEMERAL').length;
      const projectIds = new Set<string>();
      unitAgents.forEach((a) => a.currentAssignments.forEach((asg) => projectIds.add(asg.projectId)));
      unit.activeProjectsCount = projectIds.size;
      // CEO Requirement 4: Mantén leadAgentId: null hasta obtener evidencia
    }

    return {
      kind: 'ready',
      origin: 'live',
      data: {
        units,
        agents,
        totalStandingAgents: agents.filter((a) => a.type === 'STANDING').length,
        totalEphemeralAgents: agents.filter((a) => a.type === 'EPHEMERAL').length,
        totalUnknownAgents: agents.filter((a) => a.type === 'UNKNOWN').length,
        activeAssignmentsCount: agents.reduce(
          (acc, a) => acc + a.currentAssignments.filter((asg) => asg.status === 'ACTIVE').length,
          0
        ),
        coverage: {
          totalProjects: totalProjectsCount,
          inspectedProjects: inspectedProjectsCount,
          failedProjects: failedProjectsCount,
          isPartial: failedProjectsCount > 0,
          notes:
            failedProjectsCount > 0
              ? `Cobertura parcial: ${failedProjectsCount} de ${totalProjectsCount} proyectos no pudieron ser consultados.`
              : `Cobertura completa: ${inspectedProjectsCount} de ${totalProjectsCount} proyectos consultados en vivo.`,
        },
      },
      fetchedAt: new Date().toISOString(),
    };
  }

  async getAgentDetails(agentId: string): Promise<DataState<AgentIdentity>> {
    // 1. Attempt canonical direct endpoint
    try {
      const directResult = await this.request(
        `/v1/agents/${encodeURIComponent(agentId)}`,
        AgentIdentitySchema
      );
      if (directResult.kind === 'ready') {
        return directResult;
      }
      if (directResult.kind === 'forbidden') {
        return directResult;
      }
    } catch {
      // Backend does not expose direct agent endpoint; fallback to aggregated roster
    }

    const orgResult = await this.getOrganizationStructure();
    if (orgResult.kind !== 'ready') {
      return orgResult;
    }

    const found = orgResult.data.agents.find((a) => a.id === agentId);
    if (!found) {
      return {
        kind: 'unavailable',
        reason: `El agente con identificador ${agentId} no fue localizado en los registros operativos en vivo.`,
        retryable: false,
      };
    }

    return {
      kind: 'ready',
      origin: 'live',
      data: found,
      fetchedAt: new Date().toISOString(),
    };
  }
}
