Declaro la recusación: Codex participó en la autoría del código auditado. Continúo por la excepción **CEO-DEC-AUDIT-CODEX-2026-10-24**. Este dictamen es una auditoría sustituta con independencia limitada; no demuestra independencia funcional conforme a GOV-REV-001.

Veredicto: REJECT

El rechazo se fundamenta exclusivamente en los hallazgos A siguientes. Los escenarios descritos son deducciones de la lectura estática: **no ejecuté pruebas ni operaciones contra GitHub**.

Los hallazgos de categoría A son:

1. **A-01 — El token supuestamente acotado al ensayo solicita un filtro incorrecto. `self-authored` en su utilización desde el arnés.**  
   [github_app_auth.py:152](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_app_auth.py:152) envía `{"repository_names":[repo]}`; el parámetro REST para seleccionar nombres es `repositories`, alternativamente `repository_ids`. Después sólo exige HTTP 201 y un token: no comprueba sus repositorios accesibles.

   Por tanto, la restricción del token que utiliza `PUBLISH-AUDIT` **no queda establecida**. Si GitHub ignora el campo desconocido, el token conserva el alcance de la instalación, incluido el canónico para las Apps instaladas allí. La allowlist del arnés sigue bloqueando el destino canónico literal, pero no sustituye el acotamiento de la credencial. El comportamiento real del servidor ante ese campo no se verificó aquí. El mock reproduce el mismo parámetro incorrecto: [test_github_trial.py:139](/tmp/tmp.YLYdqes4RG/repo/tests/test_github_trial.py:139).

   Corrección: solicitar el alcance con el parámetro válido y comprobar mediante enumeración que el token sólo alcanza el destino autorizado. Esta dependencia, aunque no cambia en el diff, se inspeccionó por su uso en el archivo completo auditado.

2. **A-02 — La promoción omite la revalidación final del head y el tratamiento de incidentes. `self-authored`.**  
   Después de leer el head inicial, el arnés puede esperar hasta 300 segundos por los checks y publicar sin volver a consultar la PR. La mutación sólo condiciona `main` mediante `beforeOid`: [github_trial.py:393](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:393).

   La comprobación posterior sólo utiliza `merged` de la PR; no compara su head con el autorizado: [github_trial.py:409](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:409). Una respuesta con `merged=true` y otro head no impide PASS si coinciden los restantes campos. Además, las respuestas ambiguas y las discrepancias posteriores terminan en FAIL sin abrir un incidente ni congelar nuevas publicaciones.

   Esto incumple los controles de NT-03-2 y NT-09-4. Debe revalidarse inmediatamente antes de publicar y verificarse después el head; las discrepancias posteriores requieren el canal de incidentes.

3. **A-03 — A-09 puede emitir PASS por una causa distinta del permiso probado. `self-authored`.**  
   [github_trial.py:743](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:743) prueba el push del notificador contra `main` y acepta `_push_rejection_pass`, que admite rechazos genéricos por ruleset/GH013: [github_trial.py:201](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:201).

   Si se concede indebidamente `contents:write` al notificador, el ruleset A todavía puede rechazar ese push y **A-09 devuelve PASS**. Eso no demuestra el mínimo privilegio exigido. A-10 podría detectar separadamente el exceso, pero no corrige el resultado falso de A-09.

   Debe aislarse la denegación por permiso, utilizando una rama desechable sin esa protección y exigiendo la respuesta de autorización correspondiente.

4. **A-04 — El control positivo de A-14 admite un push sin actualización. `self-authored`.**  
   [github_trial.py:834](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:834) utiliza una rama determinada únicamente por el SHA del padre y considera suficiente que Git termine con código cero.

   Si esa rama ya apunta al padre, `Everything up-to-date` satisface el control y A-14 puede emitir PASS sin que GitHub haya aceptado una actualización positiva en esta ejecución. No se lee el ref antes ni después.

   Debe aplicarse también aquí una rama única por ejecución y comprobar su creación efectiva, como ya intenta hacer el modo de equivalencia.

Los hallazgos de categoría B, que no fundamentan el REJECT, son:

- **B-01 — La equivalencia falla con el identificador real del ejecutor. `self-authored`.**  
  [run_trial.sh:149](/tmp/tmp.YLYdqes4RG/repo/scripts/trial/run_trial.sh:149) genera un identificador con punto entre segundos y nanosegundos. [github_trial.py:574](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:574) sólo admite caracteres alfanuméricos y guiones. Incluso cumpliéndose las demás premisas, la ejecución termina en FAIL antes del control positivo. El test usa `trial123` y no detecta esta incompatibilidad.

- **B-02 — Los incidentes nuevos no pueden resolverse mediante la API existente del ledger. `self-authored`.**  
  [auditor_dispatch.py:223](/tmp/tmp.YLYdqes4RG/repo/src/aao/auditor_dispatch.py:223) guarda el identificador dentro de `incident`, sin `id` superior. [governance_ledger.py:68](/tmp/tmp.YLYdqes4RG/repo/src/aao/governance_ledger.py:68) sólo permite resolver filas de tipo `incident`; el verificador ampliado también busca el identificador superior. El bloqueo queda cerrado, pero la recuperación ordinaria de `integrator-incident` no funciona.

- **B-03 — P3-07 permite preparar una creación en lugar de una actualización no fast-forward. `self-authored`.**  
  [github_trial.py:951](/tmp/tmp.YLYdqes4RG/repo/src/aao/github_trial.py:951) admite que staging devuelva 404. El push posterior crea entonces una rama: no ejercita `non_fast_forward`. Puede producir FAIL con una protección correcta. Debe existir previamente un staging con un SHA divergente conocido.

- **B-04 — No todas las pruebas negativas nuevas prueban que su control sea imprescindible.**  
  Por ejemplo, [test_workflow_invariants.py:35](/tmp/tmp.YLYdqes4RG/repo/tests/test_workflow_invariants.py:35) prueba una copia local de la expresión regular, no el comprobador que inspecciona los workflows. Debilitar la expresión del comprobador puede dejar verde ese test. También hay verificaciones de seguridad del ejecutor basadas en presencia de texto. No ejecuté mutaciones; esta conclusión procede de inspeccionar las dependencias de las aserciones.

- **B-05 — El teardown de la sonda puede continuar tras fallar la destrucción de la clave.**  
  En [probe_app_setup.sh:13](/tmp/tmp.YLYdqes4RG/repo/scripts/trial/probe_app_setup.sh:13), el shell interno ejecuta `shred; rm` sin `set -e` ni enlace condicional. El éxito de `rm` oculta un fallo de `shred`. Debe propagarse ese error antes de continuar.

No registro hallazgos C adicionales.

Respecto a las ocho preguntas del encargo:

| Pregunta | Resultado de la inspección |
|---|---|
| 1. PASS atribuible a la operación y causa esperadas | **No queda garantizado:** A-02, A-03 y A-04. Los rechazos locales de stale lease se distinguen correctamente y A-04 del ensayo permanece NOT RUN. |
| 2. Acceso al canónico o destinos no listados | Los helpers bloquean el canónico literal y exigen allowlist. Persiste A-01 sobre la credencial. Además, [ceo_session.sh:104](/tmp/tmp.YLYdqes4RG/repo/scripts/governance/ceo_session.sh:104) escribe explícitamente la política de Actions del canónico; es un camino administrativo separado, contemplado en la decisión CEO-P2P3 §4. |
| 3. Equivalencia | No encontré un camino que convierta estas pruebas en PASS: permanecen pendientes o fallan. La enumeración sin filtro y paginada comprueba el alcance de la instalación examinada; B-01 impide completar el control positivo con el identificador real. |
| 4. Credenciales | No observé tokens en argv en los caminos normales revisados. Se pasan en memoria o en el entorno del hijo Git. No se verificaron permisos efectivos de `/proc`, aislamiento entre uids ni logs reales; no certifico ausencia absoluta de fugas. |
| 5. Ejecutor | Verifica sus bytes contra la revisión, exporta `src/` desde objetos Git y usa uids separados con `env -i`. Comprueba rulesets al inicio y al final del recorrido ordinario. No identifiqué una escalada concreta de un uid de agente a root u otro uid. |
| 6. Vinculación de evidencia | Incluye `run_id` y revisión; la recogida coteja archivo anunciado, rol, estado y salida observada. Eso mejora la correlación, pero no equivale por sí solo a evidencia independiente e inmutable. |
| 7. Arranque y procedimientos | La siembra ordinaria compara las protecciones restauradas y detiene el procedimiento ante fallo de verificación. No afirmo cierre ante cualquier error: existe B-05 y no se ensayaron fallos ni señales. |
| 8. Pruebas negativas nuevas | **No puede afirmarse que todas fallen al retirar su control:** B-04. No se ejecutaron pruebas ni mutaciones. |

El alcance revisado fue el diff solicitado de **33 archivos**, más los archivos completos `src/aao/github_trial.py` y `scripts/trial/run_trial.sh`, el contrato indicado y las dependencias citadas. HEAD quedó confirmado en **`2b3e9c16e520c21b2f9de15aeb9f442d7f36bc1c`**, con base **`e09a18aad4768cc9282fc794d6a3b8bd283437ee`**.

Sólo utilicé `git diff`, `git show`, `git log`, `git ls-files` y `git grep`, un comando por llamada. **No ejecuté pruebas**, no modifiqué archivos y no hice commit, push ni merge. No comprobé CI, configuración viva ni explotaciones.

La autoridad utilizada fue el encargo de lectura y auditoría sustituta del CEO. Quedan bloqueadas la aceptación técnica y la utilización de este dictamen para cerrar RA. El siguiente responsable es el PM: asignar las correcciones a sus propietarios y presentar una nueva revisión fijada para reaудitoría y verificación separada.