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

    def get_completed_binding(self, intent_id):
        return self.completed

    def complete_binding(self, issued_intent, fingerprint, csr_sha256, chain):
        # Model one atomic persisted binding record.
        binding = (issued_intent, fingerprint, csr_sha256, chain)
        self.bindings.append(binding)
        self.completed = (fingerprint, csr_sha256, chain)


class Signer:
    def __init__(self, chain=b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"):
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
    assert result == ("b" * 64, signer.chain)
    import hashlib

    assert repo.bindings == [(repo.issue, "b" * 64, hashlib.sha256(CSR).hexdigest(), signer.chain)]
    assert len(signer.calls) == len(verifier.calls) == 1

    assert reconcile_cycle_certificate(
        repo.issue.intent_id,
        CSR,
        repository=repo,
        signer=signer,
        verifier=verifier,
    ) == ("b" * 64, signer.chain)
    assert len(signer.calls) == len(verifier.calls) == 1


def test_completed_intent_with_different_csr_conflicts_without_signing():
    import hashlib

    repo, signer, verifier = Repo(intent()), Signer(), Verifier()
    reconcile_cycle_certificate(
        repo.issue.intent_id, CSR, repository=repo, signer=signer, verifier=verifier
    )
    with pytest.raises(CycleMtlError, match="different CSR"):
        reconcile_cycle_certificate(
            repo.issue.intent_id,
            CSR + b"different",
            repository=repo,
            signer=signer,
            verifier=verifier,
        )
    assert repo.completed == ("b" * 64, hashlib.sha256(CSR).hexdigest(), signer.chain)
    assert len(repo.bindings) == 1
    assert len(signer.calls) == 1


def test_binding_completion_persists_fingerprint_and_csr_digest_together():
    import hashlib

    repo, signer, verifier = Repo(intent()), Signer(), Verifier()
    reconcile_cycle_certificate(
        repo.issue.intent_id, CSR, repository=repo, signer=signer, verifier=verifier
    )
    assert repo.bindings == [(repo.issue, "b" * 64, hashlib.sha256(CSR).hexdigest(), signer.chain)]


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


def test_authenticated_certificate_chain_recovery_returns_only_public_chain(monkeypatch):
    from datetime import datetime

    from fastapi import HTTPException

    from aao.work_management_api import AuthenticatedPrincipal, _cycle_mtls_certificate_for

    seen = []
    expires = datetime.now(UTC) + timedelta(minutes=5)

    class FakeRepository:
        def get_active_certificate(self, principal_id, digest, kind, fingerprint):
            seen.append((principal_id, digest, kind, fingerprint))
            return (b"-----BEGIN CERTIFICATE-----\npublic\n", "a" * 64, expires)

    monkeypatch.setattr(
        "aao.selfdev_cycle_mtls_repository.PostgresCycleIntentRepository",
        FakeRepository,
    )
    principal = AuthenticatedPrincipal(
        "cycle-agent", "digest", "AGENT", workload_fingerprint="a" * 64
    )
    result = _cycle_mtls_certificate_for(principal)
    assert seen == [("cycle-agent", "digest", "AGENT", "a" * 64)]
    assert result["certificate_chain_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert result["certificate_sha256"] == "a" * 64
    assert "token" not in result and "private_key" not in result

    principal_without_mtls = AuthenticatedPrincipal("cycle-agent", "digest", "AGENT")
    with pytest.raises(HTTPException) as denied:
        _cycle_mtls_certificate_for(principal_without_mtls)
    assert denied.value.status_code == 403
    assert len(seen) == 1


def test_certificate_chain_recovery_returns_not_found_when_not_active(monkeypatch):
    from fastapi import HTTPException

    from aao.work_management_api import AuthenticatedPrincipal, _cycle_mtls_certificate_for

    class MissingRepository:
        def get_active_certificate(self, *_):
            return None

    monkeypatch.setattr(
        "aao.selfdev_cycle_mtls_repository.PostgresCycleIntentRepository",
        MissingRepository,
    )
    principal = AuthenticatedPrincipal(
        "cycle-agent", "digest", "AGENT", workload_fingerprint="a" * 64
    )
    with pytest.raises(HTTPException) as missing:
        _cycle_mtls_certificate_for(principal)
    assert missing.value.status_code == 404
