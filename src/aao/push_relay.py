"""Opt-in pull transport; only ack after existing HMAC-verified durable local storage.

No service configuration, credential discovery, webhook creation or deployment.
The caller must run under the supervisor identity with explicitly provisioned secrets.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from aao.github_delivery_corroboration import PushWebhookTrust, corroborate_push_delivery
from aao.push_receipts import store_push_receipt


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def drain_one(*, endpoint: str, pull_secret: bytes, github_secret: bytes,
              github_api_token: str, webhook_trust: PushWebhookTrust,
              directory: Path, private_key: str, opener=None,
              github_opener=None) -> bool:
    """Retrieve at most one receipt; failures never ack and may be retried idempotently."""
    url = urllib.parse.urlsplit(endpoint)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("relay must be an HTTPS origin without credentials or path")
    if len(pull_secret) < 32 or len(github_secret) < 32 or pull_secret == github_secret:
        raise ValueError("distinct relay and webhook secrets of at least 32 bytes required")
    if (not isinstance(github_api_token, str) or not github_api_token.strip()
            or github_api_token.encode() in (pull_secret, github_secret)):
        raise ValueError("explicit independent GitHub API credential is required")
    transport = opener or urllib.request.build_opener(_NoRedirect())

    def request(method: str, path: str) -> bytes:
        timestamp = str(int(time.time()))
        message = f"{method}\n{path}\n{timestamp}\n{hashlib.sha256(b'').hexdigest()}".encode()
        signature = hmac.new(pull_secret, message, hashlib.sha256).hexdigest()
        req = urllib.request.Request(endpoint.rstrip("/") + path, method=method,
            data=b"" if method == "POST" else None,
            headers={"X-AAO-Timestamp": timestamp, "X-AAO-Signature": signature})
        try:
            with transport.open(req, timeout=20) as response:
                body = response.read(1500001)
                if len(body) > 1500000 or response.status != (200 if method == "GET" else 204):
                    raise ValueError("relay response rejected")
                return body
        except (urllib.error.URLError, OSError):
            raise ValueError("relay request failed") from None

    rows = json.loads(request("GET", "/receipts"))
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError("invalid relay batch")
    if not rows:
        return False
    row = rows[0]
    if not isinstance(row, dict):
        raise TypeError("invalid relay receipt")
    raw_body = base64.b64decode(row["body_base64"], validate=True)
    payload = json.loads(raw_body)
    repository = payload.get("repository", {}).get("full_name")
    if repository != webhook_trust.repository:
        raise ValueError("relay repository is not allowlisted by verified configuration")
    confirmed_payload = corroborate_push_delivery(
        token=github_api_token, trust=webhook_trust, delivery_guid=row.get("delivery_id"),
        relay_payload=payload, opener=github_opener)
    # HMAC protects the relayed original bytes; GitHub's separately fetched
    # delivery corroborates the specific identity and ref-transition claims.
    store_push_receipt(directory, confirmed_payload, repository=repository,
        delivery_id=row["delivery_id"], raw_body=raw_body, secret=github_secret,
        signature=row["signature"], private_key=private_key)
    request("POST", f"/receipts/{row['delivery_id'].lower()}/ack")
    return True
