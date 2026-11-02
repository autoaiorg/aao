# Estado actual de AAO

**Corte:** 2026-11-02 21:15 UTC. **Revisión:** `197e69720c378748ac06431b051ec123258faf71` (`main` = `origin/main`). Este informe es un estado de coordinación, no una certificación de autonomía, despliegue o aceptación.

## 1. Evidencia de repositorio

| Hecho | Estado | Evidencia |
|---|---|---|
| HEAD de `main` | `197e69720c378748ac06431b051ec123258faf71` | `git rev-parse HEAD origin/main`; checkout limpio al corte |
| CI post-merge de `main` | SUCCESS | Run `41510891908`, sobre el SHA exacto de `main`; jobs `test`, `frontend`, `push-relay-worker` |
| PRs abiertos | #341, #342 y #343, todos draft | `gh pr list --state open -R autoaiorg/aao`; #341 head `de5da2b6b1c79d511ada3611fdc0f5c90c92478b`; #342 actualiza este informe; #343 head `d8d918101d3d4badf51f95ace7ad2086e399f0eb` |
| #343 preflight de límites DB runtime | OPEN, draft; CI en curso | El head `d8d9181` añade comprobaciones read-only de privilegios de conexión/esquema; no acredita el conjunto completo de privilegios runtime ni el despliegue |
| #327 bootstrap/migraciones | MERGED | PR #327, merge commit `1770974c60be729c9de95b537ed0eb4fb08ed0c7` |
| #318 push relay | MERGED, opt-in; no acredita despliegue | PR #318, head `8d749e9de2f0ff2071fafdc470b25cd7d9e74f0c`; revisión independiente previa APPROVE WITH NITS |
| #329 espejo/integrador vs git 2.56 | MERGED | PR #329, head `526f62ab58510a5f6d4c46ca94fb8767b20d1534`; revisión independiente previa APPROVE WITH NITS |
| #331 autorrotación PM de dos fases | MERGED | PR #331, merge en el HEAD actual; reauditoría independiente condicional y CI verde según el comentario de cierre de #322 |
| #251 y #330 | CLOSED, ramas/historial conservados | Verificación y comentario de cierre en issue #322 |
| #299, #325 y #321 | CLOSED/sustituidos o integrados | #299 sustituido por #327; #325 cerrado como contenido en #327; #321 cerrado al integrarse B2 en #324 |

Las fusiones y CI no equivalen a aceptación del piloto. La lista y estados se comprobaron en GitHub el 2026-11-02 21:14 UTC; el estado remoto puede cambiar después del corte. Issue #322 está CLOSED (actualizado 18:23:23 UTC); su cierre administrativo no cierra los gates de aceptación.

## 2. Gates de aceptación del proyecto

La referencia de gates sigue siendo `docs/HANDOVER_ACCEPTANCE_MATRIX.md`, criterios 1–10 y E-1/E-2. **No hay evidencia suficiente aquí para marcar ninguno como cerrado ni para declarar AAO plenamente autónomo.** La matriz contiene material histórico y debe reconciliarse con el estado actual antes de usarla como certificación.

| Área | Estado para aceptación | Qué falta demostrar |
|---|---|---|
| Candidato y SHA aceptado | ABIERTO | Candidato identificable, aprobado y verificado en la revisión exacta |
| Revisión de trabajo elegible | BLOQUEADO | La consulta actual informa que los grants `work.review` de ambos auditores están expirados; además, la última búsqueda informó 0 candidatos VERIFIED. El endpoint admite APPROVE bajo sus precondiciones, pero no hay grant activo ni candidato elegible demostrado |
| Raíz de confianza y protección del canónico | ABIERTO | Evidencia sobre el candidato; reglas finales y efectivas de protección |
| Identidades, privilegios y host | ABIERTO | Ejercicio real de roles y límites efectivos en el host/BD destino |
| Candidato W2 | ABIERTO / BLOQUEADO | Última consulta de solo lectura reportó 0 ítems VERIFIED elegibles; hace falta una cadena de aprobación/evidencia sobre SHA exacto, sin fabricar estados |
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

Actualización operativa del 2026-11-02 (reportada por el operador y reflejada en el body de #343): en `aao_dev` se retiró el privilegio TEMPORARY de `PUBLIC`; se comprobó `aao_runtime CONNECT=true`, `TEMP=false`, `aao_dev TEMP=true` y ausencia de `PUBLIC CREATE/TEMP`. Esto es evidencia de una frontera de privilegios concreta en la base de desarrollo, no acredita el resto de privilegios de tablas, la autenticación runtime, `db:runtime-complete`, el host destino ni el piloto. El auditor independiente reportó APPROVE WITH NITS para #343; el nit de redacción se corrigió en el head `d8d9181`. A la hora del corte, los seis checks observados en los dos runs de PR estaban `in_progress` o `queued`; por tanto, CI aún no estaba verde.

**Bloqueo actual del reviewer (consulta operativa del coordinador, 2026-11-02 21:15 UTC):** `principal_credentials` junto a `project_grants` muestra que los dos principals `aao-auditor-*` tienen su grant `work.review` expirado (2026-10-25 y 2026-10-26). Eso explica el rechazo actual por falta de grant vigente. No se renovó ningún grant. La consulta no secreta para reproducir la comprobación es:

```sql
SELECT p.name, c.enabled, g.capability, g.expires_at,
       (g.expires_at IS NOT NULL AND g.expires_at <= clock_timestamp()) AS expired
FROM principal_credentials c
JOIN principals p ON p.id::text = c.principal_id
JOIN project_grants g ON g.principal_id = p.id
WHERE p.name LIKE 'aao-auditor-%' AND g.capability = 'work.review'
ORDER BY p.name;
```

La fuente de esta evidencia es la comprobación live informada por el coordinador; esta actualización documental no ejecutó la consulta. Renovar dichos grants requiere una operación autorizada del CEO/principal delegado; no se ha ejecutado ni se presume autorizado aquí. En `main` `197e697`, `POST /v1/work/{id}/reviews` pasa por `require_reviewer` y `require_grant(..., "work.review")`; permite `APPROVE` si el proyecto está ACTIVE, el trabajo IN_REVIEW, reviewer distinto del autor y de workers ejecutores, evidencia resuelta, SHA ligado a una ejecución SUCCEEDED, sin intentos activos y sin veto. Por tanto, la afirmación de `docs/PRINCIPAL_AUTHORIZATION_MATRIX.md` de que APPROVE falla siempre por identidad humana/evidencia no verificada parece desactualizada respecto a la ruta actual: el endpoint ya verifica referencias de evidencia y aplica separación por identidad de principal/ejecución, aunque no prueba por sí mismo identidad humana independiente ni verdad/autoria de la evidencia. Esto no es aceptación de una revisión real. Aun tras una renovación autorizada seguiría faltando un candidato VERIFIED y SHA elegible para el ensayo W2.

No incluir tokens, DSNs, claves privadas ni digests en este documento. Re-verificar mediante preflight por cuenta y consultas de solo metadatos antes de una operación real.

## 5. Acciones necesarias para avanzar

### No se requiere acción inmediata del CEO para continuar el trabajo técnico

La coordinación de #322 quedó cerrada y no hay una cola general de PRs: el único PR abierto es #341. El siguiente avance es corregir y auditar el límite de entrega de credenciales, actualizar la matriz con evidencia actual, y ejecutar los gates de integración seguros/autorizados. No se ha demostrado todavía autonomía plena ni aceptación del piloto.

### Decisiones que sí requieren al CEO

1. **Activar el servicio PM**: decisión separada. Antes de habilitarlo, verificar rol runtime, configuración, aprobación de revisión congelada y plan de parada/rollback. No hay evidencia de activación.
2. **Delegar emisión/rotación de publishers W2**: el diseño #326 describe que la API actual no permite autorrotación W2 sin capacidad adicional. No se ha concedido `credential.issue_publisher`; hace falta decisión explícita sobre límite de grants, caducidad y principal emisor antes de implementarla.
3. **Activación de proveedores o integrador**: permanece gate estratégico y fuera de este informe; código fusionado no los activa.

No se pide al CEO que ejecute comandos host en este momento. Si el siguiente gate exige una acción física o credencial que no pueda ejecutarse con identidad de servicio autorizada, se detallará el comando exacto, impacto, verificación y reversión antes de solicitarla.

## 6. Próximos pasos recomendados

1. Reconciliar `HANDOVER_ACCEPTANCE_MATRIX.md` con `main` `197e697`; el snapshot existente observa `f8f650d` y es obsoleto para el estado de CI/PR actual. Mantener separados “implementado”, “desplegado”, “ejercitado”, “auditado” y “aceptado”.
2. Revalidar preflight sobre el `main` actual, por separado bajo `aao-pm` y `aao-impl-codex`; comprobar únicamente metadatos de credenciales, nunca leerlas.
3. Identificar, mediante lectura autorizada de la BD, si existe candidato VERIFIED y SHA aprobado. La última búsqueda reportó cero; no crear ni cambiar estados para fabricar un candidato. Este sigue siendo un bloqueo del ensayo W2.
4. Reconciliar los roles de DB/host de #327 con el despliegue real y probarlos en entorno desechable antes de aplicar grants al host.
5. Cerrar los pendientes operativos de #318 (trust por repo/forks, backoff, operación de cuarentena y prueba real) antes de afirmar que el relay aporta disponibilidad.
6. Ejecutar el piloto integrado §14 únicamente cuando exista candidato elegible y evidencia previa de identidades, App scopes, runtime y protección.
7. Solicitar auditoría final independiente GOV-REV-001 contra un SHA único; después el CEO dispone la aceptación formal.

## 7. Fuentes y límites

- Git: `git rev-parse HEAD origin/main`, ambos `197e69720c378748ac06431b051ec123258faf71`; árbol limpio al corte.
- GitHub: `gh pr list --state open -R autoaiorg/aao`; #341, #342 y #343 draft. `gh run list --branch main -R autoaiorg/aao --limit 3`; run `41510891908` SUCCESS sobre el HEAD actual. `gh api repos/autoaiorg/aao/commits/d8d918101d3d4badf51f95ace7ad2086e399f0eb/check-runs`: seis checks de PR en `in_progress`/`queued` al corte.
- #343: descripción del PR y actualización operativa del coordinador reportan retirada de `PUBLIC TEMP` y verificación de `aao_runtime TEMP=false`; el PR sigue en borrador. La reauditoría se reportó como APPROVE WITH NITS, con ajuste de wording en el head actual; no sustituye aceptación ni CI.
- Issue #322: `gh issue view 322 -R autoaiorg/aao --json state,title,updatedAt,url`, CLOSED, actualizado `2026-11-02T18:23:23Z`.
- Gates: `docs/HANDOVER_ACCEPTANCE_MATRIX.md`; debe actualizarse para el estado post-merge.
- Esta actualización no ejecutó pruebas, consultas a la BD ni operaciones del host. La evidencia de `aao_dev` y de grants expirados se atribuye a la comprobación live del coordinador, no a una consulta independiente de este informe. No confirma vigencia de tokens, despliegue, privilegios completos runtime, estado actual de servicios ni aceptación final. El candidato W2 sigue sin estar identificado y reportado como VERIFIED; los grants no se renovaron.
