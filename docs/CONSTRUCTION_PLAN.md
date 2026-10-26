# Plan de construcción de AAO (CEO-DEC-AAO-CONSTRUCTION-2026-10-25 + Adenda 1)

**Objetivo:** cumplir el criterio de éxito de [`CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md`](CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md). Un cambio pequeño, real y útil a AAO tiene que recorrer este camino, y el Control Center tiene que mostrarlo con el estado real del backend:

`AAO → proyecto → objetivo → tarea → agente ejecutor → ejecución acotada → tests → auditoría independiente → PR → resultado`

**Régimen:**
- Claude, Codex y Antigravity trabajan como equipo constructor externo.
- Las PR ordinarias pueden fusionarse bajo el régimen de construcción vigente cuando la CI completa esté verde. Una PR que contenga decisiones reservadas al CEO no se fusiona solo por tener CI verde.
- Los controles de calidad son proporcionados: CI completo (compileall, ruff, pytest `-W error`) y una revisión de segunda línea en los cambios delicados.
- Cada PR declara la fase y gate del modelo operativo al que contribuye.
- No se ejecuta ahora el paquete de certificación ni se congela candidato. La evaluación de traspaso se hace una sola vez al final sobre el candidato.

## Estado de cada tramo (inventario del 2026-10-25, actualizado con W1 #100 y W2a)

| Tramo | Estado | Dónde |
|---|---|---|
| Mandato, proyecto y objetivo | **Existe** | `POST/GET /v1/mandates`, `/v1/projects`, `confirm`, `state` |
| Tarea (work) | **Existe** | `POST /v1/projects/{id}/work`, `admit`, `progress` |
| Agente ejecutor (la tarea produce un parche) | **Existe** (W1, #100). Backend `fixture` probado de extremo a extremo. Backend `codex` ejercitado en el piloto autorizado (`gpt-6-luna`, tarea DONE, PR #114: [registro](construction-runs/20261025-codex-pilot.md)); sigue desactivado para la ejecución general | `agent_runner.py`, `inert_execution_worker.py`, `stage-agent-run` |
| Ejecución acotada y tests | **Existe** (W2a). La misma ejecución confirma el parche como commit candidato con identidad fija, lo guarda en `refs/aao/candidates/<sha>` de un repositorio bare y corre `core-unit` más los tests que añade el parche en sandbox bwrap. Una tarea con un intento fallido puede relanzarse | `agent_runner.py`, `sandboxed_repository_checks.py`, migración 014 |
| Propuesta de parche y validación | **Existe** | `patch-proposals`, `validate`, `patch_proposals.py` |
| Auditoría independiente | **Existe** en dos piezas: reviews en la API y el servicio de auditoría de manifiestos. Desde W2a, la API acepta APPROVE del auditor sobre el SHA candidato probado (tarea → VERIFIED). VERIFIED → DONE sigue bloqueado hasta W3 | `reviews`, `review.py`, `independent_audit.py`, `manifest_audit.py`, `auditor_dispatch.py` |
| De la propuesta aprobada a la PR | **Existe con clientes inyectables** (W2b). En dos pasos, uno por identidad (las claves de cada App solo las lee su uid): `--step push` (implementador, re-verifica en el almacén que el commit es base + parche de la propuesta aprobada y empuja exactamente ese SHA) y `--step open` (PM, abre la PR). Ambos requieren `code.publish` y no pueden ser el autor; quedan `work.candidate_pushed` y `work.pr_opened` en el tablero. Probado con remoto bare y apertura falsa. La vía real (Apps `aao-impl-*` → fork, `aao-pm` → PR) está escrita pero **sin ejercitar**: necesita ejecutar como el uid que custodia las claves | `pr_publisher.py`, `scripts/publish_candidate.py` |
| De la PR a `main` (R1) | **Existe**, pero desactivado hasta el traspaso | `r1_pipeline.py`, `integrator.py` |
| Resultado de la tarea (W3) | **Existe.** `publish_candidate.py --step reconcile` pasa la tarea a DONE solo si su PR está fusionada y su cabeza sigue siendo el SHA aprobado; registra `work.completed` con el `merge_commit_sha`. `GET /v1/projects/{id}/activity` da la actividad del proyecto | `pr_publisher.reconcile`, `activity` |
| Resultado visible en el Control Center | **Integrado con el backend real** (app React de `frontend/app`, #99/#105 + esta PR): el tablero muestra los intentos con su candidato y su check, y las PR publicadas; el detalle de proyecto tiene la pestaña *Actividad* (`/v1/projects/{id}/activity`). En modo demo, la actividad aparece como no disponible, sin datos inventados | `frontend/app/src` |

## Frentes de trabajo, por prioridad

| # | Frente | Responsable | Entregable |
|---|---|---|---|
| W1 | **Agente ejecutor.** Un worker toma una tarea admitida, ejecuta un agente (Codex/Claude) en sandbox sobre un clon en el SHA base, registra un parche como propuesta y registra la ejecución | Codex (backend) y Claude (sandbox y diseño) | Una tarea genera una propuesta real, con evidencia en la cola |
| W2 | **De la propuesta a la PR.** Con la propuesta aprobada, commit y push al fork del implementador con su App, y servicio `aao-pm` que abre la PR fork → canónico. Es el paso 2 de [E2E_PR_PIPELINE](E2E_PR_PIPELINE.md) | Codex (backend) y Claude (scripts y unidades) | PR abierta por `aao-pm[bot]` desde una propuesta, enlazada a la tarea |
| W3 | **Resultado y trazabilidad.** El estado de la PR (checks, auditoría y fusión) vuelve a la tarea, y endpoint de actividad | Codex | La tarea pasa a DONE con enlace a la PR y al SHA final |
| W4 | **Control Center.** Integrar la rama pendiente de Antigravity rebasada sobre #20, añadir la vista de actividad y la vista de la PR/resultado desde el estado real | Antigravity; Codex o Claude mientras Antigravity no tenga cuota (hasta el ~30-10) | Recorrido completo visible en la web |
| W5 | **Demostración E2E.** Un cambio real pequeño a AAO por todo el camino | Claude (coordinación) | Evidencia para el criterio 9 del traspaso |

**Única decisión estratégica prevista:** para que W1 y W5 ejecuten un modelo real dentro de AAO hay que activar un proveedor de modelos, con su coste y sus credenciales. El mandato lo reserva al CEO («model/provider activation»). Se le planteará cuando W1 esté listo, sin bloquear su construcción.

## Alcance vigente tras la Adenda 1 (2026-10-26)

La tabla de tramos anterior es un inventario histórico del camino técnico; no amplía el alcance autorizado ni sustituye los estados actuales de [`HANDOVER_ACCEPTANCE_MATRIX.md`](HANDOVER_ACCEPTANCE_MATRIX.md).

- **Construcción externa:** completar la Fase 0; de las fases 1–4 construir solo lo mínimo para ejecutar el piloto §14 del [modelo operativo adoptado](architecture/AAO_ENTERPRISE_OPERATING_MODEL.md): organización piloto (Producto/Planificación, Ingeniería y Calidad, manteniendo Seguridad y Auditoría independientes), cinco protocolos mínimos, colaboración entre unidades y trazabilidad de extremo a extremo.
- **Fase 0 incluye:** protección/autorización efectivas, evidencias reproducibles, identidades separadas, fail-closed y ciclo R1 demostrado o bloqueo explícitamente mantenido. Los pendientes operativos de host se resuelven con las identidades competentes; el constructor no suplanta esas cuentas.
- **Fases 1–4:** no extender a toda la empresa ni construir un motor genérico de workflows. Los protocolos reutilizan trabajo, cola, eventos y journal; fijan versión por instancia y nunca conceden autoridad. Preservar organización, grants y núcleo de confianza ya existentes.
- **Después del traspaso:** AAO completa el resto de fases bajo su propio gobierno.
- **Independencia:** Codex no audita independientemente el candidato que construya. La revisión independiente final queda a cargo de Antigravity u otra persona no constructora.
- **Ensayo R1:** solo dentro del ensayo de aceptación del piloto y con la autorización requerida; el integrador permanece OFF antes de ello.

La certificación y los gates E-1/E-2 se evalúan al cierre sobre una única revisión candidata. No son una razón para detener cambios de construcción ordinarios ni para congelar un candidato antes de tiempo.

### Incrementos en curso bajo este alcance

- **Fase 0 / evidencias de identidad y protección:** B-2 tiene código de recibos durables fusionado en PR #253, pero falta despliegue operativo y recepción firmada real. W2 permanece pendiente del ejercicio CEO con las GitHub Apps bajo sus cuentas. La comprobación de rulesets sigue devolviendo cero; la protección corresponde al owner.
- **Fases 1–4 / construcción mínima del piloto:** `docs/proposals/MINIMUM_PROTOCOLS_PILOT_SPEC.md` documenta los contratos, límites de autoridad y brechas. Los pins iniciales y varios comportamientos de los cinco protocolos ya están fusionados; no constituyen por sí solos protocolos operativos completos. La prioridad persistente `NORMAL`/`HIGH`, CEO-only, se implementó en PR #281 (`d867254ff145c434199f18e971788aca9ac5a1eb`); PR #282 conectó la Oficina Kanban al endpoint y proyección existentes (merge `3313bbb092a029f161b843b38c61c50632ffde4a`, CI post-merge run `40369565637`, `test`/`frontend` SUCCESS). Backend/PostgreSQL sigue siendo la fuente de verdad.
- **Coordinación incremental del PM:** PR #297 añade `scripts/run_project_coordinator.py`, un runner one-shot/`--watch` que consulta grupos confirmados con `work.coordinate` y asigna hijos `INBOX` sin responsable usando el endpoint existente y el grant distinto `work.assign`. El incremento en curso añade `--auto-consolidate` optativo para registrar un índice factual de resultados persistidos cuando todos los hijos están `DONE`; no usa modelo, no acepta el grupo, y la API mantiene idempotencia, revalida el snapshot e impide consolidación de trabajo propio. [`PROJECT_COORDINATOR_OPERATIONS.md`](procedures/PROJECT_COORDINATOR_OPERATIONS.md) documenta el modo acotado y sus precondiciones. No instala ni arranca una cuenta/servicio, no crea/confirma grupos, no admite ni despacha ni reintenta; no concede autoridad. Aporta automatización incremental a Fase 2 `planning-assignment` y Fase 4 §14, pero no satisface por sí solo la coordinación PM autónoma ni E-2.
- **Siguiente secuencia:** RST-6 ya cubre redelivery concurrente de creación, consolidación y turnos conversacionales, además de correlacionar sus desenlaces por la misma clave idempotente durante fallo, reintento y recuperación backend. RST-7 ya cubre publicación fail-closed antes de efectos externos (#287) y esta construcción extiende esa garantía hasta la reconciliación/cierre, verificando que la PR siga ligada a la revisión aprobada y a la ejecución persistida del mismo SHA. Luego continuar con brechas concretas de los cinco protocolos, incluido el seguimiento operativo del PM con grants existentes, y preparar las pruebas integradas del piloto §14 según el plan remitido al CEO. No habilitar proveedor, R1 ni nuevas facultades por este trabajo.

## Operación real (2026-10-25)

El ciclo se ha ejecutado en la instancia de desarrollo con estado persistente: [`construction-runs/20261025-self-development-cycle.md`](construction-runs/20261025-self-development-cycle.md). Una tarea real produjo las PR #104 (cerrada: la CI falló y la tarea volvió a IN_PROGRESS) y #106 (tercer intento). La tarea llegó a DONE tras fusionarse #106. El piloto de Codex se ejecutó el 2026-10-25 con autorización del CEO: Codex escribió el parche, la tarea quedó en DONE y la PR #114 se fusionó ([registro](construction-runs/20261025-codex-pilot.md)). Fuera del piloto, el proveedor sigue desactivado.

## Objetivo final (CEO-DEC-ENTERPRISE-MODEL-2026-10-26)

El objetivo final del mandato es el [modelo operativo de empresa autónoma](architecture/AAO_ENTERPRISE_OPERATING_MODEL.md), adoptado con las condiciones de [`CEO-DEC-ENTERPRISE-MODEL-2026-10-26`](decisions/CEO-DEC-ENTERPRISE-MODEL-2026-10-26.md).

- **Alcance de la construcción (§4 de la decisión):**
  - la Fase 0, completa;
  - de las fases 1 a 4, lo mínimo necesario para ejecutar el piloto del §14 del modelo.
- **Después del traspaso:** el resto lo completa AAO bajo su propio gobierno.
- **Correspondencia entre fases, gates, construcción y traspaso:** [Anexo A de la decisión](decisions/CEO-DEC-ENTERPRISE-MODEL-2026-10-26.md#anexo-a-correspondencia-operativa-informativa).
- **Cada PR de construcción indica a qué fase y gate contribuye.**
- **Condiciones de diseño vinculantes** (texto completo en la decisión):
  - la organización declarativa no concede autoridad (D-01);
  - primero los cinco protocolos mínimos, reutilizando la cola, los eventos y el journal, y sin motor de workflows genérico antes (D-03);
  - un protocolo nunca crea autoridad (D-04);
  - los eventos no son permisos (D-05);
  - el núcleo de confianza no se sustituye (D-10).

