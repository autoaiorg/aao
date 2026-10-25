# Prueba E2E acotada: activación del proveedor `codex` para el agente ejecutor

**Estado:** preparada. **No ejecutada.** Requiere la activación expresa del CEO, porque el mandato `CEO-MANDATE-AAO-SELF-DEV-20261019` reserva la activación de modelos y proveedores.
**Por defecto:** el proveedor está desactivado. Sin `AAO_AGENT_PROVIDER=codex`, `agent_runner` rechaza el backend `codex`. Sin un `AAO_AGENT_CODEX_HOME` dedicado, también lo rechaza.

## Qué se prueba

Una tarea real del proyecto «AAO — Self Development» recorre el mismo ciclo ya demostrado con el backend `fixture` (ver `docs/construction-runs/20261025-self-development-cycle.md`). La diferencia es que el parche lo escribe el modelo:

`tarea → codex en un clon desechable → propuesta → commit candidato → core-unit en bwrap → revisión del auditor → PR → CI → fusión del CEO → DONE`

## Alcance autorizado

| Aspecto | Límite |
|---|---|
| **Identidad en AAO** | Un principal AGENT nuevo, `aao-implementer-<fecha>`. Lo emite el CEO con `scripts/self_development_cycle.py setup`. El auditor (AUDITOR) y el publicador (AGENT con `code.publish`) son principales distintos. |
| **Permisos (grants, 8 h)** | Implementador: `project.read`, `work.create`, `work.admit`, `work.progress`, `execution.claim`, `code.propose`, `evidence.submit`. Auditor: `work.review`. Publicador: `project.read`, `code.publish`. Ningún otro. |
| **Credencial del modelo** | Un `CODEX_HOME` dedicado, `~/.local/share/aao/codex-agent`, con modo 0700 y sesión iniciada **solo** para esta prueba con `CODEX_HOME=… codex login --device-auth`. No se usa `~/.codex`. El runner pasa `--ignore-user-config`, así que no carga plugins, MCP ni configuración del operador. |
| **Sandbox del modelo** | `codex exec --sandbox workspace-write --ephemeral`, con plugins, navegador, *computer use* y memorias desactivados. Escribe solo en el clon desechable (`/tmp/aao-agent-run-*`), con `HOME` temporal y sin acceso de red para los comandos que ejecuta. El checkout de origen no se toca. |
| **Sandbox de los tests** | bwrap: sin red, fuente de solo lectura, sin `HOME` ni secretos, 1 GiB de memoria, 90 s de CPU y 120 s en total. |
| **Recursos** | Una sola tarea y una sola ejecución a la vez. El lease es de 1800 s, de los cuales 1650 s son para el modelo y 150 s para commit y tests. Como máximo 2 reintentos. El coste es el consumo del plan de Codex del CEO para esas ejecuciones. |
| **Repositorio objetivo** | `autoaiorg/aao`, rama `main` como base. El candidato solo puede tocar `src/` y `tests/`: es la política de `patch_proposals`, y `docs/`, `.github/`, `db/` y `deploy/` quedan fuera. |
| **Efectos permitidos** | Escribir en el clon desechable. Escribir en el almacén de candidatos local (`refs/aao/candidates/<sha>`). Filas en la base de datos de desarrollo. Una rama `aao/work-<id>-<sha12>` y una PR en `autoaiorg/aao`, publicadas con `--github gh` (cuenta del operador, régimen de construcción) o, tras D2, con las Apps. |
| **Efectos prohibidos** | Fusionar (lo hace el CEO), escribir en `main`, desplegar, red desde los comandos del modelo, credenciales del operador dentro del clon, Docker y root. |

## Procedimiento (una vez autorizado)

```sh
# 0. Base de datos y API de desarrollo en marcha (compose.dev.yaml, migraciones 001–014, uvicorn en :8001).
# 1. Credencial del modelo, dedicada (el CEO inicia la sesión):
install -d -m 0700 ~/.local/share/aao/codex-agent
CODEX_HOME=~/.local/share/aao/codex-agent codex login --device-auth
# 2. Identidades y tarea:
P=9d17d6c1-d644-424a-a425-fe7e084c3d91
PYTHONPATH=src python scripts/self_development_cycle.py --project-id $P setup
PYTHONPATH=src python scripts/self_development_cycle.py --project-id $P task --title "…" \
  --description "…" --criterion "…" --base-sha "$(git rev-parse origin/main)"
# 3. Ejecución con el modelo (activación expresa solo para este proceso):
AAO_AGENT_PROVIDER=codex AAO_AGENT_BACKEND=codex AAO_AGENT_CODEX_HOME=~/.local/share/aao/codex-agent \
  PYTHONPATH=src python scripts/run_self_development_worker.py --project-id $P --principal-id <implementador>
# 4. Revisión: el auditor ejecuta la suite completa sobre el candidato y después:
PYTHONPATH=src python scripts/self_development_cycle.py --project-id $P submit --work-id <id>
PYTHONPATH=src python scripts/self_development_cycle.py --project-id $P review --work-id <id> --decision APPROVE --evidence <sha256:…>
# 5. Publicación y resultado:
AAO_PUBLISH_BASE_REPO=autoaiorg/aao PYTHONPATH=src python scripts/publish_candidate.py --work-id <id> --step push --github gh
AAO_PUBLISH_BASE_REPO=autoaiorg/aao PYTHONPATH=src python scripts/publish_candidate.py --work-id <id> --step open --github gh
# (el CEO fusiona si la CI está en verde)
AAO_PUBLISH_BASE_REPO=autoaiorg/aao PYTHONPATH=src python scripts/publish_candidate.py --work-id <id> --step reconcile --github gh
```

## Criterios de éxito

1. La ejecución termina en SUCCEEDED con `backend: codex`, y el diff no está vacío y respeta los límites de rutas.
2. `core-unit` en bwrap da `success`, y la suite completa del candidato pasa, ejecutada por el auditor.
3. La PR tiene como cabeza el SHA aprobado y la CI en verde.
4. Tras la fusión, la tarea está en DONE con `work.completed` y el `merge_commit_sha`, y se ve en el Control Center (tablero, panel de la tarea y pestaña *Actividad*).
5. El checkout de origen y `~/.codex` quedan intactos.

## Desactivación

Basta con no exportar `AAO_AGENT_PROVIDER`. Para revocar el acceso del modelo, `rm -rf ~/.local/share/aao/codex-agent`. Las credenciales de AAO caducan a las 8 h y se pueden revocar antes con `POST /v1/principals/{id}/revoke`.
