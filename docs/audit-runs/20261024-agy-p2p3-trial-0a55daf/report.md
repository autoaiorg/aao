# Dictamen de Auditoría Independiente — Arnés de Ensayo P2/P3 y Correcciones de Arranque Post-Raíz de Confianza (`0a55daf`)

## 0. Declaración de no participación e independencia

Yo, **Antigravity (`aao-auditor-alt`)**, actuando como **AUDITOR INDEPENDIENTE de AAO** autorizado por la resolución delegada en el Issue #25, **declaro que NO he participado en la autoría, el diseño, la implementación ni la revisión previa de desarrollo** del código, los scripts ni los procedimientos auditados en esta revisión (`0a55daf5ee08c7f10c6c56224da145228c549011`). La autoría corresponde a Codex ([`src/aao/github_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py), sus tests y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh)) y a Claude (el resto de `scripts/trial/`, `scripts/bootstrap/`, [`scripts/identity_separation.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh), [`scripts/test_identity_separation_container.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/test_identity_separation_container.sh), `scripts/github_apps/`, `deploy/trial/`, [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py), los procedimientos y la especificación/revisión de [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh)). Ambos autores están recusados respecto a lo que escribieron o especificaron. Mi única intervención previa sobre este ámbito consistió en las auditorías independientes de solo lectura sobre las revisiones `315be35e6742504fea7fed0d0c858c6803352dba`, `592d80713b8ca9d7586037861d401adc7a67be58` y `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`. En consecuencia, procedo a emitir el dictamen.

---

## 1. Alcance, pruebas ejecutadas y limitaciones de independencia

- **Repositorio y revisión auditada (`HEAD`):** `/tmp/tmp.YuuHP1aTuM/repo` en el commit exacto `0a55daf5ee08c7f10c6c56224da145228c549011`.
- **Diff auditado:** `git diff b392750ff9c06f33a7ef39dae4a27c43f422ff9c 0a55daf5ee08c7f10c6c56224da145228c549011 -- src tests scripts deploy docs/procedures` (8 archivos modificados, 134 inserciones, 6 eliminaciones):
  - [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md) (líneas 1–96);
  - [`docs/procedures/NT_TRACEABILITY.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/NT_TRACEABILITY.md) (líneas 11–24);
  - [`scripts/identity_separation.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh) (líneas 163–185);
  - [`scripts/test_identity_separation_container.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/test_identity_separation_container.sh) (líneas 126–140);
  - [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh) (líneas 74–79, 310–345);
  - [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py) (líneas 155–165);
  - [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_fork_pr_trial.py) (líneas 150–162);
  - [`tests/test_ra_controls.py`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_ra_controls.py) (líneas 110–170).
- **Archivos auditados íntegramente en `HEAD`:**
  - [`src/aao/github_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py) (líneas 1–1063);
  - [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh) (líneas 1–369);
  - [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py) (líneas 1–185) y [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_fork_pr_trial.py) (líneas 1–173);
  - Scripts y módulos de arranque y soporte en `HEAD`: [`scripts/identity_separation.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh) (líneas 1–263), [`scripts/test_identity_separation_container.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/test_identity_separation_container.sh) (líneas 1–162), [`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/bootstrap/host_bootstrap.sh) (líneas 1–360), [`scripts/verify_trust_root_host.py`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/verify_trust_root_host.py) (líneas 1–480), [`src/aao/trial_security.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/trial_security.py) (líneas 1–23), [`src/aao/github_app_auth.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_app_auth.py) (líneas 1–169), [`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/seed_trial_ci.sh) (líneas 1–35), [`scripts/trial/actions_approval.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/actions_approval.sh) (líneas 1–15) y [`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/probe_app_setup.sh) (líneas 1–37).
- **Contrato normativo:**
  - [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0 a §16.5, líneas 686–806);
  - [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) (líneas 1–162);
  - [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md) (decisiones del CEO del 2026-10-24, líneas 1–80);
  - [`docs/procedures/EQUIVALENCE_A01_A02_P302.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/EQUIVALENCE_A01_A02_P302.md) (líneas 1–75).
- **Pruebas realmente ejecutadas:** **Ninguna (`0` pruebas ejecutadas).** Conforme a las instrucciones obligatorias del encargo, **no se ejecutó `pytest`** ni ningún otro comando de prueba o script en este entorno; el CI del repositorio las ejecuta aparte.
- **Limitaciones de independencia:** Auditoría estática de solo lectura sobre los objetos Git en `0a55daf5ee08c7f10c6c56224da145228c549011`, utilizando exclusivamente comandos individuales `git log`, `git diff`, `git show`, `git ls-files` y `git grep`, sin ejecución dinámica de pruebas ni consultas en vivo a la API de GitHub o al estado del host fuera del repositorio.

---

## 2. Evaluación de las preguntas de auditoría (1 a 8)

### Pregunta 1: ¿Puede el arnés emitir PASS sin que el servidor de GitHub haya rechazado o aceptado realmente la operación por la causa esperada?

**No.** Todos los caminos de [`src/aao/github_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py), [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh) fallan cerrado (`FAIL`, `INCONCLUSIVE` o `NOT RUN`) ante rechazos del cliente, errores de red, respuestas ambiguas, evidencia de otra ejecución o cambios en el ref protegido:

1. **Distinción entre rechazo del servidor y fallo del lado del cliente (`git push`):**
   - [`_git_push`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L100-L144) captura `OSError` y `subprocess.TimeoutExpired` devolviendo `status: None` (sin `exit_code` ni `server_rejected: True`), y en ejecuciones completadas evalúa [`_is_server_rejection(stderr)`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L147-L154), que exige una línea `[remote rejected]` o `remote:` con motivo explícito del servidor (`protected branch`, `permission to .* denied`, `not permitted`, `GH\d+:`, `workflow`, `non-fast-forward` o `ruleset`). Un rechazo local (`[rejected] ... (fetch first)` o `(stale info)`) produce `server_rejected: False`.
   - [`_push_rejection_pass`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L203-L211) exige simultáneamente `exit_code != 0`, `server_rejected is True`, coincidencia de motivo y `unchanged is True` (verificado leyendo el SHA posterior de `main` mediante [`_verify_unchanged`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L173-L175)).
   - [`_denial_outcome`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L226-L233) y [`_rejection_attributable`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L214-L223) devuelven `FAIL` si el push fue aceptado, si el ref cambió o si `server_rejected` no es `True`, y devuelven `INCONCLUSIVE` (nunca `PASS`) si la respuesta menciona checks requeridos (`required (?:status )?checks?|status checks?|aao-audit|\btest\b`, línea 217) o si un `GH013` genérico no nombra la regla bajo prueba (`restrict updates` o `non-fast-forward`).
   - En `P3-07` ([`src/aao/github_trial.py:849-851`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L849-L851)) y `P3-12` ([`src/aao/github_trial.py:868-870`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L868-L870)), ambos esperan con [`_wait_required_checks`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L391-L420) a que `aao-audit` (publicado por `aao-auditor`) y `test` estén en verde antes de intentar el push forzado; si los checks no llegan a verde, devuelven `INCONCLUSIVE` sin empujar.
   - En `A-04` ([`src/aao/github_trial.py:658-663`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L658-L663)), dado que `--force-with-lease` aborta en el cliente Git (`stale info`), el arnés devuelve `NOT RUN` y remite a `A-03` / `P3-05`.
2. **Operaciones API y GraphQL (`A-03`, `P3-05`, `P3-03`, `P3-09`, `A-05`/`P3-06`, `A-14`):**
   - `A-03`/`P3-05` ([`src/aao/github_trial.py:777-812`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L777-L812)) mueven primero `main` a un candidato distinto con checks en verde y luego ejecutan la mutación GraphQL `updateRefs` con `beforeOid` obsoleto, exigiendo error con `"before"` o `"stale"` y verificando con `_verify_unchanged` que `main` permanece en el candidato.
   - `P3-09` ([`src/aao/github_trial.py:744-763`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L744-L763)) exige HTTP `403` o `405` atribuible a `restrict updates` (devolviendo `INCONCLUSIVE` si no lo nombra) y verifica con `GET /pulls/{number}` que `merged is False` y `state == "open"`.
   - `P3-03` ([`src/aao/github_trial.py:906-923`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L906-L923)) exige HTTP `403` con mensaje de `protected branch` / `required status check` / `required check` y `_verify_unchanged`.
   - `A-05`/`P3-06` ([`_merge_trial_pr`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L236-L384)) separan `phase=stage` (retorna `STAGED`, nunca `PASS`, líneas 324–325) y `phase=promote` (verifica padres `[base_sha, candidate]` y `tree`, espera `aao-audit` del `app_id` de `aao-auditor` y `test` en verde, actualiza `aao-staging/...`, ejecuta `updateRefs` con `beforeOid: base_sha` y verifica posteriormente `main`, `tree`, `parents` y `merged is True`, líneas 373–384).
   - `A-14` ([`src/aao/github_trial.py:708-743`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L708-L743)) exige rechazo del servidor por `workflows?.*permission`, inmutabilidad de `main` en el fork y aceptación del push positivo sin cambios en `.github/workflows/`.
3. **Automatización de `A-11` y `P3-10` ([`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py#L46-L142)):**
   - `FORK-BRANCH` (`líneas 46-73`): verifica que el commit local modifique `.github/workflows/`, que el repositorio sea fork de `parent` (`HTTP 200`), que `GET /repos/{parent}/installation` con el JWT de la App del implementador devuelva `404`, que el push al fork tenga éxito y que `GET /repos/{fork}/git/ref/heads/{branch}` confirme `pushed == head`.
   - `A-11` (`líneas 76-101`): abre la PR con `aao-pm` y solo emite `PASS` si `status == 201`, `(user.login).lower() == "aao-pm[bot]"`, `(head.repo.full_name).lower() == fork.lower()` y `head.sha == expected`.
   - `P3-10` (`líneas 104-142`): vincula los workflow runs a la PR por `(head_branch, head_repository.full_name, head_sha)`, consulta `GET /repos/{parent}/actions/runs/{id}/jobs?filter=all` para cada run, devuelve `FAIL` si `total_count > 0`, devuelve `PASS` únicamente cuando existen runs listados y todos tienen `count == 0` y `"action_required"` en `(status, conclusion)`, y devuelve `INCONCLUSIVE` si expira el plazo sin aparecer ningún run o sin quedar bloqueados.
4. **Exclusión de evidencia de otra ejecución ([`scripts/trial/run_trial.sh:115-130`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L115-L130)):**
   - `capture_evidence` filtra por `d.get("run_id") == os.environ["AAO_TRIAL_RUN_ID"]` y `d.get("role") == os.environ["AAO_TRIAL_ROLE"]`. Si un paso no genera evidencia en la ejecución actual, queda como `NOT RUN (no evidence from this run)`.

---

### Pregunta 2: ¿Puede algún camino tocar el repositorio canónico `autoaiorg/aao`, o un repositorio no listado de forma explícita? Atención especial a `PUBLISH-AUDIT`, `STAGE-COMMIT` y a la promoción.

**No.** El bloqueo contra `autoaiorg/aao` y contra repositorios fuera de la lista blanca explícita se aplica antes de emitir tokens o llamadas de red en todos los puntos de entrada:

1. **Filtro global `_trial_repo_allowed` ([`src/aao/github_trial.py:157-162, 1009-1010`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L157-L162)):**
   - Rechaza incondicionalmente `target == CANONICAL_REPO` (`"autoaiorg/aao"`, línea 50), incluso si `AAO_GITHUB_TRIAL_REPOS` lo incluyera, y exige pertenencia explícita a `AAO_GITHUB_TRIAL_REPOS`.
   - En `main()` (`líneas 1009-1010`), esta validación ocurre **antes** de `GitHubAppClient(args.role)` y de `client.installation_token(...)` (`líneas 1025-1037`), por lo que para un repositorio no permitido ni siquiera se solicita un token de instalación.
   - En [`src/aao/fork_pr_trial.py:155-162`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py#L155-L162), `main()` aplica igualmente `_trial_repo_allowed(*args.repo.split("/", 1))` y, tras la corrección de C-02 en `0a55daf` (`líneas 159-160`), valida también `_trial_repo_allowed(*parent.split("/", 1))` sobre `AAO_GITHUB_TRIAL_FORK_PARENT` antes de instanciar `GitHubAppClient(args.role)`.
2. **`PUBLISH-AUDIT` ([`src/aao/github_trial.py:556-570`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L556-L570)):**
   - Verifica `_trial_repo_allowed(owner, repo)` (`líneas 556-557`), exige `role == "aao-auditor"` (`líneas 559-560`) con UID validado (`validate_role_uid`, línea 1008), exige SHA completo de 40 hex (`líneas 561-563`), solicita un token de instalación acotado exclusivamente al repositorio de ensayo (`repository_names: [repo]` en [`src/aao/github_app_auth.py:148`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_app_auth.py#L148)) y revoca el token en el bloque `finally` (`líneas 1054-1059`). Un token acotado a `aao-governance-trial` no es válido para publicar checks en `autoaiorg/aao`.
3. **`STAGE-COMMIT` ([`src/aao/github_trial.py:556-557, 571-592`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L571-L592)):**
   - Verifica `_trial_repo_allowed(owner, repo)`, exige `role == "aao-integrator"`, restringe el nombre de rama a `r"aao-trial/[A-Za-z0-9._/-]{1,90}"` sin `".."`, verifica `AAO_GITHUB_TRIAL_EXPECTED_SHA` y empuja únicamente a `https://github.com/{owner}/{repo}.git`.
4. **Promoción (`_merge_trial_pr`, [`src/aao/github_trial.py:236-384`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L236-L384)):**
   - Comprueba explícitamente `if base.lower() == f"/repos/{CANONICAL_REPO}": return "NOT RUN", ...` (`líneas 237-238`), además del bloqueo previo en `main()` y `_run_test()`, exige `AAO_GITHUB_TRIAL_PR` y `AAO_GITHUB_TRIAL_PR_HEAD`, y resuelve `repositoryId` para GraphQL `updateRefs` desde `GET /repos/{owner}/{repo}` del repositorio de ensayo (`líneas 360-368`).
5. **Repositorios en [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh):**
   - `REPO` está fijado a `autoaiorg/aao-governance-trial` (`línea 14`). Los únicos otros repositorios pasados en `AAO_GITHUB_TRIAL_REPOS` son `autoaiorg/aao-trial-probe` (`A-14` y `A-10`, `líneas 160, 188, 295`) y los forks de ensayo `autoaiorg/aao-trial-{claude,codex,agy}` (`A-10` en `líneas 292-294` y `FORK-BRANCH` en `líneas 314, 322`). En `EQUIVALENCE` (`líneas 192, 266`), los forks de producción `autoaiorg/aao-{codex,claude,agy}` se consultan únicamente en modo lectura (`GET /installation/repositories` y `GET /repos/.../keys`) para verificar el alcance exacto de dos forks por implementador.

---

### Pregunta 3: ¿Puede el modo de equivalencia (A-01, A-02, P3-02) emitir PASS? ¿Demuestra la evidencia lo que dice: sin instalación en el repo de ensayo, alcance exacto en los forks y control positivo?

1. **Imposibilidad de emitir `PASS`:**
   - En [`src/aao/github_trial.py:423-511`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L423-L511), `_run_equivalence` solo puede devolver `"NOT RUN"`, `"FAIL"` o `"EQUIVALENCE-PENDING"` (`línea 511`); no existe ningún retorno `"PASS"`.
   - Fuera de `--equivalence`, invocar `A-01`, `A-02` o `P3-02` con un rol de implementador falla cerrado en [`src/aao/github_trial.py:609-610`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L609-L610) (`return "FAIL", "this equivalence-sensitive test cannot emit PASS outside explicit equivalence mode"`).
   - En [`src/aao/github_trial.py:1042`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L1042), `EQUIVALENCE-PENDING` produce código de salida `2` (distinto de `0`), y [`scripts/trial/run_trial.sh:232, 276`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L232) registra `EQUIVALENCE-PENDING` en `summary.tsv`.
2. **Verificación de las premisas y controles (P0, P1, P2, P3, P4, P4b):**
   - **P0 (identidad del repositorio protegido):** [`run_trial.sh:62-68, 193, 267`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L62-L68) obtiene `P0` mediante la App `aao-integrator` al inicio (`EXPECTED_REPO_ID`) y antes de cada prueba de equivalencia; [`evaluate_equivalence_premises`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L514-L535) exige `status == 200`, `full_name.lower() == "autoaiorg/aao-governance-trial"` e `id == expected_repo_id > 0`.
   - **P4 y P4b (ausencia de credenciales alternativas y control exclusivo de administración):** [`collect_impl_p4`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L80-L106) y [`user_manager_state`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L74-L79) verifican desde `root` que el UID no tenga `linger` en `/var/lib/systemd/linger/$uid` y que `user@$uid.service` esté `inactive`, y desde el propio UID que no existan `~/.config/gh/hosts.yml`, `~/.git-credentials`, archivos adicionales en `~/.config/aao` distintos de `{<app>.pem, <app>.json}`, ni referencias a `GH_TOKEN`/`GITHUB_TOKEN` en `~/.config/systemd/user` o `~/.config/environment.d`; además, consulta a GitHub para confirmar `deploy_keys_empty`, `outside_collaborators_clear` y `org_members_clear`. [`collect_p4b`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L107-L113) comprueba que `ceo_login == "alessbarb"`, `org_owners == ["alessbarb"]` y `repo_admins == ["alessbarb"]`. Si cualquiera falla, `_run_equivalence` retorna `FAIL` (`líneas 438-443`).
   - **P1 (ausencia de instalación en el repositorio de ensayo):** [`_run_equivalence`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L444-L448) ejecuta `client.app_request("GET", f"/repos/{owner}/{repo}/installation")` autenticado con el JWT de la App y exige `status == 404`.
   - **P2 (alcance exacto de la instalación en los forks):** solicita un token de instalación **sin** `repository_names` (`repository_names=False`, [`src/aao/github_trial.py:456`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L456)), comprueba con el JWT que `GET /app/installations/{id}` tenga `repository_selection == "selected"` (`líneas 460-464`), pagina todas las páginas de `GET /installation/repositories?per_page=100&page={page}` verificando consistencia de `total_count` (`líneas 468-484`), exige que `actual == forks` y que ni el repositorio de ensayo ni `autoaiorg/aao` estén incluidos (`líneas 485-489`), y revoca inmediatamente ese token (`DELETE /installation/token`, exigiendo `204`, `líneas 490-494`).
   - **P3 (control positivo):** emite un nuevo token acotado únicamente al fork de ensayo (`client.installation_token(*fork.split("/", 1))`, `líneas 496-499`) y realiza un `git push` real a `refs/heads/aao-trial/equivalence-{sha[:12]}` en dicho fork (`líneas 500-510`), exigiendo `status == 0`.

---

### Pregunta 4: ¿Puede el token de una App o del CEO filtrarse a argv, a los archivos de evidencia, a los logs del ejecutor o a otro uid?

**No.**

1. **Aislamiento de claves privadas y firma de JWT:**
   - [`load_app`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_app_auth.py#L56-L75) exige que el proceso corra bajo el UID del rol (`pwd.getpwnam(linux_user(app)).pw_uid == os.getuid()`) y que `~/.config/aao/{app}.pem` pertenezca a ese UID con modo exacto `0600`.
   - [`create_jwt`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_app_auth.py#L78-L90) firma mediante `openssl dgst -sha256 -sign` pasando la entrada por `stdin` y manteniendo el JWT exclusivamente en memoria.
2. **Tokens de instalación y token del CEO:**
   - El token del CEO se obtiene en memoria dentro del proceso que ya corre como UID `alessbarb` mediante `gh auth token --hostname github.com` ([`src/aao/github_trial.py:1014-1022`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L1014-L1022)), sin pasarse por `argv` ni por variables de entorno desde `run_trial.sh`.
   - [`_NoRedirect`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_app_auth.py#L40-L44) impide reenviar cabeceras `Authorization` ante redirecciones HTTP.
   - En [`_git_push`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L100-L144), la URL remota es `https://github.com/{repo}.git` (sin credenciales en `argv`), se eliminan variables `GIT_TRACE*` y `GIT_CURL_VERBOSE*`, se fuerza `GIT_TRACE_REDACT=1`, se preservan las entradas previas de `GIT_CONFIG_COUNT` (`core.hooksPath=/dev/null` y `core.fsmonitor=false`, `líneas 112-122`) y se inyecta `http.extraheader` únicamente en el entorno del subproceso `git` del mismo UID. En `stderr` se redactan tanto cabeceras `Authorization: Basic|Bearer` como el valor literal del token (`líneas 137-138`).
3. **Archivos de evidencia y logs:**
   - [`_redact`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L87-L92) reemplaza recursivamente cualquier campo cuyo nombre coincida con `token|authorization|private.?key` por `"[REDACTED]"`.
   - [`write_evidence`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L940-L987) escribe en `~/aao-trial-evidence` (modo `0700`) usando `tempfile.mkstemp` con permisos `0600`.
   - [`scripts/trial/run_trial.sh:114, 129, 368`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L114) crea `/var/log/aao-trial/$TS` como `root:root` con modo `0750` y aplica `chmod 0640` a los archivos recolectados.

---

### Pregunta 5: ¿El ejecutor (`run_trial.sh`) usa solo código exportado desde objetos git en la revisión fijada, ejecuta cada rol con su propio uid y con un entorno limpio, y comprueba los rulesets al principio y al final? ¿Puede un uid de agente influir en lo que el ejecutor ejecuta como root o como otro uid?

**Sí a las tres primeras; no a la última.**

1. **Exportación exclusiva desde objetos Git en `$REV`:**
   - [`scripts/trial/run_trial.sh:1-27`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L1-L27) exige `#!/bin/bash -p`, `$EUID == 0`, `$SUDO_USER == alessbarb`, comprueba que `/root/aao-src` sea un clon plano propiedad exclusiva de `root` sin permisos de escritura para grupo u otros (`! -uid 0` o `-perm /022` ausentes) y verifica que el propio script en ejecución (`/root/aao-src/scripts/trial/run_trial.sh`, `0:755`) tenga exactamente el mismo SHA-256 que el objeto Git `$REV:scripts/trial/run_trial.sh`.
   - En [`scripts/trial/run_trial.sh:28-43`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L28-L43), exporta `src/` mediante `git archive "$REV" src` hacia `/opt/aao-trial/$REV/src` (`root:root`, `go-w`) y extrae el registro de Apps con `git show "$REV:deploy/github-apps/aao-github-apps-registry.json"`. Todas las invocaciones de Python usan `/usr/bin/python3 -I` cargando exclusivamente `/opt/aao-trial/$REV/src`.
2. **Aislamiento por UID y entorno limpio:**
   - Cada paso de rol se ejecuta con `runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin ...` y configuración Git aislada (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `core.hooksPath=/dev/null`, `core.fsmonitor=false`) tanto en el bucle principal ([`scripts/trial/run_trial.sh:166-298`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L166-L298)) como en los tres pasos de `A-11`/`P3-10` (`FORK-BRANCH` como `aao-impl-codex`, `A-11` como `aao-pm` y `P3-10` como `aao-supervisor`, [`scripts/trial/run_trial.sh:310-356`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L310-L356)).
3. **Comprobación de rulesets al principio y al final:**
   - [`check_rulesets`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L53-L57) se ejecuta al inicio (`línea 58`) y al final (`línea 366`), verificando que los rulesets `25776805` (A), `25776806` (B) y `25776807` (C) estén `active`, que B exija `aao-audit` (`integration_id == 5448107`) y `test` sin `bypass_actors` y con `non_fast_forward` y `deletion`, que A tenga como único actor de bypass `[(5447984, "Integration")]` y que C proteja `tag` (`creation`, `update`, `deletion`).
4. **Imposibilidad de influencia cruzada entre UIDs o hacia `root`:**
   - Los directorios de trabajo por rol están bajo `/var/lib/aao-trial/work/$uid` ([`scripts/trial/run_trial.sh:44-50`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L44-L50), padres `root:root 0755`) y se validan con [`validate_role_workdir`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/trial_security.py#L11-L17) (`lstat`, directorio real sin symlinks, propietario `$uid`, modo `0700`).
   - En [`capture_evidence`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L115-L130), el propio UID del rol verifica con `os.lstat` que el archivo de evidencia sea un archivo regular sin symlink propiedad de `os.getuid()`, y lo vuelca mediante `/bin/cat` hacia el archivo destino abierto por `root` en `$LOG`. Los valores extraídos de la evidencia (`merge_sha` en `línea 234` y `fork_pr` en `línea 351`) son validados por expresiones regulares estrictas (`[0-9a-f]{40}` y `[1-9][0-9]*`) antes de ser consumidos por otro rol.

---

### Pregunta 6: ¿Cada evidencia queda ligada a la ejecución y a la revisión del arnés que la produjo (§16.0)?

**Sí.**
- [`scripts/trial/run_trial.sh:114`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L114) genera `TS=$(date -u +%Y%m%dT%H%M%S.%NZ)` y exporta `AAO_TRIAL_RUN_ID=$TS` y `AAO_TRIAL_HARNESS_REV=$REV`.
- Todas las invocaciones a `github_trial.py` y `fork_pr_trial.py` (incluidos `STAGE-COMMIT`, `PUBLISH-AUDIT`, `promote`, `EQUIVALENCE`, `A-10`, `FORK-BRANCH`, `A-11` y `P3-10`, [`scripts/trial/run_trial.sh:189, 204, 219, 237, 243, 271, 298, 314, 341, 346, 352`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L189)) pasan `AAO_TRIAL_RUN_ID`, `AAO_TRIAL_HARNESS_REV` y `AAO_TRIAL_CANDIDATE_SHA` (incluyendo ahora `FORK-BRANCH` en la línea 341 tras la corrección de C-02 en `0a55daf`).
- [`write_evidence`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py#L940-L981) graba en cada JSON `run_id`, `harness_revision`, `candidate_sha`, `shas`, `timestamp`, `test_id`, `status`, `reason`, `repo`, `role` y `app_id`, y [`scripts/trial/run_trial.sh:367`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L367) genera `$LOG/SHA256SUMS`.

---

### Pregunta 7: Arranque y procedimientos (`scripts/bootstrap/`, `scripts/identity_separation.sh`, `scripts/trial/seed_trial_ci.sh`, `actions_approval.sh`, `probe_app_setup.sh`): ¿falla cerrado ante cualquier error? ¿Restaura la siembra de CI la protección o detiene el ensayo?

**Sí.**

1. **Corrección del preflight de identidades en un host instalado ([`scripts/identity_separation.sh:166-185`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh#L166-L185)):**
   - En `b392750`, `host_bootstrap.sh --trust-root-upgrade` falló cerrado en la fase 1 (`identity_separation.sh`) porque `find /srv/aao -mindepth 1` recorría los subárboles creados posteriormente por la instalación de la raíz de confianza (`/srv/aao/mirror`, propiedad de `aao-integrator`, y `/srv/aao/frozen/<rol>/{tree,venv}`, propiedad de `aao-auditor` o `root` y con symlinks en `venv`).
   - En `0a55daf`, [`scripts/identity_separation.sh:170-184`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh#L170-L184) define `PRUNED=(/srv/aao/mirror)` más `/srv/aao/frozen/$c/{tree,venv}` para `aao-auditor`, `aao-auditor-alt`, `aao-integrator` y `aao-supervisor`. Antes de podarlos en `find`, comprueba para cada ruta `p`:
     `[[ ! -e $p && ! -L $p ]] || [[ -d $p && ! -L $p ]] || die "$p exists and is not a plain directory"` (`línea 173`).
   - De este modo: (a) ningún symlink plantado en una ruta podada puede superar el preflight; (b) los directorios padres `/srv`, `/srv/aao`, `/srv/aao/frozen` y `/srv/aao/frozen/$c` siguen validados por `check_path` (`líneas 156-163`) como directorios reales `aao-trust:aao-trust 0755` sin ACLs; (c) cualquier archivo o directorio ajeno fuera de `PRUNED` bajo `/srv/aao` sigue siendo inspeccionado por `find` y falla cerrado; y (d) durante `--trust-root-upgrade`, [`scripts/bootstrap/host_bootstrap.sh:341-345, 258-260`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/bootstrap/host_bootstrap.sh#L341-L345) mueve los árboles/venvs anteriores a `$BK`, los reconstruye desde cero con `freeze_trees` y ejecuta `verify_trust_root_host.py`.
2. **[`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/bootstrap/host_bootstrap.sh#L1-L360):**
   - Opera con `#!/bin/bash -p` y `set -euo pipefail`, sanea el entorno con `exec /usr/bin/env -i` (`líneas 30-32`), verifica que el clon `/root/aao-src` sea plano, limpio, en `$REV` y propiedad exclusiva de `root` (`líneas 72-75`), exige `9/9` en `verify_app_auth.py` (`líneas 148-155`), valida el informe y la atestación de `aao-auditor-alt` en una instantánea propiedad de `root` exigiendo `verdicts == {"APPROVE-TECHNICAL"}` (`líneas 198-224`), y en `--trust-root-upgrade` (`líneas 301-350`) exige descendencia fast-forward (`merge-base --is-ancestor "$OLD" "$REV"`), pre-valida `make_trust_root_files.py` antes de parar servicios, detiene timers y unidades oneshot verificando que ninguna siga activa, respalda configuración, unidades y árboles congelados en `/var/backups/aao-trust-root/...`, ejecuta `verify_trust_root_host.py` antes de habilitar el despacho del auditor y mantiene el integrador apagado a menos que se invoque `--enable-integrator` con todos los `RA-*` en `PASS` (`líneas 353-359`).
3. **[`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/seed_trial_ci.sh#L1-L35), [`scripts/trial/actions_approval.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/actions_approval.sh#L1-L15) y [`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/probe_app_setup.sh#L1-L37):**
   - `seed_trial_ci.sh` guarda la configuración normalizada de los rulesets A, B y C, verifica que estén `active` antes de empezar, registra `trap restore EXIT` para reactivar A y B ante cualquier fallo, sube `deploy/trial/test.yml`, restaura A y B y compara con `diff -q` la configuración posterior frente a la guardada, saliendo con código `1` (`PROTECTION NOT RESTORED: stop the trial`) si hay cualquier diferencia.
   - `actions_approval.sh` y `probe_app_setup.sh` usan `set -euo pipefail`, verifican el estado resultante y extraen scripts/manifiestos desde objetos Git en `$REV`.

---

### Pregunta 8: ¿Cada prueba negativa nueva fallaría si se revierte su control?

**Sí.**

1. **Pruebas nuevas en el diff `b392750..0a55daf`:**
   - [`scripts/test_identity_separation_container.sh:126-140`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/test_identity_separation_container.sh#L126-L140) (`T13`):
     - Verifica que un host instalado con `/srv/aao/frozen/<rol>/{tree,venv}` y `/srv/aao/mirror` pase el preflight (`línea 133`); si se revierte la poda `PRUNED`/`PRUNE_ARGS` en [`scripts/identity_separation.sh:170-184`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh#L170-L184), esta aserción falla.
     - Verifica que si una ruta podada (`/srv/aao/frozen/aao-supervisor/tree`) es un symlink, el preflight falle cerrado con `'aao-supervisor/tree exists and is not a plain directory'` (`líneas 134-136`); si se revierte la comprobación `[[ -d $p && ! -L $p ]]` de la línea 173, `-prune` ignoraría el symlink y esta prueba negativa fallaría.
     - Verifica que un archivo ajeno fuera de los subárboles podados (`/srv/aao/frozen/stray` propiedad de `aao-auditor`) siga haciendo fallar el preflight (`líneas 137-139`); si se podara `/srv/aao/frozen` completo en lugar de solo `tree` y `venv`, esta prueba negativa fallaría.
   - [`tests/test_fork_pr_trial.py:159-161`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_fork_pr_trial.py#L159-L161):
     - Configura `AAO_GITHUB_TRIAL_REPOS=f"{FORK},autoaiorg/aao"` y `AAO_GITHUB_TRIAL_FORK_PARENT="autoaiorg/aao"` e invoca `fpt.main(["FORK-BRANCH", "--repo", FORK, "--role", "aao-impl-codex"])`, exigiendo retorno `2` sin instanciar `GitHubAppClient`. Si se revierte la validación de `_trial_repo_allowed(*parent.split("/", 1))` en [`src/aao/fork_pr_trial.py:159-160`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py#L159-L160), `main()` llamaría a `GitHubAppClient` (disparando `pytest.fail("no credential may be loaded")`).
   - [`tests/test_ra_controls.py:113, 167`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_ra_controls.py#L113) y [`docs/procedures/NT_TRACEABILITY.md:14, 21`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/NT_TRACEABILITY.md#L14):
     - Vinculan mediante `@pytest.mark.nt("NT-02-3")` y `@pytest.mark.nt("NT-02-10")` las pruebas unitarias de atribución por cadena de push en forks y de inyectividad de `push_principals`, las cuales fallan si se elimina la verificación de cadena de eventos o el rechazo de principales compartidos.
2. **Pruebas negativas del arnés en [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_fork_pr_trial.py) y `tests/test_github_trial.py`:**
   - Todas las pruebas negativas de `FORK-BRANCH`, `A-11`, `P3-10`, atribución de rechazos del servidor (`_is_server_rejection`, `_rejection_attributable`), `_wait_required_checks` en `P3-07`/`P3-12` y premisas `P0`/`P4`/`P4b` verifican tanto el fallo cerrado ante cada violación como el caso positivo de control, de modo que revertir cualquiera de sus controles hace fallar la aserción correspondiente.

---

## 3. Clasificación de hallazgos (A / B / C)

### Categoría A (Controles eludibles, evidencia que afirma PASS falsamente, fuga de credenciales o acceso al repositorio canónico)
- **Ninguno (0 hallazgos).**

### Categoría B (Defectos funcionales o de robustez no eludibles que requieren seguimiento sin comprometer la validez de la evidencia ni la seguridad del repositorio canónico)
- **Ninguno (0 hallazgos).**

### Categoría C (Observaciones menores de higiene o defensa en profundidad)
- **Ninguno (0 hallazgos nuevos).** Se verifica que los tres hallazgos menores de la auditoría anterior sobre `b392750` quedaron cerrados en `0a55daf`:
  - **C-01 (cerrado):** `user_manager_state` incluye `|| true` en [`scripts/trial/run_trial.sh:77`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L77).
  - **C-02 (cerrado):** `FORK-BRANCH` recibe `AAO_TRIAL_CANDIDATE_SHA="$fork_head"` en [`scripts/trial/run_trial.sh:341`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh#L341) y [`src/aao/fork_pr_trial.py:159-160`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py#L159-L160) valida `_trial_repo_allowed` sobre `AAO_GITHUB_TRIAL_FORK_PARENT`.
  - **C-03 (cerrado):** [`tests/test_ra_controls.py:113, 167`](file:///tmp/tmp.YuuHP1aTuM/repo/tests/test_ra_controls.py#L113) y [`docs/procedures/NT_TRACEABILITY.md:14, 21`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/NT_TRACEABILITY.md#L14) están sincronizados con `@pytest.mark.nt("NT-02-3")` y `@pytest.mark.nt("NT-02-10")`.

---

## 4. Regla de parada y Dictamen final

De acuerdo con la regla de parada establecida en el contrato de auditoría (`REJECT` solo procede ante hallazgos de Categoría A) y habiendo verificado `0` hallazgos de Categoría A, `0` hallazgos de Categoría B y `0` hallazgos de Categoría C en la revisión `0a55daf5ee08c7f10c6c56224da145228c549011`:

Veredicto: APPROVE-TECHNICAL

---

## 5. Informe de cierre (`AGENTS.md` / `GOV-REV-001`)

- **Scope:** Auditoría independiente de solo lectura del diff `git diff b392750ff9c06f33a7ef39dae4a27c43f422ff9c 0a55daf5ee08c7f10c6c56224da145228c549011 -- src tests scripts deploy docs/procedures` y de los archivos completos [`src/aao/github_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/github_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh) (junto con [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.YuuHP1aTuM/repo/src/aao/fork_pr_trial.py), [`scripts/identity_separation.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/identity_separation.sh), [`scripts/test_identity_separation_container.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/test_identity_separation_container.sh) y los scripts de arranque y procedimientos) en `HEAD`, frente a [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0–§16.5), [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) y [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md).
- **Exact revision:** Base `b392750ff9c06f33a7ef39dae4a27c43f422ff9c` → HEAD `0a55daf5ee08c7f10c6c56224da145228c549011`.
- **Actions performed:**
  - Declaración expresa de no participación en la autoría, el diseño, la implementación o la revisión previa de desarrollo del código auditado.
  - Inspección estática íntegra utilizando únicamente comandos `git` individuales de solo lectura (`git log`, `git diff`, `git show`, `git grep`), sin tuberías, encadenamientos ni redirecciones, y sin modificar archivos ni escribir fuera del directorio temporal.
  - Verificación de las Preguntas 1 a 8 y del cierre de la corrección de preflight de identidades y de los hallazgos C-01..C-03 en `#84` (`b392750..0a55daf`).
- **Evidence and limitations:**
  - **Evidencia:** Citas exactas `archivo:línea` verificadas sobre el árbol Git en `0a55daf5ee08c7f10c6c56224da145228c549011`.
  - **Pruebas ejecutadas:** `0` (`pytest` no está permitido en este entorno; el CI del repositorio las ejecuta por separado).
  - **Limitaciones:** Análisis estático sobre el repositorio sin ejecución en vivo contra la API de GitHub ni inspección directa del sistema de archivos del host fuera del clon auditado.
- **Outstanding blockers:** Ninguno (`0` hallazgos A, `0` hallazgos B y `0` hallazgos C).
- **Authority used:** Auditor Independiente de AAO (`aao-auditor-alt` / Antigravity), autorizado por la resolución delegada en el Issue #25.
- **Next owner/action:** CEO (`alessbarb`) y PM del proyecto para registrar el dictamen `APPROVE-TECHNICAL` sobre `0a55daf5ee08c7f10c6c56224da145228c549011`, proceder si así lo decide el CEO con `--trust-root-upgrade` en [`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/bootstrap/host_bootstrap.sh) siguiendo [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](file:///tmp/tmp.YuuHP1aTuM/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md) y ejecutar el ensayo P2/P3 mediante [`scripts/trial/run_trial.sh`](file:///tmp/tmp.YuuHP1aTuM/repo/scripts/trial/run_trial.sh) desde `/root/aao-src` en la revisión auditada.
