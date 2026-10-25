# Agents Office como referencia conceptual: análisis diferencial para AAO

**Estado:** análisis y propuesta incremental; no autoriza ni implementa integración con Agents Office. La oficina de AAO se diseñará e implementará de forma original e independiente.

| Campo | Valor |
|---|---|
| Referencia | [`ajsahni/agents-office`](https://github.com/ajsahni/agents-office), commit `3773c9b6aed6a1d2c3ab2765d113c644261c2019` |
| AAO comparado | `main` en `95d8427cea3d5748ca7041ee054cfc99ab5a8b72` (PR #127 y #128 incluidos) |
| Método | Lectura de código y arquitectura; el proyecto externo se clonó como datos y **no se ejecutó**. Este documento no es auditoría ni certificación. |
| Límite de licencia | La licencia limita expresamente adaptar Agents Office para conducir, mostrar o hacer de frontend de otra plataforma de agentes sin permiso. Se toman únicamente ideas funcionales generales; no código, recursos, textos, estructura visual ni adaptación derivada. |

## 1. Conclusión ejecutiva

Agents Office demuestra una experiencia coherente: un espacio visual sirve de índice a agentes, tareas, conversaciones, rutinas y conocimiento. Su sistema es una oficina local configurada por el usuario y ejecutada sobre Claude. AAO necesita otra cosa: una **vista operativa de la organización dinámica y gobernada de AAO**, independiente del proveedor y respaldada por el estado PostgreSQL existente.

La prioridad no es reconstruir esa amplitud. AAO ya tiene la oficina 2D/3D, el Control Center, identidades de dominio, tableros, actividad y una cola de ejecuciones. El código ya asocia en vivo workers de ejecuciones y revisores observados en boards con sus proyectos/tareas; acredita «ejecutando» solo si hay `RUNNING` y lease futuro, y muestra historial/modelo en el inspector. El backend ya expone `/v1/organization` como proyección de lectura PostgreSQL; aún no expone `/v1/agents/{id}` ni perfiles organizativos persistidos. La oficina consume ahora ese contrato sin reconstruir un roster alternativo cuando falla: las adscripciones desconocidas siguen siendo explícitamente desconocidas. No confundir esta proyección de actividad observada con un organigrama canónico.

**Recomendación:** preservar el contrato de lectura backend ya implementado y cerrar el siguiente hueco con perfiles organizativos persistentes y autorizados, sin tocar la fuente de trabajo. Mantener los enlaces agente/proyecto hacia los controles existentes. Una interfaz conversacional acotada vendrá después: toda petición que implique trabajo debe entrar en el motor de AAO y dejar estado persistente. No ejecutar llamadas a modelos desde React ni guardar allí un segundo ciclo de trabajo.

El primer piloto con un modelo real ya se completó el 2026-10-25 (Codex, tarea DONE, PR #114; véase [`construction-runs/20261025-codex-pilot.md`](../construction-runs/20261025-codex-pilot.md)). Esta propuesta no lo bloqueó ni debe convertirse en prerrequisito de futuras ejecuciones autorizadas. La activación general del proveedor permanece separada y reservada según las decisiones vigentes.

## 2. Qué aporta la referencia — y qué no trasladar

La lectura de `serve.mjs`, `teams.mjs`, `routines.mjs`, `roster.mjs`, `skills.mjs`, `src/main.js`, `src/tasks.js` y `src/brain.js` muestra estos patrones:

- Un servidor local concentra tareas, conversaciones, roster, skills, rutinas, herramientas y grafo de notas; el browser presenta ese estado. Las tareas y rutinas se guardan en JSON locales y el ejecutor es Claude CLI/SDK.
- El roster tiene departamentos y puestos base definidos en el programa; se personalizan nombres, briefs, herramientas y modelo, pero no se cambia libremente la estructura. Las skills se enlazan a agentes/departamentos y los cambios de usuario se convierten en lecciones que vuelven al prompt.
- Los equipos los planifica un lead, ejecutan piezas en procesos paralelos y el lead consolida el resultado. La colaboración se representa como tarea padre con piezas/notas.
- La oficina gráfica funciona como mapa interactivo de puestos y actividad de herramientas; paneles laterales enlazan selección, actividad, tareas y calendario. El cerebro muestra relaciones entre notas, no una fuente corporativa transaccional.
- Rutinas tienen reloj propio y calendario; pueden crear trabajo aunque la página no esté abierta. Las acciones externas pueden esperar aprobación.

Son **principios de producto observables**, no especificaciones de AAO. No se trasladan su servidor, JSON, prompts, lógica de equipos, catálogo Claude, apariencia 3D, gráficos, iconos, textos o artefactos. [Código de referencia en el commit revisado](https://github.com/ajsahni/agents-office/tree/3773c9b6aed6a1d2c3ab2765d113c644261c2019); [términos de licencia](https://github.com/ajsahni/agents-office/blob/3773c9b6aed6a1d2c3ab2765d113c644261c2019/LICENSE).

## 3. Diferencial frente a AAO

| Área | Agents Office (observado) | AAO actual | Evolución diferencial de AAO |
|---|---|---|---|
| Organización, departamentos, responsables | Puestos de un roster fijo de seis departamentos; personalización local | `OrganizationStructure`, `OrgUnit`, responsables, agentes standing/ephemeral y estado/evidencia ya modelados en frontend; vista organización y oficina 2D/3D existentes | Estructura dinámica que refleje org units, relación responsable-subordinado y equipos temporales desde datos persistidos. No asumir que una cuenta registrada está «en línea». |
| Actividad visual ↔ trabajo real | Actividad de procesos Claude y herramientas, reflejada en tarea local | `getOrganizationStructure()` agrega ejecución e historial desde boards reales; requiere estado `RUNNING` y lease vigente para marcar BUSY, registra historial de ejecución/proveedor/modelo y enlaza tareas/proyectos. Oficina no tiene feed unificado de eventos ni endpoint de telemetría canónico | Preservar esos vínculos y la evidencia temporal de backend; reducir el fan-out y centralizar filtrado/semántica en backend. No afirmar presencia/heartbeat si el backend no lo emite. |
| Identidades | Persona/puesto configurable; no es principal de autorización AAO | Principals/grants PostgreSQL y modelos frontend distinguen tipos y límites de autoridad | Mostrar identidad y autoridad verificadas del backend, con rol y grants resumidos; nunca equiparar nombre de pantalla y credencial. |
| Conversaciones | Chat por agente y conversación en persona; prompt armado localmente | No hay sesión conversacional de agente conectada al frontend; la oficina sí ofrece inspector de agente con historial y datos de ejecución (PR #127). AAO tiene creación/admisión de trabajo y flujo persistente | Futura conversación CEO-AAO como interfaz de intención; instrucciones ejecutables se convierten en trabajo AAO persistente y autorizado, con confirmación donde proceda. No chat directo a un proveedor desde UI. |
| Equipos y consolidación | Lead divide, procesos paralelos y síntesis; estado team anidado en tarea JSON | Cola y ejecuciones PostgreSQL por trabajo; no hay equipo efímero de producto y síntesis padre-hijas como recurso de UI | Empezar mostrando ejecuciones existentes. Solo introducir equipos efímeros cuando el motor defina trabajos padre/hijos persistentes, participantes, fallos parciales y consolidación enlazada a evidencia. |
| Calendario/rutinas | Scheduler local y JSON; ocurre con página cerrada | API de trabajos con cola y journal; no se encontró planificador/rutina durable de AAO en el alcance revisado | No añadir temporizadores en browser. Futuras rutinas deben convertirse en instancias de trabajo persistidas por backend y mostrar próxima ejecución, ejecución omitida, aprobación y resultado. |
| Conocimiento | Vault/wiki-links locales y grafo derivado de notas | Evidencia, actividad, capacidades y documentación de proyectos existentes; no hay grafo corporativo unificado en oficina | Primero un índice navegable de evidencia/proyectos y decisiones ya almacenadas. Grafo solo si se define una fuente canónica; relaciones del frontend no son hechos nuevos. |
| Skills/briefs/aprendizaje | Archivos de prompt editables y correcciones reinyectadas | Catálogo de capacidades/versiones y evaluaciones; no es lo mismo que autorización de ejecución | Representar capacidades y sus versiones como datos conocidos. Correcciones se registran primero como propuestas trazables; no autoeditar prompts ni alterar autoridad. |
| Herramientas/decisiones | Lista MCP y llamadas Claude; aprobación de ciertas salidas | Control Center ya tiene capacidades, límites `execution_authorized`, decisiones, actividad y estados de revisión | Mostrar herramientas/capacidades según registro, autoridad y evento real; hacer visibles decisiones pendientes y evidencia. Una capacidad listada no equivale a una concesión o ejecución. |
| Proveedor | Acoplado a Claude CLI/SDK y cuenta local | AAO separa identidades de agentes y backend/modelo; selección/activación de proveedor es una capa propia | La oficina consume el modelo de dominio y metadatos de ejecución, no nombres/capacidades Claude ni APIs de proveedor. |

## 4. Estado comprobado de AAO

El análisis inicial de AAO se actualizó después de #127 y #128 sobre `95d8427`; las notas de seguimiento documentan los incrementos #129, #130 y la corrección fail-closed en construcción.

### Existe

- Oficina React/Three.js con vista 3D y plano 2D, selección de unidad/agente, filtros, búsqueda e inspector: `frontend/app/src/features/office/`.
- Estructura organizativa y modelos de identidad, autoridad, confianza y evidencia: `frontend/app/src/domain/models.ts`.
- Capa de lectura `AaoReadPort`, adapter HTTP vivo y demo separado; React Query, claves ligadas a sesión, limpieza de cache al cambiar origen/salir. La UI inicia en `live`; los datos demo son explícitamente aislados.
- Control Center con proyectos, board, actividad de proyecto, capacidades/evaluaciones, decisiones y operaciones. Backend expone board/actividad/capacidades y stages de trabajo/ejecución. PostgreSQL es la fuente persistente del trabajo y journal.
- La oficina consume `GET /v1/organization`, proyección backend de proyectos visibles, ejecuciones y revisiones; `/v1/agents/{id}` no existe. La ruta ya no vuelve a fan-out de proyectos/boards ante 404, error de red o contrato inválido: LIVE muestra el estado explícito y no inventa las seis unidades estáticas que antes componían el fallback. La comprobación de lease y cobertura siguen en el contrato backend.
- La proyección no persiste perfiles de nombre/rol/unidad/responsable ni heartbeat. La única unidad de producción es `unit-unassigned`, etiqueta de agrupación visual no organizativa. Nombres worker/reviewer son IDs observados, no prueba de adscripción, liderazgo o certificación.
- PR #127 amplió la oficina con historial de proveedor/modelo, intentos y alertas de no progreso/presupuesto en el inspector; PR #128 corrigió limpieza de canvas al desmontar y añadió QA de ciclo de vida. Estos cambios ya materializan lectura visual de ejecuciones, pero no añaden un endpoint de organización.

### Puntos de código que sustentan el diferencial

| Componente | Evidencia local | Qué prueba / límite |
|---|---|---|
| Proyección de la oficina live | `frontend/app/src/data/adapters/live/HttpAaoLiveAdapter.ts:getOrganizationStructure` y `src/aao/work_management_api.py:organization` | Consume directamente `/v1/organization`; cualquier 401/403/404/error de esquema/red permanece visible. No hay fallback a unidades inventadas o consultas adicionales. La proyección tiene cobertura por proyectos visibles, no es organigrama persistido. |
| Contrato/UI de oficina | `frontend/app/src/features/office/VirtualOfficeView.tsx`, `OfficeContextSidebar.tsx`, `frontend/app/src/domain/models.ts` | Selección visual, drawer, asignaciones, historial, evidencia y campos de modelo/proveedor. No crea trabajo ni representa autoridad nueva. |
| Escena y plan | `frontend/app/src/features/office/engine/ThreeOfficeScene.ts`, `Office2DPlan.tsx` | Ubicación visual por `unitId`; sin unidad canónica el adapter agrupa explícitamente como desconocido/no asignado. La escena no es fuente de datos. |
| UI React | `frontend/app/src/app/App.tsx` | Adapter live/demo separados, query keys ligadas a sesión, cancelación y limpieza de cache al cambiar origen/cerrar sesión. |
| Trabajo persistente | `src/aao/work_management_api.py:board`, `activity`, `projects`; migraciones y módulos de cola de ejecución | Board/eventos/execution journal con persistencia PostgreSQL y permisos por proyecto. No declara organigrama o heartbeat. |
| Tests de veracidad | `frontend/app/src/test/adapters.test.ts`, `office.test.tsx` | Verifica lease, no inferencia de unidad/tipo, permisos/capacidades y UI del inspector. Son pruebas de frontend/adapter; la autorización de la API se prueba aparte con PostgreSQL. |

A SHA `95d8427` no existía `/v1/organization`; se implementó en PR #129 (`e807a5f`). A la revisión actual `/v1/agents/{id}` sigue sin existir; el adapter obtiene detalle de la proyección canónica cuando se le solicita.

### Falta o no se encontró en el alcance

- Perfiles organizativos dinámicos persistidos y autorizados (unidad, rol, responsable y adscripción), integrados en la proyección existente sin conceder grants ni alterar datos de ejecución.
- Perfiles persistentes de rol, unidad y responsable; telemetría heartbeat. Hasta que existan, la UI no puede declarar organigrama real, responsable de unidad ni disponibilidad. La actividad por ejecución sí existe parcialmente; «activo» solo se prueba con lease vigente.
- Conversación CEO-agente persistente en el producto; equipos temporales padre/hijos durables; calendario/rutinas con ejecución servidor; visualización de conocimiento corporativo unificada; feedback/skills versionadas asociadas al catálogo.
- Experiencia de dirección de proyectos desde la oficina que cree trabajo con la misma API y límites de autoridad que Control Center.

## 5. Propuesta incremental

### F0 — Oficina de lectura sobre el estado real (prioridad inmediata)

**Backend (base ya implementada en PR #129):** mantener `GET /v1/organization` como proyección de lectura, no un almacén de trabajo paralelo. Derivarla de proyectos, work items, ejecución/lease y revisiones existentes; el siguiente incremento añade perfiles organizativos persistidos, separados de grants/credenciales. Mantener separación entre perfil de agente (si existe) y principal autenticado; no inferir unidad/rol de `worker_id`, de un grant o de una revisión. Incluir relaciones mínimas: unidad/rol/responsable solo si persistidos, identidad observada, asignación y ejecución vinculadas, estado evidenciado, timestamp de origen, fuente/IDs y cobertura. Si no existe perfil canónico, devolver identidad desconocida con la relación de trabajo observada. Aplicar permisos en backend: CEO lee el ámbito autorizado por su rol; agente solo proyectos con `project.read`; no expandir datos visibles al unir proyectos.

**Frontend:** consumir el contrato canónico sin fan-out ni sustitución si falta o es inválido; preservar `DataState` (ready/unavailable/forbidden/error), origen, evidencia y cobertura. Reutilizar vista, escena, inspector, query cache y navegación existentes. Selección de agente abre la identidad/actividad observadas; enlaces van a los proyectos/boards/actividad existentes. Sin estado de tareas replicado en el cliente.

**Aceptación:**
1. Integración con PostgreSQL crea principal, trabajo y ejecución; API y Control Center/oficina muestran los mismos IDs y estados, con vínculos y timestamps.
2. Cambio de asignación o ejecución se refleja tras refresco; el cliente no puede modificar estado operativo mediante interacción espacial.
3. Un principal sin actividad aparece como `unknown`/sin asignación, no «trabajando» ni «disponible» inferido.
4. Sin endpoint, 401/403, timeout o esquema desconocido: estado no disponible/denegado/error explícito, nunca sustitución por datos demo en modo live.
5. La respuesta respeta grants por proyecto; tests de backend verifican que no se filtra información a principals no autorizados.

**Pruebas ya existentes que deben conservarse/ampliarse:** `frontend/app/src/test/adapters.test.ts` contiene negativos sobre no inferir unidad/tipo por nombre, lease ausente/vencido/vigente, separación de grants y capacidades, y cobertura parcial; `frontend/app/src/test/office.test.tsx` comprueba el inspector e historial. No repetirlas sustituyendo la fuente real por fixtures. Añadir pruebas endpoint Postgres para scope CEO/AGENT, respuesta sin perfil organizativo y esquema consumible por el adapter; mantener fixture y live distinguidos.

### F1 — Navegación y dirección del trabajo existente

**Frontend:** en detalle de agente/unidad mostrar resumen de asignaciones, recientes y decisiones relacionadas, con CTA a proyecto, Kanban y Activity ya disponibles. La oficina es un mapa de navegación, no un segundo tablero.

**Backend:** reutilizar endpoints actuales (`POST /v1/projects/{id}/work`, admisión y stages autorizados). Extender solo si la respuesta no expone ID/actor/evidencia necesarios para el enlace. Sin ejecución directa por la escena.

**Aceptación:** desde un agente se llega a un trabajo existente; una solicitud de trabajo creada por la vía aprobada aparece inmediatamente en el board y la oficina a partir del mismo registro. Usuario sin grant no ve ni crea trabajo en ese proyecto.

### F2 — Conversación orientada a proyectos, no a proveedor

Definir una interfaz CEO-AAO persistente y con contexto de proyecto/agente. Separar mensajes informativos de órdenes. Una orden genera una propuesta/recurso de trabajo por API, con actor, proyecto, criterios y estado; una conversación no concede grants ni lanza herramientas. La UI consume estado y respuestas persistidas por backend. El piloto real de modelo no depende de esta fase.

**Aceptación:** reabrir sesión recupera conversación/eventos vinculados; petición que implique ejecución se enlaza a un work ID; petición ambigua no genera trabajo oculto; autorización denegada no invoca modelo; respuesta identifica qué ejecución/proveedor produjo resultado cuando haya evidencia.

### F3 — Equipos temporales y consolidación

Solo tras validar F0/F1. Si hay necesidad demostrada, backend representa un encargo padre, trabajos hijos paralelos, asignación a identidades temporales, relaciones de dependencia, fallos parciales y resultado consolidado. UI representa estructura y enlaces; la coordinación no vive en estado React. No copiar el protocolo de `teams.mjs`.

**Aceptación:** concurrencia y reintentos sobreviven reinicio; cada resultado tiene actor/ejecución/evidencia; consolidación referencia hijos completados y marca faltantes/conflictos; cancelar/reanudar no duplica efectos.

### F4 — Calendario, conocimiento y aprendizaje

Posponer scheduler y grafo rico. Primero mostrar historial/evidencia y decisiones pendientes que ya persisten. Si luego se aprueban rutinas, su definición, calendario, próxima fecha, ejecución, catch-up y aprobación son estado PostgreSQL y trabajo normal, no timer de navegador. Skills/correcciones versionadas y referenciadas desde capacidades; una corrección propuesta no cambia instrucciones activas automáticamente.

**Aceptación:** rutina vencida/reiniciada tiene comportamiento idempotente y audit trail; cualquier efecto externo exige la ruta autorizada; contenido de conocimiento enlaza fuente y revisión; correcciones no cambian una versión activa sin el flujo definido.

## 6. Pruebas transversales de aceptación

- **Fuente única:** toda tarea, identidad, asignación, ejecución y decisión operativa visible procede de la API persistente; no hay store local paralelo ni transición simulada en modo live.
- **No datos ficticios operativos:** tests diferencian live/demo; modo live nunca cae a fixtures; demo lleva indicador visible y al cambiar de origen se cancelan peticiones y limpian cachés.
- **Trazabilidad:** cada actividad lleva ID de sujeto/objeto y hora de backend; UI no convierte ausencia de evento en actividad.
- **Identidad/autoridad:** permisos servidor-side; selección visual no concede autoridad; identidad de proveedor/modelo es evidencia de ejecución, no identidad AAO.
- **Tolerancia:** escenarios unavailable/forbidden/error/unknown se renderizan claramente y no se confunden con “idle”.
- **No bloqueo de piloto:** pruebas de oficina son consumidoras de lecturas y no se agregan como dependencia al primer piloto con modelo real.

Estas pruebas son criterios de construcción y aceptación de producto; **no establecen auditoría formal, certificación del candidato ni gate de autonomía**.

## 7. Reparto de trabajo recomendado

| Orden | Backend / PostgreSQL | Frontend / oficina y Control Center |
|---|---|---|
| 1 | Contrato/proyección `/v1/organization`; permisos; evidencia/estado explícito desde filas existentes | Reemplazar el fan-out conservando las garantías actuales; limitar o marcar datos desconocidos; mantener ya existente el inspector, historial, modelos y navegación |
| 2 | Añadir al contrato solo IDs/campos que falten para atribución y trazabilidad | Completar enlaces del inspector a board/actividad por IDs; mostrar decisiones solo si proceden de estado existente |
| 3 | Diseñar persistencia de conversación solo después de validar flujo de trabajo y autorización | UI de conversación CEO-AAO ligada a proyecto; emitir órdenes por flujo de trabajo existente, no llamadas directas a modelo |
| 4 | Modelo padre/hijos, coordinador paralelo y scheduler durable solo si piloto/producto los justifica | Mostrar tareas hijas, calendario y conocimiento consumiendo contratos canónicos |

El siguiente incremento útil es añadir perfiles organizativos persistentes y declarados por una autoridad autorizada; la proyección y el adapter ya existen y ahora fallan cerrado. Conversación, equipos o rutinas no son requisitos para ese trabajo ni para la operación del motor de ejecución.

### Incremento de construcción siguiente: perfiles organizativos persistidos

- Se añade migración `015_organization_profiles.sql`: unidades y perfiles se almacenan en PostgreSQL y referencian identidades existentes; son metadatos y **no** grants, credenciales ni estado de ejecución.
- `PUT /v1/organization/units` y `PUT /v1/organization/profiles` son operaciones CEO-protegidas en el entorno de desarrollo/test, con registro de evento. Validan referencias declaradas; la jerarquía no puede auto-parentarse ni introducir ciclo directo por la ruta de escritura.
- `GET /v1/organization` integra el perfil y las unidades declaradas en su proyección; para agentes, solo devuelve su propio perfil y unidad asociada; CEO recibe el roster declarado. Una identidad sin actividad conserva estado UNKNOWN. La metadata organizativa no altera alcance de proyectos ni grants.
- El contrato del frontend acepta `managerId`; la visualización/edición de organigrama en la oficina aún requiere su propio incremento para que el CEO pueda gestionarlo desde la interfaz.
- Validación en el contenedor PostgreSQL desechable: pruebas focalizadas de persistencia/proyección y scope, `2 passed`; `compileall`, Ruff, `git diff --check`, TypeScript y suite frontend (136 tests) pasaron. No se ha ejecutado el conjunto completo ni CI.
- **Fusionado:** PR #134 en `fecb34ea3e60c93eee6816e5af9840f8ebb84564`; PostgreSQL suite local `650 passed`, frontend `136 passed`, TypeScript/build/compileall/Ruff/pip check pasan; PR CI y `main` CI verdes ([run 40233270842](https://github.com/autoaiorg/aao/actions/runs/40233270842)). Esto acredita los checks indicados, no una certificación.
- Siguiente: ampliar pruebas (ciclo jerárquico y límites de visibilidad), luego conectar representación/edición de perfiles en la oficina sin estado duplicado.

## 8. Límites y siguientes responsables

### Seguimiento de construcción (rama `feat/agents-office-aa-integration`)

- **F0 implementado por backend y cerrado en el adapter:** `GET /v1/organization` proyecta desde PostgreSQL los proyectos visibles, ejecuciones/revisiones y para AGENT valida credencial activa y `project.read` en SQL. El agente autenticado puede aparecer como identidad desconocida; el CEO ve identidades observadas en ejecuciones/revisiones. No escribe estado ni inventa adscripciones, heartbeat o capacidades. La unidad `unit-unassigned` solo es agrupación visual. El adapter no reconstituye departamentos ni hace fan-out si falla el contrato.
- **Evidencia local inicial:** prueba PostgreSQL `tests/test_project_workflow_integration.py::test_organization_projection_is_authenticated_and_project_scoped` pasó (`1 passed`) contra el contenedor desechable; `compileall`, Ruff focal y `git diff --check` pasaron. Esto no valida aún el conjunto completo ni CI.
- **Límite de cobertura:** no se añadieron perfiles organizativos ni heartbeat, y el endpoint no concede permisos. Los estados se deducen únicamente de filas de ejecución; un `RUNNING` sin lease vigente demostrable permanece desconocido/no activo. La interfaz ya no conserva la ruta de agregación anterior: si el backend no entrega un contrato válido, muestra unavailable/forbidden/error.
- **Siguiente trabajo:** persistir perfiles organizativos dinámicos (unidad, responsable y rol solo por declaración autorizada), exponerlos en la proyección con pruebas de scope y conectar la oficina a esos datos; no inventar presencia/heartbeat. El siguiente tramo de producto después de perfiles es F2: conversación persistente vinculada a proyectos y trabajo AAO, no chat directo a proveedor. F3/F4 siguen sujetos a necesidad validada.
- **F1 implementado en incremento posterior:** desde la ficha de un agente, cada asignación abre el Kanban del proyecto real seleccionado en el Control Center. El vínculo usa el `projectId` de la respuesta; no crea ni replica tareas. Test de interacción `office.test.tsx` verifica navegación con el mismo ID. PR #130, merge `cf8b397`; suite frontend y CI de main verdes.

- Esta investigación es referencia conceptual, no revisión de seguridad ni certificación de AAO.
- No se ha inspeccionado ni verificado en ejecución un entorno PostgreSQL vivo en este trabajo; el diferencial de backend se basa en rutas y código del repositorio.
- No se ejercitaron credenciales ni llamadas a modelo de Agents Office.
- **Siguiente owner:** PM/backend define contrato mínimo de proyección con frontend; frontend implementa consumo y tests una vez estable el contrato. CEO solo interviene si aparece decisión estratégica o riesgo reservado, no por decisiones ordinarias de interfaz.


### Incremento posterior: LIVE fail-closed (`fix/office-live-organization-fail-closed`)

- **Construcción:** se eliminó el fallback de `getOrganizationStructure()` que, ante ausencia/error del contrato, reconstruía la lista de agentes desde fan-out y añadía seis departamentos estáticos. Ahora consulta únicamente `GET /v1/organization`; credencial ausente, 403, 404, error de red y respuesta inválida permanecen como estados no disponibles/denegados/error. Así la interfaz operativa no muestra organigrama ficticio ni oculta el fallo del backend.
- **Pruebas focalizadas:** `frontend/app/src/test/adapters.test.ts` verifica contrato canónico, 404 sin fan-out, 403/schema error fail-closed y ausencia de consulta sin token.
- **Validación local:** TypeScript y suite frontend completas (136 tests), `npm run build` y `git diff --check` pasan. Build advierte chunks >500 kB y anotaciones de terceros Zod ya presentes; no son errores. PR/CI/merge quedan pendientes.

### Incremento en construcción: plano LIVE desde unidades dinámicas (`feat/live-office-dynamic-org`)

- **SHA de implementación:** `a79b258a4795be99ef8fe39b93164af472be5f69`.
- **Construido:** plano 2D, chips y panel lateral muestran códigos, nombres, descripciones y responsables tal como llegan de las unidades persistidas. El color heredado de las seis salas es solo una decoración, no determina afiliación ni nombre. LIVE permanece en plano 2D; el botón 3D se deshabilita porque representa únicamente la plantilla visual DEMO. Se conserva la agrupación explícita de agentes no adscritos, evitando que el selector los fuerce silenciosamente a la primera unidad.
- **Regresión:** prueba de unidad live con código/nombre no perteneciente al catálogo fijo y aserción de que el control 3D está deshabilitado; se conserva prueba de UNKNOWN/no adscrito.
- **Validación local observada:** PostgreSQL suite `650 passed`; TypeScript, suite frontend `137 passed`, build, `compileall`, Ruff, `pip check` y `git diff --check` pasan. Build conserva avisos de tamaño de chunk y anotaciones de Zod.
- **Pendiente:** CI de PR/main. Esto es un incremento visual parcial, no completa dirección de trabajo, UI de gestión de perfiles, conversación, equipos temporales, calendario, conocimiento o skills. F1-F4 permanecen por construir según la matriz de este documento.
