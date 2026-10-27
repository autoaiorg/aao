# Servicio persistente del coordinador PM

**Alcance:** preparación de un servicio de usuario `systemd` para mantener activo el runner PM del proyecto autorizado. No se instala, habilita ni inicia en este cambio.

El unit `deploy/systemd/user/aao-project-coordinator@.service` ejecuta el runner existente con `--watch`, identidad PM y proyecto configurados por instancia. Reutiliza la API y los grants existentes; por defecto solo asigna hijos elegibles aún sin responsable. La consolidación factual sigue desactivada porque el unit no pasa `--auto-consolidate`. No crea grupos, admite ni despacha trabajo, ejecuta agentes, reintenta tareas ni amplía autoridad. Un fallo del proceso se reinicia con espera de 30 segundos, con límite de arranques de systemd; el siguiente pase vuelve a consultar el estado persistido.

## Requisitos antes de habilitarlo

1. Despliegue fijo del runtime en `/srv/aao/frozen/aao-pm/{tree,venv}`.
2. Usuario Linux `aao-pm` con sesión de usuario systemd y directorio runtime privado `/run/user/<uid>`.
3. Token AAO para el principal PM en `/run/user/<uid>/aao-pm.token`, fichero regular del usuario con modo `0600`; el script vuelve a comprobar identidad en `/v1/principals/me` en cada inicio.
4. Grants `work.coordinate` y `work.assign` explícitamente concedidos por el CEO en el proyecto. El archivo de configuración no es autorización.
5. Archivo `%h/.config/aao/project-coordinator/<project-id>.env`, propiedad de `aao-pm`, modo `0600`, con solo:

   ```text
   AAO_PROJECT_ID=<uuid del proyecto>
   AAO_PM_PRINCIPAL_ID=<principal autenticado del PM>
   ```

   No guardar tokens, claves de proveedor ni credenciales GitHub en este archivo. `AAO_API_BASE_URL` queda por defecto en `http://127.0.0.1:8001`; si el API está en otro origen, configurarlo en el entorno del manager de usuario y usar HTTPS fuera de loopback.

## Habilitación por el CEO (requiere actuar como aao-pm y un paso sudo)

Este procedimiento es una instrucción operativa, no autorización para Codex de actuar como otra cuenta, crear grants o cambiar el host. Ejecutar solo después de confirmar el proyecto y el principal:

1. Como `aao-pm`, crear el archivo `.env` descrito arriba, verificar modo `0600` y provisionar el token privado usando el mecanismo de host aprobado.
2. Como administrador, habilitar el user manager persistente para que el servicio sobreviva al cierre de sesión:

   ```sh
   sudo loginctl enable-linger aao-pm
   ```

3. Como `aao-pm`, instalar y revisar el unit, validar su sintaxis, y activarlo solo con decisión operativa expresa del CEO:

   ```sh
   mkdir -p ~/.config/systemd/user
   install -m 0644 /srv/aao/frozen/aao-pm/tree/deploy/systemd/user/aao-project-coordinator@.service \
     ~/.config/systemd/user/aao-project-coordinator@.service
   systemd-analyze --user verify ~/.config/systemd/user/aao-project-coordinator@.service
   systemctl --user daemon-reload
   systemctl --user enable --now "aao-project-coordinator@<project-uuid>.service"
   systemctl --user status "aao-project-coordinator@<project-uuid>.service"
   journalctl --user -u "aao-project-coordinator@<project-uuid>.service"
   ```

4. Para detenerlo, `systemctl --user disable --now ...`; no revocar grants ni borrar el token como sustituto de detener el proceso.

El servicio no debe habilitarse hasta que `/srv/aao/frozen/aao-pm` apunte a una revisión desplegada y revisada del repositorio. La unidad limita filesystem y privilegios, pero no configura sandbox de agente ni es un control de autorización. Si el backend rechaza una operación, revisar el estado en AAO; no relanzar con credenciales CEO ni añadir `--auto-consolidate` sin aprobación operativa explícita.

## Preflight local de instalación (solo lectura)

Contribuye a la Fase 0 (instalación, E-1) y a la preparación de planificación/asignación
para el piloto E-2; no es un gate superado, una certificación ni autorización de servicio.
Desde el checkout aprobado, con el intérprete/entorno normal del backend:

```bash
PYTHONPATH=src .venv/bin/python scripts/pm_deployment_preflight.py
# Una vez identificado el principal persistido y el rol runtime reales:
PYTHONPATH=src .venv/bin/python scripts/pm_deployment_preflight.py \
  --principal-id <principal-AAO-registrado> --runtime-role <rol-runtime>
```

El proyecto predeterminado es `9d17d6c1-d644-424a-a425-fe7e084c3d91`;
`--project-id` permite otro UUID. La cuenta Linux no identifica al principal AAO.
La conexión usa la configuración normal del backend (o `AAO_POSTGRES_URL` ya exportada),
pero rechaza servidores remotos y servicios libpq indirectos. No se debe copiar, mostrar
ni pasar por CLI ningún DSN ni token del CEO. El programa no selecciona hashes de tokens.
Todas las consultas se ejecutan tras `SET TRANSACTION READ ONLY`; no aplica migraciones,
concede grants, inicia servicios ni llama a proveedores/GitHub. Las excepciones de conexión
se redactan para no publicar credenciales.

La salida JSON contiene `PASS`, `MISSING` o `UNVERIFIED` y acciones concretas por comprobación;
el código de salida es 1 mientras haya elementos pendientes. Es una fotografía, no una
validación de autorización para ejecutar posteriormente. Comprueba un manifiesto local
completo y sin números duplicados de migraciones 001..035,
proyecto/mandato, credencial AGENT habilitada y grants vigentes (incluidos los sin caducidad
que admite el backend). Los grants solo los concede el CEO. El rol de inspección, incluso
si es un superusuario de desarrollo, **no** acredita el rol runtime. Si se especifica este,
se comprueban flags elevados y privilegios de las tablas 033/035, incluido el rechazo de
propiedad, DELETE/TRUNCATE del rol o DML/TRUNCATE público. La suficiencia global de permisos runtime sigue `UNVERIFIED`.

Los paths fijos `/srv/aao/frozen/aao-pm/{tree,venv}`, la unidad, configuración y tokens se
inspeccionan únicamente mediante metadatos (tipo, propietario, modo y ancestros). No se
leen claves, tokens ni ficheros `.env` de servicio. Los ficheros W2 `.pem` y `.json` se
esperan privados (0600) bajo cada cuenta. La revisión congelada, el contenido de la unidad,
linger/estado del servicio, la identidad efectiva del token, los scopes/instalaciones de
las Apps y una publicación W2 real requieren evidencia adicional: no se infieren de los
nombres o permisos. Un path inaccesible es `UNVERIFIED`, no permiso para usar sudo.
No instalar ni activar nada automáticamente para hacer desaparecer estos pendientes.
