#!/usr/bin/env bash
# Substitute audit by Codex as aao-auditor-alt, ONLY under the CEO exception CEO-DEC-AUDIT-CODEX-2026-10-24
# (Antigravity quota exhausted). Same contract as run_agy_audit.sh: run ONLY as aao-auditor-alt:
#   sudo -u aao-auditor-alt -H /opt/aao-audit/run_codex_audit.sh <base_sha> <head_sha> [prompt]
# Read-only: public clone at the frozen SHA, `codex exec --sandbox read-only --ephemeral`, clean environment,
# the reviewed prompt plus a fixed exception preamble. Codex authored parts of the audited code: it must declare
# that recusal and mark those findings `self-authored` instead of stopping (the exception record says so).
# Writes ~/aao-audits/<head_sha>[-prompt]/{prompt.txt,report.md,attestation.json} with "auditor":"codex".
set -euo pipefail
umask 022
CODEX=/usr/local/bin/codex
CODEX_SHA256=b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306  # openai/codex rust-v0.164.0 musl, release asset
EXCEPTION=CEO-DEC-AUDIT-CODEX-2026-10-24
declare -A PROMPTS=([r1-chain]=3ddba5375577292dc75bb0ce04634c7d63f03d20cd74bcf1fca1d232f9246ef9
                   [p2p3-trial]=6272f2160ba4281f23b4f9aa32a7a9f3819a8559ee74361beddeb132795b4fb5
                   [p2p3-dictamen]=a9b2acf1d0b88353d630efcdddffe41605f136f30defa7cfad557e62463c6e66)
me=$(id -un); [[ $me == aao-auditor-alt ]] || { echo "refusing: must run as aao-auditor-alt, not $me" >&2; exit 1; }
[[ $# -eq 2 || $# -eq 3 ]] || { echo "usage: $0 <base_sha> <head_sha> [r1-chain|p2p3-trial|p2p3-dictamen]" >&2; exit 2; }
base=$1 head=$2 pname=${3:-r1-chain}
[[ -n ${PROMPTS[$pname]:-} ]] || { echo "unknown prompt $pname" >&2; exit 2; }
PROMPT=/opt/aao-audit/$pname.md PROMPT_SHA256=${PROMPTS[$pname]}
[[ $base =~ ^[0-9a-f]{40}$ && $head =~ ^[0-9a-f]{40}$ ]] || { echo "full 40-hex SHAs required" >&2; exit 2; }
home=$(getent passwd "$me" | cut -d: -f6)
[[ $HOME == "$home" ]] || { echo "refusing: HOME=$HOME is not $me's home ($home)" >&2; exit 1; }
[[ ! -L $CODEX && $(stat -c '%u %a' "$CODEX") == "0 755" ]] || { echo "refusing: $CODEX must be a root:0755 regular file" >&2; exit 1; }
[[ $(sha256sum "$CODEX" | cut -d' ' -f1) == "$CODEX_SHA256" ]] || { echo "refusing: $CODEX is not the pinned release binary" >&2; exit 1; }
for d in /usr/local/bin /usr/local /usr /; do
  [[ ! -L $d && $(stat -c '%u' "$d") == 0 && $(( 0$(stat -c '%a' "$d") & 022 )) == 0 ]] \
    || { echo "refusing: $d lets another account replace $CODEX" >&2; exit 1; }
done
[[ $(stat -c '%u %a' "$PROMPT") == "0 644" ]] || { echo "refusing: $PROMPT must be root:0644" >&2; exit 1; }
[[ $(sha256sum "$PROMPT" | cut -d' ' -f1) == "$PROMPT_SHA256" ]] || { echo "refusing: $PROMPT is not the reviewed prompt" >&2; exit 1; }
# Codex session state must belong to this uid only (its own login; never a copied credential).
d="$home/.codex"
[[ -d $d && ! -L $d && $(realpath -e "$d") == "$home"/* ]] || { echo "refusing: $d missing (log in once: sudo -u $me -H $CODEX login --device-auth)" >&2; exit 1; }
bad=$(find "$d" \( ! -uid "$(id -u)" -o \( ! -type l -perm /022 \) \) -print -quit)
[[ -z $bad ]] || { echo "refusing: $bad is not exclusively $me's" >&2; exit 1; }
while IFS= read -r -d '' link; do
  [[ $(realpath -m -- "$link") == "$d"/* ]] || { echo "refusing: symlink $link resolves outside $d" >&2; exit 1; }
done < <(find "$d" -type l -print0)
out="$home/aao-audits/$head"; [[ $pname == r1-chain ]] || out="$out-$pname"; [[ ! -e $out ]] || { echo "refusing: $out exists (one audit per SHA)" >&2; exit 1; }
mkdir -p -m 0700 "$out"
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
g() { env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
        GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null "$@"; }
g clone -q --no-hardlinks --no-checkout https://github.com/autoaiorg/aao.git "$work/repo"
g -C "$work/repo" cat-file -e "$head^{commit}"; g -C "$work/repo" cat-file -e "$base^{commit}"
g -C "$work/repo" -c advice.detachedHead=false checkout -q "$head"
[[ $(g -C "$work/repo" rev-parse HEAD) == "$head" ]]
{
  printf '%s\n' "EXCEPCIÓN $EXCEPTION: actúas como AUDITOR SUSTITUTO de Antigravity (cuota agotada), por decisión del CEO." \
    "Codex escribió partes del código auditado (canal de incidentes B-1, supervisor watch y correcciones de src/aao/github_trial.py)." \
    "No te detengas por eso: declara esa recusación al principio, audita TODO el alcance igualmente y marca como 'self-authored'" \
    "cada hallazgo sobre código escrito por Codex. Aplica el mismo rigor y la misma regla de parada que el encargo." \
    "Puedes leer con cualquier comando de solo lectura (el entorno es de solo lectura); no ejecutes pruebas." ""
  sed -e "s/{{BASE}}/$base/g" -e "s/{{HEAD}}/$head/g" "$PROMPT"
} > "$out/prompt.txt"
( cd "$work/repo" && env -i PATH=/usr/bin:/bin:/usr/local/bin HOME="$home" USER="$me" LOGNAME="$me" LANG=C.UTF-8 CODEX_HOME="$d" \
    "$CODEX" exec --sandbox read-only --ephemeral --skip-git-repo-check -c model_reasoning_effort=high \
    --output-last-message "$out/report.md" - < "$out/prompt.txt" ) > "$out/codex.log" 2>&1
[[ -s $out/report.md ]] || { echo "refusing: codex produced no report (see $out/codex.log)" >&2; exit 1; }
cat > "$out/attestation.json" <<JSON
{"auditor":"codex","exception":"$EXCEPTION","os_user":"$me","uid":$(id -u),"base":"$base","head":"$head",
 "checked_out_head":"$(g -C "$work/repo" rev-parse HEAD)","prompt_name":"$pname","prompt_template_sha256":"$PROMPT_SHA256",
 "codex_sha256":"$(sha256sum "$CODEX" | cut -d' ' -f1)","codex_version":"$("$CODEX" --version 2>/dev/null | head -1 | tr -d '"')",
 "prompt_sha256":"$(sha256sum "$out/prompt.txt" | cut -d' ' -f1)",
 "report_sha256":"$(sha256sum "$out/report.md" | cut -d' ' -f1)","finished_at":"$(date -u +%FT%TZ)"}
JSON
sha256sum "$out/report.md" "$out/attestation.json"
