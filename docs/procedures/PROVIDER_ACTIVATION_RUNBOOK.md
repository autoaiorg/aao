# Runbook: activación de proveedores de modelos (conversación y agente Codex)

**Estado: preparado, NADA activado.** Este documento y sus artefactos
(`deploy/env/aao-provider.env.example`, `scripts/check_provider_activation.py`,
`tests/test_provider_activation.py`) no configuran, inician ni llaman a ningún
proveedor. Activar un proveedor es una decisión **reservada al CEO**; la clave la
coloca **solo el CEO**, directamente en el host, nunca en chat, tickets ni PR.

Revisión del código de referencia al actualizar este runbook: `origin/main`
47a3a36 (incluye el endurecimiento de proveedor de #363). Antes de ejecutar,
confirma que la unidad y el procedimiento del worker Codex estén instalados en
la revisión vigente; este documento no los activa.

## 0. Quién hace qué

| Paso | Requiere sudo | Requiere CEO |
|---|---|---|
| Revisar precondiciones (sección 1), ejecutar el verificador | no | no |
| Crear/editar `/etc/aao/*.env` (root) | **sí** | no (pero el valor de la clave lo teclea el CEO) |
| Escribir `AAO_CONVERSATION_API_KEY` en el fichero | **sí** (el fichero es root 0600) | **sí, solo el CEO** |
| `codex login --device-auth` con `CODEX_HOME` dedicado | **sí** si hay que cambiar a la cuenta `aao-impl-codex` (`sudo -u`); no si ya se opera como ella | **sí, solo el CEO** (sesión OpenAI) |
| `systemctl restart aao-api` / iniciar el worker Codex | **sí** (sistema) / no (unidad `--user` del propio rol) | autorización expresa del CEO |
| Fijar `AAO_AGENT_DAILY_BUDGET_USD` positivo y finito en API y worker | **sí** | decide el CEO |
| Rollback (quitar variable + reiniciar) | **sí** | puede hacerlo cualquier operador autorizado |

Ningún agente debe leer `.env.local` ni los ficheros de `/etc/aao/` con claves.

## 1. Lista de precondiciones (marcar todas antes de activar)

1. **Autorización expresa del CEO** para el proveedor concreto, por escrito y
   registrada (referencia en el registro de evidencia, sección 5).
2. **Mandato y grants**: mandato vigente (p. ej. `docs/CEO_MANDATE_AAO_SELF_DEVELOPMENT_20261019.md`)
   y, para Codex, identidades de ciclo emitidas por el CEO (`self_development_cycle.py setup`):
   implementador con `project.read, work.create, work.admit, work.progress, execution.claim,
   code.propose, evidence.submit`; auditor con `work.review`, **separado**; publicador con
   `code.publish`. La API vuelve a comprobar grants en staging y claim.
3. **Presupuesto (bloqueante)**: para Codex, `AAO_AGENT_DAILY_BUDGET_USD` debe ser
   un número positivo y finito en los procesos de la **API** y del **worker**. El código
   rechaza staging y ejecución de Codex si falta o no es válido; el verificador usa el mismo
   parser de producción. `AAO_AGENT_MAX_ATTEMPTS` (3 por defecto) lo aplica la API. Para
   conversación no existe presupuesto ni tope en AAO: antes de activar, el CEO debe configurar
   y confirmar un límite de gasto en la consola del proveedor para esa clave. Es una
   precondición manual bloqueante; el verificador no puede inspeccionarla.
4. **CODEX_HOME aislado** (solo Codex): directorio dedicado, 0700, propiedad de
   `aao-impl-codex`, p. ej. `/home/aao-impl-codex/.local/share/aao/codex-agent`; nunca el
   `~/.codex` de un operador. `agent_runner` rechaza el backend si falta o no es directorio.
5. **Aislamiento probado**: `python scripts/codex_isolation_probe.py` imprime `"ok": true`
   en el host (el jail bwrap y `network_access=false` para los comandos del modelo).
   Detalle: `docs/CODEX_PROVIDER_ACTIVATION_E2E.md`.
6. **Política de egreso de red**: el proceso de la API (conversación) y el CLI de codex
   necesitan HTTPS saliente solo hacia el host del proveedor; los comandos del modelo no
   tienen red (jail). Las unidades permiten `AF_INET/AF_INET6` pero **el repositorio no
   define una lista de destinos permitidos**: aplicarla en el firewall del host (permitir
   solo el host del proveedor, puerto 443) es precondición operativa y **no está verificada
   aquí**.
7. **Endpoint**: debe ser `https://`, sin userinfo. Solo se permite `http://` para
   `127.0.0.1`, `::1` o `localhost` en pruebas locales. El código rechaza otros esquemas,
   hosts/puertos malformados y redirecciones.
8. Backup/rollback listo (sección 4) y verificador ejecutado en estado OFF (sección 3.1).

## 2. Activación

Ficheros y lectores (valores en `deploy/env/aao-provider.env.example`, todos vacíos):

| Variable | Fichero | Lo lee | Modo/propietario |
|---|---|---|---|
| `AAO_CONVERSATION_PROVIDER`, `_API_URL`, `_MODEL`, `_API_KEY` | `/etc/aao/aao-api.env` | `aao-api.service` (`EnvironmentFile`) | 0600 root (systemd lee como root) |
| ídem + `AAO_CONVERSATION_RECOVERY_ENABLED=true` | `/etc/aao/aao-recovery.env` | `aao-conversation-recovery.service` (usuario `aao-recovery`) | 0600 root; solo si se activa la recuperación |
| `AAO_AGENT_PROVIDER=codex`, `AAO_AGENT_DAILY_BUDGET_USD`, `AAO_AGENT_MAX_ATTEMPTS` | `/etc/aao/aao-api.env` | `aao-api.service` (puerta de staging y router) | 0600 root |
| `AAO_AGENT_PROVIDER=codex`, `AAO_AGENT_CODEX_HOME`, `AAO_AGENT_DAILY_BUDGET_USD` | `/etc/aao/selfdev-codex-worker.env` | worker Codex | 0644 root, legible por `aao-impl-codex`; **sin secretos** |

En producción no se cargan ficheros dotenv (`environment_settings.py`); solo valen
las unidades systemd. La clave nunca va en la línea de comandos ni en `Environment=`.

### A. Proveedor de conversación (OpenAI-compatible)

1. (sudo) Editar `/etc/aao/aao-api.env` con un editor que no deje copias
   (`sudoedit`), modo 0600 root:
   ```
   AAO_CONVERSATION_PROVIDER=openai-compatible
   AAO_CONVERSATION_API_URL=https://<host>/v1/chat/completions
   AAO_CONVERSATION_MODEL=<modelo>
   AAO_CONVERSATION_API_KEY=<la teclea el CEO>
   ```
   El valor de `PROVIDER` debe ser exactamente `openai-compatible`; cualquier otro
   (`dummy`, `gemini`, ...) deja el proveedor apagado. Si falta cualquiera de las
   cuatro, `stream_reply` lanza `PROVIDER_NOT_CONFIGURED` sin hacer ninguna llamada.
2. (sudo) `systemctl restart aao-api`.
3. Verificar (sección 3.2). La primera llamada real, por parte del CEO o autorizada
   por él, es un turno de conversación desde el Control Center.
4. Solo si se quiere recuperación de turnos: repetir las cuatro variables y
   `AAO_CONVERSATION_RECOVERY_ENABLED=true` en `/etc/aao/aao-recovery.env`.

### B. Backend de agente Codex

1. (CEO) Sesión dedicada, sin pasar la clave por chat:
   `install -d -m 0700 <CODEX_HOME>` y
   `CODEX_HOME=<CODEX_HOME> codex login --device-auth` como `aao-impl-codex`
   (cambiar de cuenta requiere sudo). La credencial queda en `<CODEX_HOME>/auth.json`.
2. (sudo) En `/etc/aao/aao-api.env`: `AAO_AGENT_PROVIDER=codex` y
   `AAO_AGENT_DAILY_BUDGET_USD=<n>`; `systemctl restart aao-api`. Sin esto la API
   rechaza con 409 el staging de capacidades Codex (`Agent backend codex is not
   activated; CEO provider activation required`).
3. (sudo) Crear `/etc/aao/selfdev-codex-worker.env` (0644 root) con
   `AAO_AGENT_PROVIDER=codex`, `AAO_AGENT_CODEX_HOME=<CODEX_HOME>` y el mismo
   `AAO_AGENT_DAILY_BUDGET_USD` positivo y finito; instalar la unidad según
   `docs/procedures/SELFDEV_CODEX_WORKER_RUNTIME.md` e iniciarla
   solo para un ensayo acotado autorizado por el CEO. La unidad falla cerrada si falta
   ese fichero o el token del rol.
4. Verificar (sección 3.2). El modelo y el backend los decide la capacidad elegida
   con `--agent`, no el entorno (`aao.agent-runner.codex`, modelo `gpt-6-luna`).

## 3. Verificación

`scripts/check_provider_activation.py` es solo lectura, sin red, e imprime
únicamente booleanos (nunca valores). Debe ejecutarse con las variables del
servicio inspeccionado exportadas en el mismo shell. Reutiliza por importación
la puerta real (`conversation_provider.stream_reply`, con `urlopen` sustituido
para que no pueda enviarse nada, `agent_runner.activated_backends` y el parser
`agent_runner.daily_budget_usd`).

### 3.1 Verificar que está OFF (antes de activar y tras el rollback)

```sh
python scripts/check_provider_activation.py --expect off   # exit 0 y todos los *_active/*_would_run en false
```
Comprobar además que `systemctl show aao-api -p Environment` y
`systemd-analyze cat-config` **no** listan variables `AAO_CONVERSATION_*` con valor
(no imprimir el fichero con la clave).

### 3.2 Verificar que está ON

```sh
python scripts/check_provider_activation.py --expect on --conversation-spend-limit-confirmed  # exit 0
```
El flag `--conversation-spend-limit-confirmed` es una atestación explícita del
operador de que el tope existe en la consola; no es verificación técnica.
Esperado: `conversation_provider_active: true`,
`conversation_spend_limit_required: true`,
`conversation_spend_limit_confirmed_by_operator: true`,
`codex_backend_would_run: true`, `codex_budget_is_valid: true` y
`agent_budget_limit_set: true`. Sin el flag manual, `--expect on` falla.
Limitación: demuestra que la puerta deja pasar, **no** que el proveedor responda
ni que la clave sea válida; eso solo lo demuestra la primera llamada real.

## 4. Rollback

1. (sudo) Quitar la variable (basta vaciar `AAO_CONVERSATION_PROVIDER` o quitar
   `codex` de `AAO_AGENT_PROVIDER`; para retirar la clave, borrar su línea) en
   `/etc/aao/aao-api.env` (y `aao-recovery.env`, `selfdev-codex-worker.env` si aplica).
2. (sudo) `systemctl restart aao-api`; parar el worker Codex y
   `systemctl restart aao-conversation-recovery` si se usó.
3. Retirar el acceso del modelo: `rm -rf <CODEX_HOME>`; revocar identidades con
   `POST /v1/principals/{id}/revoke` (caducan a las 8 h en cualquier caso).
4. Rotar/revocar la clave en la consola del proveedor si pudo exponerse.
5. Verificar con 3.1.

## 5. Evidencia a capturar

Sin secretos. Guardar en `docs/construction-runs/` (o el registro que el PM indique):
- referencia de la autorización del CEO y fecha;
- revisión exacta (SHA) del código desplegado y de la unidad (#356);
- salida **completa** de `check_provider_activation.py` antes (OFF) y después (ON);
- salida de `codex_isolation_probe.py` (`"ok": true`);
- modo/propietario de los ficheros (`stat -c '%a %U:%G %n'`), nunca su contenido;
- `systemctl is-active` y hora del restart; evidencia de la primera llamada (id de
  turno/ejecución, `model.routed`, `execution.staged` con `cost_estimate_usd`);
- el valor de presupuesto y de `AAO_AGENT_MAX_ATTEMPTS` vigentes (sin capturar
  secretos), y confirmación de que la consola del proveedor tiene límite de gasto
  para la clave de conversación;
- para Codex: `verify` de `self_development_cycle.py` (cadena desde PostgreSQL);
- limitaciones: el coste real en tokens no se mide; el egreso no verificado en repo.

## 6. Límites y condiciones restantes

1. **Endurecimiento aplicado en #363**: el endpoint requiere HTTPS (salvo loopback local),
   rechaza userinfo y redirecciones, y falla cerrado para esquemas, hosts o puertos no válidos.
2. **Configuración de ejemplo corregida en #363**: solo `openai-compatible` activa el proveedor.
3. `AAO_AGENT_DAILY_BUDGET_USD` debe ser positivo y finito; la API y el runner Codex lo
   rechazan si falta o no es válido. El worker también debe recibirlo.
4. La conversación no tiene presupuesto ni límite en AAO; depende del tope en el proveedor,
   que sigue siendo una confirmación manual del CEO.
5. Las variables `AAO_CONVERSATION_*` deben duplicarse en el entorno del worker de
   recuperación si este se activa; `AAO_AGENT_PROVIDER` debe estar en API **y** worker.
6. El verificador importa `agent_runner.daily_budget_usd()` y replica la comprobación de
   `AAO_AGENT_CODEX_HOME` como directorio existente. Sin activación de Codex no se exige presupuesto.
