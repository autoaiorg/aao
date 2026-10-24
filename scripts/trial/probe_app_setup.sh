#!/usr/bin/env bash
# CEO only (sudo + his GitHub account). CEO decision 2026-10-24 (#65, decision 3): disposable App for A-14.
# Creates uid aao-probe-noworkflows, the App (owner: organization autoaiorg, permissions exactly
# docs/proposals/github-apps/aao-probe-noworkflows.json: contents write + metadata read, NO workflows),
# and the fork autoaiorg/aao-trial-probe of the trial repo. The CEO then installs the App ONLY on that fork.
#   scripts/trial/probe_app_setup.sh <REV of origin/main>      (run from the CEO working copy)
# Teardown after A-14 (revocation):  scripts/trial/probe_app_setup.sh --teardown
set -euo pipefail
APP=aao-probe-noworkflows FORK=autoaiorg/aao-trial-probe
if [[ ${1:-} == --teardown ]]; then
  echo "1. GitHub: Settings of $APP > Install App > Uninstall from $FORK, then Advanced > Delete GitHub App."
  read -r -p "Done on GitHub? [y/N] " ok; [[ $ok == y ]] || exit 1
  # The key must be destroyed before the account goes; a failed shred stops the teardown (Codex audit 2b3e9c1 B-05).
  sudo -u $APP -H sh -ec 'shred -u ~/.config/aao/'$APP'.pem && rm -f ~/.config/aao/'$APP'.json' || { echo "FAIL: key not destroyed" >&2; exit 1; }
  sudo userdel -r $APP && echo "uid removed"
  gh repo delete $FORK --yes && echo "fork deleted"
  exit 0
fi
REV=${1:?REV (40-hex) of origin/main to take the reviewed exchange script and manifests from}
[[ $REV =~ ^[0-9a-f]{40}$ ]] || { echo "REV must be 40 hex" >&2; exit 2; }
REPO=$(git rev-parse --show-toplevel)
GIT=(git -C "$REPO")
getent passwd $APP >/dev/null || sudo useradd --system --create-home --shell /usr/sbin/nologin $APP
sudo chmod 0700 /home/$APP
# Reviewed exchange script and manifests, from git objects (not the working tree).
git -C "$REPO" show "$REV:scripts/github_apps/exchange_manifest_code.py" | sudo install -o root -g root -m 0755 /dev/stdin /opt/aao-p2/exchange_manifest_code.py
git -C "$REPO" show "$REV:docs/proposals/github-apps/$APP.json" | sudo install -o root -g root -m 0644 /dev/stdin /opt/aao-p2/github-apps/$APP.json
# The form only builds HTML; the exchange refuses the key if GitHub's permissions differ from the reviewed manifest.
form_tmp=$(mktemp -d); trap 'rm -rf "$form_tmp"' EXIT
git -C "$REPO" archive "$REV" scripts/github_apps/create_app_form.py docs/proposals/github-apps | tar -x -C "$form_tmp"
python3 "$form_tmp/scripts/github_apps/create_app_form.py" "$APP" --org autoaiorg --manifest-dir "$form_tmp/docs/proposals/github-apps"
xdg-open "/tmp/aao-create-$APP.html" 2>/dev/null || echo "open /tmp/aao-create-$APP.html in the browser"
echo "Click 'Create GitHub App'. The browser lands on http://127.0.0.1:9/?code=...: copy the code value."
read -r -p "code: " code
sudo -u $APP -H /usr/bin/python3 -I /opt/aao-p2/exchange_manifest_code.py $APP <<<"$code"
gh repo view $FORK >/dev/null 2>&1 || gh repo fork autoaiorg/aao-governance-trial --org autoaiorg --fork-name aao-trial-probe --clone=false
echo "Last step on GitHub: App $APP > Install App > autoaiorg > Only select repositories: $FORK (nothing else)."
