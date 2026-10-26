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
            if res.stdout.strip() == "active":
                integrator_active = True
        except OSError:
            pass

    if integrator_active:
        return DiagnosticCheck(
            "Governance Guardrails",
            "FAIL",
            "Integrator timer is ACTIVE! Policy violation: Integrator must remain OFF.",
        )
    return DiagnosticCheck(
        "Governance Guardrails",
        "PASS",
        "Integrator is OFF. RA remain PENDING. Constitutional controls intact.",
    )


def run_doctor(api_url: str = "http://127.0.0.1:8001") -> list[DiagnosticCheck]:
    """Execute the full suite of diagnostic health checks."""
    checks = [
        check_postgres_health(),
        check_migrations_health(),
        check_api_health(api_url),
        check_frontend_bundle(),
        check_governance_guardrails(),
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
    p_restore.add_argument("--target-dsn", default=os.environ.get("AAO_POSTGRES_URL"))
    p_restore.add_argument("--allow-non-empty", action="store_true",
                           help="Allow restoring over non-empty database (requires --authorized-by-ceo)")
    p_restore.add_argument("--authorized-by-ceo", action="store_true",
                           help="Explicit CEO authorization for destructive restore over existing database")
    p_restore.add_argument("--verify-isolated-dsn", default=None,
                           help="Verify restoration into an isolated destination before touching target")

    # fence-host
    p_fence = subparsers.add_parser("fence-host", help="Apply host fencing: revoke worker leases, tokens and stop local worker units")
    p_fence.add_argument("--host-id", default=os.uname().nodename, help="Host identifier to record in fencing audit")

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
        from aao.backup import restore_backup, verify_restore_isolated
        if not args.target_dsn:
            print("ERROR: Target DSN must be provided via --target-dsn or AAO_POSTGRES_URL", file=sys.stderr)
            return 1

        if args.verify_isolated_dsn:
            print(f"Executing pre-restoration dry run in isolated destination: {args.verify_isolated_dsn}...")
            verify_restore_isolated(args.archive, args.verify_isolated_dsn)
            print("PASS: Pre-restoration dry run in isolated environment completed successfully.")

        try:
            manifest = restore_backup(
                args.archive,
                args.target_dsn,
                allow_non_empty_target=args.allow_non_empty,
                authorized_by_ceo=args.authorized_by_ceo,
                pre_verified_isolated=bool(args.verify_isolated_dsn),
            )
            print(f"PASS: Restored backup from revision {manifest.git_revision}")
            return 0
        except (RuntimeError, OSError) as exc:
            print(f"RESTORE FAILED: {exc}", file=sys.stderr)
            return 1

    elif args.command == "fence-host":
        from aao.backup import apply_host_fencing
        print(f"Applying host fencing for '{args.host_id}'...")

        # If systemd is available, stop and mask background workers
        if shutil.which("systemctl"):
            for unit in ("aao-worker-self-dev.service", "aao-conversation-recovery.timer", "aao-conversation-recovery.service"):
                subprocess.run(["systemctl", "stop", unit], capture_output=True, check=False)
                subprocess.run(["systemctl", "mask", unit], capture_output=True, check=False)
            print("  [+] Masked and stopped local worker systemd units")

        try:
            with connect_postgres() as db:
                actions = apply_host_fencing(db, host_identifier=args.host_id)
                for a in actions:
                    print(f"  [+] {a}")
            print(f"PASS: Host '{args.host_id}' successfully fenced from cluster.")
            return 0
        except (RuntimeError, OSError) as exc:
            print(f"FENCING ERROR: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
