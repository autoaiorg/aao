# Piloto acotado: Codex como agente ejecutor para una sola tarea

**Estado:** el piloto se **ejecutó el 2026-10-25** con la autorización expresa del CEO (`gpt-6-luna`, esfuerzo medium). La tarea quedó en DONE y la PR #114 se fusionó; [registro](construction-runs/20261025-codex-pilot.md). La autorización cubrió solo esa tarea y no activa el proveedor para la ejecución general.

**Por defecto:** el proveedor está desactivado. `agent_runner` rechaza el backend `codex` si falta `AAO_AGENT_PROVIDER=codex` y también si falta un `AAO_AGENT_CODEX_HOME` dedicado. Esas dos variables se exportan solo en el proceso del worker del piloto.

## Tarea del piloto

| Campo | Valor |
|---|---|
| Título | Cover the residual-risk boundaries and emergency-stop precedence of `decide_admission` |
| Descripción | `tests/test_planner.py` no cubre `residual_risk="moderate"` (debe dar READY), `residual_risk="critical"` (debe dar DEFER) ni que la parada de emergencia prevalece aunque fallen las demás condiciones. Añadir esas comprobaciones sin tocar `src/`. |
| Criterios | 1) `moderate` → READY y `critical` → DEFER. 2) Con `emergency_stop=True` y cualquier otra condición en contra, el resultado es DENY con el motivo «Emergency stop active». 3) La suite completa pasa. |
| Rutas admitidas | Solo `tests/`. La política de propuestas ya limita las rutas a `src/` y `tests/`, y la revisión rechaza cualquier cambio en `src/`. |
| Base | `origin/main` en el momento de lanzarlo. |

## Garantías comprobadas antes del piloto

### 1. Red y credenciales del operador (demostrado sin llamar al modelo)

Codex se ejecuta dentro de un jail bwrap propio (`agent_runner.agent_jail`), y además su propio sandbox (`CODEX_SANDBOX_FLAGS`) confina cada comando del modelo:

- **El jail:**
  - sustituye `/home`, `/run` (tokens de runtime, socket de Docker, D-Bus), `/tmp`, `/var/tmp` y `/srv` por tmpfs vacíos;
  - limpia el entorno y aísla PID, IPC y UTS;
  - solo vuelve a montar el workdir desechable, el `CODEX_HOME` dedicado y el binario de codex (de solo lectura).
- **El sandbox de codex:**
  - `workspace-write`, con `network_access=false` fijado explícitamente;
  - `exclude_slash_tmp` y `exclude_tmpdir_env_var` activados;
  - el único root escribible extra es `workdir/scratch`, que es el `TMPDIR`.

`scripts/codex_isolation_probe.py` ejecuta, con `codex sandbox`, una sonda como si fuera un comando del modelo, dentro del mismo jail y con los mismos flags. Lo hace sin modelo y sin login. Evidencia en `construction-runs/codex-isolation/`:

| Comprobación | Con jail (`probe-jail.json`) | Control negativo, sin jail y con red (`probe-control.json`) |
|---|---|---|
| DNS, TCP a Internet | bloqueado | **abierto** |
| Loopback: PostgreSQL dev y test, API :8001 | bloqueado | **abierto** |
| `~/.config/gh/hosts.yml`, `~/.codex/auth.json`, `~/.ssh`, `~/.gitconfig`, `.env.local` | ocultos | **visibles** |
| Tokens AAO en `$XDG_RUNTIME_DIR` | ocultos | **visibles** |
| Socket de Docker, D-Bus | ocultos | **visibles** |
| Escribir en `/etc`, `/usr`, `CODEX_HOME` y el `HOME` del agente | denegado | `HOME`: **escribible** |
| Escribir en el workspace y en `scratch` | permitido | permitido |
| Variables de entorno sensibles; PID visibles | ninguna; 2 | — |

En total, **0 fugas con el jail frente a 19 sin él**. `tests/test_agent_runner.py::test_isolation_probe_finds_no_leak` repite la sonda en cualquier host con codex. En CI no hay codex y se omite. La estructura del jail está cubierta por un test unitario que sí corre en CI.

**Riesgo residual (aceptado para el piloto):** los comandos del modelo pueden **leer** `CODEX_HOME/auth.json`, que es la credencial del propio modelo, pero no tienen red para sacarla. El proceso del CLI de codex sí tiene red, porque la necesita para la API del proveedor. No es un comando del modelo.

### 2. Límite efectivo de reintentos

`POST /v1/work/{id}/stage-agent-run` cuenta todos los intentos del agente para esa tarea, sea cual sea su resultado, y rechaza con 409 el que supere `AAO_AGENT_MAX_ATTEMPTS` (3 por defecto). Lo impone la API sobre PostgreSQL, así que el worker no puede saltárselo: solo puede reclamar ejecuciones que la API haya encolado. Lo cubre el E2E `test_self_development_cycle_from_task_to_merged_pr_and_done`. Para cada intento hay además un límite de tiempo: el lease es de 1800 s, de los que 1650 s son para el modelo.

### 3. Separación de permisos

| Rol | Tipo | Grants (8 h) | Quién lo opera en el piloto |
|---|---|---|---|
| Implementador | AGENT | `project.read`, `work.create`, `work.admit`, `work.progress`, `execution.claim`, `code.propose`, `evidence.submit` | worker automático; el parche lo escribe **codex** |
| Auditor | AUDITOR | `work.review` | humano asistido (Claude): lee el diff y ejecuta la suite completa sobre el candidato |
| Publicador | AGENT | `project.read`, `code.publish` | humano asistido; `--github gh` usa la cuenta del operador |
| CEO | token de desarrollo | emite credenciales y grants, y fusiona | CEO |

El modelo no recibe ninguna de esas credenciales:
- el token del implementador vive en la memoria del worker, y el jail limpia el entorno y aísla los PID;
- los ficheros de token quedan ocultos bajo `/run`;
- la sonda lo comprueba.

## Procedimiento

```sh
P=9d17d6c1-d644-424a-a425-fe7e084c3d91; export PYTHONPATH=src
python scripts/codex_isolation_probe.py            # debe imprimir "ok": true; si no, se aborta
install -d -m 0700 ~/.local/share/aao/codex-agent
CODEX_HOME=~/.local/share/aao/codex-agent codex login --device-auth   # CEO: sesión dedicada
python scripts/self_development_cycle.py --project-id $P setup         # 3 identidades, 8 h
python scripts/self_development_cycle.py --project-id $P task --title "…" --description "…" \
  --criterion "…" --base-sha "$(git rev-parse origin/main)" --agent codex
AAO_AGENT_PROVIDER=codex AAO_AGENT_CODEX_HOME=~/.local/share/aao/codex-agent \
  python scripts/run_self_development_worker.py --project-id $P --principal-id <implementador>
# auditor: comprobar que el diff solo toca tests/, ejecutar la suite completa sobre el candidato y después:
python scripts/self_development_cycle.py --project-id $P submit --work-id <id>
python scripts/self_development_cycle.py --project-id $P review --work-id <id> --decision APPROVE|REJECT --evidence <sha256:…>
# si se aprueba:
AAO_PUBLISH_BASE_REPO=autoaiorg/aao python scripts/publish_candidate.py --work-id <id> --step push --github gh
AAO_PUBLISH_BASE_REPO=autoaiorg/aao python scripts/publish_candidate.py --work-id <id> --step open --github gh
# CEO fusiona con CI en verde, y después:
AAO_PUBLISH_BASE_REPO=autoaiorg/aao python scripts/publish_candidate.py --work-id <id> --step reconcile --github gh
python scripts/self_development_cycle.py --project-id $P verify --work-id <id>   # cadena completa desde PostgreSQL
```

**Agente y modelo:** desde I3 los decide la capacidad elegida con `--agent`, no el entorno. `aao.agent-runner.codex` lleva en su `model_profile` el backend `codex`, el proveedor `openai` y el modelo `gpt-6-luna`; codex lo recibe como `-m`. La evidencia registra `capability_id`, `backend_source: capability`, proveedor, modelo y la versión real del CLI. Registrar la capacidad no activa nada: sin `AAO_AGENT_PROVIDER=codex` en el worker, el runner rechaza el backend. Las capacidades sin `model_profile` conservan el comportamiento anterior (`AAO_AGENT_BACKEND` y `AAO_AGENT_CODEX_MODEL`) y la evidencia lo indica como `backend_source: environment`.

**Activación y router (I4):** `AAO_AGENT_PROVIDER` admite una lista separada por comas (`codex`, …) y lo comprueban tres puntos por separado:
- el router (`POST /v1/work/{id}/route-model`), que solo recomienda y deja el evento `model.routed` con `execution_authorized: false`;
- el staging (`stage-agent-run`), que rechaza con 409 una capacidad cuyo backend no esté activado, aunque el router la haya recomendado;
- el runner.

**Presupuesto (I5):**
- Cada capacidad puede declarar en su `model_profile` un coste estimado por intento: `cost_per_attempt_usd`.
- Si el CEO fija `AAO_AGENT_DAILY_BUDGET_USD` en el proceso de la API, el router descarta los candidatos cuya estimación supere lo que queda del día. Ese saldo se calcula sumando los `execution.staged` del proyecto.
- El staging rechaza con 409 (`budget.exceed`, acción reservada al CEO) el intento que no quepa. Nunca baja de modelo en silencio.
- Si la variable no está fijada, no hay límite, pero la estimación se registra igualmente en el staging y en el resultado.
- El coste real (tokens) **no se mide**: `codex exec --json` podría darlo, pero su formato no está verificado sin una ejecución autorizada.

Para encolar una tarea con `--agent codex`, la variable tiene que estar también en el proceso de la API, no solo en el del worker. Sin ella, la API rechaza la tarea, y ese es el estado por defecto fuera de un piloto autorizado.

Si el intento falla o se rechaza, se puede volver a encolar hasta llegar al límite. Al alcanzarlo, la API lo rechaza y decide el CEO. También rechaza con 409 («No progress») un intento nuevo cuando los dos últimos acabaron igual: mismo parche y mismo resultado o fallo. En ese caso decide el PM, que puede reformular la tarea como una nueva o pedir una resolución del CEO.

## Verificación final

- **PostgreSQL:** `verify` muestra la tarea, cada ejecución (backend `codex`, candidato y check), las propuestas, las revisiones con su evidencia almacenada (digest y emisor), la PR y su estado, y el estado final. Además comprueba la consistencia: cada aprobación tiene una ejecución SUCCEEDED de ese SHA, y DONE va acompañado de `work.completed` con el SHA aprobado.
- **Control Center:** en el panel de la tarea aparecen los intentos, las revisiones, las PR con su estado (abierta, cerrada sin fusionar o fusionada con su merge commit) y la resolución, si la hay. La pestaña *Actividad* muestra la cronología.

## Qué es automático y qué es humano (registro obligatorio del piloto)

| Paso | Automático | Humano o asistido |
|---|---|---|
| Comprobar el aislamiento (sonda) | ✓ | la lanza el operador |
| Emitir credenciales y grants | — | CEO (`setup`) |
| Crear, seleccionar capacidad, admitir y encolar la tarea | — | operador con la identidad del implementador |
| Reclamar, clonar, **escribir el parche (codex)**, commit candidato y tests en sandbox | ✓ | lanzar el worker |
| Proponer y registrar la evidencia del check | ✓ (worker) / `submit` | `submit` lo lanza el operador |
| Revisar y decidir | — | auditor (Claude), con lectura del diff y suite completa |
| Push y PR | ✓ (script) | lo lanza el publicador; la PR sale con la cuenta del operador |
| CI | ✓ | — |
| Fusionar | — | CEO |
| Reconciliar a DONE | ✓ (script) | lo lanza el operador |

El registro del piloto se guardará en `construction-runs/` con este mismo formato, con los ID y los SHA sacados de `verify`.

## Desactivación

Basta con no exportar `AAO_AGENT_PROVIDER`. Para retirar el acceso del modelo: `rm -rf ~/.local/share/aao/codex-agent`. Las credenciales de AAO se pueden revocar con `POST /v1/principals/{id}/revoke` y caducan a las 8 h en cualquier caso.
