#!/usr/bin/env bash
# Independent audit by Antigravity (agy) as the alternate auditor (delegated resolution, #25).
# Run ONLY as aao-auditor-alt (never as the CEO, never as aao-impl-ag):
#   sudo -u aao-auditor-alt -H /opt/aao-audit/run_agy_audit.sh <base_sha> <head_sha> [prompt]
# prompt: r1-chain (default), p2p3-trial or p2p3-dictamen; each is pinned by its reviewed sha256 below.
# Read-only: public clone at the frozen SHA, plan mode, sandbox, clean environment, the reviewed prompt only.
# Writes ~/aao-audits/<head_sha>/{prompt.txt,report.md,attestation.json} and prints their sha256.
set -euo pipefail
umask 022   # report/attestation must not be group-writable: the bootstrap refuses them otherwise
AGY=/usr/local/bin/agy   # root-owned copy; never a binary another account can write
declare -A PROMPTS=([r1-chain]=3ddba5375577292dc75bb0ce04634c7d63f03d20cd74bcf1fca1d232f9246ef9   # reviewed docs/audit-prompts/r1-chain.md
                   [p2p3-trial]=6272f2160ba4281f23b4f9aa32a7a9f3819a8559ee74361beddeb132795b4fb5   # reviewed docs/audit-prompts/p2p3-trial.md
                   [p2p3-dictamen]=a9b2acf1d0b88353d630efcdddffe41605f136f30defa7cfad557e62463c6e66) # reviewed docs/audit-prompts/p2p3-dictamen.md
me=$(id -un); [[ $me == aao-auditor-alt ]] || { echo "refusing: must run as aao-auditor-alt, not $me" >&2; exit 1; }
[[ $# -eq 2 || $# -eq 3 ]] || { echo "usage: $0 <base_sha> <head_sha> [r1-chain|p2p3-trial|p2p3-dictamen]" >&2; exit 2; }
base=$1 head=$2 pname=${3:-r1-chain}
[[ -n ${PROMPTS[$pname]:-} ]] || { echo "unknown prompt $pname" >&2; exit 2; }
PROMPT=/opt/aao-audit/$pname.md PROMPT_SHA256=${PROMPTS[$pname]}
[[ $base =~ ^[0-9a-f]{40}$ && $head =~ ^[0-9a-f]{40}$ ]] || { echo "full 40-hex SHAs required" >&2; exit 2; }
home=$(getent passwd "$me" | cut -d: -f6)
[[ $HOME == "$home" ]] || { echo "refusing: HOME=$HOME is not $me's home ($home)" >&2; exit 1; }
[[ ! -L $AGY && $(stat -c '%u %a' "$AGY") == "0 755" ]] || { echo "refusing: $AGY must be a root:0755 regular file" >&2; exit 1; }
# Every ancestor of the binary root-owned and not group/other writable (no replacing the entry).
for d in /usr/local/bin /usr/local /usr /; do
  [[ ! -L $d && $(stat -c '%u' "$d") == 0 && $(( 0$(stat -c '%a' "$d") & 022 )) == 0 ]] \
    || { echo "refusing: $d lets another account replace $AGY" >&2; exit 1; }
done
# The reviewed prompt: root-owned, not group/other writable, exact digest.
[[ $(stat -c '%u %a' "$PROMPT") == "0 644" ]] || { echo "refusing: $PROMPT must be root:0644" >&2; exit 1; }
[[ $(sha256sum "$PROMPT" | cut -d' ' -f1) == "$PROMPT_SHA256" ]] || { echo "refusing: $PROMPT is not the reviewed prompt" >&2; exit 1; }
# agy session state must belong to this uid only (no copied or shared session).
for d in "$home/.antigravity" "$home/.gemini" "$home/.config" "$home/.config/antigravity"; do
  [[ -e $d || -L $d ]] || continue
  [[ ! -L $d && $(realpath -e "$d") == "$home"/* ]] || { echo "refusing: $d is a symlink or leaves $home" >&2; exit 1; }
  # Only this uid, no group/other write (symlink modes are always 0777, so links are checked by target below).
  bad=$(find "$d" \( ! -uid "$(id -u)" -o \( ! -type l -perm /022 \) \) -print -quit)
  [[ -z $bad ]] || { echo "refusing: $bad is not exclusively $me's" >&2; exit 1; }
  # agy keeps its own links (e.g. cli.log -> log/cli-<date>.log). A link may only resolve inside this same
  # state directory: never to another account's session or anywhere else.
  while IFS= read -r -d '' link; do
    [[ $(realpath -m -- "$link") == "$d"/* ]] || { echo "refusing: symlink $link resolves outside $d" >&2; exit 1; }
  done < <(find "$d" -type l -print0)
  # No other filesystem mounted inside (its content could be another account's session).
  foreign=$(find "$d" -printf '%D %p\n' | awk -v dev="$(stat -c %d "$home")" '$1 != dev {print $2; exit}')
  [[ -z $foreign ]] || { echo "refusing: $foreign is on another filesystem" >&2; exit 1; }
done
out="$home/aao-audits/$head"; [[ $pname == r1-chain ]] || out="$out-$pname"; [[ ! -e $out ]] || { echo "refusing: $out exists (one audit per SHA)" >&2; exit 1; }
mkdir -p -m 0700 "$out"
prior=$(find "$home/.antigravity" "$home/.gemini" "$home/.config/antigravity" -type f 2>/dev/null | wc -l || true)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
# Every git call: no system/global config (so no filters/hooks/credentials), no prompt.
g() { env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
        GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null "$@"; }
g clone -q --no-hardlinks --no-checkout https://github.com/autoaiorg/aao.git "$work/repo"
g -C "$work/repo" cat-file -e "$head^{commit}"; g -C "$work/repo" cat-file -e "$base^{commit}"
g -C "$work/repo" -c advice.detachedHead=false checkout -q "$head"
[[ $(g -C "$work/repo" rev-parse HEAD) == "$head" ]]
sed -e "s/{{BASE}}/$base/g" -e "s/{{HEAD}}/$head/g" "$PROMPT" > "$out/prompt.txt"
# agy with a clean environment: only this uid's HOME; nothing inherited from the caller.
( cd "$work/repo" && env -i PATH=/usr/bin:/bin:/usr/local/bin HOME="$home" USER="$me" LOGNAME="$me" LANG=C.UTF-8 \
    "$AGY" --mode plan --sandbox --effort high --print-timeout 0 -p="$(cat "$out/prompt.txt")" < /dev/null ) > "$out/report.md"
cat > "$out/attestation.json" <<JSON
{"auditor":"antigravity","os_user":"$me","uid":$(id -u),"base":"$base","head":"$head",
 "checked_out_head":"$(g -C "$work/repo" rev-parse HEAD)","prompt_name":"$pname","prompt_template_sha256":"$PROMPT_SHA256",
 "agy_sha256":"$(sha256sum "$AGY" | cut -d' ' -f1)","agy_version":"$("$AGY" --version 2>/dev/null | head -1 | tr -d '"')","prior_agy_state_files":$prior,
 "prompt_sha256":"$(sha256sum "$out/prompt.txt" | cut -d' ' -f1)",
 "report_sha256":"$(sha256sum "$out/report.md" | cut -d' ' -f1)","finished_at":"$(date -u +%FT%TZ)"}
JSON
sha256sum "$out/report.md" "$out/attestation.json"
