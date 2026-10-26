# Instalación de la raíz de confianza en el host (op. 1 del §12.3)

> **REGENERATION REQUIRED — CEO sudo operation.** The existing installed trust root predates the RA-01/RA-02 trust inputs. It must be regenerated from the audited frozen revision and reinstalled by the CEO before any RA-01/RA-02 evidence can exist. This change adds the approved protected-route map and digest, per-check publisher App allowlists, and the exact GitHub push-principal-to-implementer map to `registry.json`; it also adds the operational route map and digest to `policy.json`. This is regeneration, not rotation. Do not set any RA to PASS as part of this operation.

> **Host nuevo o traslado:** usa `docs/procedures/HOST_BOOTSTRAP.md`. El script `scripts/bootstrap/host_bootstrap.sh` automatiza esta página y además deja el integrador apagado hasta que los RA estén en PASS. Esta página queda como referencia de lo que hace.

**Estado:** BORRADOR. No ejecutar hasta que:
- el SHA final de la cadena R1 tenga APPROVE de un revisor no recusado;
- esta página fije ese SHA en `REV`.

**Quién:** el CEO, con sudo (P5 (a)). Ningún agente ejecuta estos pasos.
**Tiempo:** unos 15 minutos. Se hace **una sola vez**. Después, las integraciones R1 no requieren al CEO.
**Deshacer:** `sudo systemctl disable --now aao-supervisor-intake aao-supervisor-heartbeat.timer` y borrar `/etc/aao-audit/trust-anchor.json`. Así el auditor y el integrador fallan cerrados. Los datos no se borran.

```bash
REV=<SHA final auditado>          # sustituye a 97ad4f1
REPO=$HOME/workspace/repos/active/aao
git -C "$REPO" fetch -q origin && git -C "$REPO" cat-file -e "$REV^{commit}"
```

## 1. Árboles congelados y entornos

El árbol del auditor tiene que ser **propiedad de `aao-auditor`**. `auditor_revision()` ejecuta `git rev-parse` en él, y git 2.43 rechaza los repos de otro propietario («dubious ownership»). Nadie más puede escribir en él: E10 lo comprueba.

La venv es de root. El python del sistema no trae pytest ni ruff, que las comprobaciones de la política necesitan.

```bash
for role in aao-auditor aao-supervisor aao-integrator; do
  sudo install -d -o aao-trust -g aao-trust -m 0755 /srv/aao/frozen/$role
  sudo git clone -q --no-hardlinks "$REPO" /srv/aao/frozen/$role/tree
  sudo git -C /srv/aao/frozen/$role/tree -c advice.detachedHead=false checkout -q "$REV"
  sudo git -C /srv/aao/frozen/$role/tree remote remove origin
  sudo python3 -m venv /srv/aao/frozen/$role/venv
  sudo /srv/aao/frozen/$role/venv/bin/pip install -q -r /srv/aao/frozen/$role/tree/deploy/auditor-venv-constraints.txt
done
sudo chown -R aao-auditor:aao-auditor /srv/aao/frozen/aao-auditor/tree
sudo chmod -R go-w /srv/aao/frozen
```

## 2. Unidades, directorios y clave del supervisor

```bash
T=/srv/aao/frozen/aao-supervisor/tree/deploy
sudo install -o root -g root -m 0644 $T/systemd/*.service $T/systemd/*.timer $T/systemd/*.path /etc/systemd/system/
sudo install -o root -g root -m 0644 $T/tmpfiles.d/aao-trust-root.conf /etc/tmpfiles.d/
sudo systemd-tmpfiles --create /etc/tmpfiles.d/aao-trust-root.conf
sudo -u aao-supervisor openssl genpkey -algorithm ed25519 -out /var/lib/aao-supervisor/keys/supervisor-ed25519.pem
sudo -u aao-supervisor chmod 0600 /var/lib/aao-supervisor/keys/supervisor-ed25519.pem
sudo -u aao-supervisor openssl pkey -in /var/lib/aao-supervisor/keys/supervisor-ed25519.pem -pubout \
  | sudo install -o aao-trust -g aao-trust -m 0644 /dev/stdin /srv/aao/trust/keys/aao-supervisor-ed25519.pub
```

## 3. Ancla, política, configuración del supervisor y registro

Primero se genera la clave de firma del integrador, que custodia su propio uid. Después, los archivos se generan con el script revisado de esta misma revisión:

```bash
sudo systemd-tmpfiles --create /etc/tmpfiles.d/aao-trust-root.conf   # crea /var/lib/aao-integrator (0700)
sudo -u aao-integrator openssl genpkey -algorithm ed25519 -out /var/lib/aao-integrator/integrator-ed25519.pem
sudo -u aao-integrator chmod 0600 /var/lib/aao-integrator/integrator-ed25519.pem
sudo -u aao-integrator openssl pkey -in /var/lib/aao-integrator/integrator-ed25519.pem -pubout \
  | sudo install -o aao-trust -g aao-trust -m 0644 /dev/stdin /srv/aao/trust/keys/aao-integrator-ed25519.pub
G=$(sudo mktemp -d)/out
sudo /usr/bin/python3 -I /srv/aao/frozen/aao-supervisor/tree/scripts/make_trust_root_files.py --revision "$REV" \
  --policy-template /srv/aao/frozen/aao-supervisor/tree/docs/audit-runs/20261019-provisional/policy.json \
  --repo autoaiorg/aao-governance-trial --out "$G"     # primero el repo de ensayo; el canónico, tras PASS
sudo install -d -o root -g root -m 0755 /etc/aao-audit /etc/aao-supervisor /etc/aao-integrator
sudo install -o root -g root -m 0644 "$G/integrator-config.json" /etc/aao-integrator/config.json
sudo install -o root -g root -m 0644 "$G/dispatch.json" /etc/aao-audit/dispatch.json
sudo install -o root -g root -m 0644 "$G/trust-anchor.json" /etc/aao-audit/trust-anchor.json
sudo install -o root -g root -m 0644 "$G/supervisor-config.json" /etc/aao-supervisor/config.json
sudo install -o aao-trust -g aao-trust -m 0644 "$G/registry.json" /srv/aao/trust/registry.json
sudo install -o aao-auditor -g aao-auditor -m 0644 "$G/policy.json" /var/lib/aao-auditor/policy.json
echo 0000000000000000000000000000000000000000000000000000000000000000 | sudo install -o root -g root -m 0644 /dev/stdin /etc/aao-audit/ledger.anchor
echo "$REV" | sudo install -o root -g root -m 0644 /dev/stdin /etc/aao-audit/expected-revision
```

El registro nace con todos los RA en **PENDING**, así que el integrador falla cerrado. Cuando el ensayo P2/P3 dé PASS (A-01 a A-14, P3-01 a P3-12), el CEO reinstala `registry.json` con esos RA en PASS. Es el último paso manual. A partir de ahí no hay ningún dato por PR en el registro.

## 4. Arranque y verificación

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aao-supervisor-intake.service aao-supervisor-heartbeat.timer aao-supervisor-attribution.timer aao-supervisor-watch.timer
# 1) Verify FIRST. The status file is what the integrator requires (PASS less than 26 h old).
set -o pipefail
mkdir -p "${XDG_STATE_HOME:-$HOME/.local/state}/aao/runs/trust-root-verification"; chmod 700 "${XDG_STATE_HOME:-$HOME/.local/state}/aao/runs/trust-root-verification"; umask 077
sudo /usr/bin/python3 -I /srv/aao/frozen/aao-supervisor/tree/scripts/verify_trust_root_host.py --expected-revision "$REV" \
  --status-file /var/lib/aao-trust-verify/status.json | tee "${XDG_STATE_HOME:-$HOME/.local/state}/aao/runs/trust-root-verification/aao-trust-root-verify-$(date -u +%Y%m%dT%H%M%SZ).log" \
  || { echo "Verification failed: the R1 loop is NOT enabled. Paste the log in the bootstrap issue."; return 1 2>/dev/null || exit 1; }
# 2) Only with RESULT: PASS: daily re-verification and the R1 loop. With RA PENDING in the registry it audits
#    and stages but never promotes; without a fresh verifier PASS it never promotes either.
sudo systemctl enable --now aao-trust-root-verify.timer
sudo systemctl enable --now aao-auditor-dispatch.path aao-auditor-dispatch.timer aao-integrator-tick.timer
```

Hace falta `RESULT: PASS`. Pega el log completo en el issue del arranque.

Si alguna comprobación da FAIL, la raíz de confianza **no** se considera instalada. El auditor y el integrador siguen fallando cerrados, que es el estado seguro.
