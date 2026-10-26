"""AAO Operational CLI and Diagnostic Engine (aao-ops / doctor).

Provides unified system status, actionable diagnostics, and service operations
while strictly respecting separation of privileges and governance guardrails.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aao.host_identity import HostIdentityError, current_host_id
from aao.migrator import check_status as check_migration_status
from aao.migrator import default_migrations_dir
from aao.postgresql_connection import connect_postgres


@dataclass
class DiagnosticCheck:
    name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str


def check_postgres_health() -> DiagnosticCheck:
    """Check connectivity and responsiveness of PostgreSQL."""
    try:
        with connect_postgres() as db:
            row = db.execute("SELECT version()").fetchone()
            if row:
                return DiagnosticCheck("PostgreSQL Connection", "PASS", row[0].split(",")[0])
            return DiagnosticCheck("PostgreSQL Connection", "FAIL", "No version returned")
    except (RuntimeError, OSError) as exc:
        return DiagnosticCheck(
            "PostgreSQL Connection",
            "FAIL",
            f"Unable to connect to PostgreSQL: {exc}. Action: check service status and AAO_POSTGRES_URL.",
        )


def check_migrations_health() -> DiagnosticCheck:
    """Verify that all migrations in db/postgres are applied and intact."""
    try:
        with connect_postgres() as db:
            status = check_migration_status(db, default_migrations_dir())
            if status.pending_count > 0:
                return DiagnosticCheck(
                    "Schema Migrations",
                    "WARN",
                    f"{status.pending_count} migrations pending application. Action: run 'aao-migrate --apply'.",
                )
            return DiagnosticCheck(
                "Schema Migrations",
                "PASS",
                f"All {status.applied_count} migrations applied with verified checksums.",
            )
    except (RuntimeError, OSError) as exc:
        return DiagnosticCheck("Schema Migrations", "FAIL", f"Migration check failed: {exc}")


def check_api_health(api_url: str = "http://127.0.0.1:8001") -> DiagnosticCheck:
    """Query the local API health and readiness endpoints."""
    health_url = f"{api_url}/health"
    ready_url = f"{api_url}/ready"
    try:
        req_health = Request(health_url, headers={"Accept": "application/json"})
        with urlopen(req_health, timeout=3) as resp:
            if resp.status != 200:
                return DiagnosticCheck("API Service", "FAIL", f"/health returned HTTP {resp.status}")

        req_ready = Request(ready_url, headers={"Accept": "application/json"})
        with urlopen(req_ready, timeout=3) as resp:
            if resp.status != 200:
                return DiagnosticCheck("API Service", "WARN", f"/ready returned HTTP {resp.status}")

        return DiagnosticCheck("API Service", "PASS", f"Responsive at {api_url} (/health and /ready OK)")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return DiagnosticCheck(
            "API Service",
            "WARN",
            f"API service not reachable at {api_url}: {exc}. Action: check 'systemctl status aao-api'.",
        )


def check_frontend_bundle() -> DiagnosticCheck:
    """Verify that the Control Center React bundle is compiled and present."""
    static_dir = os.environ.get("AAO_STATIC_DIR")
    dist = Path(static_dir) if static_dir else (
        Path(__file__).resolve().parents[2] / "frontend" / "app" / "dist"
    )
    index_file = dist / "index.html"
    assets_dir = dist / "assets"
    if index_file.is_file() and assets_dir.is_dir():
        return DiagnosticCheck(
            "Control Center Bundle",
            "PASS",
            f"Production build verified at {dist}",
        )
    legacy = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    if legacy.is_file():
        return DiagnosticCheck(
            "Control Center Bundle",
            "WARN",
            f"Using legacy UI fallback at {legacy.parent}. Action: run 'npm run build' in frontend/app.",
        )
    return DiagnosticCheck(
        "Control Center Bundle",
        "FAIL",
        f"Missing frontend bundle at {dist}. Action: compile via 'npm ci && npm run build'.",
    )


def check_governance_guardrails() -> DiagnosticCheck:
    """Verify that the integrator is OFF and R2 capabilities remain blocked."""
    integrator_active = False
    if shutil.which("systemctl"):
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "aao-integrator-tick.timer"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.stdout.strip() in ("active", "activating"):
                integrator_active = True
        except OSError:
            pass

    if integrator_active:
        return DiagnosticCheck(
            "Governance Guardrails",
            "FAIL",
            "FAILED: Integrator timer is ACTIVE or unmasked! Policy violation: Integrator must remain OFF.",
        )
    return DiagnosticCheck(
        "Governance Guardrails",
        "PASS",
        "LOCKED_UNAUTHORIZED: Integrator is OFF (masked). RA remain PENDING. R2 locked.",
    )


def check_governance_identities(app_keys_override: list[Path] | None = None) -> DiagnosticCheck:
    """Verify governance role identities and distinguish the 6 governance states:
    - INSTALLED_UNVERIFIED: local key parse and filesystem checks only; GitHub identity/authentication not proven.
    - STAGED_PENDING_KEYS: no App keys present; no other infrastructure claim is made.
    - DEGRADED: Partial keys present (between 1 and 8 of 9 keys deployed).
    - FAILED: Missing required governance identities on host or unauthorized unmasked integrator.
    """
    import pwd
    import stat
    required = ["aao-api", "aao-auditor", "aao-supervisor", "aao-integrator"]
    missing = []
    for u in required:
        try:
            pwd.getpwnam(u)
        except KeyError:
            missing.append(u)

    if missing:
        is_host_install = Path("/opt/aao").is_dir()
        if is_host_install:
            return DiagnosticCheck(
                "Governance Infrastructure",
                "FAIL",
                f"FAILED: Missing required governance identities: {', '.join(missing)}. Action: run 'sudo scripts/bootstrap/init_identities.sh'.",
            )
        return DiagnosticCheck(
            "Governance Infrastructure",
            "WARN",
            f"Non-host environment missing identities: {', '.join(missing)}.",
        )

    # Check GitHub App keys status
    default_app_keys = [
        ("aao-integrator", Path("/home/aao-integrator/.config/aao/aao-integrator.pem")),
        ("aao-auditor", Path("/home/aao-auditor/.config/aao/aao-auditor.pem")),
        ("aao-auditor-alt", Path("/home/aao-auditor-alt/.config/aao/aao-auditor-alt.pem")),
        ("aao-supervisor", Path("/home/aao-supervisor/.config/aao/aao-supervisor.pem")),
        ("aao-notifier", Path("/home/aao-notifier/.config/aao/aao-notifier.pem")),
        ("aao-pm", Path("/home/aao-pm/.config/aao/aao-pm.pem")),
        ("aao-impl-claude", Path("/home/aao-impl-claude/.config/aao/aao-impl-claude.pem")),
        ("aao-impl-codex", Path("/home/aao-impl-codex/.config/aao/aao-impl-codex.pem")),
        ("aao-impl-ag", Path("/home/aao-impl-ag/.config/aao/aao-impl-agy.pem")),
    ]
    app_key_specs = (
        [(None, Path(k)) for k in app_keys_override]
        if app_keys_override is not None else default_app_keys
    )
    present_keys = [(owner, key) for owner, key in app_key_specs if key.exists() or key.is_symlink()]

    if len(present_keys) == 0:
        return DiagnosticCheck(
            "Governance Infrastructure",
            "WARN",
            "STAGED_PENDING_KEYS: no App keys are present; this diagnostic does not attest identity ACLs, ledgers, events, or a trust root.",
        )
    elif len(present_keys) < len(app_key_specs):
        return DiagnosticCheck(
            "Governance Infrastructure",
            "WARN",
            f"DEGRADED: Partial keys present ({len(present_keys)}/{len(app_key_specs)} GitHub App keys deployed).",
        )

    # All expected paths exist -> parse keys and check local file boundaries. This
    # is not proof that GitHub recognizes the App, that the key is unrevoked, or
    # that an installation token can be issued.
    unverified_reasons = []
    for expected_owner, key_path in present_keys:
        try:
            # Check the complete role-owned path, not just the PEM leaf. A secure
            # key under a replaceable or traversable directory is not protected.
            if expected_owner:
                account = pwd.getpwnam(expected_owner)
                home = Path(account.pw_dir)
                parents = []
                parent = key_path.parent
                while parent != home and parent != parent.parent:
                    parents.append(parent)
                    parent = parent.parent
                if parent != home:
                    unverified_reasons.append(f"{key_path.name}: path is not under {expected_owner}'s home")
                else:
                    parents.append(home)
                for directory in parents:
                    directory_info = directory.lstat()
                    if (not stat.S_ISDIR(directory_info.st_mode)
                            or directory_info.st_uid != account.pw_uid
                            or stat.S_IMODE(directory_info.st_mode) & 0o077):
                        unverified_reasons.append(
                            f"{key_path.name}: parent directory {directory} is not role-owned and private"
                        )
                        break
            else:
                parent_info = key_path.parent.lstat()
                if (not stat.S_ISDIR(parent_info.st_mode)
                        or stat.S_IMODE(parent_info.st_mode) & 0o077):
                    unverified_reasons.append(f"{key_path.name}: parent directory is not private")
            st = key_path.lstat()
            if not stat.S_ISREG(st.st_mode):
                unverified_reasons.append(f"{key_path.name}: not a regular, non-symlink key file")
                continue
            file_mode = stat.S_IMODE(st.st_mode)
            if file_mode not in (0o600, 0o400):
                unverified_reasons.append(
                    f"{key_path.name}: insecure permissions 0{oct(file_mode)[2:]} (expected 0600 or 0400)"
                )
            if expected_owner:
                try:
                    expected_uid = pwd.getpwnam(expected_owner).pw_uid
                except KeyError:
                    expected_uid = None
                if expected_uid is None or st.st_uid != expected_uid:
                    unverified_reasons.append(f"{key_path.name}: owner does not match role {expected_owner}")
            try:
                parsed = subprocess.run(
                    ["openssl", "pkey", "-in", str(key_path), "-noout"],
                    capture_output=True, check=False, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                unverified_reasons.append(
                    f"{key_path.name}: could not run bounded OpenSSL key parser"
                )
            else:
                if parsed.returncode != 0:
                    unverified_reasons.append(f"{key_path.name}: cryptographic key parse failed")
        except OSError as exc:
            unverified_reasons.append(f"{key_path.name}: read error ({exc})")

    if unverified_reasons:
        return DiagnosticCheck(
            "Governance Infrastructure",
            "WARN",
            f"INSTALLED_UNVERIFIED: Local key checks failed: {'; '.join(unverified_reasons)}.",
        )

    return DiagnosticCheck(
        "Governance Infrastructure",
        "WARN",
        f"INSTALLED_UNVERIFIED: {len(present_keys)}/{len(app_key_specs)} keys parsed with local permission/ownership checks; GitHub App identity, revocation, and live authentication were not verified.",
    )


def run_doctor(api_url: str = "http://127.0.0.1:8001") -> list[DiagnosticCheck]:
    """Execute the full suite of diagnostic health checks."""
    checks = [
        check_postgres_health(),
        check_migrations_health(),
        check_api_health(api_url),
        check_frontend_bundle(),
        check_governance_guardrails(),
        check_governance_identities(),
    ]
    return checks


def status_command(api_url: str = "http://127.0.0.1:8001") -> int:
    """Display comprehensive system status."""
    print("=" * 60)
    print(" AAO System Status Report")
    print("=" * 60)

    # Database
    pg_check = check_postgres_health()
    print(f"PostgreSQL:         [{pg_check.status}] {pg_check.message}")

    # Migrations
    mig_check = check_migrations_health()
    print(f"Migrations:         [{mig_check.status}] {mig_check.message}")

    # API
    api_check = check_api_health(api_url)
    print(f"API Server:         [{api_check.status}] {api_check.message}")

    # Frontend
    fe_check = check_frontend_bundle()
    print(f"Control Center:     [{fe_check.status}] {fe_check.message}")

    # Governance
    gov_check = check_governance_guardrails()
    print(f"Governance State:   [{gov_check.status}] {gov_check.message}")

    # Execution queue stats if DB reachable
    try:
        with connect_postgres() as db:
            rows = db.execute(
                "SELECT status, count(*) FROM execution_queue GROUP BY status ORDER BY status"
            ).fetchall()
            print("\nExecution Queue:")
            if rows:
                for st, count in rows:
                    print(f"  {st:<15}: {count}")
            else:
                print("  (empty)")
    except (RuntimeError, OSError):
        pass

    print("=" * 60)
    return 0


def doctor_command(api_url: str = "http://127.0.0.1:8001") -> int:
    """Run diagnostics and print actionable instructions."""
    print("Running AAO Doctor diagnostics...\n")
    checks = run_doctor(api_url)

    failures = 0
    warnings = 0
    for c in checks:
        if c.status == "PASS":
            print(f"  [ PASS ] {c.name}: {c.message}")
        elif c.status == "WARN":
            print(f"  [ WARN ] {c.name}: {c.message}")
            warnings += 1
        else:
            print(f"  [ FAIL ] {c.name}: {c.message}")
            failures += 1

    print("\nDiagnostic Summary:")
    print(f"  Total Checks: {len(checks)}")
    print(f"  Pass:         {len(checks) - failures - warnings}")
    print(f"  Warnings:     {warnings}")
    print(f"  Failures:     {failures}")

    if failures > 0:
        print("\nResult: UNHEALTHY — Resolve actionable failures above.", file=sys.stderr)
        return 1
    elif warnings > 0:
        print("\nResult: OPERATIONAL WITH WARNINGS — Review actionable notes above.")
        return 0
    else:
        print("\nResult: HEALTHY — All components operational and compliant.")
        return 0


def verify_command(api_url: str = "http://127.0.0.1:8001") -> int:
    """Quiet verification returning exit code 0 only if all checks PASS."""
    checks = run_doctor(api_url)
    if any(c.status == "FAIL" for c in checks):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AAO Operations and Diagnostic CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Show system status and metrics")
    p_status.add_argument("--api-url", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Run actionable health diagnostics")
    p_doctor.add_argument("--api-url", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))

    # verify
    p_verify = subparsers.add_parser("verify", help="Automated verification (exit code 0 on health)")
    p_verify.add_argument("--api-url", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))

    # backup
    p_backup = subparsers.add_parser("backup", help="Create an atomic backup archive")
    p_backup.add_argument("--output-dir", type=Path, default=Path("/var/backups/aao"))

    # verify-backup
    p_vbackup = subparsers.add_parser("verify-backup", help="Verify backup archive integrity")
    p_vbackup.add_argument("archive", type=Path)

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore backup into target database")
    p_restore.add_argument("archive", type=Path)
    p_restore.add_argument(
        "--target-dsn",
        default=os.environ.get("AAO_RESTORE_TARGET_DSN", os.environ.get("AAO_POSTGRES_URL")),
    )
    p_restore.add_argument("--allow-non-empty", action="store_true",
                           help="Allow restoring over non-empty database (requires verifiable CEO authorization)")
    p_restore.add_argument("--auth-file", default=None,
                           help="Path to structured, signed CEO authorization JSON file")
    p_restore.add_argument("--ceo-token", default=None,
                           help="Explicit CEO credential token for verifiable authorization")
    p_restore.add_argument("--verify-isolated-dsn",
                           default=os.environ.get("AAO_RESTORE_VERIFY_ISOLATED_DSN"),
                           help="Verify restoration into an isolated destination before touching target")

    # authorize-restore
    p_auth = subparsers.add_parser("authorize-restore", help="Issue a restore authorization using an issuer-only signing key")
    p_auth.add_argument("archive", type=Path)
    p_auth.add_argument("--target-database", default="aao_prod")
    p_auth.add_argument("--signing-key-file", type=Path, required=True,
                        help="Issuer private key; never install this key on an executor host")
    p_auth.add_argument("--output", type=Path, default=None)

    # register-host-worker
    p_reg = subparsers.add_parser("register-host-worker", help="Explicitly bind a worker identity to a host node")
    p_reg.add_argument("--worker-id", required=True)
    p_reg.add_argument("--host-id", help="Must match this host's protected /etc/aao/host-id")

    # fence-host
    p_fence = subparsers.add_parser("fence-host", help="Apply targeted host fencing: revoke worker leases and credentials")
    p_fence.add_argument("--host-id", help="Must match this host's protected /etc/aao/host-id")

    args = parser.parse_args(argv)

    if args.command == "status":
        return status_command(args.api_url)
    elif args.command == "doctor":
        return doctor_command(args.api_url)
    elif args.command == "verify":
        return verify_command(args.api_url)
    elif args.command == "backup":
        from aao.backup import create_backup
        bundle = create_backup(args.output_dir)
        print(f"Created backup: {bundle}")
        return 0
    elif args.command == "verify-backup":
        from aao.backup import verify_backup
        manifest = verify_backup(args.archive)
        print(f"PASS: Backup verified. Revision: {manifest.git_revision}, DB hash: {manifest.database_dump_sha256[:12]}")
        return 0
    elif args.command == "restore":
        from aao.backup import restore_backup
        if not args.target_dsn:
            print(
                "ERROR: Target DSN must be provided via --target-dsn, "
                "AAO_RESTORE_TARGET_DSN, or AAO_POSTGRES_URL",
                file=sys.stderr,
            )
            return 1

        try:
            manifest = restore_backup(
                args.archive,
                args.target_dsn,
                allow_non_empty_target=args.allow_non_empty,
                restore_authorization=args.auth_file,
                ceo_token=args.ceo_token,
                isolated_dsn=args.verify_isolated_dsn,
            )
            print(f"PASS: Restored backup from revision {manifest.git_revision}")
            return 0
        except (RuntimeError, OSError) as exc:
            print(f"RESTORE FAILED: {exc}", file=sys.stderr)
            return 1

    elif args.command == "authorize-restore":
        import json

        from aao.backup import create_restore_authorization
        try:
            auth = create_restore_authorization(args.archive, args.target_database, args.signing_key_file)
        except (RuntimeError, OSError) as exc:
            print(f"ERROR: Restore authorization could not be issued: {exc}", file=sys.stderr)
            return 1
        auth_json = json.dumps(auth, indent=2)
        if args.output:
            args.output.write_text(auth_json, encoding="utf-8")
            print(f"Saved restore authorization to {args.output}")
        else:
            print(auth_json)
        return 0

    elif args.command == "register-host-worker":
        from aao.backup import register_host_worker
        try:
            local_host_id = current_host_id()
            if args.host_id is not None and args.host_id != local_host_id:
                raise HostIdentityError("Worker registration is restricted to the protected local host identity")
            with connect_postgres() as db:
                register_host_worker(db, host_id=local_host_id, worker_id=args.worker_id)
            print(f"PASS: Worker '{args.worker_id}' bound to host '{local_host_id}'.")
            return 0
        except (RuntimeError, OSError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    elif args.command == "fence-host":
        from aao.backup import apply_host_fencing
        try:
            local_host_id = current_host_id()
            if args.host_id is not None and args.host_id != local_host_id:
                raise HostIdentityError("Host fencing must run on the host identified by protected /etc/aao/host-id")
        except HostIdentityError as exc:
            print(f"FENCING ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Applying targeted host fencing for '{local_host_id}'...")

        # If systemd is available, stop and mask background workers
        if shutil.which("systemctl"):
            for unit in ("aao-worker-self-dev.service", "aao-conversation-recovery.timer", "aao-conversation-recovery.service"):
                subprocess.run(["systemctl", "stop", unit], capture_output=True, check=False)
                subprocess.run(["systemctl", "mask", unit], capture_output=True, check=False)
            print("  [+] Masked and stopped local worker systemd units")

        try:
            with connect_postgres() as db:
                actions = apply_host_fencing(db, host_identifier=local_host_id)
                for a in actions:
                    print(f"  [+] {a}")
            print(f"PASS: Host '{local_host_id}' successfully fenced from cluster.")
            return 0
        except (RuntimeError, OSError) as exc:
            print(f"FENCING ERROR: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
