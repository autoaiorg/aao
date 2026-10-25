"""Minimal, memory-only GitHub App authentication for the trial harness."""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import pwd
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API_VERSION = "2022-11-28"
ROLE_NAMES = {
    "aao-integrator", "aao-auditor", "aao-auditor-alt", "aao-supervisor",
    "aao-notifier", "aao-pm", "aao-impl-codex", "aao-impl-claude", "aao-impl-agy",
    "aao-probe-noworkflows",
}
# App name -> Linux account that holds its key, where they differ (the Antigravity App is aao-impl-agy).
LINUX_USER = {"aao-impl-agy": "aao-impl-ag"}


def linux_user(app: str) -> str:
    return LINUX_USER.get(app, app)


class GitHubAuthError(RuntimeError):
    """Authentication or API failure, with credentials excluded from messages."""


@dataclass(frozen=True)
class APIResponse:
    status: int
    body: Any
    headers: dict[str, str]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward bearer credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _paths(app: str) -> tuple[Path, Path]:
    if app not in ROLE_NAMES:
        raise GitHubAuthError("unknown app role")
    conf = Path.home() / ".config" / "aao"
    return conf / f"{app}.pem", conf / f"{app}.json"


def load_app(app: str) -> tuple[int, Path]:
    key_path, metadata_path = _paths(app)
    uid = os.getuid()
    try:
        owner = pwd.getpwnam(linux_user(app)).pw_uid
    except KeyError as exc:
        raise GitHubAuthError(f"role account {app} does not exist") from exc
    if owner != uid:
        raise GitHubAuthError(f"uid {uid} does not match role {app} uid {owner}")
    try:
        key_stat = key_path.stat()
        if key_stat.st_uid != uid or key_stat.st_mode & 0o777 != 0o600:
            raise GitHubAuthError("private key must be owned by current uid with mode 0600")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        app_id = int(metadata["id"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GitHubAuthError("missing or invalid GitHub App key/metadata") from exc
    if app_id < 1:
        raise GitHubAuthError("invalid GitHub App id")
    return app_id, key_path


def create_jwt(app_id: int, key_path: Path, *, now: int | None = None) -> str:
    issued = int(time.time() if now is None else now)
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"iat": issued - 60, "exp": issued + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    try:
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
            input=signing_input, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitHubAuthError("could not sign GitHub App JWT with openssl") from exc
    return f"{signing_input.decode()}.{_b64url(result.stdout)}"


class GitHubAppClient:
    def __init__(self, app: str, *, api_base: str | None = None, timeout: float = 15.0):
        self.app_id, key_path = load_app(app)
        self.api_base = (api_base or os.environ.get("AAO_GITHUB_API", "https://api.github.com")).rstrip("/")
        parsed_base = urllib.parse.urlsplit(self.api_base)
        if self.api_base != "https://api.github.com" and os.environ.get("AAO_GITHUB_API_ALLOW_TEST") != "1":
            raise GitHubAuthError("custom GitHub API base requires AAO_GITHUB_API_ALLOW_TEST=1")
        if parsed_base.scheme != "https":
            try:
                loopback = parsed_base.scheme == "http" and ipaddress.ip_address(parsed_base.hostname or "").is_loopback
            except ValueError:
                loopback = parsed_base.scheme == "http" and parsed_base.hostname == "localhost"
            if not loopback:
                raise GitHubAuthError("GitHub API base must use HTTPS (HTTP is allowed only for loopback tests)")
        self.timeout = timeout
        self._key_path = key_path
        self._installation_token: str | None = None
        self._installation_id: int | None = None

    def app_request(self, method: str, path: str, *, body: dict | None = None) -> APIResponse:
        """Make a request authenticated as the App itself, using a short-lived JWT."""
        return self._request(method, path, token=create_jwt(self.app_id, self._key_path), body=body)

    def _request(self, method: str, path: str, *, token: str, body: dict | None = None) -> APIResponse:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.api_base + path, data=data, method=method,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": API_VERSION,
                     **({"Content-Type": "application/json"} if data is not None else {})},
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(req, timeout=self.timeout) as res:
                raw, status, headers = res.read(), res.status, dict(res.headers.items())
        except urllib.error.HTTPError as exc:
            raw, status, headers = exc.read(), exc.code, dict(exc.headers.items())
        except (OSError, urllib.error.URLError) as exc:
            raise GitHubAuthError(f"GitHub API transport failure: {type(exc).__name__}") from exc
        try:
            parsed: Any = json.loads(raw) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = raw.decode("utf-8", errors="replace")[:2000]
        return APIResponse(status, parsed, headers)

    def installation_token(self, owner: str, repo: str, *, repository_names: bool = True) -> str:
        jwt = create_jwt(self.app_id, self._key_path)
        repo_path = "/repos/" + urllib.parse.quote(owner, safe="") + "/" + urllib.parse.quote(repo, safe="") + "/installation"
        installation = self._request("GET", repo_path, token=jwt)
        if installation.status != 200 or not isinstance(installation.body, dict):
            raise GitHubAuthError(f"installation lookup failed with HTTP {installation.status}")
        installation_id = installation.body.get("id")
        if not isinstance(installation_id, int):
            raise GitHubAuthError("installation lookup returned no installation id")
        # The REST API accepts `repositories`, not `repository_names`. Keep the
        # equivalence/audit path deliberately installation-wide by omitting it.
        body = {"repositories": [repo]} if repository_names else {}
        response = self._request("POST", f"/app/installations/{installation_id}/access_tokens", token=jwt,
                                 body=body)
        if response.status != 201 or not isinstance(response.body, dict) or not response.body.get("token"):
            raise GitHubAuthError(f"installation token request failed with HTTP {response.status}")
        if repository_names:
            granted = response.body.get("repositories")
            names = []
            if isinstance(granted, list):
                names = [item.get("full_name") or item.get("name")
                         for item in granted if isinstance(item, dict)]
            if len(names) != 1 or names[0] not in {repo, f"{owner}/{repo}"}:
                raise GitHubAuthError("installation token repository scope does not match requested repository")
        self._installation_token = str(response.body["token"])
        self._installation_id = installation_id
        return self._installation_token

    def request(self, method: str, path: str, *, body: dict | None = None) -> APIResponse:
        if not self._installation_token:
            raise GitHubAuthError("installation token has not been obtained")
        return self._request(method, path, token=self._installation_token, body=body)

    def revoke(self) -> APIResponse | None:
        if not self._installation_token:
            return None
        response = self._request("DELETE", "/installation/token", token=self._installation_token)
        self._installation_token = None
        self._installation_id = None
        return response

    def close(self) -> None:
        self.revoke()
