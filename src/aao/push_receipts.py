"""Authenticated, durable GitHub push receipts for supervisor attribution.

The receiver must validate GitHub's HMAC before calling ``store_push_receipt``.
Files are additionally signed with the supervisor key so later attribution can
reject modification after receipt, without granting the GitHub webhook service
write access to the governance ledger.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from aao.integration_authorization import canonical
from aao.supervisor import _sign

SCHEMA = "aao.github-push-receipt.v1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DELIVERY = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")


def validate_signature(secret: bytes, body: bytes, signature: str) -> bool:
    """Check the GitHub X-Hub-Signature-256 header without leaking secret data."""
    if not secret or not isinstance(signature, str) or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def normalize_push(payload: Any, *, repository: str, delivery_id: str) -> dict[str, str]:
    """Extract only identity and ref transition fields required to attribute pushes."""
    if not isinstance(delivery_id, str) or not _DELIVERY.fullmatch(delivery_id):
        raise ValueError("invalid webhook delivery id")
    if not isinstance(payload, dict) or payload.get("deleted") is True:
        raise ValueError("payload is not an attributable branch push")
    repo = payload.get("repository")
    sender = payload.get("sender")
    if not isinstance(repo, dict) or repo.get("full_name") != repository:
        raise ValueError("push repository does not match configured repository")
    if not isinstance(sender, dict) or not isinstance(sender.get("login"), str) or not sender["login"].strip():
        raise ValueError("push sender is missing")
    ref, before, after = payload.get("ref"), payload.get("before"), payload.get("after")
    if not isinstance(ref, str) or not ref.startswith("refs/heads/") or not ref.removeprefix("refs/heads/"):
        raise ValueError("push ref is not a branch")
    if not isinstance(before, str) or not _SHA.fullmatch(before) or not isinstance(after, str) or not _SHA.fullmatch(after):
        raise ValueError("push transition contains an invalid commit SHA")
    return {"schema": SCHEMA, "delivery_id": delivery_id.lower(), "repository": repository,
            "actor": sender["login"], "ref": ref, "before": before, "after": after}


def _atomic_create(path: Path, data: bytes) -> None:
    """Create a new mode-0640 receipt atomically; an identical redelivery is idempotent."""
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
        raise ValueError("push receipt directory is not protected")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    except FileExistsError:
        fd = None
    if fd is None:
        existing_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(existing_fd, "rb") as existing:
            info = os.fstat(existing.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022
                    or existing.read() != data):
                raise ValueError("webhook delivery id conflicts with an existing receipt")
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def store_push_receipt(directory: Path, payload: Any, *, repository: str, delivery_id: str,
                       raw_body: bytes, secret: bytes, signature: str, private_key: str) -> Path:
    """Authenticate, normalize, supervisor-sign and durably store one webhook push."""
    if not validate_signature(secret, raw_body, signature):
        raise ValueError("GitHub webhook signature is invalid")
    receipt = normalize_push(payload, repository=repository, delivery_id=delivery_id)
    signed = _sign(receipt, private_key)
    path = Path(directory) / f"{receipt['delivery_id']}.json"
    _atomic_create(path, canonical(signed) + b"\n")
    return path


def read_push_receipts(directory: Path, *, repository: str, private_key: str) -> list[dict[str, str]]:
    """Read only protected receipt files, verify supervisor signatures and their schema."""
    directory = Path(directory)
    try:
        info = directory.lstat()
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("push receipt directory is not protected")
    with tempfile.TemporaryDirectory() as temporary:
        public = Path(temporary) / "public.pem"
        subprocess.run(["openssl", "pkey", "-in", private_key, "-pubout", "-out", str(public)],
                       check=True, capture_output=True)
        receipts = []
        for path in sorted(directory.iterdir()):
            if path.suffix != ".json":
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
                    raise ValueError("push receipt file is not protected")
                try:
                    signed = json.loads(handle.read())
                    if not isinstance(signed, dict):
                        raise TypeError("receipt is not a JSON object")
                    signature = base64.b64decode(signed.pop("signature"), validate=True)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                    raise ValueError("push receipt is malformed") from error
            signature_path = Path(temporary) / "signature"
            message_path = Path(temporary) / "message"
            signature_path.write_bytes(signature)
            message_path.write_bytes(canonical(signed))
            verified = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public),
                "-sigfile", str(signature_path), "-in", str(message_path), "-rawin"],
                check=False, capture_output=True)
            expected = {"schema", "delivery_id", "repository", "actor", "ref", "before", "after"}
            if verified.returncode or set(signed) != expected or signed.get("schema") != SCHEMA:
                raise ValueError("push receipt signature or schema is invalid")
            if (not isinstance(signed["repository"], str) or signed["repository"].count("/") != 1
                    or not all(signed["repository"].split("/")) or not isinstance(signed["delivery_id"], str)
                    or not _DELIVERY.fullmatch(signed["delivery_id"]) or path.stem != signed["delivery_id"]
                    or not isinstance(signed["before"], str) or not _SHA.fullmatch(signed["before"])
                    or not isinstance(signed["after"], str) or not _SHA.fullmatch(signed["after"])):
                raise ValueError("push receipt repository or commit schema is invalid")
            if (not isinstance(signed["ref"], str) or not signed["ref"].startswith("refs/heads/")
                    or not isinstance(signed["actor"], str) or not signed["actor"].strip()):
                raise ValueError("push receipt identity or ref is invalid")
            if signed["repository"] != repository:
                continue
            receipts.append(signed)
        return receipts


def make_webhook_handler(*, directory: Path, repository: str, repositories: set[str] | None = None,
                         secret: bytes,
                         private_key: str) -> type[BaseHTTPRequestHandler]:
    """Build a request handler; publish only behind a TLS-terminating reverse proxy."""
    if not secret:
        raise ValueError("webhook secret is required")
    allowed_repositories = repositories or {repository}
    if not allowed_repositories or repository not in allowed_repositories:
        raise ValueError("webhook repository allowlist must include the configured canonical repository")
    class Handler(BaseHTTPRequestHandler):
        server_version = "AAO-Push-Receipt"

        def log_message(self, _format: str, *_args: Any) -> None:
            # Do not log request headers or payloads; delivery metadata is sufficient for access logs upstream.
            return

        def do_POST(self) -> None:
            if self.path != "/github/push":
                self.send_error(404)
                return
            length = self.headers.get("Content-Length")
            if not length or not length.isdecimal() or int(length) > 25 * 1024 * 1024:
                self.send_error(413)
                return
            if self.headers.get("X-GitHub-Event") != "push":
                self.send_error(400)
                return
            try:
                raw_body = self.rfile.read(int(length))
                if len(raw_body) != int(length):
                    raise ValueError("incomplete request body")
                payload = json.loads(raw_body)
                payload_repo = payload.get("repository") if isinstance(payload, dict) else None
                receipt_repo = payload_repo.get("full_name") if isinstance(payload_repo, dict) else None
                if receipt_repo not in allowed_repositories:
                    raise ValueError("webhook repository is not allowlisted")
                store_push_receipt(directory, payload, repository=receipt_repo,
                    delivery_id=self.headers.get("X-GitHub-Delivery", ""), raw_body=raw_body,
                    secret=secret, signature=self.headers.get("X-Hub-Signature-256", ""),
                    private_key=private_key)
            except (ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
                self.send_error(401)
                return
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def serve_webhook(*, bind: str, port: int, directory: Path, repository: str, secret: bytes,
                  private_key: str, repositories: set[str] | None = None) -> None:
    """Serve the GitHub webhook receiver; deploy behind a TLS-terminating reverse proxy."""
    if not 1 <= port <= 65535:
        raise ValueError("valid webhook port is required")
    ThreadingHTTPServer((bind, port), make_webhook_handler(
        directory=directory, repository=repository, repositories=repositories, secret=secret,
        private_key=private_key)).serve_forever()
