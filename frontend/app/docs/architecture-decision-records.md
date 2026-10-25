# Registros de Decisiones de Arquitectura (ADR) — AAO Frontend

**Fecha:** 25 de octubre de 2026  
**Documento:** AAO-FE-ADR-2026-10-25  
**Autor:** Antigravity (`aao-impl-ag`)  

---

## ADR 001: Adopción Incremental y Coexistencia con la Consola Clásica

### Contexto
El repositorio canónico `autoaiorg/aao` cuenta con una consola operativa histórica servida en `/` mediante `frontend/index.html`, `frontend/control-center.css` y `frontend/control-center.js`. Dicha consola está validada por la suite de pruebas `tests/test_control_center_ui.py` (23 tests de integración), que comprueba la respuesta del servidor en `/` y patrones exactos en el HTML y JS heredados. Cualquier modificación invasiva a estos archivos o a los endpoints de estáticos en `src/aao/work_management_api.py` rompería la compatibilidad hacia atrás o violaría los límites de dominio (al prohibirse tocar el backend en esta PR).

### Decisión
1. Preservar intactos `frontend/index.html`, `frontend/control-center.css` y `frontend/control-center.js` en la raíz de `frontend/`.
2. Implementar la nueva aplicación React/TypeScript/Vite exclusivamente dentro del subdirectorio aislado `frontend/app/`.
3. Compilar la aplicación estática de forma independiente (`frontend/app/dist`), permitiendo su ejecución local mediante `npm run preview` o mediante un servidor estático same-origin.
4. Mantener un enlace directo y visible en la barra lateral de la nueva interfaz hacia `/` para garantizar una transición fluida y accesible.

### Consecuencias
- **Positivas:** Coexistencia pacífica y sin regresiones; el 100% de los tests antiguos de Python pasan sin modificaciones; no se toca ningún archivo de backend en `src/aao/`.
- **Negativas / Compromisos:** La sustitución completa de la raíz `/` se delega a una fase posterior cuando exista una decisión formal de promoción y deprecación.

---

## ADR 002: Puerto de Datos (`AaoReadPort`) y Segregación Total entre Live y Demo

### Contexto
El Centro de Mando debe poder operar tanto en modo conectado con el backend PostgreSQL/FastAPI como en modo de demostración sin conexión para presentaciones ejecutivas o revisiones sin base de datos activa. Existe un riesgo crítico de seguridad y gobernanza si las fixtures sintéticas se confunden con evidencia real o si un fallo de red en modo live rellena silenciosamente métricas falsas.

### Decisión
1. Definir una interfaz tipada y desacoplada `AaoReadPort` en `src/data/ports/AaoReadPort.ts`.
2. Implementar `HttpAaoLiveAdapter` que consume los endpoints FastAPI autorizados mediante `fetch` con parseo defensivo Zod. Si un endpoint falla, devuelve estados discriminados explícitos (`unavailable`, `forbidden`, `error`). **Bajo ninguna circunstancia recurre a fixtures**.
3. Implementar `MockAaoDemoAdapter` que sirve exclusivamente fixtures sintéticas rotuladas con IDs prefijados (`demo-proj-...`, `demo-task-...`) y sin hashes SHA genuinos.
4. Conmutar el modo mediante control visual superior y mostrar de forma persistente e inamovible el banner:  
   `⚠ DEMO · DATOS SIMULADOS · SIN CONEXIÓN AL NÚCLEO`.
5. Al alternar entre Live y Demo, vaciar completamente la memoria de caché de TanStack Query (`queryClient.clear()`) para evitar cualquier filtración cruzada.

### Consecuencias
- **Positivas:** Separación estricta de responsabilidades; imposibilidad técnica de mezclar datos reales y simulados; veracidad absoluta conforme a la Regla 1 (No fabricated results).
- **Compromisos:** Requiere mantener las estructuras de fixtures alineadas con los esquemas de dominio.

---

## ADR 003: Estrategia de Oficina Virtual 3D (F4) y Límite de Render 2D Accesible

### Contexto
La visión a largo plazo de AAO incluye una oficina virtual 3D para la visualización espacial de agentes y salas de reunión (F4). Sin embargo, incluir bibliotecas pesadas como Three.js o WebGL en la entrega F1-F2 aumentaría drásticamente el tamaño del bundle, comprometería el presupuesto de rendimiento (&lt; 250 KB gzip) e introduciría riesgos de incompatibilidad en hardware sin aceleración gráfica.

### Decisión
1. **Exclusión estricta de Three.js en F1-F2:** No instalar ni empaquetar infraestructura 3D en esta PR.
2. **Diseño de puntos de extensión:** Reservar la ruta `/office3d` con una vista informativa (`VirtualOfficeView`) que detalla las especificaciones y contratos proyectados para F4.
3. **Principio de alternativa 2D obligatoria:** Toda métrica, tarea o estado que se visualice en la futura escena 3D dispondrá de un equivalente textual o tabular 2D totalmente navegable con teclado y lector de pantalla.
4. **Respeto a directivas de movimiento reducido:** Cualquier animación espacial futura se suprimirá cuando `prefers-reduced-motion: reduce` esté activo.

### Consecuencias
- **Positivas:** Bundle ultraligero (~128 KB gzip frente al objetivo de 250 KB); rendimiento óptimo; cumplimiento estricto de accesibilidad WCAG 2.2 AA.

---

## ADR 004: Resolución de Hallazgos de Revisión del CEO (Identidad, Aislamiento, Memoria Volátil y Accesibilidad)

### Contexto
Tras la revisión preliminar de la PR #99 por el CEO, se identificaron cuatro hallazgos críticos, complementados por precisiones en la segunda revisión:
1. **P0 — Identidad CEO:** Se detectó que el adaptador live devolvía una identidad CEO sintética estática sin comprobar su autenticidad contra el backend.
2. **P0 — Aislamiento de sesiones y política de memoria:** Riesgo de persistencia de datos previos en caché o colisión con peticiones asíncronas lentas tras logout o alternancia LIVE/DEMO. Necesidad de reconciliar la generación de `sessionId` con `crypto.randomUUID()` y eliminar cualquier ambigüedad documental sobre `sessionStorage`.
3. **P1 — Estados desconocidos:** La capa de parseo convertía silenciosamente estados no reconocidos a `INBOX`, comprometiendo la integridad semántica de los datos.
4. **P1 — Accesibilidad (WCAG 2.2 AA):** Existían contenedores `div` interactivos sin semántica adecuada de teclado ni atributos ARIA, y carencia de restauración de foco tras cierre de diálogos.

### Decisión
1. **Verificación real de identidad CEO:**
   - Eliminar la generación sintética de identidad CEO.
   - En sesión CEO, invocar `GET /v1/mandates` con la cabecera `X-CEO-Token`. Si el backend responde HTTP 200, la identidad se marca como `verificationStatus: 'verified'`. Si responde 403 o 503, se devuelve `forbidden` o `unavailable` sin asumir credenciales válidas.
2. **Aislamiento reforzado de sesiones y política estricta de memoria volátil:**
   - Generar `sessionId` obligatoriamente mediante Web Crypto nativo (`crypto.randomUUID()` con fallback a `crypto.getRandomValues()`).
   - **Eliminación taxativa del fallback pseudoaleatorio (`Math.random()`):** Si la API Web Crypto no estuviera disponible, el sistema arroja un error crítico explícito y deniega el arranque de sesión en lugar de degradar a generadores deterministas o inseguros.
   - **Memoria volátil exclusiva:** Las credenciales residen únicamente en el estado en memoria de React. Queda taxativamente prohibido el uso de `sessionStorage`, `localStorage`, `IndexedDB`, cookies o parámetros URL.
   - Vincular todas las claves de caché de TanStack Query a `sessionId`.
   - Implementar `HttpAaoLiveAdapter.abortAll()` para abortar inmediatamente todas las peticiones HTTP en vuelo al cerrar sesión o conmutar de modo, mitigando cualquier condición de carrera por respuestas de red retrasadas.
   - Ejecutar `queryClient.cancelQueries()` y `queryClient.clear()` en cada transición de credenciales.
3. **Supresión estricta de consultas antes de establecer sesión válida:**
   - En modo LIVE, no se despacha ninguna consulta autenticada a endpoints protegidos hasta que exista una sesión activa con token en memoria (`enabled: origin === 'demo' || isAuthenticated`).
   - Si no hay credencial, el adaptador `HttpAaoLiveAdapter` (con `requireAuth: true`) devuelve inmediatamente `{ kind: 'forbidden' }` sin realizar ninguna llamada de red `fetch`.
4. **Preservación estricta de estados no reconocidos:**
   - Eliminar cualquier mutación silenciosa a `INBOX` en `WorkItemSchema` y en `HttpAaoLiveAdapter`.
   - Preservar el valor textual exacto del estado en `task.status` y marcar `isUnrecognizedStatus: true`.
   - Segregar las tareas no canónicas en `unrecognizedItems` y presentarlas en una columna dedicada de aviso en el Kanban, manteniendo intacta la semántica del ciclo de 6 estados para las tareas válidas.
5. **Sustitución semántica de accesibilidad y restauración de foco:**
   - Sustituir los elementos `div` interactivos por `<button type="button">` con `aria-pressed` (en la cartera del Dashboard) y `aria-haspopup="dialog"` (en las tarjetas del Kanban).
   - Añadir soporte para cierre mediante tecla `Escape` en `TaskDetailDrawer` y modales de autenticación.
   - Implementar **restauración automática del foco** hacia el elemento detonante (`trigger button`) cuando un diálogo o drawer se cierra, garantizando conformidad WCAG 2.2 AA.
6. **Estratificación estricta de niveles de prueba:**
   - **Pruebas de Componentes e Integración (JSDOM):** Confinadas en `src/test/` (71 pruebas pasando bajo Vitest), validando contratos de datos, renderizado defensivo y lógica de componentes en DOM simulado.
   - **Pruebas Funcionales y E2E en Navegador Real (Playwright + Google Chrome):** Confinadas en `e2e/` (3 pruebas pasando bajo Chromium/Google Chrome real), validando navegación por teclado, foco activo real, eventos del motor de renderizado y ausencia de filtraciones en almacenamiento web real.

### Consecuencias
- **Positivas:** Conformidad estricta con la Regla 1 (No fabricated results) y con las directivas de seguridad, memoria volátil y accesibilidad de AAO; 100% de aislamiento entre sesiones de usuario; trazabilidad de datos no canónicos; suite integral de pruebas estratificadas (71 pruebas de componentes en Vitest + 3 pruebas funcionales en navegador real en Playwright) pasando exitosamente.
- **Limitación de Gobernanza (Bloqueo de Integración Activo):** La infraestructura actual de agentes no dispone aún de un mecanismo de acreditación criptográfica o PKI para verificar la autoridad e identidad de auditores independientes externos. En estricta aplicación de la Regla 6 de AGENTS.md y GOV-REV-001, **se mantiene expresamente el bloqueo de integración**; la Pull Request permanece en estado no fusionado a la espera de la decisión soberana del CEO.

---

## ADR 005: Modelado de Organización, Segregación de Plantilla vs Agentes Efímeros y Honestidad en Telemetría (Fase F3)

### Contexto
El Mandato Ejecutivo `AAO-CEO-F3-2026-10-25` autoriza el desarrollo de la Fase F3: Organización y Estructura de Agentes, estableciendo los siguientes requisitos no negociables:
1. Visualización de unidades organizativas, jerarquías de supervisión y puestos de responsabilidad.
2. Segregación estricta entre agentes persistentes de plantilla fija (`STANDING`) y agentes temporales delegados a tareas/evaluaciones (`EPHEMERAL`).
3. Matriz de competencias, capacidades y asignaciones por proyecto.
4. Contratos tipados y adaptadores desacoplados para futuros servicios del núcleo (`AaoReadPort`).
5. Principio de honestidad técnica: representar expresamente los estados no disponibles y **nunca inventar presencia, latidos (heartbeats) ni actividad operativa** sin telemetría verificada.
6. Vistas plenamente accesibles (WCAG 2.2 AA) con navegación por teclado y pruebas automatizadas en Vitest y Playwright real.
7. Ámbito estrictamente de solo lectura y observabilidad: sin mutaciones, sin creación operativa de agentes ni alteración de permisos.

### Decisión
1. **Contratos tipados y esquemas Zod en dominio:**
   - Se definen las interfaces `OrgUnit`, `AgentIdentity`, `AgentType`, `AgentHeartbeatStatus`, `AgentOperationalStatus`, `AgentCapability`, `AgentAssignment` y `OrganizationStructure` en `src/domain/models.ts`.
   - Se implementan parsers defensivos en tiempo de ejecución con Zod (`OrgUnitSchema`, `AgentIdentitySchema`, `OrganizationStructureSchema`) en `src/domain/validators.ts`.
2. **Segregación categórica de agentes:**
   - Se discrimina taxativamente entre agentes de plantilla persistente (`STANDING`, como Arquitecto Jefe, Auditor Principal, Custodio de Políticas) y agentes efímeros (`EPHEMERAL`, como ejecutores de propuestas W1, evaluadores de candidatos W2, escáneres SAST y sincronizadores documentales).
3. **Honestidad estricta en telemetría y latidos:**
   - El estado de telemetría de cada agente se computa de forma estricta: `HEALTHY` (latido reciente comprobado con marca temporal), `STALE` (latido vencido o desactualizado), `UNKNOWN` (sin proveedor de telemetría configurado) y `UNAVAILABLE` (servicio de telemetría inalcanzable).
   - Queda prohibido deducir que un agente está "vivo" o "en línea" únicamente por su registro o nombre.
4. **Desacoplamiento de adaptadores y fail-closed en LIVE:**
   - La interfaz `AaoReadPort` se extiende con `getOrganizationStructure(): Promise<DataState<OrganizationStructure>>` y `getAgentDetails(agentId: string): Promise<DataState<AgentIdentity>>`.
   - En `HttpAaoLiveAdapter`: Dado que el núcleo actual no expone aún `/v1/organization` ni `/v1/agents`, el adaptador devuelve de forma honesta `kind: 'unavailable'`, documentando que el módulo se activará cuando la API canónica publique dichos contratos.
   - En `MockAaoDemoAdapter`: Se provee una estructura completa de 6 unidades organizativas jerárquicas y 12 agentes representativos, etiquetados de forma visible como entidades sintéticas de demostración arquitectónica (`isSyntheticDemo: true`).
5. **Arquitectura de componentes y accesibilidad (WCAG 2.2 AA):**
   - Se implementa `OrganizationView.tsx` estructurado en tres sub-pestañas accesibles (`role="tab"`, `aria-selected`): Organigrama y Jerarquías, Plantilla y Agentes, y Matriz de Puestos y Capacidades.
   - Se implementa `AgentDetailDrawer.tsx` con atributos de diálogo accesible (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`), captura de tecla `Escape` y restauración garantizada del foco hacia el botón de apertura.
6. **Integración limpia en el Shell:**
   - Se activa la opción "Organización" en `SideNavigation.tsx` eliminando la etiqueta de fase futura.
   - En `App.tsx`, las consultas se enlazan al ciclo de vida del adaptador y se purgan ordenadamente al cambiar de sesión.

### Consecuencias
- **Positivas:** Entrega completa de los requisitos de F3 con cero acoplamiento indebido al núcleo; visualización clara de la jerarquía de AAO y límites de autoridad; 100% de pase en suites de prueba (86 pruebas en Vitest + 4 pruebas en navegador real Playwright Google Chrome + 23 pruebas de regresión en pytest).
- **Riesgos residuales:** El backend canónico no dispone todavía de endpoints operativos para F3; en consecuencia, en modo LIVE la vista reporta honestamente su indisponibilidad a la espera de la implementación de `/v1/organization` en el núcleo por el equipo responsable.
