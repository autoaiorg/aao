# Diseño propuesto: sesión CEO en navegador mediante cookie HttpOnly

**Estado:** implementación preparada en la rama `docs/ceo-cookie-session-design`; no fusionada ni habilitada en producción.
**Base de implementación:** `main` en `1e63296902a7b111597f4481099c2baf3103d8e2` (2026-10-25).
**Alcance:** mantener una sesión de navegador tras recargar la página sin persistir el bearer CEO en almacenamiento accesible a JavaScript. No convierte el token estático actual en identidad humana ni habilita producción.

## Estado de la implementación

El flujo quedó implementado en dev/test: `POST /v1/auth/ceo/session` intercambia la credencial CEO por cookie `HttpOnly`, `Secure`, `SameSite=Strict` y sesión opaca revocable de servidor (máximo 12 h); al recargar, el frontend vuelve a obtener CSRF con cookie y presenta reautenticación explícita si la sesión no existe o caducó. Mutaciones cookie-authenticated exigen CSRF y `Origin`. En producción el bootstrap y autenticación por cookie responden 503. La compatibilidad bearer se mantiene para clientes existentes dev/test.

La aplicación de cookie `Secure` en localhost HTTP se comprobó con Playwright real; no se degrada a cookie insegura. No se ejecutó la suite PostgreSQL en esta revisión porque no había URL de DB disposable disponible. Los requests que ya pasaron autenticación antes de confirmar logout pueden terminar después; los siguientes quedan revocados.

## Situación actual verificada en el código

- `frontend/app/src/auth/AuthContext.tsx` conserva `token` únicamente en React state y prohíbe explícitamente `localStorage`, `sessionStorage`, IndexedDB, cookies y URL. Logout limpia estado y rota `sessionId`.
- `frontend/app/src/data/adapters/live/HttpAaoLiveAdapter.ts` envía `X-CEO-Token` desde ese estado.
- `src/aao/work_management_api.py:35-45` compara ese header con `AAO_CEO_TOKEN` y solo lo acepta en `AAO_ENV=development|test`; no hay login de navegador, cookie de sesión ni revocación de sesión.
- La interfaz de sesión no debe confundirse con mandato constitucional, firma del CEO ni identidad productiva; la matriz de autorización mantiene producción diferida.

## Propuesta de flujo mínimo

1. **Bootstrap manual una vez por sesión:** el CEO introduce el bearer actual en el formulario existente. `POST /v1/auth/ceo/session` lo recibe en `X-CEO-Token` solo por HTTPS, aplica la misma comprobación y límites de entorno que hoy. No poner credencial en URL, cuerpo persistido, logs ni telemetry. El frontend no almacena el bearer tras respuesta exitosa y lo elimina del estado. En producción el endpoint devuelve 503 hasta que se implemente un mecanismo de identidad/autenticación de producción separado.
2. **Emitir sesión:** generar un secreto de sesión opaco de al menos 256 bits con CSPRNG. Guardar solo `SHA-256(session_secret)` (o HMAC con clave de servidor) más `created_at`, `expires_at`, `revoked_at` y metadatos mínimos en PostgreSQL. El valor en claro solo se entrega en `Set-Cookie`; nunca se registra.
3. **Cookie:** `__Host-aao_ceo_session=<opaque>; Path=/; HttpOnly; Secure; SameSite=Strict`, sin `Domain`, con duración de navegador (cookie de sesión). La tabla impone un máximo absoluto en servidor (propuesta inicial: 12 h); no hay “remember me”. Si desarrollo local no usa TLS, no degrada silenciosamente producción: elegir HTTPS local o configuración explícita dev con nombre de cookie distinto y `Secure=false`, solo loopback y solo `AAO_ENV=development`.
4. **Autorizar solicitudes:** dependency común valida hash, expiración y revocación antes de la transacción protegida. Las rutas CEO existentes aceptan sesión-cookie como principal CEO. Durante transición, `X-CEO-Token` solo queda para clientes de desarrollo existentes con compatibilidad temporal documentada; debe tener fecha de retirada y nunca ser alternativa en producción. No enviar cookies a terceros.
5. **CSRF:** exigir `Origin` exacto de la aplicación permitido por configuración en todas las solicitudes mutantes con cookie y un header no-simple `X-AAO-CSRF`. El backend genera token CSRF aleatorio vinculado a la sesión, devuelve su valor en el bootstrap y almacena/verifica hash; React lo mantiene solo en memoria. Rechazar `Origin` ausente/no permitido para mutaciones de navegador. `SameSite=Strict` es defensa adicional, no sustituto de estas comprobaciones. El token CSRF no es una credencial de autenticación.
6. **Logout/revocación:** `POST /v1/auth/ceo/logout` valida cookie + CSRF, marca solo esa sesión como revocada y responde con `Set-Cookie` de expiración (`Max-Age=0`, iguales atributos). El frontend siempre limpia CSRF y caché/estado local, incluso si el endpoint falla; mostrar que el logout remoto no se confirmó si falló. Las sesiones caducan server-side incluso con navegador cerrado. Añadir revocación global solo si existe necesidad operativa, fuera de este cambio mínimo.

## Amenazas y límites

- **XSS:** `HttpOnly` reduce el robo/exfiltración del secreto de sesión vía `document.cookie`, pero XSS activo todavía puede operar la aplicación y enviar acciones autenticadas desde el navegador (incluido obtener/usar el token CSRF). Mantener CSP, escapar/sanitizar contenido, dependencias revisadas y no renderizar HTML no confiable. No afirmar que la cookie “resuelve XSS”.
- **CSRF:** una cookie se adjunta automáticamente; endpoints mutantes necesitan validación Origin + header CSRF vinculado a sesión. Mantener `SameSite=Strict`, CORS con origen explícito y credenciales solo para el frontend AAO. No `Access-Control-Allow-Origin: *` con credenciales.
- **Robo de equipo/perfil:** la cookie de sesión persiste en el perfil hasta cierre del navegador/logout y puede sobrevivir restauración de sesión del navegador. El TTL de servidor limita exposición; logout remoto revoca. No hay protección frente a usuario local ya autenticado.
- **Credencial inicial:** el bearer CEO estático actual sigue siendo una clave compartida en dev/test. El exchange evita almacenarla persistentemente en JS, pero no crea identidad individual, MFA, aprobación criptográfica ni autoridad de producción. Exigir canal HTTPS y nunca telemetría/logs de headers.
- **CSRF token vs XSS:** CSRF token en memoria no impide XSS que corre en mismo origen; su objetivo es impedir solicitudes iniciadas desde otros sitios.
- **Despliegue/orígenes:** puerto distinto sigue siendo el mismo site para `SameSite` en localhost, pero requiere `fetch(..., {credentials:'include'})`, CORS exacto y respuesta con credenciales. Producción requiere orígenes HTTPS configurados explícitamente. No establecer cookies para `localhost` desde hosts remotos.

## Cambios que requeriría la implementación

- Migración PostgreSQL versionada para sesiones CEO con hash único, expiración/revocación e índices/limpieza acotada.
- Endpoints bootstrap, estado de sesión (opcional; no necesario si bootstrap retorna éxito) y logout; límite de intentos y auditoría sin guardar secretos ni cookies.
- Dependency CEO compartida con fallback explícito para compatibilidad temporal de bearer solo dev/test. Cubrir cookie parsing seguro y respuestas 401/403 genéricas sin revelar secretos.
- Config explícita de `AAO_CEO_SESSION_COOKIE_SECURE`, frontend origins permitidos y expiración máxima. Rechazar config insegura en producción; por ahora no existe autenticación de producción, así que producción debe seguir fail-closed.
- Frontend: sesión CEO se verifica al arrancar mediante endpoint de estado; no token en `localStorage`/`sessionStorage`/IndexedDB. CSRF token en memoria; `credentials: 'include'`; logout remoto y purga local. Cambiar `HttpAaoLiveAdapter` de header CEO a cookie para rutas CEO después de transición.
- No usar cookie JWT firmado autocontenido como sustituto: la revocación inmediata hasta logout es más simple con identificador opaco y sesión server-side.

## Pruebas de aceptación requeridas antes de fusionar

1. Bootstrap acepta bearer válido solo en `development`/`test`; credencial inválida, ausente, producción y límites de rate devuelven rechazo genérico. Respuesta contiene atributos `HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` según ambiente y ningún bearer/session secret en JSON.
2. El bearer inicial no queda en storage web después del bootstrap ni aparece en logs/error/telemetry; tests frontend espían `localStorage`, `sessionStorage` e IndexedDB para confirmar que no se escriben tokens.
3. Cookie válida permite rutas CEO protegidas; cookie inventada, expirada, revocada o hash inválido no permite lectura ni escritura. El valor de cookie no se almacena en claro en DB.
4. Logout revoca esa sesión server-side, borra cookie y purga frontend; replay de la cookie tras logout falla aunque el navegador restaure el valor.
5. Toda mutación con cookie requiere CSRF correcto y Origin permitido. CSRF ausente/incorrecto, Origin externo/ausente y preflight/origin no configurado fallan cerrados. GET de solo lectura no produce efectos.
6. Pruebas Postgres se ejecutan solo con `AAO_TEST_DB_DISPOSABLE=yes`; concurrencia logout vs request no permite reutilización tras confirmarse la revocación.
7. E2E sobre HTTPS local verifica reload conserva sesión de navegador, cierre explícito la revoca, y modo DEMO no establece cookie. Verificar cookies en DevTools automatizado sin exponer secreto en artefactos/logs.
8. Config de producción sin TLS/orígenes explícitos/enforcement debe fallar al inicio o dejar auth CEO no disponible (503), no degradar atributos.
9. Actualizar contratos API, matriz de autorización y threat model; revisión de seguridad independiente antes de cualquier despliegue con datos/operaciones reales.

## Recomendación

Implementar como cambio backend+frontend coordinado y aislado, primero solo para desarrollo local, después de acordar expiración, compatibilidad de bearer y origen permitido. Mantener CEO token de desarrollo efímero y producción deshabilitada. No implementar “persistencia localStorage hasta logout”: elimina una recarga de UX a costa de convertir una credencial de alto privilegio en secreto extraíble por cualquier XSS.
