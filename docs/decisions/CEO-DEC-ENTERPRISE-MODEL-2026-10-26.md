# CEO-DEC-ENTERPRISE-MODEL-2026-10-26
## Adopción del modelo operativo de empresa autónoma como objetivo final de AAO Self Development

**Estado:** APROBADA por el CEO el 2026-10-26; en vigor desde su integración en `main`
**Autoridad:** CEO — decisión estratégica (R3)
**Ámbito:** Mandato `CEO-MANDATE-AAO-SELF-DEV-20261019` y proyecto AAO — Self Development

### 1. Objeto

Se adopta el documento **«AAO — Modelo operativo de empresa autónoma de ingeniería de software»** (`AAO-ARCH-ENTERPRISE-OPERATING-MODEL`, versión 1.0.0, 2026-10-26) como **objetivo final** del mandato AAO Self Development, con las decisiones y condiciones de esta resolución.

- El documento se incorpora al repositorio **sin modificaciones** en `docs/architecture/AAO_ENTERPRISE_OPERATING_MODEL.md`.
- Su contenido queda identificado por sha256 `bbea003c09b3dfac651ee298ef104522703e6cc3e76031e6f60f415dd8347c49`.
- Cualquier versión posterior requiere una nueva decisión del CEO.

### 2. Estatus del documento

1. **Contenido adoptado.** Las decisiones D-01 a D-10, las fases y gates del §13, el piloto del §14 y los escenarios del §19 pasan a ser **objetivo vinculante del proyecto**, en los términos y con las condiciones de esta resolución.
2. **Cabecera del documento.** El estado `propuesta_no_aprobada` que figura en ella queda sustituido, para lo adoptado, por esta decisión.
3. **Contenido no adoptado como norma.** El resto (ejemplos, YAML ilustrativos, catálogos, correspondencias tentativas con el código, indicadores) se conserva como **orientación de diseño**, no como especificación vinculante.
4. **Prevalencia.** Se mantiene la cláusula del §22. El documento no autoriza por sí mismo ninguna operación. Ante conflicto prevalecen, por este orden:
   - la Constitución;
   - las políticas vigentes;
   - las decisiones del CEO, incluida esta;
   - el mandato;
   - el documento.

### 3. Decisiones D-01 a D-10

| ID | Decisión | Resolución | Condiciones vinculantes |
|---|---|---|---|
| D-01 | Modelar AAO como empresa con puestos y departamentos persistentes | **APROBADA CON CONDICIONES** | (a) La estructura organizativa (unidades, puestos, perfiles, asignaciones) es declarativa y **no concede autoridad**: los permisos efectivos solo nacen de grants emitidos por quien tenga competencia para ello. (b) La implantación parte de lo ya construido (perfiles y unidades de organización, grupos de trabajo, `work.coordinate`) y no lo duplica. |
| D-02 | Separar puesto, agente, modelo e instancia ejecutora | **APROBADA** | Se aplica el principio de que AAO conoce las capacidades de sus modelos, no sus nombres. El catálogo de capacidades (`model_profile`) y el router son la base. |
| D-03 | Gestionar el trabajo mediante entidades persistentes y protocolos versionados | **APROBADA CON CONDICIONES** | (a) Primero se implantan los cinco protocolos mínimos de la Fase 2: entrada y clasificación; planificación y asignación; implementación; revisión y aceptación; bloqueos y escalado. (b) Se reutilizan la cola de ejecución, los eventos y el journal existentes; no se crea un motor de workflows genérico antes de que esos cinco funcionen y superen su gate. (c) Cada instancia fija la versión del protocolo con la que nació. |
| D-04 | Formalizar estados, autoridades, controles, excepciones y escalados en protocolos | **APROBADA CON CONDICIONES** | (a) Un protocolo **nunca crea ni amplía autoridad** por su propia definición; las operaciones sensibles se autorizan con grants y políticas externos y protegidos. (b) Crear o modificar un protocolo que afecte a materias reservadas al CEO, a la auditoría independiente, a la integración o a la raíz de confianza requiere decisión del CEO. (c) Toda excepción declara objeto, alcance, autoridad, riesgo, controles compensatorios y caducidad, y no se extiende a otras actividades. |
| D-05 | Usar eventos durables sin convertirlos en permisos | **APROBADA** | Ningún evento, recomendación o registro autoriza por sí mismo una ejecución. Cada servicio ejecutor verifica la autoridad y las precondiciones en el momento de actuar. |
| D-06 | Tratar GitHub, Git y otras herramientas como adaptadores | **APROBADA CON CONDICIONES** | Cambiar de adaptador no cambia quién puede aprobar o integrar. Cambiar el repositorio canónico, el integrador o la custodia de sus claves es una operación de alto impacto que requiere decisión del CEO. |
| D-07 | Publicar el conocimiento oficial con procedencia y validación | **APROBADA CON CONDICIONES** | (a) Un resumen o documento generado por un agente no es conocimiento normativo hasta su aprobación. (b) Mientras no exista una unidad de Conocimiento con aprobador competente designado por el CEO, la publicación de documentos normativos (políticas, protocolos, decisiones) la aprueba el CEO. (c) Los documentos sustituidos se conservan con su relación de sucesión. |
| D-08 | Ampliar la autonomía exclusivamente por capacidades acreditadas y autorizadas | **APROBADA** | Toda ampliación de autonomía (nuevas clases de riesgo, activación del integrador, de R2 o de nuevos proveedores, o elevación del techo de autonomía) requiere decisión expresa del CEO (`autonomy.ceiling.raise`), apoyada en evidencia reproducible de la capacidad. |
| D-09 | Pilotar con AAO Self Development y cambios reversibles de bajo riesgo | **APROBADA CON CONDICIONES** | (a) El piloto es el del §14 (mejora menor del Control Center, reversible y fuera de áreas privilegiadas), con sus pruebas de resistencia. (b) Su ejecución completa forma parte del ensayo de aceptación del traspaso y aporta evidencia al criterio 9 de `CEO-DEC-AAO-CONSTRUCTION-2026-10-25`. (c) El integrador R1 solo interviene en ese ensayo, con la autorización que corresponda, nunca antes. |
| D-10 | Evolución incremental y preservación del núcleo de confianza | **APROBADA** | No se sustituyen ni se debilitan el integrador R1, la raíz de confianza, la auditoría independiente ni los controles vigentes sin autorización competente. Los cambios son pequeños, reversibles y verificables. |

### 4. Reparto entre construcción y traspaso

1. **Equipo constructor externo** (régimen de `CEO-DEC-AAO-CONSTRUCTION-2026-10-25`). Construye:
   - la **Fase 0**, completa;
   - de las **fases 1 a 4**, lo **mínimo necesario para ejecutar el piloto del §14**: organización piloto (Producto/Planificación, Ingeniería y Calidad, con Seguridad y Auditoría independientes), los cinco protocolos mínimos, colaboración entre unidades para ese piloto y trazabilidad de extremo a extremo.
2. **Condición de traspaso.** El traspaso de operaciones requiere, conjuntamente:
   - los 10 criterios del §4 de `CEO-DEC-AAO-CONSTRUCTION-2026-10-25`;
   - los gates de la Fase 0;
   - el piloto del §14 superado con sus pruebas de resistencia, sobre la revisión candidata.
3. **Después del traspaso**, AAO completa por sí misma, bajo su propio gobierno, el resto de las fases 3 a 5. El equipo constructor solo interviene si el CEO lo encarga expresamente.

### 5. Validación por escenarios

Los 15 escenarios del §19 son **obligatorios antes de declarar completo el modelo operativo**, cada uno con: actor competente, autoridad, entrada, estado, evidencias, resultado seguro, escalado y cierre. **No son condición del traspaso**; para el traspaso bastan las pruebas de resistencia del piloto del §14.

### 6. Lo que esta decisión no autoriza

Esta decisión no autoriza:
- R2 ni R3;
- despliegue en producción;
- nuevos privilegios, grants o delegaciones;
- activación de proveedores de modelos, del integrador ni de capacidades autónomas;
- la sustitución del CEO en sus materias reservadas.

Cada una de esas actuaciones requiere su propia decisión conforme al gobierno vigente.

### 7. Efectos sobre el mandato y la documentación

1. Se añade la **Adenda 1** al mandato `CEO-MANDATE-AAO-SELF-DEV-20261019`, con el texto aprobado junto con esta decisión.
2. El criterio de éxito vigente del mandato (el camino de extremo a extremo hasta la PR) se mantiene como **primer hito**; el modelo operativo adoptado pasa a ser el **objetivo final**.
3. `docs/CONSTRUCTION_PLAN.md` y `docs/HANDOVER_ACCEPTANCE_MATRIX.md` se actualizan con la correspondencia del Anexo A. Cada PR de construcción indica a qué fase y gate contribuye.

### Anexo A. Correspondencia operativa (informativa)

| Fase del modelo | Gate (§13) | Relación con la construcción y el traspaso |
|---|---|---|
| 0. Verificación y estabilización del núcleo | Protección de rama y autorización efectivas; evidencias reproducibles; identidades separadas; fail-closed; ciclo R1 demostrado o bloqueo mantenido | Criterios de traspaso 1 a 8; pendientes actuales de la matriz (B-2, vía real W2 con Apps, rulesets, raíz de confianza sobre el candidato) |
| 1. Organización persistente (piloto) | Se identifica quién puede actuar y con qué delegación sin texto improvisado; grants externos al perfil | Construcción, alcance piloto; parte de perfiles, unidades y `work.coordinate` |
| 2. Motor de protocolos mínimo | Instancia que sobrevive a reinicio, rechazo y reintento, sin duplicar efectos, con política superior protegida | Construcción: los cinco protocolos mínimos |
| 3. Colaboración interdepartamental | Una tarea cruza varias unidades y resuelve un bloqueo sin el CEO, dentro de competencias aprobadas | Construcción, solo lo que exige el piloto; el resto, AAO tras el traspaso |
| 4. Ingeniería de extremo a extremo | Trazabilidad bidireccional completa; promoción solo por integrador autorizado con SHA y dictámenes vigentes | Construcción, lo que exige el piloto; se demuestra en el ensayo de aceptación (criterio 9) |
| 5. Empresa operativa multiproyecto | Varios proyectos simultáneos, asignaciones recuperables, reservas respetadas, continuidad | AAO tras el traspaso |
| Piloto §14 | Gobierno, transiciones persistentes, independencia, recuperación, trazabilidad y escalado correctos; pruebas de resistencia superadas | Condición de traspaso |
| Escenarios §19 | Los 15 escenarios con evidencia | Antes de declarar completo el modelo; no condiciona el traspaso |
