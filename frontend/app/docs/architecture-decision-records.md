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

## ADR 004: Resolución de Hallazgos de Revisión del CEO (Identidad, Aislamiento y Accesibilidad)

### Contexto
Tras la revisión preliminar de la PR #99 por el CEO, se identificaron cuatro hallazgos críticos:
1. **P0 — Identidad CEO:** Se detectó que el adaptador live devolvía una identidad CEO sintética estática sin comprobar su autenticidad contra el backend.
2. **P0 — Aislamiento de sesiones:** Riesgo de persistencia de datos previos en caché o colisión con peticiones asíncronas lentas tras logout o alternancia LIVE/DEMO.
3. **P1 — Estados desconocidos:** La capa de parseo convertía silenciosamente estados no reconocidos a `INBOX`, comprometiendo la integridad semántica de los datos.
4. **P1 — Accesibilidad:** Existían contenedores `div` interactivos sin semántica adecuada de teclado ni atributos ARIA.

### Decisión
1. **Verificación real de identidad CEO:**
   - Eliminar la generación sintética de identidad CEO.
   - En sesión CEO, invocar `GET /v1/mandates` con la cabecera `X-CEO-Token`. Si el backend responde HTTP 200, la identidad se marca como `verificationStatus: 'verified'`. Si responde 403 o 503, se devuelve `forbidden` o `unavailable` sin asumir credenciales válidas.
2. **Aislamiento reforzado de sesiones:**
   - Incorporar un identificador de sesión volátil `sessionId` en `AuthContext` que rota obligatoriamente en cada inicio de sesión, cambio de credenciales, desconexión y alternancia de origen.
   - Vincular todas las claves de caché de TanStack Query a `sessionId`.
   - Implementar `HttpAaoLiveAdapter.abortAll()` para abortar inmediatamente todas las peticiones HTTP en vuelo al cerrar sesión o conmutar de modo.
   - Ejecutar `queryClient.cancelQueries()` y `queryClient.clear()` en cada transición de credenciales.
3. **Preservación estricta de estados no reconocidos:**
   - Eliminar cualquier mutación silenciosa a `INBOX` en `WorkItemSchema` y en `HttpAaoLiveAdapter`.
   - Preservar el valor textual exacto del estado en `task.status` y marcar `isUnrecognizedStatus: true`.
   - Segregar las tareas no canónicas en `unrecognizedItems` y presentarlas en una columna dedicada de aviso en el Kanban, manteniendo intacta la semántica del ciclo de 6 estados para las tareas válidas.
4. **Sustitución semántica de accesibilidad:**
   - Sustituir los elementos `div` interactivos por `<button type="button">` con `aria-pressed` (en la cartera del Dashboard) y `aria-haspopup="dialog"` (en las tarjetas del Kanban).
   - Añadir soporte para cierre mediante tecla `Escape` en `TaskDetailDrawer` y modales de autenticación.

### Consecuencias
- **Positivas:** Conformidad estricta con la Regla 1 (No fabricated results) y con las directivas de seguridad y accesibilidad de AAO; 100% de aislamiento entre sesiones de usuario; trazabilidad de datos no canónicos; 61 pruebas unitarias y de regresión pasando exitosamente.
