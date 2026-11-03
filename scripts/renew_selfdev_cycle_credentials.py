#!/usr/bin/env python3
"""Unattended renewal of the Self Development cycle role pair, run as aao-pm.

One invocation is one tick of the persisted state machine described in
docs/procedures/SELFDEV_CYCLE_CREDENTIAL_LIFECYCLE.md section 5:

    ACTIVE -> ISSUING -> INSTALLED_PENDING -> VERIFIED -> REVOKING_OLD -> ACTIVE
    FAILED_ISSUE / FAILED_INSTALL / FAILED_EXPIRED for recovery, and
    BREAKER_OPEN after repeated or definitive issuance failures (operator reset).

Only the PM token is used. Role tokens exist only in process memory between the
issuing POST and the root wrapper's ``replace`` (stdin). They are never written
to the state file, argv, the environment, stdout or stderr. The state file holds
cycle IDs and timestamps only. Any unreadable or malformed state fails closed.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_self_dev_agent import urlopen
from provision_w2_publishers import ProvisionError, local_api_url
from request_selfdev_cycle_roles import ROLE_GRANTS, ROLES, ROOT_WRAPPER, read_pm_token

CYCLE_TTL = timedelta(hours=2)
# Renew at 50 % of the 2 h TTL: never issue N+1 while N has more than 60 min left,
# so N (hard bound: its own expiry) overlaps N+1 by at most 60 minutes.
RENEW_MARGIN = CYCLE_TTL / 2
# Drain wait cap: 30 min max lease + 5 min (#356 TimeoutStopSec margin).
DRAIN_CAP = timedelta(minutes=35)
CLOCK_SKEW = timedelta(minutes=1)
# Wait after the 1st..4th consecutive failed issuance; the 5th opens the breaker,
# so a persistent failure issues at most BREAKER_THRESHOLD pairs until an operator
# runs --reset-breaker.
BACKOFF = tuple(timedelta(minutes=m) for m in (5, 10, 20, 60))
BREAKER_THRESHOLD = 5
# POST rejections that cannot succeed on retry; nothing was issued server-side.
DEFINITIVE_REJECTIONS = {400, 401, 403, 404, 422}
# Issuance caps (PR #388); recognised only by detail.code, so an API without them
# behaves as before.
CONCURRENCY_CAP_CODE = "SELFDEV_CYCLE_CONCURRENCY_CAP"
DAILY_CAP_CODE = "SELFDEV_CYCLE_ISSUANCE_DAILY_CAP"
DAILY_CAP_BACKOFF = timedelta(hours=1)
# On a daily-cap 429, retry early enough that a successor can still be issued,
# installed, verified and N drained before N expires.
DAILY_CAP_SAFETY_MARGIN = DRAIN_CAP + CLOCK_SKEW
DAILY_CAP_MIN_WAIT = BACKOFF[0]
# The systemd timer may not observe next_attempt_at until its next activation.
# Bound that delay using the configured cadence and AccuracySec.
DAILY_CAP_TIMER_LATENCY = timedelta(minutes=5, seconds=30)
PHASES = {
    "ACTIVE", "ISSUING", "INSTALLED_PENDING", "VERIFIED", "REVOKING_OLD",
    "FAILED_ISSUE", "FAILED_INSTALL", "FAILED_EXPIRED", "BREAKER_OPEN",
}
NO_NEXT_PHASES = {"ACTIVE", "FAILED_EXPIRED", "BREAKER_OPEN"}
STATE_KEYS = {
    "phase", "project_id", "current_cycle_id", "current_expires_at",
    "next_cycle_id", "next_expires_at", "next_issued_at", "updated_at",
    "consecutive_failures", "next_attempt_at",
}
CYCLE_RE = re.compile(r"[0-9a-f]{32}")
BUSY_STATUSES = {"RUNNING", "UNCERTAIN"}
EXIT_LOCKED = 75
REPLACE_COMMITTED = 3


class RenewError(RuntimeError):
    """Fail-closed condition; message never contains credential material."""


class DailyCapMarginLost(RenewError):
    """A further daily-cap retry cannot preserve the old cycle's drain margin."""


class ApiUnavailable(RenewError):
    """Transport failure or timeout: the outcome of the request is unknown."""


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_time(value) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("naive timestamp")
    return parsed.astimezone(UTC)


# --------------------------------------------------------------------------- API


class ApiClient:
    """Loopback AAO API client returning ``(status, body)``; no proxy, no redirects."""

    def __init__(self, base_url: str, project_id: str, pm_token: str, timeout: float = 10):
        self.base = local_api_url(base_url)
        self.project_path = quote(project_id, safe="")
        self._pm = pm_token
        self.timeout = timeout

    def _request(self, path: str, *, method: str = "GET", headers: dict, body=None):
        headers = {"Accept": "application/json", **headers}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = Request(f"{self.base}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read() or b"null")
        except HTTPError as exc:
            try:
                try:
                    parsed = json.loads(exc.read() or b"null")
                except (ValueError, OSError):
                    parsed = None
                return exc.code, parsed
            finally:
                exc.close()
        except (URLError, TimeoutError, OSError, ValueError):
            raise ApiUnavailable("AAO API unavailable or returned invalid data") from None

    def issue(self, cycle_id: str):
        return self._request(
            f"/v1/projects/{self.project_path}/selfdev-cycle-roles", method="POST",
            headers={"X-Agent-Token": self._pm},
            body={"cycle_id": cycle_id, "lifetime_seconds": int(CYCLE_TTL.total_seconds())},
        )

    def revoke(self, cycle_id: str):
        return self._request(
            f"/v1/projects/{self.project_path}/selfdev-cycle-roles/{cycle_id}",
            method="DELETE", headers={"X-Agent-Token": self._pm},
        )

    def board(self):
        return self._request(
            f"/v1/projects/{self.project_path}/board", headers={"X-Agent-Token": self._pm},
        )

    def agent_me(self, token: str):
        return self._request("/v1/principals/me", headers={"X-Agent-Token": token})

    def auditor_grants(self, token: str):
        return self._request("/v1/auditors/me/grants", headers={"X-Auditor-Token": token})


# --------------------------------------------------------------------- installer


class WrapperInstaller:
    """Calls only the root-installed allowlist wrapper; the token goes on stdin."""

    def run(self, account: str, token_kind: str, operation: str, token: str) -> int:
        if (account, token_kind) not in {(a, k) for a, k, _ in ROLES} or operation not in {
            "replace", "verify",
        }:
            raise RenewError("unsupported role-token operation")
        command = [
            "/usr/bin/sudo", "-n", ROOT_WRAPPER,
            "--account", account, "--token", token_kind, "--operation", operation,
        ]
        try:
            result = subprocess.run(
                command, input=token + "\n", text=True, capture_output=True,
                check=False, timeout=30, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1
        return result.returncode


# ------------------------------------------------------------------------ state


def _validate_state(data, project_id: str) -> dict:
    if not isinstance(data, dict) or set(data) != STATE_KEYS:
        raise RenewError("state file has an unexpected shape")
    if data["phase"] not in PHASES or data["project_id"] != project_id:
        raise RenewError("state file phase or project is invalid")
    for key in ("current_cycle_id", "next_cycle_id"):
        if data[key] is not None and not (
            isinstance(data[key], str) and CYCLE_RE.fullmatch(data[key])
        ):
            raise RenewError("state file cycle id is invalid")
    failures = data["consecutive_failures"]
    if type(failures) is not int or not 0 <= failures <= BREAKER_THRESHOLD:
        raise RenewError("state file failure counter is invalid")
    for key in ("current_expires_at", "next_expires_at", "next_issued_at", "updated_at",
                "next_attempt_at"):
        if data[key] is not None:
            try:
                _parse_time(data[key])
            except (TypeError, ValueError):
                raise RenewError("state file timestamp is invalid") from None
    if (data["current_cycle_id"] is None) != (data["current_expires_at"] is None):
        raise RenewError("state file current cycle is incomplete")
    if data["current_cycle_id"] is not None and data["current_cycle_id"] == data["next_cycle_id"]:
        raise RenewError("state file current and next cycle are identical")
    has_next = data["next_cycle_id"] is not None
    if has_next != (data["next_issued_at"] is not None):
        raise RenewError("state file next cycle is incomplete")
    if data["phase"] in NO_NEXT_PHASES - {"FAILED_EXPIRED"} and has_next:
        raise RenewError("state file phase with an open next cycle")
    if data["phase"] in {"VERIFIED", "REVOKING_OLD"} and data["next_expires_at"] is None:
        raise RenewError("state file verified phase without next expiry")
    if data["phase"] not in NO_NEXT_PHASES and not has_next:
        raise RenewError("state file phase requires a next cycle")
    return data


class StateStore:
    """Secret-free JSON state; private regular file, atomic temp+fsync+rename writes."""

    def __init__(self, path: Path, project_id: str):
        self.path = path
        self.project_id = project_id

    def load(self) -> dict | None:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError:
            raise RenewError("state file is unreadable or a symlink") from None
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise RenewError("state file must be a private regular file")
            raw = os.read(fd, 65537)
        finally:
            os.close(fd)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            raise RenewError("state file is corrupt") from None
        return _validate_state(data, self.project_id)

    def save(self, state: dict) -> None:
        _validate_state(state, self.project_id)
        payload = json.dumps(state, sort_keys=True).encode()
        directory = self.path.parent
        temp = directory / f".{self.path.name}.{uuid4().hex}.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            try:
                os.fchmod(fd, 0o600)
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)
            raise
        dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


@contextlib.contextmanager
def exclusive_lock(path: Path):
    """Non-blocking exclusive flock; yields False if another run holds it."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


# ----------------------------------------------------------------------- runner


def daily_cap_retry_at(now: datetime, current_expires: datetime | None) -> datetime | None:
    """Return a safe retry time, None if no live N needs a drain margin.

    The next timer activation can be delayed by DAILY_CAP_TIMER_LATENCY. If even
    the minimum backoff plus that delay would cross the drain deadline, fail
    closed rather than scheduling an unsafe retry.
    """
    if current_expires is None or now >= current_expires:
        return None
    latest_safe_wait = (
        current_expires - now - DAILY_CAP_SAFETY_MARGIN - DAILY_CAP_TIMER_LATENCY
    )
    if latest_safe_wait < DAILY_CAP_MIN_WAIT:
        raise DailyCapMarginLost("daily cap retry would cross cycle drain margin")
    return now + min(DAILY_CAP_BACKOFF, latest_safe_wait)


def _detail_code(body) -> str | None:
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("code") if isinstance(detail, dict) else None


class Runner:
    def __init__(self, *, project_id: str, api, installer, store: StateStore, clock, log):
        self.project_id = project_id
        self.api = api
        self.installer = installer
        self.store = store
        self.clock = clock
        self.log = log

    # -- helpers ----------------------------------------------------------
    def _save(self, state: dict, phase: str, **changes) -> dict:
        state = {**state, **changes, "phase": phase, "updated_at": _iso(self.clock())}
        self.store.save(state)
        return state

    def _event(self, name: str, **fields) -> None:
        self.log({"event": f"selfdev_cycle.{name}", **fields})

    def _revoke(self, cycle_id: str) -> str:
        """Return 'revoked', 'already', 'never_issued', 'mismatch' or 'error'."""
        try:
            status, body = self.api.revoke(cycle_id)
        except ApiUnavailable:
            return "error"
        if status == 200 and isinstance(body, dict) and body.get("cycle_id") == cycle_id \
                and body.get("revoked") is True:
            return "already" if body.get("already_revoked") else "revoked"
        if status == 404 and _detail_code(body) == "CYCLE_NOT_FOUND":
            return "never_issued"
        if status == 409:
            return "mismatch"
        return "error"

    def _check_issue_response(self, cycle_id: str, status, body, now: datetime):
        if status != 201 or not isinstance(body, dict) or body.get("cycle_id") != cycle_id \
                or body.get("project_id") != self.project_id:
            raise RenewError(f"issue rejected (HTTP {status})")
        try:
            expires = _parse_time(body.get("expires_at"))
        except (TypeError, ValueError):
            raise RenewError("issue returned an invalid expiry") from None
        if not now < expires <= now + CYCLE_TTL + CLOCK_SKEW:
            raise RenewError("issue returned an out-of-range expiry")
        roles = body.get("roles")
        if not isinstance(roles, list) or len(roles) != len(ROLES):
            raise RenewError("issue returned an invalid role list")
        tokens = []
        expected_ids = (f"aao-selfdev-impl-{cycle_id}", f"aao-selfdev-review-{cycle_id}")
        for record, (_acct, _kind_name, kind), grants, expected in zip(
            roles, ROLES, ROLE_GRANTS, expected_ids, strict=True
        ):
            if (
                not isinstance(record, dict)
                or record.get("principal_id") != expected
                or record.get("kind") != kind
                or not isinstance(record.get("grants"), list)
                or len(record["grants"]) != len(grants)
                or set(record["grants"]) != grants
                or not isinstance(record.get("token"), str)
                or not record["token"]
                or any(c in record["token"] for c in "\r\n")
            ):
                raise RenewError("issue returned an invalid role")
            tokens.append(record["token"])
        return expires, tokens, expected_ids

    def _verify_identities(self, tokens, expected_ids) -> None:
        """Exact principal id, kind and grants of both new tokens, against the API."""
        impl_token, review_token = tokens
        impl_id, review_id = expected_ids
        try:
            status, me = self.api.agent_me(impl_token)
            if status != 200 or me != {"principal_id": impl_id, "kind": "AGENT", "enabled": True}:
                raise RenewError("implementer identity mismatch")
            status, grants = self.api.auditor_grants(review_token)
        except ApiUnavailable:
            raise RenewError("identity verification unavailable") from None
        if (
            status != 200
            or not isinstance(grants, list)
            or len(grants) != len(ROLE_GRANTS[1])
            or not all(
                isinstance(g, dict)
                and g.get("principal_id") == review_id
                and g.get("project_id") == self.project_id
                and g.get("active") is True
                for g in grants
            )
            or {g.get("capability") for g in grants} != ROLE_GRANTS[1]
        ):
            raise RenewError("reviewer identity or grants mismatch")

    def _old_drained(self, old_cycle: str) -> bool:
        try:
            status, board = self.api.board()
        except ApiUnavailable:
            return False
        if status != 200 or not isinstance(board, list):
            return False
        worker = f"aao-selfdev-impl-{old_cycle}"
        for item in board:
            executions = item.get("executions") if isinstance(item, dict) else None
            if not isinstance(executions, list):
                return False
            for execution in executions:
                if not isinstance(execution, dict):
                    return False
                if execution.get("worker_id") != worker:
                    continue
                status_value = execution.get("status")
                if status_value in BUSY_STATUSES or (
                    status_value == "QUEUED" and (execution.get("attempts") or 0) > 0
                ):
                    return False
        return True

    def _fail(self, state: dict, phase: str, reason: str) -> dict:
        self._event("failed", phase=state["phase"], cycle=state["next_cycle_id"], reason=reason)
        failures = min(state["consecutive_failures"] + 1, BREAKER_THRESHOLD)
        return self._save(state, phase, consecutive_failures=failures)

    # -- phases -----------------------------------------------------------
    def _issue(self, state: dict) -> dict:
        """ISSUING: persist the new ID first, POST, verify via API, then install."""
        now = self.clock()
        cycle_id = uuid4().hex
        state = self._save(state, "ISSUING", next_cycle_id=cycle_id,
                           next_issued_at=_iso(now), next_expires_at=None)
        self._event("renewal_started", current=state["current_cycle_id"], next=cycle_id,
                    expires_at=state["current_expires_at"])
        try:
            status, body = self.api.issue(cycle_id)
        except ApiUnavailable:
            return self._fail(state, "FAILED_ISSUE", "issue unavailable")
        code = _detail_code(body)
        cleared = {"next_cycle_id": None, "next_expires_at": None, "next_issued_at": None}
        if status in DEFINITIVE_REJECTIONS or (status == 409 and code == CONCURRENCY_CAP_CODE):
            # Rejected before issuance: nothing exists server-side to revoke.
            # Definitive codes (auth, grant, validation) cannot succeed on retry.
            # The concurrency cap means an untracked live cycle exists (manual, a
            # pre-reboot state, a FAILED_ISSUE closed on a 409 revoke mismatch,
            # ...). The API cannot list cycles, so it cannot be identified
            # safely: stop and alert instead of guessing.
            reason = f"HTTP {status}" + (f" {code}" if code else "")
            self._event("failed", phase="ISSUING", cycle=cycle_id,
                        reason=f"issue rejected without retry ({reason})")
            self._event("breaker_open", reason=reason)
            return self._save(state, "BREAKER_OPEN", consecutive_failures=BREAKER_THRESHOLD,
                              next_attempt_at=None, **cleared)
        if status == 429 and code == DAILY_CAP_CODE:
            # Nothing issued; not an issuance failure, never opens the breaker and
            # nothing is revoked. The API does not expose when its rolling 24 h
            # window frees a slot, so retry before N runs out (daily_cap_retry_at).
            # The tick then exits 1, which is the alert.
            current = state["current_expires_at"]
            current = _parse_time(current) if current else None
            try:
                retry = daily_cap_retry_at(now, current)
            except DailyCapMarginLost:
                reason = "daily cap retry refused: cycle drain margin cannot be preserved"
                self._event("failed", phase="ISSUING", cycle=cycle_id, reason=reason)
                self._event("breaker_open", reason=reason)
                return self._save(state, "BREAKER_OPEN",
                                  consecutive_failures=BREAKER_THRESHOLD,
                                  next_attempt_at=None, **cleared)
            until = _iso(retry) if retry else None
            self._event("failed", phase="ISSUING", cycle=cycle_id,
                        reason=f"issue daily cap reached; retry after {until or 'next tick'}")
            expired = current is not None and now >= current
            return self._save(state, "FAILED_EXPIRED" if expired else "ACTIVE",
                              next_attempt_at=until, **cleared)
        # Issuance itself may be slow even when the retry was scheduled with
        # enough margin. Do not replace either role file unless N can still
        # remain valid for the full bounded drain interval after this response.
        # Track N+1 as FAILED_INSTALL (conservative: it exists, but no token was
        # installed) so a failed/ambiguous revoke cannot make us forget it.
        current_exp = state["current_expires_at"]
        current_exp = _parse_time(current_exp) if current_exp else None
        if (
            current_exp is not None
            and now < current_exp
            and current_exp - self.clock() < DAILY_CAP_SAFETY_MARGIN
        ):
            reason = "successor issued too late to preserve old-cycle drain margin"
            self._event("failed", phase="ISSUING", cycle=cycle_id, reason=reason)
            self._event("breaker_open", reason=reason)
            return self._save(
                state, "FAILED_INSTALL", consecutive_failures=BREAKER_THRESHOLD,
                next_attempt_at=None,
            )
        try:
            expires, tokens, ids = self._check_issue_response(cycle_id, status, body, now)
            # Identity is verified with the in-memory tokens BEFORE any file is
            # touched, so a mismatch leaves cycle N's files and credentials intact.
            self._verify_identities(tokens, ids)
        except RenewError as exc:
            return self._fail(state, "FAILED_ISSUE", str(exc))
        # From here on a role file may hold N+1 (INSTALLED_PENDING = "may hold").
        state = self._save(state, "INSTALLED_PENDING", next_expires_at=_iso(expires))
        # The reviewer file is replaced AND verified before the implementer file
        # (live worker consumer) is touched, so every reviewer-side failure leaves
        # the implementer file holding cycle N. The only remaining case where the
        # implementer file ends up with a revoked N+1 token is a failure of the
        # implementer's own step after its rename: replace rc 3, a failed
        # implementer verify, a wrapper timeout (WrapperInstaller returns 1 but
        # the rename may already have happened), or a crash after the
        # implementer replace. The two
        # files live in two accounts' runtime dirs, so no single rename can
        # switch both.
        written = False
        for (account, kind_name, _kind), token in reversed(list(zip(ROLES, tokens, strict=True))):
            rc = self.installer.run(account, kind_name, "replace", token)
            # rc 3: rename committed but post-write check failed; verify decides.
            # Any other failure happened before rename.
            if rc not in {0, REPLACE_COMMITTED}:
                return self._fail(state, "FAILED_INSTALL" if written else "FAILED_ISSUE",
                                  f"replace failed for {account} (rc {rc})")
            written = True
            if self.installer.run(account, kind_name, "verify", token) != 0:
                return self._fail(state, "FAILED_INSTALL", f"file verify failed for {account}")
        self._event("installed", next=cycle_id)
        self._event("verified", next=cycle_id, impl=ids[0], reviewer=ids[1])
        return self._save(state, "VERIFIED", consecutive_failures=0, next_attempt_at=None)

    def _close_failed_next(self, state: dict) -> tuple[dict, bool]:
        cycle_id = state["next_cycle_id"]
        outcome = self._revoke(cycle_id)
        now = self.clock()
        expired = now >= _parse_time(state["next_issued_at"]) + CYCLE_TTL + CLOCK_SKEW
        # FAILED_ISSUE: no N+1 token reached disk, so a 409 (role set altered) can be
        # closed with an alert. FAILED_INSTALL: N+1 tokens may be on disk; only a
        # confirmed revoke or N+1's own expiry closes it.
        closable = outcome in {"revoked", "already", "never_issued"} or expired or (
            outcome == "mismatch" and state["phase"] == "FAILED_ISSUE"
        )
        if not closable:
            self._event("failed", phase=state["phase"], cycle=cycle_id,
                        reason=f"next cycle revoke {outcome}; kept open")
            return state, False
        if outcome in {"mismatch", "error"}:
            self._event("failed", phase=state["phase"], cycle=cycle_id,
                        reason=f"next cycle revoke {outcome}; closed (tokens lost, expires)")
        else:
            self._event("next_revoked", next=cycle_id, outcome=outcome)
        failures = state["consecutive_failures"]
        cleared = {"next_cycle_id": None, "next_expires_at": None, "next_issued_at": None}
        if failures >= BREAKER_THRESHOLD:
            self._event("breaker_open", reason=f"{failures} consecutive failures")
            return self._save(state, "BREAKER_OPEN", next_attempt_at=None, **cleared), True
        wait = BACKOFF[min(max(failures, 1), len(BACKOFF)) - 1]
        return self._save(state, "ACTIVE", next_attempt_at=_iso(now + wait), **cleared), True

    def tick(self, *, bootstrap: bool = False, reset_breaker: bool = False) -> int:
        state = self.store.load()
        if state is None:
            if not bootstrap:
                raise RenewError("no renewal state; run once with --bootstrap")
            state = {
                "phase": "ACTIVE", "project_id": self.project_id,
                "current_cycle_id": None, "current_expires_at": None,
                "next_cycle_id": None, "next_expires_at": None, "next_issued_at": None,
                "updated_at": _iso(self.clock()), "consecutive_failures": 0,
                "next_attempt_at": None,
            }
        elif bootstrap:
            raise RenewError("renewal state already exists; refusing --bootstrap")
        if reset_breaker:
            if state["phase"] != "BREAKER_OPEN":
                raise RenewError("breaker is not open; refusing --reset-breaker")
            self._event("breaker_reset", failures=state["consecutive_failures"])
            state = self._save(state, "ACTIVE", consecutive_failures=0, next_attempt_at=None)
        # Crash recovery: tokens of an in-flight issuance are lost with the process.
        if state["phase"] == "ISSUING":
            state = self._fail(state, "FAILED_ISSUE", "interrupted; tokens lost")
        elif state["phase"] == "INSTALLED_PENDING":
            state = self._fail(state, "FAILED_INSTALL", "interrupted; files may hold next")
        issued_this_tick = False
        for _ in range(8):
            phase = state["phase"]
            now = self.clock()
            current_exp = (
                _parse_time(state["current_expires_at"]) if state["current_cycle_id"] else None
            )
            if phase == "BREAKER_OPEN":
                self._event("breaker_open", reason="operator --reset-breaker required",
                            failures=state["consecutive_failures"])
                return 1
            if phase in {"FAILED_ISSUE", "FAILED_INSTALL"}:
                state, closed = self._close_failed_next(state)
                if not closed:
                    return 1
            elif phase in {"ACTIVE", "FAILED_EXPIRED"}:
                if current_exp is not None and now < current_exp - RENEW_MARGIN:
                    return 0
                if issued_this_tick:
                    return 1  # one issuance attempt per tick
                if state["next_attempt_at"] and now < _parse_time(state["next_attempt_at"]):
                    self._event("backoff_wait", until=state["next_attempt_at"],
                                failures=state["consecutive_failures"])
                    return 1  # renewal is due and failing: keep the unit visibly failed
                # A daily-cap retry is scheduled against the expected timer
                # cadence, but the process may be suspended or the timer may
                # run late. Re-check the live N margin immediately before the
                # POST; never rely solely on the scheduled timestamp.
                if (
                    state["next_attempt_at"]
                    and state["consecutive_failures"] == 0
                    and current_exp is not None
                    and now < current_exp
                    and current_exp - now < DAILY_CAP_SAFETY_MARGIN
                ):
                    reason = "daily cap retry refused: delayed tick exhausted cycle drain margin"
                    self._event("failed", phase=phase, cycle=state["current_cycle_id"],
                                reason=reason)
                    self._event("breaker_open", reason=reason)
                    self._save(state, "BREAKER_OPEN",
                               consecutive_failures=BREAKER_THRESHOLD,
                               next_attempt_at=None)
                    return 1
                if current_exp is not None and now >= current_exp and phase != "FAILED_EXPIRED":
                    self._event("expired_without_successor", old=state["current_cycle_id"])
                    state = self._save(state, "FAILED_EXPIRED")
                issued_this_tick = True
                state = self._issue(state)
            elif phase == "VERIFIED":
                old = state["current_cycle_id"]
                if old is not None:
                    issued = _parse_time(state["next_issued_at"])
                    deadline = min(current_exp, issued + DRAIN_CAP)
                    drained = self._old_drained(old)
                    if now < deadline and not drained:
                        self._event("drain_waited", old=old,
                                    seconds=int((now - issued).total_seconds()))
                        return 0
                    # A running/uncertain execution must not be killed by
                    # revoking its credential merely because the 35m lease
                    # bound elapsed. Wait for natural N expiry (at most the
                    # remaining clock-skew margin); then promote N+1 without
                    # an explicit revoke. The authorization expires on its own.
                    if not drained and current_exp is not None and now < current_exp:
                        self._event("drain_cap_busy_wait", old=old,
                                    seconds=int((now - issued).total_seconds()))
                        return 0
                    if not drained and current_exp is not None and now >= current_exp:
                        self._event("old_expired_while_busy", old=old)
                        state = self._save(
                            state, "ACTIVE", current_cycle_id=state["next_cycle_id"],
                            current_expires_at=state["next_expires_at"], next_cycle_id=None,
                            next_expires_at=None, next_issued_at=None,
                        )
                        continue
                state = self._save(state, "REVOKING_OLD")
            elif phase == "REVOKING_OLD":
                old = state["current_cycle_id"]
                if old is not None:
                    outcome = self._revoke(old)
                    if outcome in {"revoked", "already", "never_issued"}:
                        self._event("old_revoked", old=old, outcome=outcome)
                    elif now >= current_exp:
                        self._event("failed", phase=phase, cycle=old,
                                    reason=f"old revoke {outcome}; old cycle already expired")
                    else:
                        self._event("failed", phase=phase, cycle=old, reason=f"old revoke {outcome}")
                        return 1
                state = self._save(
                    state, "ACTIVE", current_cycle_id=state["next_cycle_id"],
                    current_expires_at=state["next_expires_at"], next_cycle_id=None,
                    next_expires_at=None, next_issued_at=None,
                )
        return 1


def _log(record: dict) -> None:
    print(json.dumps(record, sort_keys=True), flush=True)


def runtime_dir() -> Path:
    return Path(f"/run/user/{os.getuid()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--bootstrap", action="store_true",
                        help="create the initial state and issue the first cycle")
    parser.add_argument("--reset-breaker", action="store_true",
                        help="operator reset of an open circuit breaker, then run one tick")
    args = parser.parse_args(argv)
    # The current renewal API client has a development bearer contract only.
    # Production requires a certificate bound to each cycle role; reusing the
    # PM certificate for implementer/reviewer checks would impersonate those
    # principals, so fail closed before reading tokens or invoking sudo.
    if os.environ.get("AAO_ENV", "").strip().lower() == "production":
        _log({
            "event": "selfdev_cycle.blocked",
            "reason": "production workload identity contract unavailable",
        })
        return 1
    runtime = runtime_dir()
    lock_path = runtime / "aao-selfdev-cycle.lock"
    state_path = runtime / f"aao-selfdev-cycle-{quote(args.project_id, safe='')}.json"
    try:
        info = runtime.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
                or stat.S_IMODE(info.st_mode) & 0o077:
            raise RenewError("runtime directory must be private to this account")
        with exclusive_lock(lock_path) as held:
            if not held:
                _log({"event": "selfdev_cycle.lock_busy"})
                return EXIT_LOCKED
            api = ApiClient(args.api, args.project_id, read_pm_token())
            runner = Runner(project_id=args.project_id, api=api, installer=WrapperInstaller(),
                            store=StateStore(state_path, args.project_id),
                            clock=lambda: datetime.now(UTC), log=_log)
            return runner.tick(bootstrap=args.bootstrap, reset_breaker=args.reset_breaker)
    except (RenewError, ProvisionError) as exc:
        _log({"event": "selfdev_cycle.failed", "phase": "startup", "reason": str(exc)})
        return 1
    except OSError:
        _log({"event": "selfdev_cycle.failed", "phase": "startup", "reason": "filesystem error"})
        return 1
    except Exception as exc:  # noqa: BLE001 - never let a traceback reach the journal
        _log({"event": "selfdev_cycle.failed", "phase": "unexpected",
              "reason": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
