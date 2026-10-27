"""Read-only corroboration of relayed GitHub push deliveries.

The caller supplies the API credential and a trust configuration obtained from
separately verified configuration/persisted AAO identities. This module does
not discover credentials, verify repository administration, or create hooks.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
_LOGIN = re.compile(r"[^\s/]+\Z")


@dataclass(frozen=True)
class PushWebhookTrust:
    """Externally verified repo/hook IDs and persisted GitHub-App identity map.

    The caller is responsible for sourcing this from verified operational
    configuration and persisted AAO identity records. Values are schema-checked
    here but are not independently proven by this dataclass.
    """

    repository: str
    repository_id: int
    hook_id: int
    # Exact immutable GitHub sender user ID and login -> persisted AAO principal ID.
    actor_map: Mapping[tuple[int, str], str]

    def validate(self) -> tuple[str, str]:
        if (not isinstance(self.repository, str) or self.repository.count("/") != 1
                or not all(self.repository.split("/"))):
            raise ValueError("verified repository configuration is invalid")
        owner, repo = self.repository.split("/")
        if (not isinstance(self.repository_id, int) or isinstance(self.repository_id, bool)
                or self.repository_id <= 0 or not isinstance(self.hook_id, int)
                or isinstance(self.hook_id, bool) or self.hook_id <= 0):
            raise ValueError("verified repository or webhook ID is invalid")
        if not isinstance(self.actor_map, Mapping) or not self.actor_map:
            raise ValueError("persisted GitHub actor mapping is required")
        for identity, principal_id in self.actor_map.items():
            if (not isinstance(identity, tuple) or len(identity) != 2
                    or not isinstance(identity[0], int) or isinstance(identity[0], bool)
                    or identity[0] <= 0 or not isinstance(identity[1], str)
                    or not _LOGIN.fullmatch(identity[1]) or not isinstance(principal_id, str)
                    or not principal_id.strip()):
                raise ValueError("persisted GitHub actor mapping is invalid")
        return owner, repo


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _json_request(opener: Any, path: str, token: str) -> Any:
    if not path.startswith("/repos/") or "\r" in path or "\n" in path:
        raise ValueError("GitHub API path is invalid")
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AAO-push-corroboration",
        },
    )
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("GitHub delivery lookup returned an unexpected status")
            body = response.read(25 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("GitHub delivery credential is revoked or unauthorized") from None
        if exc.code == 503 or exc.code == 502 or exc.code == 504:
            raise ValueError("GitHub delivery corroboration is temporarily unavailable") from None
        raise ValueError("GitHub delivery lookup failed") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError("GitHub delivery corroboration request failed") from None
    if len(body) > 25 * 1024 * 1024:
        raise ValueError("GitHub delivery response is too large")
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("GitHub delivery response is malformed") from None


def _positive_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _push_claims(payload: Any) -> tuple[int, str, int, str, str, str]:
    if not isinstance(payload, dict):
        raise TypeError("push payload is not an object")
    repository, sender = payload.get("repository"), payload.get("sender")
    if not isinstance(repository, dict) or not isinstance(sender, dict):
        raise TypeError("push payload identity fields are missing")
    repo_id, sender_id = repository.get("id"), sender.get("id")
    login = sender.get("login")
    ref, before, after = payload.get("ref"), payload.get("before"), payload.get("after")
    if (not _positive_id(repo_id) or not _positive_id(sender_id)
            or not isinstance(login, str) or not _LOGIN.fullmatch(login)
            or not isinstance(ref, str) or not isinstance(before, str)
            or not isinstance(after, str)):
        raise ValueError("push payload identity or ref claims are invalid")
    return repo_id, login, sender_id, ref, before, after


def corroborate_push_delivery(*, token: str, trust: PushWebhookTrust,
                               delivery_guid: str, relay_payload: Any,
                               opener: Any = None) -> Any:
    """Fetch the exact GitHub delivery and require its identity/transition match.

    The list endpoint exposes numeric delivery IDs; the GUID is matched exactly
    before the detail endpoint is fetched. No redirect is followed. The returned
    payload is the independently fetched GitHub payload, not the relay copy.
    """
    owner, repo = trust.validate()
    if not isinstance(token, str) or not token.strip():
        raise ValueError("explicit GitHub API credential is required")
    if not isinstance(delivery_guid, str) or not _GUID.fullmatch(delivery_guid):
        raise ValueError("GitHub delivery GUID is missing or invalid")
    expected = _push_claims(relay_payload)
    if expected[0] != trust.repository_id:
        raise ValueError("relay payload repository ID does not match verified configuration")
    if relay_payload.get("repository", {}).get("full_name") != trust.repository:
        raise ValueError("relay payload does not match verified repository")
    if (expected[2], expected[1]) not in trust.actor_map:
        raise ValueError("GitHub sender has no persisted AAO identity mapping")

    transport = opener or urllib.request.build_opener(_NoRedirect())
    base = "/repos/{}/{}/hooks/{}/deliveries".format(
        urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe=""), trust.hook_id)
    deliveries = _json_request(transport, base + "?per_page=100", token)
    if not isinstance(deliveries, list):
        raise TypeError("GitHub delivery list is malformed")
    matched = [item for item in deliveries if isinstance(item, dict) and item.get("guid") == delivery_guid]
    if not matched:
        raise ValueError("GitHub delivery GUID was not found")

    fetched_payloads = []
    seen_ids: set[int] = set()
    for item in matched:
        delivery_id = item.get("id")
        if not _positive_id(delivery_id) or delivery_id in seen_ids:
            raise ValueError("GitHub delivery list contains an invalid matching ID")
        seen_ids.add(delivery_id)
        detail = _json_request(transport, f"{base}/{delivery_id}", token)
        if not isinstance(detail, dict) or detail.get("guid") != delivery_guid:
            raise ValueError("GitHub delivery detail GUID does not match")
        headers = (detail.get("request", {}).get("headers")
                   if isinstance(detail.get("request"), dict) else None)
        if not isinstance(headers, dict):
            raise TypeError("GitHub delivery headers are missing")
        normalized_headers = {str(key).lower(): value for key, value in headers.items()}
        if (normalized_headers.get("x-github-delivery") != delivery_guid
                or normalized_headers.get("x-github-event") != "push"
                or str(normalized_headers.get("x-github-hook-id")) != str(trust.hook_id)
                or detail.get("event") != "push"):
            raise ValueError("GitHub delivery is not the configured push webhook event")
        fetched = detail.get("request", {}).get("payload")
        actual = _push_claims(fetched)
        if actual[0] != trust.repository_id:
            raise ValueError("GitHub delivery repository ID does not match verified configuration")
        if (fetched.get("repository", {}).get("full_name") != trust.repository
                or actual != expected):
            raise ValueError("GitHub delivery payload does not match relayed push claims")
        fetched_payloads.append(fetched)
    return fetched_payloads[0]
