# Inventario de Contratos API — AAO Control Center (F1-F2)

**Fecha de verificación:** 25 de octubre de 2026  
**SHA verificado en canonical `main`:** `ce6caf08bc47b1c6a3adc698716317b806283494`  
**Referencia de backend:** `src/aao/work_management_api.py`  
**Rol de consumo:** `AGENT` (token individual) y `CEO` (bearer de desarrollo local)  
**Principio de seguridad:** El frontend observa y valida; nunca autoriza ni promueve. Los fallos 403 y rutas no expuestas permanecen estrictamente inaccesibles sin introducir fallbacks privilegiados engañosos.

---

## 1. Matriz de Endpoints Verificados en HEAD

| Método | Ruta | Autorización | Cabecera | Códigos esperados | Estado en esta PR |
|---|---|---|---|---|---|
| `GET` | `/` | Pública | Ninguna | 200 (HTML consola clásica) | Preservado intacto |
| `GET` | `/assets/control-center.css` | Pública | Ninguna | 200 (CSS clásico) | Preservado intacto |
| `GET` | `/assets/control-center.js` | Pública | Ninguna | 200 (JS clásico) | Preservado intacto |
| `GET` | `/health` | Pública | Ninguna | 200 | Consumido en `OperationsView` |
| `GET` | `/ready` | Pública | Ninguna | 200, 503 | Consumido en `OperationsView` |
| `GET` | `/v1/principals/me` | Autenticado | `X-Agent-Token` | 200, 401, 403 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/principals/me/grants` | Autenticado | `X-Agent-Token` | 200, 401, 403 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/projects` | Autenticado | `X-Agent-Token` / `X-CEO-Token` | 200, 401, 403 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/projects/{id}/board` | Autenticado | `X-Agent-Token` / `X-CEO-Token` | 200, 401, 403, 404 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/projects/{id}/capabilities` | Autenticado | `X-Agent-Token` / `X-CEO-Token` | 200, 401, 403, 404, 422 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/projects/{id}/capability-evaluations` | Autenticado | `X-Agent-Token` / `X-CEO-Token` | 200, 401, 403, 404 | Consumido en `HttpAaoLiveAdapter` |
| `GET` | `/v1/projects/{id}/grants` | CEO only | `X-CEO-Token` | 200, 403, 404, 503 | Restringido a CEO local |
| `GET` | `/v1/mandates` | CEO only | `X-CEO-Token` | 200, 403, 503 | Restringido a CEO local |
| `GET` | `/v1/auditors/me/grants` | AUDITOR only | `X-Auditor-Token` | 200, 401, 403 | Excluido de sesión AGENT |
| `GET` | `/v1/work/{w_id}/patch-proposals/{p_id}` | AUDITOR only | `X-Auditor-Token` | 200, 403, 404, 409 | **PROHIBIDO invocar con AGENT** |

---

## 2. Endpoints Ausentes / No Implementados en Backend

Los siguientes recursos NO existen en la API del backend actual. El frontend reporta explícitamente `kind: 'unavailable'` sin simular datos falsos ni mostrar `0` engañosos:

1. **Alertas transversales en tiempo real:** no existe `/v1/alerts`. Se reporta «Sin contrato de alertas en tiempo real expuesto en la API».
2. **Decisiones ejecutivas ejecutables:** no existe `/v1/decisions` ni endpoints de votación/aprobación en frontend. Se reporta en modo consultivo.
3. **Agregación transversal de tareas de todos los proyectos:** `/v1/projects/{id}/board` solo acepta un `project_id`. No existe un endpoint transversal; el dashboard exige seleccionar un proyecto o computa la suma solo sobre los proyectos accesibles.
4. **Historial de actividad:** `/v1/projects/{id}/activity` (mencionado en borradores antiguos) no está expuesto en HEAD.
5. **Agentes asignables:** `/v1/projects/{id}/assignable-agents` no está expuesto en HEAD.
6. **Promociones o firmas constitucionales:** no expuestas en HTTP para frontend.
7. **Estructura Organizativa y Telemetría de Agentes (F3):** no existen actualmente `/v1/organization` ni `/v1/agents` en el backend canónico. `HttpAaoLiveAdapter` devuelve estrictamente `kind: 'unavailable'` sin inventar actividad ni fingir presencia de agentes. El catálogo de unidades y plantilla opera con contratos desacoplados y se expone con fixtures sintéticas en modo DEMO.

---

## 3. Especificación Detallada de Respuestas y Manejo de Errores

### 3.1 `GET /v1/principals/me`
- **Cabecera requerida:** `X-Agent-Token: <token>`
- **Respuesta 200 OK:**
  ```json
  {
    "principal_id": "agent-uuid-or-id",
    "kind": "AGENT",
    "enabled": true
  }
  ```
- **Respuesta 401:** Token ausente o formato rechazado.
- **Respuesta 403:** Credencial revocada o deshabilitada.

### 3.2 `GET /v1/projects`
- **Cabecera requerida:** `X-Agent-Token: <token>` o `X-CEO-Token: <token>`
- **Respuesta 200 OK (con datos):**
  ```json
  [
    {
      "id": "proj-uuid",
      "name": "Nombre de Proyecto",
      "state": "ACTIVE"
    }
  ]
  ```
- **Respuesta 200 OK (vacía):** `[]` -> Mapeado defensivamente a `DataState.kind = 'empty'`.

### 3.3 `GET /v1/projects/{project_id}/board`
- **Cabecera requerida:** `X-Agent-Token: <token>` (requiere grant `project.read`) o `X-CEO-Token: <token>`
- **Respuesta 200 OK:**
  ```json
  [
    {
      "id": "task-uuid",
      "title": "Título de la tarea",
      "status": "IN_REVIEW",
      "acceptance_criteria": ["Criterio 1"],
      "evidence": [],
      "executions": [
        {
          "id": "exec-uuid",
          "status": "completed",
          "worker_id": "agent-uuid",
          "attempts": 1,
          "created_at": "2026-10-25T08:00:00Z"
        }
      ],
      "reviews": [
        {
          "id": "rev-uuid",
          "work_id": "task-uuid",
          "reviewer_id": "auditor-uuid",
          "decision": "APPROVED",
          "candidate_sha": "abc1234...",
          "created_at": "2026-10-25T08:30:00Z"
        }
      ]
    }
  ]
  ```
- **Validación de estados:** Se normaliza a los 6 estados canónicos (`INBOX`, `READY`, `IN_PROGRESS`, `IN_REVIEW`, `VERIFIED`, `DONE`).

### 3.4 `GET /v1/projects/{project_id}/capabilities`
- **Cabecera requerida:** `X-Agent-Token` con grant `project.read` o `X-CEO-Token`
- **Garantía invariable:** `execution_authorized` se fija estrictamente en `false`. Listar capacidades no confiere autorización de ejecución.

### 3.5 `GET /v1/work/{work_id}/patch-proposals/{proposal_id}`
- **Política de consumo:** **ESTRICTAMENTE EXCLUIDO**. Este endpoint requiere rol `AUDITOR`, grant `work.review`, proyecto en estado `ACTIVE`, y tarea en `IN_REVIEW`. Invocarlo con una credencial `AGENT` genera un HTTP 403 intencionado. La UI informa textualmente sobre esta frontera de aislamiento sin intentar la llamada.
