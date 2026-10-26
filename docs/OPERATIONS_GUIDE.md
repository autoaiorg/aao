# Guía de Operaciones y Diagnóstico — Autonomous AI Organization (AAO)

Este documento describe la operativa diaria, monitorización, diagnóstico y resolución de incidencias en un despliegue integral de AAO en Linux (Ubuntu 24.04 LTS).

---

## 1. Arquitectura de Servicios del Producto

El despliegue productivo de AAO desacopla la gobernanza de la ejecución del producto mediante unidades systemd gestionadas con identidades de mínimo privilegio:

| Servicio | Unidad Systemd | Usuario Linux | Finalidad |
|---|---|---|---|
| **API & Control Center** | `aao-api.service` | `aao-api` | Servidor FastAPI loopback (127.0.0.1:8001) y servicio SPA del frontend React. |
| **PostgreSQL 16** | `postgresql.service` | `postgres` | Datastore canónico de estado compartido, colas, eventos y auditoría. |
| **Worker Self-Development** | `aao-worker-self-dev.service` | `aao-impl-ag` | Procesamiento supervisado de colas en modo `--watch` con leases y fencing. |
| **Recuperación de Turnos** | `aao-conversation-recovery.timer` | `aao-api` | Recuperación periódica de turnos de conversación expirados. |
| **Integrador** | `aao-integrator-tick.timer` | `aao-integrator` | **OFF (Enmascarado).** Solo el CEO con todas las RA en PASS puede habilitarlo. |

---

## 2. Comandos Operativos Unificados (`aao-ops`)

AAO proporciona la herramienta de línea de comandos `aao-ops` (instalada en el venv del sistema y ejecutable vía `/opt/aao/venv/bin/aao-ops` o `python -m aao.ops`):

### 2.1. Estado General del Sistema
```bash
aao-ops status
```
Muestra un resumen en tiempo real de:
- Conectividad y versión de PostgreSQL.
- Versión del esquema (`schema_migrations`).
- Estado de respuesta de la API (`/health` y `/ready`).
- Estado del paquete compilado del Control Center.
- Estado de las guardas de gobernanza (Integrador en OFF).
- Conteo de tareas en la cola de ejecución agrupadas por estado.

### 2.2. Diagnóstico Accionable (`doctor`)
```bash
aao-ops doctor
```
Ejecuta la suite completa de diagnósticos y ofrece recomendaciones operativas estructuradas:
- `PASS`: El componente opera dentro de los parámetros esperados.
- `WARN`: El componente requiere atención pero no impide la operatividad general (ej. frontend en fallback legacy).
- `FAIL`: Bloqueo crítico que detiene el servicio (ej. migración alterada, DB inaccesible, integrador activo indebidamente).

### 2.3. Verificación Silenciosa (Healthcheck)
```bash
aao-ops verify
```
Retorna código de salida `0` si el sistema está completamente saludable; `1` si hay fallos activos. Ideal para sondas de monitorización externa o scripts de integración.

---

## 3. Gestión de Servicios con systemd

### Control del Servicio API:
```bash
# Iniciar o reiniciar la API
sudo systemctl restart aao-api.service

# Ver estado y logs recientes
sudo systemctl status aao-api.service
sudo journalctl -u aao-api.service -n 50 --no-pager
```

### Control del Worker de Desarrollo:
```bash
sudo systemctl start aao-worker-self-dev.service
sudo systemctl stop aao-worker-self-dev.service
sudo journalctl -u aao-worker-self-dev.service -f
```

---

## 4. Gestión de Migraciones de Base de Datos (`aao-migrate`)

El aplicador de migraciones único garantiza la consistencia entre disco y base de datos con locks concurrentes:

```bash
# Ver estado de migraciones aplicadas y pendientes
aao-migrate --status

# Aplicar migraciones pendientes
aao-migrate --apply

# Verificar que no existen migraciones pendientes ni sumas SHA-256 alteradas
aao-migrate --verify
```

---

## 5. Rotación de Credenciales del CEO

El token local del CEO no se imprime en consola ni se guarda en texto plano en Git. Para rotarlo de forma interactiva y segura:

```bash
python scripts/rotate_local_ceo_token.py
```
El script solicita la nueva clave mediante un prompt oculto sin eco, actualiza de forma atómica `/etc/aao/aao-api.env` (o `.env.local` en dev), reinicia la API y reaprovisiona las credenciales de agente dependientes.

---

## 6. Resolución de Incidencias Comunes

| Síntoma | Causa Probable | Solución Accionable |
|---|---|---|
| `HTTP 503 en /ready` | PostgreSQL no responde o base de datos inaccesible. | Comprobar `sudo systemctl status postgresql` y la cadena `AAO_POSTGRES_URL` en `/etc/aao/aao-api.env`. |
| `HTTP 403 en endpoints CEO` | Token del CEO incorrecto o no enviado en `X-CEO-Token`. | Comprobar cabecera o rotar token con `scripts/rotate_local_ceo_token.py`. |
| `FAIL: Integrity violation in migration` | Un archivo SQL en `db/postgres/` fue modificado tras ser aplicado. | Los archivos de migración son inmutables. Restaurar el archivo original desde Git (`git checkout db/postgres/...`) o crear una nueva migración incremental. |
| `FAIL: Integrator timer is ACTIVE` | El temporizador del integrador fue habilitado sin autorización. | Ejecutar `sudo systemctl mask aao-integrator-tick.timer` inmediatamente. |
