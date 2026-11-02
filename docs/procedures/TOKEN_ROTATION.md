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
2. **Publicadores W2:** la herramienta `scripts/rotate_w2_publisher_token.py` de la rama `feat/w2-scoped-issuer` solo rota un principal publisher W2 ya existente; no crea ni emite nuevos principales publisher. La emisión inicial sigue en `scripts/provision_w2_publishers.py`, como acción separada autorizada por CEO. La ruta de rotación limita la identidad existente a los dos roles W2, el proyecto activo AAO — Self Development, `project.read` + `code.publish` y ocho horas como máximo; no crea ni amplía autoridad. El texto histórico de la propuesta de emisión delegada no describe esta implementación.

La rotación W2 es de dos fases: el token vigente conserva validez mientras se guarda uno pendiente; el helper lo persiste localmente y confirma indicando el ID exacto esperado. La API rechaza la confirmación si el token pendiente pertenece a otro principal. Después el helper reemplaza el fichero activo. La recuperación valida el principal exacto, la cuenta Linux, el proyecto único y el conjunto exacto de grants antes de instalarlo. Una respuesta perdida no crea un principal nuevo.

La recuperación local también cubre ambos cortes de escritura: el sidecar de identidad se persiste antes que el bearer pendiente, de modo que un sidecar huérfano (sin bearer pendiente) se puede eliminar tras validar su propietario y modo; si ya existe un bearer pendiente pero falta el sidecar, el helper solo reconstruye el ID esperado autenticando el bearer activo anterior y volviendo a comprobar cuenta, proyecto y grants. Si no puede demostrar esa identidad, falla cerrado y conserva el pendiente; no adivina ni cambia de principal.

**No completa la rotación autónoma en el host**: falta el cliente periódico y el mecanismo acotado para entregar de forma segura el token al runtime privado de cada cuenta Linux. No se debe dar sudo general al servicio PM para cerrar ese hueco.

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

### B. Publicadores W2: delegación acotada en implementación

La capacidad `credential.issue_publisher` no permite grants arbitrarios: el endpoint dedicado fija las cuentas destino, el proyecto, los grants y la caducidad. El CEO conserva la decisión de conceder o retirar ese grant al coordinador. La ruta no debe fusionarse ni desplegarse sin auditoría independiente (GOV-REV-001), pruebas de integración y un diseño de entrega segura al runtime de destino.

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
