#!/usr/bin/env bash
# Clean Ubuntu 24.04 VM Validation Harness for AAO Bootstrap (AC-01 through AC-18).
# Uses QEMU with KVM acceleration and Ubuntu 24.04 Cloud Image with real systemd PID 1.
# Enforces Finding M-03: verifies base image provenance and SHA-256 integrity, records logs.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
EVIDENCE_DIR="$REPO_DIR/tests/evidence"
mkdir -p "$EVIDENCE_DIR"
LOG_FILE="$EVIDENCE_DIR/vm_validation_transcript.log"

# Tee output to console and transcript log
exec > >(tee -a "$LOG_FILE") 2>&1

say() { echo -e "\n\033[1;36m=== [VM VALIDATION] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL [VM VALIDATION]: $*\033[0m" >&2; exit 1; }

CEO_USER="${1:-${CEO_USER:-$(whoami)}}"
VM_DIR="/tmp/aao-vm-validation"
IMAGE_URL="https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64.img"
SUMS_URL="https://cloud-images.ubuntu.com/minimal/releases/noble/release/SHA256SUMS"
BASE_IMAGE="$VM_DIR/ubuntu-24.04-minimal-cloudimg-amd64.img"
VM_DISK="$VM_DIR/vm-disk.qcow2"
CI_ISO="$VM_DIR/cloud-init.iso"

CURRENT_SHA=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "UNKNOWN")
say "Starting Clean Ubuntu 24.04 VM Validation for AAO Bootstrap"
say "Target Revision: $CURRENT_SHA"
say "CEO User:        $CEO_USER"
say "Timestamp:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"

say "1. Checking QEMU and KVM hardware virtualization..."
command -v qemu-system-x86_64 >/dev/null 2>&1 || die "qemu-system-x86_64 is not installed."
command -v qemu-img >/dev/null 2>&1 || die "qemu-img is not installed."

KVM_FLAG=""
if [[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
  KVM_FLAG="-enable-kvm"
  say "KVM hardware acceleration is available."
else
  echo "WARN: KVM hardware acceleration not accessible; running emulated."
fi

mkdir -p "$VM_DIR"

say "2. Verifying Ubuntu 24.04 Noble cloud image provenance and SHA-256 digest..."
say "Fetching official Ubuntu SHA256SUMS from $SUMS_URL..."
EXPECTED_SHA=$(curl -fsSL "$SUMS_URL" | grep "ubuntu-24.04-minimal-cloudimg-amd64.img" | awk '{print $1}' || true)
[[ -n "$EXPECTED_SHA" ]] || die "Unable to retrieve official SHA-256 for cloud image from Ubuntu."
say "Official SHA-256: $EXPECTED_SHA"

if [[ ! -f "$BASE_IMAGE" ]]; then
  say "Downloading cloud image from $IMAGE_URL..."
  curl -fSL -o "$BASE_IMAGE" "$IMAGE_URL"
else
  say "Checking cached base image at $BASE_IMAGE..."
fi

say "Verifying base image SHA-256 integrity..."
ACTUAL_SHA=$(sha256sum "$BASE_IMAGE" | awk '{print $1}')
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  say "Checksum mismatch: $ACTUAL_SHA != $EXPECTED_SHA. Re-downloading..."
  rm -f "$BASE_IMAGE"
  curl -fSL -o "$BASE_IMAGE" "$IMAGE_URL"
  ACTUAL_SHA=$(sha256sum "$BASE_IMAGE" | awk '{print $1}')
  if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    die "SHA-256 verification failed for cloud image!"
  fi
fi
say "Base image integrity verified: $ACTUAL_SHA"

say "3. Creating copy-on-write overlay disk..."
rm -f "$VM_DISK"
qemu-img create -f qcow2 -b "$BASE_IMAGE" -F qcow2 "$VM_DISK" 20G

say "4. Generating cloud-init metadata and user-data for CEO user '$CEO_USER'..."
SSH_DIR="$VM_DIR/ssh"
mkdir -p "$SSH_DIR"
rm -f "$SSH_DIR/id_ed25519"*
ssh-keygen -t ed25519 -N "" -f "$SSH_DIR/id_ed25519" -C "aao-vm-test" >/dev/null
PUB_KEY=$(cat "$SSH_DIR/id_ed25519.pub")

cat > "$VM_DIR/user-data" <<EOF
#cloud-config
users:
  - name: ${CEO_USER}
    groups: [sudo, kvm]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ${PUB_KEY}
package_update: true
packages:
  - git
  - python3
  - python3-venv
  - python3-pip
  - openssl
  - acl
  - bubblewrap
  - postgresql-16
  - postgresql-client-16
  - rsync
  - curl
final_message: "AAO VM Ready after \$UPTIME seconds"
EOF

cat > "$VM_DIR/meta-data" <<EOF
instance-id: aao-vm-test-$(date +%s)
local-hostname: aao-clean-vm
EOF

if command -v cloud-localds >/dev/null 2>&1; then
  cloud-localds "$CI_ISO" "$VM_DIR/user-data" "$VM_DIR/meta-data"
elif command -v genisoimage >/dev/null 2>&1; then
  genisoimage -output "$CI_ISO" -volid cidata -joliet -rock "$VM_DIR/user-data" "$VM_DIR/meta-data" >/dev/null 2>&1
elif command -v xorriso >/dev/null 2>&1; then
  xorriso -as mkisofs -output "$CI_ISO" -volid cidata -joliet -rock "$VM_DIR/user-data" "$VM_DIR/meta-data" >/dev/null 2>&1
else
  die "No ISO generator tool found (install cloud-localds, genisoimage, or xorriso)."
fi

SSH_PORT=22222
say "5. Launching clean Ubuntu 24.04 VM (PID 1 systemd) on port $SSH_PORT..."
qemu-system-x86_64 \
  $KVM_FLAG \
  -m 4096 \
  -smp 4 \
  -drive file="$VM_DISK",format=qcow2 \
  -drive file="$CI_ISO",format=raw \
  -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
  -device virtio-net-pci,netdev=net0 \
  -nographic \
  -pidfile "$VM_DIR/qemu.pid" >"$VM_DIR/qemu.log" 2>&1 &

QEMU_PID=$!
say "VM launched with PID $QEMU_PID. Waiting for SSH..."

cleanup() {
  say "Cleaning up VM (PID $QEMU_PID)..."
  kill "$QEMU_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for SSH port
TIMEOUT=180
ELAPSED=0
while ! nc -z 127.0.0.1 "$SSH_PORT" 2>/dev/null; do
  sleep 3
  ELAPSED=$((ELAPSED + 3))
  if (( ELAPSED >= TIMEOUT )); then
    die "Timed out waiting for VM SSH to become responsive."
  fi
done

say "SSH port reachable. Waiting for cloud-init to finish provisioning..."
SSH_OPTS="-i $SSH_DIR/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p $SSH_PORT"

TIMEOUT=300
ELAPSED=0
while true; do
  STATUS=$(ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "cloud-init status" 2>/dev/null || true)
  if echo "$STATUS" | grep -qE "status: (done|degraded)"; then
    say "cloud-init completed: $STATUS"
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  if (( ELAPSED >= TIMEOUT )); then
    die "Timed out waiting for cloud-init to complete."
  fi
done

say "6. Synchronizing AAO repository into clean VM as verified plain git clone..."
git -C "$REPO_DIR" bundle create "$VM_DIR/repo.bundle" HEAD
rsync -avz -e "ssh $SSH_OPTS" "$VM_DIR/repo.bundle" ${CEO_USER}@127.0.0.1:/home/${CEO_USER}/repo.bundle

ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "
  rm -rf /home/${CEO_USER}/aao-repo
  git clone /home/${CEO_USER}/repo.bundle /home/${CEO_USER}/aao-repo
  cd /home/${CEO_USER}/aao-repo
  git checkout -q ${CURRENT_SHA}
  sudo chown -R root:root /home/${CEO_USER}/aao-repo
  sudo chmod -R go-w /home/${CEO_USER}/aao-repo
"

say "7. Executing AAO Integral Bootstrap in clean VM (including governance & React build)..."
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo bash /home/${CEO_USER}/aao-repo/scripts/bootstrap/aao_bootstrap.sh --apply --ceo-user ${CEO_USER} --rev ${CURRENT_SHA}"

say "8. Running diagnostic verification in clean VM..."
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo /opt/aao/venv/bin/aao-ops doctor"

say "9. Verifying direct component endpoints and services in VM..."
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "systemctl is-active aao-api.service"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "systemctl is-active postgresql.service"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "curl -fsSL http://127.0.0.1:8001/health"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "curl -fsSL http://127.0.0.1:8001/ready"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "curl -fsSL http://127.0.0.1:8001/ | grep -i 'control center'"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "systemctl is-enabled aao-integrator-tick.timer 2>&1 | grep -E 'masked|disabled'"

say "10. Rebooting VM to test persistence across machine reboots (AC-03)..."
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo reboot" || true
sleep 10

while ! nc -z 127.0.0.1 "$SSH_PORT" 2>/dev/null; do
  sleep 3
done

say "VM rebooted successfully. Verifying post-reboot health..."
sleep 5
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo /opt/aao/venv/bin/aao-ops verify"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo /opt/aao/venv/bin/aao-ops doctor"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "curl -fsSL http://127.0.0.1:8001/ready"

say "11. Running live PostgreSQL tests inside the VM..."
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo /opt/aao/venv/bin/pip install --quiet pytest"
ssh $SSH_OPTS ${CEO_USER}@127.0.0.1 "sudo -E AAO_DATABASE_URL=\"postgresql://aao_app:\$(cat /etc/aao/aao-db.secret)@127.0.0.1:5432/aao_prod\" /opt/aao/venv/bin/pytest /opt/aao/current/tests/test_migrator.py /opt/aao/current/tests/test_ops_doctor.py"

say "CLEAN VM VALIDATION COMPLETED SUCCESSFULLY (AC-01 through AC-18 verified)."
say "Tested Git Revision: $CURRENT_SHA"
say "Log transcript stored at: $LOG_FILE"
exit 0
