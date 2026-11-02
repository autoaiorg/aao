# Estado actual de AAO

**Corte:** 2026-11-02 21:25 UTC. **Revisión:** `eca67626e77a8c734230f9a431d5f0b77b177fde` (`origin/main`; merge de #344). Este informe es un estado de coordinación, no una certificación de autonomía, despliegue o aceptación.

## 1. Evidencia de repositorio

| Hecho | Estado | Evidencia |
|---|---|---|
| HEAD de `main` | `eca67626e77a8c734230f9a431d5f0b77b177fde` | `git rev-parse origin/main`; merge de #344 |
| CI post-merge de `main` | IN PROGRESS al corte | Run `41528081990` corresponde al SHA exacto de `main`; `push-relay-worker` SUCCESS y `test`/`frontend` aún en curso |
| PRs abiertos | #341, #342 y #343, todos draft | `gh pr list --state open -R autoaiorg/aao`; #341 head `f7e414a30941f2a28fb96ab4d14f75df8c612638`; #342 actualiza este informe; #343 head `d8d918101d3d4badf51f95ace7ad2086e399f0eb` |
| #343 preflight de límites DB runtime | OPEN, draft; CI SUCCESS | Checks `test`, `frontend`, `push-relay-worker` verdes en ambos runs consultados; añade comprobaciones read-only de privilegios de conexión/esquema, no acredita el conjunto completo de privilegios runtime ni el despliegue |
| #344 matriz de autorización | MERGED | Merge commit `eca67626e77a8c734230f9a431d5f0b77b177fde`, 2026-11-02T21:24:37Z; aclara que `VERIFIED` vía API no equivale a auditoría/aceptación independiente ni autoriza promoción |
| #327 bootstrap/migraciones | MERGED | PR #327, merge commit `1770974c60be729c9de95b537ed0eb4fb08ed0c7` |
| #318 push relay | MERGED, opt-in; no acredita despliegue | PR #318, head `8d749e9de2f0ff2071fafdc470b25cd7d9e74f0c`; revisión independiente previa APPROVE WITH NITS |
| #329 espejo/integrador vs git 2.56 | MERGED | PR #329, head `526f62ab58510a5f6d4c46ca94fb8767b20d1534`; revisión independiente previa APPROVE WITH NITS |
| #331 autorrotación PM de dos fases | MERGED | PR #331, merge en el HEAD actual; reauditoría independiente condicional y CI verde según el comentario de cierre de #322 |
| #251 y #330 | CLOSED, ramas/historial conservados | Verificación y comentario de cierre en issue #322 |
| #299, #325 y #321 | CLOSED/sustituidos o integrados | #299 sustituido por #327; #325 cerrado como contenido en #327; #321 cerrado al integrarse B2 en #324 |

Las fusiones y CI no equivalen a aceptación del piloto. La lista y estados se comprobaron en GitHub el 2026-11-02 21:25 UTC; el estado remoto puede cambiar después del corte. Issue #322 está CLOSED; su cierre administrativo no cierra los gates de aceptación.

## 2. Gates de aceptación del proyecto

La referencia de gates sigue siendo `docs/HANDOVER_ACCEPTANCE_MATRIX.md`, criterios 1–10 y E-1/E-2. **No hay evidencia suficiente aquí para marcar ninguno como cerrado ni para declarar AAO plenamente autónomo.** La matriz contiene material histórico y debe reconciliarse con el estado actual antes de usarla como certificación.

| Área | Estado para aceptación | Qué falta demostrar |
|---|---|---|
| Candidato y SHA aceptado | ABIERTO | Candidato identificable, aprobado y verificado en la revisión exacta |
| Revisión de trabajo elegible | BLOQUEADO | Consulta read-only en `aao_dev` al corte: ambos grants `work.review` están expirados y los dos ítems `IN_REVIEW` no tienen review `APPROVE`. El endpoint admite APPROVE bajo sus precondiciones, pero no hay grant activo ni candidato elegible demostrado |
| Raíz de confianza y protección del canónico | ABIERTO | Evidencia sobre el candidato; reglas finales y efectivas de protección |
| Identidades, privilegios y host | ABIERTO | Ejercicio real de roles y límites efectivos en el host/BD destino |
| Candidato W2 | ABIERTO / BLOQUEADO | Consulta read-only en `aao_dev` al corte: 0 ítems `VERIFIED`; hace falta una cadena de aprobación/evidencia sobre SHA exacto, sin fabricar estados. Aun si la API marca un ítem `VERIFIED`, eso no es por sí solo aceptación independiente bajo GOV-REV-001 |
| Flujo integrado de trabajo | ABIERTO | Ciclo completo reproducible, incluidos fallos, reintentos y efectos externos inciertos |
| W2 / GitHub Apps | ABIERTO | Publicación real verificable con identidades separadas y evidencia sin token CEO |
| Auditoría y aceptación | ABIERTO | Auditoría independiente aplicable a la revisión final y disposición formal del CEO |
| Autonomía operativa | ABIERTO | Despliegue, supervisión, recuperación y operación continua demostrados; una feature fusionada no basta |
| E-1 y piloto E-2 | ABIERTO | Cierre de los gates de la matriz y ensayo de resistencia §14 sobre la revisión candidata |

## 3. Capacidades fusionadas y límites conocidos

- **Bootstrap/fencing (#327):** integrado en `main`, incluidas migraciones 036–038 y endurecimiento posterior. CI verde acredita los jobs de CI, no un bootstrap limpio en el host real ni la operación con sus roles.
- **Emisión y auto-rotación de credenciales (#324/#331):** código integrado. La auto-rotación AGENT usa fase pendiente y confirmación. La emisión W2 delegada sigue en el PR #341, draft; su head publicado devuelve el token del implementador a la respuesta del coordinador PM y no debe fusionarse ni desplegarse así. Hay una modificación local sin commit en `.worktrees/w2-scoped-issuer` para corregir el límite de entrega; no forma parte aún del head publicado y requiere validación y reauditoría independiente.
- **Push relay (#318):** integrado como transporte opt-in/prototipo. No se afirma que esté desplegado, conectado al supervisor o ejercitado contra GitHub/Worker/D1 reales. El informe de #322 registra como límites: trust multi-repo/forks no resuelto (forks se ponen en cuarentena), backoff de `retry_after` pendiente y procedimiento operativo para colas atascadas pendiente.
- **Push del integrador (#329):** integrado con aislamiento frente a configuración del espejo; no prueba que el integrador esté instalado o encendido. La activación sigue separada.
- **Proveedor ChatGPT:** el trabajo permanece en rama local WIP y bundles, sin push/PR ni autorización de proveedor registrada en este informe.

## 4. Host, base de datos y credenciales

Los siguientes datos son **históricos, aportados por el coordinador el 2026-11-02 y no re-verificados en este corte**. No deben tratarse como lectura actual del host:

- `frozen:tree` y `frozen:venv` de `aao-pm` pasaron en el preflight; árbol congelado en `cfd485c`, anterior al `main` actual.
- Linger estaba `yes` para `aao-pm` y `aao-impl-codex`; los runtimes aparecieron en PASS.
- Los archivos App `.pem`/`.json` pasaron como metadatos bajo las cuentas respectivas.
- Se emitió el principal PM `aao-pm-coordinator-20261102101514-a0c6a5ce` sin expiración, y dos principals publisher W2 con expiración `2026-11-02T18:17:36Z`. Esta expiración ya pasó; **no se afirma que sigan válidos ni que se hayan rotado**. El CEO aceptó los principales emitidos aunque la auditoría formal previa no se había completado.
- El preflight por rol reportó cero MISSING antes de vencer los publishers; persistían UNVERIFIED para `pm:service`, `w2:live` y `db:inspection`.
- La unidad de usuario del coordinador se instaló y verificó sintácticamente; no hay evidencia de que esté habilitada o activa. La salida `systemd-analyze --user verify` fue limpia con `XDG_RUNTIME_DIR`.
- PostgreSQL de desarrollo se levantó durante la sesión; API local en `127.0.0.1:8001` fue reportada parada posteriormente. Estado actual: UNVERIFIED.
- No se ha presentado evidencia de grants del rol runtime aplicados/verificados en el host. El PR documental #330 se cerró porque su diseño quedó desactualizado frente a la separación de roles de #327.

Actualización operativa del 2026-11-02 (reportada por el operador y reflejada en el body de #343): en `aao_dev` se retiró el privilegio TEMPORARY de `PUBLIC`; se comprobó `aao_runtime CONNECT=true`, `TEMP=false`, `aao_dev TEMP=true` y ausencia de `PUBLIC CREATE/TEMP`. Esto es evidencia de una frontera de privilegios concreta en la base de desarrollo, no acredita el resto de privilegios de tablas, la autenticación runtime, `db:runtime-complete`, el host destino ni el piloto. El auditor independiente reportó APPROVE WITH NITS para #343; el nit de redacción se corrigió en el head `d8d9181`. A las 21:25 UTC se observaron los seis checks en SUCCESS en los dos runs consultados.

**Bloqueo actual del reviewer (consulta read-only en `aao_dev`, 2026-11-02 21:25 UTC):** los dos grants `work.review` encontrados para principals de tipo `AUDITOR` están expirados: `2026-10-25T18:32:42.718018Z` y `2026-10-26T01:30:45.350514Z`; ambos corresponden al proyecto Self Development. En el mismo proyecto hay dos ítems `IN_REVIEW` y ninguno tiene review `APPROVE`; hay 0 ítems `VERIFIED`. Hay tres reviews `APPROVE` en ítems `DONE`, por lo que la afirmación correcta no es que falten APPROVE globalmente, sino que faltan en los ítems actualmente `IN_REVIEW`. No se renovó ningún grant. Consulta no secreta reproducible (sin leer tokens ni digests):

```sql
SELECT c.principal_id, c.kind, c.enabled, g.capability, g.expires_at,
       (g.expires_at IS NOT NULL AND g.expires_at <= clock_timestamp()) AS expired
FROM principal_credentials c
JOIN project_grants g USING (principal_id)
WHERE c.kind = 'AUDITOR'
  AND g.project_id = '9d17d6c1-d644-424a-a425-fe7e084c3d91'
  AND g.capability = 'work.review'
ORDER BY g.expires_at;
```

La consulta de estado que produjo los conteos fue:

```sql
SELECT w.status, count(DISTINCT w.id) AS work_items,
       count(r.id) FILTER (WHERE r.decision = 'APPROVE') AS approve_reviews
FROM work_items w
LEFT JOIN reviews r ON r.work_id = w.id
WHERE w.project_id = '9d17d6c1-d644-424a-a425-fe7e084c3d91'
GROUP BY w.status ORDER BY w.status;
```

Esta consulta devuelve identificadores de principal y metadatos de grants; no consulta ni muestra credenciales, tokens o digests. Renovar los grants es una operación de CEO/principal delegado; no se ha ejecutado. En `main` `eca67626`, la ruta `POST /v1/work/{id}/reviews` puede registrar `APPROVE` bajo sus precondiciones, incluida identidad reviewer requerida, grant vigente, proyecto activo, trabajo en revisión, evidencia resuelta, SHA ligado a ejecución `SUCCEEDED`, sin intentos activos y sin veto. El merge de #344 actualizó `docs/PRINCIPAL_AUTHORIZATION_MATRIX.md` para reflejar ese comportamiento. También establece el límite: estado API `VERIFIED` no equivale a auditoría/aceptación independiente GOV-REV-001 ni autoriza promoción, merge o efectos externos; tampoco prueba por sí solo verdad o autoría de la evidencia. Aun tras renovar grants sigue faltando un candidato `VERIFIED` para el ensayo W2.

No incluir tokens, DSNs, claves privadas ni digests en este documento. Re-verificar mediante preflight por cuenta y consultas de solo metadatos antes de una operación real.

## 5. Acciones necesarias para avanzar

### No se requiere acción inmediata del CEO para continuar el trabajo técnico

La coordinación de #322 quedó cerrada; al corte siguen abiertos en draft #341 (rotación publisher W2), #342 (este informe) y #343 (preflight de límites DB runtime). El siguiente avance es validar el límite de entrega de credenciales de #341 y los gates de integración seguros/autorizados. No se ha demostrado todavía autonomía plena ni aceptación del piloto.

### Decisiones que sí requieren al CEO

1. **Activar el servicio PM**: decisión separada. Antes de habilitarlo, verificar rol runtime, configuración, aprobación de revisión congelada y plan de parada/rollback. No hay evidencia de activación.
2. **Delegar emisión/rotación de publishers W2**: el diseño #326 describe que la API actual no permite autorrotación W2 sin capacidad adicional. No se ha concedido `credential.issue_publisher`; hace falta decisión explícita sobre límite de grants, caducidad y principal emisor antes de implementarla.
3. **Activación de proveedores o integrador**: permanece gate estratégico y fuera de este informe; código fusionado no los activa.

No se pide al CEO que ejecute comandos host en este momento. Si el siguiente gate exige una acción física o credencial que no pueda ejecutarse con identidad de servicio autorizada, se detallará el comando exacto, impacto, verificación y reversión antes de solicitarla.

## 6. Próximos pasos recomendados

1. Reconciliar `HANDOVER_ACCEPTANCE_MATRIX.md` con `main` `eca67626`; el snapshot existente observa `f8f650d` y es obsoleto para el estado de CI/PR actual. Mantener separados “implementado”, “desplegado”, “ejercitado”, “auditado” y “aceptado”.
2. Revalidar preflight sobre el `main` actual, por separado bajo `aao-pm` y `aao-impl-codex`; comprobar únicamente metadatos de credenciales, nunca leerlas.
3. Identificar, mediante lectura autorizada de la BD, si existe candidato VERIFIED y SHA aprobado. La última búsqueda reportó cero; no crear ni cambiar estados para fabricar un candidato. Este sigue siendo un bloqueo del ensayo W2.
4. Reconciliar los roles de DB/host de #327 con el despliegue real y probarlos en entorno desechable antes de aplicar grants al host.
5. Cerrar los pendientes operativos de #318 (trust por repo/forks, backoff, operación de cuarentena y prueba real) antes de afirmar que el relay aporta disponibilidad.
6. Ejecutar el piloto integrado §14 únicamente cuando exista candidato elegible y evidencia previa de identidades, App scopes, runtime y protección.
7. Solicitar auditoría final independiente GOV-REV-001 contra un SHA único; después el CEO dispone la aceptación formal.

## 7. Fuentes y límites

- Git: `git rev-parse origin/main` = `eca67626e77a8c734230f9a431d5f0b77b177fde`; #344 muestra estado MERGED y ese merge commit. El worktree de este PR se mantiene separado y no cambia `main`.
- GitHub: `gh pr list --state open -R autoaiorg/aao --json number,title,isDraft,headRefOid,url` muestra #341 (`f7e414a`), #342 (`40d4d5b`) y #343 (`d8d9181`), todos draft. #341 y #343 tenían `test`, `frontend` y `push-relay-worker` SUCCESS en ambos runs consultados. `gh run list --branch main -R autoaiorg/aao --limit 3`: run `41528081990` sobre `eca67626` seguía IN PROGRESS; `push-relay-worker` SUCCESS y `test`/`frontend` en curso.
- Host/DB: `docker ps --filter name=aao-postgres-1` informó `Up 5 hours (healthy)`. La consulta PostgreSQL anterior se ejecutó en transacción `BEGIN READ ONLY ... ROLLBACK`; observó DONE=3 con APPROVE=3, IN_REVIEW=2 con APPROVE=0, INBOX=1, IN_PROGRESS=1; los dos grants `work.review` consultados estaban expirados. No se alteraron DB ni servicios.
- #343: el PR describe la retirada de `PUBLIC TEMP` y la verificación `aao_runtime TEMP=false`; CI está verde en sus dos runs consultados. La auditoría independiente se reportó como APPROVE WITH NITS, con ajuste de wording en el head actual; no sustituye aceptación ni acredita límites completos runtime.
- #344: merge `eca67626` actualiza la matriz para hacer explícito que `VERIFIED` de API no equivale a aceptación independiente GOV-REV-001 ni autoriza promoción/merge/efectos externos.
- Issue #322: `gh issue view 322 -R autoaiorg/aao --json state,title,updatedAt,url`, CLOSED, actualizado `2026-11-02T18:23:23Z`.
- Gates: `docs/HANDOVER_ACCEPTANCE_MATRIX.md`; debe actualizarse para el estado post-merge.
- Este informe no ejecutó pruebas ni operaciones que cambien host/DB; sí ejecutó una consulta read-only dentro de una transacción de solo lectura. No confirma vigencia de tokens, despliegue, privilegios completos runtime, activación de servicios ni aceptación final. Al corte hay 0 ítems `VERIFIED` en el proyecto y 0 `APPROVE` en los dos ítems `IN_REVIEW`; los grants no se renovaron.
