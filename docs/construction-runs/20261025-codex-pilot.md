# Piloto de Codex como agente ejecutor (2026-10-25)

Lo **autorizó el CEO** el 2026-10-25 («autorizado, gpt-6 luna medium»), solo para esta tarea. El proveedor sigue desactivado para la ejecución general: `AAO_AGENT_PROVIDER` se exportó únicamente en el proceso del worker del piloto. El procedimiento es [`CODEX_PROVIDER_ACTIVATION_E2E.md`](../CODEX_PROVIDER_ACTIVATION_E2E.md).

Se ejecutó en la instancia de desarrollo: PostgreSQL `compose.dev.yaml` y API en `127.0.0.1:8001`, proyecto `9d17d6c1-d644-424a-a425-fe7e084c3d91`. Los datos salen de PostgreSQL (`verify` y la tabla `events`); no hay nada simulado.

## Resultado

**La tarea `185cc836-2f7f-4f05-906e-e78ac0095c35` está en DONE.** Codex escribió el parche. La cadena completa, de la tarea a la PR #114 fusionada, es **CONSISTENT** según `verify`.

| Campo | Valor |
|---|---|
| Tarea | Cover the residual-risk boundaries and emergency-stop precedence of `decide_admission` (texto del procedimiento) |
| Base | `94271c2f05a469f3a71ceec1781257fd75d78619` |
| Ejecución | `3ac3eeed-8fba-4fa3-b080-8ce611a7a428` SUCCEEDED, worker `aao-implementer-202610251730` (AGENT) |
| Agente | `backend=codex`, `provider=openai`, `model=gpt-6-luna` (fijado con `AAO_AGENT_CODEX_MODEL`), `backend_version=codex-cli 0.164.0-x86_64-unknown-linux-musl`, esfuerzo `medium` (fijo en el runner), 36,6 s, salida 0 |
| Sesión del modelo | `CODEX_HOME` dedicado en `~/.local/share/aao/codex-agent`; el login (`--device-auth`) lo hizo el CEO. No se usó la sesión del operador |
| Aislamiento | Sonda `codex_isolation_probe.py` antes del lanzamiento: `ok: true`, sin fugas |
| Candidato | `27a09c00b0401ac2e860fc699fa35246bd4cbc04`, en `refs/aao/candidates/…`, autor `aao-implementer-202610251730@agents.aao.invalid` |
| Propuesta | `15f5e873-d094-4f27-8685-75bbd75f58c4`, patch_sha256 `67650abde859cff9…`, solo `tests/test_planner.py` (+21 líneas, 2 tests) |
| Check en sandbox | `core-unit` success, salida 0, 966 ms: «21 passed, 1 skipped». `tests/test_planner.py` está en la lista fija de `core-unit`, así que los 2 tests nuevos se ejecutaron en el sandbox (22 tests recogidos en el candidato frente a 20 en la base). `extra_tests` está vacío porque solo recoge ficheros de tests nuevos |
| Evidencia | `sha256:8a30ce1332ac6118f064121fcfe3978ddf5f6a06b2b4aef467c451fd399ed7e5`, registro del check, almacenada y emitida por el implementador |
| Revisión | `f7776db3-df5d-4a25-b51b-cdd9e0381aa8` APPROVE, `aao-auditor-202610251730` (AUDITOR), sobre el SHA candidato |
| PR | [#114](https://github.com/autoaiorg/aao/pull/114): rama `aao/work-185cc836-…-27a09c00b040`, CI en verde; la fusionó el CEO, merge commit `547842297ddec6984f98252fbe4bd6fe3c8c2c17`; CI de `main` en verde |
| Cierre | `work.completed` con el SHA aprobado y el merge commit; `reconciled_by aao-publisher-202610251730` |

**Cronología (UTC):**
- 17:30:57: `work.created`, `capability.evaluated`, `work.admitted`, `execution.staged` y `work.progressed`.
- 17:31:39: `work.patch_proposed`.
- 17:33:25: `work.reviewed` APPROVE.
- 17:33:38: `work.candidate_pushed`.
- 17:33:42: `work.pr_opened` #114.
- 17:36:20: `work.completed`.

## Auditoría (Claude, segunda línea; no es independiente)

1. **Diff:** solo toca `tests/test_planner.py`.
   - Añade `test_residual_risk_boundaries`: `moderate` da READY y `critical` da DEFER.
   - Añade `test_emergency_stop_takes_precedence_over_other_failed_conditions`: con todas las condiciones en contra y `emergency_stop=True`, el resultado es DENY con el motivo «Emergency stop active».
   - Lo contrasté con `src/aao/planner.py`: los tests cumplen los tres criterios.
2. **Suite completa sobre el candidato** (worktree desechable en `27a09c0`): compileall y ruff limpios; pytest `-W error` contra PostgreSQL desechable, **642 passed** (las 640 anteriores más las 2 nuevas).
3. **Mutación**, para comprobar que los tests no son vacíos:
   - poner la parada de emergencia después de la comprobación de autorización hace fallar el test de precedencia;
   - quitar `critical` del conjunto que da DEFER hace fallar el test de límites.
   - Después se restauró el fichero.

## Qué fue automático y qué humano

| Paso | Automático | Humano o asistido |
|---|---|---|
| Sonda de aislamiento | ✓ | la lanzó Claude |
| Login del modelo en el `CODEX_HOME` dedicado | — | CEO |
| Credenciales y grants (`setup`, 8 h) | — | CEO, con su token; Claude no usa el token del CEO |
| Crear la tarea, evaluar la capacidad, admitir y encolar | — | Claude, con la identidad del implementador |
| Reclamar, clonar, **escribir el parche (codex)**, commit candidato, tests en sandbox y proponer | ✓ | Claude lanzó el worker |
| `submit` | — | Claude, con la identidad del implementador |
| Revisión | — | Claude, con la identidad del auditor (lectura del diff, suite completa y mutación) |
| Push y PR | ✓ (script) | Claude, con la identidad del publicador; modo `--github gh`, así que la PR sale con la cuenta del operador |
| CI | ✓ | — |
| Fusión | — | CEO |
| Reconciliación a DONE y `verify` | ✓ (script) | los lanzó Claude |

## Límites

- **Las tres identidades AAO las operó Claude.** Están separadas en AAO, pero no en el sistema operativo. La separación real de identidades es un criterio del traspaso.
- **El check en sandbox ejecuta su lista fija más los ficheros de tests nuevos.** Un fichero de tests ya existente que no esté en la lista de `core-unit` y que el parche modifique no se ejecuta en el sandbox: lo cubren la suite del auditor y la CI de la PR. En este piloto no ocurrió, porque `tests/test_planner.py` está en la lista.
  - *Corrección:* la primera versión de este registro (#115) decía que los tests nuevos no se habían ejecutado en el sandbox. Era falso: la salida del check y el recuento de tests lo desmienten.
- **La evidencia que cita la revisión es el registro del check.** El auditor no puede registrar evidencia, porque `register_evidence` solo admite AGENT. El detalle de la auditoría está en este documento.
- **Coste y tokens no se midieron.** No se ha comprobado si `codex exec` los reporta; queda pendiente para el incremento I5 de [`RONIN_DIFFERENTIAL.md`](../research/RONIN_DIFFERENTIAL.md).
- **La autorización del piloto termina aquí.** Usar Codex en otras tareas requiere una nueva autorización del CEO.
