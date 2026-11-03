# AUDITOR-DICTAMEN-REQUEST-R2-2026-11-03
## Solicitud de dictamen R2 para la activación de la autonomía R2 y del integrador

> **BORRADOR. NO FIRMADO. SIN EFECTO.**
> Esta solicitud no concede, activa ni autoriza nada. Un dictamen emitido a partir de ella **tampoco** activa R2. Solo aporta evidencia para la decisión del CEO descrita en [`CEO-REQ-R2-AUTONOMY-ACTIVATION-2026-11-03.md`](CEO-REQ-R2-AUTONOMY-ACTIVATION-2026-11-03.md) §7.
> Fusionar este archivo no es una aprobación ([CEO-DEC-2026-10-25](CEO-DEC-2026-10-25.md), Decisión 1). `docs/decisions/` es una ruta R3.

**Fecha de redacción original:** 2026-11-03. La evidencia del expediente relacionado está anclada a `f127a7e` y fechada alrededor de las 12:20 UTC; debe revalidarse y fijarse de nuevo antes de iniciar el dictamen.
**Redacta:** agente Claude del equipo constructor. **Claude está recusado** como auditor de este alcance: es autor de commits en él y ha participado en el diseño (§4.3.1).
**Normas aplicables:** GOV-REV-001 v1.1 (`docs/AUTONOMOUS_AUDIT_POLICY.md`), pasos 1 a 9, y GOV-REV-002 §3.2 (R2), §4.3, §5, §6.1, §6.2 y §9. GOV-REV-002 sigue en BORRADOR (P-01 de la solicitud al CEO): el auditor la aplica como especificación de la evaluación, no como autoridad vigente.

---

## 1. SHA que se audita

- **SHA de referencia al redactar:** `f127a7e37b41e015b07ab25bb076201178a96795` (`origin/main`, 2026-11-03).
- **Hay que volver a fijarlo al empezar la auditoría.** El dictamen se emite sobre el SHA del candidato congelado que se vaya a desplegar en `/srv/aao/frozen/*`. No puede ser `f127a7e` si `main` ha avanzado o si antes hay que corregir algo (por ejemplo P-18).
- Antes de evaluar, el auditor registra el SHA, `base_sha`, el árbol y la versión de Git (GOV-REV-002 §5.1; GOV-REV-001, paso 1).
- Hay que fijar también, por separado, el SHA del paquete de evidencia (GOV-REV-001, paso 1).

## 2. Alcance

1. **Mecanismo que se activa:** `deploy/systemd/aao-integrator-tick.{service,timer}`, `src/aao/r1_pipeline.py`, `src/aao/integrator.py`, `src/aao/integration_authorization.py`, `src/aao/authorization_issuer.py`, `src/aao/auditor_dispatch.py`, `src/aao/governance_ledger.py`, `src/aao/identity_attribution.py`, `src/aao/github_app_auth.py`, `src/aao/protected_routes.py` y `src/aao/supervisor*.py`. Además, `scripts/make_trust_root_files.py`, `scripts/verify_trust_root_host.py` y `scripts/governance/canonical_protection.py`.
2. **Todo el árbol afectado** (requisito R2, §3.2): todas las rutas con `minimum_risk_class` R2 de `docs/protected-routes.json` **y sus importadores**, hasta el cierre transitivo dentro de `src/`, `scripts/` y `deploy/`. El auditor debe incluir en el expediente el método con el que obtuvo la lista de importadores (comando y salida).
3. **Configuración efectiva que se va a desplegar**, aunque no esté en el repositorio: el contenido no secreto de `registry.json` (`enabled_risk_classes`, `ra_status`, `trusted_auditor_revisions`, `auditor_models`, `author_models`, `push_principals`, `required_check_publishers`, `protected_routes_sha256`), el campo `repo` de `/etc/aao-integrator/config.json`, los rulesets del canónico y los permisos y repositorios de instalación de las Apps.
4. **Fuera de alcance:** R3, los proveedores y la producción. Si algún hallazgo exige R3, se marca como tal y no se resuelve en el dictamen.

## 3. Requisito de modelo distinto y recusación

1. El auditor no puede estar recusado según el §4.3.1. Su modelo y su uid no pueden coincidir con los del autor de **ningún** commit del rango auditado. No puede haber diseñado ni implementado el componente. El candidato no puede modificar su propio código, su clave ni su habilitación.
2. La atribución se calcula con fuentes autenticadas (§4.3.2): uid efectivo, principal de push o evento de GitHub, firmas vinculadas en el registro y check runs con `app_id`. **No sirven** para descartar una recusación los campos `author` y `committer`, `Co-Authored-By`, `producer` ni `implementer_id` (§4.3.3).
3. **El rango hay que fijarlo:** `<base_auditada>..<SHA>`. El auditor debe declarar qué base usa (por ejemplo, la última revisión con un dictamen válido, o la raíz del repositorio si no existe ninguna) y justificarla.
4. **Bloqueo previsible, que este redactor no puede resolver:**
   - El registro declara `auditor_models = {aao-auditor: claude, aao-auditor-alt: gemini}` y `author_models = {aao-impl-claude: claude, aao-impl-codex: codex, aao-impl-ag: gemini}`. El §4.2 y D13 asignan el auditor alterno a Codex.
   - Si el rango contiene commits de los tres modelos, puede que **ningún auditor quede sin recusar**. En ese caso la materia es R3 (§4.3.8) y decide el CEO.
   - Con RA-02 en PENDING, la atribución no está resuelta y el resultado tiene que ser `INCONCLUSIVE`, nunca `APPROVE` (§4.3.4).
   - El auditor debe pronunciarse expresamente sobre este punto antes de entrar en el fondo.
5. Mientras F2 no esté en PASS, el dictamen debe decir que la independencia no está demostrada y que el dictamen es **INCONCLUSIVE** conforme a §4.3.4. No debe afirmar que revisor y autor comparten uid o credenciales, salvo que exista evidencia autenticada específica que lo demuestre.

## 4. Pruebas negativas que el auditor debe ejecutar o evaluar

Hay que ejecutarlas sobre el SHA re-fijado, registrando el comando, la salida y su digest:

- `PYTHONPATH=src python -m pytest -m nt`: casos NT-01-1…5, NT-02-1…10, NT-03-1…5, NT-03-7, NT-07-1, NT-09-3 y NT-09-4. El mapa a pruebas está en `docs/procedures/NT_TRACEABILITY.md` y en la solicitud al CEO (§4).
- Pruebas R2:
  - `test_authorization_rejects_auditor_with_same_model_as_author_for_r2`;
  - `test_authorization_rejects_same_model_and_long_or_naive_dates`;
  - `test_authorization_rejects_protected_path_change_below_minimum_class` (las tres en `tests/test_governance_mechanisms.py`);
  - `test_protected_path_does_not_emit_when_r2_is_disabled` (`tests/test_e2e_r1_integration.py`).
- **Faltan, y el auditor debe tratarlas como hallazgo si siguen faltando:**
  - NT-03-6;
  - NT-09-1 y NT-09-2, en vivo contra GitHub con la credencial efectiva;
  - la agregación causal (§3.5; plan §8.2);
  - una autorización R2 válida de extremo a extremo (hoy imposible por `authorization_issuer.py:112-113`);
  - las variantes de NT-09-3 con otra credencial u otra protección.
- **Referencia, sin valor de evidencia:** el redactor obtuvo en local, sobre `f127a7e`, `43 passed` con `-m nt` y `4 passed` en las pruebas R2. No es independiente ni corresponde a un candidato.

## 5. Preguntas que el dictamen debe responder

1. ¿El §12.5.2 está satisfecho, con evidencia PASS vinculada al SHA, para F2, RA-02, RA-03, RA-09, el plan §8.2 y GOV-REV-001?
2. ¿Puede el integrador, con la configuración efectiva, promover algo distinto del árbol autorizado, o algo R2 sin un dictamen R2 de modelo distinto?
3. ¿Un cambio R2 fusionado puede desactivar o debilitar los controles que lo vigilan (auditor, gate, supervisor, CI) sin que se detecte? ¿Qué controles compensatorios existen?
4. ¿Coinciden los rulesets efectivos con A/B/C (`canonical_protection.py verify`), y es el integrador la única identidad con escritura en `main`?
5. ¿La reversión del §6 de la solicitud al CEO es suficiente y se puede ejecutar?

## 6. Formato del dictamen

Un documento **JSON canónico y firmado** con la clave del auditor registrada en la raíz de confianza (§5.3). Contiene, como mínimo:

```
target_ref, candidate_sha, base_sha, merge_result_tree_sha (o tree_sha del candidato), git_version,
risk_class: "R2", assurance_level, policy_id, policy_sha256, protected_paths_sha256,
auditor_id, auditor_key_id, auditor_code_revision, auditor_model,
audited_range: {base, head, commits_count, author_models_resolved[], attribution_sources[]},
recusal_assessment: {recused: bool, reasons[], unresolved_attributions[]},
attribution[{sha, principal, source, evidence_sha256}],
checks_executed[{name, cmd, result, evidence_sha256}],
negative_tests[{id, test, result, evidence_sha256}], missing_negative_tests[],
whole_tree_review: {paths[], importers_method, importers_evidence_sha256},
scope, known_limitations, residual_risks,
permitted_operations, prohibited_operations,
findings[{id, severity, claim, evidence, reproduction, disposition}],
expediente_sha256, verdict, issued_at, expires_at
```

- `verdict` ∈ {`APPROVE`, `REJECT`, `VETO`, `INCONCLUSIVE`} (§5.2). Un `VETO` cumple el §5.2.1.
- El dictamen caduca a las 72 h, o antes si cambian el árbol, la base, la política o la clave (§5.2, `EXPIRED`).
- Si falta cualquier campo, el dictamen no es válido (§5.3).
- `permitted_operations` solo puede contener operaciones de la solicitud al CEO, §2 (A-1 a A-5). El dictamen no puede ampliarlas.
- Hay que guardar el expediente completo (comandos, salidas y digests) en `docs/audit-runs/<fecha>-r2-activation-<sha8>/`.

## 7. Quién puede emitirlo

Un auditor que cumpla todo lo siguiente:
- no está recusado según el §3;
- su modelo es distinto del de todos los autores del rango;
- no ha participado en el diseño ni en la construcción del candidato (matriz de traspaso, criterio 7: «Antigravity u otro revisor que no haya construido el candidato»).

Si nadie cumple estas condiciones, la solicitud queda bloqueada y se escala al CEO como R3 (§4.3.8). Que venza un plazo no aprueba nada (§5.5.3).
