/**
 * RONIN I1-I6 Shared Domain Models & Pure Parsers
 * Spec: AAO-FE-RONIN-2026-10-25
 *
 * Provides typed models and fail-closed parsing for:
 * - I1: Provider, model, and CLI release identity.
 * - I2: No-progress retry detection.
 * - I3: Staged capability determinant of backend/model.
 * - I4: Capability/provider router recommendations (advisory only).
 * - I5: Estimated per-attempt cost and daily agent budget.
 * - I6: Execution history and evidence presentation.
 */

export interface ModelProfile {
  backend: 'fixture' | 'codex' | string;
  provider: string;
  model: string | null;
  seats: string[];
  quality: Record<string, number> | null;
  cost_per_attempt_usd: number | null;
  costPerAttemptUsd?: number | null;
}

export interface CheckSummary {
  check_id: string;
  conclusion: string;
  exit_code: number;
  error?: string;
}

export interface RunExecutionSummary {
  conclusion?: string;
  candidate_sha?: string;
  candidateSha?: string;
  candidate?: string;
  check?: string;
  check_details?: CheckSummary | string;
  checkDetails?: string;
  agent?: string;
  provider?: string | null;
  model?: string | null;
  backend_version?: string;
  backendVersion?: string;
  selection?: string;
  capability_id?: string | null;
  capabilityId?: string | null;
  capability_version?: string | null;
  capabilityVersion?: string | null;
  backend_source?: 'capability' | 'environment' | string;
  backendSource?: string;
  cost_estimate_usd?: number;
  costEstimateUsd?: number;
  error?: string;
  alert?: string;
  is_no_progress_retry?: boolean;
  isNoProgressRetry?: boolean;
  is_budget_exceeded?: boolean;
  isBudgetExceeded?: boolean;
}

export interface ModelRoutingRejectedCandidate {
  candidate: string;
  reason: string;
}

export interface ModelRoutingRecord {
  id?: string;
  work_id: string;
  taskId?: string;
  capability_id: string | null;
  capabilityId?: string | null;
  version: string | null;
  capabilityVersion?: string | null;
  reasons: string[];
  rejected: ModelRoutingRejectedCandidate[];
  seat: string;
  role: string;
  exclude_providers: string[];
  activated_backends: string[];
  activatedBackends?: string[];
  budget_left_usd: number | null;
  budgetLeftUsd?: number | null;
  principal_id?: string;
  execution_authorized: false; // Inviolable invariant: routing recommendations NEVER authorize execution
  executionAuthorized: false;
  hasContractInconsistency?: boolean;
  contractInconsistencyReason?: string;
  created_at?: string;
  routedAt?: string;
}

export interface ProjectBudgetInfo {
  daily_budget_usd: number | null;
  budget_left_usd: number | null;
  spent_today_usd: number | null;
  window: 'UTC';
  is_configured: boolean;
  notes?: string;
}

/**
 * Parses optional model_profile from capability contract or raw profile object.
 * Pure and fail-closed: returns null if absent or malformed.
 * Strictly adheres to backend contract:
 * - seats must be a list of identifier names (string[]).
 * - quality must be an object mapping seat names to integer scores 0..5.
 * - cost_per_attempt_usd: strictly differentiates declared 0 from missing/unknown (null).
 */
export function parseModelProfile(contractOrProfile: unknown): ModelProfile | null {
  if (typeof contractOrProfile !== 'object' || contractOrProfile === null) return null;
  const obj = contractOrProfile as Record<string, unknown>;

  // Check if caller passed the full contract or the inner model_profile object
  const p = (typeof obj.model_profile === 'object' && obj.model_profile !== null
    ? obj.model_profile
    : obj) as Record<string, unknown>;

  const backend = typeof p.backend === 'string' ? p.backend.trim() : '';
  const provider = typeof p.provider === 'string' ? p.provider.trim() : '';
  if (!backend || !provider) return null;

  const model = typeof p.model === 'string' && p.model.trim() !== '' ? p.model.trim() : null;

  // Backend contract (src/aao/capability_contracts.py:53):
  // "model_profile.seats must be a list of names"
  let seats: string[] = [];
  if (Array.isArray(p.seats)) {
    seats = p.seats.filter(
      (s): s is string => typeof s === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(s)
    );
  }

  // Backend contract (src/aao/capability_contracts.py:46):
  // "model_profile.quality must map seats to 0-5"
  let quality: Record<string, number> | null = null;
  if (typeof p.quality === 'object' && p.quality !== null && !Array.isArray(p.quality)) {
    const qMap: Record<string, number> = {};
    for (const [k, v] of Object.entries(p.quality)) {
      if (typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 5) {
        qMap[k] = v;
      }
    }
    quality = Object.keys(qMap).length > 0 ? qMap : null;
  }

  // CEO Requirement 3: Strictly distinguish declared 0 (e.g. free fixture) from missing (null).
  const rawCost = p.cost_per_attempt_usd !== undefined ? p.cost_per_attempt_usd : p.costPerAttemptUsd;
  let cost: number | null = null;
  if (typeof rawCost === 'number' && !Number.isNaN(rawCost) && rawCost >= 0 && rawCost <= 1000) {
    cost = rawCost;
  }

  return {
    backend,
    provider,
    model,
    seats,
    quality,
    cost_per_attempt_usd: cost,
    costPerAttemptUsd: cost,
  };
}

/**
 * Extracts and formats RONIN execution evidence from backend result JSON or task execution object.
 * Preserves exact observed fields without fabricating values.
 */
export function parseRunSummary(input: unknown): RunExecutionSummary {
  if (typeof input !== 'object' || input === null) return {};
  const wrapper = input as Record<string, unknown>;

  // If passed a TaskExecutionRecord (which has .result), unwrap or merge with .result
  const r: Record<string, unknown> =
    typeof wrapper.result === 'object' && wrapper.result !== null
      ? { ...wrapper, ...(wrapper.result as Record<string, unknown>) }
      : wrapper;

  const str = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() !== '' ? v : undefined);
  const num = (v: unknown): number | undefined => (typeof v === 'number' ? v : undefined);

  let checkDetails: CheckSummary | undefined;
  let checkFormatted: string | undefined;

  if (typeof r.check === 'object' && r.check !== null) {
    const c = r.check as Record<string, unknown>;
    if ('check_id' in c || 'exit_code' in c) {
      checkDetails = {
        check_id: str(c.check_id) ?? 'check',
        conclusion: str(c.conclusion) ?? '?',
        exit_code: typeof c.exit_code === 'number' ? c.exit_code : -1,
        error: str(c.error),
      };
      checkFormatted = `${checkDetails.check_id}: ${checkDetails.conclusion} (exit ${checkDetails.exit_code})`;
    } else {
      // General check object with pass/fail counts
      const parts: string[] = [];
      if ('passed' in c) parts.push(`passed=${String(c.passed)}`);
      if ('tests_passed' in c) parts.push(`tests_passed=${String(c.tests_passed)}`);
      if ('tests_failed' in c) parts.push(`tests_failed=${String(c.tests_failed)}`);
      checkFormatted = parts.length > 0 ? parts.join(', ') : JSON.stringify(c);
    }
  } else if (typeof r.check === 'string') {
    checkFormatted = r.check;
  }

  const provider = str(r.provider) ?? null;
  const model = str(r.model) ?? null;
  const backendVersion = str(r.backend_version) ?? str(r.backendVersion);

  // Formatted agent line: provider · model · backend_version
  let agentStr: string | undefined;
  if (provider) {
    agentStr = [provider, model ?? 'modelo por defecto del CLI', backendVersion].filter(Boolean).join(' · ');
  }

  const capabilityId = str(r.capability_id) ?? str(r.capabilityId) ?? null;
  const capabilityVersion = str(r.capability_version) ?? str(r.capabilityVersion) ?? null;
  const backendSource = str(r.backend_source) ?? str(r.backendSource);
  const rawCost = r.cost_estimate_usd ?? r.costEstimateUsd;
  const costEstimateUsd = num(rawCost);

  // Formatted selection line
  let selectionStr: string | undefined;
  if (capabilityId) {
    const capTag = `${capabilityId}@${capabilityVersion ?? '?'}`;
    const sourceLabel =
      backendSource === 'capability' || backendSource === 'staged_determinant'
        ? 'elegido por la capacidad'
        : backendSource === 'environment' || backendSource === 'environment_default'
        ? 'elegido por el entorno'
        : undefined;
    const costLabel = costEstimateUsd !== undefined ? `coste estimado ${costEstimateUsd} USD` : undefined;
    selectionStr = [capTag, sourceLabel, costLabel].filter(Boolean).join(' · ');
  } else if (backendSource === 'environment_default') {
    selectionStr = 'modelo por defecto del entorno';
  }

  const error = str(r.error);
  const alert = str(r.alert) ?? error;

  const errorOrAlert = alert ?? error ?? '';
  const isBudgetExceeded = Boolean(
    errorOrAlert &&
      (errorOrAlert.includes('budget.exceed') ||
        errorOrAlert.includes('budget exceeded') ||
        errorOrAlert.includes('daily_budget') ||
        errorOrAlert.includes('budget limit'))
  );

  const isNoProgress = Boolean(
    errorOrAlert &&
      (errorOrAlert.includes('No progress') ||
        errorOrAlert.includes('no progress') ||
        errorOrAlert.includes('same outcome'))
  );

  const conclusion = str(r.conclusion);
  const candidateSha = str(r.candidate_sha) ?? str(r.candidateSha);

  return {
    conclusion,
    candidate_sha: candidateSha,
    candidateSha,
    candidate: candidateSha,
    check: checkFormatted,
    check_details: checkDetails ?? checkFormatted,
    checkDetails: checkFormatted,
    agent: agentStr,
    provider,
    model,
    backend_version: backendVersion,
    backendVersion,
    selection: selectionStr,
    capability_id: capabilityId,
    capabilityId,
    capability_version: capabilityVersion,
    capabilityVersion,
    backend_source: backendSource,
    backendSource,
    cost_estimate_usd: costEstimateUsd,
    costEstimateUsd,
    error,
    alert,
    is_no_progress_retry: isNoProgress,
    isNoProgressRetry: isNoProgress,
    is_budget_exceeded: isBudgetExceeded,
    isBudgetExceeded,
  };
}

/**
 * Parses a model.routed event details into a typed ModelRoutingRecord.
 * CEO Requirement 5: Valida execution_authorized en lugar de sustituir silenciosamente un valor recibido.
 * Un valor distinto de false debe tratarse como una inconsistencia de contrato, no como una autorización.
 */
export function parseRoutingDecision(
  details: unknown,
  workId = '',
  eventId?: string,
  createdAt?: string
): ModelRoutingRecord | null {
  if (typeof details !== 'object' || details === null) return null;
  const d = details as Record<string, unknown>;

  const actualWorkId = typeof d.work_id === 'string' ? d.work_id : workId;
  const capabilityId =
    typeof d.capability_id === 'string'
      ? d.capability_id
      : typeof d.capabilityId === 'string'
      ? d.capabilityId
      : null;
  const version =
    typeof d.version === 'string'
      ? d.version
      : typeof d.capabilityVersion === 'string'
      ? d.capabilityVersion
      : null;
  const seat = typeof d.seat === 'string' ? d.seat : '';
  const role = typeof d.role === 'string' ? d.role : 'implementer';

  const reasons = Array.isArray(d.reasons)
    ? d.reasons.filter((r): r is string => typeof r === 'string')
    : [];

  const rejected: ModelRoutingRejectedCandidate[] = [];
  if (Array.isArray(d.rejected)) {
    for (const item of d.rejected) {
      if (Array.isArray(item) && item.length >= 2) {
        rejected.push({
          candidate: String(item[0]),
          reason: String(item[1]),
        });
      } else if (typeof item === 'object' && item !== null) {
        const obj = item as Record<string, unknown>;
        if (typeof obj.candidate === 'string' && typeof obj.reason === 'string') {
          rejected.push({
            candidate: obj.candidate,
            reason: obj.reason,
          });
        }
      }
    }
  }

  const excludeProviders = Array.isArray(d.exclude_providers)
    ? d.exclude_providers.filter((p): p is string => typeof p === 'string')
    : [];

  const activatedBackends = Array.isArray(d.activated_backends)
    ? d.activated_backends.filter((b): b is string => typeof b === 'string')
    : Array.isArray(d.activatedBackends)
    ? d.activatedBackends.filter((b): b is string => typeof b === 'string')
    : [];

  const rawBudget = d.budget_left_usd ?? d.budgetLeftUsd;
  const budgetLeft = typeof rawBudget === 'number' ? rawBudget : null;
  const principalId = typeof d.principal_id === 'string' ? d.principal_id : undefined;
  const actualCreatedAt =
    typeof d.created_at === 'string'
      ? d.created_at
      : createdAt ?? (typeof d.routedAt === 'string' ? d.routedAt : undefined);

  // CEO Requirement 5: Validation of execution_authorized
  const rawAuth = d.execution_authorized !== undefined ? d.execution_authorized : d.executionAuthorized;
  let hasContractInconsistency = false;
  let contractInconsistencyReason: string | undefined;

  if (rawAuth !== false) {
    hasContractInconsistency = true;
    contractInconsistencyReason =
      `Inconsistencia de contrato: el router de modelos es estrictamente consultivo y exige 'execution_authorized: false'. ` +
      `El payload recibido contiene '${String(rawAuth)}'. Esta decisión NUNCA autoriza ejecución.`;
  }

  return {
    id: eventId ?? (typeof d.id === 'string' ? d.id : undefined),
    work_id: actualWorkId,
    taskId: actualWorkId,
    capability_id: capabilityId,
    capabilityId,
    version,
    capabilityVersion: version,
    reasons,
    rejected,
    seat,
    role,
    exclude_providers: excludeProviders,
    activated_backends: activatedBackends,
    activatedBackends,
    budget_left_usd: budgetLeft,
    budgetLeftUsd: budgetLeft,
    principal_id: principalId,
    execution_authorized: false, // Fundamental invariant: NUNCA autoriza ejecución
    executionAuthorized: false,
    hasContractInconsistency,
    contractInconsistencyReason,
    created_at: actualCreatedAt,
    routedAt: actualCreatedAt,
  };
}
