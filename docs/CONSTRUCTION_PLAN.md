# Plan de construcción de AAO (régimen CEO-DEC-AAO-CONSTRUCTION-2026-10-25)

**Objetivo:** cumplir el criterio de éxito de [`CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md`](CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md). Un cambio pequeño, real y útil a AAO tiene que recorrer este camino, y el Control Center tiene que mostrarlo con el estado real del backend:

`AAO → proyecto → objetivo → tarea → agente ejecutor → ejecución acotada → tests → auditoría independiente → PR → resultado`

**Régimen:**
- Claude, Codex y Antigravity trabajan como equipo constructor externo.
- La integración es la ordinaria: el CEO fusiona.
- Los controles de calidad son proporcionados: CI completo (compileall, ruff, pytest `-W error`) y una revisión de segunda línea en los cambios delicados.
- No hay gates de gobierno por PR.
- La certificación se hace sobre el candidato de traspaso: [criterios del §4](decisions/CEO-DEC-AAO-CONSTRUCTION-2026-10-25.md).

## Estado de cada tramo (inventario del 2026-10-25, actualizado con W1 #100 y W2a)

| Tramo | Estado | Dónde |
|---|---|---|
| Mandato, proyecto y objetivo | **Existe** | `POST/GET /v1/mandates`, `/v1/projects`, `confirm`, `state` |
| Tarea (work) | **Existe** | `POST /v1/projects/{id}/work`, `admit`, `progress` |
| Agente ejecutor (la tarea produce un parche) | **Existe** (W1, #100). Backend `fixture` probado de extremo a extremo; backend `codex` sin ejercitar: requiere activar el proveedor y resolver su autenticación con `HOME` aislado | `agent_runner.py`, `inert_execution_worker.py`, `stage-agent-run` |
| Ejecución acotada y tests | **Existe** (W2a). La misma ejecución confirma el parche como commit candidato con identidad fija, lo guarda en `refs/aao/candidates/<sha>` de un repositorio bare y corre `core-unit` más los tests que añade el parche en sandbox bwrap. Una tarea con un intento fallido puede relanzarse | `agent_runner.py`, `sandboxed_repository_checks.py`, migración 014 |
| Propuesta de parche y validación | **Existe** | `patch-proposals`, `validate`, `patch_proposals.py` |
| Auditoría independiente | **Existe** en dos piezas: reviews en la API y el servicio de auditoría de manifiestos. Desde W2a, la API acepta APPROVE del auditor sobre el SHA candidato probado (tarea → VERIFIED). VERIFIED → DONE sigue bloqueado hasta W3 | `reviews`, `review.py`, `independent_audit.py`, `manifest_audit.py`, `auditor_dispatch.py` |
| De la propuesta aprobada a la PR | **Existe con clientes inyectables** (W2b). En dos pasos, uno por identidad (las claves de cada App solo las lee su uid): `--step push` (implementador, re-verifica en el almacén que el commit es base + parche de la propuesta aprobada y empuja exactamente ese SHA) y `--step open` (PM, abre la PR). Ambos requieren `code.publish` y no pueden ser el autor; quedan `work.candidate_pushed` y `work.pr_opened` en el tablero. Probado con remoto bare y apertura falsa. La vía real (Apps `aao-impl-*` → fork, `aao-pm` → PR) está escrita pero **sin ejercitar**: necesita ejecutar como el uid que custodia las claves | `pr_publisher.py`, `scripts/publish_candidate.py` |
| De la PR a `main` (R1) | **Existe**, pero desactivado hasta el traspaso | `r1_pipeline.py`, `integrator.py` |
| Resultado visible en el Control Center | **Parcial.** Tablero, tareas, propuestas, ejecuciones y auditorías, sí. Actividad y agentes asignables, no. La vista del ciclo Git está en una rama sin fusionar | `frontend/`, rama `feat/control-center-daily-ui` (967dc73 y cambios locales) |

## Frentes de trabajo, por prioridad

| # | Frente | Responsable | Entregable |
|---|---|---|---|
| W1 | **Agente ejecutor.** Un worker toma una tarea admitida, ejecuta un agente (Codex/Claude) en sandbox sobre un clon en el SHA base, registra un parche como propuesta y registra la ejecución | Codex (backend) y Claude (sandbox y diseño) | Una tarea genera una propuesta real, con evidencia en la cola |
| W2 | **De la propuesta a la PR.** Con la propuesta aprobada, commit y push al fork del implementador con su App, y servicio `aao-pm` que abre la PR fork → canónico. Es el paso 2 de [E2E_PR_PIPELINE](E2E_PR_PIPELINE.md) | Codex (backend) y Claude (scripts y unidades) | PR abierta por `aao-pm[bot]` desde una propuesta, enlazada a la tarea |
| W3 | **Resultado y trazabilidad.** El estado de la PR (checks, auditoría y fusión) vuelve a la tarea, y endpoint de actividad | Codex | La tarea pasa a DONE con enlace a la PR y al SHA final |
| W4 | **Control Center.** Integrar la rama pendiente de Antigravity rebasada sobre #20, añadir la vista de actividad y la vista de la PR/resultado desde el estado real | Antigravity; Codex o Claude mientras Antigravity no tenga cuota (hasta el ~30-10) | Recorrido completo visible en la web |
| W5 | **Demostración E2E.** Un cambio real pequeño a AAO por todo el camino | Claude (coordinación) | Evidencia para el criterio 9 del traspaso |

**Única decisión estratégica prevista:** para que W1 y W5 ejecuten un modelo real dentro de AAO hay que activar un proveedor de modelos, con su coste y sus credenciales. El mandato lo reserva al CEO («model/provider activation»). Se le planteará cuando W1 esté listo, sin bloquear su construcción.

## Fuera de la construcción (se hará en el traspaso)

Todo esto se hará sobre el candidato de aceptación:
- separación de identidades de los agentes;
- reglas del repositorio canónico;
- actualización de la raíz de confianza;
- ensayo P2/P3 completo y dictamen de equivalencia;
- RA en PASS;
- auditoría independiente;
- activación del integrador.

Los planes anteriores (M2-A en `CLOSURE_PLAN.md`, F4 en `F4_PENDING_WORK.md`) quedan como referencia de requisitos, no como orden de trabajo.
