# Inspiraciones y código de terceros

Este fichero agradece a los proyectos de terceros que han influido en AAO y deja trazabilidad de esa influencia. Cada entrada distingue dos casos:

- **Código copiado o adaptado:** fragmentos de terceros incorporados al repositorio. Hay que conservar la licencia y el aviso de copyright, e indicar la ruta de AAO donde está cada fragmento.
- **Inspiración:** ideas o diseños tomados como referencia y reimplementados desde cero. El código de AAO es original y no arrastra obligaciones de licencia, pero se reconoce el origen.

**Política:**
- Antes de fusionar cualquier código copiado de un tercero, se añade aquí su entrada con el repositorio, el commit, la licencia, los ficheros de origen y las rutas de AAO afectadas, y se incluye su aviso de licencia.
- Las inspiraciones se registran en cuanto una idea de un tercero se implementa en AAO.

---

## RONIN Orchestration Engine

| Campo | Valor |
|---|---|
| Repositorio | <https://github.com/Gaurav2693/ronin-orchestration-engine> |
| Autor | Gaurav2693 (GitHub) |
| Revisión consultada | `0a3666a` («feat: add live cost dashboard (flip-flap UI) + metrics API») |
| Licencia | MIT |
| Consultado | 2026-10-25, a petición del CEO, como referencia externa |
| Análisis | [`docs/research/RONIN_DIFFERENTIAL.md`](docs/research/RONIN_DIFFERENTIAL.md) (PR #112) |

**Código copiado: ninguno.** RONIN está escrito en JavaScript (`.mjs`) y AAO en Python y TypeScript. No se ha copiado ningún fichero ni fragmento: las ideas se reimplementaron desde cero sobre los componentes que AAO ya tenía. RONIN se clonó solo para leerlo; no se ejecutó su código ni se usó como dependencia.

**Inspiraciones implementadas:**

| Idea de RONIN | Origen en RONIN | Implementación original en AAO | PR |
|---|---|---|---|
| Registrar qué modelo ejecuta cada tarea, con sus propiedades (proveedor, modelo) | `config/modelConfig.mjs` (catálogo por modelo) | `agent_runner.backend_identity()`: proveedor, modelo fijado y versión real del CLI en la evidencia de cada ejecución; el panel de la tarea en el Control Center los muestra. AAO hace lo **contrario** que RONIN en un punto: RONIN oculta el modelo (`model_hidden`, ADR-010) y AAO lo exige como evidencia | #113 |
| Detectar bucles de un agente | `middleware/loopDetection.mjs` (llamadas repetidas a herramientas) | `stage_agent_run`: rechaza un intento nuevo si los dos últimos acabaron igual (mismo parche y mismo resultado). Se compara entre intentos, no entre llamadas a herramientas | #116 |
| Roles de modelo (*seats*) y catálogo de modelos | `config/modelConfig.mjs` (`seat`, `getModelsBySeat`) | Bloque `model_profile` (backend, proveedor, modelo, seats) en el contrato de la capacidad `agent`, validado al registrarla. El worker ejecuta lo que dice la capacidad del job, no el entorno. El modelo es un dato del catálogo; registrar una capacidad no activa el proveedor | I3 |
| Selección de modelo según la tarea | `router/intelligence-router.mjs` (puntuación por palabras clave) | `model_router.route()`: función pura sobre el catálogo que filtra por rol, seat, activación, proveedor excluido y disponibilidad, y elige la mayor calidad para el seat. Si hay empate, no recomienda. `POST /v1/work/{id}/route-model` registra `model.routed` sin autorizar nada, y el staging vuelve a comprobar la activación por su cuenta | I4 |
| Presupuesto diario y comprobación previa a la llamada | `observability/costTracker.mjs` (`canAfford`), `intelligence/costGuardrail.mjs` | `cost_per_attempt_usd` en `model_profile`; presupuesto diario del CEO (`AAO_AGENT_DAILY_BUDGET_USD`); gasto estimado sumado desde los eventos `execution.staged` en PostgreSQL. El router filtra y el staging rechaza (`budget.exceed`). A diferencia de RONIN, no hay niveles con rebaja silenciosa: se para y decide el CEO | I5 |

**Inspiraciones planificadas, sin implementar** (incremento I6 del análisis):

| Idea de RONIN | Origen en RONIN | Plan en AAO |
|---|---|---|
| Límites y clases de datos por modelo | `config/modelConfig.mjs` (`maxTokens`) | Ampliar `model_profile` con `limits` y `data_classes` cuando haga falta (`quality` y `cost_per_attempt_usd` ya existen) |
| Árbol de tareas y cronología del ciclo | `forge/forgeTaskTree.mjs`, `api/cycleManager.mjs`, `dashboard/index.html` | Presentación de los intentos en el Control Center sobre los datos que AAO ya persiste |

Cuando alguna de estas ideas se implemente, la fila pasará a la tabla de inspiraciones implementadas con su PR.

**Descartado de forma expresa:**
- el modelo oculto;
- el fallback silencioso entre proveedores;
- BYOK y el baúl de claves;
- el sandbox (simulado o Docker);
- el SSE sin autenticación;
- el estado en memoria.

Los motivos están en el análisis, §2.9.

Gracias al autor de RONIN por publicar su trabajo con licencia abierta.
