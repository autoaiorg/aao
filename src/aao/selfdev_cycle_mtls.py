"""Fail-closed orchestration contract for typed Self Development cycle mTLS.

This module deliberately contains no CA implementation. Production must inject
an independently reviewed Unix-socket signer and certificate-chain verifier.
The workload generates and retains its own private key; only its CSR crosses
the signer boundary.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

MAX_CSR_BYTES = 64 * 1024
MAX_CHAIN_BYTES = 128 * 1024
_CYCLE_ID = re.compile(r"^[0-9a-f]{32}$")


class CycleMtlError(RuntimeError):
    """Safe-to-display cycle mTLS orchestration failure; contains no secret."""


@dataclass(frozen=True)
class CycleSigningIntent:
    """Authoritative server-created intent; never constructed from CSR fields."""

    intent_id: uuid.UUID
    project_id: uuid.UUID
    cycle_id: str
    principal_id: str
    kind: str
    not_before: datetime
    not_after: datetime

    def __post_init__(self) -> None:
        if not _CYCLE_ID.fullmatch(self.cycle_id):
            raise ValueError("invalid Self Development cycle id")
        expected = {
            "AGENT": f"aao-selfdev-impl-{self.cycle_id}",
            "AUDITOR": f"aao-selfdev-review-{self.cycle_id}",
        }
        if self.kind not in expected or self.principal_id != expected[self.kind]:
            raise ValueError("principal is not the fixed identity for this cycle kind")
        if (
            self.not_before.tzinfo is None
            or self.not_after.tzinfo is None
            or self.not_before.utcoffset() != UTC.utcoffset(self.not_before)
            or self.not_after.utcoffset() != UTC.utcoffset(self.not_after)
            or self.not_after <= self.not_before
            or (self.not_after - self.not_before).total_seconds() > 2 * 60 * 60
        ):
            raise ValueError("intent validity must be a bounded UTC interval")


@dataclass(frozen=True)
class SignedCycleCertificate:
    """Public certificate chain returned by the signer, never a private key."""

    certificate_chain_pem: bytes


class IntentRepository(Protocol):
    """Persistence boundary; implementations must use transactions/row locks."""

    def get_pending_intent(self, intent_id: uuid.UUID) -> CycleSigningIntent | None: ...

    def get_completed_binding(self, intent_id: uuid.UUID) -> tuple[str, str, bytes] | None:
        """Return fingerprint, exact CSR digest, and stored public chain."""

    def complete_binding(
        self,
        intent: CycleSigningIntent,
        fingerprint: str,
        csr_sha256: str,
        certificate_chain_pem: bytes,
    ) -> None:
        """Atomically bind cert+CSR digest, enable principal, and complete intent."""
        ...


class CycleSigner(Protocol):
    """Narrow signer boundary. Implementations must validate the committed intent."""

    def issue(self, intent: CycleSigningIntent, csr_pem: bytes) -> SignedCycleCertificate:
        """Idempotently issue for exactly this intent; reject general signing requests."""
        ...


class CertificateVerifier(Protocol):
    """Independent verifier for chain, CSR key match, SAN identity and validity."""

    def verify(
        self, intent: CycleSigningIntent, csr_pem: bytes, certificate_chain_pem: bytes
    ) -> str:
        """Return lowercase SHA-256 leaf fingerprint or raise without leaking inputs."""
        ...


def reconcile_cycle_certificate(
    intent_id: uuid.UUID,
    csr_pem: bytes,
    *,
    repository: IntentRepository,
    signer: CycleSigner,
    verifier: CertificateVerifier,
) -> tuple[str, bytes]:
    """Issue or recover one certificate and publish its binding atomically.

    Replaying a completed intent returns its existing fingerprint and public
    chain only when the
    exact CSR SHA-256 matches; mismatched CSR replay conflicts without contacting
    the signer. Any missing intent, malformed CSR, oversized result,
    verifier error, or invalid fingerprint leaves the principal non-executable.
    No credential, private key, or CSR is logged or returned. The result
    contains only the public certificate fingerprint and chain.
    """
    if not isinstance(csr_pem, bytes) or not csr_pem or len(csr_pem) > MAX_CSR_BYTES:
        raise CycleMtlError("cycle CSR is invalid")
    if b"-----BEGIN CERTIFICATE REQUEST-----" not in csr_pem:
        raise CycleMtlError("cycle CSR is invalid")

    csr_sha256 = hashlib.sha256(csr_pem).hexdigest()
    completed = repository.get_completed_binding(intent_id)
    if completed is not None:
        fingerprint, stored_csr_sha256, stored_chain = completed
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint) or not re.fullmatch(
            r"[0-9a-f]{64}", stored_csr_sha256
        ):
            raise CycleMtlError("stored cycle binding is invalid")
        if stored_csr_sha256 != csr_sha256:
            raise CycleMtlError("cycle intent already completed with a different CSR")
        if not isinstance(stored_chain, bytes) or not stored_chain:
            raise CycleMtlError("stored cycle certificate is unavailable")
        return fingerprint, stored_chain

    intent = repository.get_pending_intent(intent_id)
    if intent is None:
        raise CycleMtlError("pending cycle intent not found")
    try:
        signed = signer.issue(intent, csr_pem)
    except Exception:  # noqa: BLE001 - redact arbitrary injected signer failures
        raise CycleMtlError("cycle signer unavailable") from None
    chain = signed.certificate_chain_pem
    if not isinstance(chain, bytes) or not chain or len(chain) > MAX_CHAIN_BYTES:
        raise CycleMtlError("cycle signer returned an invalid certificate chain")
    if b"-----BEGIN CERTIFICATE-----" not in chain or b"PRIVATE KEY" in chain:
        raise CycleMtlError("cycle signer returned an invalid certificate chain")
    try:
        chain.decode("ascii")
    except UnicodeDecodeError:
        raise CycleMtlError("cycle signer returned an invalid certificate chain") from None
    try:
        fingerprint = verifier.verify(intent, csr_pem, chain)
    except Exception:  # noqa: BLE001 - redact arbitrary verifier failures
        raise CycleMtlError("cycle certificate verification failed") from None
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise CycleMtlError("cycle certificate verification failed")

    # This repository operation must lock the intent and principal, re-check
    # revocation/expiry, and atomically insert the binding before enabling it.
    repository.complete_binding(intent, fingerprint, csr_sha256, chain)
    return fingerprint, chain
