#!/usr/bin/env bash
# Clean Ubuntu 24.04 VM Validation Harness for AAO Bootstrap (AC-01 through AC-18).
# Uses QEMU with KVM acceleration and Ubuntu 24.04 Cloud Image with real systemd PID 1.
set -euo pipefail

say() { echo -e "\n\033[1;36m=== [VM VALIDATION] $*\033[0m"; }
die() { echo -e "\n\033[1;31mFAIL [VM VALIDATION]: $*\033[0m" >&2; exit 1; }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
VM_DIR="/tmp/aao-vm-validation"
IMAGE_URL="https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64.img"
BASE_IMAGE="$VM_DIR/noble-base.img"
VM_DISK="$VM_DIR/vm-disk.qcow2"
CI_ISO="$VM_DIR/cloud-init.iso"

say "1. Checking QEMU and KVM hardware virtualization..."
command -v qemu-system-x86_64 >/dev/null 2>&1 || die "qemu-system-x86_64 is not installed."
command -v cloud-localds >/dev/null 2>&1 || command -v genisoimage >/dev/null 2>&1 || die "genisoimage or cloud-utils required for cloud-init."

KVM_FLAG=""
if [[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
  KVM_FLAG="-enable-kvm"
  say "KVM hardware acceleration is available."
else
  echo "WARN: KVM hardware acceleration not accessible; running emulated."
fi

mkdir -p "$VM_DIR"

say "2. Downloading or verifying Ubuntu 24.04 Noble minimal cloud image..."
if [[ ! -f "$BASE_IMAGE" ]]; then
  say "Downloading cloud image from $IMAGE_URL..."
  curl -fsSL -o "$BASE_IMAGE" "$IMAGE_URL"
else
  say "Using cached cloud image at $BASE_IMAGE."
fi

say "3. Creating copy-on-write overlay disk..."
rm -f "$VM_DISK"
qemu-img create -f qcow2 -b "$BASE_IMAGE" -F qcow2 "$VM_DISK" 20G

say "4. Generating cloud-init metadata and user-data..."
SSH_DIR="$VM_DIR/ssh"
mkdir -p "$SSH_DIR"
rm -f "$SSH_DIR/id_ed25519"*
ssh-keygen -t ed25519 -N "" -f "$SSH_DIR/id_ed25519" -C "aao-vm-test" >/dev/null
PUB_KEY=$(cat "$SSH_DIR/id_ed25519.pub")

cat > "$VM_DIR/user-data" <<EOF
#cloud-config
users:
  - name: alessbarb
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
else
  genisoimage -output "$CI_ISO" -volid cidata -joliet -rock "$VM_DIR/user-data" "$VM_DIR/meta-data" >/dev/null 2>&1
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
  say "Cleaning up VM..."
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

say "SSH port reachable. Waiting for cloud-init to finish..."
SSH_OPTS="-i $SSH_DIR/id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p $SSH_PORT"

while ! ssh $SSH_OPTS alessbarb@127.0.0.1 "cloud-init status --wait" >/dev/null 2>&1; do
  sleep 5
done

say "6. Synchronizing AAO repository into VM..."
rsync -avz -e "ssh $SSH_OPTS" \
  --exclude ".git" \
  --exclude ".worktrees" \
  --exclude "node_modules" \
  --exclude ".pytest_cache" \
  --exclude "__pycache__" \
  "$REPO_DIR/" alessbarb@127.0.0.1:/home/alessbarb/aao-repo/

say "7. Executing AAO Integral Bootstrap in clean VM (including full frontend build)..."
ssh $SSH_OPTS alessbarb@127.0.0.1 "sudo bash /home/alessbarb/aao-repo/scripts/bootstrap/aao_bootstrap.sh --apply --ceo-user alessbarb"

say "8. Running diagnostic verification in clean VM..."
ssh $SSH_OPTS alessbarb@127.0.0.1 "sudo /opt/aao/venv/bin/aao-ops doctor"

say "9. Testing full acceptance suite inside clean VM..."
ssh $SSH_OPTS alessbarb@127.0.0.1 "sudo bash /home/alessbarb/aao-repo/tests/test_clean_install_container.sh /home/alessbarb/aao-repo"

say "10. Rebooting VM to test persistence across machine reboots (AC-03)..."
ssh $SSH_OPTS alessbarb@127.0.0.1 "sudo reboot" || true
sleep 10

while ! nc -z 127.0.0.1 "$SSH_PORT" 2>/dev/null; do
  sleep 3
done

say "VM rebooted successfully. Verifying post-reboot health..."
ssh $SSH_OPTS alessbarb@127.0.0.1 "sudo /opt/aao/venv/bin/aao-ops verify"

say "CLEAN VM VALIDATION COMPLETED SUCCESSFULLY (AC-01 through AC-18 verified)."
exit 0
