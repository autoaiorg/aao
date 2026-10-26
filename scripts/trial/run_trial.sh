#!/bin/bash -p
set -euo pipefail
[[ $- == *p* ]] || { echo 'FAIL: invoke directly as root' >&2; exit 2; }
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONPATH PYTHONHOME PYTHONSTARTUP LD_PRELOAD LD_LIBRARY_PATH
REV= ONLY=() A13_COLLECT=
while (($#)); do case $1 in
  --rev) (($# >= 2)) || exit 2; REV=$2; shift;;
  --only) (($# >= 2)) || exit 2; IFS=, read -r -a ONLY <<<"$2"; shift;;
  --a13-collect) (($# >= 2)) || exit 2; A13_COLLECT=$2; shift;;
  *) echo "unknown argument: $1" >&2; exit 2;; esac; shift; done
[[ $EUID == 0 && $REV =~ ^[0-9a-f]{40}$ ]] || { echo 'FAIL: root and --rev <40-hex> required' >&2; exit 2; }
if [[ -n $A13_COLLECT ]]; then [[ $A13_COLLECT =~ ^[0-9]{8}T[0-9]{6}\.[0-9]{9}Z$ ]] || { echo 'FAIL: --a13-collect <run_id>' >&2; exit 2; }; ONLY=(A-13-collect); fi
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
check_rulesets(){ # [snapshot_file]: exact security shape of rulesets A/B/C (targets, refs, bypass, rules, checks)
  local list; list=$(runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh api "repos/$REPO/rulesets?includes_parents=true") || return 1
  python3 -I - "$list" "${1:-/dev/null}" "$CEO" "$REPO" <<'PY'
import json, pwd, subprocess, sys
listing, out, ceo, repo = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
home = pwd.getpwnam(ceo).pw_dir
def get(ident):
    return json.loads(subprocess.run(["runuser", "-u", ceo, "--", "env", "-i", f"HOME={home}", "PATH=/usr/bin:/bin", "gh", "api",
                                      f"repos/{repo}/rulesets/{int(ident)}"], check=True, capture_output=True, text=True).stdout)
full = {r["name"]: get(r["id"]) for r in listing}
json.dump(full, open(out, "w"), indent=1, sort_keys=True)
integrator = [(5447984, "Integration", "always")]
want = {"A main: integrator only": ("branch", ["refs/heads/main"], integrator, {"update", "pull_request"}),
        "B main+staging: integrity (no bypass)": ("branch", ["refs/heads/aao-staging/**", "refs/heads/main"], [],
                                                  {"non_fast_forward", "deletion", "required_status_checks"}),
        "C tags": ("tag", ["~ALL"], integrator, {"creation", "update", "deletion"})}
problems = []
for name, (target, include, bypass, rules) in want.items():
    r = full.get(name)
    if r is None:
        problems.append(f"missing {name}"); continue
    ref = (r.get("conditions") or {}).get("ref_name") or {}
    got_bypass = sorted((b.get("actor_id"), b.get("actor_type"), b.get("bypass_mode")) for b in r.get("bypass_actors") or [])
    types = {x.get("type") for x in r.get("rules") or []}
    if r.get("enforcement") != "active": problems.append(f"{name}: not active")
    if r.get("target") != target: problems.append(f"{name}: target {r.get('target')}")
    if sorted(ref.get("include") or []) != include or (ref.get("exclude") or []): problems.append(f"{name}: refs {ref}")
    if got_bypass != bypass: problems.append(f"{name}: bypass {got_bypass}")
    if not rules <= types: problems.append(f"{name}: missing rules {sorted(rules - types)}")
b = full.get("B main+staging: integrity (no bypass)") or {}
checks = next((x.get("parameters", {}).get("required_status_checks", []) for x in b.get("rules") or [] if x.get("type") == "required_status_checks"), [])
got = {(c.get("context"), c.get("integration_id")) for c in checks}
if ("aao-audit", 5448107) not in got or not ({("test", None), ("test", 15368)} & got) or len(got) != 2:
    problems.append(f"B: required checks {sorted(got, key=str)}")
for p in problems: print("ruleset gate:", p, file=sys.stderr)
sys.exit(1 if problems else 0)
PY
}
check_rulesets "$tmp/rulesets-start.json" || die 'trial rulesets A/B/C do not have the verified shape (targets, refs, bypass, rules, checks)'
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
capture_evidence(){ # uid home test_id role [observed_rc] [output_file]
  # The role uid owns its evidence directory, so the file is only believed if root can tie it to the invocation it
  # just ran: the exact path that invocation printed, this run and this harness revision, and a status consistent
  # with the exit code root observed (PASS=0, FAIL=1, other=2). Otherwise the root copy is recorded as FAIL.
  local uid=$1 home=$2 test_id=$3 role=${4:-} observed_rc=${5:-} outfile=${6:-} source dest announced verdict
  source=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_ROLE="$role" /usr/bin/python3 -I -c 'import glob,json,os,sys; matches=[]
root=os.environ.get("XDG_DATA_HOME", os.path.join(sys.argv[1], ".local", "share"))
if not os.path.isabs(root): raise SystemExit("XDG_DATA_HOME must be absolute")
directory=os.path.join(root, "aao", "evidence", "trials")
for p in glob.glob(os.path.join(directory, sys.argv[2]+"-*.json")):
 try:
  st=os.lstat(p)
  if not os.path.isfile(p) or os.path.islink(p) or st.st_uid != os.getuid(): continue
  d=json.load(open(p, encoding="utf-8"))
  if d.get("run_id")==os.environ["AAO_TRIAL_RUN_ID"] and (not os.environ.get("AAO_TRIAL_ROLE") or d.get("role")==os.environ["AAO_TRIAL_ROLE"]): matches.append((os.path.getmtime(p),p))
 except (OSError,ValueError): pass
print(max(matches)[1] if matches else "")' "$home" "$test_id") || return 1
  [[ -n $source ]] || return 1
  if [[ -n $outfile ]]; then
    announced=$(grep -Eo '^Evidence: .*' "$outfile" | tail -1 | cut -d' ' -f2-)
    [[ $announced == "$home/.local/share/aao/evidence/trials/$test_id-"*.json && $announced != *..* ]] || announced="<outside $home/.local/share/aao/evidence/trials>"
    [[ $announced == "$source" || $announced == "<"* ]] || source=$announced
  fi
  dest=$LOG/collected-${uid}-${test_id}-${role:-role}.json
  runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin /bin/cat -- "$source" >"$dest" || { rm -f -- "$dest"; return 1; }
  chown root:root "$dest"; chmod 0640 "$dest"
  verdict=$(python3 -I - "$dest" "$test_id" "${role}" "$AAO_TRIAL_RUN_ID" "$REV" "$observed_rc" "${announced-unchecked}" "$source" <<'PY'
import json, sys
path, test_id, role, run_id, rev, rc, announced, source = sys.argv[1:9]
problems = []
try:
    d = json.load(open(path))
    if not isinstance(d, dict): raise ValueError("not an object")
except (OSError, ValueError) as error:
    d, problems = {"test_id": test_id, "role": role}, [f"unreadable evidence ({type(error).__name__})"]
if d.get("test_id") != test_id: problems.append("test_id")
if role and d.get("role") != role: problems.append("role")
if d.get("run_id") != run_id: problems.append("run_id")
if d.get("harness_revision") != rev: problems.append("harness_revision")
if announced != "unchecked" and announced != source: problems.append("not the file this invocation announced")
if rc != "":
    expected = {"PASS": "0", "FAIL": "1"}.get(d.get("status"), "2")
    if rc != expected: problems.append(f"status {d.get('status')} vs observed exit {rc}")
if problems:
    d = {**d, "status": "FAIL", "reason": "evidence inconsistent with the root-observed invocation: " + ", ".join(problems),
         "original_status": d.get("status"), "original_reason": d.get("reason")}
    json.dump(d, open(path, "w"), indent=1)
    print("inconsistent")
PY
)
  [[ $verdict != inconsistent ]] || echo "WARNING: $test_id/$role evidence did not match the root-observed invocation; recorded as FAIL" >&2
  printf '%s\n' "$dest"
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
declare -a IDS=(A-01 A-02 A-03 A-04 A-05 A-06 A-09 A-12 A-14 P3-01 P3-02 P3-03 P3-04 P3-05 P3-06 P3-07 P3-08 P3-09 P3-12)
declare -A ROLE=([P3-04]=aao-integrator [P3-08]=aao-integrator [A-01]=aao-impl-codex [A-02]=aao-impl-codex [A-03]=aao-integrator [A-04]=aao-integrator [A-05]=aao-integrator [A-06]=aao-auditor [A-09]=aao-notifier [A-12]=aao-integrator [A-14]=aao-probe-noworkflows [P3-01]=ceo [P3-02]=aao-impl-codex [P3-03]=aao-integrator [P3-05]=aao-integrator [P3-06]=aao-integrator [P3-07]=aao-integrator [P3-09]=ceo [P3-12]=aao-integrator)
declare -A APP_UID=(); for row in "${APPS[@]}"; do read -r app uid <<<"$row"; APP_UID[$app]=$uid; done
if [[ -n $A13_COLLECT ]]; then
  iuid=${APP_UID[aao-integrator]}; ihome=$(getent passwd "$iuid" | cut -d: -f6)
  unit="aao-trial-a13-${A13_COLLECT//[^0-9A-Za-z]/-}"
  [[ $(systemctl show -P SubState "$unit") == exited ]] || { echo "A-13 unit $unit has not finished (SubState=$(systemctl show -P SubState "$unit"))" >&2; exit 2; }
  a13_rc=$(systemctl show -P ExecMainStatus "$unit"); journalctl -u "$unit" -o cat --no-pager > "$LOG/A-13-aao-integrator.out"
  ev=$(AAO_TRIAL_RUN_ID=$A13_COLLECT capture_evidence "$iuid" "$ihome" A-13 aao-integrator "$a13_rc" "$LOG/A-13-aao-integrator.out" || true)
  systemctl stop "$unit" 2>/dev/null || true
  state='NOT RUN (no A-13 evidence for that run yet: still waiting, or the detached unit failed)'; [[ -n $ev ]] && state=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status","FAIL"))' "$ev")
  printf 'A-13\taao-integrator\t%s\t%s\n' "$state" "${ev:-none}" | tee "$LOG/summary.tsv"
  (cd "$LOG" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS); chmod 0640 "$LOG"/*
  echo "Evidence: $LOG"; [[ $state == PASS ]]; exit $?
fi
APP_UID[aao-probe-noworkflows]=aao-probe-noworkflows
# Stage the local candidate (integrator) and publish `aao-audit` on it (auditor; aao-auditor-alt for the
# P3-04 wrong-publisher fixture). Sets $candidate. Records FAIL and returns 1 on any helper failure.
seed_candidate(){
  local id=$1 uid=$2 home=$3 clone=$4 pub=$5 role=${6:-$5} pub_uid helper_rc staged_sha helper_reason auditor_home auditor_work auditor_clone
  pub_uid=${APP_UID[$pub]}
  candidate=$(runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" rev-parse HEAD)
  set +e
  (cd "$clone" && runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_BRANCH="aao-trial/required-$id-$TS" AAO_GITHUB_TRIAL_EXPECTED_SHA="$candidate" AAO_TRIAL_CANDIDATE_SHA="$candidate" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" STAGE-COMMIT --repo "$REPO" --role aao-integrator --branch "aao-trial/required-$id-$TS") >"$LOG/$id-STAGE-COMMIT.out" 2>&1
  helper_rc=$?
  set -e
  cat "$LOG/$id-STAGE-COMMIT.out"
  if ((helper_rc != 0)); then helper_reason=$(head -n 1 "$LOG/$id-STAGE-COMMIT.out"); printf '%s\t%s\tFAIL\t%s\n' "$id" "$role" "$helper_reason" | tee -a "$LOG/summary.tsv"; rc=1; return 1; fi
  staged_sha=$(grep -Eo 'staged local commit [0-9a-f]{40}' "$LOG/$id-STAGE-COMMIT.out" | awk '{print $4}' | tail -1)
  if [[ $staged_sha != "$candidate" ]]; then printf '%s\t%s\tFAIL\tSTAGE-COMMIT SHA mismatch\n' "$id" "$role" | tee -a "$LOG/summary.tsv"; rc=1; return 1; fi
  auditor_home=$(getent passwd "$pub_uid" | cut -d: -f6)
  auditor_work=$WORK_ROOT/$pub_uid; [[ ! -L $auditor_work ]] || die 'auditor work directory is a symlink'
  if [[ ! -e $auditor_work ]]; then install -d -o "$pub_uid" -g "$(id -gn "$pub_uid")" -m 0700 "$auditor_work"; fi
  role_work_safe "$auditor_work" "$pub_uid" || die 'unsafe auditor work directory'
  runuser -u "$pub_uid" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin mkdir -p "$auditor_work/$TS"
  auditor_clone=$auditor_work/$TS/trial
  if [[ ! -d $auditor_clone/.git ]]; then runuser -u "$pub_uid" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false clone --quiet "https://github.com/$REPO.git" "$auditor_clone"; fi
  set +e
  (cd "$auditor_clone" && runuser -u "$pub_uid" -- env -i HOME="$auditor_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_GITHUB_TRIAL_SHA="$candidate" AAO_TRIAL_CANDIDATE_SHA="$candidate" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" PUBLISH-AUDIT --repo "$REPO" --role "$pub") >"$LOG/$id-PUBLISH-AUDIT.out" 2>&1
  helper_rc=$?
  set -e
  cat "$LOG/$id-PUBLISH-AUDIT.out"
  if ((helper_rc != 0)); then helper_reason=$(head -n 1 "$LOG/$id-PUBLISH-AUDIT.out"); printf '%s\t%s\tFAIL\t%s\n' "$id" "$role" "$helper_reason" | tee -a "$LOG/summary.tsv"; rc=1; return 1; fi

}
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
  if [[ $id == A-03 || $id == A-04 || $id == P3-04 || $id == P3-05 || $id == P3-07 || $id == P3-08 || $id == P3-12 ]]; then
    pub=aao-auditor; [[ $id != P3-04 ]] || pub=aao-auditor-alt
    seed_candidate "$id" "$uid" "$home" "$clone" "$pub" "$role" || continue
  fi
  if [[ $id == A-05 || $id == P3-06 ]]; then runuser -u "$uid" -- env -i HOME="$home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false -C "$clone" fetch --quiet origin "refs/pull/$fixture_num/head"; fi
  set +e
  (cd "$clone" && runuser -u "$uid" -- env -i "${envs[@]}" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" "${args[@]}") >"$LOG/$id-$role.out" 2>&1
  status=$?
  set -e
  cat "$LOG/$id-$role.out"
  evidence=$(capture_evidence "$uid" "$home" "$id" "$role" "$status" "$LOG/$id-$role.out" || true)
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
    evidence=$(capture_evidence "$uid" "$home" "$id" "$role" "$status" "$LOG/$id-$role-promote.out" || true)
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
      extra_ev=$(capture_evidence "$impl_uid" "$impl_home" "$id" "$impl" "$extra_rc" "$LOG/$id-$impl.out" || true)
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
  ev=$(capture_evidence "$uid" "$home" A-10 "$role" "$a10_rc" "$LOG/A-10-$role.out" || true)
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
  step_ev=$(capture_evidence "$uid" "$home" "$step" "$role" "$step_rc" "$LOG/$step-$role.out" || true)
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
wants(){ ((${#ONLY[@]} == 0)) || [[ " ${ONLY[*]} " =~ " $1 " ]]; }
record(){ # id role status reason [json-evidence-file]: a root-side evidence record bound to this run
  python3 -I -c 'import json,sys; ev=json.load(open(sys.argv[5])) if len(sys.argv) > 5 and sys.argv[5] else []
json.dump({"test_id":sys.argv[1],"role":sys.argv[2],"status":sys.argv[3],"reason":sys.argv[4],"run_id":sys.argv[6],"harness_revision":sys.argv[7],"supervisor_revision":sys.argv[9],"evidence":ev},open(sys.argv[8],"w"),indent=1)' \
    "$1" "$2" "$3" "$4" "${5:-}" "$AAO_TRIAL_RUN_ID" "$REV" "$LOG/root-$1.json" "${sup_rev:-unknown}"
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$LOG/root-$1.json" | tee -a "$LOG/summary.tsv"; [[ $3 != FAIL ]] || rc=1
}
SUP_CONFIG=/etc/aao-supervisor/config.json
# A-07/A-08/P3-11 test the INSTALLED supervisor, so they only count if its frozen code is this harness revision.
sup_rev=$(env -i PATH=/usr/bin:/bin HOME=/nonexistent GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_NO_REPLACE_OBJECTS=1 \
  git -c safe.directory='*' -c core.fsmonitor=false -c core.hooksPath=/dev/null -C /srv/aao/frozen/aao-supervisor/tree rev-parse HEAD 2>/dev/null || echo unknown)
installed_rev=$(cat /etc/aao-audit/expected-revision 2>/dev/null || echo unknown)
SUP_AT_REV=0; [[ $sup_rev == "$REV" && $installed_rev == "$REV" && $(stat -c %u /srv/aao/frozen/aao-supervisor/tree 2>/dev/null) == 0 ]] && SUP_AT_REV=1
sup_skip(){ record "$1" aao-supervisor "NOT RUN" "installed supervisor is at ${sup_rev} (trust root ${installed_rev}), not the harness revision $REV: upgrade first"; }
sup_cfg(){ python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]))' "$SUP_CONFIG" "$1" "$2"; }

# A-08: the supervisor attributes the fork PR head to the implementer that pushed it (authenticated PushEvent
# chain in the fork), not to the PR author (aao-pm[bot]). Uses the installed supervisor unit, triggered by root.
if wants A-08 && ((!SUP_AT_REV)); then sup_skip A-08
elif wants A-08; then
  if [[ ${fork_head:-} =~ ^[0-9a-f]{40}$ && -n ${fork_pr:-} ]]; then
    attribution=$(sup_cfg attribution_path /var/lib/aao-supervisor/attribution.json); a08=; deadline=$((SECONDS + 420))
    while ((SECONDS < deadline)); do
      systemctl start aao-supervisor-attribution.service || true
      a08=$(python3 -I -c 'import json,sys
try: print(json.dumps(json.load(open(sys.argv[1]))["candidates"].get(sys.argv[2])))
except (OSError, ValueError, KeyError): print("null")' "$attribution" "$fork_head")
      [[ $a08 == null ]] || break; sleep 30
    done
    printf '%s\n' "{\"pr\": $fork_pr, \"head\": \"$fork_head\", \"principals\": $a08}" > "$LOG/A-08-attribution.json"
    if [[ $a08 == '["aao-impl-codex[bot]"]' ]]; then record A-08 aao-supervisor PASS "PR #$fork_pr head attributed only to the pushing implementer aao-impl-codex[bot], not to the PR author aao-pm[bot]"
    elif [[ $a08 == null ]]; then record A-08 aao-supervisor INCONCLUSIVE "no attribution for $fork_head within 420s"
    else record A-08 aao-supervisor FAIL "unexpected principals for $fork_head: $a08"; fi
  else
    record A-08 aao-supervisor "NOT RUN" "no fork PR from A-11 in this run"
  fi
fi

# A-07 + P3-11: the CEO disables ruleset A (emergency), lands a fully checked commit on main, and the supervisor
# must report both the ruleset drift and the non-integrator push; ruleset A is then restored and re-verified.
# Ruleset A is restored on ANY exit while disabled; if restoration cannot be verified the run fails loudly.
A_ID=25776805; A_DISABLED=0
ceo_gh(){ runuser -u "$CEO" -- env -i HOME="$(getent passwd "$CEO"|cut -d: -f6)" PATH=/usr/bin:/bin gh "$@"; }
restore_a(){
  ((A_DISABLED)) || return 0
  ceo_gh api -X PUT "repos/$REPO/rulesets/$A_ID" -f enforcement=active >/dev/null && check_rulesets && A_DISABLED=0 && return 0
  echo "CRITICAL: ruleset A of $REPO could not be restored/verified. Re-enable it by hand NOW: gh api -X PUT repos/$REPO/rulesets/$A_ID -f enforcement=active" >&2
  return 1
}
trap 'if ! restore_a; then rm -rf "$tmp"; exit 99; fi; rm -rf "$tmp"' EXIT  # unrestorable ruleset A = failed run
trap 'exit 130' INT TERM HUP  # route signals through the EXIT trap so ruleset A is always restored
sup_events(){ # newer than marker, of a type: prints matching event JSON lines
  python3 -I -c 'import json,os,sys
d,marker,kind=sys.argv[1],float(sys.argv[2]),sys.argv[3]
for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
  p=os.path.join(d,n)
  try:
    if os.path.getmtime(p) < marker: continue
    e=json.load(open(p))
  except (OSError, ValueError): continue
  if e.get("type")==kind: print(json.dumps(e))' "$1" "$2" "$3"
}
if (wants A-07 || wants P3-11) && ((!SUP_AT_REV)); then
  wants A-07 && sup_skip A-07; wants P3-11 && sup_skip P3-11
elif wants A-07 || wants P3-11; then
  iuid=${APP_UID[aao-integrator]}; ihome=$(getent passwd "$iuid" | cut -d: -f6); iwork=$WORK_ROOT/$iuid
  ensure_work(){ [[ ! -L $1 ]] || die "role work directory is a symlink: $1"; [[ -e $1 ]] || install -d -o "$2" -g "$(id -gn "$2")" -m 0700 "$1"; role_work_safe "$1" "$2" || die "unsafe role work directory: $1"; }
  ensure_work "$iwork" "$iuid"
  runuser -u "$iuid" -- env -i HOME="$ihome" PATH=/usr/bin:/bin mkdir -p "$iwork/$TS"; a07_clone=$iwork/$TS/a07
  IG=(runuser -u "$iuid" -- env -i HOME="$ihome" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false)
  "${IG[@]}" clone --quiet "https://github.com/$REPO.git" "$a07_clone"
  "${IG[@]}" -C "$a07_clone" -c user.name='AAO Trial Fixture' -c user.email=trial-fixture@users.noreply.github.com commit -q --allow-empty -m "AAO trial A-07 $TS"
  if seed_candidate A-07 "$iuid" "$ihome" "$a07_clone" aao-auditor ceo; then
    a07_sha=$candidate; green=0; deadline=$((SECONDS + 420))
    while ((SECONDS < deadline)); do
      green=$(ceo_gh api "repos/$REPO/commits/$a07_sha/check-runs?per_page=100" | python3 -I -c 'import json,sys; r=json.load(sys.stdin)["check_runs"]
ok=lambda n,app=None: any(x["name"]==n and x["status"]=="completed" and x["conclusion"]=="success" and (app is None or x["app"]["id"]==app) for x in r)
print(1 if ok("test") and ok("aao-audit",5448107) else 0)' || echo 0)
      ((green)) && break; sleep 20
    done
    if ((green)); then
      marker=$(date +%s.%N); events_dir=$(sup_cfg events_path /var/lib/aao-supervisor/events)
      ceo_gh api "repos/$REPO/rulesets/$A_ID" > "$LOG/P3-11-ruleset-A.before.json"
      A_DISABLED=1; ceo_gh api -X PUT "repos/$REPO/rulesets/$A_ID" -f enforcement=disabled > "$LOG/P3-11-ruleset-A.disabled.json"
      ceo_home=$(getent passwd "$CEO" | cut -d: -f6); ceo_clone=$WORK_ROOT/$CEO/$TS/a07
      ensure_work "$WORK_ROOT/$CEO" "$CEO"
      runuser -u "$CEO" -- env -i HOME="$ceo_home" PATH=/usr/bin:/bin mkdir -p "$ceo_clone"
      CG=(runuser -u "$CEO" -- env -i HOME="$ceo_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c core.fsmonitor=false)
      "${CG[@]}" clone --quiet "https://github.com/$REPO.git" "$ceo_clone/trial" && "${CG[@]}" -C "$ceo_clone/trial" fetch --quiet origin "aao-trial/required-A-07-$TS" && "${CG[@]}" -C "$ceo_clone/trial" checkout -q --detach "$a07_sha"
      set +e
      (cd "$ceo_clone/trial" && runuser -u "$CEO" -- env -i HOME="$ceo_home" PATH=/usr/bin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null GIT_CONFIG_KEY_1=core.fsmonitor GIT_CONFIG_VALUE_1=false AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_TRIAL_CANDIDATE_SHA="$a07_sha" AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" A-07 --repo "$REPO" --role ceo) >"$LOG/A-07-ceo.out" 2>&1
      set -e
      cat "$LOG/A-07-ceo.out"
      violation= drift=; deadline=$((SECONDS + 420))
      while ((SECONDS < deadline)) && [[ -z $violation || -z $drift ]]; do
        systemctl start aao-supervisor-watch.service || true
        violation=$(sup_events "$events_dir" "$marker" governance-violation | python3 -I -c 'import json,sys; print(next((l for l in sys.stdin if (e:=json.loads(l)).get("head")==sys.argv[1] and e.get("actor")==sys.argv[2] and e.get("ref")=="refs/heads/main" and e.get("repo")==sys.argv[3]),""),end="")' "$a07_sha" "$CEO" "$REPO")
        drift=$(sup_events "$events_dir" "$marker" ruleset-drift | python3 -I -c 'import json,sys; print(next((l for l in sys.stdin if "update" in (e:=json.loads(l)).get("missing",[]) and e.get("repo")==sys.argv[1]),""),end="")' "$REPO")
        [[ -n $violation && -n $drift ]] || sleep 30
      done
      restore_a || { record P3-11 ceo FAIL "ruleset A could not be restored and verified"; exit 1; }
      restored=; deadline=$((SECONDS + 300))
      while ((SECONDS < deadline)) && [[ -z $restored ]]; do
        systemctl start aao-supervisor-watch.service || true
        restored=$(sup_events "$events_dir" "$marker" ruleset-restored | python3 -I -c 'import json,sys; print(next((l for l in sys.stdin if json.loads(l).get("repo")==sys.argv[1]),""),end="")' "$REPO"); [[ -n $restored ]] || sleep 30
      done
      printf '%s\n' "${violation:-null}" > "$LOG/A-07-event.json"; printf '[%s,%s]\n' "${drift:-null}" "${restored:-null}" > "$LOG/P3-11-events.json"
      landed=$(ceo_gh api "repos/$REPO/git/ref/heads/main" --jq .object.sha 2>/dev/null || true)
      if wants A-07; then
        if [[ $landed != "$a07_sha" ]]; then record A-07 ceo INCONCLUSIVE "the CEO push did not land on main (main=$landed); see A-07-ceo.out"
        elif [[ -n $violation ]]; then record A-07 aao-supervisor PASS "supervisor reported governance-violation for the CEO push $a07_sha to main" "$LOG/A-07-event.json"
        else record A-07 aao-supervisor FAIL "non-integrator push $a07_sha landed on main and no governance-violation was reported within 420s"; fi
      fi
      if wants P3-11; then
        if [[ -n $drift && -n $restored ]]; then record P3-11 aao-supervisor PASS "supervisor reported ruleset A drift (update missing) and its restoration; ruleset A re-verified active" "$LOG/P3-11-events.json"
        elif [[ -n $drift ]]; then record P3-11 aao-supervisor INCONCLUSIVE "drift reported; restoration event not seen within 300s (ruleset A itself re-verified active)" "$LOG/P3-11-events.json"
        else record P3-11 aao-supervisor FAIL "ruleset A was disabled and no ruleset-drift alert was reported within 420s"; fi
      fi
    else
      record A-07 ceo INCONCLUSIVE "A-07 candidate checks did not turn green within 420s; ruleset A was not touched"
      record P3-11 ceo INCONCLUSIVE "skipped with A-07: ruleset A was not touched"
    fi
  else
    record A-07 ceo INCONCLUSIVE "A-07 candidate could not be staged/published (see A-07-STAGE-COMMIT.out); ruleset A was not touched"
    record P3-11 ceo INCONCLUSIVE "skipped with A-07: ruleset A was not touched"
  fi
fi

# A-13: an installation token used after expiry must get 401. It needs ~62 minutes, so it runs detached as the
# integrator (token only in that process' memory) and is collected later with: run_trial.sh --rev REV --a13-collect <run_id>
if wants A-13; then
  iuid=${APP_UID[aao-integrator]}; ihome=$(getent passwd "$iuid" | cut -d: -f6)
  systemd-run --quiet --remain-after-exit --unit "aao-trial-a13-${AAO_TRIAL_RUN_ID//[^0-9A-Za-z]/-}" --uid="$iuid" --gid="$(id -g "$iuid")" \
    --working-directory="$ihome" /usr/bin/env -i HOME="$ihome" PATH=/usr/bin:/bin AAO_GITHUB_TRIAL_REPOS="$REPO" AAO_TRIAL_A13_WAIT=1 \
    AAO_TRIAL_RUN_ID="$AAO_TRIAL_RUN_ID" AAO_TRIAL_HARNESS_REV="$REV" /usr/bin/python3 -I -c "import sys;sys.path.insert(0,'$INSTALL/src');from aao.github_trial import main;raise SystemExit(main())" A-13 --repo "$REPO" --role aao-integrator \
    && printf 'A-13\taao-integrator\tPENDING\tdetached ~62 min; collect: run_trial.sh --rev %s --a13-collect %s\n' "$REV" "$AAO_TRIAL_RUN_ID" | tee -a "$LOG/summary.tsv" \
    || record A-13 aao-integrator FAIL "could not start the detached A-13 expiry check"
fi
declare -A HOMES=(); HOMES[$CEO]=$(getent passwd "$CEO" | cut -d: -f6)
for app in "${!APP_UID[@]}"; do user=${APP_UID[$app]}; HOMES[$user]=$(getent passwd "$user" | cut -d: -f6); done
cp "$tmp/rulesets-start.json" "$LOG/rulesets-start.json" 2>/dev/null || true
check_rulesets "$LOG/rulesets-end.json" || { echo 'FAIL: trial rulesets changed or are no longer active at end' >&2; rc=1; }
(cd "$LOG" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
chmod 0640 "$LOG"/*; echo "Evidence: $LOG"; column -t -s $'\t' "$LOG/summary.tsv" 2>/dev/null || cat "$LOG/summary.tsv"
exit "$rc"
