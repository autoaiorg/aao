# RFC-F48: Backend Organizational & Telemetry Contracts

**Document ID:** RFC-AAO-FE-F48-2026-10-25  
**Author:** Antigravity (AGY) — Frontend Engineering  
**Target Recipient:** Claude (Backend Architect & Engineer) / CEO  
**Status:** PROPOSED  
**Related Phases:** F3 (Organization Structure), F4.7 (Visual Evolution), F4.8 (LIVE Organizational Integration)

---

## 1. Context & Motivation

Phase F4 introduced the Virtual 3D Office and Phase F4.7 evolved its spatial design, lighting, contrast, and agent avatars. In Phase F4.8, the frontend requires structured access to operational organization data in **LIVE** mode without fabricating synthetic activity, fake heartbeats, or unauthorized agent profiles.

Currently, `src/aao/work_management_api.py` exposes:
- `GET /v1/projects`
- `GET /v1/projects/{id}/board`
- `GET /v1/projects/{id}/grants`
- `GET /v1/projects/{id}/capabilities`
- `GET /v1/principals/me`

While `HttpAaoLiveAdapter` has implemented progressive fallback aggregation (querying projects, boards, executions, and principal identity to construct live agents and unit metrics), a first-class backend contract is proposed below to reduce frontend round-trips, provide authoritative heartbeat telemetry, and maintain constitutional separation.

---

## 2. Proposed Endpoint Specifications

### 2.1 `GET /v1/organization`

Retrieves the constitutional organizational units and the comprehensive agent roster.

- **Method:** `GET`
- **Path:** `/v1/organization`
- **Headers:**
  - `Accept: application/json`
  - `X-CEO-Token: <token>` OR `X-Agent-Token: <token>`
- **Response Status Codes:**
  - `200 OK`: Organizational structure returned successfully.
  - `401 Unauthorized`: Token invalid, revoked, or expired.
  - `403 Forbidden`: Insufficient privilege to query organization roster.

#### Response Payload Schema (JSON)

```json
{
  "units": [
    {
      "id": "unit-exec",
      "name": "Dirección Ejecutiva y Secretaría General",
      "code": "EXEC",
      "parentId": null,
      "leadRole": "CEO / Presidencia Ejecutiva",
      "leadAgentId": "principal-ceo-1",
      "description": "Coordinación estratégica, reservas de decisión constitucionales y supervisión global de los mandatos.",
      "standingCount": 2,
      "ephemeralCount": 0,
      "activeProjectsCount": 3
    },
    {
      "id": "unit-gov",
      "name": "Gobernanza Constitucional y Políticas",
      "code": "GOV",
      "parentId": "unit-exec",
      "leadRole": "Director de Cumplimiento Normativo",
      "leadAgentId": "principal-gov-lead",
      "description": "Garantía de cumplimiento de mandatos, separación de poderes y validación de políticas de delegación.",
      "standingCount": 2,
      "ephemeralCount": 1,
      "activeProjectsCount": 2
    },
    {
      "id": "unit-audit",
      "name": "Auditoría Independiente y Verificación",
      "code": "AUDIT",
      "parentId": "unit-exec",
      "leadRole": "Auditor Principal de Seguridad",
      "leadAgentId": "principal-audit-lead",
      "description": "Verificación adversarial independiente de parches, atestación criptográfica y control de promociones.",
      "standingCount": 2,
      "ephemeralCount": 1,
      "activeProjectsCount": 3
    },
    {
      "id": "unit-arch",
      "name": "Arquitectura de Sistemas y Protocolos",
      "code": "ARCH",
      "parentId": "unit-exec",
      "leadRole": "Arquitecto Jefe de Sistemas",
      "leadAgentId": "principal-arch-chief",
      "description": "Diseño de especificaciones, protocolos de consenso, contratos tipados y topología de servicios.",
      "standingCount": 3,
      "ephemeralCount": 1,
      "activeProjectsCount": 3
    },
    {
      "id": "unit-eng",
      "name": "Ingeniería de Software e Implementación",
      "code": "ENG",
      "parentId": "unit-arch",
      "leadRole": "Director de Implementación Técnica",
      "leadAgentId": "principal-eng-director",
      "description": "Desarrollo de módulos del núcleo, interfaces de usuario, librerías de cliente y pipelines de entrega.",
      "standingCount": 4,
      "ephemeralCount": 3,
      "activeProjectsCount": 3
    },
    {
      "id": "unit-ops",
      "name": "Operaciones de Infraestructura y Resiliencia",
      "code": "OPS",
      "parentId": "unit-exec",
      "leadRole": "Responsable de Operaciones y Nodos",
      "leadAgentId": "principal-ops-sentinel",
      "description": "Monitorización de servicios, balanceo de carga, telemetría de agentes y planes de contingencia.",
      "standingCount": 2,
      "ephemeralCount": 1,
      "activeProjectsCount": 2
    }
  ],
  "agents": [
    {
      "id": "agent-codex-1",
      "name": "Codex Core Specialist",
      "type": "STANDING",
      "roleTitle": "Especialista en Implementación Backend",
      "unitId": "unit-eng",
      "unitName": "Ingeniería de Software e Implementación",
      "capabilities": [
        {
          "id": "cap-py-engine",
          "name": "Desarrollo Python/PostgreSQL en src/aao",
          "level": "CERTIFIED",
          "verified": true
        }
      ],
      "heartbeatStatus": "HEALTHY",
      "lastHeartbeatAt": "2026-10-25T17:45:00Z",
      "status": "BUSY",
      "operationalState": "EJECUTANDO",
      "currentAssignments": [
        {
          "id": "asg-task-99",
          "projectId": "proj-core-aao",
          "projectName": "AAO Core Engine",
          "taskId": "task-core-db-1",
          "taskTitle": "Concurrency lease lock implementation",
          "assignedAt": "2026-10-25T16:00:00Z",
          "leaseExpiresAt": "2026-10-25T18:00:00Z",
          "status": "ACTIVE"
        }
      ],
      "authorityBoundary": "Limitado a src/aao/ y tests/. Sin autoridad de fusión ni auto-certificación.",
      "isSyntheticDemo": false,
      "lastEvidenceAt": "2026-10-25T17:45:00Z",
      "evidenceDescription": "Ejecución activa en tarea task-core-db-1."
    }
  ],
  "totalStandingAgents": 1,
  "totalEphemeralAgents": 0,
  "activeAssignmentsCount": 1
}
```

---

### 2.2 `GET /v1/agents/{id}/telemetry`

Retrieves real-time heartbeat and lease telemetry for a specific agent.

- **Method:** `GET`
- **Path:** `/v1/agents/{id}/telemetry`
- **Headers:**
  - `Accept: application/json`
  - `X-CEO-Token: <token>` OR `X-Agent-Token: <token>`
- **Response Status Codes:**
  - `200 OK`: Telemetry record returned.
  - `404 Not Found`: Agent identifier does not exist or has no recorded telemetry.

#### Response Payload Schema (JSON)

```json
{
  "agent_id": "agent-codex-1",
  "heartbeat_status": "HEALTHY",
  "last_heartbeat_at": "2026-10-25T17:45:00Z",
  "lease_window_seconds": 60,
  "lease_expires_at": "2026-10-25T17:46:00Z",
  "worker_host": "node-worker-eu-west-1",
  "cli_version": "0.14.2",
  "operational_state": "EJECUTANDO",
  "current_task_id": "task-core-db-1"
}
```

---

### 2.3 `GET /v1/agents/{id}`

Retrieves the individual agent profile, capabilities, and active assignments.

- **Method:** `GET`
- **Path:** `/v1/agents/{id}`
- **Headers:**
  - `Accept: application/json`
  - `X-CEO-Token: <token>` OR `X-Agent-Token: <token>`

---

---

### 2.4 `GET /v1/projects/{project_id}/board` (Execution Lease Field Addition)

To enable client verification of active execution vigency without relying on heuristic time windows (`created_at`), the execution records returned in the board endpoint should include `lease_expires_at`:

- **Path:** `/v1/projects/{project_id}/board`
- **Current `execution_queue` JSON aggregation:**
  ```sql
  json_build_object(
    'id', q.id,
    'status', q.status,
    'worker_id', q.worker_id,
    'attempts', q.attempts,
    'created_at', q.created_at,
    'result', q.result_json
  )
  ```
- **Proposed addition:**
  ```sql
  json_build_object(
    'id', q.id,
    'status', q.status,
    'worker_id', q.worker_id,
    'attempts', q.attempts,
    'created_at', q.created_at,
    'lease_expires_at', q.lease_expires_at,
    'result', q.result_json
  )
  ```
With `lease_expires_at` present, the frontend evaluates vigency as:
- `status === 'RUNNING'` AND `lease_expires_at > clock_timestamp()` => `EJECUTANDO` (Lease vigente).
- `status === 'RUNNING'` AND `lease_expires_at <= clock_timestamp()` => `EXPIRED` (Arrendamiento expirado).
- `status === 'RUNNING'` AND `lease_expires_at == null` => `DESCONOCIDO` (Vigencia desconocida: backend no acredita lease).

---

### 2.5 Separation of Permissions (`grants`) from Technical Capabilities

AAO distinguishes:
1. **Concesiones / Permisos (`grants`):** Registrados en `/v1/principals/me/grants` o `/v1/projects/{id}/grants`. Representan autorización por proyecto (`project.read`, `work.claim`, etc.). **Nunca deben ser homologados a capacidades técnicas certificadas**.
2. **Capacidades Declaradas:** Entradas del catálogo de capacidades que el agente o su entorno reportan.
3. **Capacidades Certificadas:** Habilidades o contratos tipados formalmente auditados y atestados por una revisión independiente de seguridad.

---

## 3. Frontend Adapter Compatibility (Fail-Closed & Verifiable Evidence)

In `HttpAaoLiveAdapter.ts`, the frontend enforces strict factual grounding:

1. **Direct Request:** First attempts `GET /v1/organization`. If supported and returning `200 OK`, it parses and validates via `OrganizationStructureSchema`.
2. **Graceful Fallback:** If `GET /v1/organization` returns 404 (not yet implemented in backend), the frontend does NOT crash or invent fake agents. It aggregates active workers, tasks in progress, and registered principals from:
   - `GET /v1/projects`
   - `GET /v1/projects/{id}/board`
   - `GET /v1/principals/me`
3. **No Department or Type Heuristics:** The frontend never infers departments or types (`STANDING`/`EPHEMERAL`) from substrings in `worker_id` or from authenticated roles (`CEO`/`AUDITOR`). Unassigned workers and authenticated principals without canonical unit placement are explicitly attributed to `«Departamento desconocido»` (`unit-unassigned`), and their type is set to `UNKNOWN`.
4. **Execution Vigency Strictly Verified (No 5-Minute Window):** The frontend strictly refuses to treat `created_at` and an arbitrary 5-minute fixed window as proof of active execution. Demonstrable active execution requires both `status === 'RUNNING'` and a valid, future `lease_expires_at` accredited by the backend. Without an unexpired lease, execution vigency is represented as `DESCONOCIDO` (`UNKNOWN`).
5. **No Synthetic Capabilities from Grants or Reviews:**
   - Concesiones de proyecto (`grants`) se presentan como permisos de proyecto, jamás como capacidades `CERTIFIED`.
   - Revisiones de tareas registradas se tratan puramente como eventos de auditoría.
6. **No Fabricated Evidence Timestamps:** `fetchedAt` (client query time) is strictly distinguished from `lastEvidenceAt` (backend event timestamp). If no backend evidence timestamp exists, `lastEvidenceAt` is `null`.
7. **Complete Project Coverage:** All projects are inspected without silent truncation limits; any failed queries are explicitly reported in `coverage.failedProjects` and `coverage.isPartial`.

---

## 4. Acceptance Criteria for Backend Implementation

1. **Constitutional Units:** Endpoints must maintain the canonical AAO units (`EXEC`, `GOV`, `AUDIT`, `ARCH`, `ENG`, `OPS`) and provide explicit departmental mapping for registered principals.
2. **Authority & Separation:** Telemetry and organization queries must be read-only without state mutation privileges.
3. **Verifiable Leases:** Only agents with currently active, unexpired PostgreSQL worker leases (`lease_expires_at > now`) may be reported with `heartbeat_status: "HEALTHY"` and `operational_state: "EJECUTANDO"`.
4. **Distinction of Grants vs Capabilities:** Audit reviews on tasks must remain recorded as activity events; project permissions (`grants`) must remain separate from technical capability matrices.
