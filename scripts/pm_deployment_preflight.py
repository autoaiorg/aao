#!/usr/bin/env python3
"""Read-only local PM deployment inventory; never an activation or authority grant.

Only metadata is inspected: no token/key/config file contents, GitHub requests,
provider calls, installation, migration, service start or grant creation.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
from pathlib import Path
from uuid import UUID

PROJECT_ID = "9d17d6c1-d644-424a-a425-fe7e084c3d91"
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_GRANTS = {"project.read", "work.assign", "work.coordinate"}


def result(check: str, status: str, detail: str, action: str = "") -> dict:
    return {"check": check, "status": status, "detail": detail, "action": action}


def path_check(
    name: str, path: Path, uid: int, mode: int | None = None, directory: bool = False
) -> dict:
    """lstat only, including ancestors: never dereference a secret or read its bytes."""
    try:
        info = path.lstat()
        ancestors = [p.lstat() for p in path.parents]
    except FileNotFoundError:
        return result(name, "MISSING", "Path absent", f"Administrator provision {path}")
    except OSError:
        return result(name, "UNVERIFIED", "Path metadata inaccessible", f"Inspect {path} as owner")
    valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    safe = all(
        not stat.S_ISLNK(p.st_mode) and not p.st_mode & 0o022 and p.st_uid in {0, uid}
        for p in ancestors
    )
    # A private runtime may live below /run/user, not a shared writable /tmp tree.
    valid_mode = (
        stat.S_IMODE(info.st_mode) == mode if mode is not None else not info.st_mode & 0o022
    )
    if not valid_type or info.st_uid != uid or not valid_mode or not safe:
        return result(
            name,
            "MISSING",
            "Ownership, type, mode or ancestor boundary unsafe",
            f"Administrator inspect ownership/permissions and symlinks: {path}",
        )
    return result(name, "PASS", f"Metadata only: {path}")


def host_checks(project_id: str) -> list[dict]:
    checks = []
    accounts = {}
    expected = {
        "aao-pm": 1001,
        "aao-impl-codex": 1002,
        "aao-supervisor": 1008,
        "aao-auditor": None,
        "aao-auditor-alt": None,
        "aao-integrator": None,
    }
    for name, uid in expected.items():
        try:
            account = pwd.getpwnam(name)
        except KeyError:
            checks.append(
                result(
                    f"linux:{name}", "MISSING", "Account absent", "Administrator provision account"
                )
            )
            continue
        accounts[name] = account
        checks.append(
            result(
                f"linux:{name}",
                "PASS" if uid is None or account.pw_uid == uid else "MISSING",
                f"Observed UID {account.pw_uid}",
                "Verify dedicated account mapping",
            )
        )
    ids = [account.pw_uid for account in accounts.values()]
    checks.append(
        result(
            "linux:distinct-uids",
            "PASS" if len(ids) == len(set(ids)) else "MISSING",
            "Observed account UIDs must be distinct",
            "Administrator separate identities",
        )
    )
    for suffix in ("tree", "venv"):
        checks.append(
            path_check(
                f"frozen:{suffix}", Path("/srv/aao/frozen/aao-pm") / suffix, 0, directory=True
            )
        )
    for name in ("aao-pm", "aao-impl-codex"):
        if name not in accounts:
            continue
        account = accounts[name]
        home = Path(account.pw_dir)
        runtime = Path(f"/run/user/{account.pw_uid}")
        checks.append(path_check(f"runtime:{name}", runtime, account.pw_uid, 0o700, True))
        for extension in ("pem", "json"):
            checks.append(
                path_check(
                    f"w2:{name}:{extension}",
                    home / ".config/aao" / f"{name}.{extension}",
                    account.pw_uid,
                    0o600,
                )
            )
        checks.append(
            path_check(
                f"w2:{name}:publisher-token", runtime / "aao-publisher.token", account.pw_uid, 0o600
            )
        )
        if name == "aao-pm":
            checks.append(path_check("pm:token", runtime / "aao-pm.token", account.pw_uid, 0o600))
            checks.append(
                path_check(
                    "pm:environment",
                    home / ".config/aao/project-coordinator" / f"{project_id}.env",
                    account.pw_uid,
                    0o600,
                )
            )
            checks.append(
                path_check(
                    "pm:unit",
                    home / ".config/systemd/user/aao-project-coordinator@.service",
                    account.pw_uid,
                )
            )
    for name, detail, action in (
        (
            "pm:service",
            "Service enablement, running state and frozen revision not inspected",
            "Administrator verify approved revision, installed unit content and user service; do not start implicitly",
        ),
        (
            "w2:live",
            "Metadata cannot prove App installation scopes, token identity, candidate or real publication",
            "Follow W2_REAL_GITHUB_APPS.md under separate accounts; record real evidence without CEO token",
        ),
    ):
        checks.append(result(name, "UNVERIFIED", detail, action))
    return checks


def database_checks(
    db, project_id: str, principal_id: str | None, runtime_role: str | None
) -> list[dict]:
    """Caller supplies a dedicated connection. All SQL runs in a READ ONLY transaction."""
    checks = []
    with db.transaction():
        db.execute("SET TRANSACTION READ ONLY")
        rows = db.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {r[0] for r in rows}
        manifest = [
            p
            for p in (ROOT / "db/postgres").glob("*.sql")
            if p.name[:3].isdigit() and 1 <= int(p.name[:3]) <= 35
        ]
        numbers = [int(p.name[:3]) for p in manifest]
        absent = sorted(set(range(1, 36)) - set(numbers))
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if absent or duplicates:
            checks.append(
                result(
                    "db:migrations-001-035",
                    "UNVERIFIED",
                    f"Invalid local migration manifest; absent numbers: {absent}; duplicate numbers: {duplicates}",
                    "Restore complete unique local manifest 001..035 before checking installation",
                )
            )
        else:
            missing = sorted({p.stem for p in manifest} - applied)
            checks.append(
                result(
                    "db:migrations-001-035",
                    "MISSING" if missing else "PASS",
                    "Missing: " + ", ".join(missing) if missing else "All 001..035 recorded",
                    "Administrator apply missing migrations; preflight never applies them"
                    if missing
                    else "",
                )
            )
        project = db.execute(
            "SELECT p.state, m.status FROM projects p JOIN mandates m ON m.id=p.mandate_id WHERE p.id=%s",
            (project_id,),
        ).fetchone()
        checks.append(
            result(
                "db:project",
                "PASS" if project == ("ACTIVE", "CONFIRMED") else "MISSING",
                "Active project and confirmed mandate"
                if project == ("ACTIVE", "CONFIRMED")
                else "Project absent/inactive or mandate unconfirmed",
                "CEO confirm project/mandate as appropriate",
            )
        )
        if principal_id is None:
            checks.append(
                result(
                    "db:pm-identity-grants",
                    "UNVERIFIED",
                    "No persisted PM principal selected; Linux name is not AAO identity",
                    "Identify registered PM and rerun with --principal-id",
                )
            )
        else:
            identity = db.execute(
                "SELECT kind, enabled FROM principal_credentials WHERE principal_id=%s",
                (principal_id,),
            ).fetchone()
            checks.append(
                result(
                    "db:pm-identity",
                    "PASS" if identity == ("AGENT", True) else "MISSING",
                    "Enabled AGENT required",
                    "CEO provision/enable dedicated PM identity if absent",
                )
            )
            rows = db.execute(
                "SELECT capability FROM project_grants WHERE principal_id=%s AND project_id=%s AND (expires_at IS NULL OR expires_at > clock_timestamp())",
                (principal_id, project_id),
            ).fetchall()
            missing = sorted(REQUIRED_GRANTS - {r[0] for r in rows})
            checks.append(
                result(
                    "db:pm-grants",
                    "PASS" if not missing and identity == ("AGENT", True) else "MISSING",
                    "Missing live grants: " + ", ".join(missing)
                    if missing
                    else "Live grants checked; identity must also be enabled",
                    "Only CEO may issue required scoped expiring grants; never auto-grant",
                )
            )
        connection_role = db.execute(
            "SELECT current_user, rolsuper FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        checks.append(
            result(
                "db:inspection-connection",
                "PASS",
                f"Inspection connection superuser={connection_role[1]}; NOT runtime identity",
            )
        )
        checks.extend(runtime_checks(db, runtime_role))
    return checks


def runtime_checks(db, role: str | None) -> list[dict]:
    if role is None:
        return [
            result(
                "db:runtime-role",
                "UNVERIFIED",
                "Runtime role not identified; developer connection does not prove runtime installation",
                "Administrator provision least-privilege role, then supply --runtime-role",
            )
        ]
    row = db.execute(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname=%s",
        (role,),
    ).fetchone()
    if row is None or any(row[:5]) or not row[5]:
        return [
            result(
                "db:runtime-role",
                "MISSING",
                "Role absent, elevated or cannot login",
                "Administrator provision non-elevated login runtime role",
            )
        ]
    checks = [
        result("db:runtime-role", "PASS", "Non-elevated login role; credentials not inspected")
    ]
    for table, needed in (
        ("protocol_instances", "SELECT,INSERT"),
        ("project_routines", "SELECT,INSERT,UPDATE"),
        ("routine_occurrences", "SELECT,INSERT"),
    ):
        row = db.execute(
            "SELECT has_table_privilege(%s, %s, 'DELETE'), pg_has_role(%s, c.relowner, 'USAGE'), EXISTS (SELECT 1 FROM aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a WHERE a.grantee=0 AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE')) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=%s",
            (role, f"public.{table}", role, table),
        ).fetchone()
        if row is None:
            checks.append(
                result(
                    f"db:runtime:{table}",
                    "MISSING",
                    "Table absent",
                    "Administrator apply migrations",
                )
            )
            continue
        truncate = db.execute(
            "SELECT has_table_privilege(%s, %s, 'TRUNCATE')", (role, f"public.{table}")
        ).fetchone()[0]
        allowed = not row[0] and not row[1] and not row[2] and not truncate
        for privilege in needed.split(","):
            allowed = (
                bool(
                    db.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, f"public.{table}", privilege),
                    ).fetchone()[0]
                )
                and allowed
            )
        if table == "protocol_instances":
            allowed = (
                allowed
                and not db.execute(
                    "SELECT has_table_privilege(%s, %s, 'UPDATE')", (role, f"public.{table}")
                ).fetchone()[0]
            )
        checks.append(
            result(
                f"db:runtime:{table}",
                "PASS" if allowed else "MISSING",
                f"Requires {needed}; no PUBLIC DML/TRUNCATE, ownership or DELETE/TRUNCATE"
                + ("/UPDATE" if table == "protocol_instances" else ""),
                "Administrator review explicit grants; 033/035 revoke PUBLIC",
            )
        )
    checks.append(
        result(
            "db:runtime-complete",
            "UNVERIFIED",
            "Checks cover 033/035 tables, not all backend runtime privileges or role inheritance",
            "Administrator validate full runtime permissions and authenticate using runtime role before deployment",
        )
    )
    return checks


def local_connection_options(url: str) -> dict:
    """Reject service/remote targets, including libpq environment fallbacks."""
    from psycopg.conninfo import conninfo_to_dict

    options = conninfo_to_dict(url)
    host = options.get("host", os.environ.get("PGHOST", ""))
    addr = options.get("hostaddr", os.environ.get("PGHOSTADDR", ""))
    if (
        options.get("service")
        or os.environ.get("PGSERVICE")
        or not host
        or "," in host
        or not (host in {"localhost", "127.0.0.1", "::1"} or host.startswith("/"))
        or addr not in {"", "127.0.0.1", "::1"}
    ):
        raise ValueError(
            "Preflight requires an explicit local PostgreSQL target without service indirection"
        )
    return {**options, "host": host, "hostaddr": addr, "connect_timeout": 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=lambda value: str(UUID(value)), default=PROJECT_ID)
    parser.add_argument("--principal-id")
    parser.add_argument("--runtime-role")
    args = parser.parse_args(argv)
    checks = host_checks(args.project_id)
    try:
        import psycopg

        from aao.postgresql_connection import database_url

        options = local_connection_options(database_url())
        with psycopg.connect(**options) as db:
            checks.extend(
                database_checks(db, args.project_id, args.principal_id, args.runtime_role)
            )
    except Exception as exc:  # noqa: BLE001 - redact all database/config exception payloads
        # libpq errors can contain DSN/credentials. Never serialize exception messages.
        checks.append(
            result(
                "db:inspection",
                "UNVERIFIED",
                f"Database inspection unavailable ({type(exc).__name__})",
                "Configure normal backend local connection; inspect privately, never paste DSN or CEO token",
            )
        )
    ready = all(item["status"] == "PASS" for item in checks)
    print(json.dumps({"readOnly": True, "ready": ready, "checks": checks}, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
