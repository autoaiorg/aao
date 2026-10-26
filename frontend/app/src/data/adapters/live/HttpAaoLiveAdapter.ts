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
import type { AaoOrganizationCommandPort, OrganizationProfileCommand, OrganizationUnitCommand } from '../../ports/AaoOrganizationCommandPort';
import type { AaoWorkCommandPort, CEOWorkRequest, CreatedWorkRequest } from '../../ports/AaoWorkCommandPort';
import type { AaoConversationPort, AssignableAgent, ConversationWorkGroupInput, ConversationWorkGroupProposal, ConversationWorkGroupResult, ConversationWorkRequestInput, ConversationWorkRequestResult, ProjectConversation, ProjectConversationMessage, ProjectWorkGroup, WorkGroupConsolidationResult } from '../../ports/AaoConversationPort';
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
  BoardStage,
  TaskItem,
  ActivityEvent,
  KnowledgeSourceRecord,
} from '../../../domain/models';
import {
  parseModelProfile,
  parseRoutingDecision,
  type ModelRoutingRecord,
} from '../../../features/ronin/modelProfile';
import {
  ActivityEventSchema,
  KnowledgeSourceSchema,
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
  getCeoCookieSession?: () => boolean;
  getCsrfToken?: () => string | null;
  onUnauthorized?: () => void;
  requireAuth?: boolean;
}

export class HttpAaoLiveAdapter implements AaoReadPort, AaoOrganizationCommandPort, AaoWorkCommandPort, AaoConversationPort {
  private baseUrl: string;
  private timeoutMs: number;
  private getToken: () => string | null;
  private getAuthRole: () => 'AGENT' | 'CEO';
  private getCeoCookieSession: () => boolean;
  private getCsrfToken: () => string | null;
  private onUnauthorized?: () => void;
  private requireAuth: boolean;
  private activeControllers: Set<AbortController> = new Set();

  private hasAuthenticatedSession(): boolean {
    return Boolean(this.getToken() || (this.getAuthRole() === 'CEO' && this.getCeoCookieSession()));
  }

  constructor(config: HttpLiveAdapterConfig = {}) {
    this.baseUrl = config.baseUrl ?? '';
    this.timeoutMs = config.timeoutMs ?? 10000;
    this.getToken = config.getToken ?? (() => null);
    this.getAuthRole = config.getAuthRole ?? (() => 'AGENT');
    this.getCeoCookieSession = config.getCeoCookieSession ?? (() => false);
    this.getCsrfToken = config.getCsrfToken ?? (() => null);
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
    options: RequestInit = {},
    timeoutMs = this.timeoutMs,
  ): Promise<DataState<T>> {
    const controller = new AbortController();
    this.activeControllers.add(controller);

    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    const token = this.getToken();
    const cookieSession = this.getAuthRole() === 'CEO' && this.getCeoCookieSession();
    if (this.requireAuth && !token && !cookieSession) {
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
    if (cookieSession && !['GET', 'HEAD', 'OPTIONS'].includes((options.method || 'GET').toUpperCase())) {
      const csrfToken = this.getCsrfToken();
      if (!csrfToken) {
        clearTimeout(timeoutId);
        this.activeControllers.delete(controller);
        return { kind: 'forbidden', reason: 'Falta token CSRF de la sesión CEO.' };
      }
      headers['X-AAO-CSRF'] = csrfToken;
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers,
        credentials: 'include',
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
        // Cookie-backed CEO sessions are used only for CEO-scoped API access. A
        // rejection means the browser's local auth state is stale (for example,
        // the server session was revoked); clear that state instead of leaving
        // the shell showing a verified CEO indefinitely. Do not apply this to
        // ordinary bearer/agent 403s, which can be resource-level denials.
        if (cookieSession && this.onUnauthorized) this.onUnauthorized();
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
          message: `La solicitud a ${endpoint} fue cancelada o excedió el tiempo límite (${timeoutMs}ms)`,
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
    const cookieSession = role === 'CEO' && this.getCeoCookieSession();

    if (!token && !cookieSession) {
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
          headers: { ...(token ? { 'X-CEO-Token': token } : {}), Accept: 'application/json' },
          credentials: 'include',
          signal: controller.signal,
        });

        if (response.status === 401 || response.status === 403) {
          if (cookieSession && this.onUnauthorized) this.onUnauthorized();
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
            principal_id: cookieSession ? 'ceo (sesión de navegador verificada)' : 'ceo (bearer de desarrollo verificado)',
            kind: 'CEO',
            enabled: true,
            verificationStatus: 'verified',
            authMethod: cookieSession ? 'Cookie de sesión comprobada vía GET /v1/mandates' : 'X-CEO-Token comprobado vía GET /v1/mandates',
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
    const cookieSession = this.getAuthRole() === 'CEO' && this.getCeoCookieSession();
    if (this.requireAuth && !token && !cookieSession) {
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
        credentials: 'include',
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
        if (cookieSession && this.onUnauthorized) this.onUnauthorized();
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

        const rawRouting = Array.isArray(itemObj.routing_decisions)
          ? itemObj.routing_decisions
          : Array.isArray(itemObj.routingDecisions)
          ? itemObj.routingDecisions
          : [];
        const taskRoutingDecisions = rawRouting
          .map((r) => parseRoutingDecision(r, id))
          .filter((d): d is ModelRoutingRecord => d !== null);

        const taskItem: TaskItem = {
          id,
          title,
          status: rawStatus, // PRESERVES RAW SEMANTIC STATUS WITHOUT MUTATION
          rawStatus,
          isUnrecognizedStatus: !isCanonical,
          acceptanceCriteria: Array.isArray(itemObj.acceptance_criteria)
            ? (itemObj.acceptance_criteria as string[])
            : [],
          parentWorkId: typeof itemObj.parent_work_id === 'string' ? itemObj.parent_work_id : null,
          dependsOn: Array.isArray(itemObj.depends_on)
            ? itemObj.depends_on.filter((id): id is string => typeof id === 'string')
            : [],
          workGroupId: typeof itemObj.work_group_id === 'string' ? itemObj.work_group_id : null,
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
          routingDecisions: taskRoutingDecisions.length > 0 ? taskRoutingDecisions : undefined,
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

  async exchangeCeoBearerForSession(token: string): Promise<DataState<{ csrf_token: string }>> {
    return this.authSessionRequest('/v1/auth/ceo/session', token);
  }

  async restoreCeoBrowserSession(): Promise<DataState<{ csrf_token: string }>> {
    return this.authSessionRequest('/v1/auth/ceo/session/csrf');
  }

  async revokeCeoBrowserSession(csrfToken: string): Promise<DataState<{ logged_out: boolean }>> {
    return this.authSessionRequest('/v1/auth/ceo/logout', undefined, csrfToken);
  }

  private async authSessionRequest<T extends { csrf_token?: string; logged_out?: boolean }>(
    path: string, bearer?: string, csrfToken?: string,
  ): Promise<DataState<T>> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (bearer) headers['X-CEO-Token'] = bearer;
    if (csrfToken) headers['X-AAO-CSRF'] = csrfToken;
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST', headers, credentials: 'include',
      });
      if (!response.ok) {
        return { kind: 'forbidden', reason: `Sesión CEO rechazada (HTTP ${response.status}).` };
      }
      const payload: unknown = await response.json();
      const schema = path.endsWith('/logout')
        ? z.object({ logged_out: z.boolean() })
        : z.object({ authenticated: z.literal(true), csrf_token: z.string().min(32), expires_in_seconds: z.number() });
      const parsed = schema.safeParse(payload);
      if (!parsed.success) return { kind: 'error', code: 'SCHEMA_VALIDATION_ERROR', message: 'Respuesta de sesión CEO inválida.', retryable: false };
      return { kind: 'ready', origin: 'live', fetchedAt: new Date().toISOString(), data: parsed.data as T };
    } catch {
      return { kind: 'error', code: 'NETWORK_ERROR', message: 'No se pudo contactar el servicio de sesión CEO.', retryable: true };
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
        modelProfile: parseModelProfile(c.contract),
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

  async getKnowledgeSourceIndex(): Promise<DataState<KnowledgeSourceRecord[]>> {
    if (this.getAuthRole() !== 'CEO') {
      return { kind: 'forbidden', reason: 'El índice corporativo de fuentes requiere una sesión CEO.' };
    }
    const result = await this.request('/v1/knowledge/index', z.array(KnowledgeSourceSchema));
    if (result.kind !== 'ready') return result;
    if (result.data.length === 0) return { kind: 'empty', origin: 'live', fetchedAt: new Date().toISOString() };
    return {
      kind: 'ready', origin: 'live', fetchedAt: new Date().toISOString(),
      data: result.data.map((record) => ({
        workId: record.work_id, projectId: record.project_id, projectName: record.project_name,
        title: record.title, status: record.status, evidenceReferences: record.evidence_references,
        reviews: record.reviews.map((review) => ({
          id: review.id, reviewerId: review.reviewer_id, decision: review.decision,
          createdAt: review.created_at, evidenceReferences: review.evidence_references,
        })),
      })),
    };
  }

  async getCeoOverview(projectId?: string): Promise<CeoOverview> {
    const now = new Date().toISOString();

    if (this.requireAuth && !this.hasAuthenticatedSession()) {
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

  // The organization projection is a backend-owned contract. In LIVE mode, do not
  // substitute a client-built roster or static departments when that contract fails.
  async getOrganizationStructure(): Promise<DataState<OrganizationStructure>> {
    if (!this.hasAuthenticatedSession() && this.requireAuth) {
      return {
        kind: 'unavailable',
        reason: 'Se requiere una credencial autenticada para consultar la organización real.',
        retryable: false,
      };
    }
    return this.request('/v1/organization', OrganizationStructureSchema);
  }

  async putOrganizationUnit(input: OrganizationUnitCommand): Promise<DataState<unknown>> {
    if (this.getAuthRole() !== 'CEO') {
      return { kind: 'forbidden', reason: 'Solo la sesión CEO puede declarar unidades organizativas.' };
    }
    return this.request('/v1/organization/units', undefined, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
  }

  async putOrganizationProfile(input: OrganizationProfileCommand): Promise<DataState<unknown>> {
    if (this.getAuthRole() !== 'CEO') {
      return { kind: 'forbidden', reason: 'Solo la sesión CEO puede declarar perfiles organizativos.' };
    }
    return this.request('/v1/organization/profiles', undefined, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
  }

  async createCEOWorkRequest(projectId: string, input: CEOWorkRequest): Promise<DataState<CreatedWorkRequest>> {
    if (this.getAuthRole() !== 'CEO') {
      return { kind: 'forbidden', reason: 'Solo la sesión CEO puede registrar una solicitud de trabajo.' };
    }
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/work-requests`,
      z.object({ id: z.string().uuid(), status: z.literal('INBOX') }),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      },
    );
  }

  async listProjectConversations(projectId: string): Promise<DataState<ProjectConversation[]>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede leer conversaciones de proyecto.' };
    return this.request(`/v1/projects/${encodeURIComponent(projectId)}/conversations`, z.array(z.object({
      id: z.string().uuid(), project_id: z.string().uuid(), title: z.string(),
      created_at: z.string(), updated_at: z.string(),
    })), { method: 'GET' });
  }

  async listAssignableAgents(projectId: string): Promise<DataState<AssignableAgent[]>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede asignar trabajo.' };
    return this.request(`/v1/projects/${encodeURIComponent(projectId)}/assignable-agents`, z.array(z.object({
      principal_id: z.string(), display_name: z.string(),
    })), { method: 'GET' });
  }

  async listConversationMessages(projectId: string, conversationId: string): Promise<DataState<ProjectConversationMessage[]>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede leer conversaciones de proyecto.' };
    return this.request(`/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/messages`, z.array(z.object({
      id: z.string().uuid(), sender: z.enum(['CEO', 'AAO']), body: z.string(),
      related_work_id: z.string().uuid().nullable(), work_status: z.string().nullable(),
      latest_execution: z.object({ id: z.string().uuid(), status: z.string(),
        backend: z.string().nullable(), provider: z.string().nullable(), model: z.string().nullable(),
      }).nullable(), provider: z.string().nullable().optional(), model: z.string().nullable().optional(),
      turn_status: z.enum(['PENDING', 'COMPLETED', 'FAILED']).nullable().optional(),
      turn_error_code: z.string().nullable().optional(), created_at: z.string(),
      turn_idempotency_key: z.string().uuid().nullable().optional(),
    })), { method: 'GET' });
  }

  async createProjectConversation(projectId: string, title: string): Promise<DataState<Pick<ProjectConversation, 'id' | 'project_id' | 'title'>>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede crear conversaciones de proyecto.' };
    return this.request(`/v1/projects/${encodeURIComponent(projectId)}/conversations`, z.object({
      id: z.string().uuid(), project_id: z.string().uuid(), title: z.string(),
    }), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) });
  }

  async appendCEOConversationMessage(projectId: string, conversationId: string, body: string): Promise<DataState<ProjectConversationMessage>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede escribir en conversaciones de proyecto.' };
    return this.request(`/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/messages`, z.object({
      id: z.string().uuid(), sender: z.literal('CEO'), body: z.string(),
      related_work_id: z.string().uuid().nullable(), work_status: z.string().nullable(),
      latest_execution: z.object({ id: z.string().uuid(), status: z.string(),
        backend: z.string().nullable(), provider: z.string().nullable(), model: z.string().nullable(),
      }).nullable(), created_at: z.string(),
    }), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
  }

  async streamCEOConversationTurn(
    projectId: string,
    conversationId: string,
    body: string,
    idempotencyKey: string,
    onDelta: (delta: string) => void,
  ): Promise<DataState<{ message_id: string }>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede conversar con AAO.' };
    const token = this.getToken();
    const cookieSession = this.getCeoCookieSession();
    if (this.requireAuth && !token && !cookieSession) return { kind: 'forbidden', reason: 'Sesión CEO requerida.' };
    const headers: Record<string, string> = { Accept: 'text/event-stream', 'Content-Type': 'application/json' };
    if (token) headers['X-CEO-Token'] = token;
    if (cookieSession) {
      const csrfToken = this.getCsrfToken();
      if (!csrfToken) return { kind: 'forbidden', reason: 'Falta token CSRF de la sesión CEO.' };
      headers['X-AAO-CSRF'] = csrfToken;
    }
    const controller = new AbortController();
    this.activeControllers.add(controller);
    try {
      const response = await fetch(`${this.baseUrl}/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/turns`, {
        method: 'POST', headers, credentials: 'include', signal: controller.signal,
        body: JSON.stringify({ body, idempotency_key: idempotencyKey }),
      });
      if (!response.ok || !response.body) {
        if (response.status === 401 || response.status === 403) this.onUnauthorized?.();
        return { kind: response.status === 401 || response.status === 403 ? 'forbidden' : 'error',
          ...(response.status === 401 || response.status === 403
            ? { reason: `No autorizado (HTTP ${response.status}).` }
            : { code: `HTTP_${response.status}`, message: 'No se pudo iniciar la respuesta de AAO.', retryable: response.status >= 500 }) } as DataState<{ message_id: string }>;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let messageId = '';
      let streamError: { code: string; message?: string } | undefined;
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (const event of events) {
          const type = event.match(/^event: (.+)$/m)?.[1];
          const data = event.match(/^data: (.+)$/m)?.[1];
          if (!data) continue;
          const parsed = JSON.parse(data) as { delta?: string; message_id?: string; code?: string; message?: string };
          if (type === 'delta' && parsed.delta) onDelta(parsed.delta);
          if (type === 'done') messageId = parsed.message_id || '';
          if (type === 'error') streamError = { code: parsed.code || 'PROVIDER_ERROR', message: parsed.message };
        }
        if (done) break;
      }
      if (streamError) return { kind: 'error', code: streamError.code || 'PROVIDER_ERROR', message: streamError.message || 'El proveedor no pudo responder.', retryable: true };
      if (!messageId) return { kind: 'error', code: 'INCOMPLETE_STREAM', message: 'La respuesta terminó sin confirmación de persistencia.', retryable: true };
      return { kind: 'ready', origin: 'live', fetchedAt: new Date().toISOString(), data: { message_id: messageId } };
    } catch {
      return { kind: 'error', code: 'STREAM_ERROR', message: 'Se interrumpió la respuesta de AAO.', retryable: true };
    } finally {
      this.activeControllers.delete(controller);
    }
  }

  async createWorkRequestFromMessage(
    projectId: string,
    conversationId: string,
    messageId: string,
    input: ConversationWorkRequestInput,
  ): Promise<DataState<ConversationWorkRequestResult>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede convertir mensajes en solicitudes de trabajo.' };
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/work-request`,
      z.object({ id: z.string().uuid(), status: z.string(), created: z.boolean() }),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      },
    );
  }

  async createWorkRequestFromConversation(
    projectId: string,
    conversationId: string,
    input: ConversationWorkRequestInput,
  ): Promise<DataState<ConversationWorkRequestResult>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede estructurar trabajo desde una conversación.' };
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/work-requests`,
      z.object({ id: z.string().uuid(), status: z.string(), created: z.boolean() }),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
    );
  }

  async createWorkGroupFromConversation(
    projectId: string,
    conversationId: string,
    input: ConversationWorkGroupInput,
  ): Promise<DataState<ConversationWorkGroupResult>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede estructurar un desglose desde una conversación.' };
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/work-groups`,
      z.object({
        id: z.string().uuid(), project_id: z.string().uuid(), conversation_id: z.string().uuid(),
        parent_work_id: z.string().uuid(), status: z.string(), created: z.boolean(),
        tasks: z.array(z.object({
          id: z.string().uuid(), title: z.string(), status: z.string(),
          assigned_principal_id: z.string().nullable(), depends_on: z.array(z.string().uuid()),
        })),
      }),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
    );
  }

  async proposeWorkGroupFromConversation(
    projectId: string,
    conversationId: string,
  ): Promise<DataState<ConversationWorkGroupProposal>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede pedir una propuesta de tareas.' };
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/work-group-proposals`,
      z.object({
        proposal: z.object({
          title: z.string(), description: z.string(), acceptance_criteria: z.array(z.string()),
          tasks: z.array(z.object({
            key: z.string(), title: z.string(), description: z.string(),
            acceptance_criteria: z.array(z.string()), depends_on: z.array(z.string()),
          })),
        }),
        based_on_message_ids: z.array(z.string().uuid()),
        provider: z.string(), model: z.string(), persisted_as_work: z.literal(false),
      }),
      { method: 'POST' },
      75_000,
    );
  }

  async listProjectWorkGroups(projectId: string): Promise<DataState<ProjectWorkGroup[]>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede consultar equipos de trabajo.' };
    const evidence = z.unknown();
    const child = z.object({
      work_id: z.string().uuid(), status: z.string(), assigned_principal_id: z.string().nullable(), evidence,
      executions: z.array(z.object({
        id: z.string().uuid(), status: z.string(), worker_id: z.string().nullable(),
        result_sha256: z.string().regex(/^[0-9a-f]{64}$/).nullable(),
      })),
      reviews: z.array(z.object({
        id: z.string().uuid(), decision: z.string(), candidate_sha: z.string().nullable(), evidence,
      })),
    });
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/work-groups`,
      z.array(z.object({
        id: z.string().uuid(), conversation_id: z.string().uuid(), parent_work_id: z.string().uuid(),
        title: z.string(), parent_status: z.string(), source_sha256: z.string().regex(/^[0-9a-f]{64}$/),
        consolidation_ready: z.boolean(), children: z.array(child),
        consolidation: z.object({
          id: z.string().uuid(), summary: z.string(), source_sha256: z.string(),
          source_snapshot: z.object({ children: z.array(child) }), idempotency_key: z.string().uuid(),
          created_by: z.string(), created_at: z.string(),
        }).nullable(),
        partial_reports: z.array(z.object({
          id: z.string().uuid(), report_kind: z.enum(['PARTIAL', 'CONFLICT_REVIEW']),
          summary: z.string(), source_sha256: z.string().regex(/^[0-9a-f]{64}$/),
          source_snapshot: z.unknown(), idempotency_key: z.string().uuid(),
          created_by: z.string(), created_at: z.string(),
        })),
      })),
    );
  }

  async assignWorkGroupChild(workId: string, principalId: string): Promise<DataState<{ work_id: string; principal_id: string; assigned_by: string; grants_created: false }>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede asignar trabajos.' };
    return this.request(`/v1/work/${encodeURIComponent(workId)}/assignment`, z.object({
      work_id: z.string().uuid(), principal_id: z.string(), assigned_by: z.literal('ceo'), grants_created: z.literal(false),
    }), {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ principal_id: principalId }),
    });
  }

  async confirmWorkGroupConsolidation(
    projectId: string,
    groupId: string,
    input: { idempotency_key: string; expected_source_sha256: string; summary: string },
  ): Promise<DataState<WorkGroupConsolidationResult>> {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden', reason: 'Solo la sesión CEO puede confirmar una consolidación.' };
    const evidence = z.unknown();
    const child = z.object({
      work_id: z.string().uuid(), status: z.string(), assigned_principal_id: z.string().nullable(), evidence,
      executions: z.array(z.object({
        id: z.string().uuid(), status: z.string(), worker_id: z.string().nullable(),
        result_sha256: z.string().regex(/^[0-9a-f]{64}$/).nullable(),
      })),
      reviews: z.array(z.object({
        id: z.string().uuid(), decision: z.string(), candidate_sha: z.string().nullable(), evidence,
      })),
    });
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/work-groups/${encodeURIComponent(groupId)}/consolidation`,
      z.object({
        id: z.string().uuid(), project_id: z.string().uuid(), work_group_id: z.string().uuid(),
        parent_work_id: z.string().uuid(), summary: z.string(), source_sha256: z.string(),
        source_snapshot: z.object({ children: z.array(child) }), idempotency_key: z.string().uuid(),
        created_by: z.string(), created_at: z.string(), created: z.boolean(),
      }),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
    );
  }

  async createWorkGroupPartialReport(
    projectId: string,
    groupId: string,
    input: { idempotency_key: string; expected_source_sha256: string; report_kind: 'PARTIAL' | 'CONFLICT_REVIEW'; summary: string },
  ) {
    if (this.getAuthRole() !== 'CEO') return { kind: 'forbidden' as const, reason: 'Solo la sesión CEO puede registrar informes.' };
    return this.request(
      `/v1/projects/${encodeURIComponent(projectId)}/work-groups/${encodeURIComponent(groupId)}/partial-reports`,
      z.object({
        id: z.string().uuid(), report_kind: z.enum(['PARTIAL', 'CONFLICT_REVIEW']),
        summary: z.string(), source_sha256: z.string().regex(/^[0-9a-f]{64}$/),
        source_snapshot: z.unknown(), idempotency_key: z.string().uuid(),
        created_by: z.string(), created_at: z.string(), created: z.boolean(), final: z.literal(false),
      }),
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
    );
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
