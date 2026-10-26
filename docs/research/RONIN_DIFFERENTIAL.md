# RONIN como referencia externa: análisis diferencial y propuesta incremental

**Estado:** investigación y propuesta. No se implementa nada en este documento. Cualquier cambio de arquitectura que salga de aquí se revisará primero frente a AAO, como pidió el CEO.

| Campo | Valor |
|---|---|
| Referencia | [`Gaurav2693/ronin-orchestration-engine`](https://github.com/Gaurav2693/ronin-orchestration-engine), commit `0a3666a`, licencia MIT, unas 30 000 líneas de `.mjs` sin contar los tests (81 ficheros de test) |
| AAO comparado | `main` en `973f165` (tras #111) |
| Método | Lectura del código fuente, no solo del README. RONIN se clonó como datos: **no se ha ejecutado su código ni sus tests**. Las afirmaciones sobre su comportamiento salen de la lectura, no de una ejecución |
| Autor | Claude, constructor externo (CEO-DEC-AAO-CONSTRUCTION-2026-10-25). No es una auditoría independiente |

## 1. Resumen

RONIN y AAO resuelven problemas distintos:
- **RONIN** busca que una conversación multimodelo resulte fluida y barata. Elige un modelo por cada mensaje, oculta al operador qué modelo respondió, baja de modelo cuando el gasto se dispara y lo transmite todo en vivo.
- **AAO** busca autonomía organizativa con estado persistente, autoridad explícita y evidencia trazable.

La combinación que merece la pena es la experiencia y la selección inteligente de RONIN sobre la ejecución persistente y el gobierno de AAO. Para AAO, la idea central es la del CEO: **AAO tiene que conocer las capacidades de sus modelos, no depender de sus nombres.** Si se implementa bien, incorporar o sustituir un modelo será una operación administrable (registrar una versión de capacidad y activar su proveedor), no una reconstrucción.

**Conclusiones:**
1. Del código de RONIN no hay nada que copiar. Las ideas útiles son pocas y basta con una función pura y unas columnas de contrato para reimplementarlas. Así tampoco surge la obligación de atribución de la licencia MIT.
2. Hay que adoptar el concepto de *seats* (roles de modelo), el catálogo con coste y latencia por modelo, los presupuestos por niveles y la detección de bucles, pero adaptados a las tareas de AAO y no a mensajes de chat.
3. Hay que rechazar:
   - el modelo oculto;
   - el fallback silencioso entre proveedores;
   - BYOK y el baúl de claves;
   - el sandbox de RONIN;
   - el SSE sin autenticación;
   - el estado en memoria.
4. La lectura destapa dos huecos de AAO que conviene cerrar primero, porque son pequeños y no dependen de RONIN:
   - **el backend no está ligado a la capacidad seleccionada**;
   - **la evidencia no registra qué modelo ni qué versión se ejecutaron**.

## 2. Comparación por área, sobre el código

### 2.1 Router de inteligencia

**En RONIN**, `router/intelligence-router.mjs` puntúa cada mensaje con listas de palabras clave y elige un modelo:
- Las listas son `SIGNALS.tech`, `reasoning`, `bulk` y `roninProjects`, que contiene los nombres de los proyectos personales del autor.
- Hay atajos fijos: `/director` siempre lleva a Opus y una imagen siempre a GPT-4o.
- Mantiene su **propio** registro `MODELS`, con claves (`haiku`, `sonnet`…) distintas de las de `config/modelConfig.mjs`, aunque este último se declara «single source of truth». Es decir, hay dos registros que no coinciden.
- `route()` no consulta los *seats*, el presupuesto (`costGuardrail`), la disponibilidad ni los permisos.

**En AAO:**
- La selección es por capacidad registrada, en el registro versionado de la migración 010.
- `capability_evaluation.recommend` compara reuse/adapt/build en seis dimensiones y, si hay empate, no recomienda nada.
- `stage_agent_run` exige capacidad `agent`, en estado `registered_local`, con entrypoint `aao.agent_runner:patch` y con una evaluación `capability.evaluated` de la tarea.
- **No hay selección entre modelos ni proveedores.** El backend sale de la variable de entorno global `AAO_AGENT_BACKEND`, con valor por defecto `codex` (`inert_execution_worker.py:48`).

**Diferencial:** RONIN aporta la idea de un catálogo con propiedades por modelo y un selector. Su implementación (palabras clave sobre un mensaje) no sirve para tareas con criterios de aceptación. AAO ya tiene el lugar natural para el catálogo, que es el contrato de la capacidad `agent`, y un estilo de decisión determinista sin desempates arbitrarios.

### 2.2 Roles de modelo (*seats*)

**En RONIN**, `config/modelConfig.mjs` asigna a cada modelo un `seat` (`core`, `ops`, `director`, `specialist-*`, `analyst`, `memory`), además de `lane`, `maxTokens`, `firstTokenMs` y el coste por millón de tokens. `getModelsBySeat()` filtra por seat.

**En AAO** ya existen roles con autoridad: implementador, auditor, PM, integrador y supervisor, cada uno con identidad propia. El contrato `agent` exige `compatible_roles` y `authority_boundary`. Falta la otra mitad: qué modelos pueden ocupar cada rol.

**Diferencial:** conviene adoptar los *seats* como **requisito funcional** ligado a los roles de AAO, por ejemplo «implementador de parches Python», «auditor de diff» o «resumen de evidencia», nunca como autoridad. La regla de independencia del auditor (su proveedor tiene que ser distinto del del implementador, GOV-REV-001) la **respeta** el router, pero no la **define** él: la sigue fijando la política de revisión.

### 2.3 Despachador de workers

**En RONIN**, `workers/workerDispatch.mjs`:
- toma `suggestedWorker` del preclasificador;
- usa la cadena de fallback del registro (`FALLBACK_CHAINS`);
- si `costGuardrail.canAfford` falla, baja al worker gratuito más barato;
- si el worker pide escalar, vuelve a despachar siguiendo `ESCALATION_MAP`.

Todo ocurre en la misma petición, sin registro duradero, y el resultado lleva `model_hidden: true` (línea 151).

**En AAO**, la cola PostgreSQL tiene leases, claim/complete, journal y fencing. Hay una sola ejecución activa por tarea (014) y un límite de intentos efectivo (`AAO_AGENT_MAX_ATTEMPTS`, `work_management_api.py:1432-1437`). El worker autentica la credencial del agente antes de proponer (`inert_execution_worker.py`).

**Diferencial:** el fallback y la escalada silenciosos de RONIN son justo lo que AAO no puede permitir. Cambiar de worker dentro de una petición equivale a **elegir un modelo sin pasar por la autorización** y deja la evidencia incompleta. En AAO, todo cambio de modelo tiene que ser un **intento nuevo, registrado, contado contra el límite** y solo hacia un proveedor ya activado. El motor de AAO es más fuerte y se conserva tal cual.

### 2.4 Gestión de costes

**En RONIN:**
- `observability/costTracker.mjs` calcula el coste en USD por modelo con el precio de `modelConfig`.
- Acumula el gasto diario en Redis (`cost:daily:{date}`, `cost:model:{id}:{date}`).
- `canAfford(modelId)` compara con los umbrales diarios por modelo y totales (`COST_THRESHOLDS`).
- `intelligence/costGuardrail.mjs` define cuatro niveles (verde, amarillo, naranja y rojo, al 60, 80 y 95 %) que bloquean modelos de forma acumulativa y bajan siguiendo `DOWNGRADE_MAP`.

**En AAO** no hay contabilidad de coste ni de tokens. `capability_evaluation` puntúa `cost` y `tokens` como estimaciones del evaluador, no como medidas.

**Diferencial:**
- Interesa adoptar el presupuesto por niveles y la comprobación previa a la llamada, persistidos en PostgreSQL y no en Redis, que sería un componente nuevo sin necesidad.
- En AAO el presupuesto **filtra candidatos** en el router y **puede bloquear** el staging, pero nunca rebaja en silencio.
- **No está verificado** que `codex exec` informe de los tokens o del coste. Hay que confirmarlo en el piloto antes de prometer medidas reales. Mientras tanto se puede registrar la duración y la estimación.

### 2.5 Memoria contextual

**En RONIN:**
- `intelligence/memoryManager.mjs` guarda en JSON por operador tres niveles: persistente, de sesión e *insight*.
- `middleware/contextSummarizer.mjs` resume los mensajes antiguos con un modelo gratuito cuando se supera el límite de tokens.

Está orientado a una conversación con una sola persona.

**En AAO**, el contexto de cada ejecución lo forman la tarea (título, descripción y criterios), el SHA base y el repositorio. La memoria institucional está en la base de datos (eventos, propuestas, reviews) y en `docs/`.

**Diferencial:** de momento no hace falta. El agente de AAO trabaja sobre una tarea acotada y un clon limpio, así que el contexto ya está acotado por diseño. Una mejora útil y pequeña, para cuando haya varios intentos, sería pasar al siguiente intento el **motivo del fallo anterior** (check fallido o rechazo de review) como dato de la tarea. Queda como candidato, no como prioridad.

### 2.6 Detección de bucles

**En RONIN**, `middleware/loopDetection.mjs` detecta tres patrones sobre el historial de llamadas a herramientas de una sesión:
- la misma herramienta con los mismos argumentos 3 veces;
- 10 llamadas seguidas sin intervención del usuario;
- ciclos A→B→A→B.

**En AAO**, Codex corre dentro del jail bwrap y AAO no ve sus llamadas a herramientas, así que ese método no se puede aplicar. Hoy los bucles se acotan con el timeout del agente, el lease y el límite de intentos. Cuando un intento reproduce el mismo parche, el conflicto 409 «Identical patch proposal» lo detecta, pero **reutiliza la propuesta en lugar de detener los reintentos** (`inert_execution_worker.py`, rama del 409).

**Diferencial:** la detección de bucles equivalente en AAO se hace **entre intentos**. Si el intento N produce el mismo `patch_sha256` o el mismo fallo de check que el N-1, se para y se escala al PM sin consumir más intentos. Es pequeño y no necesita nada de RONIN.

### 2.7 Eventos SSE

**En RONIN**, `api/sseController.mjs` emite `ronin.state`, `ronin.stream`, `ronin.complete` y `ronin.error`. Lo hace sin autenticación, con `Access-Control-Allow-Origin: *` (línea 43) y con un mapa de clientes en memoria. El *dashboard* (`dashboard/index.html`) no usa SSE: consulta `/api/cost-metrics` cada 3 s (línea 294).

**En AAO**, los eventos están persistidos en PostgreSQL (`events`) y se exponen en `/v1/projects/{id}/activity` y `/board`. El Control Center los carga desde la API real, sin streaming.

**Diferencial:** SSE solo aportaría inmediatez visual. Si algún día se añade, tiene que leer de la tabla `events` ya existente, con la misma autenticación que el resto de la API, y sin CORS abierto. Va después de W4 y sin prisa: para W5 basta con refrescar periódicamente.

### 2.8 Visualización de ciclos y tareas (Forge)

**En RONIN:**
- `api/cycleManager.mjs` define una máquina de 10 estados para el ciclo (briefing → creative → … → complete, más blocked).
- `forge/forgeTaskTree.mjs` gestiona un árbol de tareas con estados queued, running, completed, failed y blocked, y emite eventos `task:*`.
- `forge/forgeSession.mjs` crea sesiones con un contenedor Docker y, si falla, cae a «in-process mode» en `process.cwd()`.

Todo vive en memoria.

**En AAO**, los estados de la tarea (READY, IN_PROGRESS, VERIFIED, DONE) son persistentes y tienen fencing. El tablero muestra los intentos con su candidato, su check y la PR. La pestaña *Actividad* ya existe (#109/#111).

**Diferencial:** la parte reaprovechable es de **presentación**. Un árbol con el estado de cada intento y su coste y duración junto a cada nodo, y una línea de tiempo del ciclo, son ideas para W4 sobre los datos que AAO ya persiste. Su máquina de estados no aporta nada a AAO, y el «in-process mode» en el directorio actual es un antipatrón de aislamiento.

### 2.9 Sandbox, claves y proveedores (lo que hay que rechazar)

- **Sandbox:**
  - El sandbox de `workers/codexWorker.mjs` es simulado: `exec` devuelve el eco del comando (línea 75).
  - `infra/sandboxManager.mjs` usa Docker, que D2 de CEO-DEC-2026-10-25 deniega a las cuentas de agente.
  - `forge/forgeToolRegistry.mjs` ejecuta `execSync` con una lista negra de expresiones regulares (`/docker/i`, `/sudo/`…) y hereda `...process.env` (línea 298).
  - El jail bwrap de AAO, con la sonda de aislamiento y su control negativo (`CODEX_PROVIDER_ACTIVATION_E2E.md`), es estrictamente más fuerte. **No se reutiliza nada.**
- **BYOK y `envVault`** (`config/byokRegistry.mjs`): claves por usuario cifradas en el proceso. Chocan con la precisión 3 de la ratificación (no conceder acceso general a secretos) y con la separación de credenciales que exige el traspaso. **Excluido.**
- **Modelo oculto (ADR-010)**: es lo contrario del requisito de evidencia de AAO. **En AAO, qué modelo se ejecutó es un dato obligatorio de la evidencia.**
- **`models/providerRegistry.mjs`**: un mapa nombre → cliente SDK con `stream()` y `complete()`. Es razonable, pero AAO ejecuta agentes CLI dentro de un jail, no llamadas SDK desde el proceso. La abstracción equivalente en AAO es el **backend** de `agent_runner`.

### 2.10 No revisado

No se ha leído en detalle: `intelligence/critic.mjs`, `consensus.mjs`, `confidenceScorer.mjs`, `epistemicGuard.mjs`, `operatorProfile.mjs`, `topologyLearner.mjs`, `gates/parallelReview.mjs`, `durableBuild.mjs`, `api/chatServer.mjs` ni `api/agentManager.mjs`. Este documento no afirma nada sobre ellos.

## 3. Huecos de AAO detectados

Son independientes de RONIN. Los trato como defectos de trazabilidad:

| # | Hueco | Evidencia | Efecto |
|---|---|---|---|
| H1 | La capacidad seleccionada no determina qué se ejecuta | El job lleva `capability_id`/`version`, pero el backend sale de `AAO_AGENT_BACKEND` (`inert_execution_worker.py:48`) | La cadena capacidad → proveedor que ejecutó no es verificable desde la base de datos |
| H2 | La evidencia no identifica el modelo | `backend_version` es la constante `"codex-cli"` (`agent_runner.py:204`); no se registra la versión del binario ni el modelo | No se puede reconstruir qué modelo produjo un parche |
| H3 | Los reintentos no se detienen ante una repetición | La rama del 409 «Identical patch proposal» reutiliza la propuesta | Consume intentos sin progreso |

## 4. Propuesta: router de capacidades y proveedores

### 4.1 Principio

Hay que separar tres decisiones con dueños distintos:

| Decisión | Quién | Dónde | Efecto |
|---|---|---|---|
| **Activación de proveedor** | CEO (reservado por el mandato) | Configuración del host: `AAO_AGENT_PROVIDER` generalizado a lista `AAO_ACTIVATED_PROVIDERS` | Sin activación no hay ejecución, diga lo que diga el router |
| **Selección de modelo** (router) | PM o planificador, función determinista | Evento `model.routed` sobre la tarea | Solo recomienda. **No concede nada** |
| **Autorización de ejecución** | Grants y comprobaciones de `stage_agent_run` | API, transacción PostgreSQL | Vuelve a verificar todo, incluida la activación, de forma independiente al router |

El staging tiene que seguir funcionando **sin** router, como hoy. El router es una ayuda para elegir, no un paso obligatorio de autorización.

### 4.2 Catálogo: capacidades, no nombres

No hace falta un registro nuevo. Basta con extender el contrato de la capacidad `agent` (migración 010: `contract`, `required_permissions`, `risks`, `compatibility`) con un bloque `model_profile`:

```json
{
  "purpose": "...", "compatible_roles": ["implementer"], "inputs": "...", "outputs": "...",
  "authority_boundary": "...",
  "entrypoint": "aao.agent_runner:patch",
  "model_profile": {
    "backend": "codex",
    "provider": "openai",
    "model": "<id del proveedor>",
    "seats": ["patch.python", "patch.tests"],
    "quality": {"patch.python": 3, "patch.tests": 4},
    "cost": {"unit": "usd_per_attempt_estimate", "value": 0.4},
    "limits": {"max_timeout_s": 1800, "max_patch_bytes": 65536},
    "data_classes": ["repo_public"]
  }
}
```

- El **nombre del modelo** es un dato más del perfil, y nada en el código lo usa para decidir. Sustituir un modelo es registrar una versión nueva de la capacidad.
- `quality` lo fija el registrador. Mejorará con resultados reales (§4.6), pero nunca se infiere en silencio.
- `missing_contract_fields` añade `model_profile` como obligatorio solo para capacidades `agent` con `entrypoint = aao.agent_runner:patch`.

### 4.3 Interfaz del router

Es una función pura en `src/aao/model_router.py`, sin E/S, en la línea de `capability_evaluation.recommend`:

```python
@dataclass(frozen=True)
class Requirements:
    seat: str                    # p. ej. "patch.tests"
    role: str                    # rol AAO que ocupará el modelo
    data_class: str              # clase de datos de la tarea
    max_cost: float | None
    exclude_providers: frozenset[str] = frozenset()   # p. ej. independencia del auditor

@dataclass(frozen=True)
class RouteDecision:
    capability_id: str | None    # None = sin recomendación (empate o ningún candidato)
    version: str | None
    reasons: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]   # (capability@version, motivo)

def route(req: Requirements, candidates: list[dict], *, activated: frozenset[str],
          budget_left: float | None, unavailable: frozenset[str]) -> RouteDecision: ...
```

**Orden de filtros**, cada uno con su motivo de rechazo registrado:
1. el rol está en `compatible_roles`;
2. el seat está en `seats`;
3. la clase de datos está permitida;
4. el proveedor está activado;
5. el proveedor no está excluido;
6. el proveedor está disponible;
7. el coste cabe en `max_cost` y en `budget_left`.

Entre los que quedan, gana la mayor `quality[seat]`, y a igual calidad, el menor coste. **Si persiste el empate, no hay recomendación**: decide el PM, igual que en `recommend`.

### 4.4 Componentes afectados

| Componente | Cambio |
|---|---|
| `capability_contracts.py` | Validación de `model_profile` para las capacidades agent-runner |
| `model_router.py` (nuevo) | La función `route` |
| `work_management_api.py` | `POST /v1/work/{id}/route-model`, que solo calcula y registra `model.routed`. `stage_agent_run` vuelve a comprobar que el proveedor del perfil está activado |
| `inert_execution_worker.py` | El backend sale del `model_profile` de la capacidad del job, no de la variable de entorno (H1) |
| `agent_runner.py` | Registra `provider`, `model` y la versión real del binario (H2) |
| Migración nueva | Tabla `agent_spend` (execution_id, provider, estimate, measured, at) o, en su lugar, eventos `execution.cost`. Se decide al implementar, prefiriendo eventos si bastan |
| Control Center | Mostrar el proveedor, el modelo y el coste por intento en el tablero (W4) |

### 4.5 Pruebas de aceptación

1. El router **nunca** devuelve un proveedor no activado, aunque sea el de mayor calidad.
2. `stage_agent_run` rechaza (409) una capacidad cuyo proveedor no está activado, **aunque exista** un `model.routed` que la recomiende.
3. Si hay empate de calidad y coste, `capability_id` es `None` y el motivo es explícito.
4. Con un presupuesto agotado, el candidato aparece en `rejected` con el motivo `budget`, y el staging devuelve 409 si se fuerza.
5. Con la exclusión de proveedor del auditor, el router no recomienda el mismo proveedor que el del implementador.
6. El worker ejecuta el backend del `model_profile` de la capacidad del job. Con `AAO_AGENT_BACKEND` en otro valor, ejecuta lo que dice el perfil (H1).
7. El resultado de la ejecución incluye `provider`, `model` y la versión real del binario (H2).
8. Un cambio de modelo tras un fallo es un intento nuevo, aparece en el tablero y cuenta contra `AAO_AGENT_MAX_ATTEMPTS`.
9. Si un intento repite el `patch_sha256` o el mismo fallo de check que el anterior, el staging siguiente devuelve 409 con «sin progreso; decisión del PM» (H3).
10. Las pruebas existentes del flujo W1–W3 con el backend `fixture` siguen pasando sin router.

### 4.6 Lo que queda fuera de esta propuesta

- Calidad aprendida a partir de resultados (tasa de checks verdes y aprobaciones por capacidad). Requiere volumen real y se deja para después del traspaso.
- La disponibilidad en vivo de los proveedores. Por ahora basta con la marca manual `unavailable`.
- El streaming SSE.
- La memoria entre intentos más allá del motivo del fallo anterior.

## 5. Incrementos, complejidad y relación con el plan

Ninguno de estos incrementos bloquea el piloto de Codex ni el Control Center, y todos son compatibles hacia atrás con el procedimiento del piloto, que configura el proveedor por entorno.

| # | Incremento | Complejidad | Relación con el plan | Cuándo |
|---|---|---|---|---|
| I1 | **Evidencia del modelo** (H2): registrar provider, model y versión real del binario en el resultado de la ejecución y mostrarlo en el tablero | S | Evidencia de W5 y criterio 9 del traspaso | Puede entrar antes del piloto: mejora su evidencia sin cambiar su procedimiento |
| I2 | **Parada sin progreso** (H3) | S | W1/W2, reintentos | Después del piloto o en paralelo |
| I3 | **Backend ligado a la capacidad** (H1) y `model_profile` en el contrato. Se mantiene el entorno como valor por defecto si el perfil falta, para no romper el piloto | M | W1 | Después del piloto |
| I4 | **Router puro** + `route-model` + recomprobación de la activación en el staging | M | W1, entre tarea y agente ejecutor | Después de I3 |
| I5 | **Presupuesto**: estimación por intento, filtro en el router y bloqueo en el staging. La medida real de tokens o coste, solo si el piloto confirma que el CLI la reporta | M | W1/W5 | Después de I4 y del piloto |
| I6 | **Control Center**: proveedor, modelo y coste por intento, y árbol de intentos estilo Forge | S–M | W4 | Cuando W4 lo admita, sin desplazar el trabajo en curso |

S = menos de un día de constructor; M = 1-3 días; L = más.

## 6. Decisiones

- **El router no necesita decisión nueva del CEO:** no añade proveedores ni concede nada.
- **La activación de cualquier proveedor sigue reservada al CEO** (`CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md`), y el piloto de Codex conserva su autorización propia.
- Si se quiere un segundo proveedor (por ejemplo, un modelo distinto para el auditor), habrá que plantearlo como una activación aparte.

## 7. Informe (AGENTS.md)

| Campo | Contenido |
|---|---|
| Alcance | Lectura del código de RONIN `0a3666a` en las áreas pedidas. Comparación con AAO `973f165`. Propuesta escrita. Sin cambios de código |
| Revisión | AAO `973f165`; RONIN `0a3666a` |
| Acciones | Clon de solo lectura de RONIN, con hooks desactivados y sin configuración global. Lectura de los ficheros citados. Lectura de `agent_runner.py`, `inert_execution_worker.py`, `work_management_api.py` (staging), `capability_*.py` y las migraciones 010 y 014 |
| Evidencia y límites | Las referencias de línea apuntan a esos commits. RONIN no se ha ejecutado ni se han corrido sus tests. Los módulos listados en §2.10 no se han revisado. No está verificado que `codex exec` reporte tokens o coste |
| Bloqueos | Ninguno para la propuesta. La medida real de coste depende del piloto |
| Autoridad usada | Régimen de construcción externa. Ninguna autoridad de AAO |
| Siguiente | El CEO revisa y fusiona. Después de su visto bueno, I1 puede ir en una PR pequeña. I3 e I4 van después del piloto de Codex |
### I7: conversación por el catálogo de capacidades, con activación y presupuesto (pendiente)

La conversación CEO–AAO aún selecciona proveedor/modelo mediante `AAO_CONVERSATION_*`, fuera del catálogo de capacidades y de la activación/presupuesto de I3–I5. Evolucionar a una capacidad de conversación independiente, con proveedor activado expresamente, modelo del catálogo, límites de coste/presupuesto y trazabilidad por turno. **No implementado**: activar cualquier proveedor sigue siendo decisión reservada al CEO.
