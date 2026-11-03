# CEO-DEC-PM-WORK-CREATION-2026-11-03
## Delegación al coordinador PM de la creación de trabajo INBOX en AAO Self Development

**ID:** CEO-DEC-PM-WORK-CREATION-2026-11-03
**Estado:** aceptada por el CEO el 2026-11-03 vía chat.
**Autoridad:** CEO.
**Registra:** Claude (agente constructor, a instancia del coordinador PM).
**Fuente:** conversación de gobierno del 2026-11-03. El coordinador PM preguntó al CEO si el principal PM coordinador podía crear trabajo de Self Development por el endpoint de la PR #355. El CEO respondió literalmente:

> «si»

Los límites de §3 no son texto del CEO. Son los valores por defecto delegados que fijó el coordinador PM en la misma consulta y que el CEO aceptó con esa respuesta.

## 1. Objeto

Se autoriza al principal del coordinador PM (`aao-pm-coordinator-*`) a crear work items en el proyecto AAO Self Development, en estado `INBOX`, por el endpoint acotado `POST /v1/projects/{project_id}/selfdev-cycle-work` que introduce la PR #355. El endpoint lo endurece la PR de correcciones de la auditoría de #355.

## 2. Ámbito

- **Quién:** solo principales `AGENT` con prefijo `aao-pm-coordinator-` que tengan el grant vigente `work.coordinate` sobre el proyecto.
- **Dónde:** solo el proyecto AAO Self Development, y solo si es el único proyecto activo con ese nombre.
- **Qué:** solo la creación de work items `INBOX`, con título, descripción y criterios de aceptación acotados.

## 3. Límites

a. **Solo `INBOX`.** El PM nunca admite, asigna ni ejecuta trabajo por esta vía.
b. **Solo en el proyecto Self Development** cuando es el único activo. En cualquier otro caso el endpoint responde 409.
c. **Tope diario:** 20 work items creados por principal PM en una ventana móvil de 24 h. El endpoint cuenta los eventos `work.selfdev_cycle_requested` del principal en las últimas 24 h y, al superar el tope, responde **429**.
d. **Auditoría:** cada creación queda registrada como evento `work.selfdev_cycle_requested`, con actor, proyecto, clave de idempotencia, hash de la petición y `admitted: false`.
e. **La admisión no se delega aquí, y hoy no existe una puerta independiente.** Esta decisión no delega la admisión. El control real de `POST /v1/work/{id}/admit` (`src/aao/work_management_api.py:4632-4645`) de autorización es solo `require_grant(..., "work.admit")` (más `require_group_work_assignee` y comprobaciones de estado y dependencias, que no son una puerta de revisión). El grant `work.admit` lo incluye `SELFDEV_IMPLEMENTER_GRANTS` (`src/aao/work_management_api.py:888-891`; `docs/procedures/SELF_DEVELOPMENT_CYCLE_ROLES.md:18`), que el PM emite al implementador de cada ciclo. Por tanto, el implementador emitido por el PM puede admitir trabajo. No hay hoy ninguna exigencia de paso del CEO ni de revisión independiente en la admisión. El registro abierto de esa brecha es el issue #367.

## 4. Lo que esta decisión NO autoriza

- No concede `work.create` ni ningún otro grant. Los grants del PM siguen siendo `project.read`, `work.coordinate` y `work.assign` (`docs/procedures/PM_TOKEN_PROVISIONING.md`).
- No habilita `--materialize-routines` ni la ruta AGENT general de creación de trabajo.
- No autoriza admisión, asignación, ejecución, R2, integrador, activación de proveedores ni cambios de raíz de confianza.
- No sustituye la auditoría independiente de la PR #355 ni la de su PR de correcciones (GOV-REV-001). La delegación solo puede ejercerse una vez integradas por la vía autorizada.

## 5. Revocación

El CEO puede revocar la delegación en cualquier momento. Basta con revocar el grant `work.coordinate` del principal PM (o revocar el principal). Sin ese grant, el endpoint deniega con 403.

## 6. Evidencia

- PR #355 (`feat/selfdev-scoped-cycle-intake`, head `5cd9112`): endpoint de solicitud acotada.
- Comentario de auditoría de #355: https://github.com/autoaiorg/aao/pull/355#issuecomment-6603660549
- PR de correcciones de esa auditoría (`fix/355-audit-findings`, #362): añade el tope del límite (c), devuelve el estado real en la repetición idempotente, acota la idempotencia al principal y endurece la entrada y el prompt del worker.

## 7. Documentos conciliados

Se añadió una nota fechada, sin reescribir el texto histórico, en:

- `docs/procedures/PM_TOKEN_PROVISIONING.md`;
- `scripts/provision_pm_coordinator_token.py` (solo comentario; el comportamiento no cambia);
- `docs/research/AGENTS_OFFICE_DIFFERENTIAL.md`.

**Integración:** toca una ruta protegida (`docs/decisions/`). Se fusiona solo por la vía autorizada; no se fusiona por esta PR.
