# Operar el coordinador de proyecto PM

**Estado:** guía de ejecución manual controlada. No instala ni activa un servicio.
El runner no es un modo de solo lectura: una pasada puede asignar trabajo.

## Alcance y precondiciones

`scripts/run_project_coordinator.py` consulta grupos ya confirmados por el CEO y, si encuentra hijos `INBOX` sin asignar, llama al endpoint existente protegido por `work.assign`. Por defecto no consolida. La opción explícita `--auto-consolidate` registra una consolidación descriptiva solo cuando todos los hijos están en `DONE` y aún no existe consolidación. No crea ni confirma grupos, no admite ni ejecuta trabajo, no cambia grants ni acepta resultados.

La consolidación automática es deliberadamente mecánica: genera un índice de IDs, estados, ejecuciones y dictámenes persistidos, ligado al SHA-256 del snapshot. No copia el campo de evidencia, no llama a un modelo, no infiere significado, no confirma criterios de aceptación y no equivale a una revisión independiente. La API revalida la fuente bajo transacción y rechaza consolidación obsoleta; además impide que el PM consolide hijos que haya escrito, asignado a sí mismo o ejecutado. El mismo snapshot genera la misma clave UUIDv5 para que un retry/replay no duplique el efecto.

Antes de ejecutarlo, el CEO debe verificar:

1. El backend AAO esperado está disponible y `AAO_API_BASE_URL` apunta a ese backend. HTTP solo se permite para loopback; cualquier API remota debe usar HTTPS.
2. El proyecto está activo y el grupo que se va a coordinar ya fue confirmado por el CEO. No existe modo `--dry-run`: la primera pasada puede cambiar asignaciones persistentes.
3. El principal PM seleccionado tiene grants vigentes `work.coordinate` y `work.assign` en ese proyecto. Los grants se conceden por el mecanismo CEO existente; este runner no los crea.
4. El usuario Linux que ejecutará el proceso es el custodio de la credencial del principal PM. Tiene un token AAO válido en `$XDG_RUNTIME_DIR/aao-pm.token`, con directorio privado suyo y fichero regular suyo con modo `0600`. No usar la clave privada de la GitHub App como token AAO.
5. El código se ejecuta desde un checkout/releases instalado y legible por `aao-pm`, no desde un worktree de desarrollo. Seleccionar la versión de código explícitamente antes de operar.

## Primera pasada: una sola vez

Sustituir los marcadores por valores comprobados por el CEO; no copiar credenciales a argumentos o variables de entorno. Este ejemplo supone que el API es local y el usuario de ejecución es `aao-pm`:

```bash
PM_UID="$(id -u aao-pm)"
AAO_CHECKOUT="/ruta/al/checkout-AAO-fijado"
AAO_PYTHON="/ruta/al/python-del-entorno-AAO"
PROJECT_ID="<UUID-del-proyecto-activo>"
PM_PRINCIPAL_ID="<principal-id-correspondiente-al-token>"

sudo -u aao-pm -H env \
  XDG_RUNTIME_DIR="/run/user/${PM_UID}" \
  AAO_API_BASE_URL="http://127.0.0.1:8001" \
  bash -c 'cd "$1" && exec "$2" -m scripts.run_project_coordinator \
    --project-id "$3" --principal-id "$4"' \
    _ "$AAO_CHECKOUT" "$AAO_PYTHON" "$PROJECT_ID" "$PM_PRINCIPAL_ID"
```

La pasada comprueba `/v1/principals/me` y se detiene si la identidad autenticada no coincide con `PM_PRINCIPAL_ID`; no inferir que el ID del principal siempre coincide con el nombre del usuario Linux. Si faltan permisos, proyecto, credencial o servicio, no se debe ampliar autoridad para ocultar el fallo: inspeccionar el rechazo y corregir solo la precondición correspondiente. Para permitir la consolidación descriptiva del runner, añadir `--auto-consolidate` al comando. Sin esa opción no se crean consolidaciones.

Tras la salida, comprobar en Control Center/API que las asignaciones y eventos persistidos corresponden al grupo y proyecto esperados. El número impreso por el proceso es un resumen, no la evidencia canónica.

## Polling continuo

Solo después de revisar satisfactoriamente la primera pasada, y con aprobación operativa explícita del CEO para el proyecto indicado, se puede añadir `--watch` al mismo comando. El intervalo predeterminado es 15 segundos y el máximo permitido es 300; detener con `Ctrl-C`/`SIGTERM`. La opción `--auto-consolidate` puede combinarse con `--watch`, pero cada consolidación queda persistida de forma irreversible para ese grupo: la API no permite sustituir una consolidación existente. Confirmar el modo elegido antes de ejecutarlo.

No se proporciona aún una unidad `systemd`, política de reinicio, rotación de credencial ni despliegue automático. No habilitar el proceso al arranque ni ejecutarlo para varios proyectos sin revisar su identidad, grants y alcance por separado. La consolidación no cierra ni acepta el trabajo padre: el CEO conserva la aceptación. El proceso no supervisa ejecuciones, no reintenta trabajos ni sustituye el ensayo de aceptación §14.
