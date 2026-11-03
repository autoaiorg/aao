# CEO-REQ-R2-AUTONOMY-ACTIVATION-2026-11-03
## Solicitud de activación de la autonomía R2 y del integrador (§12.5 de GOV-REV-002)

> **BORRADOR. NO FIRMADO. SIN EFECTO.**
> Este documento no concede, activa ni autoriza nada. Solo tendría efecto si el CEO firma una decisión propia (`CEO-DEC-…`, R3) sobre un SHA exacto, **después** de que exista el dictamen pedido en [`AUDITOR-DICTAMEN-REQUEST-R2-2026-11-03.md`](AUDITOR-DICTAMEN-REQUEST-R2-2026-11-03.md).
> Fusionar este archivo **no** es una aprobación: «No utilices la fusión de una PR como sustituto de una autorización formal en futuras decisiones R3» ([CEO-DEC-2026-10-25](CEO-DEC-2026-10-25.md), Decisión 1). `docs/decisions/` es ruta protegida R3 (`docs/protected-routes.json`).

**Fecha de redacción:** 2026-11-03, alrededor de las 12:20 UTC.
**Redacta:** agente Claude en el equipo constructor ([CEO-DEC-AAO-CONSTRUCTION-2026-10-25](CEO-DEC-AAO-CONSTRUCTION-2026-10-25.md)). No implementa la activación, no audita y no fusiona.
**Origen:** instrucción del CEO del 2026-11-03, transmitida por el coordinador, de «lanzar la solicitud del §12.5». En el repositorio no consta un registro de esa instrucción.
**Revisión observada:** `origin/main` = `f127a7e37b41e015b07ab25bb076201178a96795`.
**Canal previsto:** issue `ceo-proposal` (D7-bis; GOV-REV-002 §10.1), con enlace a este documento y al dictamen.

---

## 1. Qué exige exactamente el §12.5 y qué no define

Texto de `docs/AUTONOMOUS_GOVERNANCE_POLICY.md:596-605`:

1. La autonomía R2 **no** se activa con P5 ni con la extinción del arranque (§12.5.1).
2. Solo se activa con evidencia PASS, vinculada a SHA, de todo lo siguiente (§12.5.2):
   - el aislamiento (F2; plan v3.1, §8.1);
   - la atribución de actores y un ledger independiente (RA-02);
   - la promoción con árbol autorizado (RA-03) y el comportamiento del servidor en la configuración real (RA-09);
   - las pruebas del integrador (plan v3.1, §8.2);
   - las demás precondiciones aplicables de GOV-REV-001.
3. Si falta cualquiera, no se fusiona nada R2 (§12.5.3; también §13.5).

Requisitos de clase para cada cambio R2 (`AUTONOMOUS_GOVERNANCE_POLICY.md:152`): los de R1, más pruebas negativas, revisión de todo el árbol afectado (importadores incluidos) y dictamen de un auditor no recusado cuyo modelo sea distinto del del autor. El integrador lo comprueba en el §6.2.6.

**El §12.5 no define** quién solicita, en qué formato ni qué firma el CEO. Este borrador no inventa ese procedimiento. Se apoya en los instrumentos vigentes que sí lo fijan:

| Instrumento | Qué dice | Referencia |
|---|---|---|
| GOV-REV-002, estado | «BORRADOR. **No está vigente.** Solo entra en vigor si el CEO aprueba la propuesta P5» | `docs/AUTONOMOUS_GOVERNANCE_POLICY.md:4` |
| P5 | No consta aprobada en `docs/decisions/`. CEO-DEC-REPO-PUBLIC: «No aprueba P1, P2, P3 ni P5, ni activa R2» | `docs/decisions/CEO-DEC-REPO-PUBLIC-2026-10-21.md:24` |
| CEO-DEC-2026-10-25, Decisión 4 | «No autorizados todavía: `--enable-integrator` y la autonomía R2». Exige demostrar el canal de incidentes, la separación de privilegios, el aislamiento del auditor, la protección real de `main`, las pruebas obligatorias y los estados RA | `docs/decisions/CEO-DEC-2026-10-25.md`, Decisión 4 |
| CEO-DEC-P2P3-2026-10-24 §5 | «**No se activa el integrador** mientras `main` no tenga una protección preventiva verificada». §2, condición 6: «No se habilita R2 bajo esta excepción» | `docs/decisions/CEO-DEC-P2P3-2026-10-24.md:41,59,74-75` |
| CEO-DEC-AAO-CONSTRUCTION §4 | Diez criterios de traspaso. «La activación inicial podrá limitarse a R1. No se entenderá incluida la autorización R2» | `docs/decisions/CEO-DEC-AAO-CONSTRUCTION-2026-10-25.md`, §4 |
| CEO-DEC-ENTERPRISE-MODEL, D-08 | La activación del integrador y la de R2 requieren «decisión expresa del CEO (`autonomy.ceiling.raise`), apoyada en evidencia reproducible». §6: la decisión no autoriza R2 ni la activación del integrador | `docs/decisions/CEO-DEC-ENTERPRISE-MODEL-2026-10-26.md:39`; `src/aao/policy.py:17` (operación reservada) |
| Cadena de dependencias | P5 → operaciones de arranque (§12.3) → primera fusión R1 válida del integrador (§12.4) → evidencia del §12.5 → decisión del CEO. El plan sitúa la primera PR R2 controlada en F5, después de F4 | GOV-REV-002 §12.3-§12.5 y §13.4-§13.5; plan v3.1, §7 (F4, F5) |

**Consecuencia.** Encender el integrador es un acto **R1** (`autonomy.ceiling.raise`). Activar R2 es **otro acto posterior**. Esta solicitud cubre los dos porque así lo pidió el CEO, pero R2 depende de que la activación R1 se haya completado antes (P-02 y P-03).

## 2. Alcance que se solicitaría

| # | Elemento | Qué se activaría | Hoy |
|---|---|---|---|
| A-1 | Temporizador `aao-integrator-tick.timer` (`deploy/systemd/aao-integrator-tick.timer`) | Un pase cada minuto de `aao.r1_pipeline:main tick` como `aao-integrator` (`deploy/systemd/aao-integrator-tick.service`) | `inactive` y `disabled` (`systemctl is-active` / `is-enabled`, 2026-11-03 12:20 UTC) |
| A-2 | Repositorio servido por el integrador | `autoaiorg/aao`, ref `refs/heads/main` | `/etc/aao-integrator/config.json` apunta a `autoaiorg/aao-governance-trial` (lectura del campo `repo`, 2026-11-03) |
| A-3 | Clases habilitadas en el registro de confianza | `enabled_risk_classes` = `["R1","R2"]` | `["R1"]` (`/srv/aao/trust/registry.json`, lectura de solo ese campo) |
| A-4 | Áreas R2 (`docs/protected-routes.json`, entradas con `minimum_risk_class: R2`) | Auditor y ledger: `independent_audit.py`, `manifest_audit.py`, `auditor_dispatch.py`. Gate e integrador: `integrator.py`, `integration_authorization.py`, `r1_pipeline.py`, `pr_conformity.py`, `review.py`, `policy.py`. Supervisor y notificador: `supervisor.py`, `supervisor_service.py`, `notifier.py`. CI y workflows: `.github/workflows/`, `policy*.json`. Reglas de agentes: `AGENTS.md`, `docs/AGENT_OPERATING_RULES.md`. Y el resto de entradas R2 de ese archivo | R2 bloqueado |
| A-5 | Permiso `workflows` de la App `aao-integrator` (5447984) | Solo si el alcance incluye `.github/workflows/`: la App no puede promover árboles que cambien workflows sin ese permiso | La App declara `checks:read, contents:write, metadata:read, pull_requests:write, statuses:read`, sin `workflows` (`gh api apps/aao-integrator`, 2026-11-03) |

**Fuera de alcance:** R3 (incluidas la raíz de confianza, `docs/decisions/` y la política normativa), los proveedores de modelo nuevos, la producción y los efectos externos. Tampoco entra cualquier cambio de custodia de claves (D-06).

**Opción que el CEO podría elegir:** R2 **sin** `.github/workflows/`. A-5 no haría falta y el riesgo bajaría, pero esa exclusión requiere una decisión expresa y no puede reducir la clase de la ruta (§3.4.4).

## 3. Precondiciones, con su estado y su evidencia

Estados posibles: **CUMPLIDO** (hay evidencia citada), **NO CUMPLIDO** (la evidencia muestra que falta) y **NO VERIFICADO** (no hay evidencia suficiente en ningún sentido). Ninguna fila se da por cumplida sin evidencia.

| ID | Precondición | Fuente | Estado | Evidencia y límites |
|---|---|---|---|---|
| P-01 | GOV-REV-002 vigente (P5 aprobada sobre su SHA) | §1.2, §15.1 | **NO CUMPLIDO** | `AUTONOMOUS_GOVERNANCE_POLICY.md:4` dice BORRADOR. Ninguna decisión aprueba P5 (búsqueda de `P5` en `docs/decisions/`) |
| P-02 | Arranque (§12.3) ejecutado y extinguido (§12.4): primera fusión R1 válida del integrador | §12.4, §13.4 | **NO CUMPLIDO** | Integrador `disabled`. Matriz, criterio 9: «ABIERTO … No se ha acreditado un ciclo real» (`HANDOVER_ACCEPTANCE_MATRIX.md:30`) |
| P-03 | Decisión del CEO que active el integrador en R1 (`autonomy.ceiling.raise`) | CEO-DEC-2026-10-25 D4; D-08 | **NO CUMPLIDO** | No hay registro. D4 lo mantiene «SIGUE BLOQUEADA» |
| P-04 | Aislamiento F2 (plan §8.1) en PASS, vinculado al SHA candidato | §12.5.2 | **NO VERIFICADO** | Hay evidencia parcial en revisiones anteriores (probe del jail de Codex `ok:true` sobre `f8f650d`, `HANDOVER_ACCEPTANCE_MATRIX.md:13`). Matriz, criterio 3: ABIERTO. No hay una matriz §8.1 completa en PASS sobre un candidato |
| P-05 | RA-01 PASS | §16.0; `integrator.py:338,404-405` | **NO CUMPLIDO** | `ra_status.RA-01 = PENDING` en `/srv/aao/trust/registry.json` (lectura 2026-11-03) |
| P-06 | RA-02 PASS (atribución y ledger independiente) | §12.5.2 | **NO CUMPLIDO** | `RA-02 = PENDING` (ídem). `NT_TRACEABILITY.md`: «No cases are marked PASS» |
| P-07 | RA-03 PASS | §12.5.2 | **NO CUMPLIDO** | `RA-03 = PENDING` |
| P-08 | RA-07 PASS (latidos) | §6.2.12; `integrator.py:341` | **NO CUMPLIDO** | `RA-07 = PENDING` |
| P-09 | RA-09 PASS (servidor real con la credencial efectiva) | §12.5.2 | **NO CUMPLIDO** | `RA-09 = PENDING`. NT-09-1 y NT-09-2 son «live-trial … trial not run» (`docs/procedures/NT_TRACEABILITY.md`) |
| P-10 | Pruebas del integrador (plan §8.2) en PASS sobre el SHA candidato | §12.5.2 | **NO VERIFICADO** | Hay pruebas unitarias (§4). Ejecución local en `f127a7e`: 43 + 4 passed. No es un candidato, no es una ejecución independiente y falta el caso de agregación causal |
| P-11 | Pruebas negativas completas (§16.1-§16.5 y casos R2) | R2, §3.2 | **NO CUMPLIDO** | Faltan NT-03-6, NT-09-1, NT-09-2 y una prueba de agregación causal (§3.5; último punto del plan §8.2). Detalle en §4 |
| P-12 | Protección preventiva de `main` verificada: rulesets A/B/C, P retirado, `canonical_protection.py verify` en PASS | P2P3 §5; matriz, criterio 4 | **NO CUMPLIDO** | `gh api repos/autoaiorg/aao/rulesets` (2026-11-03 12:20 UTC) devuelve dos rulesets activos. **25937576** «P main: construccion (provisional)»: deletion, non_fast_forward, pull_request con 0 aprobaciones, checks `test`/`frontend` (App 15368), `bypass_actors: []`. **25937577** «C tags»: creation, update y deletion sobre `~ALL`, bypass solo para 5447984. No existen A ni B. Con P en vigor y sin bypass, un push directo del integrador a `main` debería ser rechazado. Esto se infiere de la definición del ruleset; no se ha probado |
| P-13 | Permisos de la App integradora adecuados para R2 | P2, línea 48 | **NO CUMPLIDO** (si el alcance incluye workflows) | La App no tiene `workflows` (`gh api apps/aao-integrator`). `docs/proposals/P2_GITHUB_IDENTITIES_AND_PERMISSIONS.md:48`: «Se añadirá al activar R2 (§12.5), con decisión del CEO» |
| P-14 | Solo el integrador tiene `contents:write` en el canónico | P2:55 | **NO VERIFICADO** | Permisos declarados por cada App (`gh api apps/<slug>`): `aao-impl-codex` y `aao-impl-claude` = `contents:write, workflows:write`; `aao-auditor` y `aao-auditor-alt` = `contents:read`; `aao-pm` = `contents:read`; `aao-supervisor` = `contents:read`; `aao-notifier` = `issues:write`. El slug `aao-impl-ag` devuelve 404. **No se consultó en qué repositorios está instalada cada App**, y eso es lo que decide la condición |
| P-15 | Raíz de confianza verificada sobre el candidato | §12.3.1; matriz, criterio 2 | **NO CUMPLIDO** | `/var/lib/aao-trust-verify/status.json`: `result: PASS`, `expected_revision: 0a55daf5ee08c7f10c6c56224da145228c549011`, `verified_at: 2026-11-02T16:25:28Z`. Solo vale para `0a55daf`. Los árboles congelados de integrador, auditor y supervisor están en `0a55daf` (`.git/HEAD`). `/srv/aao/frozen/aao-auditor-alt/tree/.git/HEAD` no existe. `TRUST_ROOT_HOST_INSTALL.md:3`: «REGENERATION REQUIRED» |
| P-16 | `trusted_auditor_revisions` contiene la revisión del auditor candidato | §6.2.7 | **NO CUMPLIDO** | El registro contiene solo `0a55daf…` |
| P-17 | `enabled_risk_classes` incluye R2 | §6.2.6; `integration_authorization.py:192-194` | **NO CUMPLIDO** | Valor `["R1"]`. Cambiarlo modifica la raíz de confianza, que es R3 y la ejecuta el CEO con sudo |
| P-18 | El emisor de autorizaciones puede emitir R2 | código | **NO CUMPLIDO** | `src/aao/authorization_issuer.py:112-113` lanza `AuditError("R1 autonomy refused: …")` para cualquier clase distinta de R1, **incluso con R2 habilitado**. `NT_TRACEABILITY.md`: «The runtime authorization issuer refuses every protected-route classification above R1». Corregirlo toca una ruta R2 |
| P-19 | La configuración del integrador apunta al canónico | A-2 | **NO CUMPLIDO** | `repo = autoaiorg/aao-governance-trial` |
| P-20 | Identidades de los auditores y modelo distinto del autor, acreditados | §4.2, §4.3, §6.2.6 | **NO VERIFICADO** | Registro: `auditor_models = {aao-auditor: claude, aao-auditor-alt: gemini}` y `author_models = {aao-impl-ag: gemini, aao-impl-claude: claude, aao-impl-codex: codex}`. Son cadenas declaradas, no atestaciones. **Discrepancia:** §4.2 y D13 dicen que el auditor alterno es Codex. Con RA-02 PENDING, la atribución no está resuelta, y el §4.3.4 da `INCONCLUSIVE` |
| P-21 | Vigilancia y reverificación en marcha | §7; §6.2.12 | **CUMPLIDO** (solo como estado de las unidades) | `systemctl is-active` devuelve `active` para `aao-trust-root-verify.timer`, `aao-supervisor-heartbeat.timer`, `aao-supervisor-intake.service` y `aao-auditor-dispatch.path` (2026-11-03 12:20 UTC, sin sudo). No demuestra que la vigilancia sea correcta ni independiente (§7.4.7), y el código es el de `0a55daf` |
| P-22 | Segunda línea sobre el código del auditor (§9) | §9.1 | **NO VERIFICADO** | No hay registro de una revisión §9 sobre la revisión del auditor que se activaría |
| P-23 | Dictamen de un auditor no recusado, de modelo distinto, sobre el árbol completo afectado | R2, §3.2 | **NO CUMPLIDO** | No existe. Se pide en `AUDITOR-DICTAMEN-REQUEST-R2-2026-11-03.md` |
| P-24 | Matriz de traspaso: criterio 4 (protección) y criterio 8 (servicios operativos) | CONSTRUCTION §4 | **NO CUMPLIDO** | `HANDOVER_ACCEPTANCE_MATRIX.md:25,29`: los dos ABIERTO |
| P-25 | Estado de partida seguro: integrador apagado | `ops.py:139-164` | **CUMPLIDO** | `inactive` y `disabled`. Hay un matiz: `ops.py:164` dice «OFF (masked)», pero la unidad **no está enmascarada** y la comprobación solo mira `is-active` |
| P-26 | Claves del integrador: clave privada de la App `aao-integrator` bajo su uid y clave de firma ed25519 registrada | §4.2; `TRUST_ROOT_HOST_INSTALL.md` §3 | **NO VERIFICADO** | Existe `/srv/aao/trust/keys/aao-integrator-ed25519.pub`, y el registro tiene `integrator_key_id = aao-integrator`. `ESTADO_ACTUAL.md:91`: los `.pem` y `.json` de las Apps «habían pasado como metadatos en verificaciones previas; no se revalidó aquí». `:145`: el preflight dio PASS en «Apps config». Sin sudo no se puede comprobar la custodia de la clave privada en `/var/lib/aao-integrator`, ni que la clave de la App corresponda a la App 5447984 |

**Recuento:** 2 CUMPLIDO, 18 NO CUMPLIDO y 6 NO VERIFICADO, sobre 26.

## 4. Pruebas negativas disponibles y las que faltan

Comandos ejecutados por este redactor en `f127a7e`, en local y sin independencia. **No es un candidato y no cuenta como evidencia PASS de ningún RA**:
- `PYTHONPATH=src python3 -m pytest -q -m nt -p no:cacheprovider` dio `43 passed, 1041 deselected`;
- las cuatro pruebas R2 de la tabla, seleccionadas con `-k`, dieron `4 passed`.

| Caso | Prueba (`archivo:línea::nombre`) |
|---|---|
| NT-01-1…5 | `tests/test_ra_controls.py:20,29,38,48,55,67` |
| NT-02-1/2 | `tests/test_manifest_audit.py:436::test_manifest_and_git_metadata_do_not_authenticate_the_implementer` |
| NT-02-3 | `tests/test_ra_controls.py:115` |
| NT-02-4 | `tests/test_pr_conformity.py:148` |
| NT-02-5 | `tests/test_ra_controls.py:89`; `tests/test_github_trial.py:238` |
| NT-02-6/7 | `tests/test_governance_mechanisms.py:511,1690`; `tests/test_manifest_audit.py:497,511` |
| NT-02-8 | `tests/test_governance_mechanisms.py:475`; `tests/test_manifest_audit.py:464` |
| NT-02-9 | `tests/test_governance_mechanisms.py:466`; `tests/test_manifest_audit.py:425`; `tests/test_e2e_r1_integration.py:357` |
| NT-02-10 | `tests/test_ra_controls.py:169` |
| NT-03-1 | `tests/test_governance_mechanisms.py:1855` (solo local, con un remoto bare) |
| NT-03-2 | `tests/test_governance_mechanisms.py:2013`; `tests/test_manifest_audit.py:288` |
| NT-03-3/5 | `tests/test_e2e_r1_integration.py:237`; `tests/test_manifest_audit.py:308`; `tests/test_governance_mechanisms.py:1947` |
| NT-03-4 | `tests/test_governance_mechanisms.py:423,1803` |
| NT-03-7 | `tests/test_manifest_audit.py:278` |
| NT-07-1 | `tests/test_governance_mechanisms.py:1434,1453,1470,1499,1722` |
| NT-09-3 | `tests/test_governance_mechanisms.py:1824` |
| NT-09-4 | `tests/test_governance_mechanisms.py:2024` |
| R2: auditor del mismo modelo que el autor | `tests/test_governance_mechanisms.py::test_authorization_rejects_auditor_with_same_model_as_author_for_r2` (aserción en :1706); `::test_authorization_rejects_same_model_and_long_or_naive_dates` (:403) |
| R2 deshabilitado no emite | `tests/test_e2e_r1_integration.py::test_protected_path_does_not_emit_when_r2_is_disabled` (:297) |
| Ruta R2 por debajo de su clase | `tests/test_governance_mechanisms.py::test_authorization_rejects_protected_path_change_below_minimum_class` (:1519) |

**Faltan:**
- **NT-03-6:** retroceso forzado de `main` a un ancestro. No hay prueba; `NT_TRACEABILITY.md` lo da como «live-trial».
- **NT-09-1 y NT-09-2:** solo pueden demostrarse contra el servidor real de GitHub con la credencial efectiva; el ensayo no se ha ejecutado.
- **Agregación causal (§3.5; plan §8.2, «serie de R1 que en conjunto es R2 sin dictamen R2»):** no se encontró ninguna prueba (búsqueda de `aggregat|agregaci|causal` en `tests/`).
- **R2 positiva de extremo a extremo:** emisión, validación y promoción de una autorización R2 válida. No puede existir mientras se mantenga P-18.
- **Variantes de NT-09-3 con otra credencial u otra protección:** «remain untested» (`NT_TRACEABILITY.md`).

## 5. Radio de impacto

- **Hoy (inferido del código, sin ejecutarlo):** encender el temporizador ejecutaría el integrador contra `autoaiorg/aao-governance-trial` (P-19). El árbol desplegado es `0a55daf`, y en él la puerta de RA está en `/srv/aao/frozen/aao-integrator/tree/src/aao/integrator.py:269,337` («required RA status pending») y el rechazo de lo no-R1 en `…/authorization_issuer.py:113`. Con todos los RA en PENDING, debería fallar cerrado. No escribiría en el canónico.
- **Con el alcance solicitado (A-1 a A-5):** el integrador publicaría commits de fusión en `refs/heads/main` de `autoaiorg/aao` con la App 5447984 (`contents:write` y, si se concede, `workflows`). R2 incluye el código del propio auditor, del gate, del integrador, del supervisor y de la CI. **Una fusión R2 defectuosa puede debilitar los controles que vigilan las fusiones siguientes.** Ese es el riesgo principal.
- **Prevención:** el ruleset A (todavía no aplicado) limitaría el bypass de `main` al integrador. **Detección:** el supervisor (§7.2) y el workflow detectivo. Ninguno de los dos impide un push (§7.2).
- **Recuperación:** congelación, PR de reversión e incidente en el ledger (§6.3.7), con un dictamen sobre la causa.

## 6. Reversión

Todos los pasos marcados **[sudo]** los ejecuta el CEO u operador con sudo en el host. Ningún agente los ejecuta.

```bash
# 1. Apagar el integrador. [sudo]
sudo systemctl disable --now aao-integrator-tick.timer
sudo systemctl stop aao-integrator-tick.service
systemctl is-active aao-integrator-tick.timer     # se espera: inactive
systemctl is-enabled aao-integrator-tick.timer    # se espera: disabled

# 2. (Opcional) Enmascarar. [sudo]
# /etc/systemd/system/aao-integrator-tick.timer es un archivo regular (ls -l, 2026-11-03),
# así que `systemctl mask` se negará mientras exista. Primero hay que apartarlo:
sudo mv /etc/systemd/system/aao-integrator-tick.timer /root/aao-integrator-tick.timer.disabled
sudo systemctl daemon-reload
sudo systemctl mask aao-integrator-tick.timer
```

3. **Retirar R2 de la raíz.** [sudo, R3] Se regenera `registry.json` con `enabled_risk_classes: ["R1"]` mediante `scripts/make_trust_root_files.py` y se reinstala como `aao-trust` (custodia del §4.2). Después se ejecuta `verify_trust_root_host.py`. Ver `docs/procedures/TRUST_ROOT_HOST_INSTALL.md` §3-§4.
4. **Si se concedió `workflows` a la App 5447984:** el CEO lo retira en la configuración de la App en GitHub, que es administración (D4).
5. **Emergencia:** el CEO suspende la instalación de `aao-integrator`. No queda ninguna promoción posible (`P2_GITHUB_IDENTITIES_AND_PERMISSIONS.md:97`).
6. **Rulesets:** con el integrador apagado y A/B aplicados, nada se fusiona, que es el estado fail-closed. Volver a P es una decisión de administración del CEO, no parte de la reversión.
7. **Fusiones ya hechas:** PR de reversión R1 con prioridad y un auditor no recusado (§6.3.7, §7.5).

## 7. Qué firmaría el CEO, y nada más

Firmaría una decisión `CEO-DEC-R2-AUTONOMY-ACTIVATION-<fecha>` (R3, `autonomy.ceiling.raise`, D-08), solo cuando todas las filas del §3 estén en CUMPLIDO y exista el dictamen. Su contenido sería:

1. Encender `aao-integrator-tick.timer` en el host identificado, sirviendo `autoaiorg/aao`, con `target_refs = ["refs/heads/main"]`, desde el árbol congelado en el SHA `<S>` auditado.
2. Instalar el registro de confianza regenerado sobre `<S>`, con `enabled_risk_classes = ["R1","R2"]`, `trusted_auditor_revisions = [<S_auditor>]` y los RA en PASS que respalde la evidencia, identificado por su sha256.
3. Una de dos: conceder `workflows` a la App 5447984, o excluir expresamente `.github/workflows/` del alcance R2 operativo.
4. Aceptar los riesgos residuales que el dictamen enumere, con nombre y caducidad.

**La firma no incluye:** R3, proveedores, producción, cambios de custodia, ni ninguna convalidación de la evidencia que falte. La aprobación de P5 y la activación R1 (P-01 a P-03) son decisiones previas y separadas.

## 8. Lista de tareas pendientes antes de que el CEO pueda firmar (en orden)

| # | Tarea | Rol responsable | Cierra |
|---|---|---|---|
| 1 | Decidir sobre P5: aprobar GOV-REV-002 sobre su SHA, o sustituir expresamente el §12.5 por otro instrumento | CEO (R3), con propuesta del PM | P-01 |
| 2 | Completar y evidenciar el aislamiento F2 (matriz del plan §8.1) bajo cada uid, sobre el candidato | Implementador; CEO ejecuta sudo (P1) | P-04 |
| 3 | Regenerar e instalar la raíz de confianza sobre el candidato, incluido el árbol congelado de `aao-auditor-alt`, y obtener `verify_trust_root_host.py` en PASS | CEO (sudo, R3), con un artefacto auditado | P-15, P-16 |
| 4 | Ejecutar el ensayo P2/P3 y las pruebas en vivo (NT-09-1, NT-09-2 y NT-03-6). Llevar RA-01, 02, 03, 07 y 09 a PASS con evidencia vinculada al SHA | Implementador y auditor no recusado; el CEO reinstala el registro | P-05 a P-09 |
| 5 | Añadir la prueba de agregación causal y las variantes de NT-09-3 | Implementador (cambio R2) | P-11 |
| 6 | Aplicar los rulesets A/B, retirar P y obtener `canonical_protection.py verify` en PASS | CEO (administración de GitHub, D4) | P-12, P-24 (criterio 4) |
| 7 | Verificar en qué repositorios está instalada cada App (solo el integrador con `contents:write` en el canónico) y resolver el slug de `aao-impl-ag`. Revalidar con el preflight los metadatos y la custodia de las claves de la App integradora | PM / auditor (lectura); CEO u operador con sudo para el preflight; CEO si hay que reinstalar | P-14, P-26 |
| 8 | Cambiar la configuración del integrador al canónico | CEO (sudo) | P-19 |
| 9 | Decisión R1 del CEO, encendido del integrador y primera fusión R1 válida (§12.4) | CEO; integrador | P-02, P-03, P-24 (criterio 8) |
| 10 | Cambio de código en `authorization_issuer.py:112-113` para emitir R2 bajo `enabled_risk_classes`, con una prueba R2 positiva y negativas. Es en sí un cambio R2 y necesita su propio dictamen | Implementador; auditor no recusado de otro modelo | P-18, P-10 |
| 11 | Conciliar `auditor_models` del registro con el §4.2 y D13 (alterno = Codex o Gemini) y aclarar si la recusación sobre todo el árbol deja algún auditor disponible (§4.3.1, §4.3.8) | PM propone; CEO decide si hace falta (R3) | P-20 |
| 12 | Segunda línea (§9) sobre la revisión del auditor que se activaría | Auditor alterno no autor | P-22 |
| 13 | Decidir el permiso `workflows` de la App integradora o excluir los workflows del alcance | CEO (D4) | P-13 |
| 14 | Dictamen R2 sobre el SHA re-fijado (ver la solicitud adjunta) | Auditor no recusado de modelo distinto | P-23, P-10 |
| 15 | Expediente final con la tabla del §3 actualizada; issue `ceo-proposal` | PM | — |
| 16 | Firma del CEO (§7) | CEO | — |

## 9. Límites de este borrador

- Las lecturas del host se hicieron sin sudo y solo sobre metadatos y campos no secretos: el estado de las unidades, `status.json`, campos concretos de `registry.json`, el campo `repo` de `config.json` y los `.git/HEAD` de los árboles congelados. No se leyeron claves, tokens ni `.env.local`.
- Las consultas a GitHub fueron de solo lectura (`gh api`), a las 12:20 UTC del 2026-11-03. El estado puede cambiar.
- Las pruebas se ejecutaron en local, en un worktree, sobre `f127a7e`. No son independientes y no corresponden a ningún candidato.
- El redactor (Claude) es parte del equipo constructor y **no puede auditar** este alcance.
- No se inició, paró ni habilitó ningún servicio, y no se tocó la raíz de confianza.
