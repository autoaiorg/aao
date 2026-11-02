# Rol PostgreSQL de runtime no propietario (`aao_runtime`)

**Estado:** diseño. **Nada de este documento se ha ejecutado contra el host ni contra la base de datos real.** No añade migraciones ni cambia código. Lo validé en un PostgreSQL 16 desechable (§9), y eso no es auditoría independiente (GOV-REV-001) ni prueba la instalación real. El SQL vive solo en este documento. No debe copiarse a `db/postgres/`, que es el directorio de migraciones versionadas.

## 1. Problema

`scripts/pm_deployment_preflight.py` deja `db:runtime-role` en `UNVERIFIED` cuando no recibe `--runtime-role` y `db:runtime-complete` siempre en `UNVERIFIED`. Además, `db:inspection` queda en `UNVERIFIED` si no hay conexión local. No existe un rol PostgreSQL que el backend use en runtime y que no sea propietario ni superusuario. La fila 8 de [`HANDOVER_ACCEPTANCE_MATRIX.md`](../HANDOVER_ACCEPTANCE_MATRIX.md) y [`SUPERVISOR_PUSH_RECEIPTS.md`](SUPERVISOR_PUSH_RECEIPTS.md) exigen un rol que cumpla todo esto:

- no es propietario de objetos;
- no es superusuario ni tiene atributos elevados;
- no tiene `UPDATE`, `DELETE`, `TRUNCATE` ni DDL sobre las tablas protegidas;
- recibe `SELECT`/`INSERT` explícitos donde la migración revoca `PUBLIC` (`033_protocol_instances`, `035_project_routines`).

## 2. Identidades

| Rol | Función | Atributos | Usado por |
|---|---|---|---|
| propietario/migraciones (nombre a fijar por el administrador; aquí `<owner>`) | Propietario de la base, del esquema `public` y de todas las tablas. Aplica migraciones y ejecuta los `GRANT` de este documento | `LOGIN` solo durante migraciones, sin superusuario | Migrador y administrador. **Nunca** el API |
| `aao_runtime` | Conexión del backend en ejecución | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT`, sin pertenencias | `AAO_POSTGRES_URL` del API y de los procesos que comparten esa DSN (§6) |

**Conflicto con el PR abierto #325.** Su `scripts/bootstrap/init_postgres.sh` crea `aao_app`, lo hace propietario de `aao_prod` (`createdb -O aao_app`) y le concede `GRANT ALL`. Con este diseño, `aao_app` solo puede ser el rol `<owner>`. El API no puede conectarse como `aao_app`, porque `db:runtime:*` daría `MISSING` por propiedad. Decide el PM; aquí no se edita #325.

## 3. Creación (una sola vez)

### 3.1 Rol — administrador PostgreSQL (superusuario o `CREATEROLE`)

```sql
-- Paso 1 (administrador PostgreSQL con CREATEROLE o superusuario), una sola vez.
-- Sin PASSWORD: la contraseña se fija fuera de banda (ver §3.2) o se usa peer.
CREATE ROLE aao_runtime
  LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  NOINHERIT
  CONNECTION LIMIT 20;
```

### 3.2 Credencial, siempre fuera de banda

Este archivo no contiene ninguna contraseña. Hay dos opciones:

- **Preferida: autenticación `peer` por socket Unix.** Se añade una línea en `pg_hba.conf` (`local <db> aao_runtime peer map=aao`) y en `pg_ident.conf` se mapea el usuario Linux del servicio API a `aao_runtime`. No hay secreto. La DSN queda así: `postgresql:///<db>?host=/var/run/postgresql&user=aao_runtime`. El preflight ya acepta host de socket.
- **Alternativa: contraseña.** El administrador ejecuta `\password aao_runtime` en un `psql` interactivo, que cifra la contraseña en el cliente y no la deja en el historial ni en `pg_stat_statements`. La guarda en el fichero de secretos del servicio (propietario el usuario del servicio, modo `0600`). Nunca va en el repositorio, ni en tickets ni en logs.

### 3.3 Base de datos y esquema — `<owner>`, conectado a la base de AAO

```sql
-- Paso 2 (propietario de la base de datos), conectado a la base de AAO.
BEGIN;
DO $$
BEGIN
  EXECUTE format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO aao_runtime', current_database());
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO aao_runtime;
COMMIT;
```

### 3.4 Grants — `<owner>` (propietario de las tablas)

El bloque es idempotente. Primero retira todo lo concedido a `aao_runtime` y a `PUBLIC` en las tablas de `public` y después concede la matriz exacta. Se vuelve a ejecutar completo después de cada migración (§8).

```sql
-- Paso 3 (propietario de las tablas = rol de migraciones). Idempotente:
-- primero retira todo lo concedido al rol y vuelve a conceder la matriz exacta.
BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aao_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;

-- A. Solo lectura.
GRANT SELECT ON TABLE schema_migrations TO aao_runtime;

-- B. Append-only: solo SELECT + INSERT.
GRANT SELECT, INSERT ON TABLE
  events,
  execution_journal,
  patch_proposals,
  patch_proposal_validations,
  work_item_dependencies,
  work_group_partial_reports,
  protocol_instances,
  routine_occurrences
TO aao_runtime;

-- C. Append-only con lecturas bloqueantes (SELECT ... FOR SHARE/UPDATE).
--    PostgreSQL exige UPDATE en al menos una columna para bloquear filas;
--    se concede solo sobre created_at. reviews/evidence_artifacts además
--    tienen trigger append-only que rechaza cualquier UPDATE.
GRANT SELECT, INSERT ON TABLE
  reviews,
  evidence_artifacts,
  capability_versions,
  work_groups,
  work_group_consolidations
TO aao_runtime;
GRANT UPDATE (created_at) ON TABLE
  reviews,
  evidence_artifacts,
  capability_versions,
  work_groups,
  work_group_consolidations
TO aao_runtime;

-- D. Estado mutable: SELECT + INSERT + UPDATE, sin DELETE.
GRANT SELECT, INSERT, UPDATE ON TABLE
  mandates,
  projects,
  work_items,
  execution_queue,
  external_effects,
  principal_credentials,
  organization_units,
  organization_profiles,
  project_conversations,
  project_conversation_messages,
  project_conversation_turns,
  work_item_assignments,
  capability_feedback_proposals,
  project_routines
TO aao_runtime;

-- E. Únicas tablas con DELETE en runtime.
GRANT SELECT, INSERT, DELETE ON TABLE project_grants TO aao_runtime;
GRANT UPDATE (expires_at) ON TABLE project_grants TO aao_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ceo_browser_sessions TO aao_runtime;

-- F. Sin acceso: principals (tabla 001 sin uso en src/aao).
COMMIT;
```

Recuento medido en la base desechable (V9): **76 privilegios de tabla y 6 de columna (82 en total)**, sobre **30 tablas**. `principals` queda sin acceso. Hay además `CONNECT` sobre la base y `USAGE` sobre `public`.

## 4. Matriz derivada del código

Fuente: cadenas SQL de `src/aao/*.py` en `81cb877`. Quedan excluidos `sqlite_api.py`, `sqlite_storage.py` y `execution.py`, que son de SQLite. Uso los literales extraídos con `ast` y cuento las sentencias por tabla y verbo. También revisé `scripts/self_development_cycle.py` (solo `SELECT` en work_items, execution_queue, reviews, events, evidence_artifacts, patch_proposals y principal_credentials) y `scripts/pm_deployment_preflight.py` (solo `SELECT`). Ningún SQL usa nombres de tabla dinámicos, `TRUNCATE`, `LOCK TABLE`, tablas temporales, secuencias ni DDL. `pg_advisory_xact_lock` es ejecutable por `PUBLIC` por defecto.

| Tabla | S | I | U | D | `FOR SHARE/UPDATE` | Append-only | Grant |
|---|---|---|---|---|---|---|---|
| schema_migrations | ✓ | | | | | — | S |
| mandates | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| projects | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| principals | | | | | | — (sin uso) | ninguno |
| project_grants | ✓ | ✓ | | ✓ | ✓ | no | S I D + U(expires_at) |
| work_items | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| reviews | ✓ | ✓ | | | ✓ | **trigger** (011) | S I + U(created_at) |
| events | ✓ | ✓ | | | | por diseño | S I |
| execution_queue | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| execution_journal | ✓ | ✓ | | | | por diseño | S I |
| external_effects | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| principal_credentials | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| evidence_artifacts | ✓ | ✓ | | | ✓ | **trigger** (008/009) | S I + U(created_at) |
| capability_versions | ✓ | ✓ | | | ✓ | por diseño (versiones inmutables) | S I + U(created_at) |
| patch_proposals | ✓ | ✓ | | | solo `OF w` | **trigger** (012) | S I |
| patch_proposal_validations | ✓ | ✓ | | | | **trigger** (012) | S I |
| organization_units | ✓ | ✓ | upsert | | | no | S I U |
| organization_profiles | ✓ | ✓ | upsert | | ✓ | no | S I U |
| project_conversations | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| project_conversation_messages | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| ceo_browser_sessions | ✓ | ✓ | ✓ | ✓ (caducadas) | ✓ | no | S I U D |
| project_conversation_turns | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| work_groups | ✓ | ✓ | | | ✓ | por diseño | S I + U(created_at) |
| work_item_dependencies | ✓ | ✓ | | | | por diseño | S I |
| work_item_assignments | ✓ | ✓ | upsert | | ✓ | no | S I U |
| work_group_consolidations | ✓ | ✓ | | | ✓ | por diseño | S I + U(created_at) |
| work_group_partial_reports | ✓ | ✓ | | | | por diseño | S I |
| capability_feedback_proposals | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| protocol_instances | ✓ | ✓ | | | | por diseño (033) | S I |
| project_routines | ✓ | ✓ | ✓ | | ✓ | no | S I U |
| routine_occurrences | ✓\* | ✓ | | | | por diseño | S I |

\* `routine_occurrences` solo recibe `INSERT` en el código. Se le da `SELECT` porque `db:runtime:routine_occurrences` del preflight lo exige.

`DELETE` existe solo en dos sitios: la revocación de grants por el CEO (`work_management_api.py:1503`) y la purga de sesiones CEO caducadas más de 30 días (`:641`). Los `ON DELETE CASCADE` de las FK se ejecutan con los permisos del propietario, así que no requieren `DELETE` del runtime. Los triggers (`enforce_capability_version_creator`, append-only) se ejecutan como invocador y solo leen tablas donde `aao_runtime` ya tiene `SELECT`.

### 4.1 Por qué hay `UPDATE` de columna en tablas append-only

PostgreSQL 16 exige `UPDATE` en al menos una columna de cada tabla bloqueada con `SELECT ... FOR SHARE/UPDATE`. Lo comprobé en la base desechable: al revocar `UPDATE(created_at)` en `reviews` o `work_groups`, o `UPDATE(expires_at)` en `project_grants`, el `SELECT ... FOR SHARE/UPDATE` del código falla con `permission denied`. El código bloquea así `reviews` (`work_management_api.py:2029`), `evidence_artifacts` (`evidence_registry.py:110,160`), `capability_versions` (`execution_queue.py:80`, `work_management_api.py:3613,4461,4581`), `work_groups` (`:2219,2364,2467,2554`), `work_group_consolidations` (`:2281`) y `project_grants` (unas 20 lecturas `FOR SHARE` que serializan con la revocación).

Consecuencias, por clase de tabla:

- **`reviews` y `evidence_artifacts`.** Sus triggers `BEFORE UPDATE` rechazan cualquier `UPDATE`. `aao_runtime` no puede desactivarlos (`ALTER TABLE ... DISABLE TRIGGER` exige ser propietario; lo probé y devuelve `must be owner`). En la práctica siguen siendo append-only.
- **`capability_versions`, `work_groups` y `work_group_consolidations`.** Son append-only solo por convención. `aao_runtime` **puede reescribir `created_at`**. Es un riesgo residual: puede falsificar una marca temporal, pero no el contenido. Siguiente acción para el owner del backend: una migración con trigger `BEFORE UPDATE` como los de 011/012, o quitar el bloqueo de filas de esas lecturas.
- **`project_grants`.** Todas sus columnas confieren autoridad. `UPDATE(expires_at)` no añade poder a nivel de base sobre el `INSERT`/`DELETE` que el runtime ya necesita para emitir y revocar grants. La frontera de autoridad de los grants es el API (CEO), no el rol de base de datos.
- **`has_table_privilege(..., 'UPDATE')` no ve los grants de columna.** Devuelve `f` en estas tablas aunque exista `UPDATE` de columna. Por eso V5 y V6 usan además `has_any_column_privilege` e `information_schema.column_privileges`.

## 5. Verificación (solo lectura; puede ejecutarla `aao_runtime` o el administrador)

```sql
-- V1. Atributos del rol: todo f salvo rolcanlogin = t.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication,
       rolbypassrls, rolinherit, rolcanlogin
FROM pg_roles WHERE rolname = 'aao_runtime';

-- V2. Pertenencias: 0 filas (ni rol propietario, ni pg_write_all_data, etc.).
SELECT r.rolname AS member_of
FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
WHERE m.member = 'aao_runtime'::regrole;

-- V3. Propiedad: 0 filas. Incluye propiedad indirecta vía pertenencia.
SELECT 'table' AS kind, c.relname AS name
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND pg_has_role('aao_runtime', c.relowner, 'USAGE')
UNION ALL
SELECT 'schema', nspname FROM pg_namespace
WHERE pg_has_role('aao_runtime', nspowner, 'USAGE')
UNION ALL
SELECT 'function', p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND pg_has_role('aao_runtime', p.proowner, 'USAGE')
UNION ALL
SELECT 'database', datname FROM pg_database
WHERE pg_has_role('aao_runtime', datdba, 'USAGE');

-- V4. Sin DDL ni temporales: todo f.
SELECT has_schema_privilege('aao_runtime', 'public', 'CREATE')                AS schema_create,
       has_database_privilege('aao_runtime', current_database(), 'CREATE')    AS db_create,
       has_database_privilege('aao_runtime', current_database(), 'TEMPORARY') AS db_temp;

-- V5. Tablas append-only: sin UPDATE/DELETE/TRUNCATE a nivel tabla, y la
--     única UPDATE de columna permitida es created_at donde se necesita bloqueo.
SELECT t AS table_name,
       has_table_privilege('aao_runtime', 'public.' || t, 'UPDATE')        AS tbl_update,
       has_table_privilege('aao_runtime', 'public.' || t, 'DELETE')        AS tbl_delete,
       has_table_privilege('aao_runtime', 'public.' || t, 'TRUNCATE')      AS tbl_truncate,
       has_table_privilege('aao_runtime', 'public.' || t, 'REFERENCES')    AS tbl_references,
       has_table_privilege('aao_runtime', 'public.' || t, 'TRIGGER')       AS tbl_trigger,
       has_any_column_privilege('aao_runtime', 'public.' || t, 'UPDATE')   AS any_col_update
FROM unnest(ARRAY[
  'events', 'execution_journal', 'patch_proposals', 'patch_proposal_validations',
  'work_item_dependencies', 'work_group_partial_reports', 'protocol_instances',
  'routine_occurrences', 'reviews', 'evidence_artifacts', 'capability_versions',
  'work_groups', 'work_group_consolidations'
]) AS t
ORDER BY 1;
-- Esperado: tbl_* = f en todas; any_col_update = t solo en reviews,
-- evidence_artifacts, capability_versions, work_groups, work_group_consolidations.

-- V6. Privilegios solo de columna: exactamente 6 filas UPDATE
--     (created_at en las 5 tablas de bloqueo, expires_at en project_grants).
SELECT p.table_name, p.column_name, p.privilege_type
FROM information_schema.column_privileges p
WHERE p.grantee = 'aao_runtime' AND p.table_schema = 'public'
  AND NOT EXISTS (SELECT 1 FROM information_schema.role_table_grants g
                  WHERE g.grantee = p.grantee AND g.table_schema = p.table_schema
                    AND g.table_name = p.table_name AND g.privilege_type = p.privilege_type)
ORDER BY 1, 2;

-- V7. PUBLIC sin DML en ninguna tabla de public: 0 filas.
SELECT c.relname, a.privilege_type
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
     aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.grantee = 0;

-- V8. Deriva contra la matriz aprobada: 0 filas.
--     'missing' = falta un grant aprobado; 'extra' = privilegio no aprobado;
--     'unclassified' = tabla nueva (p. ej. 036/037/038) sin decisión explícita.
WITH expected(table_name, privilege_type) AS (
  SELECT t, p FROM unnest(ARRAY['schema_migrations']) t, unnest(ARRAY['SELECT']) p
  UNION ALL
  SELECT t, p FROM unnest(ARRAY[
    'events', 'execution_journal', 'patch_proposals', 'patch_proposal_validations',
    'work_item_dependencies', 'work_group_partial_reports', 'protocol_instances',
    'routine_occurrences', 'reviews', 'evidence_artifacts', 'capability_versions',
    'work_groups', 'work_group_consolidations']) t, unnest(ARRAY['SELECT', 'INSERT']) p
  UNION ALL
  SELECT t, p FROM unnest(ARRAY[
    'mandates', 'projects', 'work_items', 'execution_queue', 'external_effects',
    'principal_credentials', 'organization_units', 'organization_profiles',
    'project_conversations', 'project_conversation_messages',
    'project_conversation_turns', 'work_item_assignments',
    'capability_feedback_proposals', 'project_routines']) t,
    unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
  UNION ALL
  SELECT 'project_grants', p FROM unnest(ARRAY['SELECT', 'INSERT', 'DELETE']) p
  UNION ALL
  SELECT 'ceo_browser_sessions', p FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p
),
no_access(table_name) AS (VALUES ('principals')),
actual AS (
  SELECT table_name::text, privilege_type::text
  FROM information_schema.role_table_grants
  WHERE grantee = 'aao_runtime' AND table_schema = 'public'
)
SELECT 'missing' AS problem, e.* FROM expected e EXCEPT SELECT 'missing', a.* FROM actual a
UNION ALL
(SELECT 'extra', a.* FROM actual a EXCEPT SELECT 'extra', e.* FROM expected e)
UNION ALL
SELECT 'unclassified', c.relname::text, NULL
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
  AND c.relname NOT IN (SELECT table_name FROM expected)
  AND c.relname NOT IN (SELECT table_name FROM no_access)
ORDER BY 1, 2, 3;

-- V9. Recuento (informativo): 76 privilegios de tabla, 6 de columna.
SELECT (SELECT count(*) FROM information_schema.role_table_grants
         WHERE grantee = 'aao_runtime' AND table_schema = 'public') AS table_level,
       (SELECT count(*) FROM information_schema.column_privileges p
         WHERE grantee = 'aao_runtime' AND table_schema = 'public'
           AND NOT EXISTS (SELECT 1 FROM information_schema.role_table_grants g
                           WHERE g.grantee = p.grantee AND g.table_name = p.table_name
                             AND g.privilege_type = p.privilege_type)) AS column_level;
```

Resultado en la base desechable con 001–035: V1 da `f` en todo salvo `rolcanlogin=t`. V2, V3, V7 y V8 devuelven 0 filas. V4 da todo `f`. V5 y V6 coinciden con lo esperado y V9 da `76 | 6`.

Opcionalmente se puede añadir un sondeo negativo en sesión `aao_runtime`. Cada sentencia debe fallar con `permission denied` o `must be owner`, y después se ejecuta `ROLLBACK`: `TRUNCATE protocol_instances`, `UPDATE protocol_instances SET started_by='x' WHERE false`, `DELETE FROM events WHERE false`, `CREATE TABLE x(i int)`, `CREATE TEMP TABLE y(i int)`, `SELECT 1 FROM principals` y `ALTER TABLE reviews DISABLE TRIGGER reviews_append_only`.

## 6. Cómo debe consumirlo el preflight (descripción; el preflight no se modifica)

1. El backend usa una DSN local con `user=aao_runtime`, por socket Unix o loopback, porque `local_connection_options` rechaza destinos remotos y `service`. La conexión de inspección de `pm_deployment_preflight.py` es la misma DSN normal del backend (`database_url()`), así que `db:inspection-connection` debe informar `superuser=False`.
2. Se ejecuta `scripts/pm_deployment_preflight.py --runtime-role aao_runtime --principal-id <pm>`. Todas las consultas de `database_checks` y `runtime_checks` son lecturas de catálogo o `SELECT` sobre tablas con grant (`schema_migrations`, `mandates`, `projects`, `principal_credentials`, `project_grants`), así que `aao_runtime` puede ejecutarlas.
3. Resultado esperado. Lo comprobé invocando `runtime_checks(db, "aao_runtime")` contra la base desechable:
   - `db:runtime-role` → `PASS`
   - `db:runtime:protocol_instances` → `PASS`
   - `db:runtime:project_routines` → `PASS`
   - `db:runtime:routine_occurrences` → `PASS`
   - `db:runtime-complete` → `UNVERIFIED`, por diseño, porque el preflight solo cubre 033/035.
4. **Para cerrar `db:runtime-complete`**, el administrador ejecuta V1–V9 de §5 y adjunta la salida (sin DSN) como evidencia. Una mejora posterior del preflight, que no se hace aquí, sería incorporar V2, V3, V4, V6 y V8. Hoy el preflight usa solo `has_table_privilege`, que no ve los `UPDATE` de columna (§4.1). Su comprobación «sin UPDATE» en `protocol_instances` es correcta porque esa tabla no tiene grant de columna.

**Alcance de procesos.** El coordinador PM (`scripts/run_project_coordinator.py`) solo habla HTTP con el API (`urllib`; no importa `psycopg`), así que no necesita rol de base de datos. El API, el worker inerte, la recuperación de turnos, el publisher W2 (`pr_publisher.py`) y `self_development_cycle.py` comparten `AAO_POSTGRES_URL`. La matriz cubre la unión de sus sentencias.

## 7. Revocación / retirada

Un administrador:

1. ejecuta `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aao_runtime;`
2. revoca `CONNECT` de la base y `USAGE` de `public`;
3. ejecuta `DROP ROLE aao_runtime;`.

`DROP OWNED` no hace falta, porque el rol no posee nada (V3).

## 8. Migraciones nuevas (036 de #325, futuras 037/038)

Los grants no van dentro de las migraciones. CI aplica las migraciones como `aao_test`, y ahí `aao_runtime` no existe, así que un `GRANT ... TO aao_runtime` rompería CI. Siguiendo el patrón de 033/035/036, cada migración que cree una tabla hace `REVOKE ALL ... FROM PUBLIC` y no concede nada.

Procedimiento obligatorio para cada migración que añada tablas:

1. El autor de la migración clasifica cada tabla nueva en §4: verbos usados por `src/aao`, si hay `FOR SHARE/UPDATE` y si es append-only (y si lo es por trigger). Actualiza en el mismo PR el bloque §3.4, la lista `expected` de V8 y, si aplica, `no_access`.
2. Si la tabla es append-only y se bloquea con `FOR SHARE/UPDATE`, se añade `UPDATE` de una sola columna y se documenta en §4.1. Si no tiene trigger append-only, queda como riesgo residual.
3. Tras aplicar la migración, `<owner>` vuelve a ejecutar §3.4 completo (idempotente) y después V1–V9. Hasta que V8 devuelva 0 filas, la instalación se trata como no verificada.
4. **No usar `ALTER DEFAULT PRIVILEGES`.** Concedería DML automáticamente a tablas nuevas sin revisión. V8 hace visible cualquier tabla sin clasificar.

Caso concreto comprobado. Al aplicar en la base desechable `036_host_worker_fencing.sql` del PR #325, V8 devolvió `unclassified | host_worker_bindings`. La matriz no la incluye porque 036 no está en `main`. Según #325, los workers leen el registro y `aao-ops` lo escribe. La clasificación de esa tabla (si va en `aao_runtime` o en un rol de operador separado) queda pendiente de que #325 se fusione.

## 9. Evidencia y limitaciones

- **Revisión:** `main` `81cb877`, migraciones `001`–`035`.
- **Base desechable:** contenedor `postgres:16-alpine` (PostgreSQL 16.15) efímero y local. Las migraciones se aplicaron como rol no superusuario `aao_owner` y después se ejecutó §3.1–§3.4 dos veces (idempotencia), con autenticación `trust` solo en ese contenedor y sin credenciales reales. Las consultas V1–V9 dieron lo indicado en §5.
- **Ejercicio funcional:** ejecuté 88 tests de integración PostgreSQL (`test_durable_routines`, `test_execution_leases_integration`, `test_execution_reconciliation_integration`, `test_patch_proposals_integration`, `test_principal_credential_lifecycle_integration`, `test_project_workflow_integration` y `test_retry_diagnostics`) con `AAO_TEST_POSTGRES_URL` conectado como `aao_runtime` y `AAO_ENV=test`. Resultado: **79 passed, 9 failed**. Los 9 fallos vienen del propio fixture de test, nunca de `src/aao`:
  - `LOCK TABLE execution_journal` usado como bloqueador (6 tests);
  - `UPDATE` o `DELETE` directos para comprobar los triggers append-only (2 tests);
  - `INSERT INTO principals` (1 test).

  Con el rol de runtime, todos esos fallos son esperables y deseables.
- **No ejercitado:** el publisher W2 real (`pr_publisher.py` contra GitHub), la recuperación de turnos con proveedor real y `self_development_cycle.py` (sus `SELECT` sí están en la matriz). Tampoco `test_postgres_runtime_privileges.py` ni `test_protocol_instance_runtime_privileges.py`, que necesitan `CREATE ROLE`.
- **Hallazgo:** `tests/test_postgres_runtime_privileges.py` concede a su rol solo `SELECT, INSERT` sobre `evidence_artifacts` e inserta directamente. Con solo eso, la lectura del API vía `evidence_registry` (`FOR SHARE`) fallaría. Ese test valida la frontera de mutación, no la ruta de lectura bloqueante.
- **Pendiente:** nada de esto prueba la instalación en el host. La comprobación real la hace el administrador con §5 y el preflight (§6).
