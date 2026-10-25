Declaro la recusación: Codex participó en la autoría y revisión previa de parte del alcance. Continúo por la excepción **CEO-DEC-AUDIT-CODEX-2026-10-24**. Este dictamen tiene independencia limitada; marco `self-authored` los hallazgos sobre código atribuido a Codex.

**Veredicto: REJECT.** Se fundamenta exclusivamente en los hallazgos A siguientes.

Revisión auditada: `50033ae97701c4158588dd18c3488a19425ced0e`. Alcance: el diff solicitado desde `e09a18aad4768cc9282fc794d6a3b8bd283437ee` —29 archivos—, los archivos completos `github_trial.py` y `run_trial.sh`, y los contratos y dependencias necesarios para seguir sus controles.

Todos los hallazgos proceden de lectura estática. Los escenarios descritos son deducciones del código, **no reproducciones ejecutadas**.

1. **A-01 — El nuevo canal de incidentes no conserva el bloqueo independiente. `self-authored`.**

   Hay tres obstáculos acumulativos:

   - El integrador crea la solicitud con modo `0640`, bajo su grupo; el servicio del auditor corre con `aao-ledger-read`, sin acceso concedido al grupo del integrador.
   - El dispatcher admite por defecto únicamente registros de confianza propiedad de root, mientras el bootstrap instala ese registro como `aao-trust`.
   - Incluso superados ambos obstáculos, escribe `type: integrator-incident`, mientras `open_incidents()` solo reconoce `type: incident`.

   Por tanto, borrar el marcador de congelación controlado por el integrador puede dejarlo sin el bloqueo duradero que debía imponer el ledger, una vez satisfechos los demás gates. La prueba existente de borrar el marcador introduce manualmente el tipo antiguo y no cubre este recorrido.

   Referencias: [integrator.py:44](/tmp/tmp.TIr4WJCCyC/repo/src/aao/integrator.py:44), [servicio del dispatcher:9](/tmp/tmp.TIr4WJCCyC/repo/deploy/systemd/aao-auditor-dispatch.service:9), [auditor_dispatch.py:134](/tmp/tmp.TIr4WJCCyC/repo/src/aao/auditor_dispatch.py:134), [auditor_dispatch.py:217](/tmp/tmp.TIr4WJCCyC/repo/src/aao/auditor_dispatch.py:217), [governance_ledger.py:171](/tmp/tmp.TIr4WJCCyC/repo/src/aao/governance_ledger.py:171), [prueba:2009](/tmp/tmp.TIr4WJCCyC/repo/tests/test_governance_mechanisms.py:2009).

2. **A-02 — `ceo_session.sh` permite que una copia de trabajo influya en código ejecutado con otra identidad.**

   Bajo el modelo de amenaza documentado —los agentes pueden modificar la copia de trabajo y su `.git`—, `fetch_rev()` usa su configuración y hooks. Después, `install_audit_runner()` exporta con `git show` sin `GIT_NO_REPLACE_OBJECTS=1` y lo instala mediante sudo.

   Un objeto de reemplazo puede hacer que el SHA nominal exporte otro runner. Ese runner se ejecuta después como `aao-auditor-alt`. La misma fuente se usa para exportar el script que opera con la identidad GitHub del CEO. Esto rompe la separación entre datos del implementador y código de otra identidad.

   Referencias: [ceo_session.sh:25](/tmp/tmp.TIr4WJCCyC/repo/scripts/governance/ceo_session.sh:25), [instalación:29](/tmp/tmp.TIr4WJCCyC/repo/scripts/governance/ceo_session.sh:29), [ejecución:36](/tmp/tmp.TIr4WJCCyC/repo/scripts/governance/ceo_session.sh:36), [exportación para el CEO:94](/tmp/tmp.TIr4WJCCyC/repo/scripts/governance/ceo_session.sh:94). La atribución individual de este archivo no queda desglosada en el commit mixto `b8f23f9`; no acredito independencia sobre él.

3. **A-03 — La promoción pierde la vinculación con el head y el árbol autorizados. `self-authored`.**

   Primero compara el head del listado con `AAO_GITHUB_TRIAL_PR_HEAD`; después lo sustituye por el head de otra respuesta, sin volver a compararlo. Un cambio entre ambas lecturas pasa esa comprobación.

   Además, en `phase=promote` acepta cualquier árbol sintácticamente válido si los padres coinciden. No recalcula el árbol de fusión ni lo contrasta con un registro protegido de la fase anterior. La verificación posterior compara contra ese mismo árbol recibido. Un commit con padres correctos y contenido distinto puede, con los checks exigidos, terminar en PASS.

   Incumple las garantías que deben demostrar NT-03-2 y NT-03-5.

   Referencias: [github_trial.py:272](/tmp/tmp.TIr4WJCCyC/repo/src/aao/github_trial.py:272), [segunda lectura:279](/tmp/tmp.TIr4WJCCyC/repo/src/aao/github_trial.py:279), [validación de promoción:320](/tmp/tmp.TIr4WJCCyC/repo/src/aao/github_trial.py:320), [PASS posterior:399](/tmp/tmp.TIr4WJCCyC/repo/src/aao/github_trial.py:399).

4. **A-04 — El gate de rulesets acepta protecciones que no cubren las refs previstas. `self-authored`.**

   `check_rulesets()` comprueba nombres, activación y determinados tipos de reglas, pero omite `conditions.ref_name.include/exclude`, los targets de A/B y los bypass de C.

   Por ejemplo, C puede excluir todos los tags, o B dejar de cubrir staging, y superar las comprobaciones inicial y final. Tampoco se conservan esas respuestas como snapshots de configuración efectiva, necesarios para vincular la evidencia conforme a §16.0.

   Referencias: [run_trial.sh:55](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:55), [predicado:58](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:58), [comprobación final:549](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:549).

5. **A-05 — Los PASS del supervisor pueden corresponder a otra revisión del componente. `self-authored`.**

   A-08, A-07 y P3-11 invocan unidades del supervisor instaladas en el host. El ejecutor no verifica que su código sea el exportado desde `REV`, ni registra su revisión efectiva. Después genera registros con `harness_revision=REV`.

   Una instalación anterior que conserve el comportamiento puede producir PASS aunque el componente de la revisión auditada haya perdido el control. El SHA del arnés no identifica por sí solo el SHA del componente probado.

   Referencias: [registro raíz:419](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:419), [unidad de atribución:434](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:434), [unidad watch:504](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:504), [PASS:519](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/run_trial.sh:519).

Los hallazgos B no determinan el REJECT:

- **B-01 — La sesión administrativa continúa tras un fallo crítico del ensayo.** Captura `trial_rc`, pero continúa incluso si vale `99` por restauración fallida, y llega a la operación sobre el canónico. Debe distinguir ese fallo de los resultados negativos previstos. [ceo_session.sh:89](/tmp/tmp.TIr4WJCCyC/repo/scripts/governance/ceo_session.sh:89).

- **B-02 — La secuencia del watch no se reserva conjuntamente con su publicación. `self-authored`.** Lee la secuencia fuera del bloqueo y comparte contador con los latidos. Puede reutilizar secuencias concurrentes; además, los latidos intercalados dejan huecos para un consumidor de eventos que exige continuidad exacta. [supervisor_service.py:323](/tmp/tmp.TIr4WJCCyC/repo/src/aao/supervisor_service.py:323), [supervisor.py:135](/tmp/tmp.TIr4WJCCyC/repo/src/aao/supervisor.py:135), [notifier.py:71](/tmp/tmp.TIr4WJCCyC/repo/src/aao/notifier.py:71).

- **B-03 — No queda demostrada la sensibilidad de todas las pruebas negativas.** Las del canal de incidentes sustituyen custodias y corren con un único uid. El test de workflows también admite un permiso inline como `permissions: {contents: write}` dentro de un job, porque su regex exige que `write` termine la línea. Esto afecta a controles compensatorios de P3-10. [test_integrator_incident_dispatch.py:45](/tmp/tmp.TIr4WJCCyC/repo/tests/test_integrator_incident_dispatch.py:45), [test_workflow_invariants.py:27](/tmp/tmp.TIr4WJCCyC/repo/tests/test_workflow_invariants.py:27).

- **B-04 — El control positivo de equivalencia puede ser una operación sin cambios. `self-authored`.** La rama depende únicamente del SHA; repetirlo puede producir `Everything up-to-date`. El código interpreta el exit 0 como push aceptado sin comprobar una actualización real. Esto debilita la evidencia positiva, aunque conserva correctamente `EQUIVALENCE-PENDING`. [github_trial.py:560](/tmp/tmp.TIr4WJCCyC/repo/src/aao/github_trial.py:560).

- **B-05 — No todos los errores de limpieza/restauración se propagan.** La restauración excepcional de la siembra silencia errores y no verifica el estado final; el recorrido normal sí compara configuraciones y falla si difieren. En el teardown, un fallo de `shred` puede quedar oculto por el `rm` posterior. [seed_trial_ci.sh:19](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/seed_trial_ci.sh:19), [probe_app_setup.sh:13](/tmp/tmp.TIr4WJCCyC/repo/scripts/trial/probe_app_setup.sh:13).

Como **C-01**, el runbook sigue describiendo como manuales pruebas ahora automatizadas y normaliza su `NOT RUN`; debe actualizarse. [CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md:82](/tmp/tmp.TIr4WJCCyC/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md:82).

Respuestas al encargo:

| Pregunta | Resultado |
|---|---|
| 1. PASS y causa real | Existen los caminos de falsa atribución descritos en A-03/A-05. Las negativas de push normalmente exigen rechazo remoto y ref intacta; A-04 evita contar el rechazo local como PASS. |
| 2. Canónico y allowlist | Los helpers nominalmente rechazan el canónico y exigen allowlist. Los nuevos scripts administrativos sí lo modifican expresamente; A-02 compromete la confianza en el código que ejecutan. |
| 3. Equivalencia | No encontré un retorno PASS en ese modo. Comprueba ausencia de instalación y alcance seleccionado exacto; el control positivo tiene B-04. Sigue pendiente. |
| 4. Credenciales | No observé tokens en argv en el recorrido normal. No acredito aislamiento completo por A-02 ni verifiqué permisos del host en ejecución. |
| 5. Ejecutor fijado y uids | Exporta `src/` desde git y usa `runuser` con `env -i`. Las excepciones y carencias son A-02, A-04 y A-05. |
| 6. Vinculación de evidencia | Hay validación de run ID, revisión del arnés y exit observado; falta identificar todos los componentes probados y conservar la configuración efectiva. |
| 7. Arranque y restauración | No falla cerrado ante todos los errores: B-01/B-05. |
| 8. Pruebas negativas | No puede afirmarse que todas fallen al retirar su control; B-03 muestra carencias concretas. |

**Pruebas ejecutadas: ninguna.** Solo utilicé comandos individuales `git diff`, `git show`, `git log`, `git ls-files` y `git grep`. No modifiqué archivos ni realicé operaciones en GitHub. No ejecuté pytest, pruebas de mutación, pruebas entre uids ni verificaciones del host.

Autoridad utilizada: el encargo de lectura y la excepción del CEO, sin facultades de promoción. Quedan bloqueantes A-01 a A-05. Siguiente acción: el PM debe asignar sus correcciones a los propietarios, fijar una revisión nueva y solicitar reauditoría; la revisión retroactiva de Antigravity sigue pendiente conforme a la excepción.