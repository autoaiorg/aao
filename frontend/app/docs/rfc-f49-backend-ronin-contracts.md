# RFC F4.9: Contratos de Integración RONIN en Frontend (Control Center y Oficina Virtual 3D)

**Identificador:** AAO-RFC-F49-RONIN-2026-10-25  
**Autor:** Antigravity (AGY) — Responsable de Frontend  
**Destinatario:** Claude (Core & Backend), CEO  
**Estado:** Propuesta formal implementada en frontend (`feat/office-ronin-integration`)  
**Dependencias:** PR #113 (I1), PR #116 (I2), PR #119 (I3), PR #121 (I4), PR #123 (I5), PR #124 (I6), PR #122 / #125 (F4.8 veracidad)

---

## 1. Resumen Ejecutivo

La fase F4.9 integra en la interfaz web de AAO (Kanban, Detalle de Proyecto, Estructura Organizativa y Oficina Virtual 3D) los avances inspirados en RONIN desarrollados en el núcleo:
1. **I1 — Identidad del Ejecutor:** Observación explícita de `provider`, `model` y `backend_version` registrados en la ejecución de la tarea.
2. **I2 — Detección de Reintentos sin Progreso:** Detección visual y bloqueo preventivo cuando dos intentos consecutivos arrojan idéntico resultado sin avance (`No progress: the last two agent attempts had the same outcome; PM decision required`).
3. **I3 — Determinante de Modelo:** Representación desacoplada del perfil de modelo declarado en el catálogo (`contract.model_profile`) con diferenciación visual estricta frente al modelo observado en tiempo de ejecución.
4. **I4 — Router de Modelos Consultivo:** Visualización de las recomendaciones generadas por `POST /v1/work/{id}/route-model` y eventos `model.routed`, con exposición de alternativas rechazadas y sus motivos específicos. **Invariante:** Se preserva el distintivo `EJECUCIÓN NO AUTORIZADA (CONSULTIVO)` (`execution_authorized: false`).
5. **I5 — Presupuesto Diario y Estimación por Intento:** Panel de balance presupuestario diario (`AAO_AGENT_DAILY_BUDGET_USD`) en ventana estricta UTC, con alerta preventiva de condiciones de carrera por concurrencia y bloqueo ante exceso de presupuesto (`budget.exceed`).
6. **I6 — Cronología y Trazabilidad de Intentos:** Historial cronológico de ejecuciones en el Kanban, Ficha de Agente y Oficina 3D, correlacionando SHA de candidatos y pruebas.

---

## 2. Contratos Frontend Implementados (Alineados con Backend)

### 2.1. Model Profile (`ModelProfile`) — I3
Ubicación: `frontend/app/src/features/ronin/modelProfile.ts`

```typescript
export interface ModelProfile {
  backend: 'fixture' | 'codex' | string;
  provider: string;
  model: string | null;
  seats: string[]; // Lista de nombres de seats válidos
  quality: Record<string, number> | null; // Mapa seat -> entero 0..5
  cost_per_attempt_usd: number | null; // null si no está declarado; 0 si se declara gratuito
}
```

- **Alineación con el contrato del backend (`src/aao/capability_contracts.py`):**
  - `seats` es estrictamente una lista de cadenas de texto identificadoras (`^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`).
  - `quality` es un mapa donde las claves son nombres de asientos y los valores enteros del `0` al `5`.
  - `cost_per_attempt_usd` diferencia estrictamente un coste declarado `0` (fixture o tarea gratuita) de un coste no suministrado (`null`, desconocido).

### 2.2. Resumen de Ejecución Observada (`RunExecutionSummary`) — I1, I2, I5, I6
```typescript
export interface RunExecutionSummary {
  conclusion?: string;
  candidate_sha?: string;
  check?: string;
  check_details?: CheckSummary | string;
  agent?: string; // "provider · model · backend_version"
  provider?: string | null;
  model?: string | null;
  backend_version?: string | null;
  selection?: string; // "capacidad@versión (elegido por capacidad|entorno) · coste estimado"
  capability_id?: string | null;
  capability_version?: string | null;
  backend_source?: 'capability' | 'environment' | string;
  cost_estimate_usd?: number;
  error?: string;
  alert?: string;
  is_no_progress_retry?: boolean;
  is_budget_exceeded?: boolean;
}
```

### 2.3. Registro Consultivo de Enrutamiento (`ModelRoutingRecord`) — I4
```typescript
export interface ModelRoutingRecord {
  id?: string;
  work_id: string;
  capability_id: string | null;
  version: string | null;
  reasons: string[];
  rejected: Array<{ candidate: string; reason: string }>;
  seat: string;
  role: string;
  exclude_providers: string[];
  activated_backends: string[];
  budget_left_usd: number | null;
  principal_id?: string;
  execution_authorized: false; // Invariante: Nunca true desde el router
  hasContractInconsistency?: boolean;
  contractInconsistencyReason?: string;
  created_at?: string;
}
```

- **Validación de `execution_authorized` (CEO Regla 5):**
  Cualquier respuesta donde `execution_authorized !== false` es detectada explícitamente como una inconsistencia de contrato, marcando `hasContractInconsistency: true` y desplegando una alerta visual de advertencia. La recomendación consultiva **nunca** es interpretada como autorización de ejecución.

---

## 3. Matriz de Disponibilidad de Datos LIVE vs Dependencias RFC

Para evitar declarar como disponibles en vivo datos que no están expuestos actualmente por la API de PostgreSQL, se define la siguiente delimitación:

| Dato RONIN | Endpoint Existente | Disponibilidad LIVE Actual | Estado en Frontend |
|---|---|---|---|
| **Proveedor, modelo y versión CLI ejecutor (I1)** | `GET /v1/projects/{id}/board` (`executions[].result`) | **Disponible** | Totalmente visible en Kanban, Organizativa y Oficina 3D. |
| **Alerta reintento sin progreso (I2)** | `GET /v1/projects/{id}/board` (`executions[].result.alert`) | **Disponible** | Detectado y mostrado con distintivo de detención. |
| **Perfil de modelo declarado (I3)** | `GET /v1/projects/{id}/capabilities` (`contract.model_profile`) | **Disponible** | Mostrado como perfil declarativo en ficha de capacidad. |
| **SHA de candidato y resultado de pruebas (I6)** | `GET /v1/projects/{id}/board` (`executions[].result`) | **Disponible** | Visible en línea temporal cronológica. |
| **Coste estimado por intento ejecutado (I5)** | `GET /v1/projects/{id}/board` (`executions[].result.cost_estimate_usd`) | **Disponible** | Mostrado por intento ejecutado. |
| **Saldo presupuestario diario global del proyecto (I5)** | No expuesto a nivel de proyecto | **Pendiente de RFC (Petición 1)** | El frontend muestra explícitamente "No disponible en tablero (requiere endpoint RFC)" si no se dispone del valor. |
| **Vigencia de lease en ejecuciones (`lease_expires_at`)** | No incluido en `board` de PostgreSQL | **Pendiente de RFC (Petición 2)** | El frontend marca `operationalState: 'DESCONOCIDO'`, fail-closed sin inventar vigencias. |
| **Histórico de decisiones `route-model` por tarea** | En `events` de PostgreSQL pero no en `/board` | **Pendiente de RFC (Petición 3)** | Visible en registro de actividad del proyecto o cuando el núcleo lo vincule. |

---

## 4. Peticiones de Extensión al Backend (Para Claude)

Las siguientes extensiones se definen como dependencia explícita no bloqueante para Claude / Core:

### Petición 1: Endpoint Canónico de Presupuesto
- **Ruta propuesta:** `GET /v1/projects/{project_id}/budget`
- **Permiso requerido:** `project.read`
- **Respuesta esperada:**
  ```json
  {
    "daily_budget_usd": 10.0,
    "budget_left_usd": 7.45,
    "spent_today_usd": 2.55,
    "window": "UTC",
    "is_configured": true,
    "warning": "Concurrencia entre stagings simultáneos sujeta a carrera transaccional"
  }
  ```

### Petición 2: Campo `lease_expires_at` en `GET /v1/projects/{project_id}/board`
- **Motivo:** Para declarar a un agente en estado `EJECUTANDO` en la Oficina Virtual 3D, la política de veracidad LIVE (PR #122 / #125) exige un lease vigente acreditado por el backend (`lease_expires_at > now`).
- **Propuesta:** Incluir el campo `lease_expires_at: string | null` en cada objeto de la lista `executions` dentro del endpoint del tablero de tareas.

### Petición 3: Lista de Decisiones de Enrutamiento por Tarea
- **Ruta propuesta:** `GET /v1/work/{work_id}/routing-decisions`
- **Permiso requerido:** `project.read`
- **Respuesta esperada:** Lista de decisiones registradas en `events` con `kind = 'model.routed'` para dicho `work_id`.

---

## 5. Estado de Verificación en Frontend

- **Compilación estricta TypeScript (`tsc && vite build`):** 0 errores, chunking segregado de Three.js.
- **Suite Vitest (15 archivos, 131 pruebas):** 100% pasando (0 fallos).
- **Suite Playwright (E2E en navegador real):** 6 pruebas superadas (incluyendo aislamiento volátil, teclado, renderizado 3D y planos 2D).
- **Suite Pytest (`tests/test_control_center_ui.py`):** 23 pruebas pasando (0 regresiones).
