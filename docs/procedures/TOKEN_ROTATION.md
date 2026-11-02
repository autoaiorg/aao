# Rotación de tokens AAO sin token CEO — diseño (solo documento)

Estado: **diseño, no implementado**. Revisión base: `81cb877` (origin/main).
Alcance: token del coordinador PM (`scripts/provision_pm_coordinator_token.py`, principal `aao-pm-coordinator-*`, grants `project.read`, `work.coordinate`, `work.assign`) y tokens de publicadores W2 (`scripts/provision_w2_publishers.py`, principals `aao-publisher-{impl,pm}-*`, grants con caducidad de 8 h).

## Conclusión

**Hoy no existe ninguna ruta de rotación que no use el token CEO.** No se implementa `scripts/rotate_role_token.py`: implementarlo exigiría el token CEO (que es lo que se quiere eliminar) o escribir directamente en `principal_credentials` por PostgreSQL, saltándose la API, su auditoría y el control de identidad. Ninguna de las dos es aceptable (AGENTS.md, regla 6).

## Evidencia (lectura de `src/aao/work_management_api.py` en `81cb877`)

Toda escritura de credenciales o grants depende de `require_ceo`:

| Endpoint | Dependencia | Efecto |
|---|---|---|
| `POST /v1/principals/credentials` | `require_ceo` | Emite principal nuevo (409 si ya existe: «use rotation») |
| `POST /v1/principals/{id}/rotate` | `require_ceo` | Sustituye `token_digest` atómicamente; el token anterior deja de valer en el mismo commit |
| `POST /v1/principals/{id}/revoke` | `require_ceo` | `enabled=false` y escalado de trabajo asignado |
| `GET/POST /v1/projects/{id}/grants`, `DELETE …/grants/{principal}/{cap}` | `require_ceo` | Consulta/concesión/retirada de grants |

Lo único que un principal AGENT puede hacer sobre su identidad es leer: `GET /v1/principals/me` y `GET /v1/principals/me/grants` (`require_worker`). `grep "UPDATE principal_credentials\|INSERT INTO principal_credentials" src scripts` solo encuentra las tres funciones CEO anteriores.

`src/aao/identity.py` (`verify_service_token`) solo reconoce `AAO_CEO_TOKEN`, `AAO_WORK_TOKEN` y `AAO_REVIEW_TOKEN` vía entorno; ninguno de ellos tiene ruta de gestión de credenciales. No hay capacidad de proyecto (`work.assign`, `work.coordinate`, etc.) que autorice emitir, rotar o revocar credenciales ni conceder grants.

Además, `require_ceo` con cabecera `X-CEO-Token` solo funciona con `AAO_ENV` en `development`/`test` (`_ceo_bearer_enabled`), así que los emisores actuales tampoco son una ruta de producción.

## Qué falta exactamente

1. **Coordinador PM** (token sin caducidad, grants posiblemente sin caducidad): falta un endpoint de **auto-rotación** autenticado por la propia credencial AGENT vigente. Basta con esto: rotar el token no cambia grants ni identidad.
2. **Publicadores W2** (principal nuevo y grants de 8 h por ejecución): la auto-rotación **no basta**. El diseño actual crea un principal nuevo y le concede grants caducables cada vez; conceder grants es CEO-only. Falta además una de estas dos cosas (decisión reservada al CEO, ver abajo):
   - (a) una capacidad delegada y acotada de emisión, p. ej. `credential.issue_publisher`, que permita a un principal operador emitir principals `aao-publisher-*` con exactamente los grants W2 fijos y caducidad ≤ 8 h; o
   - (b) cambiar el modelo W2 a principals estables cuyo token se auto-rota y cuyos grants se renuevan por una regla fija, lo que también requiere una ruta no-CEO de renovación de grants.

## Cambio mínimo de API propuesto

### A. `POST /v1/principals/me/rotate` (cubre el coordinador PM)

- Dependencia: `require_worker` (o `require_reviewer` para AUDITOR, en endpoint gemelo).
- En una transacción: `SELECT … FROM principal_credentials WHERE principal_id=%s AND token_digest=%s AND enabled FOR UPDATE` con el digest del token presentado; si no hay fila, 403.
- Generar token nuevo, `UPDATE … SET token_digest=<nuevo>` condicionado al digest antiguo, auditar `principal.credential.self_rotated` con `principal_id` y `kind`, y devolver el token una sola vez.
- No permite cambiar `principal_id`, `kind` ni grants; no requiere migración.

Riesgo conocido de la variante sin migración: la sustitución es atómica, así que si el cliente pierde la respuesta o la instalación falla, el principal queda bloqueado y su recuperación vuelve a requerir al CEO (rotate/revoke). La variante robusta, que **sí requiere migración** (no incluida aquí; las migraciones 037/038 pertenecen a otro agente), añade `pending_token_digest` + `pending_expires_at`:

- `POST /v1/principals/me/rotate` guarda el digest nuevo como pendiente (TTL corto) y el antiguo sigue válido.
- `POST /v1/principals/me/rotate/confirm`, autenticado **con el token nuevo**, promueve el pendiente y anula el antiguo.

Así se cumple «retirar el anterior solo después de verificar el nuevo».

Riesgo de seguridad: quien robe el token puede rotarlo y dejar fuera al titular legítimo. No aumenta privilegios, pero convierte un robo en denegación de servicio; el evento auditado y el fallo de verificación del servicio legítimo lo hacen detectable. Mitigación opcional: límite de frecuencia por principal.

### B. Publicadores W2: requiere decisión CEO

Crear una capacidad que emita credenciales o conceda grants a otro principal amplía la autoridad del sistema; según AGENTS.md (regla 2) y `docs/AGENT_OPERATING_RULES.md`, no se auto-concede. Se propone al CEO la opción (a): capacidad no transferible, lista blanca fija de grants W2, caducidad ≤ 8 h forzada en servidor, cuentas destino distintas del emisor y auditoría por emisión. Hasta esa decisión, la emisión W2 sigue siendo CEO-only.

## Flujo de rotación una vez exista A (`scripts/rotate_role_token.py`, futuro)

1. Leer el token vigente del fichero instalado del rol mediante el instalador existente (nunca argv/env/stdout).
2. `POST /v1/principals/me/rotate` con ese token; comprobar que `principal_id` devuelto coincide con el esperado (fail-closed).
3. Instalar el nuevo token por stdin con el instalador (`--token pm` o el de publicadores) y verificar con `GET /v1/principals/me`.
4. Con la variante con migración: `confirm` solo tras verificar; sin ella, ante fallo en 3, escalar al CEO (el antiguo ya no vale).
5. Tests unitarios con fakes, `-W error`, ruff.

## Qué NO se hizo

- No se ejecutó nada contra host, API real ni base de datos; no se usó `sudo` ni ningún token; no se leyó `.env.local`.
- No se modificó código, migraciones, `scripts/pm_deployment_preflight.py` ni relay/transport.
- Tests y CI no constituyen auditoría independiente (GOV-REV-001).

Siguiente responsable: CEO (decidir B y aprobar A); después, propietario de la API para implementar A y el script.
