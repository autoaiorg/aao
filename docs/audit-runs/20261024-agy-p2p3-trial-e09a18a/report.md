Voy a iniciar la auditoría independiente en modo de solo lectura verificando primero la revisión `HEAD`, el historial reciente para comprobar la no participación previa, los documentos de contrato y el `git diff` del alcance indicado.
Voy a leer íntegramente `scripts/trial/run_trial.sh` y `src/aao/github_trial.py` en `HEAD` (`e09a18aad4768cc9282fc794d6a3b8bd283437ee`), así como `src/aao/fork_pr_trial.py` y los tests modificados, utilizando comandos `git` de solo lectura.
# Dictamen de Auditoría Independiente — Arnés de Ensayo P2/P3 y Correcciones de Arranque Post-Raíz de Confianza (`e09a18a`)

## 0. Declaración de no participación e independencia

Yo, **Antigravity (`aao-auditor-alt`)**, actuando como **AUDITOR INDEPENDIENTE de AAO** autorizado por la resolución delegada en el Issue #25, **declaro que NO he participado en la autoría, el diseño, la implementación ni la revisión previa de desarrollo** del código, los scripts ni los procedimientos auditados en esta revisión (`e09a18aad4768cc9282fc794d6a3b8bd283437ee`). La autoría corresponde a Codex ([`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py), sus tests y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh)) y a Claude (el resto de `scripts/trial/`, `scripts/bootstrap/`, `scripts/github_apps/`, `deploy/trial/`, [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py), los procedimientos y la especificación/revisión de [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh)). Ambos autores están recusados respecto a lo que escribieron o especificaron. Mi única intervención previa sobre este ámbito consistió en las auditorías independientes de solo lectura sobre las revisiones `315be35e6742504fea7fed0d0c858c6803352dba`, `592d80713b8ca9d7586037861d401adc7a67be58`, `b392750ff9c06f33a7ef39dae4a27c43f422ff9c` y `0a55daf5ee08c7f10c6c56224da145228c549011`. En consecuencia, procedo a emitir el dictamen.

---

## 1. Alcance, pruebas ejecutadas y limitaciones de independencia

- **Repositorio y revisión auditada (`HEAD`):** `/tmp/tmp.GuGcN4xRQ9/repo` en el commit exacto `e09a18aad4768cc9282fc794d6a3b8bd283437ee`.
- **Diff auditado:** `git diff 0a55daf5ee08c7f10c6c56224da145228c549011 e09a18aad4768cc9282fc794d6a3b8bd283437ee -- src tests scripts deploy docs/procedures` (7 archivos modificados, 133 inserciones, 33 eliminaciones):
  - [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md) (líneas 8–14, 51–57);
  - [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) (líneas 137–145, 170–179);
  - [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py) (líneas 76–99);
  - [`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py) (líneas 214–252, 383–386, 667–668, 710–721, 780–784, 821–829, 939–945);
  - [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_fork_pr_trial.py) (líneas 105–110);
  - [`tests/test_github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_github_trial.py) (líneas 173–177, 269–277, 420–485, 558–564, 608–616, 927–953);
  - [`tests/test_trial_runner.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_trial_runner.py) (líneas 117–122).
- **Archivos auditados íntegramente en `HEAD`:**
  - [`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py) (líneas 1–1085);
  - [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) (líneas 1–370);
  - [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py) (líneas 1–182) y [`tests/test_fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_fork_pr_trial.py) (líneas 1–169);
  - Módulos y scripts de soporte y arranque en `HEAD`: [`src/aao/github_app_auth.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py) (líneas 1–169), [`src/aao/trial_security.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/trial_security.py) (líneas 1–23), [`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh) (líneas 1–360), [`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/seed_trial_ci.sh) (líneas 1–35), [`scripts/trial/actions_approval.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/actions_approval.sh) (líneas 1–15) y [`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/probe_app_setup.sh) (líneas 1–37).
- **Contrato verificado:**
  - [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0 a §16.5, líneas 686–757);
  - [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) (líneas 1–252) y [`docs/proposals/P3_PUBLIC_REPOSITORY_MAIN_PROTECTION.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/proposals/P3_PUBLIC_REPOSITORY_MAIN_PROTECTION.md) (líneas 1–116);
  - [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md) y [`docs/audit-runs/20261024-trial-run-0a55daf/README.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-trial-run-0a55daf/README.md).
- **Pruebas ejecutadas:** **No se ejecutaron pruebas (`pytest` no está permitido en este entorno).** El CI del repositorio las ejecuta aparte. La verificación se realizó mediante inspección estática exhaustiva con comandos `git` de solo lectura.
- **Limitaciones de independencia:**
  - La auditoría es estática sobre el árbol Git en `e09a18aad4768cc9282fc794d6a3b8bd283437ee`; no realiza llamadas en vivo a la API de GitHub ni inspecciona el estado en vivo fuera del repositorio, aunque se contrastó el registro de la primera ejecución en vivo en `0a55daf` ([`docs/audit-runs/20261024-trial-run-0a55daf/README.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-trial-run-0a55daf/README.md) y [`docs/audit-runs/20261024-trial-run-0a55daf/run.log`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-trial-run-0a55daf/run.log)).

---

## 2. Respuestas a las preguntas de auditoría (1 a 8)

### Pregunta 1: ¿Puede el arnés emitir `PASS` sin que el servidor de GitHub haya rechazado o aceptado realmente la operación por la causa esperada?

**No.** Todos los caminos en [`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py), [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) exigen respuesta real del servidor de GitHub por la causa específica bajo prueba y verificación posterior de estado:

1. **Rechazo del lado del cliente vs. rechazo real `receive-pack` del servidor (`git push`):**
   - [`_git_push`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L100-L145) captura `stderr` y calcula `server_rejected = _is_server_rejection(stderr)` ([`src/aao/github_trial.py:141`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L141)).
   - [`_is_server_rejection`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L147-L154) exige líneas `[remote rejected] ... (:|()` o `remote: ... (protected branch|permission to .* denied|not permitted|GH\d+:|workflow|non-fast-forward|ruleset)`. Un rechazo local del cliente Git (`[rejected] ... (stale info)` o `(fetch first)`) produce `server_rejected: False`.
   - [`_push_rejection_pass`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L203-L211) y [`_denial_outcome`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L244-L251) exigen `exit_code != 0`, `server_rejected is True` y `unchanged is True` (comprobado en el servidor vía [`_verify_unchanged`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L173-L175) / [`_ref_unchanged`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L188-L191)).
   - En `A-04` ([`src/aao/github_trial.py:672-681`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L672-L681)), dado que `--force-with-lease` con lease obsoleto falla en el cliente Git antes de `receive-pack`, el arnés registra la limitación y devuelve siempre `NOT RUN`, remitiendo a `A-03`/`P3-05` para la prueba CAS en el servidor.
2. **Evaluación de la regla de atribución corregida en `#86` (`_rejection_attributable` y `_denial_outcome`, [`src/aao/github_trial.py:214-251`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L214-L251)):**
   - **Dictamen sobre la discrepancia sometida por el PM (`Restrict updates` en `P3-01` y `P3-09`):** Se valida como **técnicamente correcta y segura** la atribución adoptada en [`src/aao/github_trial.py:217-226`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L217-L226). En los rulesets activos verificados al inicio y al final por [`check_rulesets()`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L53-L58), únicamente el Ruleset A (`25776805`, bypass exclusivo `aao-integrator` `5447984`) contiene la regla `update` (*Restrict updates*), mientras que el Ruleset B (`25776806`, sin bypass) contiene `non_fast_forward`, `deletion` y `required_status_checks`. Cuando un actor sin bypass en A (el CEO en `P3-01` o `P3-09`) intenta actualizar `refs/heads/main`, GitHub evalúa todos los rulesets activos y emite una viñeta por cada regla violada. La viñeta `"Cannot update this protected ref."` solo la emite GitHub cuando se viola la regla `update` del Ruleset A (como lo confirma empíricamente `P3-03`, donde `aao-integrator` —que sí tiene bypass en A— intenta actualizar `main` sin checks y GitHub **no** emite `"Cannot update this protected ref."`, sino únicamente `"2 of 2 required status checks are expected."`). Por tanto, exigir `"cannot update this protected ref" in response` en [`_rejection_attributable`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L225-L226) demuestra de forma necesaria y suficiente que el servidor aplicó `Restrict updates` (Ruleset A) al CEO sin excepción, aunque concurran las viñetas de `pull_request` o `required_status_checks`. Si solo aparece el mensaje de checks requeridos o un `GH013` genérico sin `"cannot update this protected ref"`, devuelve `False` y el resultado es `INCONCLUSIVE` ([`src/aao/github_trial.py:249-250`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L249-L250), [`src/aao/github_trial.py:782-783`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L782-L783)). Además, [`_violated_rules`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L238-L241) e `item["response"]` dejan constancia expresa en `reason` de todas las reglas listadas por GitHub ([`src/aao/github_trial.py:251, 784`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L251)).
   - **Causa única en `non-fast-forward` (`P3-07`, `P3-12`) y `deletion`:** En [`src/aao/github_trial.py:229-232`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L229-L232), `non-fast-forward` exige `any(text in response for text in ("cannot force-push", "non-fast-forward", "non_fast_forward")) and not checks`, y `deletion` exige `"cannot delete" in response and not checks`, donde `checks` es `_REQUIRED_CHECKS_EXPECTED.search(response) is not None` (`r"\d+ of \d+ required status checks? (?:is|are) expected"`, [`src/aao/github_trial.py:214`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L214)). Adicionalmente, en [`scripts/trial/run_trial.sh:172-176`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L172-L176), el candidato de `P3-07` y `P3-12` ahora se construye con padre `origin/main^` (no descendiente de `main`) pero conservando el árbol de `origin/main` (`checkout -q origin/main -- .`), de modo que incluye `.github/workflows/test.yml`, permite que el check `test` y `aao-audit` se pongan en verde en [`_wait_required_checks`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L870-L872) / [`889-891`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L889-L891) antes del push forzado, y garantiza que el rechazo del servidor se deba exclusivamente a `non_fast_forward`.
   - **Atribución estricta de checks requeridos en `P3-03` ([`src/aao/github_trial.py:227-228, 939-945`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L939-L945)):** `P3-03` acepta HTTP `403` o `422` (código devuelto por la API REST de GitHub ante violación de rulesets en `PATCH /git/refs/heads/main`) únicamente cuando `_rejection_attributable({"response": message}, "required status check")` es verdadero —lo que exige la frase exacta del servidor `_REQUIRED_CHECKS_EXPECTED` (`"\d+ of \d+ required status checks? (?:is|are) expected"`)— y `main` permanece sin cambios (`_verify_unchanged`). Un `422` por validación ajena no coincide con `_REQUIRED_CHECKS_EXPECTED` y produce `FAIL`.
3. **Mutaciones GraphQL `updateRefs` (`A-03`, `P3-05`, `A-04`, `A-05`, `P3-06`):**
   - Se corrigió el payload de `updateRefs` en [`src/aao/github_trial.py:383, 667, 821, 827`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L383) sustituyendo `{ refs { name } }` (campo inexistente en `UpdateRefsPayload`) por `{ clientMutationId }`.
   - En `A-03` y `P3-05` ([`src/aao/github_trial.py:821-833`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L821-L833)), el arnés primero mueve realmente `main` a `candidate` verificando `moved_ok` y `_main_sha(client, base, evidence) == candidate`, y luego ejecuta `updateRefs` con `beforeOid: sha` obsoleto exigiendo error de precondición (`"before"` o `"stale"` en `errors[].message`) y `_verify_unchanged(client, base, candidate, evidence)`.
   - En `A-05` y `P3-06` ([`src/aao/github_trial.py:383-402`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L383-L402)), tras `updateRefs`, verifica con tres lecturas independientes que `main` apunta a `merge_sha`, que `tree` y `parents == [base_sha, candidate]` coinciden y que la PR figura con `merged is True`.
4. **Verificación de permisos en `A-10` ([`src/aao/github_trial.py:710-721`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L710-L721)):**
   - `A-10` consulta `client.app_request("GET", f"/repos/{owner}/{repo}/installation")` autenticándose con el JWT de la App ([`src/aao/github_app_auth.py:113-115`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L113-L115)). Si el estado HTTP no es `200`, devuelve `INCONCLUSIVE` ([`src/aao/github_trial.py:713-714`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L713-L714)); solo emite `PASS` si el mapa de permisos devuelto por GitHub coincide exactamente con `FORK_PERMISSIONS` o `EXPECTED_PERMISSIONS` ([`src/aao/github_trial.py:720-721`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L720-L721)).
5. **Creación de PR de fork en `A-11` ([`src/aao/fork_pr_trial.py:76-99`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py#L76-L99)):**
   - Envía `head_repo: fork` (`owner/name`) y `maintainer_can_modify: False` ([`src/aao/fork_pr_trial.py:84-85`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py#L84-L85)), y exige HTTP `201`, `head.repo.full_name == fork`, `head.sha == expected`, `base.repo.full_name == parent` y `user.login == "aao-pm[bot]"` ([`src/aao/fork_pr_trial.py:91-96`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py#L91-L96)).
6. **Errores de red, excepciones o evidencia de otra ejecución:**
   - Cualquier fallo de red en [`GitHubAppClient._request`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L132-L133) lanza `GitHubAuthError`, que en [`github_trial.py:1065-1075`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L1065-L1075) y [`fork_pr_trial.py:173-179`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py#L173-L179) produce `NOT RUN` (código `2`).
   - [`capture_evidence`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L115-L130) filtra por `d.get("run_id") == os.environ["AAO_TRIAL_RUN_ID"]` y `d.get("role") == os.environ["AAO_TRIAL_ROLE"]`, impidiendo reutilizar archivos de otra ejecución.

---

### Pregunta 2: ¿Puede algún camino tocar el repositorio canónico `autoaiorg/aao`, o un repositorio no listado de forma explícita?

**No.**

1. **Bloqueo en [`_trial_repo_allowed`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L157-L162):**
   - Rechaza incondicionalmente `CANONICAL_REPO = "autoaiorg/aao"` ([`src/aao/github_trial.py:50, 159-160`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L159-L160)) y exige que `target` figure explícitamente en `AAO_GITHUB_TRIAL_REPOS`.
   - En [`main()`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L1031-L1032), esta validación se ejecuta **antes** de instanciar `GitHubAppClient` o solicitar tokens.
   - En [`src/aao/fork_pr_trial.py:155-160`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py#L155-L160), se valida `_trial_repo_allowed` tanto para `--repo` como para `AAO_GITHUB_TRIAL_FORK_PARENT` antes de cargar credenciales.
2. **Atención especial a `PUBLISH-AUDIT`, `STAGE-COMMIT` y promoción (`A-05` / `P3-06`):**
   - En [`_run_test`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L574-L575), `PUBLISH-AUDIT` y `STAGE-COMMIT` verifican de nuevo `not _trial_repo_allowed(owner, repo)`.
   - Cuando [`main()`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L1059) solicita el token de instalación para `PUBLISH-AUDIT`, `STAGE-COMMIT` o promoción, invoca [`client.installation_token(owner, repo)`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L140-L155) con `repository_names=True` por defecto, enviando `{"repository_names": [repo]}` a `POST /app/installations/{id}/access_tokens` ([`src/aao/github_app_auth.py:148-150`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L148-L150)). Así, aunque la App `aao-auditor` está instalada también en `autoaiorg/aao`, el token emitido por GitHub para `PUBLISH-AUDIT` queda **restringido en el servidor exclusivamente a `aao-governance-trial`** y además publica el check únicamente sobre el SHA explícito de ensayo (`AAO_GITHUB_TRIAL_SHA`, [`src/aao/github_trial.py:579-583`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L579-L583)).
   - En [`_merge_trial_pr`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L255-L256), existe una guarda adicional explícita contra `/repos/autoaiorg/aao`, y la mutación GraphQL `updateRefs` incluye obligatoriamente `"repositoryId": repository_id` del repositorio de ensayo ([`src/aao/github_trial.py:380-385`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L380-L385)).

---

### Pregunta 3: ¿Puede el modo de equivalencia (`A-01`, `A-02`, `P3-02`) emitir `PASS`? ¿Demuestra la evidencia lo que dice: sin instalación en el repo de ensayo, alcance exacto en los forks y control positivo?

**No puede emitir `PASS`, y la evidencia demuestra exactamente los cuatro extremos requeridos.**

1. **Imposibilidad de emitir `PASS`:**
   - Sin `--equivalence`, ejecutar `A-01`, `A-02` o `P3-02` con un rol de implementador devuelve `FAIL` en [`src/aao/github_trial.py:627-628`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L627-L628).
   - Con `--equivalence` (o `test_id == "EQUIVALENCE"`), [`_run_equivalence`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L441-L529) solo puede devolver `"NOT RUN"`, `"FAIL"` o `"EQUIVALENCE-PENDING"` ([`src/aao/github_trial.py:529`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L529)), con código de salida `2` ([`src/aao/github_trial.py:1064`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L1064)).
2. **Completitud de la evidencia de equivalencia:**
   - **Premisas `P0`, `P4` y `P4b` ([`src/aao/github_trial.py:449-461, 532-566`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L532-L566) y [`scripts/trial/run_trial.sh:62-113, 197-200, 271-275`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L62-L113)):** Verifica identidad e `id` inmutable del repositorio de ensayo (`P0`), ausencia de credenciales alternas en el uid y en GitHub (`P4`: sin `.config/gh/hosts.yml`, sin `.git-credentials`, `user@UID.service` inactivo y sin linger, sin `GH_TOKEN`/`GITHUB_TOKEN` en unidades de usuario ni `environment.d`, `~/.config/aao` con solo `<app>.pem` y `<app>.json`, 0 deploy keys en repo de ensayo y forks, 0 colaboradores externos y ningún bot implementador como miembro de la organización), y `alessbarb` como único owner/admin (`P4b`). Si falla cualquier premisa, devuelve `FAIL` ([`src/aao/github_trial.py:459-461`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L459-L461)).
   - **Sin instalación en el repositorio de ensayo:** Consulta `GET /repos/{owner}/{repo}/installation` con el JWT de la App y exige HTTP `404` ([`src/aao/github_trial.py:462-466`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L462-L466)).
   - **Alcance exacto en los forks:** Obtiene un token de instalación sin restricción de nombres (`repository_names=False`, [`src/aao/github_trial.py:474`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L474)), verifica con JWT `GET /app/installations/{id}` que `repository_selection == "selected"` ([`src/aao/github_trial.py:478-482`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L478-L482)), pagina `GET /installation/repositories` verificando `total_count` y que el conjunto de repositorios accesibles sea exactamente `forks` (`autoaiorg/aao-<impl>` y `autoaiorg/aao-trial-<impl>`), excluyendo el repo de ensayo y el canónico ([`src/aao/github_trial.py:486-507`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L486-L507)).
   - **Control positivo con token acotado:** Revoca el token de inspección (`DELETE /installation/token` == `204`, [`src/aao/github_trial.py:508-512`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L508-L512)), emite un nuevo token restringido al fork de ensayo ([`src/aao/github_trial.py:514`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L514)) y verifica un `git push` positivo a `refs/heads/aao-trial/equivalence-<sha[:12]>` en dicho fork ([`src/aao/github_trial.py:524-528`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L524-L528)).

---

### Pregunta 4: ¿Puede el token de una App o del CEO filtrarse a `argv`, a los archivos de evidencia, a los logs del ejecutor o a otro `uid`?

**No.**

1. **Sin exposición en `argv`:**
   - La firma del JWT con `openssl` recibe la entrada por `stdin` y lee la clave privada desde su ruta en `0600` ([`src/aao/github_app_auth.py:86-90`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L86-L90)).
   - Las peticiones HTTP llevan el token en la cabecera `Authorization` en memoria y bloquean redirecciones HTTP mediante [`_NoRedirect`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L40-L44).
   - [`_git_push`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L100-L133) pasa la cabecera `http.extraheader` mediante variables de entorno `GIT_CONFIG_KEY_i` / `GIT_CONFIG_VALUE_i` del subproceso `git`, nunca en la línea de comandos (`argv`) ni en la URL remota (`https://github.com/{repo}.git`).
   - El token del CEO se obtiene dentro del proceso Python del propio uid del CEO mediante `gh auth token --hostname github.com` por `stdout` capturado en memoria ([`src/aao/github_trial.py:1036-1038`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L1036-L1038)).
2. **Sin exposición en archivos de evidencia ni logs:**
   - [`_git_push`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L108-L111) elimina `GIT_TRACE*` y `GIT_CURL_VERBOSE*`, fija `GIT_TRACE_REDACT=1` y redacta en `stderr` tanto `Authorization: Basic/Bearer ...` como el valor literal de `token` ([`src/aao/github_trial.py:137-138`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L137-L138)).
   - [`_redact`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L87-L92) redacta recursivamente cualquier clave de diccionario que coincida con `token|authorization|private.?key` antes de guardar en `evidence` ([`src/aao/github_trial.py:97, 989`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L97)).
3. **Sin exposición a otros `uid`:**
   - [`load_app`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py#L57-L76) verifica que `os.getuid()` coincida con el usuario Linux propietario del rol y que `~/.config/aao/<app>.pem` pertenezca a ese `uid` con modo exacto `0600`.
   - [`write_evidence`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L965-L1003) crea `~/aao-trial-evidence` con modo `0700` y los archivos JSON temporales y definitivos con modo `0600`. En [`scripts/trial/run_trial.sh:114, 129, 369`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L114), `/var/log/aao-trial/$TS` es `root:root` `0750` y los archivos recolectados quedan en `root:root` `0640`.

---

### Pregunta 5: ¿El ejecutor (`run_trial.sh`) usa solo código exportado desde objetos git en la revisión fijada, ejecuta cada rol con su propio `uid` y con un entorno limpio, y comprueba los rulesets al principio y al final? ¿Puede un `uid` de agente influir en lo que el ejecutor ejecuta como `root` o como otro `uid`?

**Sí a la primera parte; no puede influir ningún `uid` de agente.**

1. **Ejecución exclusiva desde objetos Git en `$REV`:**
   - [`scripts/trial/run_trial.sh:3-27`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L3-L27) exige ejecución directa como `root` en modo privilegiado (`-p`), `SUDO_USER == alessbarb`, `--rev` de 40 hex, clon `/root/aao-src` propiedad íntegra de `root` sin permisos `022`, y verifica que el propio script ejecutado tenga el mismo `sha256` que el objeto `$REV:scripts/trial/run_trial.sh`.
   - Exporta `src/` directamente desde objetos Git (`git archive "$REV" src | tar -x -C "$tmp"`) hacia `/opt/aao-trial/$REV/src` con propietario `root:root` y sin escritura para grupo/otros ([`scripts/trial/run_trial.sh:29-41`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L29-L41)), y extrae el registro de Apps desde `$REV:deploy/github-apps/aao-github-apps-registry.json` ([`scripts/trial/run_trial.sh:42-43`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L42-L43)).
2. **Aislamiento por `uid`, entorno limpio y comprobación de rulesets al principio y al final:**
   - Cada rol se invoca con `runuser -u "$uid" -- env -i ... /usr/bin/python3 -I` pasando únicamente una lista blanca de variables de entorno y desactivando hooks/fsmonitor y configuración global/sistema de Git ([`scripts/trial/run_trial.sh:193, 208, 223, 231, 241, 249, 275, 302, 318`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L193)).
   - [`check_rulesets`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L53-L58) se ejecuta antes de iniciar las pruebas (línea 58) y al finalizar todas las pruebas ([`scripts/trial/run_trial.sh:367`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L367)), verificando que los rulesets A (`25776805`), B (`25776806`) y C (`25776807`) sigan `active`, con `aao-audit` fijado a `integration_id == 5448107`, `test` requerido, sin bypass en B y con `[(5447984, "Integration")]` como único bypass en A.
3. **Incapacidad de un `uid` de agente para influir en `root` o en otro `uid`:**
   - Los directorios de trabajo `/var/lib/aao-trial/work/$uid` cuelgan de padres `root:root` `0755`, se validan con [`validate_role_workdir`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/trial_security.py#L12-L17) (directorio real sin symlinks, propietario `$uid`, modo `0700`) y todas las operaciones dentro de `$work` o `$home` se ejecutan tras caer de privilegios a `$uid` con `runuser -u "$uid"`, incluyendo la recolección de evidencia en [`capture_evidence`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L115-L130).
   - En [`make_fixture_pr`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L134-L148), corregido en `#86`, el árbol JSON se construye con `python3 -I -c 'import json,sys; ...'` pasando `$main_sha`, `"trial-fixtures/$fixture_ts.txt"` y `$blob` como argumentos posicionales (`sys.argv[1..3]`) y enviando la salida por `stdin` (`--input -`) al subproceso `gh api` ejecutado como `$CEO`. Ningún `uid` de agente interviene en esa ruta.

---

### Pregunta 6: ¿Cada evidencia queda ligada a la ejecución y a la revisión del arnés que la produjo (§16.0)?

**Sí.**

- [`scripts/trial/run_trial.sh:114`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L114) define `TS=$(date -u +%Y%m%dT%H%M%S.%NZ)` y exporta `AAO_TRIAL_RUN_ID=$TS` y `AAO_TRIAL_HARNESS_REV=$REV`, que se pasan explícitamente a cada invocación de [`github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py) y [`fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py) (`lines 193, 208, 223, 241, 247, 275, 302, 318`).
- [`write_evidence`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L962-L989) incluye en cada JSON de evidencia `"run_id"`, `"harness_revision"`, `"candidate_sha"`, `"shas"`, `"repo"`, `"role"`, `"app_id"`, `"timestamp"` y `"evidence"`.
- Al finalizar, [`scripts/trial/run_trial.sh:368`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh#L368) genera `/var/log/aao-trial/$TS/SHA256SUMS` sobre todos los archivos recolectados.

---

### Pregunta 7: Arranque y procedimientos (`scripts/bootstrap/`, `scripts/trial/seed_trial_ci.sh`, `actions_approval.sh`, `probe_app_setup.sh`): ¿falla cerrado ante cualquier error? ¿Restaura la siembra de CI la protección o detiene el ensayo?

**Sí, todos fallan cerrado y `seed_trial_ci.sh` restaura la protección o detiene el ensayo.**

1. **Arranque ([`scripts/bootstrap/host_bootstrap.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh) y [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md)):**
   - Corre con `set -euo pipefail` y modo `-p` ([`scripts/bootstrap/host_bootstrap.sh:24-35`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L24-L35)), verifica el clon `/root/aao-src` en `$REV` ([`lines 72-75`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L72-L75)), exige `9/9` en `verify_app_auth.py` ([`lines 146-156`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L146-L156)), valida la atestación y el dictamen `APPROVE-TECHNICAL` del auditor alternativo contra el SHA-256 fijado por el CEO ([`lines 198-224`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L198-L224)), impide rollbacks en `--trust-root-upgrade` (`merge-base --is-ancestor "$OLD" "$REV"`, [`line 307`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L307)), detiene unidades activas antes de respaldar y reemplazar árboles congelados ([`lines 323-336`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L323-L336)), ejecuta `verify_trust_root_host.py` antes de habilitar el despacho del auditor ([`lines 257-263`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L257-L263)) y mantiene el integrador apagado mientras los `RA-*` no estén todos en `PASS` ([`lines 353-359`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L353-L359)).
   - El cambio en [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md:55`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md#L55) elimina `--keys-dir /root/aao-keys` del comando `--trust-root-upgrade` en un host donde las 9 claves ya están instaladas en cada uid (`0600`), coherente con [`scripts/bootstrap/host_bootstrap.sh:96-129`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/bootstrap/host_bootstrap.sh#L96-L129) (que verifica in situ cada clave instalada y solo requiere `--keys-dir` cuando falta alguna).
2. **[`scripts/trial/seed_trial_ci.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/seed_trial_ci.sh) (líneas 1–35):**
   - Opera con `set -euo pipefail`, guarda el estado normalizado previo de los rulesets A, B y C, exige que los tres estén en `enforcement == active` antes de empezar (`lines 14-17`), registra `trap restore EXIT` (`lines 18-19`) para reactivar A y B ante cualquier fallo intermedio, y tras subir `deploy/trial/test.yml` compara con `diff -q` la configuración normalizada anterior y posterior de los tres rulesets (`lines 25-31`). Si existe cualquier diferencia, imprime `PROTECTION NOT RESTORED: stop the trial` y sale con código `1` (`line 31`).
3. **[`scripts/trial/actions_approval.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/actions_approval.sh) (líneas 1–15) y [`scripts/trial/probe_app_setup.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/probe_app_setup.sh) (líneas 1–37):**
   - Ambos operan con `set -euo pipefail` y fallan cerrado (`exit 1` / `exit 2`) si no se cumplen las poscondiciones o si `REV` no es un SHA de 40 hex exportado desde objetos Git.

---

### Pregunta 8: ¿Cada prueba negativa nueva fallaría si se revierte su control?

**Sí.** Se verificaron todas las pruebas nuevas y actualizadas en el diff `0a55daf..e09a18a`:

1. **[`tests/test_github_trial.py:269-277`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_github_trial.py#L269-L277) (`test_a10_installation_lookup_uses_app_jwt_and_404_is_inconclusive`):**
   - Verifica que `A-10` invoque `client.app_request("GET", "/repos/org/trial/installation")` (con JWT de la App, no con token de instalación sobre `/installation`) y que un HTTP `404` devuelva `INCONCLUSIVE`. Si se revierte a `_api(client, "GET", "/installation")` o si se ignora el estado HTTP, la prueba falla.
2. **[`tests/test_github_trial.py:420-485, 558-564, 608-616, 941-953`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_github_trial.py#L420-L485) (atribución por regla en `_rejection_attributable`, `_denial_outcome`, `P3-01`, `P3-03`, `P3-07`, `P3-09`):**
   - `test_p3_01_ceo_pass_requires_restrict_updates_attribution` y `test_restrict_updates_attribution_lists_co_occurring_rules_and_checks_need_expected_phrase` comprueban que el texto real de GitHub `"- Cannot update this protected ref."` (con reglas concurrentes listadas en `reason`) produce `PASS`, mientras que una respuesta que solo contiene `"- 2 of 2 required status checks are expected."` o un `GH013` genérico produce `INCONCLUSIVE`.
   - `test_required_status_check_text_is_attributable_even_with_http_422` y `test_p3_03_live_required_status_check_422_is_pass` comprueban el caso positivo de `P3-03` con HTTP `422` y la frase `"2 of 2 required status checks are expected."`, mientras que `test_restrict_updates_attribution_lists_co_occurring_rules_and_checks_need_expected_phrase` comprueba que `"Validation failed: required status check context is invalid"` es rechazado (`not _rejection_attributable(..., "required status check")`).
   - `test_non_fast_forward_with_required_checks_is_not_attributable` y `test_p3_07_non_fast_forward_name_does_not_override_failed_checks` comprueban que si concurre `"2 of 2 required status checks are expected"` junto con `non-fast-forward`, `_rejection_attributable` devuelve `False` y `P3-07` devuelve `INCONCLUSIVE`.
   - En `test_restrict_updates_attribution_lists_co_occurring_rules_and_checks_need_expected_phrase`, se verifica que `"deletion of this branch is not supported here"` no es atribuible a `deletion`, mientras que `"Cannot delete this protected ref."` sí lo es.
   - Si se revierte cualquiera de los controles en [`_rejection_attributable`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py#L217-L236) o en `P3-03`/`P3-09`, estas pruebas fallan.
3. **[`tests/test_github_trial.py:927-939`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_github_trial.py#L927-L939) (`test_promotion_phase_requires_staged_sha_green_checks_and_cas` y `test_all_update_refs_inputs_include_repository_id`):**
   - Verifican que ninguna mutación `updateRefs` en [`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py) contenga `"refs {"` y que todas incluyan `"repositoryId": repository_id`. Si se revierte a `{ refs { name } }` o se omite `repositoryId`, fallan.
4. **[`tests/test_fork_pr_trial.py:105-110`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_fork_pr_trial.py#L105-L110) (`test_a11_sends_full_head_repo_and_requests_no_maintainer_edits`):**
   - Verifica que `open_pr` envíe `head_repo == FORK` (`owner/name`), `maintainer_can_modify is False` y `head == "autoaiorg:aao-trial/a11-p310-x"`. Si se revierte cualquiera de esos campos, falla.
5. **[`tests/test_trial_runner.py:117-122`](file:///tmp/tmp.GuGcN4xRQ9/repo/tests/test_trial_runner.py#L117-L122) (`test_fixture_tree_is_sent_as_json_and_p3_07_candidate_keeps_main_tree`):**
   - Verifica que `make_fixture_pr` en [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) envíe el árbol por `--input -` sin `-f 'tree[0]` y que el bloque de `P3-07`/`P3-12` ejecute tanto `checkout -q -B trial-candidate origin/main^` como `checkout -q origin/main -- .`. Si se revierte cualquiera de los dos controles en [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh), la prueba falla.

---

## 3. Clasificación de hallazgos (A / B / C)

### Categoría A (Control eludible, evidencia que puede afirmar `PASS` falsamente, fuga de credenciales o acceso al repositorio canónico)
- **Ninguno (`0` hallazgos).**

### Categoría B (Defectos funcionales o de robustez acotados que no comprometen la validez de la evidencia ni la seguridad del repositorio canónico)
- **Ninguno (`0` hallazgos).**

### Categoría C (Observaciones menores de higiene o defensa en profundidad)
- **Ninguno (`0` hallazgos).**

---

## 4. Regla de parada y Dictamen final

De acuerdo con la regla de parada establecida en el contrato de auditoría (`REJECT` solo procede ante hallazgos de Categoría A) y habiendo verificado `0` hallazgos de Categoría A, `0` hallazgos de Categoría B y `0` hallazgos de Categoría C en la revisión `e09a18aad4768cc9282fc794d6a3b8bd283437ee`:

Veredicto: APPROVE-TECHNICAL

---

## 5. Informe de cierre (`AGENTS.md` / `GOV-REV-001`)

- **Scope:** Auditoría independiente de solo lectura del diff `git diff 0a55daf5ee08c7f10c6c56224da145228c549011 e09a18aad4768cc9282fc794d6a3b8bd283437ee -- src tests scripts deploy docs/procedures` y de los archivos completos [`src/aao/github_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_trial.py) y [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) (junto con [`src/aao/fork_pr_trial.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/fork_pr_trial.py), [`src/aao/github_app_auth.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/github_app_auth.py), [`src/aao/trial_security.py`](file:///tmp/tmp.GuGcN4xRQ9/repo/src/aao/trial_security.py) y los scripts de arranque y procedimientos) en `HEAD`, frente a [`docs/AUTONOMOUS_GOVERNANCE_POLICY.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/AUTONOMOUS_GOVERNANCE_POLICY.md) (§16.0–§16.5), [`docs/procedures/P2_P3_TRIAL_SETUP.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/P2_P3_TRIAL_SETUP.md) y [`docs/audit-runs/20261024-p2p3-trial-setup/README.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-p2p3-trial-setup/README.md).
- **Exact revision:** Base `0a55daf5ee08c7f10c6c56224da145228c549011` → HEAD `e09a18aad4768cc9282fc794d6a3b8bd283437ee`.
- **Actions performed:**
  - Declaración expresa de no participación en la autoría, el diseño, la implementación o la revisión previa de desarrollo del código auditado.
  - Inspección estática íntegra utilizando únicamente comandos `git` individuales de solo lectura (`git log`, `git diff`, `git show`, `git grep`), sin tuberías, encadenamientos ni redirecciones, y sin modificar archivos ni escribir fuera del directorio temporal.
  - Verificación de las Preguntas 1 a 8 y evaluación técnica independiente de las correcciones D1 a D6 en `#86` (`0a55daf..e09a18a`), incluida la regla de atribución de `Restrict updates` sometida por el PM en [`docs/audit-runs/20261024-trial-run-0a55daf/README.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/audit-runs/20261024-trial-run-0a55daf/README.md).
- **Evidence and limitations:**
  - **Evidencia:** Citas exactas `archivo:línea` verificadas sobre el árbol Git en `e09a18aad4768cc9282fc794d6a3b8bd283437ee`.
  - **Pruebas ejecutadas:** `0` (`pytest` no está permitido en este entorno; el CI del repositorio las ejecuta por separado).
  - **Limitaciones:** Análisis estático sobre el repositorio sin ejecución en vivo contra la API de GitHub ni inspección directa del sistema de archivos del host fuera del clon auditado.
- **Outstanding blockers:** Ninguno (`0` hallazgos A, `0` hallazgos B y `0` hallazgos C).
- **Authority used:** Auditor Independiente de AAO (`aao-auditor-alt` / Antigravity), autorizado por la resolución delegada en el Issue #25.
- **Next owner/action:** CEO (`alessbarb`) y PM del proyecto para registrar el dictamen sobre `e09a18aad4768cc9282fc794d6a3b8bd283437ee`, actualizar el clon `/root/aao-src` a `e09a18aad4768cc9282fc794d6a3b8bd283437ee` (y, si corresponde según [`docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md`](file:///tmp/tmp.GuGcN4xRQ9/repo/docs/procedures/CEO_RUNBOOK_TRUST_ROOT_UPGRADE.md), la raíz de confianza tras la auditoría `r1-chain`) y ejecutar el ensayo P2/P3 mediante [`scripts/trial/run_trial.sh`](file:///tmp/tmp.GuGcN4xRQ9/repo/scripts/trial/run_trial.sh) en la revisión auditada.
