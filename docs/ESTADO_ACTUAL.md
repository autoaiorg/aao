# Estado actual de AAO

**Corte:** 2026-11-02 21:51 UTC. **Revisión:** `1a70bca5411191a479840a673478fc60fa3f9b6b` (`origin/main`; merge de #343). Este informe es un estado de coordinación, no una certificación de autonomía, despliegue o aceptación.

## 1. Evidencia de repositorio

| Hecho | Estado | Evidencia |
|---|---|---|
| HEAD de `main` | `1a70bca5411191a479840a673478fc60fa3f9b6b` | `git rev-parse origin/main`; merge de #343 |
| CI post-merge de `main` | SUCCESS | Run `41531435732` corresponde al SHA exacto de `main`; `gh run view` informa `completed/success` |
| PRs abiertos | #341 y #342, ambos draft | `gh pr list --state open -R autoaiorg/aao`; #341 head `33bc64f2309d0a504127be6b581833864d3d34b5`; #342 actualiza este informe |
| CI post-merge de #343 | SUCCESS | Run `41531435732` corresponde al SHA actual de `main`; `completed/success` |
| #344 matriz de autorización | MERGED | Merge commit `eca67626e77a8c734230f9a431d5f0b77b177fde`, 2026-11-02T21:24:37Z; aclara que `VERIFIED` vía API no equivale a auditoría/aceptación independiente ni autoriza promoción |
| #345 provisión de roles de ciclo Self Development | MERGED | Merge commit `9a91345facc7ed8f1c6c707479f1af19bf94b494`, 2026-11-02T21:43:29Z; permite aprovisionar identidades de ciclo con límites definidos, pero no acredita que se hayan provisionado ni que haya candidato |
| #327 bootstrap/migraciones | MERGED | PR #327, merge commit `1770974c60be729c9de95b537ed0eb4fb08ed0c7` |
| #318 push relay | MERGED, opt-in; no acredita despliegue | PR #318, head `8d749e9de2f0ff2071fafdc470b25cd7d9e74f0c`; revisión independiente previa APPROVE WITH NITS |
| #329 espejo/integrador vs git 2.56 | MERGED | PR #329, head `526f62ab58510a5f6d4c46ca94fb8767b20d1534`; revisión independiente previa APPROVE WITH NITS |
| #331 autorrotación PM de dos fases | MERGED | PR #331, merge en el HEAD actual; reauditoría independiente condicional y CI verde según el comentario de cierre de #322 |
| #341 autorrotación publisher W2 dirigida al rol | OPEN, draft; checks no verdes en los dos runs más recientes: un `test` FAILURE y otro `test` IN_PROGRESS; sin reviews GitHub registradas al corte | Head `33bc64f2309d0a504127be6b581833864d3d34b5`; requiere resolver el fallo, CI verde y revisión independiente del head vigente antes de considerar merge |
| #343 límites de privilegio runtime | MERGED | Head `d8d918101d3d4badf51f95ace7ad2086e399f0eb`; merge commit `1a70bca5411191a479840a673478fc60fa3f9b6b`, 2026-11-02T21:46:41Z. Auditoría previa APPROVE WITH NITS reportada; no equivale a despliegue ni aceptación |
| #342 este estado | OPEN, draft | Head `ec23b0b94892606c18ad90b029d0a956bd62d2d8` antes de esta actualización; se mantiene draft |
| #251 y #330 | CLOSED, ramas/historial conservados | Verificación y comentario de cierre en issue #322 |
| #299, #325 y #321 | CLOSED/sustituidos o integrados | #299 sustituido por #327; #325 cerrado como contenido en #327; #321 cerrado al integrarse B2 en #324 |

Las fusiones y CI no equivalen a aceptación del piloto. La lista y estados se comprobaron en GitHub el 2026-11-02 21:49 UTC; el estado remoto puede cambiar después del corte. Issue #322 está CLOSED; su cierre administrativo no cierra los gates de aceptación.

## 2. Gates de aceptación del proyecto

La referencia de gates sigue siendo `docs/HANDOVER_ACCEPTANCE_MATRIX.md`, criterios 1–10 y E-1/E-2. **No hay evidencia suficiente aquí para marcar ninguno como cerrado ni para declarar AAO plenamente autónomo.** La matriz contiene material histórico y debe reconciliarse con el estado actual antes de usarla como certificación.

| Área | Estado para aceptación | Qué falta demostrar |
|---|---|---|
| Candidato y SHA aceptado | ABIERTO | Candidato identificable, aprobado y verificado en la revisión exacta |
| Revisión de trabajo elegible | BLOQUEADO | Consulta read-only en `aao_dev` al corte: los dos ítems `IN_REVIEW` no tienen review `APPROVE`. No se consultó/renovó grant en esta actualización; la elegibilidad de un reviewer no se da por demostrada |
| Raíz de confianza y protección del canónico | ABIERTO | Evidencia sobre el candidato; reglas finales y efectivas de protección |
| Identidades, privilegios y host | ABIERTO | Ejercicio real de roles y límites efectivos en el host/BD destino |
| Candidato W2 | ABIERTO / BLOQUEADO | Consulta read-only en `aao_dev` a las 21:51 UTC: 0 ítems `VERIFIED`; los dos `IN_REVIEW` tienen 0 reviews `APPROVE`. No hay candidato elegible observado. No crear ni cambiar estados para fabricar uno. Aun si la API marca un ítem `VERIFIED`, eso no es por sí solo aceptación independiente bajo GOV-REV-001 |
| Flujo integrado de trabajo | ABIERTO | Ciclo completo reproducible, incluidos fallos, reintentos y efectos externos inciertos |
| W2 / GitHub Apps | ABIERTO | Publicación real verificable con identidades separadas y evidencia sin token CEO |
| Auditoría y aceptación | ABIERTO | Auditoría independiente aplicable a la revisión final y disposición formal del CEO |
| Autonomía operativa | ABIERTO | Despliegue, supervisión, recuperación y operación continua demostrados; una feature fusionada no basta |
| E-1 y piloto E-2 | ABIERTO | Cierre de los gates de la matriz y ensayo de resistencia §14 sobre la revisión candidata |

## 3. Capacidades fusionadas y límites conocidos

- **Bootstrap/fencing (#327):** integrado en `main`, incluidas migraciones 036–038 y endurecimiento posterior. CI verde acredita los jobs de CI, no un bootstrap limpio en el host real ni la operación con sus roles.
- **Emisión y auto-rotación de credenciales (#324/#331/#345):** código integrado. La auto-rotación AGENT usa fase pendiente y confirmación. #345 añade aprovisionamiento acotado para roles del ciclo Self Development, pero la presencia del código no demuestra que las identidades se hayan provisionado. #341 sigue abierto en draft con autorrotación publisher dirigida al rol; el head `33bc64f` no tiene review GitHub registrada al corte y sus dos runs más recientes muestran `test` FAILURE e IN_PROGRESS. No se debe tratar como aprobado ni fusionable hasta resolver el fallo, obtener CI verde y completar revisión independiente. No se reporta entrega de un token de implementador al coordinador como diseño aceptado.
- **Límites DB runtime (#343):** el código de preflight está integrado. Añade comprobaciones read-only concretas de privilegios de conexión/esquema; no demuestra todos los grants runtime, una instalación en host limpio, ni un ciclo completo del servicio.
- **Push relay (#318):** integrado como transporte opt-in/prototipo. No se afirma que esté desplegado, conectado al supervisor o ejercitado contra GitHub/Worker/D1 reales. El informe de #322 registra como límites: trust multi-repo/forks no resuelto (forks se ponen en cuarentena), backoff de `retry_after` pendiente y procedimiento operativo para colas atascadas pendiente.
- **Push del integrador (#329):** integrado con aislamiento frente a configuración del espejo; no prueba que el integrador esté instalado o encendido. La activación sigue separada.
- **Proveedor ChatGPT:** el trabajo permanece en rama local WIP y bundles, sin push/PR ni autorización de proveedor registrada en este informe.

## 4. Host, base de datos y credenciales

Los siguientes datos se verificaron en el host el 2026-11-02 21:45 UTC, en modo de solo lectura. No se leyeron claves ni tokens:

- `frozen:tree` y `frozen:venv` de `aao-pm` pasaron en el preflight; árbol congelado en `cfd485c`, anterior al `main` actual.
- Linger estaba `yes` para `aao-pm` y `aao-impl-codex`; los runtimes aparecieron en PASS.
- Los archivos App `.pem`/`.json` habían pasado como metadatos en verificaciones previas; no se revalidó aquí su contenido ni sus permisos.
- Se emitió el principal PM `aao-pm-coordinator-20261102101514-a0c6a5ce` sin expiración, y dos principals publisher W2 con expiración `2026-11-02T18:17:36Z`. Esta expiración ya pasó; **no se afirma que sigan válidos ni que se hayan rotado**. El CEO aceptó los principales emitidos aunque la auditoría formal previa no se había completado.
- La unidad de usuario del coordinador existe como `aao-pm:aao-pm`, modo 0644. `systemctl --machine=aao-pm@.host --user is-active aao-project-coordinator@9d17d6c1-d644-424a-a425-fe7e084c3d91.service` devolvió `inactive`; no se inició ni habilitó.
- `loginctl show-user` devolvió `Linger=yes` para `aao-pm` y `aao-impl-codex`.
- `aao-postgres-1` está `Up 5 hours (healthy)`. `GET http://127.0.0.1:8001/health` devolvió HTTP 200 y `{"service":"postgres-dev","autonomous_execution":false}`; la API está activa, pero declara explícitamente `autonomous_execution=false`.
- Búsqueda de solo metadatos de ficheros `*.token` en los directorios runtime de los roles (UID 1001–1006) no encontró ninguno. No se leyó ningún fichero. Esto significa que no hay tokens runtime observables para usar el flujo en esta comprobación; no prueba por sí solo el estado de credenciales en la base de datos.
- Consulta PostgreSQL `BEGIN READ ONLY ... ROLLBACK` a Self Development: `DONE=3` (3 APPROVE asociados), `INBOX=1`, `IN_PROGRESS=1`, `IN_REVIEW=2` (0 APPROVE), `VERIFIED=0`. Los dos ítems IN_REVIEW son `0614ff49-8e8a-4f97-95fc-3499266fb60b` y `96fcff4e-c45f-48c0-9814-0242aaf8c08b`; ninguno tiene review APPROVE. No se alteraron datos.
- No se ha presentado evidencia de grants del rol runtime aplicados/verificados en el host. El PR documental #330 se cerró porque su diseño quedó desactualizado frente a la separación de roles de #327.

Actualización operativa del 2026-11-02 (reportada por el operador y reflejada en el body de #343): en `aao_dev` se retiró el privilegio TEMPORARY de `PUBLIC`; se comprobó `aao_runtime CONNECT=true`, `TEMP=false`, `aao_dev TEMP=true` y ausencia de `PUBLIC CREATE/TEMP`. Esto es evidencia de una frontera de privilegios concreta en la base de desarrollo, no acredita el resto de privilegios de tablas, la autenticación runtime, `db:runtime-complete`, el host destino ni el piloto. El auditor independiente reportó APPROVE WITH NITS para #343; el nit de redacción se corrigió en el head `d8d9181`. Se observaron seis checks SUCCESS en cada uno de los dos runs consultados.

**Bloqueo actual del reviewer/candidato (consulta read-only en `aao_dev`, 2026-11-02 21:51 UTC):** hay dos ítems `IN_REVIEW` y ninguno tiene review `APPROVE`; hay 0 ítems `VERIFIED`. Hay tres reviews `APPROVE` en ítems `DONE`, por lo que no faltan APPROVE globalmente, sino en los ítems actualmente `IN_REVIEW`. Esta actualización no consultó ni renovó ningún grant de reviewer. Consulta no secreta reproducible (sin leer tokens ni digests):

```sql
SELECT w.status, count(DISTINCT w.id) AS work_items,
       count(r.id) FILTER (WHERE r.decision = 'APPROVE') AS approve_reviews
FROM work_items w
LEFT JOIN reviews r ON r.work_id = w.id
WHERE w.project_id = '9d17d6c1-d644-424a-a425-fe7e084c3d91'
GROUP BY w.status ORDER BY w.status;
```

La consulta devuelve estado y conteos, no credenciales, tokens ni digests. En `main` `9a91345`, la ruta `POST /v1/work/{id}/reviews` puede registrar `APPROVE` bajo sus precondiciones, incluida identidad reviewer requerida, grant vigente, proyecto activo, trabajo en revisión, evidencia resuelta, SHA ligado a ejecución `SUCCEEDED`, sin intentos activos y sin veto. #344 actualizó `docs/PRINCIPAL_AUTHORIZATION_MATRIX.md`: estado API `VERIFIED` no equivale a auditoría/aceptación independiente GOV-REV-001 ni autoriza promoción, merge o efectos externos; tampoco prueba por sí solo verdad o autoría de la evidencia. No existe candidato `VERIFIED` observado para el ensayo W2.

No incluir tokens, DSNs, claves privadas ni digests en este documento. Re-verificar mediante preflight por cuenta y consultas de solo metadatos antes de una operación real.

## 5. Acciones necesarias para avanzar

### No se requiere acción inmediata del CEO para continuar el trabajo técnico

La coordinación de #322 quedó cerrada; al corte siguen abiertos en draft #341 (rotación publisher W2) y #342 (este informe). #343 ya está fusionado, pero sus comprobaciones son parciales y no acreditan despliegue completo. El siguiente avance es investigar el fallo de `test` en uno de los runs de #341 (el otro sigue en curso), luego validar el límite de entrega de credenciales y los gates de integración seguros/autorizados. No se ha demostrado todavía autonomía plena ni aceptación del piloto.

### Decisiones que sí requieren al CEO

1. **Activar el servicio PM**: decisión separada. Antes de habilitarlo, verificar rol runtime, configuración, aprobación de revisión congelada y plan de parada/rollback. No hay evidencia de activación.
2. **Delegar emisión/rotación de publishers W2**: el diseño #326 describe que la API actual no permite autorrotación W2 sin capacidad adicional. No se ha concedido `credential.issue_publisher`; hace falta decisión explícita sobre límite de grants, caducidad y principal emisor antes de implementarla.
3. **Activación de proveedores o integrador**: permanece gate estratégico y fuera de este informe; código fusionado no los activa.

No se pide al CEO que ejecute comandos host en este momento. Si el siguiente gate exige una acción física o credencial que no pueda ejecutarse con identidad de servicio autorizada, se detallará el comando exacto, impacto, verificación y reversión antes de solicitarla.

## 6. Próximos pasos recomendados

1. Reconciliar `HANDOVER_ACCEPTANCE_MATRIX.md` con `main` `1a70bca`; mantener separados “implementado”, “desplegado”, “ejercitado”, “auditado” y “aceptado”.
2. Revalidar preflight sobre el `main` actual, por separado bajo `aao-pm` y `aao-impl-codex`; comprobar únicamente metadatos de credenciales, nunca leerlas.
3. Identificar, mediante lectura autorizada de la BD, si existe candidato VERIFIED y SHA aprobado. La última búsqueda reportó cero; no crear ni cambiar estados para fabricar un candidato. Este sigue siendo un bloqueo del ensayo W2.
4. Reconciliar los roles de DB/host de #327 con el despliegue real y probarlos en entorno desechable antes de aplicar grants al host.
5. Cerrar los pendientes operativos de #318 (trust por repo/forks, backoff, operación de cuarentena y prueba real) antes de afirmar que el relay aporta disponibilidad.
6. Ejecutar el piloto integrado §14 únicamente cuando exista candidato elegible y evidencia previa de identidades, App scopes, runtime y protección.
7. Solicitar auditoría final independiente GOV-REV-001 contra un SHA único; después el CEO dispone la aceptación formal.

## 7. Fuentes y límites

- Git: `git rev-parse origin/main` = `1a70bca5411191a479840a673478fc60fa3f9b6b`; #343 está MERGED y su merge commit coincide con ese SHA. El worktree de este PR se actualizó incorporando `origin/main`; la rama del PR sigue separada de `main`.
- GitHub: `gh pr list --state open -R autoaiorg/aao` a 21:51 UTC mostró solo #341 (`33bc64f`) y #342 (head previo `ec23b0b`), ambos draft. `gh pr view 341` confirmó el head `33bc64f2309d0a504127be6b581833864d3d34b5`; `gh run view 41531685699` (PR, 21:48:24Z) terminó FAILURE: `test` falló y `frontend`/`push-relay-worker` pasaron. `gh run view 41531674897` (push, 21:48:20Z) sigue IN_PROGRESS: `test` sigue ejecutándose y los otros dos jobs pasaron. `gh api repos/autoaiorg/aao/pulls/341/reviews` devolvió lista vacía al corte. `gh run list --branch main -R autoaiorg/aao --limit 3`: run `41531435732` sobre `1a70bca` está `completed/success`. `gh pr view` confirmó #318, #327 y #343 MERGED; #345 MERGED a `9a91345` a las 21:43:29Z.
- Host/API/DB: `curl -sS -w 'http=%{http_code}' http://127.0.0.1:8001/health` devolvió HTTP 200 y `{"service":"postgres-dev","autonomous_execution":false}`. `docker ps` informó PostgreSQL healthy. Consulta a Self Development dentro de `BEGIN READ ONLY ... ROLLBACK`: DONE=3/3 APPROVE, INBOX=1, IN_PROGRESS=1, IN_REVIEW=2/0 APPROVE, VERIFIED=0. La consulta no alteró DB. Un intento exploratorio read-only de ordenar por `work_items.created_at` falló porque esa columna no existe; se repitió la consulta corregida, solo lectura, y los conteos anteriores sí proceden de esta última.
- Runtime: `loginctl show-user` devolvió Linger=yes para aao-pm y aao-impl-codex; la unidad de usuario del PM existe con propietario/modo esperados pero está `inactive`. No se inició ni habilitó. La búsqueda de metadata para `*.token` en runtimes UID 1001–1006 no encontró ficheros; no se leyó contenido ni se infiere el estado DB de credenciales.
- #343: el PR describe la retirada de `PUBLIC TEMP` y la verificación `aao_runtime TEMP=false`; quedó MERGED como `1a70bca`. La auditoría independiente se reportó como APPROVE WITH NITS, con ajuste de wording antes de merge; no sustituye aceptación ni acredita límites completos runtime.
- #344: merge `eca67626` actualiza la matriz para hacer explícito que `VERIFIED` de API no equivale a aceptación independiente GOV-REV-001 ni autoriza promoción/merge/efectos externos.
- Issue #322: `gh issue view 322 -R autoaiorg/aao --json state,title,updatedAt,url`, CLOSED, actualizado `2026-11-02T18:23:23Z`.
- Gates: `docs/HANDOVER_ACCEPTANCE_MATRIX.md`; debe actualizarse para el estado post-merge.
- Este informe no ejecutó pruebas ni operaciones que cambien host/DB; sí ejecutó consultas read-only dentro de una transacción de solo lectura. No confirma vigencia de tokens, despliegue, privilegios completos runtime, activación de servicios ni aceptación final. La consulta a Self Development a las 21:51 UTC observó 0 ítems `VERIFIED` y 0 `APPROVE` en los dos ítems `IN_REVIEW`. El CI post-merge de `main` está en SUCCESS; #341, en cambio, tiene un run de PR fallido y otro en curso. Esto no cierra los gates de operación ni aceptación.
