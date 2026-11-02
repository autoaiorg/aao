# Runbook — Backup, Verificación, Restauración Aislada y Migración de Host (AAO)

Este documento define los procedimientos operativos certificados para realizar copias de seguridad consistentes, verificar su integridad criptográfica, ejecutar restauraciones seguras en entornos aislados y trasladar AAO de un host a otro garantizando la exclusividad de ejecución y la ausencia de split-brain (fencing).

---

## 1. Principios de Seguridad y Aislamiento

1. **Verificación Previa en Entorno Aislado:** Conforme a las directrices de gobierno y la Condición 6 del CEO, ninguna restauración destructiva sobre un entorno con datos activos está autorizada sin haber sido verificada previamente en una base de datos aislada/desechable.
2. **Inmutabilidad y Checksums:** Cada copia de seguridad empaqueta un manifiesto (`manifest.json`) que registra la suma SHA-256 del volcado SQL de PostgreSQL y de cada archivo de artefactos incluido, además del commit Git exacto y la versión de migración.
3. **Canal Separado de Secretos:** Los secretos de producción (`/etc/aao/*.env`, `/etc/aao/aao-db.secret`) nunca se empaquetan en el backup público o no cifrado; se gestionan mediante canales protegidos con permisos `0600`.
4. **Fencing de Host (Exclusividad):** Antes de activar un nuevo host de producción, se revoca la autoridad del host origen mediante la expiración de turnos de conversación y el fallo de tareas en cola para evitar que dos instancias actúen concurrentemente.

---

## 2. Creación Atómica de Backup

Para generar un backup completo del estado de PostgreSQL y de los artefactos de trabajo:

```bash
# Ejecutar desde el entorno productivo con privilegios autorizados
aao-ops backup --output-dir /var/backups/aao
```

### Contenido del Paquete (`aao-backup-<timestamp>.tar.gz`):
- `manifest.json`: Manifiesto firmado con metadatos y tabla de hashes SHA-256.
- `database_dump.sql`: Volcado consistente de PostgreSQL generado mediante `pg_dump --clean --if-exists`.
- `artifacts/`: Árbol de evidencias, candidatos y salidas de ejecución persistidas bajo `/var/lib/aao/`.
- Permisos del archivo resultante: `0600` restringido a root.

---

## 3. Verificación de Integridad de la Copia

Antes de cualquier transferencia o restauración, valide que el archivo no ha sufrido corrupción o manipulación:

```bash
aao-ops verify-backup /var/backups/aao/aao-backup-20261026T120000Z.tar.gz
```

### Validaciones Ejecutadas por `verify-backup`:
- Estructura de archivo tar y ausencia de secuencias maliciosas de path traversal (`..`).
- Existencia y formato del manifiesto `manifest.json`.
- Recálculo en memoria del SHA-256 de `database_dump.sql` y comparación contra el hash del manifiesto.
- Recálculo del SHA-256 de todos los artefactos empaquetados.
- Código de salida: `0` si todo es íntegro; `1` si hay disparidad o corrupción.

---

## 4. Procedimiento de Restauración Aislada (Pre-flight Obligatorio)

### Autoridad anti-replay para restauraciones destructivas

Antes de habilitar restauraciones destructivas, provisionar una base PostgreSQL de autoridad **duradera y operada por separado** del destino. Aplicar como propietario el SQL versionado `db/postgres/restore_authority/001_consumed_restore_authorizations.sql` únicamente en esa base, no en la base AAO restaurable. Instalar el DSN de solo uso del ejecutor en `/etc/aao/restore-authority.database-url`, como archivo regular propiedad de root con modo `0600`, bajo un directorio padre propiedad de root no escribible por grupo/otros. El proceso lee exclusivamente esa ruta fija; no acepta DSN alternativo por variable de entorno o argumento. Mantener la URL fuera de argumentos de shell, logs y evidencia. El destino y la base de autoridad deben tener nombres distintos. El cliente exige `fsync=on` y `synchronous_commit=on`; si falta el archivo, la conexión, la tabla o la durabilidad, se deniega la restauración.

La clave pública autorizada debe instalarse como archivo regular propiedad de root bajo `/etc/aao/governance/ceo_restore_authority.pub`, con directorio padre no escribible por grupo/otros. La verificación no acepta una clave ni un identificador de autoridad elegidos por argumentos o variables de entorno del operador. El generador de artefactos requiere la clave privada del emisor (0600, propia del emisor) y esa clave privada no se instala en el host ejecutor.

El rol ejecutor de restauraciones debe tener únicamente `CONNECT` a la base, `USAGE` en `restore_authority` y `INSERT` más `SELECT(nonce)` sobre `restore_authority.consumed_authorizations`; no conceder `UPDATE`, `DELETE`, `TRUNCATE`, `CREATE` ni propiedad de objetos. El propietario de la base/tabla debe ser un rol de provisión distinto. Revise que la base de autoridad tenga retención, copias y recuperación independientes de la base restaurada. La aplicación no crea el esquema automáticamente. **La provisión/configuración de producción no se considera completada por el código o las pruebas**: debe quedar evidencia operacional antes de autorizar una restauración real.

La separación por nombre de base evita escribir el ledger en el destino PostgreSQL inmediato, pero no demuestra que ambos nombres estén en clusters físicos o dominios de recuperación distintos. Esa independencia debe verificarse operacionalmente; no ejecutar una restauración que pueda reemplazar la base de autoridad.

Las reservas se confirman antes de modificar el destino. Si la conexión se pierde con resultado incierto, el proceso deniega y exige reconciliación; no reintentar con el mismo permiso sin comprobar el ledger. Reservas previas no se eliminan: un permiso consumido por una restauración fallida requiere una nueva autorización.

Para cumplir la directriz de restauración en entorno aislado:

1. **Crear una base de datos desechable de verificación:**
   ```bash
   sudo -u postgres createdb -O aao_app aao_restore_verify
   ```
   Configure `/etc/aao/restore-target.env` y `/etc/aao/restore-verify.env` como
   archivos regulares `root:root` modo `0600`, con `AAO_RESTORE_TARGET_DSN` apuntando
   **a `aao_restore_verify`** y `AAO_RESTORE_VERIFY_ISOLATED_DSN` a otra base
   desechable aislada. No use el DSN productivo de `/etc/aao/aao-api.env` como destino
   de esta prueba ni pase DSN en argumentos de línea de comandos.

2. **Ejecutar la restauración de prueba:**
   ```bash
   # Para una base vacía, no usar --allow-non-empty ni una autorización destructiva.
   sudo /bin/bash -c 'set -a; . /etc/aao/restore-target.env; . /etc/aao/restore-verify.env; set +a; \
     exec /opt/aao/venv/bin/aao-ops restore /var/backups/aao/aao-backup-20261026T120000Z.tar.gz'
   ```

3. **Verificar el esquema y datos restaurados:**
   ```bash
   python -m aao.migrator --verify --dsn "postgresql://aao_app:SECRETO@127.0.0.1:5432/aao_restore_verify"
   ```

4. **Destruir la base de datos de prueba tras la validación:**
   ```bash
   sudo -u postgres dropdb aao_restore_verify
   ```

---

## 5. Procedimiento de Migración de Host (Cutover y Fencing)

Para trasladar AAO de un Host A a un Host B de forma reproducible y segura:

### Fase 1: En el Host Origen (Host A)
1. **Aplicar Fencing de Host (Exclusividad Efectiva):**
   Detener servicios de worker, enmascarar unidades locales, revocar credenciales de agentes activos en base de datos, expirar leases de turnos y registrar el evento de auditoría `host.fenced`:
   ```bash
   sudo aao-ops fence-host
   sudo systemctl stop aao-api.service
   ```

2. **Generar el backup final:**
   ```bash
   aao-ops backup --output-dir /var/backups/aao
   ```

3. **Verificar el backup generado:**
   ```bash
   aao-ops verify-backup /var/backups/aao/aao-backup-final.tar.gz
   ```

### Fase 2: Transferencia Segura
1. Copiar el paquete verificado al Host B mediante canal cifrado (`scp` sobre SSH con host keys verificadas).
2. Transferir de forma independiente las credenciales de `/etc/aao/`.

### Fase 3: En el Host Destino (Host B)
1. **Ejecutar Bootstrap Limpio en Host B:**
   ```bash
   sudo ./scripts/bootstrap/aao_bootstrap.sh --apply
   ```

2. **Restaurar el estado de datos con pre-verificación aislada y autorización explícita:**
   ```bash
   # Solo tras decisión de la autoridad competente y emisión del artefacto firmado.
   # Emitirlo fuera del host ejecutor, con la clave privada custodiada por esa autoridad:
   aao-ops authorize-restore /var/backups/aao/aao-backup-final.tar.gz \
     --target-database "$AAO_RESTORE_TARGET_DATABASE" \
     --signing-key-file /protected/issuer/ceo-restore-authority.key \
     --output /protected/issuer/restore-authorization.json
   # Copiar el artefacto al host por un canal controlado y protegido. Ejecutar como root
   # para leer la configuración fija de la base anti-replay; no pasar DSN en argumentos.
   sudo /bin/bash -c 'set -a; . /etc/aao/restore-target.env; . /etc/aao/restore-verify.env; set +a; \
     exec /opt/aao/venv/bin/aao-ops restore /var/backups/aao/aao-backup-final.tar.gz \
       --allow-non-empty --auth-file /protected/restore/restore-authorization.json'
   ```
3. **Verificar coherencia:**
   ```bash
   aao-ops doctor
   ```
4. **Iniciar servicios en Host B:**
   ```bash
   sudo systemctl start aao-api.service
   sudo systemctl start aao-worker-self-dev.service
   ```
5. **Garantía final:** El integrador permanece en OFF (`aao-integrator-tick.timer` enmascarado).
