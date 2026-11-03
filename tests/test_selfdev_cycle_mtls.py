import uuid
from datetime import UTC, datetime, timedelta

import pytest

from aao.selfdev_cycle_mtls import (
    CycleMtlError,
    CycleSigningIntent,
    SignedCycleCertificate,
    reconcile_cycle_certificate,
)


def intent() -> CycleSigningIntent:
    now = datetime.now(UTC)
    cycle = "a" * 32
    return CycleSigningIntent(
        intent_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        cycle_id=cycle,
        principal_id=f"aao-selfdev-impl-{cycle}",
        kind="AGENT",
        not_before=now,
        not_after=now + timedelta(hours=2),
    )


class Repo:
    def __init__(self, issue):
        self.issue = issue
        self.completed = None
        self.bindings = []

    def get_pending_intent(self, intent_id):
        return self.issue if self.issue.intent_id == intent_id else None

    def get_completed_fingerprint(self, intent_id):
        return self.completed

    def complete_binding(self, issued_intent, fingerprint):
        self.bindings.append((issued_intent, fingerprint))
        self.completed = fingerprint


class Signer:
    def __init__(self, chain=b"test-only-certificate-chain"):
        self.calls = []
        self.chain = chain

    def issue(self, signing_intent, csr_pem):
        self.calls.append((signing_intent, csr_pem))
        return SignedCycleCertificate(self.chain)


class Verifier:
    def __init__(self, fingerprint="b" * 64, error=None):
        self.fingerprint = fingerprint
        self.error = error
        self.calls = []

    def verify(self, signing_intent, csr_pem, chain):
        self.calls.append((signing_intent, csr_pem, chain))
        if self.error:
            raise self.error
        return self.fingerprint


CSR = b"-----BEGIN CERTIFICATE REQUEST-----\nopaque-test-only\n"


def test_issue_verifies_before_binding_and_replay_is_idempotent():
    repo, signer, verifier = Repo(intent()), Signer(), Verifier()
    result = reconcile_cycle_certificate(
        repo.issue.intent_id,
        CSR,
        repository=repo,
        signer=signer,
        verifier=verifier,
    )
    assert result == "b" * 64
    assert repo.bindings == [(repo.issue, "b" * 64)]
    assert len(signer.calls) == len(verifier.calls) == 1

    assert (
        reconcile_cycle_certificate(
            repo.issue.intent_id,
            CSR,
            repository=repo,
            signer=signer,
            verifier=verifier,
        )
        == "b" * 64
    )
    assert len(signer.calls) == len(verifier.calls) == 1


def test_verification_failure_does_not_bind_or_enable():
    repo, signer = Repo(intent()), Signer()
    with pytest.raises(CycleMtlError, match="verification failed"):
        reconcile_cycle_certificate(
            repo.issue.intent_id,
            CSR,
            repository=repo,
            signer=signer,
            verifier=Verifier(error=ValueError("do not expose this")),
        )
    assert repo.bindings == []
    assert repo.completed is None


@pytest.mark.parametrize(
    "csr", [b"", b"not a CSR", b"-----BEGIN CERTIFICATE REQUEST-----" + b"x" * 65536]
)
def test_invalid_or_oversized_csr_never_reaches_signer(csr):
    repo, signer = Repo(intent()), Signer()
    with pytest.raises(CycleMtlError, match="CSR is invalid"):
        reconcile_cycle_certificate(
            repo.issue.intent_id,
            csr,
            repository=repo,
            signer=signer,
            verifier=Verifier(),
        )
    assert signer.calls == []


def test_signer_failure_is_redacted_and_does_not_bind():
    class BrokenSigner:
        def issue(self, *_):
            raise RuntimeError("private key bytes must not escape")

    repo = Repo(intent())
    with pytest.raises(CycleMtlError) as exc:
        reconcile_cycle_certificate(
            repo.issue.intent_id,
            CSR,
            repository=repo,
            signer=BrokenSigner(),
            verifier=Verifier(),
        )
    assert "private key" not in str(exc.value)
    assert repo.bindings == []


@pytest.mark.parametrize(
    "kind,principal",
    [("AGENT", "aao-selfdev-review-" + "a" * 32), ("PUBLISHER", "aao-publisher-x")],
)
def test_intent_rejects_non_cycle_or_mismatched_identity(kind, principal):
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        CycleSigningIntent(
            uuid.uuid4(), uuid.uuid4(), "a" * 32, principal, kind, now, now + timedelta(hours=1)
        )


def test_production_cycle_issue_endpoint_fails_closed_before_db(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import (
        AuthenticatedPrincipal,
        SelfDevCycleIssueRequest,
        issue_selfdev_cycle_roles,
    )

    monkeypatch.setenv("AAO_ENV", "production")
    principal = AuthenticatedPrincipal("pm", "digest", "AGENT", workload_fingerprint="c" * 64)
    payload = SelfDevCycleIssueRequest(cycle_id="a" * 32, lifetime_seconds=60)
    with pytest.raises(HTTPException) as exc:
        issue_selfdev_cycle_roles(str(uuid.uuid4()), payload, principal)
    assert exc.value.status_code == 503
    assert "mTLS signer" in exc.value.detail
