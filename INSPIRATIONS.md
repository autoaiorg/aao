# Inspiraciones y código de terceros

Registro de procedencia para código y conceptos externos relacionados con AAO.

## Política y clasificación

- **Código copiado o adaptado:** requiere identificar repositorio, commit, licencia, ficheros de origen y rutas de AAO afectadas; conservar los avisos aplicables. No se incorpora código de terceros sin revisar antes los términos.
- **Inspiración conceptual:** registrar la referencia y las ideas funcionales que influyen en AAO. Una idea se acredita como implementada solo cuando el cambio AAO existe; las ideas meramente estudiadas o planificadas se etiquetan como tales.
- El registro no sustituye la licencia del tercero ni concede permiso para usos que esta prohíba.

## Inspiraciones conceptuales

### RONIN Orchestration Engine — ideas implementadas y planificadas

---

## RONIN Orchestration Engine

| Campo | Valor |
| --- | --- |
| Repositorio | <https://github.com/Gaurav2693/ronin-orchestration-engine> |
| Autor | Gaurav2693 (GitHub) |
| Revisión consultada | `0a3666a` («feat: add live cost dashboard (flip-flap UI) + metrics API») |
| Licencia | MIT |
| Consultado | 2026-10-25, a petición del CEO, como referencia externa |
| Análisis | [`docs/research/RONIN_DIFFERENTIAL.md`](docs/research/RONIN_DIFFERENTIAL.md) (PR #112) |

**Código copiado: ninguno.** RONIN está escrito en JavaScript (`.mjs`) y AAO en Python y TypeScript. No se ha copiado ningún fichero ni fragmento: las ideas se reimplementaron desde cero sobre los componentes que AAO ya tenía. RONIN se clonó solo para leerlo; no se ejecutó su código ni se usó como dependencia.

**Inspiraciones implementadas:**

| Idea de RONIN | Origen en RONIN | Implementación original en AAO | PR |
| --- | --- | --- | --- |
| Registrar qué modelo ejecuta cada tarea, con sus propiedades (proveedor, modelo) | `config/modelConfig.mjs` (catálogo por modelo) | `agent_runner.backend_identity()`: proveedor, modelo fijado y versión real del CLI en la evidencia de cada ejecución; el panel de la tarea en el Control Center los muestra. AAO hace lo **contrario** que RONIN en un punto: RONIN oculta el modelo (`model_hidden`, ADR-010) y AAO lo exige como evidencia | #113 |
| Detectar bucles de un agente | `middleware/loopDetection.mjs` (llamadas repetidas a herramientas) | `stage_agent_run`: rechaza un intento nuevo si los dos últimos acabaron igual (mismo parche y mismo resultado). Se compara entre intentos, no entre llamadas a herramientas | #116 |
| Roles de modelo (*seats*) y catálogo de modelos | `config/modelConfig.mjs` (`seat`, `getModelsBySeat`) | Bloque `model_profile` (backend, proveedor, modelo, seats) en el contrato de la capacidad `agent`, validado al registrarla. El worker ejecuta lo que dice la capacidad del job, no el entorno. El modelo es un dato del catálogo; registrar una capacidad no activa el proveedor | I3 |
| Selección de modelo según la tarea | `router/intelligence-router.mjs` (puntuación por palabras clave) | `model_router.route()`: función pura sobre el catálogo que filtra por rol, seat, activación, proveedor excluido y disponibilidad, y elige la mayor calidad para el seat. Si hay empate, no recomienda. `POST /v1/work/{id}/route-model` registra `model.routed` sin autorizar nada, y el staging vuelve a comprobar la activación por su cuenta | I4 |
| Presupuesto diario y comprobación previa a la llamada | `observability/costTracker.mjs` (`canAfford`), `intelligence/costGuardrail.mjs` | `cost_per_attempt_usd` en `model_profile`; presupuesto diario del CEO (`AAO_AGENT_DAILY_BUDGET_USD`); gasto estimado sumado desde los eventos `execution.staged` en PostgreSQL. El router filtra y el staging rechaza (`budget.exceed`). A diferencia de RONIN, no hay niveles con rebaja silenciosa: se para y decide el CEO | I5 |

**Inspiraciones planificadas, sin implementar** (incremento I6 del análisis):

| Idea de RONIN | Origen en RONIN | Plan en AAO |
| --- | --- | --- |
| Límites y clases de datos por modelo | `config/modelConfig.mjs` (`maxTokens`) | Ampliar `model_profile` con `limits` y `data_classes` cuando haga falta (`quality` y `cost_per_attempt_usd` ya existen) |
| Árbol de tareas y cronología del ciclo | `forge/forgeTaskTree.mjs`, `api/cycleManager.mjs`, `dashboard/index.html` | Presentación de los intentos en el Control Center sobre los datos que AAO ya persiste |

Cuando alguna idea planificada se implemente, se actualizará su estado con la evidencia de AAO correspondiente.

**Descartado de forma expresa:**

- el modelo oculto;
- el fallback silencioso entre proveedores;
- BYOK y el baúl de claves;
- el sandbox (simulado o Docker);
- el SSE sin autenticación;
- el estado en memoria.

Los motivos están en el análisis, §2.9.

Gracias al autor de RONIN por publicar su trabajo con licencia abierta.

### Agents Office — referencia conceptual estudiada; sin adaptación

| Campo | Valor |
| --- | --- |
| Repositorio | <https://github.com/ajsahni/agents-office> |
| Autor | Ajsahni / Sahni.ai (según los metadatos del repositorio) |
| Revisión consultada | `3773c9b6aed6a1d2c3ab2765d113c644261c2019` |
| Licencia | PolyForm Noncommercial con términos adicionales de Sahni.ai; consultar el texto licenciado antes de cualquier uso |
| Consultado | 2026-10-25, a petición del CEO; revisión de código sin ejecutarlo |
| Análisis | [`docs/research/AGENTS_OFFICE_DIFFERENTIAL.md`](docs/research/AGENTS_OFFICE_DIFFERENTIAL.md) |

**Código, texto y recursos adaptados: ninguno.** La licencia restringe expresamente adaptar Agents Office para conducir, mostrar o servir de frontend a otra plataforma de agentes sin permiso escrito. La implementación de AAO debe ser original e independiente; esta entrada no pretende afirmar que la licencia permita reutilizar sus diseños.

**Ideas funcionales estudiadas, no atribuidas como implementadas:**

| Idea observada | Evolución independiente propuesta para AAO | Estado |
| --- | --- | --- |
| Un espacio visual que enlaza organización, personas y trabajo | Proyección original de solo lectura `/v1/organization`, derivada de proyectos, ejecuciones y revisiones persistidos; identidad organizativa no persistida se marca desconocida | F0 implementado en `feat/agents-office-aa-integration`; validación inicial backend PostgreSQL y test del adapter, pendiente CI/merge |
| Actividad visual asociada a trabajos | Mostrar solo estados y eventos de PostgreSQL/API con IDs, hora y procedencia; reutilizar board y Activity del Control Center | Propuesta |
| Chat, equipos temporales y síntesis | En su caso, convertir órdenes en trabajo AAO persistente y autorizado; los equipos requieren trabajos padre/hijos en backend | Diferido; no copiar prompts ni protocolo de `teams.mjs` |
| Calendario, conocimiento, skills y correcciones | Usar estado y evidencia canónicos; cualquier scheduler, conocimiento o skill futura debe ser persistente, versionada y gobernada por los flujos AAO | Diferido; no copiar almacenamiento local, grafo, skills, briefs o aprendizaje del proyecto externo |

**Elementos expresamente no trasladados:** código, arquitectura interna, prompts, textos, apariencia 3D, composición visual, gráficos, iconos, recursos artísticos, roster, scheduler, sistema de skills, implementación de chat/equipos o almacenamiento JSON. Se agradece al autor por compartir una referencia que permitió estudiar estos patrones de producto.
