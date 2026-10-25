/**
 * Synthetic Demo Fixtures
 * Strictly synthetic mock data for demonstration and offline UI preview.
 * Contains NO genuine SHAs, credentials, or actual organization data.
 */

import type {
  ProjectSummary,
  ProjectBoard,
  CapabilitySummary,
  EvaluationSummary,
  PrincipalSummary,
  CeoOverview,
  WorkSummary,
  GovernanceSummary,
  OperationsSummary,
  AlertSummary,
  DecisionSummary,
} from '../../../domain/models';

export const DEMO_PROJECTS: ProjectSummary[] = [
  {
    id: 'demo-proj-orion',
    name: 'Proyecto Orión (Demo)',
    description: 'Espacio de simulación de infraestructura cognitiva descentralizada',
    status: 'ACTIVE',
    taskCounts: {
      INBOX: 2,
      READY: 3,
      IN_PROGRESS: 4,
      IN_REVIEW: 2,
      VERIFIED: 1,
      DONE: 6,
    },
  },
  {
    id: 'demo-proj-polaris',
    name: 'Proyecto Polaris (Demo)',
    description: 'Protocolo de sincronización y resiliencia de servicios',
    status: 'ACTIVE',
    taskCounts: {
      INBOX: 1,
      READY: 1,
      IN_PROGRESS: 2,
      IN_REVIEW: 1,
      VERIFIED: 0,
      DONE: 3,
    },
  },
  {
    id: 'demo-proj-saturn',
    name: 'Proyecto Saturno (Demo)',
    description: 'Sandbox de aislamiento para pruebas adversariales sintéticas',
    status: 'PLANNING',
    taskCounts: {
      INBOX: 4,
      READY: 0,
      IN_PROGRESS: 0,
      IN_REVIEW: 0,
      VERIFIED: 0,
      DONE: 0,
    },
  },
];

export const DEMO_PRINCIPAL: PrincipalSummary = {
  principal_id: 'demo-agent-simulated-01',
  kind: 'AGENT',
  enabled: true,
  grants: [
    { project_id: 'demo-proj-orion', capability: 'project.read', expires_at: null, active: true },
    { project_id: 'demo-proj-polaris', capability: 'project.read', expires_at: null, active: true },
  ],
};

export const DEMO_BOARD_ORION: ProjectBoard = {
  projectId: 'demo-proj-orion',
  projectName: 'Proyecto Orión (Demo)',
  totalCount: 18,
  stages: {
    INBOX: [
      {
        id: 'demo-task-001',
        title: 'Definir especificación de agregación de métricas de telemetría',
        status: 'INBOX',
        acceptanceCriteria: ['Validar esquema de eventos', 'Diseñar contratos de ingestión'],
        evidence: [],
      },
      {
        id: 'demo-task-002',
        title: 'Explorar compresión de registros para auditoría diferida',
        status: 'INBOX',
        acceptanceCriteria: ['Evaluar zstandard', 'Documentar latencias'],
        evidence: [],
      },
    ],
    READY: [
      {
        id: 'demo-task-003',
        title: 'Implementar parser para validación estricta de payloads',
        status: 'READY',
        acceptanceCriteria: ['Zod schema compilado', 'Pruebas unitarias de límites'],
        evidence: [],
      },
      {
        id: 'demo-task-004',
        title: 'Crear suite de pruebas de concurrencia en aislamiento',
        status: 'READY',
        acceptanceCriteria: ['Simulación con 10 hilos', 'Detección de bloqueos mutuos'],
        evidence: [],
      },
      {
        id: 'demo-task-005',
        title: 'Diseñar interfaz accesible para tabla de capacidades',
        status: 'READY',
        acceptanceCriteria: ['Soporte ARIA completo', 'Navegación por teclado'],
        evidence: [],
      },
    ],
    IN_PROGRESS: [
      {
        id: 'demo-task-006',
        title: 'Refactorizar capa cliente de eventos de streaming',
        status: 'IN_PROGRESS',
        acceptanceCriteria: ['Manejo de desconexión', 'Backoff exponencial'],
        executions: [
          {
            id: 'exec-demo-01',
            status: 'running',
            worker_id: 'demo-agent-simulated-01',
            attempts: 1,
            created_at: '2026-10-25T08:30:00Z',
          },
        ],
      },
      {
        id: 'demo-task-007',
        title: 'Configurar variables CSS y tokens de contraste WCAG AA',
        status: 'IN_PROGRESS',
        acceptanceCriteria: ['Contraste >= 4.5:1', 'Tokens semánticos'],
        executions: [
          {
            id: 'exec-demo-02',
            status: 'running',
            worker_id: 'demo-agent-simulated-02',
            attempts: 1,
            created_at: '2026-10-25T08:45:00Z',
          },
        ],
      },
      {
        id: 'demo-task-008',
        title: 'Integrar adaptadores segregados demo y live',
        status: 'IN_PROGRESS',
        acceptanceCriteria: ['Segregación de cachés', 'Banner permanente en modo demo'],
        executions: [
          {
            id: 'exec-demo-03',
            status: 'running',
            worker_id: 'demo-agent-simulated-01',
            attempts: 1,
            created_at: '2026-10-25T09:00:00Z',
          },
        ],
      },
      {
        id: 'demo-task-009',
        title: 'Diseñar arquitectura de fallback 2D para oficina virtual',
        status: 'IN_PROGRESS',
        acceptanceCriteria: ['ADR publicado', 'Renderizado sin WebGL validado'],
      },
    ],
    IN_REVIEW: [
      {
        id: 'demo-task-010',
        title: 'Verificación de integridad de tokens volátiles en memoria',
        status: 'IN_REVIEW',
        acceptanceCriteria: ['Sin almacenamiento en localStorage ni cookies', 'Limpieza en logout'],
        reviews: [
          {
            id: 'rev-demo-01',
            work_id: 'demo-task-010',
            reviewer_id: 'demo-auditor-simulated',
            decision: 'PENDING',
            created_at: '2026-10-25T07:15:00Z',
          },
        ],
      },
      {
        id: 'demo-task-011',
        title: 'Contrato de solo lectura para endpoints de inspección',
        status: 'IN_REVIEW',
        acceptanceCriteria: ['GET exclusivo', 'Sin mutación de estado'],
        reviews: [
          {
            id: 'rev-demo-02',
            work_id: 'demo-task-011',
            reviewer_id: 'demo-auditor-simulated',
            decision: 'PENDING',
            created_at: '2026-10-25T07:45:00Z',
          },
        ],
      },
    ],
    VERIFIED: [
      {
        id: 'demo-task-012',
        title: 'Aislamiento de sesiones y prevención de transposición de proyectos',
        status: 'VERIFIED',
        acceptanceCriteria: ['Validación estricta por project_id', 'Test E2E superado'],
        evidence: [
          {
            type: 'demo_test_run',
            summary: 'Verificación sintética de aislamiento completada',
            passed: true,
          },
        ],
      },
    ],
    DONE: [
      {
        id: 'demo-task-013',
        title: 'Definir modelo de datos tipado y tipos discriminados',
        status: 'DONE',
        acceptanceCriteria: ['DataState union type', 'Confidence y Availability enums'],
      },
      {
        id: 'demo-task-014',
        title: 'Estructurar árbol de carpetas frontend/app con Vite y React',
        status: 'DONE',
      },
      {
        id: 'demo-task-015',
        title: 'Preservar interfaz heredada y tests existentes de control center',
        status: 'DONE',
      },
      {
        id: 'demo-task-016',
        title: 'Diseñar paleta cromática sobria y tipografía legible del sistema',
        status: 'DONE',
      },
      {
        id: 'demo-task-017',
        title: 'Crear componentes base de navegación y cabecera de contexto',
        status: 'DONE',
      },
      {
        id: 'demo-task-018',
        title: 'Configurar entorno de pruebas con Vitest y Testing Library',
        status: 'DONE',
      },
    ],
  },
  items: [],
};

// Flatten items list for quick lookup
DEMO_BOARD_ORION.items = Object.values(DEMO_BOARD_ORION.stages).flat();

export const DEMO_CAPABILITIES_ORION: CapabilitySummary[] = [
  {
    capability_id: 'demo-skill-code-analysis',
    version: '1.0.0-demo',
    capability_type: 'agent_skill',
    status: 'ACTIVE',
    provenance: { source: 'demo-fixtures', repo: 'synthetic' },
    contract: { inputs: ['source_code'], outputs: ['ast_report'] },
    required_permissions: ['project.read'],
    risks: ['Uso moderado de CPU'],
    dependencies: [],
    tests: ['test_syntax_parser.py'],
    compatibility: ['python>=3.12'],
    created_at: '2026-10-24T12:00:00Z',
    execution_authorized: false,
  },
  {
    capability_id: 'demo-script-doc-generator',
    version: '0.9.1-demo',
    capability_type: 'cli_script',
    status: 'DRAFT',
    provenance: { source: 'demo-fixtures', repo: 'synthetic' },
    contract: { inputs: ['markdown_files'], outputs: ['pdf_manifest'] },
    required_permissions: ['project.read'],
    risks: ['Escritura local en directorio temporal'],
    dependencies: [],
    tests: ['test_docgen.py'],
    compatibility: ['node>=20'],
    created_at: '2026-10-24T14:30:00Z',
    execution_authorized: false,
  },
];

export const DEMO_EVALUATIONS_ORION: EvaluationSummary[] = [
  {
    task_id: 'demo-task-012',
    task_title: 'Aislamiento de sesiones y prevención de transposición de proyectos',
    details: {
      result: 'APROBADO_SIMULADO',
      checks: ['Sin fugas de tokens', 'Aislamiento entre tenants sintéticos'],
    },
    created_at: '2026-10-25T08:10:00Z',
  },
];

export const DEMO_ALERTS: AlertSummary[] = [
  {
    id: 'demo-alert-01',
    title: 'Aviso consultivo: 2 tareas en revisión requieren dictamen de auditor',
    severity: 'medium',
    source: 'tablero-sintético',
    confidence: 'reported',
    timestamp: '2026-10-25T08:00:00Z',
    description: 'Las propuestas de patch asociadas a las tareas demo-task-010 y demo-task-011 esperan asignación de auditoría independiente.',
  },
  {
    id: 'demo-alert-02',
    title: 'Informativo: Capacidad demo-script-doc-generator en estado borrador',
    severity: 'low',
    source: 'catálogo-capacidades',
    confidence: 'reported',
    timestamp: '2026-10-25T07:30:00Z',
    description: 'El script de documentación no dispone de pruebas de regresión completas.',
  },
];

export const DEMO_DECISIONS: DecisionSummary[] = [
  {
    id: 'demo-dec-01',
    title: 'Aprobación de alcance F1+F2 para Centro de Mando del CEO',
    category: 'ceo_pending',
    subjectId: 'demo-mandate-fe-01',
    proposedBy: 'Antigravity (Asistente de Desarrollo)',
    createdAt: '2026-10-25T09:00:00Z',
    description: 'El CEO revisará la entrega técnica de frontend en worktree independiente.',
  },
  {
    id: 'demo-dec-02',
    title: 'Validación de aislamiento de roles de base de datos en PostgreSQL',
    category: 'auditor_pending',
    subjectId: 'demo-task-010',
    proposedBy: 'Sistema de pruebas sintético',
    createdAt: '2026-10-25T08:20:00Z',
    description: 'Requiere verificación independiente de permisos por esquema antes de promoción.',
  },
];

export const DEMO_WORK_SUMMARY: WorkSummary = {
  totalTasks: 18,
  byStage: {
    INBOX: 2,
    READY: 3,
    IN_PROGRESS: 4,
    IN_REVIEW: 2,
    VERIFIED: 1,
    DONE: 6,
  },
  activeWorkersCount: 3,
  inReviewCount: 2,
  blockedCount: 0,
};

export const DEMO_GOVERNANCE_SUMMARY: GovernanceSummary = {
  certified: false,
  classification: {
    rLevel: 'R1',
    assuranceLevel: 'B',
  },
  pendingReviewsCount: 2,
  notes: 'Entorno de demostración sintética. Los estados simulados NO certifican conformidad en producción.',
};

export const DEMO_OPERATIONS_SUMMARY: OperationsSummary = {
  serviceHealth: 'healthy',
  readyStatus: true,
  checkedAt: new Date().toISOString(),
  message: 'Modo demostración activo. Todos los subsistemas son simulaciones locales.',
};

export const DEMO_CEO_OVERVIEW: CeoOverview = {
  projects: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_PROJECTS,
    fetchedAt: new Date().toISOString(),
  },
  work: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_WORK_SUMMARY,
    fetchedAt: new Date().toISOString(),
  },
  governance: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_GOVERNANCE_SUMMARY,
    fetchedAt: new Date().toISOString(),
  },
  operations: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_OPERATIONS_SUMMARY,
    fetchedAt: new Date().toISOString(),
  },
  alerts: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_ALERTS,
    fetchedAt: new Date().toISOString(),
  },
  decisions: {
    kind: 'ready',
    origin: 'demo',
    data: DEMO_DECISIONS,
    fetchedAt: new Date().toISOString(),
  },
};
