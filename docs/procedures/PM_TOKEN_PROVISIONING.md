# Provisión del token AAO del coordinador PM (`aao-pm.token`)

**Estado:** diseño + emisor implementado (bloqueo B2). Autorizado como *diseño* por el CEO a PM/COO; la implementación del emisor fue autorizada por el CEO; nada de esto es autorización para ejecutar. **Nada de este documento se ha ejecutado contra el host, la API, PostgreSQL ni las cuentas Linux.** Código añadido: la opción `--token pm` del instalador existente y el emisor `scripts/provision_pm_coordinator_token.py`, ambos solo con tests unitarios locales (API y `sudo` simulados). El emisor es código que emite credenciales: requiere auditoría independiente (GOV-REV-001) antes de fusionarse o usarse.

## Problema

`scripts/pm_deployment_preflight.py` comprueba `pm:token` y `scripts/run_project_coordinator.py` lee `aao-pm.token`, pero no existe un procedimiento para emitirlo e instalarlo. Los análogos (`provision_w2_publishers.py`, `install_publisher_token_for_role.py`) solo cubren `aao-publisher.token` con grants `project.read` + `code.publish`, que no sirven al coordinador.

## Dónde vive y con qué metadatos

| Aspecto | Valor exigido | Fuente |
|---|---|---|
| Ruta | `/run/user/<uid de aao-pm>/aao-pm.token` (el preflight espera uid `1001`) | `pm_deployment_preflight.py` `pm:token`; `run_project_coordinator.PM_TOKEN_NAME` |
| Fichero | regular, propietario `aao-pm`, modo `0600`, no symlink | `path_check(..., 0o600)`; `_read_agent_token` |
| Directorio | `/run/user/<uid>` propiedad de `aao-pm`, modo `0700` | `runtime:aao-pm`; `target_path` del instalador |
| Ancestros | sin symlinks, propiedad de root o `aao-pm`, sin escritura de grupo/otros | `path_check` |
| Contenido | token + un único `\n`; sin CR ni espacios; ≤ 4096 bytes | `_read_agent_token`; el instalador escribe `token + "\n"` |

`/run/user` es tmpfs: el token **desaparece al reiniciar** y al cerrar la última sesión si no hay *linger* (`PROJECT_COORDINATOR_SERVICE.md` ya incluye `loginctl enable-linger aao-pm`). Tras un reinicio la secuencia es rotar e instalar de nuevo (ver «Rotación»). No se persiste en disco para evitarlo.

## Principal y grants (mínimo privilegio)

- **Principal propio**, `kind=AGENT`, p. ej. `aao-pm-coordinator-<YYYYmmddHHMMSS>-<nonce>`. Debe ser distinto del principal W2 `aao-publisher-pm-*`: en el mismo directorio runtime convivirán dos tokens distintos. **Nunca copiar `aao-publisher.token` a `aao-pm.token`** ni conceder `code.publish` al coordinador.
- **Grants requeridos** sobre el proyecto (`REQUIRED_GRANTS` del preflight): `project.read`, `work.coordinate`, `work.assign`.
- **Solo si el CEO aprueba aparte `--materialize-routines`:** `work.create`.
- **Excluidos:** `code.publish`, `code.propose`, `work.admit`, `work.progress`, `work.review`, `execution.*`, `effect.*`, `evidence.submit`.
- **Caducidad: decisión del CEO, sin valor por defecto.**
  - Con caducidad (W2 usa 8 h): al vencer, el servicio `--watch` pierde autoridad y falla; es el comportamiento buscado, pero exige renovar.
  - Sin caducidad (`expires_at` nulo): sin corte automático; la retirada depende de revocar el principal.
  - `POST /v1/projects/{id}/grants` es `ON CONFLICT DO NOTHING`: volver a conceder **no amplía** una caducidad existente.

## Garantías de la instalación

Se reutiliza `scripts/install_publisher_token_for_role.py` con `--account aao-pm --token pm` (la opción `pm` solo se acepta para `aao-pm`; el valor por defecto `publisher` no cambia y W2 sigue igual):

- **Entrada por stdin**, nunca argumentos ni variables de entorno; el token no se imprime.
- Debe ejecutarse **como `aao-pm`** con `XDG_RUNTIME_DIR=/run/user/<uid>`; comprueba directorio `0700` propio.
- **No sobrescribe:** `O_CREAT|O_EXCL|O_NOFOLLOW`; si existe (o es symlink) falla. `--check` lo comprueba antes de emitir nada.
- `--verify` exige fichero regular propio, `0600` y contenido idéntico al token de stdin.
- `--remove` solo borra si el contenido coincide con el token de stdin.
- En la API, emitir un `principal_id` ya registrado devuelve 409 («use rotation»): tampoco hay sobrescritura en esa capa.

## Emisor: `scripts/provision_pm_coordinator_token.py`

`bootstrap_self_dev_agent.py` tiene grants fijos de worker y escribe en el runtime del invocante; `provision_w2_publishers.py` fija `code.publish`. Por eso existe un emisor propio. **No se debe sustituir por `curl`**: pondría el token CEO o el del PM en argv, entorno, historial o terminal.

El emisor reutiliza los helpers de `provision_w2_publishers.py` (`local_api_url`, `issue_agent_credential`, `grant_exactly`, `cleanup`, `_run_role_helper` con `token_kind="pm"`). Concede exactamente `project.read`, `work.coordinate`, `work.assign`; **no** concede `work.create` (no tiene opción para ello). La caducidad es obligatoria y explícita: `--expires-at <ISO-8601 con zona, futura>` o `--no-expiry`; sin una de las dos, el emisor no pide el token CEO ni hace nada. Al extraer los helpers se corrigió además un defecto latente de W2: `_run_role_helper` pasaba `--install`, que el instalador no acepta (instala por defecto).

Especificación implementada:

1. API solo loopback (`local_api_url`); token CEO por `getpass`, nunca impreso ni guardado.
2. Verificar que el proyecto existe y está `ACTIVE`; que `aao-pm` es una cuenta distinta del invocante.
3. `sudo -u aao-pm … install_publisher_token_for_role.py --account aao-pm --token pm --check`.
4. `POST /v1/principals/credentials` (`kind=AGENT`), validando `principal_id`/`kind` de la respuesta.
5. Conceder exactamente los grants elegidos con la caducidad decidida por el CEO; releer `GET /v1/projects/{id}/grants` y exigir conjunto exacto, `AGENT`, credencial habilitada y caducidad igual a la pedida.
6. Instalar por stdin (`--token pm`) y `--verify`.
7. **Ante cualquier fallo:** `--remove` con el token emitido y `POST /v1/principals/{id}/revoke`. No existe endpoint para borrar grants: las filas quedan, inertes, porque el principal queda deshabilitado (el preflight marcará `db:pm-identity`/`db:pm-grants` como `MISSING`). No afirmar que los grants se eliminan.
8. Imprimir solo `principal_id`, grants y caducidad (no secretos), para `AAO_PM_PRINCIPAL_ID` en el `.env` del servicio.

Tests unitarios con API y `sudo` simulados: `tests/test_provision_pm_coordinator_token.py`. B2 sigue abierto en la parte de emisión hasta que el emisor pase auditoría independiente y el CEO lo ejecute.

## Ejecución por el CEO

Pasos con `sudo` o como otra cuenta: **solo los ejecuta el CEO**, con decisión expresa; ningún agente los ejecuta.

```bash
AAO_ROOT='<checkout AAO fijado y legible por aao-pm>'
PYTHON='<python del entorno AAO accesible por aao-pm>'
PM_UID="$(id -u aao-pm)"          # el preflight espera 1001

# 1 (sudo, CEO). Sesión/linger de aao-pm para que exista /run/user/$PM_UID.
sudo loginctl enable-linger aao-pm

# 2 (sudo, CEO). Destino vacío y seguro, sin emitir nada.
sudo -u aao-pm -H env XDG_RUNTIME_DIR="/run/user/$PM_UID" \
  "$PYTHON" "$AAO_ROOT/scripts/install_publisher_token_for_role.py" \
  --account aao-pm --token pm --check

# 3 (CEO; usa sudo internamente). Emitir, conceder, instalar y verificar.
#   Caducidad: decisión del CEO, obligatoria. Elegir UNA de las dos formas:
"$PYTHON" "$AAO_ROOT/scripts/provision_pm_coordinator_token.py" \
  --project-id '<UUID del proyecto>' --python "$PYTHON" \
  --expires-at '<YYYY-MM-DDTHH:MM:SS+00:00>'              # pide el token CEO sin eco
# o, sin caducidad:  ... --project-id '<UUID>' --python "$PYTHON" --no-expiry
```

Si se interrumpe a mano tras instalar: `--remove` (con el token por stdin, desde el propio proceso emisor, nunca tecleado en una línea de comandos) y revocar el principal.

## Verificación

1. Metadatos sin leer el secreto (sudo, CEO):

   ```bash
   sudo stat -c '%U %a %F %n' "/run/user/$PM_UID" "/run/user/$PM_UID/aao-pm.token"
   # esperado: aao-pm 700 directory … / aao-pm 600 regular file …
   ```

2. Preflight de solo lectura. Ejecutado como el usuario CEO, `pm:token` saldrá `UNVERIFIED` (no puede hacer `lstat` dentro de `/run/user/1001`); eso **no** es PASS. Para obtener PASS en `pm:token`, ejecutarlo como `aao-pm` o con sudo, y con el principal para los checks de base de datos:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/pm_deployment_preflight.py \
     --principal-id '<principal emitido>' --runtime-role '<rol runtime>'
   ```

   Esperado: `pm:token`, `db:pm-identity` y `db:pm-grants` en `PASS`. El preflight no lee el token ni prueba que autentique.
3. La identidad efectiva se comprueba en la primera pasada del coordinador (`/v1/principals/me` debe coincidir con `--principal-id`), según `PROJECT_COORDINATOR_OPERATIONS.md`.

## Rotación y revocación

- **Rotación** (p. ej. tras reinicio): `POST /v1/principals/{id}/rotate` invalida el token anterior; después instalar el nuevo con `--token pm` (el fichero antiguo, si sigue, debe retirarse antes con `--remove` y el token antiguo). No está automatizada; es seguimiento del emisor.
- **Revocación:** detener el servicio primero (`systemctl --user disable --now …`), después `POST /v1/principals/{id}/revoke` y `--remove`. Revocar no borra grants (quedan inertes).

## Qué NO se hace

- No se ejecutó nada contra el host, la API, la base de datos ni cuentas Linux; no se usó `sudo` ni ningún token.
- No se emite credencial ni se conceden grants: el emisor existe pero no se ha ejecutado; solo tiene tests unitarios con fakes.
- No se instala ni habilita el servicio, ni se crea el `.env` del coordinador.
- No se toca trust root, integrador, activación de proveedores ni governance-guard.
- No se habilita `--auto-consolidate` ni `--materialize-routines`; `work.create` solo con aprobación aparte.
- Tests y CI no constituyen auditoría independiente (GOV-REV-001).
