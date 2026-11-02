#!/usr/bin/env python3
"""Idempotent technical state initialization for AAO.

Enforces strict separation between technical seeding and CEO reserved governance decisions.
Conforms strictly to CEO Condition 5: no confirmed mandate or active project
is created without verifiable CEO authorization.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from aao.postgresql_connection import connect_postgres

MANDATE_TITLE = "AAO — Self Development"
MANDATE_OBJECTIVE = (
    "Build the minimum functional AAO core that can manage, develop, test, "
    "audit, and improve AAO software as its first project, observable from "
    "AAO Control Center using authentic shared backend state."
)
PROJECT_NAME = "AAO — Self Development"
DEFAULT_ORG_UNIT_ID = "org-engineering"


def init_organization_structure(db: Any) -> list[str]:
    """Ensure base organizational units exist without overriding customized records."""
    created = []
    unit = db.execute(
        "SELECT id FROM organization_units WHERE id=%s",
        (DEFAULT_ORG_UNIT_ID,),
    ).fetchone()
    if not unit:
        db.execute(
            """
            INSERT INTO organization_units (id, name, code, enabled)
            VALUES (%s, 'Ingeniería y Desarrollo', 'ENG', TRUE)
            ON CONFLICT (id) DO NOTHING
            """,
            (DEFAULT_ORG_UNIT_ID,),
        )
        created.append(f"unit:{DEFAULT_ORG_UNIT_ID}")
    return created


def check_self_development_status(db: Any) -> dict[str, Any]:
    """Inspect the database for existing Self-Development mandate and project."""
    mandate_row = db.execute(
        "SELECT id, title, status FROM mandates WHERE title=%s",
        (MANDATE_TITLE,),
    ).fetchone()

    project_row = db.execute(
        "SELECT id, name, state FROM projects WHERE name=%s",
        (PROJECT_NAME,),
    ).fetchone()

    return {
        "mandate": {
            "id": mandate_row[0],
            "title": mandate_row[1],
            "status": mandate_row[2],
        }
        if mandate_row
        else None,
        "project": {
            "id": str(project_row[0]),
            "name": project_row[1],
            "state": project_row[2],
        }
        if project_row
        else None,
    }


def draft_self_development_mandate_proposal(db: Any) -> str:
    """Draft a mandate proposal if none exists. Leaves status strictly in DRAFT."""
    status = check_self_development_status(db)
    if status["mandate"]:
        return status["mandate"]["id"]

    mandate_id = str(uuid4())
    event_id = str(uuid4())
    db.execute(
        """
        INSERT INTO mandates(id, title, objective, status)
        VALUES (%s, %s, %s, 'DRAFT')
        """,
        (mandate_id, MANDATE_TITLE, MANDATE_OBJECTIVE),
    )
    db.execute(
        """
        INSERT INTO events(id, subject_id, kind, details)
        VALUES (%s, %s, 'mandate.drafted', %s)
        """,
        (event_id, mandate_id, json.dumps({"title": MANDATE_TITLE, "objective": MANDATE_OBJECTIVE})),
    )
    return mandate_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AAO Technical State Initializer")
    parser.add_argument(
        "--ensure-proposal",
        action="store_true",
        help="Draft Self-Development mandate proposal in DRAFT status if missing",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report status of state entities without modifying",
    )
    args = parser.parse_args(argv)

    with connect_postgres() as db:
        if args.status:
            status = check_self_development_status(db)
            print("Status of AAO state entities:")
            print(f"  Mandate: {status['mandate']}")
            print(f"  Project: {status['project']}")
            return 0

        created_units = init_organization_structure(db)
        if created_units:
            print(f"Initialized organizational units: {', '.join(created_units)}")
        else:
            print("Organizational units already initialized.")

        status = check_self_development_status(db)
        if status["mandate"]:
            print(f"Mandate found: {status['mandate']['id']} ({status['mandate']['status']})")
        elif args.ensure_proposal:
            m_id = draft_self_development_mandate_proposal(db)
            print(f"PROPOSED: Mandate drafted with ID {m_id}. Status: DRAFT (PENDING CEO confirmation).")
        else:
            print("NOTICE: No Self-Development mandate exists. Run with --ensure-proposal to create DRAFT.")

        if status["project"]:
            print(f"Project found: {status['project']['id']} ({status['project']['state']})")
        else:
            print("NOTICE: No active project. Requires CEO confirmation before project activation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
