Declaro mi participación previa: Codex escribió parte del código auditado. Continúo como auditor sustituto por la excepción CEO-DEC-AUDIT-CODEX-2026-10-24. Los hallazgos sobre código atribuido a Codex llevan la marca `self-authored`. Esta revisión no acredita independencia plena.

Veredicto: REJECT

El rechazo se fundamenta exclusivamente en los hallazgos A siguientes. Los hallazgos B y C no determinan el rechazo.

**Alcance y revisión.** HEAD confirmado: `50033ae97701c4158588dd18c3488a19425ced0e`. Revisado el diff solicitado desde `0a55daf5ee08c7f10c6c56224da145228c549011`: 29 archivos, más contratos y dependencias de promoción, custodia y clasificación. Distingo regresiones del diff y defectos preexistentes relevantes para la cadena.

**A-01 — La congelación por incidente pierde su respaldo independiente — `self-authored`; introducido en el diff.**

El dispatch añade filas `integrator-incident`, pero `open_incidents()` únicamente reconoce filas `incident`. Por tanto, el incidente nuevo no activa el bloqueo del integrador. Si se elimina el archivo local `freeze`, escribible por el propio integrador, una promoción posterior puede superar ese control sin resolución del incidente.

Evidencia: [auditor_dispatch.py:217](/tmp/tmp.dkx0kDRJ20/repo/src/aao/auditor_dispatch.py:217), [governance_ledger.py:174](/tmp/tmp.dkx0kDRJ20/repo/src/aao/governance_ledger.py:174), [integrator.py:286](/tmp/tmp.dkx0kDRJ20/repo/src/aao/integrator.py:286).

La prueba de persistencia sigue insertando manualmente el tipo antiguo; no recorre el nuevo canal: [test_governance_mechanisms.py:2014](/tmp/tmp.dkx0kDRJ20/repo/tests/test_governance_mechanisms.py:2014). Deben alinearse escritura, detección y resolución, manteniendo las capacidades separadas de cada firmante.

**A-02 — El verificador ejecutado como root confía en configuración Git escribible por el auditor; preexistente.**

La instalación entrega todo el repositorio congelado del auditor, incluido `.git`, a `aao-auditor`. El verificador admite ese propietario y ejecuta como root `git status` con `safe.directory=*`, sin desactivar `core.fsmonitor`. Un proceso capaz de escribir como `aao-auditor` puede configurar un ejecutable de fsmonitor que Git invoque como root. Esto cruza la frontera de custodia y permitiría alterar el ancla, el estado del verificador o las claves.

Evidencia: [host_bootstrap.sh:247](/tmp/tmp.dkx0kDRJ20/repo/scripts/bootstrap/host_bootstrap.sh:247), [verify_trust_root_host.py:339](/tmp/tmp.dkx0kDRJ20/repo/scripts/verify_trust_root_host.py:339), [verify_trust_root_host.py:343](/tmp/tmp.dkx0kDRJ20/repo/scripts/verify_trust_root_host.py:343), [aao-trust-root-verify.service:7](/tmp/tmp.dkx0kDRJ20/repo/deploy/systemd/aao-trust-root-verify.service:7).

Es una conclusión estática: requiere escritura bajo el uid auditor; no he demostrado que el sandbox del candidato permita obtenerla. Las operaciones Git sobre ese repositorio deben ejecutarse sin privilegios y con configuración controlada.

**A-03 — Dependencias de seguridad pueden clasificarse como R1 — `self-authored`; preexistente.**

El clasificador parte de R1 y solo eleva por coincidencia de ruta. El mapa aprobado omite, entre otros, `src/aao/authorization_issuer.py`, `src/aao/identity_attribution.py`, `src/aao/pending_veto.py`, `src/aao/git_paths.py` y el propio `src/aao/protected_routes.py`.

Una PR que cambie exclusivamente esos controles conserva clasificación R1 tanto en el emisor como en la validación. Así puede eludir el bloqueo de cambios R2 aunque `enabled_risk_classes` contenga únicamente R1. La congelación del runtime limita cuándo se ejecutaría ese código; no corrige su integración bajo una clase insuficiente.

Evidencia: [protected_routes.py:81](/tmp/tmp.dkx0kDRJ20/repo/src/aao/protected_routes.py:81), [authorization_issuer.py:104](/tmp/tmp.dkx0kDRJ20/repo/src/aao/authorization_issuer.py:104) y [mapa completo de rutas](/tmp/tmp.dkx0kDRJ20/repo/docs/protected-routes.json:14). Corresponde al PM preparar la corrección de la lista normativa por su cauce R3.

Los restantes hallazgos son:

| ID | Clase | Hallazgo y evidencia |
|---|---|---|
| B-01 | B · `self-authored` | Las peticiones ordinarias del inbox quedan `0600` por `mkstemp`; el auditor tiene otro uid. Los incidentes quedan `0640`, pero con el grupo del integrador. Bloquean la lectura entre roles. [r1_pipeline.py:114](/tmp/tmp.dkx0kDRJ20/repo/src/aao/r1_pipeline.py:114), [integrator.py:53](/tmp/tmp.dkx0kDRJ20/repo/src/aao/integrator.py:53). |
| B-02 | B · `self-authored` | El nuevo lector de incidentes solo admite registro propiedad de root; el instalador lo crea propiedad de `aao-trust`. El canal falla con la instalación documentada. [auditor_dispatch.py:134](/tmp/tmp.dkx0kDRJ20/repo/src/aao/auditor_dispatch.py:134), [host_bootstrap.sh:264](/tmp/tmp.dkx0kDRJ20/repo/scripts/bootstrap/host_bootstrap.sh:264). |
| B-03 | B · `self-authored` | Si el supervisor todavía no ha anclado la fila recién añadida de auditoría, la emisión de autorización falla. Los siguientes dispatch omiten la petición porque ya existe `report.json`. El E2E fuerza un latido mediante monkeypatch, ocultando esa ventana. [auditor_dispatch.py:241](/tmp/tmp.dkx0kDRJ20/repo/src/aao/auditor_dispatch.py:241), [test_r1_runtime_e2e.py:303](/tmp/tmp.dkx0kDRJ20/repo/tests/test_r1_runtime_e2e.py:303). |
| B-04 | B · `self-authored` en la dependencia | El nuevo ruleset exige ambos checks al crear staging. El pipeline intenta crear esa rama antes de solicitar el gate que publica `aao-audit` sobre M. Hay una dependencia circular. [canonical_protection.py:49](/tmp/tmp.dkx0kDRJ20/repo/scripts/governance/canonical_protection.py:49), [r1_pipeline.py:280](/tmp/tmp.dkx0kDRJ20/repo/src/aao/r1_pipeline.py:280). |
| B-05 | B · `self-authored` | Watch comparte secuencia con los latidos, pero el notificador exige secuencia consecutiva. Un latido intermedio produce `event sequence gap`. La reserva de números para watch tampoco abarca toda la publicación bajo el lock compartido. [supervisor_service.py:323](/tmp/tmp.dkx0kDRJ20/repo/src/aao/supervisor_service.py:323), [notifier.py:72](/tmp/tmp.dkx0kDRJ20/repo/src/aao/notifier.py:72). |
| B-06 | B · `self-authored` | P3-04 exige `test` exitoso, pero no exige éxito del `aao-audit` del publicador incorrecto. Si ese check está fallido o pendiente, retirar la restricción de publicador aún puede dejar la actualización rechazada y producir un falso PASS. [github_trial.py:432](/tmp/tmp.dkx0kDRJ20/repo/src/aao/github_trial.py:432). |
| B-07 | B | Falta un separador entre la asignación de `EXC` y `[[ … ]]`. La rama con excepción no representa dos órdenes válidamente separadas y compromete el procedimiento `apply`. Detectado por lectura; no ejecutado. [ceo_session.sh:70](/tmp/tmp.dkx0kDRJ20/repo/scripts/governance/ceo_session.sh:70). |
| C-01 | C | El runbook sigue describiendo como manuales pruebas ahora automatizadas y presenta B-1 como lote futuro. Debe actualizarse para evitar interpretar omisiones como resultados esperados. [CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md:86](/tmp/tmp.dkx0kDRJ20/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md:86). |

Respuestas a las cinco preguntas:

1. **No queda acreditada la imposibilidad global de elusión.** La ruta contiene validación de APPROVE firmado y evidencias, autorización §6.1, latido, vetos, checks sobre M, CAS y autenticación de la App. Véanse [manifest_audit.py:444](/tmp/tmp.dkx0kDRJ20/repo/src/aao/manifest_audit.py:444), [integrator.py:210](/tmp/tmp.dkx0kDRJ20/repo/src/aao/integrator.py:210) y [r1_pipeline.py:294](/tmp/tmp.dkx0kDRJ20/repo/src/aao/r1_pipeline.py:294). R2/R3 están deshabilitados en el registro generado, pero A-03 permite clasificar controles como R1. El PASS del host se exige con antigüedad máxima de 26 horas, aunque A-02 compromete su frontera de confianza. No verifiqué la configuración efectiva de GitHub ni la semántica CAS del servidor.
2. **Sí existe una frontera de escritura indebida:** A-02 permite que metadatos del uid auditor sean ejecutados por root. Para inbox, informes, ancla, registro, latido, atribución y claves revisé las reglas previstas de custodia; no comprobé permisos efectivos del host. B-01 y B-02 muestran además incompatibilidades de lectura.
3. **No identifiqué una fuga directa de tokens a argv, archivos o sandbox en los caminos revisados.** Los pushes pasan la autorización mediante entorno y el sandbox usa un entorno limitado. Esto no constituye una prueba dinámica de confidencialidad; A-02 permitiría comprometer credenciales del host.
4. **El registro generado es estático y no contiene datos por PR.** El flujo previsto no requiere root por PR. Los fallos B impiden considerar demostrado su funcionamiento autónomo.
5. **No.** B-06 ofrece un contraejemplo de prueba negativa que puede seguir aprobando tras retirar el control. La prueba de incidentes usa el formato antiguo y varios ensayos sustituyen controles o comparten uid. No hay evidencia obtenida aquí de suficiencia por mutación.

**Evidencia, autoridad y límites.** Ejecuté únicamente lecturas mediante `git diff`, `git show`, `git log`, `git ls-files` y `git grep`. **No se ejecutaron pruebas**, incluido pytest, ni exploits, comprobaciones del host o consultas a GitHub. No modifiqué archivos ni realicé commit, push o merge. La autoridad utilizada fue el encargo de lectura y la excepción CEO indicada; este dictamen textual no es una autorización firmada §6.1 ni una certificación de independencia.

**Siguiente responsable:** el PM debe coordinar las correcciones A con los propietarios de código y custodia, preparar las modificaciones R3 que correspondan y presentar un SHA nuevo para revisión. Los A pendientes bloquean la aceptación de este paquete.