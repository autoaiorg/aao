# Arquitectura de Despliegue y Arranque de Host en AAO

AAO distingue explícitamente entre dos niveles de despliegue en un host Linux:

1. **Bootstrap Integral del Producto (`scripts/bootstrap/aao_bootstrap.sh`):**
   - **Objetivo:** Poner en funcionamiento de manera reproducible, automatizada e idempotente el producto completo de AAO en una máquina Linux limpia (Ubuntu 24.04 LTS).
   - **Componentes desplegados:** PostgreSQL 16 nativo, aplicador de migraciones unificado (001 a 031), entorno virtual aislado en `/opt/aao/venv`, cuenta de servicio sin privilegios `aao-api`, servicio systemd `aao-api.service`, Control Center React compilado y servido como SPA, worker supervisado `aao-worker-self-dev.service`, configuración protegida en `/etc/aao/`, backup/restore seguro y herramienta operativa `aao-ops`.
   - **Fencing de workers:** la migración 031 crea el registro de fencing, pero no asigna identidades automáticamente. `init_secrets.sh` conserva `/etc/machine-id` como `/etc/aao/host-id`, protegido como `root:aao-impl-ag 0440`; el ejecutor compara esa identidad local protegida con la única vinculación activa del worker al reclamar, completar o proponer un efecto. Registra explícitamente el valor de ese archivo con `aao-ops register-host-worker --worker-id <principal-id> --host-id "$(cat /etc/aao/host-id)"`; en una migración de host, cerca primero la asociación antigua. La identidad es un identificador local protegido, no una atestación criptográfica ni una defensa contra root o un clon que conserve `/etc/machine-id`.
   - **Garantías de gobierno:** El integrador permanece en **OFF**, las RA permanecen en **PENDING** y el nivel de riesgo **R2** permanece bloqueado.

2. **Infraestructura de Gobierno y Raíz de Confianza (`scripts/bootstrap/host_bootstrap.sh`):**
   - **Objetivo:** Establecer la raíz criptográfica de confianza, auditorías independientes, verificación 9/9 de GitHub Apps, árboles congelados en `/srv/aao/frozen` y unidades de despacho.
   - **Quién:** El CEO, con sudo (P5 (a)).

---

# 1. Bootstrap Integral del Producto (`aao_bootstrap.sh`)

### Requisitos Mínimos:
- Ubuntu 24.04 LTS (Noble Numbat) x86_64 o Debian 12.
- 4 GB de RAM mínima y 15 GB de almacenamiento libre en `/`.
- Acceso a internet durante la instalación para descargar paquetes del sistema y Node.js 24 LTS.

### Ejecución de Instalación Limpia:
```bash
# Simulación (Dry-run de preflight)
sudo ./scripts/bootstrap/aao_bootstrap.sh

# Despliegue completo con aplicación de cambios
sudo ./scripts/bootstrap/aao_bootstrap.sh --apply
```

### Verificación Inmediata tras la Instalación:
```bash
# Diagnóstico de salud accionable
sudo /opt/aao/venv/bin/aao-ops doctor

# Acceso al Control Center
curl -I http://127.0.0.1:8001/
```

---

# 2. Arranque de Gobernanza y Raíz de Confianza (`host_bootstrap.sh`)

**Quién:** el CEO, con sudo (P5 (a)). Ningún agente ejecuta estos pasos.
**Para qué:** dejar un host nuevo en el mismo estado que el actual, o mover AAO de una máquina a otra.
**Qué hace:** encadena las piezas revisadas, en este orden:
1. cuentas y directorios de P1;
2. claves de las Apps, cada una en su uid;
3. verificación 9/9 de las Apps;
4. Antigravity como auditor alternativo;
5. de forma opcional, la raíz de confianza.

**El integrador queda apagado.** Solo se enciende con `--enable-integrator`, y el script se niega mientras algún RA del registro instalado no esté en PASS.

Por defecto el script **simula**: imprime lo que haría sin cambiar nada. Con `--apply` lo hace. Falla en cerrado y nunca regenera una clave privada que ya exista. Las fases 1 a 4 se pueden repetir sin riesgo. La fase de la raíz de confianza solo corre en un host que no tenga ninguna instalada: si ya existe cualquiera de sus archivos, se niega antes de escribir nada. Rotar la raíz es otro procedimiento.

## 0. Requisitos del host

Ubuntu 24.04 o equivalente, con `git` ≥ 2.38, `python3`, `python3-venv`, `openssl`, `systemd` y `acl`:

```bash
sudo apt-get install -y git python3 python3-venv openssl acl
```

## 1. Clon de root en la revisión exacta

El script nunca corre desde tu copia de trabajo: los agentes pueden escribir en ella, incluido `.git`. Root clona el repo público en un directorio suyo y comprueba el SHA:

```bash
REV=<SHA de main auditado>       # 40 hex
sudo test -e /root/aao-src && sudo mv /root/aao-src /root/aao-src.old-$(date +%Y%m%dT%H%M%S)   # el clon anterior se aparta, no se borra
sudo env -i PATH=/usr/bin:/bin HOME=/root GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_NO_REPLACE_OBJECTS=1 \
  git -c core.hooksPath=/dev/null clone -q https://github.com/autoaiorg/aao.git /root/aao-src
sudo git -C /root/aao-src -c advice.detachedHead=false checkout -q "$REV"
[ "$(sudo git -C /root/aao-src rev-parse HEAD)" = "$REV" ] && echo "clon OK en $REV"
B="sudo /root/aao-src/scripts/bootstrap/host_bootstrap.sh --rev $REV --ceo-user $USER"
```

## 2. Claves de las GitHub Apps

Hay dos caminos. Elige uno:

- **(a) Traer las claves de la máquina anterior, de root a root.** Copia `/home/<uid>/.config/aao/<app>.pem` de cada App a un directorio de root en la máquina nueva: `/root/aao-keys`, modo 0700, con los nueve archivos `<app>.pem` (`aao-impl-agy.pem` incluido). El script rechaza cualquier directorio bajo `/home` o `/tmp`.
- **(b) Generar claves nuevas** en la configuración de cada App en GitHub (*Private keys → Generate*). GitHub descarga el `.pem` en tu home, donde los agentes pueden leerlo. Para este camino:
  1. Para antes las sesiones de los agentes.
  2. Mueve los archivos a `/root/aao-keys` nada más descargarlos.
  3. Ejecuta `shred -u` sobre las descargas.

  Después revoca en GitHub las claves de la máquina anterior.

## 3. Ejecución

```bash
$B                                            # simulación: revisa la salida
$B --apply --keys-dir /root/aao-keys          # P1 + claves + 9/9 + Antigravity
```

**agy.** Se instala solo contra un hash que das tú: `--agy ~/.local/bin/agy --agy-sha256 <hex>`. Calcula ese hash con `sha256sum` sobre el binario que descargaste de la fuente oficial, no sobre uno que hayan podido tocar los agentes. Sin `--agy`, un `/usr/local/bin/agy` existente se deja como está. Con `--agy`, se sustituye, solo si el hash coincide (así se actualiza).

Si nunca has iniciado sesión de agy como `aao-auditor-alt` en esta máquina, el script imprime el comando de login. Hazlo una vez y une la URL en **una sola línea** antes de abrirla.

Luego, la auditoría independiente de la revisión que vas a instalar:

```bash
sudo -u aao-auditor-alt -H /opt/aao-audit/run_agy_audit.sh <base auditada> "$REV"
```

Instala la raíz de confianza solo si el `report.md` dice **APPROVE-TECHNICAL**, que es el único veredicto favorable del prompt de auditoría:

```bash
sudo sha256sum /home/aao-auditor-alt/aao-audits/$REV/report.md   # el hash del informe que has leído
$B --apply --keys-dir /root/aao-keys --trust-root --loop-repo <OWNER/REPO> --audit-report-sha256 <ese hash>
```

`--loop-repo` es el repo que servirá el bucle R1. Hasta que pase el ensayo P2/P3, debe ser el repo de ensayo, que tienes que crear tú (`autoaiorg/aao-governance-trial`, ver `P2_P3_TRIAL_SETUP.md`).

El script lee la auditoría de ese mismo `REV` en `/home/aao-auditor-alt/aao-audits/$REV/`, donde solo escribe `aao-auditor-alt`. Exige que el informe sea exactamente el que fijaste con `--audit-report-sha256`, porque la instalación la autorizas tú. Además comprueba que coincide con la atestación y que el veredicto es exactamente APPROVE-TECHNICAL. Si algo no cuadra, se niega. **Límite conocido:** la atestación no lleva firma. Que la produjo el auditor se apoya en que solo `aao-auditor-alt` puede escribir en esa carpeta. Una firma con una clave de ese mismo uid no demostraría nada más. Lo que autoriza la instalación es tu hash. Después verifica el host y exige `RESULT: PASS`. Después activa la reverificación diaria y el despacho del auditor, pero **no** el integrador. Los logs quedan en `/var/log/aao-bootstrap/<fecha>/`.

Cuando el ensayo P2/P3 dé PASS y reinstales el registro con los RA en PASS:

```bash
$B --apply --keys-dir /root/aao-keys --enable-integrator
```

## 4. Si es un traslado: la máquina anterior

Haz esto **antes** de activar el bucle en la máquina nueva, para que nunca haya dos integradores con claves válidas a la vez:

```bash
sudo systemctl disable --now aao-integrator-tick.timer aao-auditor-dispatch.path aao-auditor-dispatch.timer \
  aao-supervisor-intake.service aao-supervisor-heartbeat.timer aao-trust-root-verify.timer 2>/dev/null
sudo /root/aao-src/scripts/identity_separation.sh --purge    # (clon de root del paso 1) archiva ledgers, claves y registro en /root/aao-identity-archive-*.tar.gz
```

Guarda el archivo `.tar.gz`, porque los logs no se borran. Si usaste el camino (b), revoca en GitHub las claves antiguas de las Apps en cuanto la máquina nueva dé 9/9.

## 5. Actualizar una raíz de confianza ya instalada (`--trust-root-upgrade`)

Úsalo para llevar la raíz de confianza instalada a una revisión posterior y auditada, por ejemplo cuando el registro necesita campos nuevos (RA-01 y RA-02). También para registrar tu decisión de poner los RA en PASS (`--ra-status`). **No sirve para volver a una revisión anterior:** la nueva revisión tiene que descender de la instalada.

**Requisitos:**
- una auditoría de Antigravity de la nueva `REV` con el prompt `r1-chain` y veredicto APPROVE-TECHNICAL (`/home/aao-auditor-alt/aao-audits/$REV/`);
- el clon de root del paso 1 en esa `REV`.

```bash
sudo sha256sum /home/aao-auditor-alt/aao-audits/$REV/report.md          # el informe que has leído
$B                       --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 <hash>   # simulación
$B --apply --keys-dir /root/aao-keys --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 <hash>
# Solo cuando el ensayo dé PASS, como decisión del CEO; cada RA que no indiques queda en PENDING:
#   ... --trust-root-upgrade ... --ra-status RA-01=PASS --ra-status RA-02=PASS ...
```

**Qué hace:**
1. Comprueba la auditoría igual que una instalación nueva.
2. Exige que la nueva `REV` descienda de `/etc/aao-audit/expected-revision`.
3. Detiene todo el bucle, integrador incluido.
4. Guarda en `/var/backups/aao-trust-root/<fecha>-<rev anterior>/` la configuración y las unidades instaladas (`config.tar`), y los árboles congelados anteriores.
5. Congela los árboles nuevos, reinstala las unidades y regenera el registro y la configuración.
6. Conserva las claves, el ledger del auditor y `ledger.anchor`, de modo que la cadena continúa.
7. Ejecuta el verificador del host. Con PASS, reactiva el supervisor, la reverificación y el despacho del auditor. **El integrador queda apagado:** se enciende aparte con `--enable-integrator`.

**Si el verificador falla:** el despacho queda apagado y el script imprime cómo deshacer el cambio. Hay que detener las unidades `aao-*`, quitar las unidades `aao-*` que haya añadido la nueva revisión, ejecutar `tar -C / -xpf config.tar` (restaura la configuración y las unidades anteriores), devolver los `frozen-*/` a su sitio, escribir la revisión anterior en `expected-revision` y ejecutar `systemctl daemon-reload`.
