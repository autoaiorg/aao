import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  parseModelProfile,
  parseRunSummary,
  parseRoutingDecision,
} from '../features/ronin/modelProfile';
import { ModelProfileBadge } from '../features/ronin/components/ModelProfileBadge';
import { RoutingDecisionCard } from '../features/ronin/components/RoutingDecisionCard';
import { BudgetOverviewBadge } from '../features/ronin/components/BudgetOverviewBadge';
import { ExecutionTimeline } from '../features/ronin/components/ExecutionTimeline';
import { HttpAaoLiveAdapter } from '../data/adapters/live/HttpAaoLiveAdapter';
import type { TaskItem } from '../domain/models';

describe('RONIN F4.9 Integration — Parsers and Pure Logic', () => {
  describe('parseModelProfile (I3 & Contract Alignment)', () => {
    it('parses valid model_profile with identifier seats and score map quality', () => {
      const rawContract = {
        model_profile: {
          backend: 'claude',
          provider: 'anthropic',
          model: 'claude-3-7-sonnet',
          seats: ['implementer', 'reviewer'],
          quality: { implementer: 5, reviewer: 4 },
          cost_per_attempt_usd: 0.05,
        },
      };

      const parsed = parseModelProfile(rawContract);
      expect(parsed).not.toBeNull();
      expect(parsed?.backend).toBe('claude');
      expect(parsed?.provider).toBe('anthropic');
      expect(parsed?.model).toBe('claude-3-7-sonnet');
      expect(parsed?.seats).toEqual(['implementer', 'reviewer']);
      expect(parsed?.quality).toEqual({ implementer: 5, reviewer: 4 });
      expect(parsed?.cost_per_attempt_usd).toBe(0.05);
    });

    it('strictly differentiates declared cost 0 (free) from missing cost (null / unknown)', () => {
      // 1. Declared cost 0
      const declaredZero = parseModelProfile({
        backend: 'fixture',
        provider: 'synthetic',
        cost_per_attempt_usd: 0,
      });
      expect(declaredZero?.cost_per_attempt_usd).toBe(0);

      // 2. Missing cost: MUST be null, NEVER silently defaulted to 0!
      const missingCost = parseModelProfile({
        backend: 'codex',
        provider: 'openai',
        model: 'gpt-4o',
      });
      expect(missingCost?.cost_per_attempt_usd).toBeNull();
      expect(missingCost?.costPerAttemptUsd).toBeNull();
    });

    it('negative tests: enforces list of string identifier names for seats and ignores invalid numbers/strings', () => {
      // Number instead of string[]
      const numberSeats = parseModelProfile({
        backend: 'claude',
        provider: 'anthropic',
        seats: 2 as unknown as string[],
      });
      expect(numberSeats?.seats).toEqual([]);

      // Invalid characters in seat identifiers
      const invalidChars = parseModelProfile({
        backend: 'claude',
        provider: 'anthropic',
        seats: ['valid_seat-1', 'invalid seat with spaces!', 'another.valid:seat'],
      });
      expect(invalidChars?.seats).toEqual(['valid_seat-1', 'another.valid:seat']);
    });

    it('negative tests: enforces score map 0-5 for quality and rejects invalid non-object or out-of-bounds scores', () => {
      // String quality ('high') is rejected as non-contractual
      const stringQuality = parseModelProfile({
        backend: 'claude',
        provider: 'anthropic',
        quality: 'high' as unknown as Record<string, number>,
      });
      expect(stringQuality?.quality).toBeNull();

      // Out of bounds scores (< 0 or > 5 or non-integer) are filtered out
      const outOfBounds = parseModelProfile({
        backend: 'claude',
        provider: 'anthropic',
        quality: { implementer: 5, architect: 9, reviewer: -1, tester: 3.5 },
      });
      expect(outOfBounds?.quality).toEqual({ implementer: 5 });
    });

    it('returns null when backend or provider is missing, empty, or contract is invalid', () => {
      expect(parseModelProfile(undefined)).toBeNull();
      expect(parseModelProfile(null)).toBeNull();
      expect(parseModelProfile({})).toBeNull();
      expect(parseModelProfile({ backend: 'claude' })).toBeNull(); // Missing provider
      expect(parseModelProfile({ provider: 'anthropic' })).toBeNull(); // Missing backend
      expect(parseModelProfile({ backend: '   ', provider: 'anthropic' })).toBeNull();
    });
  });

  describe('parseRunSummary (I1, I2, I5, I6)', () => {
    it('extracts complete provider, model, CLI version, SHA and check info from execution result', () => {
      const exec = {
        id: 'exec-1',
        status: 'succeeded',
        worker_id: 'worker-agent-fe',
        attempts: 1,
        created_at: '2026-10-25T12:00:00Z',
        result: {
          provider: 'google',
          model: 'gemini-2.5-pro',
          backend_version: 'antigravity-cli 1.4.0',
          capability_id: 'cap-react-impl',
          capability_version: '1.2.0',
          backend_source: 'staged_determinant',
          cost_estimate_usd: 0.045,
          candidate_sha: '7249e506b9d2d0238b0638baef6599bf35fcc2f0',
          check: { passed: true, tests_passed: 14, tests_failed: 0 },
        },
      };

      const summary = parseRunSummary(exec);
      expect(summary.provider).toBe('google');
      expect(summary.model).toBe('gemini-2.5-pro');
      expect(summary.backendVersion).toBe('antigravity-cli 1.4.0');
      expect(summary.capabilityId).toBe('cap-react-impl');
      expect(summary.capabilityVersion).toBe('1.2.0');
      expect(summary.backendSource).toBe('staged_determinant');
      expect(summary.costEstimateUsd).toBe(0.045);
      expect(summary.candidateSha).toBe('7249e506b9d2d0238b0638baef6599bf35fcc2f0');
      expect(summary.isNoProgressRetry).toBe(false);
      expect(summary.isBudgetExceeded).toBe(false);
      expect(summary.checkDetails).toContain('tests_passed=14');
    });

    it('detects I2 No Progress Retry condition from alert message', () => {
      const exec = {
        id: 'exec-retry-1',
        status: 'failed',
        attempts: 2,
        result: {
          alert: 'No progress: the last two agent attempts had the same outcome; PM decision required',
          cost_estimate_usd: 0.03,
        },
      };

      const summary = parseRunSummary(exec);
      expect(summary.isNoProgressRetry).toBe(true);
      expect(summary.alert).toBe('No progress: the last two agent attempts had the same outcome; PM decision required');
    });

    it('detects I5 daily budget exceeded alert', () => {
      const exec = {
        id: 'exec-budget-1',
        status: 'failed',
        result: {
          alert: 'daily_budget_limit_exceeded: Daily budget limit reached',
          cost_estimate_usd: 0.02,
        },
      };

      const summary = parseRunSummary(exec);
      expect(summary.isBudgetExceeded).toBe(true);
    });

    it('identifies unprofiled environment default model without fabricating capability link', () => {
      const exec = {
        id: 'exec-default-1',
        status: 'running',
        result: {
          backend_source: 'environment_default',
        },
      };

      const summary = parseRunSummary(exec);
      expect(summary.backendSource).toBe('environment_default');
      expect(summary.capabilityId).toBeNull();
      expect(summary.provider).toBeNull();
    });
  });

  describe('parseRoutingDecision (I4 & Authorization Contradiction Validation)', () => {
    it('parses consultative decision when execution_authorized === false with no inconsistencies', () => {
      const rawDetails = {
        capability_id: 'cap-code-review',
        version: '2.1.0',
        seat: 'reviewer',
        role: 'auditor',
        reasons: ['Selected deterministically with high quality match.'],
        rejected: [
          ['cap-legacy-review:1.0', 'provider not activated'],
          ['cap-basic:0.5', 'insufficient seats'],
        ],
        activated_backends: ['claude', 'gemini'],
        budget_left_usd: 7.25,
        execution_authorized: false,
      };

      const record = parseRoutingDecision(rawDetails, 'task-101', 'audit-ev-99', '2026-10-25T14:00:00Z');
      expect(record).not.toBeNull();
      expect(record?.id).toBe('audit-ev-99');
      expect(record?.taskId).toBe('task-101');
      expect(record?.capabilityId).toBe('cap-code-review');
      expect(record?.capabilityVersion).toBe('2.1.0');
      expect(record?.executionAuthorized).toBe(false);
      expect(record?.execution_authorized).toBe(false);
      expect(record?.hasContractInconsistency).toBe(false);
      expect(record?.budgetLeftUsd).toBe(7.25);
      expect(record?.rejected).toHaveLength(2);
      expect(record?.rejected[0].candidate).toBe('cap-legacy-review:1.0');
      expect(record?.rejected[0].reason).toBe('provider not activated');
    });

    it('CEO Requirement 5: treats execution_authorized: true as a contract inconsistency and NEVER authorizes execution', () => {
      const contradictoryDetails = {
        capability_id: 'cap-code-review',
        version: '2.1.0',
        seat: 'reviewer',
        role: 'auditor',
        reasons: ['Attempting illegitimate execution authorization.'],
        rejected: [],
        activated_backends: ['claude'],
        budget_left_usd: 5.0,
        execution_authorized: true, // Contradiction! Advisory router must never authorize!
      };

      const record = parseRoutingDecision(contradictoryDetails, 'task-102');
      expect(record).not.toBeNull();
      // Must flag the contract inconsistency explicitly
      expect(record?.hasContractInconsistency).toBe(true);
      expect(record?.contractInconsistencyReason).toContain('Inconsistencia de contrato');
      expect(record?.contractInconsistencyReason).toContain('true');
      // Must NEVER confer execution authorization!
      expect(record?.execution_authorized).toBe(false);
      expect(record?.executionAuthorized).toBe(false);
    });

    it('CEO Requirement 5: treats missing or undefined execution_authorized as a contract inconsistency', () => {
      const missingAuth = {
        capability_id: 'cap-review',
        version: '1.0',
        // execution_authorized is omitted!
      };

      const record = parseRoutingDecision(missingAuth, 'task-103');
      expect(record?.hasContractInconsistency).toBe(true);
      expect(record?.execution_authorized).toBe(false);
    });

    it('returns null if raw payload is not an object', () => {
      expect(parseRoutingDecision(null)).toBeNull();
      expect(parseRoutingDecision('invalid')).toBeNull();
    });
  });
});

describe('RONIN F4.9 Integration — UI Components', () => {
  describe('<ModelProfileBadge /> (I3)', () => {
    it('renders declared model profile properties with seats and quality stars', () => {
      render(
        <ModelProfileBadge
          profile={{
            backend: 'claude',
            provider: 'anthropic',
            model: 'claude-3-7-sonnet',
            seats: ['implementer', 'reviewer'],
            quality: { implementer: 5, reviewer: 4 },
            cost_per_attempt_usd: 0.05,
            costPerAttemptUsd: 0.05,
          }}
        />
      );

      expect(screen.getByText(/claude-3-7-sonnet/i)).toBeInTheDocument();
      expect(screen.getByText(/anthropic/i)).toBeInTheDocument();
      expect(screen.getByText(/implementer/i)).toBeInTheDocument();
      expect(screen.getByText(/★5\/5/i)).toBeInTheDocument();
      expect(screen.getByText(/reviewer/i)).toBeInTheDocument();
      expect(screen.getByText(/★4\/5/i)).toBeInTheDocument();
      expect(screen.getByText(/\$0.05 USD/i)).toBeInTheDocument();
    });

    it('distinguishes declared cost 0.00 (free) from unknown cost (no declarado)', () => {
      // 1. Declared free
      const { unmount } = render(
        <ModelProfileBadge
          profile={{
            backend: 'fixture',
            provider: 'synthetic',
            model: null,
            seats: [],
            quality: null,
            cost_per_attempt_usd: 0,
          }}
        />
      );
      expect(screen.getByText(/Declarado gratuito/i)).toBeInTheDocument();
      expect(screen.getByText(/\$0.00 USD/i)).toBeInTheDocument();
      unmount();

      // 2. Unknown cost (null)
      render(
        <ModelProfileBadge
          profile={{
            backend: 'codex',
            provider: 'openai',
            model: 'gpt-4o',
            seats: [],
            quality: null,
            cost_per_attempt_usd: null,
          }}
        />
      );
      expect(screen.getByText(/No declarado \(desconocido\)/i)).toBeInTheDocument();
    });
  });

  describe('<RoutingDecisionCard /> (I4)', () => {
    it('renders routing recommendation card with prominent advisory non-authorizing badge', () => {
      render(
        <RoutingDecisionCard
          decision={{
            work_id: 'task-101',
            capability_id: 'cap-syntax-analyzer',
            capabilityId: 'cap-syntax-analyzer',
            version: '1.0.0',
            capabilityVersion: '1.0.0',
            seat: 'implementer',
            role: 'implementer',
            exclude_providers: [],
            reasons: ['Capacidad preferente de análisis sintáctico.'],
            rejected: [
              { candidate: 'cap-naive-regex:0.1', reason: 'No soporta análisis AST profundo' },
            ],
            activated_backends: ['claude', 'gemini'],
            activatedBackends: ['claude', 'gemini'],
            budget_left_usd: 8.5,
            budgetLeftUsd: 8.5,
            execution_authorized: false,
            executionAuthorized: false,
            created_at: '2026-10-25T15:30:00Z',
            routedAt: '2026-10-25T15:30:00Z',
          }}
        />
      );

      expect(screen.getByText(/Recomendación del Router RONIN/i)).toBeInTheDocument();
      expect(screen.getByText(/EJECUCIÓN NO AUTORIZADA \(CONSULTIVO\)/i)).toBeInTheDocument();
      expect(screen.getByText(/cap-syntax-analyzer@1.0.0/i)).toBeInTheDocument();
      expect(screen.getByText(/cap-naive-regex:0.1/i)).toBeInTheDocument();
      expect(screen.getByText(/No soporta análisis AST profundo/i)).toBeInTheDocument();
      expect(screen.getByText(/\$8.5 USD/i)).toBeInTheDocument();
    });

    it('renders contract inconsistency alert banner when authorization contradiction is present', () => {
      render(
        <RoutingDecisionCard
          decision={{
            work_id: 'task-104',
            capability_id: 'cap-syntax-analyzer',
            version: '1.0.0',
            seat: 'implementer',
            role: 'implementer',
            exclude_providers: [],
            reasons: [],
            rejected: [],
            activated_backends: ['claude'],
            budget_left_usd: 5.0,
            execution_authorized: false,
            executionAuthorized: false,
            hasContractInconsistency: true,
            contractInconsistencyReason: "Inconsistencia de contrato: el payload recibido contiene 'true'",
          }}
        />
      );

      const alertEl = screen.getByRole('alert');
      expect(alertEl).toBeInTheDocument();
      expect(alertEl).toHaveTextContent(/Inconsistencia de Contrato:/i);
      expect(alertEl).toHaveTextContent(/el payload recibido contiene 'true'/i);
    });
  });

  describe('<BudgetOverviewBadge /> (I5)', () => {
    it('renders daily budget left and UTC window concurrency warning', () => {
      render(<BudgetOverviewBadge budgetLeftUsd={4.5} costEstimateUsd={0.05} />);

      expect(screen.getByText(/Ventana UTC/i)).toBeInTheDocument();
      expect(screen.getByText(/\$4.50 USD/i)).toBeInTheDocument();
      expect(screen.getByText(/\$0.05 USD/i)).toBeInTheDocument();
      expect(screen.getByText(/Control presupuestario basado en estimación/i)).toBeInTheDocument();
    });

    it('explicitly states budget is unavailable in board when budgetLeftUsd is null', () => {
      render(<BudgetOverviewBadge budgetLeftUsd={null} costEstimateUsd={0.05} />);

      expect(screen.getByText(/No disponible en tablero \(requiere endpoint RFC\)/i)).toBeInTheDocument();
    });

    it('displays budget exceed blocking alert when isBudgetExceeded is true', () => {
      render(
        <BudgetOverviewBadge
          budgetLeftUsd={0.0}
          costEstimateUsd={0.05}
          isBudgetExceeded={true}
        />
      );

      expect(screen.getByText(/BLOQUEO: budget.exceed/i)).toBeInTheDocument();
      expect(screen.getByText(/Bloqueo Presupuestario/i)).toBeInTheDocument();
    });
  });

  describe('<ExecutionTimeline /> (I2, I5, I6)', () => {
    it('renders timeline with attempt history, model identity and no-progress alert badge', () => {
      const executions: TaskItem['executions'] = [
        {
          id: 'exec-attempt-1',
          status: 'failed',
          worker_id: 'agent-w1',
          attempts: 1,
          created_at: '2026-10-25T10:00:00Z',
          result: {
            provider: 'anthropic',
            model: 'claude-3-5-sonnet',
            cost_estimate_usd: 0.03,
          },
        },
        {
          id: 'exec-attempt-2',
          status: 'failed',
          worker_id: 'agent-w1',
          attempts: 2,
          created_at: '2026-10-25T10:15:00Z',
          result: {
            provider: 'anthropic',
            model: 'claude-3-5-sonnet',
            alert: 'No progress: the last two agent attempts had the same outcome; PM decision required',
            cost_estimate_usd: 0.03,
            check: { tests_passed: 10, tests_failed: 2 },
          },
        },
      ];

      render(<ExecutionTimeline executions={executions} />);

      expect(screen.getByText(/Intento #1/i)).toBeInTheDocument();
      expect(screen.getByText(/Intento #2/i)).toBeInTheDocument();
      expect(screen.getByText(/Detención por falta de progreso \(RONIN I2\)/i)).toBeInTheDocument();
      expect(screen.getByText(/decisión del PM o resolución del CEO/i)).toBeInTheDocument();
    });
  });
});

describe('RONIN F4.9 Integration — Live Adapter Mapping & Grounding', () => {
  it('HttpAaoLiveAdapter.getProjectCapabilities maps modelProfile from backend contract', async () => {
    const rawCapabilities = [
      {
        capability_id: 'cap-backend-test',
        version: '1.0.0',
        capability_type: 'agent_skill',
        status: 'ACTIVE',
        created_at: '2026-10-25T12:00:00Z',
        contract: {
          model_profile: {
            backend: 'claude',
            provider: 'anthropic',
            model: 'claude-3-7-sonnet',
            seats: ['implementer'],
            quality: { implementer: 5 },
            cost_per_attempt_usd: 0.05,
          },
        },
        execution_authorized: false,
      },
    ];

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => rawCapabilities,
    } as Response);

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });
    const result = await adapter.getProjectCapabilities('proj-test');

    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') {
      expect(result.data).toHaveLength(1);
      const cap = result.data[0];
      expect(cap.modelProfile).toBeDefined();
      expect(cap.modelProfile?.backend).toBe('claude');
      expect(cap.modelProfile?.provider).toBe('anthropic');
      expect(cap.modelProfile?.cost_per_attempt_usd).toBe(0.05);
      expect(cap.modelProfile?.seats).toEqual(['implementer']);
      expect(cap.modelProfile?.quality).toEqual({ implementer: 5 });
    }
  });

  it('HttpAaoLiveAdapter.getOrganizationStructure associates RONIN executions with agents without fabricating active execution', async () => {
    const rawProjects = [
      { id: 'proj-1', name: 'Proyecto 1', state: 'ACTIVE' },
    ];

    const rawBoard = [
      {
        id: 'task-1',
        title: 'Tarea RONIN',
        status: 'IN_PROGRESS',
        executions: [
          {
            id: 'exec-1',
            status: 'running',
            worker_id: 'agent-ronin-01',
            attempts: 1,
            created_at: '2026-10-25T11:00:00Z',
            // Notice: lease_expires_at is null or absent!
            result: {
              provider: 'google',
              model: 'gemini-2.5-pro',
              cost_estimate_usd: 0.04,
            },
          },
        ],
      },
    ];

    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes('/v1/organization')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.includes('/v1/principals/me')) {
        return { status: 404, ok: false, json: async () => ({}) } as Response;
      }
      if (u.endsWith('/v1/projects')) {
        return { status: 200, ok: true, json: async () => rawProjects } as Response;
      }
      if (u.includes('/board')) {
        return { status: 200, ok: true, json: async () => rawBoard } as Response;
      }
      return { status: 404, ok: false, json: async () => ({}) } as Response;
    });

    const adapter = new HttpAaoLiveAdapter({ getToken: () => 'test-token' });
    const result = await adapter.getOrganizationStructure();

    expect(result.kind).toBe('ready');
    if (result.kind === 'ready') {
      const agent = result.data.agents.find((a) => a.id === 'agent-ronin-01');
      expect(agent).toBeDefined();

      // Execution history must be populated with observed provider and model
      expect(agent?.executionHistory).toBeDefined();
      expect(agent?.executionHistory?.length).toBeGreaterThan(0);
      expect(agent?.executionHistory?.[0].provider).toBe('google');
      expect(agent?.executionHistory?.[0].model).toBe('gemini-2.5-pro');
      expect(agent?.executionHistory?.[0].costEstimateUsd).toBe(0.04);

      // GROUNDING: Without an active unexpired lease accredited by backend,
      // operationalState MUST NOT be 'EJECUTANDO'!
      expect(agent?.operationalState).not.toBe('EJECUTANDO');
      expect(['REGISTRADO', 'DESCONOCIDO']).toContain(agent?.operationalState);
    }
  });
});
