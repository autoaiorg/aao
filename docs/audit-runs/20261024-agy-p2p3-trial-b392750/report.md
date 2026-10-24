# Dictamen de Auditoría Independiente — Arnés de Ensayo P2/P3 y Correcciones de Arranque Post-Raíz de Confianza (`b392750`)

## 0. Declaración de no participación e independencia

Yo, **Antigravity (`aao-auditor-alt`)**, actuando como **AUDITOR INDEPENDIENTE de AAO** autorizado por la resolución delegada en el Issue #25, **declaro que NO he participado en la autoría, el diseño, la implementación ni la revisión previa de desarrollo** del código, los scripts ni los procedimientos auditados en esta revisión (`b392750ff9c06f33a7ef39dae4a27c43f422ff9c`). La autoría corresponde a Codex ([`src/aao/github_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py), sus tests y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh)) y a Claude (el resto de `scripts/trial/`, `scripts/bootstrap/`, `scripts/github_apps/`, `deploy/trial/`, [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py), las correcciones del lote #82 y la especificación/revisión de [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh)). Ambos autores están recusados respecto a lo que escribieron o especificaron. Mi única intervención previa sobre este ámbito consistió en las auditorías independientes de solo lectura sobre las revisiones `315be35e6742504fea7fed0d0c858c6803352dba` y `592d80713b8ca9d7586037861d401adc7a67be58`. En consecuencia, procedo a emitir el dictamen.

---

## 1. Alcance, pruebas ejecutadas y limitaciones de independencia

- **Repositorio y revisión auditada (`HEAD`):** `/tmp/tmp.hgVEZyY2zo/repo` en el commit exacto `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`.
- **Diff auditado:** `git diff 592d80713b8ca9d7586037861d401adc7a67be58 b392750ff9c06f33a7ef39dae4a27c43f422ff9c -- src tests scripts deploy docs/procedures` (15 archivos modificados, 796 inserciones, 100 eliminaciones).
- **Archivos auditados íntegramente en `HEAD`:**
  - [`src/aao/github_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py) (líneas 1–1063);
  - [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh) (líneas 1–369);
  - [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py) (líneas 1–183) y [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_fork_pr_trial.py) (líneas 1–170);
  - Módulos y scripts de soporte y arranque en `HEAD`: [`src/aao/trial_security.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/trial_security.py), [`src/aao/github_app_auth.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py), [`src/aao/auditor_dispatch.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/auditor_dispatch.py), [`src/aao/authorization_issuer.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/authorization_issuer.py), [`src/aao/supervisor_service.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/supervisor_service.py), [`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/seed_trial_ci.sh), [`scripts/trial/actions_approval.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/actions_approval.sh), [`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/probe_app_setup.sh), [`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/bootstrap/host_bootstrap.sh) y [`deploy/trial/test.yml`](file:///tmp/tmp.hgVEZyY2zo/repo/deploy/trial/test.yml).
- **Contrato normativo:**
  - [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0 a §16.5, líneas 684–806);
  - [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) (líneas 1–162);
  - [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md) (decisiones del CEO del 2026-10-24, líneas 1–80);
  - [`docs/procedures/EQUIVALENCE_A01_A02_P302.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/procedures/EQUIVALENCE_A01_A02_P302.md) (líneas 1–75).
- **Pruebas realmente ejecutadas:** **Ninguna (`0` pruebas ejecutadas).** Conforme a las instrucciones obligatorias del encargo, **no se ejecutó `pytest`** ni ningún otro comando de prueba o script en este entorno; el CI del repositorio las ejecuta aparte.
- **Limitaciones de independencia:** Auditoría estática de solo lectura sobre los objetos Git en `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`, utilizando exclusivamente comandos individuales `git log`, `git diff`, `git show`, `git ls-files` y `git grep`, sin ejecución dinámica de pruebas ni consultas en vivo a la API de GitHub o al estado del host fuera del repositorio.

---

## 2. Evaluación de las preguntas de auditoría (1 a 8)

### Pregunta 1: ¿Puede el arnés emitir PASS sin que el servidor de GitHub haya rechazado o aceptado realmente la operación por la causa esperada?

**No.** Todos los caminos de [`src/aao/github_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py), [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh) fallan cerrado (`FAIL`, `INCONCLUSIVE` o `NOT RUN`) ante rechazos del cliente, errores de transporte, causas ambiguas, evidencia de otra ejecución o mutación inesperada de refs:

1. **Distinción entre rechazo del servidor y fallo del lado del cliente (`git push`):**
   - [`_git_push`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L100-L144) captura `OSError` y `subprocess.TimeoutExpired` devolviendo `status: None` (sin `exit_code` ni `server_rejected: True`), y en ejecuciones completadas evalúa [`_is_server_rejection(stderr)`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L147-L154), que exige una línea `[remote rejected]` o `remote:` con causa explícita del servidor (`protected branch`, `permission to .* denied`, `not permitted`, `GH\d+:`, `workflow`, `non-fast-forward` o `ruleset`). Un rechazo local (`[rejected] ... (fetch first)` o `(stale info)`) produce `server_rejected: False`.
   - [`_push_rejection_pass`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L203-L211) exige simultáneamente `exit_code != 0`, `server_rejected is True`, coincidencia de motivo y `unchanged is True` (comprobado leyendo el SHA posterior de `main` mediante [`_verify_unchanged`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L173-L175)).
   - [`_denial_outcome`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L226-L233) y [`_rejection_attributable`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L214-L223) devuelven `FAIL` si el push fue aceptado, si el ref cambió o si `server_rejected` no es `True`, y devuelven `INCONCLUSIVE` (nunca `PASS`) si la respuesta menciona checks requeridos (`required (?:status )?checks?|status checks?|aao-audit|\btest\b`, línea 217) o si un `GH013` genérico no nombra la regla específica (`restrict updates` o `non-fast-forward`).
   - En `P3-07` ([`src/aao/github_trial.py:849-851`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L849-L851)) y `P3-12` ([`src/aao/github_trial.py:868-870`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L868-L870)), se corrigió el hallazgo B-01.3 de `592d807`: ambos esperan ahora con [`_wait_required_checks`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L391-L420) a que `aao-audit` (publicado por `aao-auditor`) y `test` estén en verde antes de intentar el push forzado; si los checks no están en verde, devuelven `INCONCLUSIVE` sin empujar.
   - En `A-04` ([`src/aao/github_trial.py:658-663`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L658-L663)), dado que `--force-with-lease` aborta en el cliente Git (`stale info`), el arnés devuelve explícitamente `NOT RUN` y remite a la prueba CAS del lado del servidor (`A-03` / `P3-05`).
2. **Operaciones API y GraphQL (`A-03`, `P3-05`, `P3-03`, `P3-09`, `A-05`/`P3-06`, `A-14`):**
   - `A-03`/`P3-05` ([`src/aao/github_trial.py:777-812`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L777-L812)) mueven primero `main` a un candidato distinto con checks en verde y luego ejecutan la mutación GraphQL `updateRefs` con `beforeOid` obsoleto, exigiendo error con `"before"` o `"stale"` y verificando con `_verify_unchanged` que `main` permanece en el candidato.
   - `P3-09` ([`src/aao/github_trial.py:744-763`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L744-L763)) exige HTTP `403` o `405` atribuible a `restrict updates` (devolviendo `INCONCLUSIVE` si el rechazo no nombra la regla) y comprueba mediante `GET /pulls/{number}` que `merged is False` y `state == "open"`.
   - `A-14` ([`src/aao/github_trial.py:708-743`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L708-L743)) exige el rechazo del servidor por falta del permiso `workflows` (`re.search(r"workflows?.{0,12}permission", message)`), comprueba que `main` del fork no cambió y exige a continuación un push de control positivo exitoso del commit padre sin cambios en `.github/workflows/`.
3. **Automatización de `FORK-BRANCH`, `A-11` y `P3-10` ([`src/aao/fork_pr_trial.py:45-147`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L45-L147)):**
   - [`fork_branch`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L45-L73) verifica que el commit local modifique `.github/workflows/`, que el repositorio sea fork de `parent` (`HTTP 200`), que `GET /repos/{parent}/installation` con el JWT de la App del implementador devuelva `404`, y que el push al fork deje el ref remoto exactamente en `head`.
   - [`open_pr`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L76-L100) (`A-11`) exige `HTTP 201`, autor `aao-pm[bot]`, `head.repo.full_name == fork`, `head.sha == expected` y `base.repo.full_name == parent`.
   - [`approval_gate`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L103-L147) (`P3-10`) verifica primero en `GET /repos/{parent}/pulls/{number}` que la PR sigue apuntando a `(fork, branch, head)` (si no, devuelve `INCONCLUSIVE`), filtra las ejecuciones de `/actions/runs?event=pull_request&head_sha={head}` por `head_branch == branch` y `head_repository.full_name == fork`, consulta `/actions/runs/{id}/jobs?filter=all` para cada run, devuelve `FAIL` si algún run tiene `total_count > 0`, y solo emite `PASS` si existe al menos un run listado y todos están en `action_required` con `0` jobs ejecutados (si se agota `P310_WAIT_SECONDS` sin runs o con runs aún en cola, devuelve `INCONCLUSIVE`).
4. **Errores de red, respuestas malformadas y evidencia de otra ejecución:**
   - [`GitHubAppClient._request`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py#L127-L128) convierte cualquier `OSError`/`URLError` en `GitHubAuthError`, que [`github_trial.py:1042-1053`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L1042-L1053) y [`fork_pr_trial.py:172-177`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L172-L177) registran como `NOT RUN` (código de salida `2`).
   - [`capture_evidence`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L115-L130) filtra los archivos en `~/aao-trial-evidence` exigiendo `d.get("run_id") == os.environ["AAO_TRIAL_RUN_ID"]` y coincidencia de `role`; si no hay evidencia emitida en la ejecución actual, el estado se fija en `NOT RUN (no evidence from this run)` ([`scripts/trial/run_trial.sh:232, 303, 319`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L232)).

---

### Pregunta 2: ¿Puede algún camino tocar el repositorio canónico `autoaiorg/aao`, o un repositorio no listado de forma explícita?

**No.** Existen barreras redundantes que impiden tocar `autoaiorg/aao` o cualquier repositorio fuera de la lista explícita:

1. **Bloqueo incondicional en `_trial_repo_allowed` y antes de autenticar:**
   - [`_trial_repo_allowed(owner, repo)`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L157-L162) rechaza `CANONICAL_REPO = "autoaiorg/aao"` (`línea 47`) incluso si figurara en `AAO_GITHUB_TRIAL_REPOS`, y exige que `owner/repo` esté explícitamente listado en `AAO_GITHUB_TRIAL_REPOS`.
   - Tanto [`github_trial.py:main()`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L1009-L1010) como [`fork_pr_trial.py:main()`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L156-L157) validan `_trial_repo_allowed` **antes** de instanciar `GitHubAppClient`, leer claves privadas o solicitar tokens.
2. **`PUBLISH-AUDIT` ([`src/aao/github_trial.py:556-570`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L556-L570)):**
   - Comprueba `_trial_repo_allowed` en `main()` (`línea 1009`) y de nuevo en `_run_test()` (`línea 556`).
   - Exige `role == "aao-auditor"` (`línea 559`) y un SHA explícito de 40 caracteres hexadecimales en `AAO_GITHUB_TRIAL_SHA` (`líneas 561-563`).
   - Además, [`client.installation_token(owner, repo)`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py#L134-L149) solicita el token de instalación restringido exclusivamente al repositorio objetivo mediante `body = {"repository_names": [repo]}` (`línea 143`), por lo que el token emitido para `autoaiorg/aao-governance-trial` carece de permisos sobre `autoaiorg/aao` aunque la App `aao-auditor` esté instalada en ambos.
3. **`STAGE-COMMIT` ([`src/aao/github_trial.py:556, 571-592`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L571-L592)):**
   - Protegido por `_trial_repo_allowed` (`líneas 1009, 556`), restringido a `role == "aao-integrator"` (`línea 572`), a ramas con prefijo `aao-trial/` sin `..` (`línea 575`) y al commit exacto esperado `AAO_GITHUB_TRIAL_EXPECTED_SHA` (`líneas 584-586`).
4. **Promoción (`_merge_trial_pr`, `A-05`/`P3-06`, [`src/aao/github_trial.py:236-385`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L236-L385)):**
   - Además de `_trial_repo_allowed` en `líneas 1009` y `593`, incluye una guarda explícita `if base.lower() == f"/repos/{CANONICAL_REPO}": return "NOT RUN"` en [`src/aao/github_trial.py:237-238`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L237-L238).
   - Opera únicamente sobre el `repositoryId` GraphQL obtenido de `GET {base}` (`líneas 360-369`) y sobre la PR explícitamente autorizada en `AAO_GITHUB_TRIAL_PR` y `AAO_GITHUB_TRIAL_PR_HEAD` (`líneas 241-256`).
5. **Ejecutor `run_trial.sh`:**
   - Fija `REPO=autoaiorg/aao-governance-trial` ([`scripts/trial/run_trial.sh:14`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L14)) y asigna a `AAO_GITHUB_TRIAL_REPOS` únicamente `$REPO` o los forks de ensayo (`autoaiorg/aao-trial-{claude,codex,agy,probe}`, [`scripts/trial/run_trial.sh:160, 188, 271, 290-298, 314, 324`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L160)).

---

### Pregunta 3: ¿Puede el modo de equivalencia (A-01, A-02, P3-02) emitir PASS? ¿Demuestra la evidencia lo que dice?

1. **Imposibilidad de emitir `PASS`:**
   - [`_run_equivalence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L423-L511) solo puede devolver `"NOT RUN"`, `"FAIL"` o `"EQUIVALENCE-PENDING"` (`línea 511`); nunca devuelve `"PASS"`.
   - En [`main()`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L1002-L1003), `--equivalence` está restringido a `A-01`, `A-02` y `P3-02` para roles de implementador, y `"EQUIVALENCE-PENDING"` produce código de salida `2` (`línea 1039`).
   - Si se invoca `A-01`, `A-02` o `P3-02` con un rol de implementador sin `--equivalence`, [`_run_test`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L609-L610) devuelve inmediatamente `"FAIL"`.
2. **Verificación de las premisas y de la evidencia en `_run_equivalence`:**
   - **P0 (identidad del repositorio objetivo):** [`run_trial.sh:62-68, 193, 267`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L62-L68) consulta `GET /repos/autoaiorg/aao-governance-trial` con la App `aao-integrator` al inicio (`EXPECTED_REPO_ID`) y antes de cada ejecución; [`evaluate_equivalence_premises`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L514-L535) exige `status == 200`, `full_name == "autoaiorg/aao-governance-trial"` e `id == expected_repo_id > 0`.
   - **P4 (ausencia de otras credenciales del implementador):** [`run_trial.sh:74-106`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L74-L106) corrige los hallazgos B-01.2/B-2 y C-02b de `592d807`: `user_manager_state` comprueba como `root` ante el gestor del sistema que no exista `/var/lib/systemd/linger/$uid` y que `user@$n.service` esté `inactive`; el propio uid del implementador verifica la ausencia de `~/.config/gh/hosts.yml` y `~/.git-credentials`, que `~/.config/aao` contenga exactamente `{<app>.pem, <app>.json}`, y que ningún archivo en `~/.config/systemd/user` ni `~/.config/environment.d` contenga `GH_TOKEN` o `GITHUB_TOKEN` (tratando cualquier `OSError` de lectura como fallo cerrado). Además, verifica que no existan deploy keys en `$REPO` ni en los dos forks (`deploy_keys_empty`), que la lista de colaboradores externos de `$REPO` esté vacía (`not [x for x in outside if x]`) y que ningún miembro de `autoaiorg` coincida con identidades de implementador.
   - **P4b (control exclusivo del CEO):** [`run_trial.sh:107-113`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L107-L113) y [`evaluate_equivalence_premises`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L527-L529) exigen `ceo_login == "alessbarb"`, `org_owners == ["alessbarb"]` y `repo_admins == ["alessbarb"]`.
   - **P1 (sin instalación en el repo de ensayo):** [`_run_equivalence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L444-L448) consulta `GET /repos/{owner}/{repo}/installation` autenticado con el JWT de la App y exige `HTTP 404`.
   - **P2 (alcance exacto en los dos forks):** [`_run_equivalence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L449-L494) emite un token de instalación **sin** `repository_names` (`repository_names=False`), comprueba con el JWT en `GET /app/installations/{id}` que `repository_selection == "selected"`, pagina `/installation/repositories?per_page=100&page={page}` verificando la consistencia de `total_count`, comprueba que la lista completa de repositorios de la instalación coincida exactamente con `AAO_GITHUB_TRIAL_FORKS` (fork de producción y fork de ensayo para los tres implementadores en [`run_trial.sh:192, 258-279`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L192)) excluyendo `autoaiorg/aao-governance-trial` y `autoaiorg/aao`, y revoca ese token sin restricción exigiendo `HTTP 204`.
   - **P3 (control positivo):** [`_run_equivalence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L495-L511) solicita un nuevo token restringido al fork de ensayo y ejecuta un `git push` a `refs/heads/aao-trial/equivalence-{sha[:12]}`, exigiendo `status == 0`.

---

### Pregunta 4: ¿Puede el token de una App o del CEO filtrarse a argv, a los archivos de evidencia, a los logs del ejecutor o a otro uid?

**No.**

1. **Claves privadas y JWT:** [`load_app`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py#L55-L75) exige que el proceso corra bajo el UID del rol y que `~/.config/aao/<app>.pem` pertenezca a ese UID con modo exacto `0600`. [`create_jwt`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py#L78-L91) invoca `openssl dgst -sha256 -sign` pasando los datos por `stdin` y leyendo la firma por `stdout` en memoria, sin exponer clave ni JWT en `argv` ni en archivos temporales.
2. **Tokens de instalación y del CEO en API y `git push`:**
   - El token del CEO se obtiene en memoria dentro del propio proceso de rol `ceo` mediante `gh auth token --hostname github.com` ([`src/aao/github_trial.py:1014-1022`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L1014-L1022)), sin pasarse por `argv` ni variables de entorno de `run_trial.sh`.
   - [`_NoRedirect`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_app_auth.py#L40-L44) impide reenviar cabeceras `Authorization` ante redirecciones HTTP.
   - En [`_git_push`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L100-L144), la URL remota es `https://github.com/{repo}.git` (sin credenciales en `argv`), se eliminan variables `GIT_TRACE*` y `GIT_CURL_VERBOSE*`, se fuerza `GIT_TRACE_REDACT=1`, se preservan las claves previas de `GIT_CONFIG_COUNT` (`core.hooksPath=/dev/null` y `core.fsmonitor=false`, corrigiendo C-01 de `592d807` en las líneas 112–122) e inyecta `http.extraheader` únicamente en el entorno del subproceso `git` del mismo UID. En `stderr` se redactan tanto cabeceras `Authorization: Basic|Bearer` como el valor literal del token (`líneas 137-138`).
3. **Archivos de evidencia y logs:**
   - [`_redact`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L87-L92) reemplaza recursivamente cualquier clave que coincida con `token|authorization|private.?key` por `"[REDACTED]"`.
   - [`write_evidence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L940-L987) escribe en `~/aao-trial-evidence` (modo `0700`) con `mkstemp` y permisos `0600`.
   - [`run_trial.sh:114, 129, 368`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L114) crea `/var/log/aao-trial/$TS` como `root:root` con modo `0750` y fija `0640` en todos los archivos recolectados.

---

### Pregunta 5: ¿El ejecutor (`run_trial.sh`) usa solo código exportado desde objetos git en la revisión fijada, ejecuta cada rol con su propio uid y con un entorno limpio, y comprueba los rulesets al principio y al final? ¿Puede un uid de agente influir en lo que el ejecutor ejecuta como root o como otro uid?

**Sí a las tres primeras; no a la última.**

1. **Exportación exclusiva desde objetos Git en `$REV`:**
   - [`scripts/trial/run_trial.sh:1-27`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L1-L27) exige `#!/bin/bash -p`, `$EUID == 0`, `$SUDO_USER == alessbarb`, valida que `/root/aao-src` sea un clon plano propiedad exclusiva de `root` (`! -uid 0` o `-perm /022` ausentes) y verifica que el propio script en ejecución (`/root/aao-src/scripts/trial/run_trial.sh`, `0:755`) tenga exactamente el mismo SHA-256 que el blob `$REV:scripts/trial/run_trial.sh`.
   - En [`scripts/trial/run_trial.sh:28-49`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L28-L49), exporta `src/` mediante `git archive "$REV" src` hacia `/opt/aao-trial/$REV/src` (`root:root`, `go-w`) y extrae el registro de Apps mediante `git show "$REV:deploy/github-apps/aao-github-apps-registry.json"`. Todas las invocaciones de Python usan `/usr/bin/python3 -I` e insertan `/opt/aao-trial/$REV/src` en `sys.path`.
2. **Aislamiento por UID y entorno limpio:**
   - Cada paso de rol se ejecuta con `runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin ...` y configuración Git endurecida (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `core.hooksPath=/dev/null`, `core.fsmonitor=false`) tanto en los ensayos principales ([`scripts/trial/run_trial.sh:166-298`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L166-L298)) como en los tres pasos separados de `A-11`/`P3-10` (`FORK-BRANCH` bajo `aao-impl-codex`, `A-11` bajo `aao-pm`, `P3-10` bajo `aao-supervisor`, [`scripts/trial/run_trial.sh:310-356`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L310-L356)).
3. **Comprobación de rulesets al principio y al final:**
   - [`check_rulesets`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L52-L57) se ejecuta antes de iniciar las pruebas (`línea 58`) y al finalizar (`línea 366`), verificando que los rulesets `25776805` (A), `25776806` (B) y `25776807` (C) estén `active`, que B exija `aao-audit` (`integration_id == 5448107`) y `test` sin `bypass_actors` con `non_fast_forward` y `deletion`, que A tenga como único actor de bypass `[(5447984, "Integration")]` (corrigiendo C-03 de `592d807`), y que C proteja `tag` (`creation`, `update`, `deletion`).
4. **Imposibilidad de influencia cruzada entre UIDs o hacia `root`:**
   - Los directorios de trabajo por rol se ubican bajo `/var/lib/aao-trial/work/$uid` ([`scripts/trial/run_trial.sh:42-48`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L42-L48), padres `root:root 0755`) y se validan con [`validate_role_workdir`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/trial_security.py#L11-L17) (`lstat`, directorio real sin symlinks, propietario `$uid`, modo `0700`).
   - En [`capture_evidence`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L115-L130), el propio UID del rol verifica con `os.lstat` que el archivo de evidencia no sea symlink y le pertenezca, y lo vuelca con `/bin/cat` hacia el descriptor abierto por `root` en `$LOG`. Los valores extraídos de la evidencia (`merge_sha` en `línea 234` y `fork_pr` en `línea 351`) son validados por expresiones regulares estrictas (`[0-9a-f]{40}` y `[1-9][0-9]*`) antes de su uso.

---

### Pregunta 6: ¿Cada evidencia queda ligada a la ejecución y a la revisión del arnés que la produjo (§16.0)?

**Sí.**
- [`scripts/trial/run_trial.sh:114`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L114) define `TS=$(date -u +%Y%m%dT%H%M%S.%NZ)` y exporta `AAO_TRIAL_RUN_ID=$TS` y `AAO_TRIAL_HARNESS_REV=$REV`, pasándolos a cada invocación de [`src/aao/github_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py) y [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py).
- [`write_evidence`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L940-L981) (compartida por ambos módulos) incluye en cada JSON de evidencia `"run_id"`, `"harness_revision"`, `"candidate_sha"`, `"shas"`, `"repo"`, `"role"`, `"app_id"`, `"timestamp"` y `"evidence"`.
- Al cierre de `run_trial.sh` (`línea 367`), se genera `SHA256SUMS` sobre todos los archivos de `$LOG`. (Véase la observación menor **C-02** sobre la variable de entorno `AAO_TRIAL_CANDIDATE_SHA` en el subpaso `FORK-BRANCH`, donde el SHA queda igualmente registrado en `"shas"` y en `evidence[0]["sha"]`).

---

### Pregunta 7: Arranque y procedimientos (`scripts/bootstrap/`, `scripts/trial/seed_trial_ci.sh`, `actions_approval.sh`, `probe_app_setup.sh`): ¿falla cerrado ante cualquier error? ¿Restaura la siembra de CI la protección o detiene el ensayo?

**Sí.** Todos los scripts de arranque y procedimientos operan en modo fail-closed (`set -euo pipefail`):

1. **[`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/seed_trial_ci.sh#L1-L35):**
   - Guarda la configuración normalizada de los rulesets A (`25776805`), B (`25776806`) y C (`25776807`) antes de modificar nada y aborta (`exit 1`) si alguno no está `active` (`líneas 14-18`).
   - Instala `trap restore EXIT` (`líneas 19-20`) antes de desactivar A y B, garantizando que cualquier fallo durante la subida de `deploy/trial/test.yml` reactive A y B.
   - Tras restaurar, descarga el estado posterior de A, B y C y compara byte a byte (`diff -q`) con el estado guardado (`líneas 26-31`); ante cualquier diferencia imprime `PROTECTION NOT RESTORED: stop the trial` y sale con código `1` (`línea 32`).
2. **[`scripts/trial/actions_approval.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/actions_approval.sh#L1-L16):**
   - Guarda el estado previo y posterior de `fork-pr-contributor-approval` y `workflow` en `autoaiorg/aao-governance-trial`, aplica `approval_policy=all_external_contributors` y falla cerrado (`exit 1`) si la lectura posterior no confirma `all_external_contributors` y `default_workflow_permissions == read` (`líneas 13-14`).
3. **[`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/probe_app_setup.sh#L1-L36):**
   - Exige un SHA `REV` de 40 caracteres hexadecimales (`líneas 18-19`), instala `exchange_manifest_code.py`, `create_app_form.py` y el manifiesto `aao-probe-noworkflows.json` desde objetos Git en `$REV` (nunca desde el árbol de trabajo, `líneas 24-29`), realiza el canje como uid `aao-probe-noworkflows` por `stdin` (`línea 34`) e incluye `--teardown` (`líneas 10-17`) para destruir la clave con `shred -u`, eliminar el usuario y borrar el fork.
4. **[`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/bootstrap/host_bootstrap.sh#L1-L319):**
   - Se ejecuta con `#!/bin/bash -p` y entorno limpio (`líneas 22-32`), exige clon plano propiedad de `root` limpio en `$REV` (`líneas 69-75`), exige `9/9 PASS` en `verify_app_auth.py` (`líneas 150-169`), valida el dictamen `APPROVE-TECHNICAL` de `aao-auditor-alt` sobre una copia instantánea propiedad de `root` (`check_audit`, `líneas 200-224`), detiene unidades y verifica que estén inactivas antes de actualizar en `--trust-root-upgrade` (`líneas 285-296`), y mantiene el integrador desactivado salvo que todos los RA (`RA-01`, `RA-02`, `RA-03`, `RA-07`, `RA-09`) estén en `PASS` (`líneas 312-317`).
   - Además, las correcciones en [`src/aao/authorization_issuer.py:57-65, 100`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/authorization_issuer.py#L57-L65), [`src/aao/auditor_dispatch.py:110, 166`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/auditor_dispatch.py#L110) y [`src/aao/supervisor_service.py:78-200`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/supervisor_service.py#L78-L200) resuelven los hallazgos B-1 (`registry_owner_uids` incluye `(0, aao-trust)`) y B-3/PM-1 (atribución de actores desde la cadena de eventos `PushEvent` del repositorio/fork cabeza de cada PR abierta, con detección de ciclos y fallo cerrado ante cadenas incompletas o truncadas) de la auditoría anterior.

---

### Pregunta 8: ¿Cada prueba negativa nueva fallaría si se revierte su control?

**Sí.** Todas las pruebas negativas —incluidas las añadidas o reforzadas en `b392750`— ejercitan directamente el control de producción correspondiente y fallarían si dicho control se revirtiera:

- **Resolución del hallazgo B-02 de `592d807` (`NT-02-10`):** [`test_push_principal_maps_must_be_injective`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L167-L195) (y su homóloga en [`tests/test_r1_live_fixes.py:224-253`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_r1_live_fixes.py#L224-L253)) prueba ahora explícitamente un mapa `push_principals` con colisión (`{"one": "same", "two": "same"}`) contra `supervisor_service.load_config` (`pytest.raises(ValueError, match="ambiguous")`), `manifest_audit.attributed_implementers` (`== []`) e `integration_authorization.validate` (`"actor attribution inconclusive"`). Revertir el control de inyectividad en cualquiera de los tres módulos hace fallar la prueba.
- **Atribución desde forks y cadenas incompletas (`RA-02`):** [`test_supervisor_attributes_fork_prs_through_push_chain_and_commit_history`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L113-L147), [`test_supervisor_incomplete_chain_and_malformed_fork_events_skip_prs`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L149-L157), [`test_supervisor_malformed_fork_skips_repo_and_pull_failure_writes_nothing`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L159-L165), [`test_attribution_cycle_without_creation_path_skips_pr`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_r1_live_fixes.py#L193-L209) y [`test_attribution_skips_pull_with_commit_pagination_limit`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_r1_live_fixes.py#L212-L226) verifican que cadenas sin `0*40`, ciclos, eventos malformados o PRs con `>= 100` commits se omiten sin escribir atribución.
- **Espera de checks requeridos en `P3-07` y `P3-12`:** [`test_p3_07_waits_for_required_checks_before_push`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_github_trial.py#L468-L482) y [`test_p3_12_waits_for_required_checks_before_push`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_github_trial.py#L485-L498) verifican que si `_wait_required_checks` devuelve `False`, no se invoca `_git_push` y el resultado es `INCONCLUSIVE`.
- **Automatización de `FORK-BRANCH`, `A-11` y `P3-10` ([`tests/test_fork_pr_trial.py:55-170`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_fork_pr_trial.py#L55-L170)):** verifica el rechazo cuando el implementador está instalado en el repo protegido (`HTTP 200`), cuando la PR no la abre `aao-pm[bot]` o no proviene del fork/SHA esperado, cuando un workflow run de `P3-10` ejecuta jobs (`jobs(1)` -> `FAIL`), cuando los runs pertenecen a otro fork/rama o la cabeza de la PR se movió (`INCONCLUSIVE`), y cuando se intenta usar un rol incorrecto o `autoaiorg/aao`.

---

## 3. Clasificación de hallazgos (A / B / C)

### Categoría A (Controles eludibles, PASS falsos, fugas de credenciales o acceso al repositorio canónico)

- **Ninguno (0 hallazgos A).**

### Categoría B (Defectos no eludibles o de robustez operativa que fallan cerrado)

- **Ninguno (0 hallazgos B).** Todos los hallazgos de Categoría B señalados en la revisión `592d807` (`B-1`, `B-2`/`B-01.2`, `B-3`/`PM-1`, `B-01.3` y `B-02`) han sido verificados como corregidos en `b392750`.

### Categoría C (Observaciones menores de defensa en profundidad, estilo o trazabilidad documental)

1. **[C-01] `user_manager_state()` en [`scripts/trial/run_trial.sh:74-79`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L74-L79) depende de su invocación en el lado izquierdo de `||` para ignorar el código de salida `3` de `systemctl is-active`:**
   En la línea 77, `st=$(systemctl is-active "user@$n.service" 2>/dev/null)` se ejecuta sin `|| true`. Cuando `user@$n.service` está inactivo, `systemctl is-active` imprime `inactive` y devuelve código de salida `3`. En la llamada actual ([`scripts/trial/run_trial.sh:93`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L93)), `$(user_manager_state "$uid")` forma parte del comando a la izquierda de `|| printf '%s' '{}'`, por lo que Bash suprime `set -e` dentro de la función y devuelve `absent` según lo previsto. Si en el futuro se llamara a `user_manager_state` fuera de un contexto `||`, `set -e` terminaría la subshell en la línea 77 devolviendo `""` (lo que igualmente fallaría cerrado en la línea 85). Añadir `|| true` dentro de `user_manager_state` evita esa dependencia contextual.
2. **[C-02] El paso `FORK-BRANCH` en [`scripts/trial/run_trial.sh:341`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L341) no pasa `AAO_TRIAL_CANDIDATE_SHA="$fork_head"` (y [`src/aao/fork_pr_trial.py:59`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L59) no valida `_trial_repo_allowed` sobre `parent` antes del `GET` de solo lectura):**
   A diferencia de `A-11` en [`scripts/trial/run_trial.sh:346`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh#L346), la llamada a `fork_step` para `FORK-BRANCH` en la línea 341 no incluye `AAO_TRIAL_CANDIDATE_SHA="$fork_head"`, dejando `"candidate_sha": ""` en el nivel superior de su archivo JSON (aunque el SHA del commit sí queda registrado en `"shas"` y en `evidence[0]["sha"]` por [`src/aao/fork_pr_trial.py:50`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L50) y [`src/aao/github_trial.py:950-958`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py#L950-L958)). Asimismo, en [`src/aao/fork_pr_trial.py:156-161`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py#L156-L161) se valida `_trial_repo_allowed` sobre `args.repo`, pero para `FORK-BRANCH` convendría validar también `_trial_repo_allowed` sobre `AAO_GITHUB_TRIAL_FORK_PARENT` antes del `GET /repos/{parent}/installation` de la línea 59.
3. **[C-03] Sincronización de marcadores `@pytest.mark.nt` y nombre de test en [`docs/procedures/NT_TRACEABILITY.md:14, 21`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/procedures/NT_TRACEABILITY.md#L14):**
   Al reemplazar `test_supervisor_resolves_only_unique_exact_push_principals` por [`test_supervisor_attributes_fork_prs_through_push_chain_and_commit_history`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L113) y [`test_push_principal_maps_must_be_injective`](file:///tmp/tmp.hgVEZyY2zo/repo/tests/test_ra_controls.py#L167), no se trasladaron los decoradores `@pytest.mark.nt("NT-02-3")` y `@pytest.mark.nt("NT-02-10")` ni se actualizó el nombre de la función en [`docs/procedures/NT_TRACEABILITY.md:14, 21`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/procedures/NT_TRACEABILITY.md#L14).

---

## 4. Regla de parada y Dictamen final

De acuerdo con la regla de parada establecida en el contrato de auditoría (`REJECT` solo procede ante hallazgos de Categoría A) y habiendo verificado `0` hallazgos de Categoría A y `0` hallazgos de Categoría B en la revisión `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`:

Veredicto: APPROVE-TECHNICAL

---

## 5. Informe de cierre (`AGENTS.md` / `GOV-REV-001`)

- **Scope:** Auditoría independiente de solo lectura del diff `git diff 592d80713b8ca9d7586037861d401adc7a67be58 b392750ff9c06f33a7ef39dae4a27c43f422ff9c -- src tests scripts deploy docs/procedures` y de los archivos completos [`src/aao/github_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/github_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh) (junto con [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.hgVEZyY2zo/repo/src/aao/fork_pr_trial.py) y los scripts de arranque y procedimientos) en `HEAD`, frente a [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0–§16.5), [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) y [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.hgVEZyY2zo/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md).
- **Exact revision:** Base `592d80713b8ca9d7586037861d401adc7a67be58` → HEAD `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`.
- **Actions performed:**
  - Declaración expresa de no participación en la autoría, el diseño, la implementación o la revisión previa de desarrollo del código auditado.
  - Inspección estática íntegra utilizando únicamente comandos `git` individuales de solo lectura (`git log`, `git diff`, `git show`, `git ls-files`, `git grep`), sin tuberías, encadenamientos ni redirecciones, y sin modificar archivos ni escribir fuera del directorio temporal.
  - Verificación de las Preguntas 1 a 8 y del cierre de los hallazgos del lote `592d807..b392750` (#82).
- **Evidence and limitations:**
  - **Evidencia:** Citas exactas `archivo:línea` verificadas sobre el árbol Git en `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`.
  - **Pruebas ejecutadas:** `0` (`pytest` no está permitido en este entorno; el CI del repositorio las ejecuta por separado).
  - **Limitaciones:** Análisis estático sobre el repositorio sin ejecución en vivo contra la API de GitHub ni inspección directa del sistema de archivos del host fuera del clon auditado.
- **Outstanding blockers:** Ninguno (`0` hallazgos A y `0` hallazgos B).
- **Authority used:** Auditor Independiente de AAO (`aao-auditor-alt` / Antigravity), autorizado por la resolución delegada en el Issue #25.
- **Next owner/action:** CEO (`alessbarb`) y PM del proyecto para registrar el dictamen `APPROVE-TECHNICAL` sobre `b392750ff9c06f33a7ef39dae4a27c43f422ff9c`, proceder si así lo decide el CEO con `--trust-root-upgrade` en [`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/bootstrap/host_bootstrap.sh) y ejecutar el ensayo P2/P3 mediante [`scripts/trial/run_trial.sh`](file:///tmp/tmp.hgVEZyY2zo/repo/scripts/trial/run_trial.sh) desde `/root/aao-src` en la revisión auditada.
