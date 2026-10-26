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
