# Estado actual de AAO

Fecha: 2026-11-02. Describe `origin/main` = `81cb877e94d99729636dc0376887e03f8b284894` (PR #324). Re-comprobar con `git rev-parse origin/main`; si difiere, este documento está desfasado.
Convención (AGENTS.md reglas 1 y 5): cada línea cita fuente (PR, SHA, run, fichero) o va marcada **UNVERIFIED**. «Aportado por coordinador» = dato de la sesión del 2026-11-02 que este documento no pudo reverificar.

## 1. Hito y SHA

| Dato | Valor | Fuente |
|---|---|---|
| main | `81cb877` feat: PM coordinator token issuer (B2) (#324) | `git log origin/main` |
| Último CI en main | run `41426754388`, conclusión `success` (jobs `frontend`, `test`: success) | `gh run view 41426754388` |
| Línea de versión de git en ese run | UNVERIFIED (no se leyó el log del run) | — |
| Fase | Construcción: sin candidato declarado; auditoría independiente diferida al cierre | `docs/HANDOVER_ACCEPTANCE_MATRIX.md` filas 1, 7 |

## 2. Gates de aceptación

Fuente: `docs/HANDOVER_ACCEPTANCE_MATRIX.md` (criterios 1-10 de CEO-DEC-AAO-CONSTRUCTION-2026-10-25; filas E-1, E-2). El texto de la matriz puede ir por detrás de main; abajo, lo que dice la matriz.

| Gate | Estado | Cita |
|---|---|---|
| 1 Candidato con SHA exacto | ABIERTO (diferido) | fila 1 |
| 2 Raíz de confianza sobre candidato | ABIERTO (base instalada, candidato pendiente) | fila 2 |
| 3 Identidades separadas / mínimo privilegio | ABIERTO (parcial; falta ejercicio host W2) | fila 3 |
| 4 Repo canónico protegido | ABIERTO (protección provisional de construcción; reglas finales A/B no aplicadas) | fila 4 |
| 5 Ensayos P2/P3 y negativos | ABIERTO (parcial) | fila 5 |
| 6 Requisitos RA | ABIERTO (pendiente) | fila 6 |
| 7 Auditoría independiente | ABIERTO (aplazada; GOV-REV-001) | fila 7 |
| 8 Auditoría/integración/recuperación operativas | ABIERTO (parcial; integrador OFF) | fila 8 |
| 9 Ciclo R1 auténtico | ABIERTO (no demostrado por W2) | fila 9 |
| 10 Acta de aceptación CEO | ABIERTO (diferido; decisión reservada al CEO) | fila 10 |
| E-1 Gates Fase 0 | ABIERTO | fila E-1 |
| E-2 Piloto §14 + resistencia | ABIERTO | fila E-2 |

Cerrados: ninguno según la matriz (0 de 12). Cerrado no equivale a «hay trabajo fusionado»: la matriz no certifica nada hasta la auditoría final.

## 3. Capacidades

Niveles: implementada (código en main) / desplegada / ejercitada / revisada (auditoría independiente) / aceptada (CEO).

| Capacidad | Impl. | Desplegada | Ejercitada | Revisada | Aceptada | Evidencia / nota |
|---|---|---|---|---|---|---|
| Emisor de token PM (B2) | sí | UNVERIFIED | sí, aportado por coordinador (credenciales emitidas hoy) | **no** | no | #324 `81cb877`; título del propio PR: «needs independent audit» |
| Servicio PM (`pm:service`) | sí (`scripts/run_project_coordinator.py`, #297) | **no habilitado** (aportado por coordinador) | no | no | no | `docs/procedures/PROJECT_COORDINATOR_SERVICE.md`; matriz líneas 25-26 |
| Integrador | sí (`src/aao/integrator.py`) | **OFF** | no | no | no | matriz fila 8 |
| W2 publicación vía GitHub Apps reales | sí (`pr_publisher.py`, `provision_w2_publishers.py`) | UNVERIFIED | **no ejercitado** | no | no | matriz filas 3, 9; `docs/procedures/W2_REAL_GITHUB_APPS.md` |
| Relay push B-2 | prototipo | no | no | no | no | PR #318 borrador; recibos base #253 (matriz fila 8) |
| Proveedores de agentes (Codex, ChatGPT, etc.) | parcial | UNVERIFIED | UNVERIFIED | no | no | rama `feat/chatgpt-conversation-transport` solo local, «not for PR until CEO authorizes provider» |
| Preflight PM | sí (#320, #323 en main) | n/a | sí, ver sec. 7 | no | no | `scripts/pm_deployment_preflight.py` |
| Bootstrap integral de host | en PR | no | UNVERIFIED | no | no | PR #325 / #251 borradores |
| `db:inspection` | UNVERIFIED | UNVERIFIED | UNVERIFIED | no | no | no verificado por este documento |

## 4. PRs abiertos (`gh pr list --state open`, 2026-11-02)

Todos borrador. Ninguno tiene reviews registradas en GitHub (`reviews: []`). «Auditoría» = GOV-REV-001 independiente: ninguna hecha.

| # | Título | Draft | Head | Checks (statusCheckRollup) | Auditoría |
|---|---|---|---|---|---|
| 326 | docs: token rotation without CEO token (design only) | sí | `75c3d83` | 4 SUCCESS | ninguna |
| 325 | feat(bootstrap): integral host bootstrap (renumber) | sí | `695cb31` | 4 SUCCESS | ninguna |
| 318 | feat: prototype durable opt-in push relay transport for B-2 | sí | `e4dd85d` | 4 SUCCESS | pendiente (bloqueo, sec. 6) |
| 299 | fix: harden worker API bootstrap boundary | sí | `28a3d63` | 2 SUCCESS | ninguna |
| 251 | feat(bootstrap): integral host bootstrap (original) | sí | `c6ee903` | 2 SUCCESS | ninguna |

Nota: #325 es renumeración de #251; relación de sustitución inferida del título, no confirmada. #319 (fix, ver sec. 6) no figura entre los abiertos: estado UNVERIFIED (puede estar cerrado o ser borrador local).

## 5. Principales y credenciales emitidas hoy

Fuente de la tabla: aportado por el coordinador el 2026-11-02, quien indica `principal_credentials` en `aao_dev` (solo lectura). Este documento no consultó la BD. Sin tokens ni digests.

| Principal | Tipo / rol | Grants | Caducidad | Emitido | Estado |
|---|---|---|---|---|---|
| `aao-pm-coordinator-20261102101514-a0c6a5ce` | AGENT (PM) | `project.read`, `work.coordinate`, `work.assign` | ninguna (`--no-expiry`) | 2026-11-02 10:15 UTC | activo |
| `aao-publisher-impl-20261102101736-876c2aab` | W2, `aao-impl-codex` | `project.read`, `code.publish` | 2026-11-02T18:17:36Z | 2026-11-02 (ts en el ID: 10:17:36) | activo |
| `aao-publisher-pm-20261102101736-876c2aab` | W2, `aao-pm` | `project.read`, `code.publish` | 2026-11-02T18:17:36Z | idem | activo |
| `aao-publisher-impl-20261102100124-fec37ecc` | W2 (intento fallido) | n/d | n/d | 2026-11-02 (ts en el ID: 10:01:24) | desactivado; limpieza OK |

El principal PM no caduca: solo se retira revocando (`PM_TOKEN_PROVISIONING.md` l.29).

- Grants del principal PM por diseño (coinciden con la tabla): `project.read`, `work.coordinate`, `work.assign` (`PM_TOKEN_PROVISIONING.md` l.24).
- **Hecho:** #324 se fusionó y se usó para emitir credenciales sin auditoría formal GOV-REV-001. Evidencia: título de #324 «needs independent audit»; cero reviews en el repo. Las credenciales emitidas dependen de código no revisado.
- Durante la regla de construcción vigente (memoria: merge de PRs en verde por el coordinador, CEO 2026-10-25) esto está permitido, pero no cuenta como revisión (matriz fila 7).

## 6. Bloqueos y dueño

| Bloqueo | Dueño | Fuente / estado |
|---|---|---|
| #299 (Codex/subagente) | Codex / coordinador | PR #299 borrador; sin review; worktrees `codex-rebuild-299`, `/tmp/aao-rebuild-299-final` |
| Auditoría de #318 | revisor independiente (no constructor) | #318 borrador; sin auditoría |
| #326: decisiones CEO (endpoint de auto-rotación; capacidad emisora W2) | CEO | PR #326, solo diseño («no non-CEO path exists») |
| #319 fix en borrador | coordinador | UNVERIFIED (no listado entre abiertos); contexto: memoria `ci-drift-r1-e2e` |
| Candidato VERIFIED = 0 en proyecto Self Development | coordinador | Aportado por coordinador: consulta de estados -> VERIFIED 0; DONE 3, IN_REVIEW 2, IN_PROGRESS 1, INBOX 1. No reverificado aquí (sin acceso a la BD) |
| Diseño de rol runtime | coordinador / CEO | UNVERIFIED; `--runtime-role` requerido por preflight (`PM_TOKEN_PROVISIONING.md` l.102) |
| `pm:service` no habilitado | coordinador (tras decisión de rol runtime) | aportado por coordinador |
| `db:inspection` | coordinador | UNVERIFIED |

## 7. Preflight

- Revisión probada: árbol congelado de `aao-pm` en `81cb877` (`/srv/aao/frozen/aao-pm/tree`; anterior en `tree.cfd485c-prev`). Fuente: coordinador; no reverificado aquí.
- Ejecutado como `aao-pm` y como `aao-impl-codex`, con `--principal-id aao-pm-coordinator-20261102101514-a0c6a5ce`: **sin MISSING** (coordinador).
- UNVERIFIED restantes (coordinador): `w2:aao-impl-codex:pem/json/publisher-token` (visto desde aao-pm), `w2:aao-pm:pem/json/publisher-token` (visto desde aao-impl-codex), `pm:service`, `w2:live`, `db:inspection`.
- Conteos numéricos PASS/UNVERIFIED: no aportados; UNVERIFIED en este documento.
- Salvedad documentada: ejecutado como usuario CEO, `pm:token` sale UNVERIFIED (no puede `lstat` en `/run/user/1001`); UNVERIFIED no es PASS (`PM_TOKEN_PROVISIONING.md` l.99).
- El preflight no lee el token ni prueba que autentique (l.106).

## 8. Limpieza de host y repo

Salida de `git worktree list` / `git branch -vv` a 81cb877.

| Elemento | Estado | Dueño |
|---|---|---|
| `.claude/worktrees/agent-*` (4 listados; 3 bloqueados) | de agentes Claude efímeros; no tocar | coordinador |
| `.worktrees/codex-bootstrap-hardening` (`fix/codex-bootstrap-hardening`, `06f2cf9`, 1 por delante de origin) | trabajo Codex | Codex |
| `.worktrees/codex-rebuild-299` (`5febcc4`) y `/tmp/aao-rebuild-299-final` (`9e89892`) | trabajo #299; el segundo está en /tmp (volátil) | Codex |
| `.worktrees/integral-host-bootstrap` (`0ecc8df`) | #251/#325 | Antigravity (remoto `agy`) |
| `.worktrees/push-relay-318-fix` (`e4dd85d`), `push-relay-transport` (`51ea6e8`, 3 detrás) | #318 | constructor de #318 |
| Ramas locales con upstream `gone` (~20, p. ej. `feat/phase2-*`) | fusionadas/borradas en remoto; candidatas a limpieza, no borradas aquí | coordinador |
| Archivo | `~/aao-archive/2026-11-02/`: UNVERIFIED (no comprobado desde este worktree) | coordinador |

Servicios locales (coordinador, 2026-11-02): `aao-postgres-1` (dev, compose) arrancado de nuevo por la tarde (hora CET); API uvicorn en 8001 NO activa en ese momento (curl 000). No verificado aquí.

Autorrotación: #326 (diseño) y un PR de implementación en curso; el CEO lo aprobó el 2026-11-02 (coordinador). Ninguno fusionado; el PR de implementación no figura en la lista de abiertos (sec. 4), número UNVERIFIED.

## 9. Actualización de este documento

Dueño: coordinador. Actualizar en cada merge a main o cambio de gate; reescribir el SHA de la cabecera y de la sec. 1, y cada fila afectada con su fuente. Si no hay evidencia, marcar UNVERIFIED en vez de borrar la fila. README debe apuntar aquí (PR aparte).

## 10. Límites

No verificado: log de cada run (solo conclusión de checks); CI de PRs más allá del `statusCheckRollup` de `gh`; comportamiento en runtime; GitHub Apps reales; privilegios de roles de BD; contenido de la BD (conteos de Self Development, de coordinador); conteos numéricos del preflight; archivo en `~/aao-archive`; estado de #319. Tests y CI no son auditoría independiente (AGENTS.md).
