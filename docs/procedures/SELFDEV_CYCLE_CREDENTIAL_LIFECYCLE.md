# Ciclo de vida desatendido de credenciales de ciclo Self Development (diseño)

Estado: **orquestador de renovación implementado en código (rama
`feat/selfdev-cycle-renew-runner`); no desplegado, no habilitado y no verificado
en el host. No hay operación desatendida en producción.**
Revisión base: `478781e` (origin/main, 2026-11-03), tras #377 y #379.
Actualiza el diseño
publicado en el PR #357 y la implementación de ciclo fusionada. Este documento
no emite, concede ni amplía credenciales. Toca la
emisión de credenciales: exige auditoría independiente (GOV-REV-001) antes de
fusionarse y antes de cualquier implementación derivada.

Objetivo: que el PM (`aao-pm`), solo con su token PM, mantenga al worker
`aao-impl-codex` con una credencial de ciclo válida, sin token CEO y sin
intervención humana. Hay dos condiciones simultáneas:

- (a) el worker nunca debe quedar con una credencial caducada mientras haya
  trabajo;
- (b) nunca debe haber dos ciclos válidos más allá de un solape acotado.

## 1. Conclusión

La API actual resuelve la emisión y revocación de varios bloqueos de ciclo
(PR #377, migración 041): vincula al host el implementador nuevo, hereda un
perfil organizativo elegible y, al revocar, retira el vínculo, deshabilita el
perfil y escala el trabajo sin ejecución activa. El DELETE de un ciclo nunca
emitido devuelve 404. Esto **no demuestra que exista renovación automática
operativa en el host**.

Bloqueos restantes principales:

1. **El orquestador de renovación existe en código, pero no está instalado.**
   `scripts/renew_selfdev_cycle_credentials.py` y las unidades
   `deploy/systemd/user/aao-selfdev-cycle-renew.{service,timer}` implementan
   §3–§6 y están probados solo con dobles (fakes). No se ha ejecutado contra la
   API real, el helper root ni el host; nada se ha habilitado.
2. **El worker no está desplegado.** En las comprobaciones aportadas por el
   operador el 2026-11-03, `aao-selfdev-codex-worker` era `LoadState=not-found`
   y faltaban `/etc/aao/selfdev-codex-worker.env` y
   `/run/user/1002/aao-self-development-agent.token`.
3. **El reemplazo atómico (#361) está implementado en código, pero no verificado
   en el host.** El helper root instalado debe admitir `replace` antes de
   habilitar la renovación.

El orquestador usa solo el token PM, la API acotada de #377 y el wrapper root
de #361 mediante `sudo -n`, con el token en stdin. No usa DSN ni token CEO, y
no modifica componentes root. Su despliegue sí exige pasos de administrador
(§3.1).

**#331 (auto-rotación AGENT) no sirve para renovar el TTL.**
`POST /v1/principals/me/rotate` (`src/aao/work_management_api.py`) y
`…/confirm` (`:1056`) solo sustituyen `token_digest`. No tocan
`principal_credentials.expires_at` ni `project_grants.expires_at`.
`lock_pending_agent_rotation` exige además que la credencial siga vigente
(`src/aao/principal_credentials.py:72-77`), y AUDITOR no puede auto-rotar
(`kind='AGENT'`). Renovar un ciclo significa **emitir el ciclo N+1 con
principals nuevos y revocar el ciclo N**.

## 2. Mapa: qué es posible hoy sin token CEO

Notación: `rw` = `require_worker` (bearer AGENT individual,
`work_management_api.py:112`); `PM-issuer` =
`_require_selfdev_cycle_issuer` (`:899`), que exige el prefijo
`aao-pm-coordinator-`, `work.coordinate` y
`credential.issue_selfdev_cycle_roles` vigentes.

| Paso | ¿Posible hoy sin CEO? | Evidencia |
|---|---|---|
| Leer token PM | Sí | `scripts/request_selfdev_cycle_roles.py:49-69` (`/run/user/<uid>/aao-pm.token`, 0600) |
| Emitir par de ciclo N+1 (TTL ≤ 2 h) | Sí, si el grant emisor sigue vigente | `POST /v1/projects/{id}/selfdev-cycle-roles` (`:907`), `rw` + PM-issuer; TTL `SELFDEV_CYCLE_TTL` (`:885`) |
| Idempotencia ante respuesta perdida | Sí (fail-closed) | Repetir el POST con el mismo `cycle_id` devuelve 409 (`:938-939`) y no reemite; recuperar con DELETE del mismo ID |
| Revocar ciclo N | Sí, idempotente | DELETE requiere `rw` + PM-issuer y migración 041 para retirar el binding; `already_revoked` verifica/repara limpieza; un ciclo nunca emitido devuelve 404 `CYCLE_NOT_FOUND`. |
| Verificar identidad del implementador | Sí | `GET /v1/principals/me` (`:861`, `rw`) con el token nuevo |
| Verificar identidad del revisor | Parcial | No existe `/v1/auditors/me`; `GET /v1/auditors/me/grants` (`:1219`, `require_reviewer`) devuelve principal y grants |
| Observar el drenaje del worker antiguo | Sí | `GET /v1/projects/{id}/board` (`:3771`, `read_principal` + `project.read`, que el PM tiene) expone `executions[].worker_id/status` y `assigned_principal_id` |
| Comprobar / instalar / verificar fichero de rol | Sí, con helper actualizado; `--replace` cubre destinos existentes | `sudo /usr/local/libexec/aao/selfdev_role_token_helper.py` (`scripts/selfdev_role_token_helper.py:18-22`), con el instalador `install` `O_EXCL` (`scripts/install_publisher_token_for_role.py:73-78`) |
| **Reemplazar atómicamente el fichero existente** | Sí en el código de #361; despliegue host no verificado | `install_publisher_token_for_role.py --replace`; helper actualizado para permitir `replace` |
| **Borrar el fichero del ciclo N** | Sí con el helper actualizado; despliegue host no verificado | Operación `remove` del helper; el PM no conserva el token antiguo |
| **Vincular el implementador nuevo al host** | Sí, en código (#377) | La emisión usa `current_host_id()` y `register_host_worker(..., new_worker_only=True)` dentro de la transacción; requiere host activo y sin cercar. |
| Parar o reiniciar el worker de `aao-impl-codex` | No, y el diseño no lo requiere | #356 está fusionado: worker opt-in, identidad comprobada por ejecución y configuración de servicio. La instalación/activación real del servicio sigue sin verificarse aquí. |
| Heredar perfil organizativo elegible | Sí, en código (#377) | Copia el perfil activo más reciente de un implementador previo elegible del mismo proyecto; no inventa competencias ni crea perfil si no hay fuente. |
| Transferir automáticamente las asignaciones al ciclo nuevo | No | La revocación escala el trabajo no reclamado para reasignación; no lo transfiere automáticamente al nuevo principal. |
| Escalar el trabajo asignado al ciclo revocado | Sí, en código (#377), sujeto a migración 041 | DELETE deshabilita credencial, retira binding y escala trabajo no reclamado en la misma transacción. |
| Renovar el grant emisor del PM (30 días) | **No: CEO, por diseño** | `SELFDEV_CYCLE_ISSUER_GRANT_TTL` (`:886`); concesión de grants solo `require_ceo` |
| Autenticación de principals en `AAO_ENV=production` | **No** (fuera de este alcance) | `_development_credentials_enabled` solo admite `development` y `test` (`principal_credentials.py:16-19`) |

Hallazgo adicional: en el repositorio no hay ningún consumidor runtime del
fichero `aao-self-development-reviewer.token` fuera del instalador.
`scripts/self_development_cycle.py:30` usa `aao-auditor.token`. El ciclo de
vida del revisor está, por tanto, definido solo a medias (G5).

## 3. Orquestador de renovación: implementado en código, no desplegado

- Script: `scripts/renew_selfdev_cycle_credentials.py --project-id <uuid>`.
  Cada ejecución es un *tick* de la máquina de estados (§5). El cliente API, el
  instalador y el reloj son inyectables; los tests usan dobles.
- Unidades de usuario de `aao-pm`, que sustituyen al nombre plantilla propuesto
  antes (`aao-selfdev-cycle-credentials@<project>`):
  `deploy/systemd/user/aao-selfdev-cycle-renew.service` (oneshot) y
  `aao-selfdev-cycle-renew.timer` (`OnActiveSec=1min`,
  `OnUnitActiveSec=5min`). El proyecto se lee de
  `~/.config/aao/selfdev-cycle-renew.env` (`AAO_PROJECT_ID=<uuid>`). Usan el
  árbol y el venv congelados de `/srv/aao/frozen/aao-pm`, igual que el
  coordinador. **Este cambio no las instala ni las habilita.**
- La unidad **no** lleva `NoNewPrivileges=yes`, porque necesita `sudo` hacia el
  wrapper root. En modo usuario, systemd implica `NoNewPrivileges` con
  `PrivateDevices`, `ProtectKernel*`, `ProtectControlGroups`,
  `RestrictSUIDSGID`, `LockPersonality`, `RestrictAddressFamilies`,
  `SystemCallFilter` y otras. Las directivas de espacio de nombres
  (`PrivateTmp`, `ProtectSystem`, `ProtectHome`) ejecutan el proceso en un user
  namespace, donde setuid no obtiene root. Por eso se omiten todas. Es la
  diferencia consciente respecto de `aao-project-coordinator@.service`.
  Compensación: el sudoers solo permite el wrapper
  (`SELF_DEVELOPMENT_CYCLE_ROLES.md` §setup 3).
- Lock exclusivo no bloqueante `flock` en
  `/run/user/<uid-pm>/aao-selfdev-cycle.lock`. Un segundo tick concurrente sale
  con código 75 (`SuccessExitStatus=75`) sin leer el token ni actuar.
- Credencial: solo el token PM (`read_pm_token`, con la misma validación que
  `request_selfdev_cycle_roles.py`). Nunca el token CEO, ni `.env.local`, ni un
  DSN. Los tokens de rol viajan solo por el stdin del wrapper (`sudo -n`, con
  entorno mínimo). Nunca aparecen en argv, entorno, stdout/stderr ni estado.
- Verificación de identidad, antes de tocar ficheros:
  - `GET /v1/principals/me` con el token implementador debe devolver
    exactamente
    `{"principal_id": "aao-selfdev-impl-<id>", "kind": "AGENT", "enabled": true}`.
  - `GET /v1/auditors/me/grants` con `X-Auditor-Token` debe devolver
    exactamente una fila `work.review` activa del proyecto para
    `aao-selfdev-review-<id>`.
  - Los grants del implementador se comprueban como conjunto exacto en la
    respuesta del POST, porque no existe un endpoint de grants para AGENT.

### 3.1 Pasos pendientes en el host (administrador/CEO; no realizados)

1. Auditoría independiente GOV-REV-001 de este cambio, de #361 y de #377.
2. Root: reinstalar en `/usr/local/libexec/aao` los ficheros revisados
   `selfdev_role_token_helper.py` e `install_publisher_token_for_role.py`
   (root:root, 0755/0644), para que exista `--operation replace`. Comprobar el
   sudoers de `aao-pm` con `visudo -cf`.
3. Root/operador de despliegue: aplicar la migración 041 y comprobar los grants
   de `aao_runtime`. Congelar en `/srv/aao/frozen/aao-pm` una revisión que
   contenga este script.
4. CEO: confirmar que el grant `credential.issue_selfdev_cycle_roles` del PM
   está vigente (≤ 30 días) y que existe un perfil semilla del implementador.
5. `aao-pm`:
   - Copiar las dos unidades a `~/.config/systemd/user/`.
   - Crear `~/.config/aao/selfdev-cycle-renew.env`.
   - Ejecutar una vez
     `renew_selfdev_cycle_credentials.py --project-id <uuid> --bootstrap`
     (§5).
   - Solo después, y con autorización, ejecutar
     `systemctl --user enable --now aao-selfdev-cycle-renew.timer`.

## 4. Privilegios mínimos

| Sujeto | Necesita | Ya existe |
|---|---|---|
| Principal PM | `project.read`, `work.coordinate`, `credential.issue_selfdev_cycle_roles` (≤ 30 días) en Self Development | Sí (#347/#348/#349; aplicación en host **no verificada** aquí) |
| Linux `aao-pm` | `sudo` NOPASSWD solo sobre `/usr/local/libexec/aao/selfdev_role_token_helper.py` | Diseñado en #347; aplicación en host no verificada |
| Wrapper root | Operación `replace` | Implementada en #361; despliegue en host no verificado |
| API (`aao_runtime`) | Permisos requeridos por #377, incluida la función restringida de la migración 041 | Implementado en la línea de migraciones; despliegue/ejecución en el host no se demuestra aquí |

No se necesita `work.assign` para el ciclo en sí. Solo hace falta si se
resuelve G3 por reasignación.

## 5. Máquina de estados

Estado persistido **sin secretos** en
`/run/user/<uid-pm>/aao-selfdev-cycle-<project>.json`: fichero regular 0600, de
un solo enlace y propiedad de `aao-pm`. La escritura es atómica: temp
`O_EXCL`, `fsync`, `rename` y `fsync` del directorio.

```json
{"phase": "...", "project_id": "<uuid>", "current_cycle_id": "<hex32|null>",
 "current_expires_at": "...", "next_cycle_id": "<hex32|null>",
 "next_expires_at": "...", "next_issued_at": "...", "updated_at": "..."}
```

Diferencia con el diseño previo: el estado vive en el runtime dir y no en
`~/.local/state`, igual que los tokens que describe. Tras un reinicio,
desaparecen ambos.

- Un estado ausente **falla cerrado**: el script exige `--bootstrap`
  explícito, que crea el estado y emite el primer ciclo sin predecesor.
- `--bootstrap` con un estado existente se rechaza.
- Un estado corrupto falla cerrado sin llamadas a la API. Cuenta como corrupto
  si tiene forma inesperada, es de otro proyecto, no tiene modo 0600 o es un
  enlace simbólico.
- Limitación: si quedaba un ciclo vigente no registrado (manual o anterior al
  reinicio), el runner no lo revoca. Caduca en ≤ 2 h y debe revocarse con el
  endpoint de ciclo.

Ningún token se escribe en el estado, en argv, en el entorno, en stdout o en
los logs. Los tokens viven solo en la memoria del proceso entre el POST y el
`replace` (stdin del wrapper).

| Estado | Significado | Transición normal | Fallo |
|---|---|---|---|
| `ACTIVE` | El ciclo N está instalado y verificado, y le queda más del margen | Al cruzar el umbral de renovación (§6): genera `next_cycle_id`, **persiste** y pasa a `ISSUING` | — |
| `ISSUING` | El ID N+1 y `next_issued_at` están persistidos antes del POST | POST correcto → verificación de identidad por API → `replace` del revisor y después del implementador (el fichero con consumidor vivo cambia el último) → `INSTALLED_PENDING`. Si `replace` devuelve el código 3 (renombrado hecho, comprobación posterior fallida), decide el `verify` siguiente | Error, 409, 5xx, timeout, desajuste de identidad o fallo de `replace` → `FAILED_ISSUE` |
| `INSTALLED_PENDING` | Los ficheros contienen N+1; falta verificarlos | `verify` de fichero con el token en memoria → `VERIFIED`. La verificación por API (IDs, kind y grants exactos) ya se hizo en `ISSUING`, antes de instalar, para que un desajuste deje intactos los ficheros de N | → `FAILED_INSTALL` |
| `VERIFIED` | N+1 está verificado; el worker lo recoge en la siguiente iteración | Si el board no muestra ejecuciones `RUNNING`/`UNCERTAIN`/`QUEUED` con `attempts>0` y `worker_id = impl-N`, o si N ya caducó → `REVOKING_OLD` | Plazo de drenaje superado → `REVOKING_OLD` igualmente (§6) |
| `REVOKING_OLD` | Se revoca el ciclo N | DELETE N devuelve `revoked`, `already_revoked` o `CYCLE_NOT_FOUND` → `current := next` y `next := null` → `ACTIVE` | Error → se queda en `REVOKING_OLD` y reintenta en cada tick. Si N ya caducó, avanza con alerta para no bloquear la renovación de N+1 |
| `FAILED_ISSUE` | N+1 puede existir o no en el servidor | DELETE N+1. Con `revoked`, `already_revoked` o 404 con `detail.code == "CYCLE_NOT_FOUND"` → `next := null` → `ACTIVE`, y se vuelve a emitir con un ID **nuevo** (como máximo una emisión por tick) | 409 (conjunto alterado): se alerta y se cierra igualmente, porque N+1, si existe, caduca en ≤ 2 h y sus tokens se perdieron. Otro 404, 5xx o error de red: se mantiene hasta `next_issued_at + 2 h + 1 min` y entonces se cierra con alerta. Mientras se mantiene, nunca se emite otro ciclo |
| `FAILED_INSTALL` | Falló el `verify` posterior a la instalación; un fichero puede contener N+1 | Igual que `FAILED_ISSUE` (DELETE N+1). Si el fichero del implementador ya tenía N+1, el worker falla cerrado (403) hasta la siguiente emisión correcta, que el runner intenta en el siguiente tick | — |
| `FAILED_EXPIRED` | `current_expires_at` ya pasó y no hay ciclo válido instalado | Emite directamente (`ISSUING`) sin drenaje; el worker estaba fallando cerrado | Se mantiene; alerta crítica |

Recuperación tras una caída (en cada tick se lee el estado y se hace la
acción idempotente del estado persistido):

- **Caída antes de persistir `next_cycle_id`:** no se ha emitido nada.
- **Caída en `ISSUING`, tras el POST y antes del `replace`:** los tokens se
  perdieron. Se aplica `FAILED_ISSUE` (DELETE N+1). El ciclo N sigue intacto
  en los ficheros.
- **Caída en `INSTALLED_PENDING`:** el token no está en memoria, así que no se
  puede usar `verify` con stdin. Se hace DELETE N+1 y se pasa a
  `FAILED_ISSUE`. Si un fichero ya tenía N+1, el worker recibirá 403 hasta el
  siguiente tick correcto. Esto es aceptable: falla cerrado y no usa una
  credencial ambigua.
- **Caída en `VERIFIED` o `REVOKING_OLD`:** se repite la consulta del board y
  el DELETE N. Ambos son idempotentes.
- **Respuesta del POST perdida:** nunca se reenvía el POST con el mismo ID (la
  API devuelve 409 y no reemite). Siempre se usa DELETE de ese ID y después un
  ID nuevo.

## 6. Política de margen TTL y semántica de fallo

- TTL del ciclo: 2 h (máximo de la API).
- Margen mínimo necesario:
  `lease máx. (MAX_LEASE_SECONDS=1800, run_self_development_worker.py:29)
  + emisión/instalación/verificación (≤ 2 min) + desfase de reloj (≤ 1 min)
  + un tick del timer (5 min)` ≈ 38 min.
- **Renovar al 50 % del TTL (T−60 min).** Cubre ese margen con unos 20 min de
  holgura, lo que permite ~4 reintentos completos de emisión antes de que el
  worker se quede sin credencial. No se renueva antes porque cada renovación
  crea un principal y abre una ventana de solape.
- **Cota de solape (b):** N y N+1 conviven desde el POST hasta el DELETE N. El
  DELETE espera al drenaje, pero nunca más allá de
  `min(expires_at(N), POST + 35 min)`. 35 min es la duración del lease más el
  `TimeoutStopSec` de #356. La caducidad de N es una cota dura e
  independiente: **el solape máximo es de 60 min**, aunque el DELETE falle
  siempre.
- **Credencial caducada (a):** si la emisión falla hasta `expires_at(N)`, el
  worker recibe 403 y falla cerrado. No hay reintentos indefinidos con la
  credencial muerta. Hoy #356 sale con un código distinto de cero y
  `Restart=on-failure` puede agotar `StartLimitBurst=5/300s`, dejando la
  unidad en estado `failed`, que el PM no puede reiniciar (G6).
- Nunca se emite un tercer ciclo si `next_cycle_id` no está cerrado: como
  máximo hay dos ciclos no revocados a la vez.

## 7. Huecos y propuestas exactas

Estado de integración en `origin/main` 5531466 (PR #377): G1, herencia de
perfil G3, G4 y G7 están implementados. La transferencia de asignaciones entre
ciclos no está implementada por la emisión. Las propuestas históricas siguientes
se conservan como contexto, no como estado actual.

**G1. Vínculo host — implementado por #377.** La emisión vincula el nuevo
principal implementador al host protegido de la API; la revocación limpia el
binding mediante la función restringida de la migración 041. No sustituir este
flujo por `register-host-worker` manual en cada renovación. La instalación de
041 y los grants del runtime deben verificarse en el host.

**G2. Operación `replace` del instalador — implementada por #361.**
El código admite reemplazo atómico, restringido a tokens Self Development, y
el helper permite esa operación. Falta verificar que el helper actualizado
esté instalado en el host; no se hizo ninguna acción de host para este PR.

- `install_publisher_token_for_role.py --replace`: lee el token de stdin;
  crea `.<name>.<rand>.tmp` con `O_CREAT|O_EXCL|O_NOFOLLOW` y modo 0600 en el
  mismo runtime; hace `write` + `fsync`, `os.replace` sobre el destino, y
  `fsync` del directorio.
- Solo se permite para `selfdev-implementer` y `selfdev-reviewer`. El destino
  previo, si existe, debe ser un fichero regular con un enlace, propiedad de
  la cuenta y modo 0600; si no, se rechaza.
- El helper permite `replace`. Un administrador debe desplegar la revisión
  actualizada en `/usr/local/libexec/aao`; el sudoers no necesita cambiar.

**G3. Herencia del perfil — resuelta en código (#377); transferencia de tareas
— pendiente.** La API copia solo el perfil activo más reciente de un
implementador previo elegible del mismo proyecto. Al revocar, el trabajo no
reclamado se escala para que un coordinador lo reasigne; no se transfiere
automáticamente al implementador nuevo.

**G4. Escalado al revocar un ciclo — resuelto en código (#377).** El DELETE
deshabilita la credencial, retira el binding mediante la función de migración
041 y escala trabajo no reclamado dentro de la misma transacción.

**G5. Consumidor del token revisor.** Hay que definir qué proceso usa
`aao-self-development-reviewer.token`, o dejar de emitirlo en las
renovaciones mientras no exista consumidor. Hoy no hay ninguno en el repo.

**G6. Tolerancia del worker** (sin cambio de API; afecta a #356).

- Ante un 403 en `/v1/principals/me`, el worker debe esperar con backoff
  acotado y no salir; también puede usarse `Restart=always` sin agotar
  `StartLimit`.
- Nunca debe actuar sin una identidad verificada.

**G7. DELETE de un ciclo inexistente — resuelto en código (#377).** Si ninguno
de los dos principals existe, la API devuelve 404 `CYCLE_NOT_FOUND`; el estado
parcial inesperado continúa fallando cerrado.

## 8. Eventos de auditoría

Los de la API ya existen: `principal.selfdev_cycle_role.issued` y
`principal.selfdev_cycle_role.revoked` (`:956-960`, `:1008-1011`), con
`issuer_principal_id`.

El orquestador los emite como líneas JSON en stdout (journal de la unidad, sin
secretos):

- `selfdev_cycle.renewal_started{current,next,expires_at}`
- `…installed{next}`, `…verified{next,impl,reviewer}`
- `…drain_waited{old,seconds}`, `…old_revoked{old,already}`
- `…failed{phase,cycle,reason}`, `…next_revoked{next,outcome}`
- `…expired_without_successor{old}` (alerta), `…lock_busy`

El evento API de emisión incluye `host_id` y `profile_inherited_from` cuando
aplica. Todavía no hay alertas externas: un fallo deja la unidad oneshot en
`failed` y el evento en el journal, y alguien debe vigilarlo.

## 9. Decisiones reservadas al CEO (estratégicas o de gobernanza)

1. Aceptar que el grant `credential.issue_selfdev_cycle_roles` se renueve cada
   ≤ 30 días como punto de control humano recurrente, o fijar otro plazo. La
   renovación es una concesión de autoridad y no se automatiza aquí.
2. La aprobación CEO para G1 y la herencia de perfiles G3 fue comunicada el
   2026-11-03 durante el desarrollo de #377. No se ha localizado en esta revisión
   un registro formal del repositorio; enlazarlo antes de elevar autonomía.

G2 está implementado por #361, pero su despliegue en host requiere un
administrador. G5 (consumidor del token revisor) y G6 (recuperación del worker
tras fallos) siguen siendo huecos técnicos. El runner renueva también el token
revisor, aunque no tenga consumidor (G5).

## 10. Límites de este documento

- El análisis original fue estático de `120f222`; las referencias de código se
  actualizaron tras #377. Esta revisión documental no usó tokens.
- No se ha verificado si #349 (`restore_pm_cycle_authority.py`) se ejecutó en
  el host ni si el grant emisor está vigente.
- #356 está fusionado en main. Este documento no verifica la instalación,
  activación ni funcionamiento del worker en el host.
- #377 implementa el binding y la limpieza de ciclo con migración 041; #361
  implementa `replace`. Estas fusiones no demuestran que el helper, la unidad
  worker o el orquestador estén desplegados en el host.
- El estado de host citado en §1 procede de metadatos aportados por el operador
  el 2026-11-03; no se inspeccionaron ficheros de entorno ni tokens.
- El orquestador (`renew_selfdev_cycle_credentials.py` y sus unidades) solo se
  ha probado con dobles (`tests/test_renew_selfdev_cycle_credentials.py`) y con
  `systemd-analyze --user verify`. No se ejecutó contra la API, el wrapper ni el
  host; no se instaló y no se habilitó ningún timer.
- **Bloqueos para la operación desatendida real:**
  - Pasos de host de §3.1 sin hacer.
  - Worker `aao-selfdev-codex-worker` no desplegado (§1).
  - G5: no hay consumidor del token revisor.
  - G6: el worker sale ante un 403 y puede agotar `StartLimitBurst`; el PM no
    puede reiniciarlo.
  - G3: la transferencia de asignaciones entre ciclos no está implementada.
  - El grant emisor del PM caduca cada ≤ 30 días (decisión CEO, §9.1).
  - Tras un reinicio hay que reaprovisionar el token PM y repetir
    `--bootstrap`.
  - La autenticación de principals solo funciona si la API corre con
    `AAO_ENV` igual a `development` o `test` (`principal_credentials.py:16-19`).
  - Con un fallo persistente de despliegue (por ejemplo, el wrapper sin
    `replace`, que devuelve el código 2), cada tick de 5 min emite y revoca un
    par de ciclo, con su vínculo host. El código de salida queda en el evento
    `failed`.
- El worker (`run_self_development_worker.py`, `run()`) vuelve a leer el fichero
  de token en cada iteración. Por eso recoge N+1 en la siguiente iteración sin
  reiniciarse; el drenaje de §5 depende de ello.
- Tests y CI no constituyen auditoría independiente (GOV-REV-001).
