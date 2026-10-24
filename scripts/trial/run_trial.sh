#!/bin/bash -p
set -euo pipefail
[[ $- == *p* ]] || { echo 'FAIL: invoke directly as root' >&2; exit 2; }
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP LD_PRELOAD LD_LIBRARY_PATH
REV= ONLY=()
while (($#)); do case $1 in
  --rev) (($# >= 2)) || exit 2; REV=$2; shift;;
  --only) (($# >= 2)) || exit 2; IFS=, read -r -a ONLY <<<"$2"; shift;;
  *) echo "unknown argument: $1" >&2; exit 2;; esac; shift; done
[[ $EUID == 0 && $REV =~ ^[0-9a-f]{40}$ ]] || { echo 'FAIL: root and --rev <40-hex> required' >&2; exit 2; }
CEO=${SUDO_USER:-}; [[ -n $CEO && $CEO != root ]] || { echo 'FAIL: run via sudo from the CEO login' >&2; exit 2; }
[[ $CEO == alessbarb ]] || { echo 'FAIL: SUDO_USER must be the configured CEO alessbarb' >&2; exit 2; }
SRC=/root/aao-src; REPO=autoaiorg/aao-governance-trial
GIT=(/usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null -c safe.directory='*')
die(){ echo "FAIL: $*" >&2; exit 1; }
role_work_safe(){ /usr/bin/python3 -I "$INSTALL/src/aao/trial_security.py" "$1" "$(id -u "$2")"; }
[[ -d $SRC/.git && ! -L $SRC/.git ]] || die "$SRC must be a root-owned plain git clone"
[[ -z $(find "$SRC" \( ! -uid 0 -o \( ! -type l -perm /022 \) \) -print -quit) ]] || die "$SRC must be entirely root-owned and not group/other writable"
origin=$("${GIT[@]}" -C "$SRC" remote get-url origin)
[[ $origin =~ (^|[:/])autoaiorg/aao(\.git)?$ ]] || die "$SRC origin must be autoaiorg/aao"
"${GIT[@]}" -C "$SRC" cat-file -e "$REV^{commit}" || die "revision absent from root clone"
script=$(readlink -f -- "$0"); [[ $script == "$SRC/scripts/trial/run_trial.sh" ]] || die "invoke the pinned runner from $SRC/scripts/trial/run_trial.sh"
[[ $(stat -c '%u %a' "$script") == '0 755' ]] || die 'runner must be root-owned mode 0755'
blob_sha=$("${GIT[@]}" -C "$SRC" show "$REV:scripts/trial/run_trial.sh" | sha256sum | cut -d' ' -f1)
file_sha=$(sha256sum "$script" | cut -d' ' -f1)
[[ $blob_sha == "$file_sha" ]] || die "runner bytes do not match scripts/trial/run_trial.sh at $REV"
# Export only src/ from Git objects; no working-tree content or hooks/config is trusted.
[[ ! -L /opt/aao-trial ]] || die '/opt/aao-trial must not be a symlink'
install -d -o root -g root -m 0755 /opt/aao-trial
INSTALL=/opt/aao-trial/$REV
if [[ -e $INSTALL ]]; then
  [[ ! -L $INSTALL && $(stat -c '%u' "$INSTALL") == 0 ]] || die "$INSTALL is not a safe root-owned directory"
  [[ -z $(find "$INSTALL" \( ! -uid 0 -o -perm /022 \) -print -quit) ]] || die "$INSTALL contains non-root-owned or writable content"
fi
install -d -o root -g root -m 0755 "$INSTALL"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
"${GIT[@]}" -C "$SRC" archive "$REV" src | tar -x -C "$tmp"
chown -R root:root "$tmp/src"; chmod -R go-w "$tmp/src"
if [[ -e $INSTALL/src ]]; then [[ -d $INSTALL/src && ! -L $INSTALL/src && $(stat -c '%u' "$INSTALL/src") == 0 ]] || die "$INSTALL/src is not a safe root-owned directory"; rm -rf -- "$INSTALL/src"; fi
install -d -o root -g root -m 0755 "$INSTALL/src"; cp -a "$tmp/src/." "$INSTALL/src/"
REG=$tmp/registry.json
"${GIT[@]}" -C "$SRC" show "$REV:deploy/github-apps/aao-github-apps-registry.json" >"$REG" || die 'registry missing at pinned revision'
WORK_PARENT=/var/lib/aao-trial
WORK_ROOT=$WORK_PARENT/work
[[ ! -L /var/lib && ! -L $WORK_PARENT && ! -L $WORK_ROOT ]] || die 'trial work path must not contain symlinks'
if [[ -e $WORK_PARENT ]]; then [[ -d $WORK_PARENT && $(stat -c '%u:%g %a' "$WORK_PARENT") == '0:0 755' ]] || die 'trial work parent must be root:root 0755'; fi
install -d -o root -g root -m 0755 "$WORK_PARENT"
if [[ -e $WORK_ROOT ]]; then [[ -d $WORK_ROOT && $(stat -c '%u:%g %a' "$WORK_ROOT") == '0:0 755' ]] || die 'trial work root must be root:root 0755'; fi
install -d -o root -g root -m 0755 "$WORK_ROOT"
mapfile -t APPS < <(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); [print(a["name"],a["linux_uid"]) for a in d["apps"]]' "$REG")
# Verify the exact three live trial rulesets, including the auditor identity on B.
check_rulesets(){
  local list details id data; list=$(runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api "repos/$REPO/rulesets?includes_parents=true") || return 1
  details=$(python3 -I -c 'import json,sys; rows=json.load(sys.stdin); want={"A main: integrator only":25776805,"B main+staging: integrity (no bypass)":25776806,"C tags":25776807}; by={r.get("name"):r.get("id") for r in rows}; print("\n".join(str(by.get(n) or i) for n,i in want.items()))' <<<"$list") || return 1
  while IFS= read -r id; do data=$(runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api "repos/$REPO/rulesets/$id") || return 1; printf '%s\n' "$data"; done <<<"$details" | python3 -I -c 'import json,sys; rows=[json.loads(x) for x in sys.stdin]; a,b,c=rows; ok=[x.get("name") for x in rows]==["A main: integrator only","B main+staging: integrity (no bypass)","C tags"] and all(x.get("enforcement")=="active" for x in rows); rules=b.get("rules",[]); required=next((r.get("parameters",{}).get("required_status_checks",[]) for r in rules if r.get("type")=="required_status_checks"),[]); arules={r.get("type") for r in a.get("rules",[])}; brules={r.get("type") for r in rules}; crules={r.get("type") for r in c.get("rules",[])}; abypass=a.get("bypass_actors",[]); ok=ok and {x.get("context"):x.get("integration_id") for x in required}.get("aao-audit")==5448107 and "test" in {x.get("context") for x in required} and not b.get("bypass_actors") and "non_fast_forward" in brules and "deletion" in brules and {"update","pull_request"}.issubset(arules) and [(x.get("actor_id"),x.get("actor_type")) for x in abypass]==[(5447984,"Integration")] and c.get("target")=="tag" and {"creation","update","deletion"}.issubset(crules); sys.exit(0 if ok else 1)'
}
check_rulesets || die 'trial rulesets A/B/C are not active with required auditor/test and no B bypass'
# Pin the protected trial repository identity once, using the integrator App's
# installation credential. Every equivalence record receives this immutable
# start-of-run observation and compares the id again.
integrator_target_identity(){ runuser -u aao-integrator -- env -i HOME="$(getent passwd aao-integrator|cut -d: -f6)" PATH=/usr/bin:/bin /usr/bin/python3 -I -c 'import json,sys;sys.path.insert(0,"'"$INSTALL"'/src");from aao.github_app_auth import GitHubAppClient
c=GitHubAppClient("aao-integrator")
try:
 c.installation_token(*sys.argv[1].split("/",1));r=c.request("GET","/repos/"+sys.argv[1]);b=r.body if isinstance(r.body,dict) else {};print(json.dumps({"status":r.status,"full_name":b.get("full_name"),"id":b.get("id")}))
finally:c.close()' "$REPO" 2>/dev/null || printf '%s' '{"status":0}'; }
P0_JSON=$(integrator_target_identity)
EXPECTED_REPO_ID=$(python3 -I -c 'import json,sys;d=json.loads(sys.argv[1]);print(d.get("id") if isinstance(d.get("id"),int) else 0)' "$P0_JSON")
gh_read(){ runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api --paginate "$1" --jq '.[].login' 2>/dev/null || printf '%s\n' '__GH_API_ERROR__'; }
gh_keys(){ runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api --paginate "$1" --jq '.[].id' 2>/dev/null || printf '%s\n' '__GH_API_ERROR__'; }
# P4: root asks the system manager. Inactive user@UID and no linger means no user service is running at check
# time; the role side also rejects GH_TOKEN/GITHUB_TOKEN in its user unit and environment.d files (units that
# would carry a token once a manager starts). Any other manager state fails P4 closed.
user_manager_state(){
  local n st; n=$(id -u "$1" 2>/dev/null) || { printf unknown; return; }
  [[ -e /var/lib/systemd/linger/$1 ]] && { printf lingering; return; }
  st=$(systemctl is-active "user@$n.service" 2>/dev/null || true)
  [[ $st == inactive ]] && printf absent || printf '%s' "${st:-unknown}"
}
collect_impl_p4(){
  local uid=$1 home=$2 app=$3 forks=$4 local_json outside members keys_ok keys_listing
  local_json=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin /usr/bin/python3 -I -c 'import json,os,pathlib,subprocess,sys
h=pathlib.Path.home(); app=sys.argv[1]; gh=h/".config/gh/hosts.yml"; cred=h/".git-credentials"; conf=h/".config/aao"
expected={app+".pem",app+".json"}; actual={p.name for p in conf.iterdir()} if conf.is_dir() else set()
state=sys.argv[2]; tokens=[] if state=="absent" else ["systemd-user-manager-"+state]
for d in (h/".config/systemd/user", h/".config/environment.d"):
 for f in (sorted(d.rglob("*")) if d.is_dir() else []):
  try: text=f.read_text(errors="replace") if f.is_file() else ""
  except OSError: text="GH_TOKEN="
  if "GH_TOKEN" in text or "GITHUB_TOKEN" in text: tokens.append("user-unit-token:"+str(f.relative_to(h)))
print(json.dumps({"gh_hosts_yml_absent":not gh.exists(),"git_credentials_absent":not cred.exists(),"token_environment_absent":not tokens,
"runner_environment_token_absent":True,"runner_environment":"runuser env -i allowlist; no GH_TOKEN/GITHUB_TOKEN passed",
"aao_config_exact":actual==expected,"uid":os.getuid(),"config_names":sorted(actual),"systemd_user_manager":state,"systemd_checked":state=="absent"}))' "$app" "$(user_manager_state "$uid")" 2>/dev/null || printf '%s' '{}')
  outside=$(gh_read "repos/$REPO/collaborators?affiliation=outside&per_page=100" || true)
  members=$(gh_read "orgs/autoaiorg/members?per_page=100" || true)
  keys_ok=true
  keys_listing=''
  local target key_ids
  IFS=, read -r -a fork_list <<<"$forks"
  for target in "$REPO" "${fork_list[@]}"; do
    key_ids=$(gh_keys "repos/$target/keys?per_page=100")
    keys_listing+="${target}=[${key_ids//$'\n'/,}];"
    [[ -z $key_ids ]] || keys_ok=false
  done
  python3 -I -c 'import json,sys; p=json.loads(sys.argv[1]); outside=sys.argv[2].splitlines(); members=sys.argv[3].splitlines(); ids={x.lower() for x in ("aao-impl-claude","aao-impl-codex","aao-impl-agy","aao-impl-claude[bot]","aao-impl-codex[bot]","aao-impl-agy[bot]")}; p.update({"deploy_keys_empty":sys.argv[4]=="true","deploy_keys_by_repository":sys.argv[5],"outside_collaborators_clear":"__GH_API_ERROR__" not in outside and not [x for x in outside if x],"org_members_clear":"__GH_API_ERROR__" not in members and not any(x.lower() in ids for x in members),"outside_collaborators":outside,"org_members":members}); print(json.dumps(p))' "$local_json" "$outside" "$members" "$keys_ok" "$keys_listing"
}
collect_p4b(){
  local owners admins login
  owners=$(gh_read "orgs/autoaiorg/members?role=admin&per_page=100" || true)
  admins=$(gh_read "repos/$REPO/collaborators?permission=admin&per_page=100" || true)
  login=$(runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api user --jq .login 2>/dev/null || printf '%s' '__GH_API_ERROR__')
  python3 -I -c 'import json,sys;print(json.dumps({"ceo_login":sys.argv[3].lower(),"org_owners":sorted(x.lower() for x in sys.argv[1].splitlines() if x),"repo_admins":sorted(x.lower() for x in sys.argv[2].splitlines() if x)}))' "$owners" "$admins" "$login"
}
TS=$(date -u +%Y%m%dT%H%M%S.%NZ); export AAO_TRIAL_RUN_ID=$TS AAO_TRIAL_HARNESS_REV=$REV; LOG=/var/log/aao-trial/$TS; install -d -o root -g root -m 0750 "$LOG"
capture_evidence(){
  local uid=$1 home=$2 test_id=$3 role=${4:-} source dest
  source=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_ROLE="$role" /usr/bin/python3 -I -c 'import glob,json,os,sys; matches=[]
for p in glob.glob(os.path.join(sys.argv[1], "aao-trial-evidence", sys.argv[2]+"-*.json")):
 try:
  st=os.lstat(p)
  if not os.path.isfile(p) or os.path.islink(p) or st.st_uid != os.getuid(): continue
  d=json.load(open(p, encoding="utf-8"))
  if d.get("run_id")==os.environ["AAO_TRIAL_RUN_ID"] and (not os.environ.get("AAO_TRIAL_ROLE") or d.get("role")==os.environ["AAO_TRIAL_ROLE"]): matches.append((os.path.getmtime(p),p))
 except (OSError,ValueError): pass
print(max(matches)[1] if matches else "")' "$home" "$test_id") || return 1
  [[ -n $source ]] || return 1
  dest=$LOG/collected-${uid}-${test_id}-${role:-role}.json
  runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin /bin/cat -- "$source" >"$dest" || { rm -f -- "$dest"; return 1; }
  chown root:root "$dest"; chmod 0640 "$dest"; printf '%s\n' "$dest"
}
fixture_num= fixture_head=
need_pr=0; for id in "${ONLY[@]}"; do [[ $id != A-02 && $id != P3-09 && $id != A-05 && $id != P3-06 ]] || need_pr=1; done
if ((${#ONLY[@]} == 0)); then need_pr=1; fi
make_fixture_pr(){
  ceohome=$(getent passwd "$CEO" | cut -d: -f6)
  # Create a uniquely named open PR only in the disposable trial repository.
  fixture_ts=$(date -u +%Y%m%dT%H%M%S%NZ); branch="aao-trial/runner-$fixture_ts"
  main_sha=$(runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh api "repos/$REPO/git/ref/heads/main" --jq .object.sha)
  blob=$(runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh api -X POST "repos/$REPO/git/blobs" -f content="AAO disposable trial fixture $fixture_ts" -f encoding=utf-8 --jq .sha)
  # gh -f cannot express an array of objects (tree[0][path] becomes an object): send the JSON body on stdin.
  tree=$(python3 -I -c 'import json,sys; print(json.dumps({"base_tree": sys.argv[1], "tree": [{"path": sys.argv[2], "mode": "100644", "type": "blob", "sha": sys.argv[3]}]}))' "$main_sha" "trial-fixtures/$fixture_ts.txt" "$blob" | runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh api -X POST "repos/$REPO/git/trees" --input - --jq .sha)
  commit=$(runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh api -X POST "repos/$REPO/git/commits" -f message="AAO trial fixture $fixture_ts" -f "tree=$tree" -f "parents[]=$main_sha" --jq .sha)
  runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh api -X POST "repos/$REPO/git/refs" -f "ref=refs/heads/$branch" -f "sha=$commit" >/dev/null
  runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh pr create --repo "$REPO" --base main --head "$branch" --title "AAO disposable trial fixture $fixture_ts" --body 'Runner-created disposable fixture; do not merge manually.' >/dev/null
  pr=$(runuser -u "$CEO" -- env -i HOME="$ceohome" PATH=/usr/bin:/bin gh pr view "$branch" --repo "$REPO" --json number,headRefOid)
  fixture_num=$(python3 -I -c 'import json,sys;d=json.loads(sys.stdin.read());print(d["number"])' <<<"$pr")
  fixture_head=$(python3 -I -c 'import json,sys;d=json.loads(sys.stdin.read());print(d["headRefOid"])' <<<"$pr")
}
if ((need_pr)); then make_fixture_pr; fi
declare -a IDS=(A-01 A-02 A-03 A-04 A-05 A-06 A-09 A-12 A-14 P3-01 P3-02 P3-03 P3-05 P3-06 P3-07 P3-09 P3-12)
declare -A ROLE=([A-01]=aao-impl-codex [A-02]=aao-impl-codex [A-03]=aao-integrator [A-04]=aao-integrator [A-05]=aao-integrator [A-06]=aao-auditor [A-09]=aao-notifier [A-12]=aao-integrator [A-14]=aao-probe-noworkflows [P3-01]=ceo [P3-02]=aao-impl-codex [P3-03]=aao-integrator [P3-05]=aao-integrator [P3-06]=aao-integrator [P3-07]=aao-integrator [P3-09]=ceo [P3-12]=aao-integrator)
declare -A APP_UID=(); for row in "${APPS[@]}"; do read -r app uid <<<"$row"; APP_UID[$app]=$uid; done
APP_UID[aao-probe-noworkflows]=aao-probe-noworkflows
printf 'test\trole\tstatus\tevidence\n' | tee "$LOG/summary.tsv"
rc=0
for id in "${IDS[@]}"; do
  if ((${#ONLY[@]})) && [[ ! " ${ONLY[*]} " =~ " $id " ]]; then continue; fi
  if [[ $id == A-05 || $id == P3-06 ]]; then make_fixture_pr; fi
  role=${ROLE[$id]}; uid=${APP_UID[$role]:-$CEO}; [[ $role == ceo ]] && uid=$CEO
  target=$REPO; clone_name=trial
  [[ $id != A-14 ]] || { target=autoaiorg/aao-trial-probe; clone_name=probe; }
  home=$(getent passwd "$uid" | cut -d: -f6); [[ -n $home ]] || { printf '%s\t%s\tFAIL\tmissing uid\n' "$id" "$role" | tee -a "$LOG/summary.tsv"; rc=1; continue; }
  work=$WORK_ROOT/$uid
  [[ ! -L $work ]] || die "role work directory is a symlink: $work"
  if [[ -e $work ]]; then role_work_safe "$work" "$uid" || die "unsafe role work directory: $work"; else install -d -o "$uid" -g "$(id -gn "$uid")" -m 0700 "$work"; fi
  [[ ! -L $work ]] && role_work_safe "$work" "$uid" || die "role work directory failed ownership/mode validation: $work"
  runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin mkdir -p "$work/$TS"
  clone=$work/$TS/$clone_name
  if [[ ! -d $clone/.git ]]; then runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false clone --quiet "https://github.com/$target.git" "$clone" || { printf '%s\t%s\tFAIL\tclone failed\n' "$id" "$role" | tee -a "$LOG/summary.tsv"; rc=1; continue; }; fi
  # A disposable child commit is available for tests which need a distinct candidate.
  runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" fetch --quiet origin main || { printf '%s\t%s\tFAIL\torigin main fetch failed\n' "$id" "$role" | tee -a "$LOG/summary.tsv"; rc=1; continue; }
  if [[ $id == P3-07 || $id == P3-12 ]]; then
    # Divergent candidate (parent main^, so not a descendant of main) carrying main's tree, so it still has the
    # CI workflow and the required `test` check can turn green before the forced push.
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" checkout -q -B trial-candidate origin/main^
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" checkout -q origin/main -- .
  else
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" checkout -q -B trial-candidate origin/main
  fi
  if [[ $id == A-14 ]]; then
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" -c user.name='AAO Trial Fixture' -c user.email=trial-fixture@users.noreply.github.com commit --allow-empty -m 'AAO workflow probe fixture' >/dev/null
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin mkdir -p "$clone/.github/workflows"
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin /bin/sh -c 'printf "name: trial-probe\non: push\njobs:\n  probe:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo probe\n" > "$1/.github/workflows/probe.yml"' sh "$clone"
  fi
  if [[ $id == A-14 ]]; then
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" add .github/workflows/probe.yml
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" -c user.name='AAO Trial Fixture' -c user.email=trial-fixture@users.noreply.github.com commit -m 'Add workflow probe fixture' >/dev/null
  else
    runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" -c user.name='AAO Trial Fixture' -c user.email=trial-fixture@users.noreply.github.com commit --allow-empty -m "AAO trial fixture $id" >/dev/null
  fi
  args=("$id" --repo "$target" --role "$role")
  allow="$REPO"; [[ $id != A-14 ]] || allow="$REPO,$target"
  envs=(HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$allow" AAO_GITHUB_TRIAL_FORK_PARENT="$REPO" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" AAO_TRIAL_CANDIDATE_SHA=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" rev-parse HEAD))
  case $id in A-02|P3-09|A-05|P3-06) envs+=(AAO_GITHUB_TRIAL_PR="$fixture_num" AAO_GITHUB_TRIAL_PR_HEAD="$fixture_head");; esac
  case $id in A-01|A-02|P3-02)
    impl_fork=autoaiorg/aao-trial-codex; envs+=(AAO_GITHUB_TRIAL_FORK="$impl_fork" AAO_GITHUB_TRIAL_FORKS="autoaiorg/aao-codex,$impl_fork")
    p0_run_json=$(integrator_target_identity)
    p4_json=$(collect_impl_p4 "$uid" "$home" "$role" "autoaiorg/aao-codex,$impl_fork")
    p4b_json=$(collect_p4b)
    envs+=(AAO_TRIAL_P0_EVIDENCE="$p0_run_json" AAO_TRIAL_EXPECTED_REPO_ID="$EXPECTED_REPO_ID" AAO_TRIAL_P4_EVIDENCE="$p4_json" AAO_TRIAL_P4B_EVIDENCE="$p4b_json")
    args+=(--equivalence);;
  esac
  case $id in A-05|P3-06) envs+=(AAO_GITHUB_TRIAL_PHASE=stage);; esac
  # Seed the exact required audit check only after the candidate exists in the trial repo.
  if [[ $id == A-03 || $id == A-04 || $id == P3-05 || $id == P3-07 || $id == P3-12 ]]; then
    candidate=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" rev-parse HEAD)
    set +e
    (cd "$clone" && runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_BRANCH="aao-trial/required-$id-$TS" AAO_GITHUB_TRIAL_EXPECTED_SHA="$candidate" AAO_TRIAL_CANDIDATE_SHA="$candidate" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" STAGE-COMMIT --repo "$REPO" --role aao-integrator --branch "aao-trial/required-$id") >"$LOG/$id-STAGE-COMMIT.out" 2>&1
    helper_rc=$?
    set -e
    cat "$LOG/$id-STAGE-COMMIT.out"
    if ((helper_rc != 0)); then helper_reason=$(head -n 1 "$LOG/$id-STAGE-COMMIT.out"); printf '%s\t%s\tFAIL\t%s\n' "$id" "$role" "$helper_reason" | tee -a "$LOG/summary.tsv"; rc=1; continue; fi
    staged_sha=$(grep -Eo 'staged local commit [0-9a-f]{40}' "$LOG/$id-STAGE-COMMIT.out" | awk '{print $4}' | tail -1)
    if [[ $staged_sha != "$candidate" ]]; then printf '%s\t%s\tFAIL\tSTAGE-COMMIT SHA mismatch\n' "$id" "$role" | tee -a "$LOG/summary.tsv"; rc=1; continue; fi
    auditor_home=$(getent passwd "${APP_UID[aao-auditor]}" | cut -d: -f6)
    auditor_work=$WORK_ROOT/${APP_UID[aao-auditor]}; [[ ! -L $auditor_work ]] || die 'auditor work directory is a symlink'
    if [[ ! -e $auditor_work ]]; then install -d -o "${APP_UID[aao-auditor]}" -g "$(id -gn "${APP_UID[aao-auditor]}")" -m 0700 "$auditor_work"; fi
    role_work_safe "$auditor_work" "${APP_UID[aao-auditor]}" || die 'unsafe auditor work directory'
    runuser -u "${APP_UID[aao-auditor]}" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin mkdir -p "$auditor_work/$TS"
    auditor_clone=$auditor_work/$TS/trial
    if [[ ! -d $auditor_clone/.git ]]; then runuser -u "${APP_UID[aao-auditor]}" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false clone --quiet "https://github.com/$REPO.git" "$auditor_clone"; fi
    set +e
    (cd "$auditor_clone" && runuser -u "${APP_UID[aao-auditor]}" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_SHA="$candidate" AAO_TRIAL_CANDIDATE_SHA="$candidate" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" PUBLISH-AUDIT --repo "$REPO" --role aao-auditor) >"$LOG/$id-PUBLISH-AUDIT.out" 2>&1
    helper_rc=$?
    set -e
    cat "$LOG/$id-PUBLISH-AUDIT.out"
    if ((helper_rc != 0)); then helper_reason=$(head -n 1 "$LOG/$id-PUBLISH-AUDIT.out"); printf '%s\t%s\tFAIL\t%s\n' "$id" "$role" "$helper_reason" | tee -a "$LOG/summary.tsv"; rc=1; continue; fi
  fi
  if [[ $id == A-05 || $id == P3-06 ]]; then runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" fetch --quiet origin "refs/pull/$fixture_num/head"; fi
  set +e
  (cd "$clone" && runuser -u "$uid" -- env -i "${envs[@]}" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" "${args[@]}") >"$LOG/$id-$role.out" 2>&1
  status=$?
  set -e
  cat "$LOG/$id-$role.out"
  evidence=$(capture_evidence "$uid" "$home" "$id" "$role" || true)
  state='NOT RUN (no evidence from this run)'; [[ -n $evidence ]] && state=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status","FAIL"))' "$evidence")
  if [[ ( $id == A-05 || $id == P3-06 ) && $state == STAGED ]]; then
    merge_sha=$(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(x["sha"] for x in d["evidence"] if x.get("method")=="staged merge commit"))' "$evidence")
    auditor_home=$(getent passwd "${APP_UID[aao-auditor]}" | cut -d: -f6); auditor_clone=$WORK_ROOT/${APP_UID[aao-auditor]}/$TS/trial
    set +e
    runuser -u "${APP_UID[aao-auditor]}" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_SHA="$merge_sha" AAO_TRIAL_CANDIDATE_SHA="$merge_sha" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" PUBLISH-AUDIT --repo "$REPO" --role aao-auditor >"$LOG/$id-PUBLISH-AUDIT.out" 2>&1
    helper_rc=$?
    set -e
    cat "$LOG/$id-PUBLISH-AUDIT.out"
    if ((helper_rc != 0)); then state=FAIL; status=1; rc=1; fi
    if ((helper_rc == 0)); then
    promote_envs=(HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_PR="$fixture_num" AAO_GITHUB_TRIAL_PR_HEAD="$fixture_head" AAO_GITHUB_TRIAL_PHASE=promote AAO_GITHUB_TRIAL_PROMOTE_SHA="$merge_sha" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" AAO_TRIAL_CANDIDATE_SHA="$merge_sha")
    set +e
    (cd "$clone" && runuser -u "$uid" -- env -i "${promote_envs[@]}" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" "$id" --repo "$REPO" --role "$role") >"$LOG/$id-$role-promote.out" 2>&1
    status=$?
    set -e
    cat "$LOG/$id-$role-promote.out"
    evidence=$(capture_evidence "$uid" "$home" "$id" "$role" || true)
    [[ -n $evidence ]] && state=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status","FAIL"))' "$evidence")
    fi
  fi
  printf '%s\t%s\t%s\t%s\n' "$id" "$role" "$state" "${evidence:-none}" | tee -a "$LOG/summary.tsv"
  true
  [[ $state != FAIL ]] || rc=1
  [[ $status -ne 1 || $state == FAIL ]] || rc=1
  if [[ $id == A-01 || $id == A-02 || $id == P3-02 ]]; then
    for impl in aao-impl-claude aao-impl-agy; do
      impl_uid=${APP_UID[$impl]}; impl_home=$(getent passwd "$impl_uid" | cut -d: -f6); impl_work=$WORK_ROOT/$impl_uid
      [[ ! -L $impl_work ]] || die "role work directory is a symlink: $impl_work"
      if [[ -e $impl_work ]]; then role_work_safe "$impl_work" "$impl_uid" || die "unsafe role work directory: $impl_work"; else install -d -o "$impl_uid" -g "$(id -gn "$impl_uid")" -m 0700 "$impl_work"; fi
      runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin mkdir -p "$impl_work/$TS"
      impl_clone=$impl_work/$TS/trial
      if [[ ! -d $impl_clone/.git ]]; then runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false clone --quiet "https://github.com/$REPO.git" "$impl_clone"; fi
      runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$impl_clone" fetch --quiet origin main
      impl_fork=autoaiorg/aao-trial-claude; production_fork=autoaiorg/aao-claude; [[ $impl != aao-impl-agy ]] || { impl_fork=autoaiorg/aao-trial-agy; production_fork=autoaiorg/aao-agy; }
      impl_p0=$(integrator_target_identity)
      impl_p4=$(collect_impl_p4 "$impl_uid" "$impl_home" "$impl" "$production_fork,$impl_fork")
      impl_p4b=$(collect_p4b)
      set +e
      (cd "$impl_clone" && runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_FORKS="$production_fork,$impl_fork" AAO_GITHUB_TRIAL_FORK="$impl_fork" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" AAO_TRIAL_P0_EVIDENCE="$impl_p0" AAO_TRIAL_EXPECTED_REPO_ID="$EXPECTED_REPO_ID" AAO_TRIAL_P4_EVIDENCE="$impl_p4" AAO_TRIAL_P4B_EVIDENCE="$impl_p4b" AAO_TRIAL_CANDIDATE_SHA=$(runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$impl_clone" rev-parse origin/main) /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" "$id" --repo "$REPO" --role "$impl" --equivalence) >"$LOG/$id-$impl.out" 2>&1
      extra_rc=$?
      set -e
      cat "$LOG/$id-$impl.out"
      extra_ev=$(capture_evidence "$impl_uid" "$impl_home" "$id" "$impl" || true)
      extra_state=NOT\ RUN; [[ -n $extra_ev ]] && extra_state=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status","FAIL"))' "$extra_ev")
      printf '%s\t%s\t%s\t%s\n' "$id" "$impl" "$extra_state" "${extra_ev:-none}" | tee -a "$LOG/summary.tsv"
      [[ $extra_state != FAIL && $extra_rc -ne 1 ]] || rc=1
    done
  fi
done
# A-10 covers every configured App. Implementers are inspected on their trial forks;
# other Apps are inspected on the trial repository. The probe has no A-10 column.
declare -a A10_ROLES=(aao-integrator aao-auditor aao-auditor-alt aao-supervisor aao-notifier aao-pm aao-impl-claude aao-impl-codex aao-impl-agy aao-probe-noworkflows)
for role in "${A10_ROLES[@]}"; do
  if ((${#ONLY[@]})) && [[ ! " ${ONLY[*]} " =~ " A-10 " ]]; then break; fi
  uid=${APP_UID[$role]:-aao-probe-noworkflows}; [[ $role != aao-probe-noworkflows ]] || uid=aao-probe-noworkflows
  home=$(getent passwd "$uid" | cut -d: -f6)
  if [[ -z $home ]]; then printf 'A-10\t%s\tFAIL\tmissing uid\n' "$role" | tee -a "$LOG/summary.tsv"; rc=1; continue; fi
  target=$REPO; parent=$REPO
  case $role in
    aao-impl-claude) target=autoaiorg/aao-trial-claude;;
    aao-impl-codex) target=autoaiorg/aao-trial-codex;;
    aao-impl-agy) target=autoaiorg/aao-trial-agy;;
    aao-probe-noworkflows) target=autoaiorg/aao-trial-probe;;
  esac
  set +e
  runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$target" AAO_GITHUB_TRIAL_FORK_PARENT="$parent" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" A-10 --repo "$target" --role "$role" >"$LOG/A-10-$role.out" 2>&1
  a10_rc=$?
  set -e
  cat "$LOG/A-10-$role.out"
  ev=$(capture_evidence "$uid" "$home" A-10 "$role" || true)
  state='NOT RUN (no evidence from this run)'; [[ -n $ev ]] && state=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status", "FAIL"))' "$ev")
  printf 'A-10\t%s\t%s\t%s\n' "$role" "$state" "${ev:-none}" | tee -a "$LOG/summary.tsv"
  [[ $state != FAIL && $a10_rc -ne 1 ]] || rc=1
  true
done
# A-11 (fork PR creation) and P3-10 (external workflow approval gate) are separate evidence records.
# Each step runs under its own uid with its own App key: implementer -> its fork, aao-pm -> PR, aao-supervisor -> verify.
fork_step(){
  local uid=$1 step=$2 target=$3 role=$4 cwd=$5 home step_rc; shift 5
  home=$(getent passwd "$uid" | cut -d: -f6)
  set +e
  (cd "$cwd" && runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$target,$REPO" AAO_GITHUB_TRIAL_FORK_PARENT="$REPO" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" "$@" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.fork_pr_trial import main;raise SystemExit(main())" "$step" --repo "$target" --role "$role") >"$LOG/$step-$role.out" 2>&1
  step_rc=$?
  set -e
  cat "$LOG/$step-$role.out"
  step_ev=$(capture_evidence "$uid" "$home" "$step" "$role" || true)
  step_state='NOT RUN (no evidence from this run)'; [[ -n $step_ev ]] && step_state=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status","FAIL"))' "$step_ev")
  printf '%s\t%s\t%s\t%s\n' "$step" "$role" "$step_state" "${step_ev:-none}" | tee -a "$LOG/summary.tsv"
  [[ $step_state != FAIL && $step_rc -ne 1 ]] || rc=1
}
if ((${#ONLY[@]} == 0)) || [[ " ${ONLY[*]} " =~ " A-11 " || " ${ONLY[*]} " =~ " P3-10 " ]]; then
  impl=aao-impl-codex; impl_uid=${APP_UID[$impl]}; impl_home=$(getent passwd "$impl_uid" | cut -d: -f6); fork=autoaiorg/aao-trial-codex
  fork_branch="aao-trial/a11-p310-$TS"
  impl_work=$WORK_ROOT/$impl_uid; [[ ! -L $impl_work ]] || die "role work directory is a symlink: $impl_work"
  if [[ -e $impl_work ]]; then role_work_safe "$impl_work" "$impl_uid" || die "unsafe role work directory: $impl_work"; else install -d -o "$impl_uid" -g "$(id -gn "$impl_uid")" -m 0700 "$impl_work"; fi
  runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin mkdir -p "$impl_work/$TS"
  fork_clone=$impl_work/$TS/fork
  IGIT=(runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false)
  fork_ready=0
  if "${IGIT[@]}" clone --quiet "https://github.com/$fork.git" "$fork_clone" && "${IGIT[@]}" -C "$fork_clone" fetch --quiet "https://github.com/$REPO.git" main && "${IGIT[@]}" -C "$fork_clone" checkout -q -B a11-candidate FETCH_HEAD; then
    # The PR changes a workflow, so the pull_request run executes PR-controlled workflow code unless approval gates it.
    runuser -u "$impl_uid" -- env -i HOME="$impl_home" PATH=/usr/bin:/bin /bin/sh -c 'printf "      - run: echo AAO-P3-10-canary-%s\n" "$2" >> "$1/.github/workflows/test.yml"' sh "$fork_clone" "$TS" \
      && "${IGIT[@]}" -C "$fork_clone" add .github/workflows/test.yml \
      && "${IGIT[@]}" -C "$fork_clone" -c user.name='AAO Trial Fixture' -c user.email=trial-fixture@users.noreply.github.com commit -q -m "AAO trial A-11/P3-10 workflow change $TS" \
      && fork_ready=1
  fi
  if ((fork_ready)); then
    fork_head=$("${IGIT[@]}" -C "$fork_clone" rev-parse HEAD)
    fork_step "$impl_uid" FORK-BRANCH "$fork" "$impl" "$fork_clone" AAO_GITHUB_TRIAL_BRANCH="$fork_branch" AAO_TRIAL_CANDIDATE_SHA="$fork_head"
  else
    step_state=FAIL; printf 'FORK-BRANCH\t%s\tFAIL\tcould not prepare the workflow-changing fork commit\n' "$impl" | tee -a "$LOG/summary.tsv"; rc=1
  fi
  if [[ $step_state == PASS ]]; then
    fork_step "${APP_UID[aao-pm]}" A-11 "$REPO" aao-pm / AAO_GITHUB_TRIAL_FORK="$fork" AAO_GITHUB_TRIAL_BRANCH="$fork_branch" AAO_TRIAL_CANDIDATE_SHA="$fork_head"
  else
    printf 'A-11\taao-pm\tNOT RUN\tFORK-BRANCH did not pass\n' | tee -a "$LOG/summary.tsv"
  fi
  if [[ $step_state == PASS ]]; then
    fork_pr=$(python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(x["number"] for x in d["evidence"] if x.get("method")=="fork pull request"))' "$step_ev")
    fork_step "${APP_UID[aao-supervisor]}" P3-10 "$REPO" aao-supervisor / AAO_GITHUB_TRIAL_PR="$fork_pr" AAO_GITHUB_TRIAL_PR_HEAD="$fork_head" AAO_GITHUB_TRIAL_FORK="$fork" AAO_GITHUB_TRIAL_BRANCH="$fork_branch"
  else
    printf 'P3-10\taao-supervisor\tNOT RUN\tno fork PR was created in this run\n' | tee -a "$LOG/summary.tsv"
  fi
fi
# Manual tests remain explicit, never silently omitted.
for id in A-07 A-08 A-13 P3-04 P3-08 P3-11; do
  if ((${#ONLY[@]} == 0)) || [[ " ${ONLY[*]} " =~ " $id " ]]; then printf '%s\tmanual\tNOT RUN\tmanual step documented in trial setup\n' "$id" | tee -a "$LOG/summary.tsv"; fi
done
declare -A HOMES=(); HOMES[$CEO]=$(getent passwd "$CEO" | cut -d: -f6)
for app in "${!APP_UID[@]}"; do user=${APP_UID[$app]}; HOMES[$user]=$(getent passwd "$user" | cut -d: -f6); done
check_rulesets || { echo 'FAIL: trial rulesets changed or are no longer active at end' >&2; rc=1; }
(cd "$LOG" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
chmod 0640 "$LOG"/*; echo "Evidence: $LOG"; column -t -s $'\t' "$LOG/summary.tsv" 2>/dev/null || cat "$LOG/summary.tsv"
exit "$rc"
