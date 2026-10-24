# Procedimiento del CEO: actualizar la raíz de confianza y ejecutar el ensayo P2/P3

Este procedimiento es válido para cualquier revisión auditada. Necesitas tres valores, que el PM deja en el registro de las auditorías de esa revisión (`docs/audit-runs/<fecha>-agy-r1-chain-<sha>/README.md`):
- `REV`: el SHA completo de `main` auditado;
- `RH`: el sha256 del informe r1-chain que has leído;
- la confirmación de que el informe p2p3-trial de la misma `REV` es APPROVE-TECHNICAL y no tiene hallazgos A.

Todos los comandos usan `REV` de forma explícita, así que una fusión posterior en `main` no la cambia.

**Historial:**
- `b392750`: el paso 2 falló en la comprobación previa de identidades, porque `identity_separation.sh` no admitía los árboles congelados de un host ya instalado. No se cambió nada en el host. Se corrigió en la revisión siguiente.

**Qué incluye:** solo las operaciones que requieren tus privilegios: sudo y la decisión de fijar la raíz de confianza.

**Qué queda fuera, y por tanto no se hace aquí:**
- `--ra-status RA-0x=PASS` y `--enable-integrator`;
- la aceptación de la equivalencia de A-01, A-02 y P3-02;
- la retirada de la App de sondeo.

Todo ello requiere antes los resultados del ensayo y tu decisión R3. El integrador sigue apagado durante todo el procedimiento.

Copia y pega los bloques en orden. Si un paso termina en `FAIL`, detente y envía la salida.

## Paso 1. Clon de root en la revisión fijada (unos 30 s)

```bash
REV=<SHA auditado>      # 40 hex, del registro de la auditoría
RH=<sha256 del informe r1-chain>
sudo test -e /root/aao-src && sudo mv /root/aao-src /root/aao-src.old-$(date +%Y%m%dT%H%M%S)
sudo env -i PATH=/usr/bin:/bin HOME=/root GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_NO_REPLACE_OBJECTS=1 \
  git -c core.hooksPath=/dev/null clone -q https://github.com/autoaiorg/aao.git /root/aao-src
sudo git -C /root/aao-src -c advice.detachedHead=false checkout -q "$REV"
[ "$(sudo git -C /root/aao-src rev-parse HEAD)" = "$REV" ] && echo "clon OK en $REV"
B="sudo /root/aao-src/scripts/bootstrap/host_bootstrap.sh --rev $REV --ceo-user $USER"
```

El clon anterior no se borra: se aparta.

## Paso 2. Actualizar la raíz de confianza (simulación y después aplicación, unos 5 min)

```bash
[ "$(sudo sha256sum /home/aao-auditor-alt/aao-audits/$REV/report.md | cut -d" " -f1)" = "$RH" ] && echo "informe OK"
$B --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 $RH
```

La simulación no cambia nada. Comprueba en su salida:
- `audit verdict ['APPROVE-TECHNICAL']`;
- que `REV` desciende de la revisión instalada (`/etc/aao-audit/expected-revision`);
- que las líneas `DRY:` paran las unidades, hacen la copia de seguridad, congelan y regeneran.

Si todo está bien:

```bash
$B --apply --keys-dir /root/aao-keys --trust-root-upgrade --loop-repo autoaiorg/aao-governance-trial --audit-report-sha256 $RH
```

**Resultado esperado:**
- el verificador del host termina con `RESULT PASS`;
- el supervisor, la reverificación y el despacho del auditor quedan activos;
- **el integrador queda apagado**;
- la copia de la configuración anterior queda en `/var/backups/aao-trust-root/<fecha>-<revisión anterior>/`.

**Si el verificador falla**, el despacho queda apagado y el script imprime cómo restaurar. Envíame la salida y no improvises.

## Paso 3. Ensayo P2/P3 (de 30 a 60 min; no lo interrumpas)

```bash
sudo /root/aao-src/scripts/trial/run_trial.sh --rev $REV 2>&1 | tee ~/aao-trial-run-$REV.log
```

**Qué hace:** opera solo sobre el repositorio desechable `autoaiorg/aao-governance-trial` y sus forks, y nunca sobre `autoaiorg/aao`. Comprueba los rulesets al empezar y al terminar.

**Qué produce:**
- PR desechables en el repositorio de ensayo, que se quedan abiertas;
- una rama en `aao-trial-codex` con un cambio de workflow, para A-11 y P3-10. Nadie aprueba sus workflows.

**Duración:** hay pasos que esperan a los checks o a la aparición de los runs. P3-10 espera hasta 10 min.

**Resultados:** se espera que A-01, A-02 y P3-02 terminen en `EQUIVALENCE-PENDING`, nunca en PASS, hasta tu decisión. Un `NOT RUN` en las pruebas que siguen siendo manuales (A-07, A-08, A-13, P3-04, P3-08 y P3-11) es normal.

Al terminar, deja la evidencia legible para el PM:

```bash
TS=$(sudo ls -t /var/log/aao-trial | head -1)
sudo tar -C /var/log/aao-trial -czf ~/aao-trial-$TS.tgz "$TS" && sudo chown "$USER": ~/aao-trial-$TS.tgz && sha256sum ~/aao-trial-$TS.tgz
```

## Después del procedimiento

El PM analiza la evidencia y prepara:
1. el registro del ensayo;
2. la propuesta de validación formal de la equivalencia (decisión R3);
3. el procedimiento de las pruebas manuales restantes;
4. el siguiente lote: B-1 de r1-chain, que bloquea `--enable-integrator`, más C-01, C-02 y C-03 de p2p3-trial.

Ese lote necesitará su propia auditoría independiente antes de volver a tocar la raíz de confianza.
