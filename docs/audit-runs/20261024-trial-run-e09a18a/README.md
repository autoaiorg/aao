# Ensayo P2/P3 completo con el arnés e09a18a (2026-10-24 21:00 UTC)

**Ejecutó:** el CEO, con sudo, `run_trial.sh --rev e09a18aad4768cc9282fc794d6a3b8bd283437ee` sin `--only`.

**Revisión del arnés:** auditada como APPROVE-TECHNICAL, sin ningún hallazgo ([registro](../20261024-agy-p2p3-trial-e09a18a/README.md)).

**Raíz de confianza instalada:** `0a55daf`, sin cambios en este paso.

**Análisis:** Claude (PM). No es una revisión independiente.

**Evidencia:**
- [`evidence-…tgz`](evidence-20261024T210029.560027569Z.tgz), sha256 `5b05e1ff…`; incluye `SHA256SUMS`;
- [`run.log`](run.log), sha256 `4dd505fb…`;
- comprobación de secretos (PM): sin tokens ni claves.

## Resultados

| Prueba | Resultado |
|---|---|
| A-06, A-09, A-14, P3-01, P3-03, P3-09 | **PASS** |
| A-10 (las 9 Apps) | **PASS** |
| FORK-BRANCH, A-11 | **PASS** (la PR #6 la abrió aao-pm desde `aao-trial-codex`) |
| A-01, A-02, P3-02 (×3 implementadores) | EQUIVALENCE-PENDING, a falta de la decisión R3 del CEO |
| A-12, y A-10 de la App de sondeo | NOT RUN, como era de esperar |
| A-07, A-08, A-13, P3-04, P3-08, P3-11 | NOT RUN: son pruebas manuales |
| A-03, A-04, P3-05, P3-07, P3-12 | FAIL, por el **defecto D7 del arnés** |
| A-05, P3-06 | FAIL, por el **defecto D8 del arnés** |
| **P3-10** | **FAIL, hallazgo real**: ver abajo |

## D7 y D8: defectos del arnés, corregidos en la revisión siguiente

**D7.** STAGE-COMMIT empujaba siempre a `aao-trial/required-<id>`. Esa rama ya existía desde la ejecución anterior, así que el candidato nuevo era un non-fast-forward y el push se rechazaba. Ahora la rama incluye el identificador de la ejecución.

**D8.** El `git commit-tree` del arnés no recibía mensaje, por lo que lo esperaba por stdin, que era la terminal del CEO, y agotaba los 30 s (`TimeoutExpired`). Ahora el mensaje se pasa por `input`.

El código de producción (`integrator.py`, `r1_pipeline.py`, `manifest_audit.py` y `local_candidate_controller.py`) ya pasa el mensaje, así que no le afecta.

## P3-10: hallazgo real (protección ausente)

**Qué pasó.** La PR #6 la abrió `aao-pm[bot]` desde el fork `autoaiorg/aao-trial-codex` y modifica `.github/workflows/test.yml`.

La ejecución `40132652973`:
- evento `pull_request`;
- `triggering_actor` y `actor`: `aao-pm[bot]`;
- `head_repository`: `autoaiorg/aao-trial-codex`.

**Ejecutó el job `test` sin aprobación**, con conclusión `success`. Y eso pese a que la política del repositorio de ensayo es `all_external_contributors`.

**Por qué no lo frenó la política.** La documentación de GitHub define "external contributors" como usuarios que no son miembros del repositorio ni de la organización, y dice que comprueba tanto al autor de la PR como al actor del evento. No dice nada de las GitHub Apps. Según la evidencia, el bot de una App de la propia organización no cuenta como externo.

**Qué no alcanza.** La evidencia y los controles existentes limitan el alcance:
- Una ejecución `pull_request` desde un fork no recibe secretos y su `GITHUB_TOKEN` es de solo lectura. La configuración del repositorio también es `read` por defecto.
- RA-01 clasifica `.github/workflows/` como R2 como mínimo, así que el emisor R1 nunca integra un cambio de workflows.
- Los checks obligatorios se evalúan sobre M, la fusión que el integrador empuja a `aao-staging`, y M usa el workflow de `main`. El check de la PR no cuenta para ruleset B.

**Riesgo residual.** Un implementador, a través de su fork y de la PR que abre aao-pm, puede ejecutar código arbitrario en un runner alojado por GitHub sin aprobación humana, con un token de solo lectura y sin secretos.

**Relacionado.** El repositorio canónico `autoaiorg/aao` tiene una política más débil, `first_time_contributors`.

**Decisión R3 pendiente del CEO.** El P3 exige que no se ejecute sin aprobación, y no se cumple.

## Decisión del CEO (R3, 2026-10-24): se acepta el riesgo residual de P3-10

P3-10 queda como **FAIL con riesgo residual aceptado**. La aceptación queda sujeta a estas condiciones:

1. RA-01 mantiene `.github/workflows/` como mínimo en R2. Hoy en `docs/protected-routes.json`: `minimum_risk_class: R2`.
2. `default_workflow_permissions` sigue en `read`. Comprobado el 2026-10-24 en `autoaiorg/aao`.
3. No hay secretos, variables ni entornos de Actions:
   - repositorios: comprobado el 2026-10-24, 0 en `autoaiorg/aao` y 0 en `autoaiorg/aao-governance-trial`;
   - organización: **pendiente de que lo verifique el CEO**, porque la API exige `admin:org`.
4. La política de aprobación del repositorio canónico pasa de `first_time_contributors` a `all_external_contributors`. Es una operación administrativa que va en el próximo procedimiento consolidado del CEO.

Si alguna condición deja de cumplirse, la aceptación se invalida.
