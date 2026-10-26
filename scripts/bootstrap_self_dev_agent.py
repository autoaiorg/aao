#!/usr/bin/env python3
"""One-shot local CEO bootstrap for a narrowly scoped Self Development agent.

The CEO bearer is entered through a no-echo terminal prompt, used only for
loopback API requests, and never written or printed. The newly issued agent
bearer is written only to the user's private runtime directory.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MANDATE_TITLE = "AAO — Self Development"
MANDATE_OBJECTIVE = (
    "Build the minimum functional AAO core that can manage, develop, test, "
    "audit, and improve AAO software as its first project, observable from "
    "AAO Control Center using authentic shared backend state."
)
PROJECT_NAME = "AAO — Self Development"
GRANTS = (
    "project.read", "work.create", "work.admit", "work.progress", "execution.claim",
)
GRANT_LIFETIME = timedelta(hours=8)


class BootstrapError(RuntimeError):
    pass


def request_json(base_url: str, path: str, *, method: str = "GET",
                 ceo_token: str | None = None, agent_token: str | None = None,
                 body: dict | None = None) -> dict | list:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if ceo_token is not None:
        headers["X-CEO-Token"] = ceo_token
    if agent_token is not None:
        headers["X-Agent-Token"] = agent_token
    payload = None if body is None else json.dumps(body).encode()
    request = Request(
        f"{base_url}{path}",
        data=payload,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        if exc.code == 405:
            raise BootstrapError(
                "the local API does not support the requested HTTP method; "
                "restart it from the current checkout and retry"
            ) from None
        raise BootstrapError(f"AAO API rejected the bootstrap request (HTTP {exc.code})") from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise BootstrapError("AAO API is unavailable or returned invalid data") from None


def private_runtime_file() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise BootstrapError("XDG_RUNTIME_DIR is required; no persistent fallback is used")
    directory = Path(runtime).resolve()
    try:
        mode = stat.S_IMODE(directory.stat().st_mode)
    except OSError:
        raise BootstrapError("XDG_RUNTIME_DIR is unavailable") from None
    if directory.stat().st_uid != os.getuid() or mode & 0o077:
        raise BootstrapError("XDG_RUNTIME_DIR must be owned by this user and private")
    target = directory / "aao-self-development-agent.token"
    if target.exists():
        raise BootstrapError("agent token file already exists; refusing to overwrite it")
    return target


def write_private_token(path: Path, token: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(token)
            stream.write("\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def ensure_mandated_project(base_url: str, ceo_token: str) -> tuple[dict, dict]:
    """Verify the separately confirmed AAO self-development scope."""
    mandates = request_json(base_url, "/v1/mandates", ceo_token=ceo_token)
    if not isinstance(mandates, list):
        raise BootstrapError("mandate inventory response is invalid")
    matches = [row for row in mandates if row.get("title") == MANDATE_TITLE]
    if len(matches) > 1:
        raise BootstrapError("multiple matching CEO mandates exist; refusing ambiguity")
    if matches:
        mandate = matches[0]
        if mandate.get("objective") != MANDATE_OBJECTIVE:
            raise BootstrapError("existing CEO mandate does not match the canonical objective")
    else:
        if any(
            isinstance(row.get("project"), dict)
            and row["project"].get("name") == PROJECT_NAME
            for row in mandates
        ):
            raise BootstrapError("project name is already bound to a different mandate")
        raise BootstrapError(
            "separately CEO-confirmed mandate is required; bootstrap will not create or confirm one"
        )

    mandate_id = mandate["id"]
    if mandate.get("status") != "CONFIRMED":
        raise BootstrapError(
            "CEO mandate is not confirmed; bootstrap will not confirm it"
        )

    inventory = request_json(base_url, "/v1/mandates", ceo_token=ceo_token)
    record = next((row for row in inventory if row.get("id") == mandate_id), None)
    if not record or record.get("status") != "CONFIRMED":
        raise BootstrapError("confirmed mandate could not be verified")
    events = record.get("events")
    if not isinstance(events, list) or not any(
        event.get("kind") == "mandate.confirmed"
        and event.get("subject_id") == mandate_id
        for event in events
    ):
        raise BootstrapError("mandate confirmation event is missing")

    project = record.get("project")
    if project is None:
        if any(
            isinstance(row.get("project"), dict)
            and row["project"].get("name") == PROJECT_NAME
            for row in inventory
        ):
            raise BootstrapError("project name is already bound to a different mandate")
        project = request_json(
            base_url, "/v1/projects", method="POST", ceo_token=ceo_token,
            body={"name": PROJECT_NAME, "mandate_id": mandate_id},
        )
        if not isinstance(project, dict) or not project.get("id"):
            raise BootstrapError("project creation response is invalid")
        inventory = request_json(base_url, "/v1/mandates", ceo_token=ceo_token)
        record = next((row for row in inventory if row.get("id") == mandate_id), None)
        project = record.get("project") if record else None
    if (
        not isinstance(project, dict)
        or project.get("name") != PROJECT_NAME
        or project.get("state") != "ACTIVE"
    ):
        raise BootstrapError("project record does not match the active mandate scope")
    project_events = [
        event for event in record["events"]
        if event.get("kind") == "project.created"
        and event.get("subject_id") == project.get("id")
    ]
    if not project_events:
        raise BootstrapError("project creation event is missing")
    return record, project


def bootstrap(
    base_url: str, *, ceo_token: str | None = None,
) -> tuple[str, str, str, datetime, Path]:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise BootstrapError("bootstrap is restricted to the local HTTP API")
    if parsed.path or parsed.query or parsed.fragment:
        raise BootstrapError("base URL must not contain a path, query, or fragment")
    token_path = private_runtime_file()
    if ceo_token is None:
        ceo_token = getpass.getpass("CEO development token (hidden): ")
    if not ceo_token:
        raise BootstrapError("CEO credential is required")

    mandate, project = ensure_mandated_project(base_url, ceo_token)
    # Inspect the currently authorized inventory before creating any new identity.
    # The endpoint is CEO-only and returns metadata only, never credential material.
    existing_grants = request_json(
        base_url, f"/v1/projects/{project['id']}/grants", ceo_token=ceo_token,
    )
    if not isinstance(existing_grants, list):
        raise BootstrapError("project grant inventory response is invalid")
    now = datetime.now(UTC)
    active_agents = {
        row.get("principal_id")
        for row in existing_grants
        if isinstance(row, dict)
        and row.get("kind") == "AGENT"
        and row.get("credential_enabled") is True
        and isinstance(row.get("principal_id"), str)
        and (
            row.get("expires_at") is None
            or datetime.fromisoformat(row["expires_at"]) > now
        )
    }
    if active_agents:
        raise BootstrapError(
            "an active AGENT grant already exists for this project; refusing to provision a duplicate"
        )
    principal_id = f"aao-selfdev-{secrets.token_hex(6)}"
    credential = request_json(
        base_url,
        "/v1/principals/credentials",
        method="POST",
        ceo_token=ceo_token,
        body={"principal_id": principal_id, "kind": "AGENT"},
    )
    if not isinstance(credential, dict) or credential.get("principal_id") != principal_id:
        raise BootstrapError("credential issuance response is invalid")
    agent_token = credential.get("token")
    if not isinstance(agent_token, str) or not agent_token:
        raise BootstrapError("credential issuance response omitted the agent token")

    expiry = datetime.now(UTC) + GRANT_LIFETIME
    grant_body = {"principal_id": principal_id, "expires_at": expiry.isoformat()}
    try:
        for capability in GRANTS:
            response = request_json(
                base_url,
                f"/v1/projects/{project['id']}/grants",
                method="POST",
                ceo_token=ceo_token,
                body={**grant_body, "capability": capability},
            )
            if not isinstance(response, dict) or response.get("created") is not True:
                raise BootstrapError("a narrowly scoped project grant was not created")
        visible_projects = request_json(
            base_url, "/v1/projects", agent_token=agent_token,
        )
        if not isinstance(visible_projects, list) or not any(
            item.get("id") == project["id"] for item in visible_projects
        ):
            raise BootstrapError("the issued AGENT identity failed its scoped read check")
        write_private_token(token_path, agent_token)
    except BaseException:
        try:
            request_json(
                base_url,
                f"/v1/principals/{principal_id}/revoke",
                method="POST",
                ceo_token=ceo_token,
                body={},
            )
        except BootstrapError:
            pass
        token_path.unlink(missing_ok=True)
        raise
    finally:
        del ceo_token
        del agent_token

    return principal_id, mandate["id"], project["id"], expiry, token_path


def configured_local_ceo_token() -> str:
    """Load the explicitly selected private development dotenv, without echoing it."""
    if os.environ.get("AAO_ENV", "development").lower() != "development":
        raise BootstrapError("configured-token bootstrap is restricted to development")
    if "AAO_CEO_TOKEN" in os.environ:
        raise BootstrapError(
            "AAO_CEO_TOKEN is already inherited by this process; refusing ambiguous configuration"
        )
    from aao.environment_settings import load_local_env

    loaded = load_local_env()
    expected = Path(__file__).resolve().parents[1] / ".env.local"
    if loaded != expected or not expected.is_file() or expected.is_symlink():
        raise BootstrapError("private .env.local was not selected as the local configuration source")
    info = expected.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BootstrapError(".env.local must be owned by this user and private")
    token = os.environ.get("AAO_CEO_TOKEN")
    if not token:
        raise BootstrapError("AAO_CEO_TOKEN is absent from the selected local configuration")
    return token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--use-local-configured-ceo-token", action="store_true",
        help="use AAO_CEO_TOKEN from private .env.local without prompting or displaying it",
    )
    arguments = parser.parse_args()
    try:
        local_token = configured_local_ceo_token() if arguments.use_local_configured_ceo_token else None
        principal, mandate, project, expiry, token_file = bootstrap(
            arguments.base_url, ceo_token=local_token,
        )
    except BootstrapError as exc:
        print(f"Bootstrap not completed: {exc}", file=sys.stderr)
        return 1
    print(f"AGENT provisioned: {principal}")
    print(f"Confirmed mandate: {mandate}")
    print(f"Project: {PROJECT_NAME} ({project})")
    print(f"Grants: {', '.join(GRANTS)}")
    print(f"Grant expiry (UTC): {expiry.isoformat()}")
    print(f"Agent token file (mode 0600): {token_file}")
    print("No CEO or AGENT credential was printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
