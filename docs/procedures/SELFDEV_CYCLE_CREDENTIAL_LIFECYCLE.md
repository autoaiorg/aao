# Ciclo de vida desatendido de credenciales de ciclo Self Development (diseño)

Estado: **diseño; no implementado**. Revisión base: `f127a7e` (origin/main,
2026-11-03). Este documento no emite, concede ni amplía credenciales. Toca la
emisión de credenciales: exige auditoría independiente (GOV-REV-001) antes de
fusionarse y antes de cualquier implementación derivada.

Objetivo: que el PM (`aao-pm`), solo con su token PM, mantenga al worker
`aao-impl-codex` con una credencial de ciclo válida, sin token CEO y sin
intervención humana. Hay dos condiciones simultáneas:

- (a) el worker nunca debe quedar con una credencial caducada mientras haya
  trabajo;
- (b) nunca debe haber dos ciclos válidos más allá de un solape acotado.

## 1. Conclusión

Con la superficie actual de la API, el ciclo **no puede cerrarse sin
intervención privilegiada**. Hay dos bloqueos duros:

1. **Vínculo host del principal nuevo (G1).** Cada ciclo crea un principal
   implementador nuevo (`aao-selfdev-impl-<cycle>`). Para reclamar
   ejecuciones, ese principal necesita exactamente un `host_worker_bindings`
   ACTIVE. Ese vínculo solo se crea con `aao-ops register-host-worker`, que
   requiere DSN de base de datos o root. La solución exige cambiar la API, así
   que este documento se queda en el diseño (§7).
2. **Instalación atómica (G2).** El instalador rechaza sobrescribir. Su
   operación `remove` exige el token antiguo, que el PM no conserva. La
   solución exige cambiar un helper instalado como root y reinstalarlo en el
   host (§7).

Por tanto **no se implementa `scripts/rotate_selfdev_cycle_credentials.py`**.
Un script así acabaría en un paso con sudo/DSN o tendría que modificar un
componente de credenciales instalado como root. Ambas cosas quedan fuera del
mandato de este cambio.

**#331 (auto-rotación AGENT) no sirve para renovar el TTL.**
`POST /v1/principals/me/rotate` (`src/aao/work_management_api.py:1024`) y
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
| Revocar ciclo N | Sí, idempotente | `DELETE …/selfdev-cycle-roles/{cycle_id}` (`:967`), `rw` + PM-issuer; `already_revoked` (`:1001-1002`). Un `cycle_id` que nunca llegó a existir devuelve **409** y no 404 (conjunto vacío ≠ grants, `:994-998`; G7) |
| Verificar identidad del implementador | Sí | `GET /v1/principals/me` (`:861`, `rw`) con el token nuevo |
| Verificar identidad del revisor | Parcial | No existe `/v1/auditors/me`; `GET /v1/auditors/me/grants` (`:1219`, `require_reviewer`) devuelve principal y grants |
| Observar el drenaje del worker antiguo | Sí | `GET /v1/projects/{id}/board` (`:3771`, `read_principal` + `project.read`, que el PM tiene) expone `executions[].worker_id/status` y `assigned_principal_id` |
| Comprobar / instalar / verificar fichero de rol | Sí, solo si el destino está vacío | `sudo /usr/local/libexec/aao/selfdev_role_token_helper.py` (`scripts/selfdev_role_token_helper.py:18-22`), con el instalador `install` `O_EXCL` (`scripts/install_publisher_token_for_role.py:73-78`) |
| **Reemplazar atómicamente el fichero existente** | **No (G2)** | `install` rechaza sobrescribir (`:77-78`); `check` falla si existe (`:135-137`) |
| **Borrar el fichero del ciclo N** | **No (G2)** | `remove` exige el token N por stdin y lo verifica (`:142-144`); el PM no lo conserva (solo en memoria, `request_selfdev_cycle_roles.py:176`) |
| **Vincular el implementador nuevo al host** | **No (G1)** | `claim` → `active_host_fence_epoch(worker_id)` (`src/aao/execution_queue.py:152-179, 215`); solo escribe `aao-ops register-host-worker` (`src/aao/ops.py:527-539`, `src/aao/backup.py:1000-1014`) mediante `AAO_POSTGRES_URL` (`src/aao/postgresql_connection.py:14`); los docs lo ejecutan con `sudo` (`docs/procedures/W2_REAL_GITHUB_APPS.md:46`) |
| Parar o reiniciar el worker de `aao-impl-codex` | No, pero **no hace falta** | `aao-pm` no controla el gestor systemd de otro usuario. El worker relee el token en cada iteración (`scripts/run_self_development_worker.py:82, 127`), y #356 (abierto) resuelve `/v1/principals/me` en cada `run()` |
| Reasignar hijos de grupo al principal nuevo | **No (G3)** | `work.assign` del PM existe, pero la asignación PM exige un perfil con competencias (`work_management_api.py:3155-3168`), y `PUT /v1/organization/profiles` es `require_ceo` (`:1551-1552`) |
| Escalar el trabajo asignado al ciclo revocado | **No (G4)** | El DELETE de ciclo (`:967-1012`) no escala, a diferencia de `/principals/{id}/revoke` (`:1270-1300`, CEO) |
| Renovar el grant emisor del PM (30 días) | **No: CEO, por diseño** | `SELFDEV_CYCLE_ISSUER_GRANT_TTL` (`:886`); concesión de grants solo `require_ceo` |
| Autenticación de principals en `AAO_ENV=production` | **No** (fuera de este alcance) | `_development_credentials_enabled` solo admite `development` y `test` (`principal_credentials.py:16-19`) |

Hallazgo adicional: en el repositorio no hay ningún consumidor runtime del
fichero `aao-self-development-reviewer.token` fuera del instalador.
`scripts/self_development_cycle.py:30` usa `aao-auditor.token`. El ciclo de
vida del revisor está, por tanto, definido solo a medias (G5).

## 3. Quién lo ejecuta

- Unidad systemd de usuario de `aao-pm`:
  `aao-selfdev-cycle-credentials@<project>.service` (oneshot) más un `.timer`
  (`OnUnitActiveSec=5min`, `Persistent=true`). Usa el árbol y el venv
  congelados de `/srv/aao/frozen/aao-pm`, igual que el coordinador.
- La unidad **no** puede llevar `NoNewPrivileges=yes`, porque necesita `sudo`
  hacia el wrapper root. Es la diferencia consciente respecto de
  `deploy/systemd/user/aao-project-coordinator@.service`. Compensación: el
  sudoers solo permite el wrapper (`SELF_DEVELOPMENT_CYCLE_ROLES.md` §setup 3).
- Lock exclusivo `flock` en `/run/user/<uid-pm>/aao-selfdev-cycle.lock`: nunca
  hay dos ejecuciones simultáneas.
- Credencial: solo el token PM. Nunca el token CEO, ni `.env.local`, ni un DSN.

## 4. Privilegios mínimos

| Sujeto | Necesita | Ya existe |
|---|---|---|
| Principal PM | `project.read`, `work.coordinate`, `credential.issue_selfdev_cycle_roles` (≤ 30 días) en Self Development | Sí (#347/#348/#349; aplicación en host **no verificada** aquí) |
| Linux `aao-pm` | `sudo` NOPASSWD solo sobre `/usr/local/libexec/aao/selfdev_role_token_helper.py` | Diseñado en #347; aplicación en host no verificada |
| Wrapper root | Nueva operación `replace` (G2) | **No** |
| API (`aao_runtime`) | `INSERT` sobre `host_worker_bindings` (G1) | Sí (`scripts/bootstrap/apply_api_grants.sql:31`); falta el código |

No se necesita `work.assign` para el ciclo en sí. Solo hace falta si se
resuelve G3 por reasignación.

## 5. Máquina de estados

Estado persistido **sin secretos** en
`~aao-pm/.local/state/aao/selfdev-cycle-<project>.json` (0600, escritura
atómica con temp + `fsync` + `rename`):

```json
{"phase": "...", "current_cycle_id": "<hex32|null>", "current_expires_at": "...",
 "next_cycle_id": "<hex32|null>", "next_expires_at": "...", "updated_at": "..."}
```

Ningún token se escribe en el estado, en argv, en el entorno, en stdout o en
los logs. Los tokens viven solo en la memoria del proceso entre el POST y el
`replace` (stdin del wrapper).

| Estado | Significado | Transición normal | Fallo |
|---|---|---|---|
| `ACTIVE` | El ciclo N está instalado y verificado, y le queda más del margen | Al cruzar el umbral de renovación (§6): genera `next_cycle_id`, **persiste** y pasa a `ISSUING` | — |
| `ISSUING` | El ID N+1 está persistido antes del POST | POST correcto → `replace` de ambos ficheros → `INSTALLED_PENDING` | Error, 409 o respuesta perdida → `FAILED_ISSUE` |
| `INSTALLED_PENDING` | Los ficheros contienen N+1; falta verificarlos | `verify` de fichero + `/v1/principals/me` (impl) y `/v1/auditors/me/grants` (revisor): IDs exactos, kind y grants exactos → `VERIFIED` | → `FAILED_INSTALL` |
| `VERIFIED` | N+1 está verificado; el worker lo recoge en la siguiente iteración | Si el board no muestra ejecuciones `RUNNING`/`UNCERTAIN`/`QUEUED` con `attempts>0` y `worker_id = impl-N`, o si N ya caducó → `REVOKING_OLD` | Plazo de drenaje superado → `REVOKING_OLD` igualmente (§6) |
| `REVOKING_OLD` | Se revoca el ciclo N | DELETE N devuelve `revoked` o `already_revoked` → `current := next` y `next := null` → `ACTIVE` | Error → se queda en `REVOKING_OLD` y reintenta en cada tick |
| `FAILED_ISSUE` | N+1 puede existir o no en el servidor | DELETE N+1. `revoked` o `already_revoked` → `next := null` → `ACTIVE`; reintenta en el próximo tick con un ID **nuevo** | 409 es ambiguo (nunca existió o conjunto alterado; G7): se registra, se alerta y se cierra igualmente, porque N+1, si existe, caduca en ≤ 2 h y sus tokens se perdieron. Error de red → se mantiene |
| `FAILED_INSTALL` | Un fichero puede contener N+1, y su token ya se perdió de memoria | DELETE N+1. Si N sigue vigente, el fichero debe volver a N, pero el PM no tiene ese token. El worker falla cerrado (403) hasta la siguiente emisión correcta → `FAILED_ISSUE` | — |
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

## 7. Huecos y propuestas exactas (no implementadas)

**G1. Vínculo host del implementador del ciclo** (necesita cambio de API; sin
migración).

- En `issue_selfdev_cycle_roles` (`:907`), dentro de la misma transacción y
  solo para el rol `aao-selfdev-impl-<cycle>`: `pg_advisory_xact_lock`
  sobre `host_id`, después `INSERT INTO host_worker_bindings(host_id,
  worker_id, status, fence_epoch) SELECT %s, %s, 'ACTIVE',
  COALESCE(MAX(fence_epoch),1) FROM host_worker_bindings WHERE host_id=%s`.
- `host_id` sale de `current_host_id(allow_test_override=False)` en el
  proceso de la API. No se acepta del cliente.
- Debe ser un INSERT simple, sin `ON CONFLICT DO UPDATE`: `aao_runtime` solo
  tiene `SELECT, INSERT` (`apply_api_grants.sql:31`) y el principal es nuevo
  por construcción.
- Hay que rechazar la emisión si el host está cercado (ningún ACTIVE con epoch
  coherente) y auditar `host_id` en `principal.selfdev_cycle_role.issued`.
- Revocación: no hace falta un UPDATE del vínculo. `claim` ya falla en
  `verify_execution_principal` con la credencial deshabilitada. Las filas
  ACTIVE de ciclos revocados las limpia el rol `aao_fencer`.

**G2. Operación `replace` del instalador** (cambio en un helper root;
reinstalación única por un administrador del host; no es decisión del CEO).

- `install_publisher_token_for_role.py --replace`: lee el token de stdin;
  crea `.<name>.<rand>.tmp` con `O_CREAT|O_EXCL|O_NOFOLLOW` y modo 0600 en el
  mismo runtime; hace `write` + `fsync`, `os.replace` sobre el destino, y
  `fsync` del directorio.
- Solo se permite para `selfdev-implementer` y `selfdev-reviewer`. El destino
  previo, si existe, debe ser un fichero regular con un enlace, propiedad de
  la cuenta y modo 0600; si no, se rechaza.
- En `selfdev_role_token_helper.py:22`, añadir `replace` a `OPERATIONS`.
  Después, el root copia ambos ficheros a `/usr/local/libexec/aao`. El sudoers
  no cambia.

**G3. Perfil y reasignación de hijos de grupo** (necesita cambio de API).

- Opción preferida: que la emisión copie al implementador N+1 el perfil
  organizativo (competencias) del implementador del ciclo anterior **solo** si
  este pertenece al mismo proyecto y es un `aao-selfdev-impl-*`. Así no hace
  falta un nuevo endpoint CEO.
- Además, `POST /v1/projects/{id}/selfdev-cycle-roles/{new}/inherit-assignments`
  (`rw` + PM-issuer): reasigna los hijos en `INBOX`/`READY`/`IN_PROGRESS` del
  `impl` antiguo, sin ejecuciones activas, al nuevo, y audita `work.assigned`
  con `previous_principal_id`.
- Sin G3, los hijos de grupo asignados al ciclo N quedan huérfanos.

**G4. Escalado al revocar un ciclo** (cambio de API). El DELETE de ciclo debe
reutilizar el escalado de `/principals/{id}/revoke` (`:1270-1300`) para el
trabajo asignado que G3 no haya heredado.

**G5. Consumidor del token revisor.** Hay que definir qué proceso usa
`aao-self-development-reviewer.token`, o dejar de emitirlo en las
renovaciones mientras no exista consumidor. Hoy no hay ninguno en el repo.

**G6. Tolerancia del worker** (sin cambio de API; afecta a #356).

- Ante un 403 en `/v1/principals/me`, el worker debe esperar con backoff
  acotado y no salir; también puede usarse `Restart=always` sin agotar
  `StartLimit`.
- Nunca debe actuar sin una identidad verificada.

**G7. DELETE de un ciclo inexistente** (cambio menor de API).

- Si ninguno de los dos principals del ciclo existe, `DELETE
  …/selfdev-cycle-roles/{cycle_id}` debe devolver `404 {"code":
  "CYCLE_NOT_FOUND"}`.
- Así la recuperación de una respuesta perdida distingue entre «nunca se
  emitió» y «conjunto alterado». Hoy ambos casos devuelven 409.

## 8. Eventos de auditoría

Los de la API ya existen: `principal.selfdev_cycle_role.issued` y
`principal.selfdev_cycle_role.revoked` (`:956-960`, `:1008-1011`), con
`issuer_principal_id`.

Locales (journal de la unidad, sin secretos):

- `selfdev_cycle.renewal_started{current,next,expires_at}`
- `…installed{next}`, `…verified{next,impl,reviewer}`
- `…drain_waited{old,seconds}`, `…old_revoked{old,already}`
- `…failed{phase,cycle,reason}`
- `…expired_without_successor{old}` (alerta)

Propuesta asociada a G1: añadir `host_id` al evento de emisión.

## 9. Decisiones reservadas al CEO (estratégicas o de gobernanza)

1. Aceptar que el grant `credential.issue_selfdev_cycle_roles` se renueve cada
   ≤ 30 días como punto de control humano recurrente, o fijar otro plazo. La
   renovación es una concesión de autoridad y no se automatiza aquí.
2. Aprobar que la API cree vínculos host para los implementadores de ciclo
   (G1) y que se hereden perfiles y asignaciones (G3). Ambas cosas amplían lo
   que hace hoy la emisión delegada de #347, aunque no amplían grants.

G2, G5, G6 y G7 son decisiones técnicas del propietario del componente. Su
despliegue en el host lo hace un administrador. No son decisiones
estratégicas.

## 10. Límites de este documento

- Análisis estático de `f127a7e`. No se ejecutó nada contra el host, la API ni
  la base de datos, y no se usaron tokens.
- No se ha verificado si #349 (`restore_pm_cycle_authority.py`) se ejecutó en
  el host ni si el grant emisor está vigente.
- #356 sigue abierto. Este diseño asume su resolución de identidad por
  iteración.
- Tests y CI no constituyen auditoría independiente (GOV-REV-001).
