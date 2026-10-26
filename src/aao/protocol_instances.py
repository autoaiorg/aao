"""Pinned protocol-instance metadata for canonical work operations."""

import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException

PROTOCOL_VERSIONS = {"intake-classification": "1.0.0"}


def start_work_protocol(
    db,
    *,
    protocol_id: str,
    work_id: str,
    started_by: str,
    request: dict,
) -> str:
    """Pin a fixed protocol version and emit its start event in the caller's tx."""
    version = PROTOCOL_VERSIONS.get(protocol_id)
    if version is None:
        raise ValueError(f"Protocol is not enabled: {protocol_id}")
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    request_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    key = f"{protocol_id}:{work_id}"
    instance_id = str(uuid4())
    inserted = db.execute(
        "INSERT INTO protocol_instances(id,protocol_id,protocol_version,subject_type,subject_id,"
        "idempotency_key,request_sha256,started_by) VALUES (%s,%s,%s,'work_item',%s,%s,%s,%s) "
        "ON CONFLICT (protocol_id,subject_type,subject_id,idempotency_key) DO NOTHING RETURNING id",
        (instance_id, protocol_id, version, work_id, key, request_sha256, started_by),
    ).fetchone()
    if inserted is None:
        existing = db.execute(
            "SELECT id,protocol_version,request_sha256 FROM protocol_instances "
            "WHERE protocol_id=%s AND subject_type='work_item' AND subject_id=%s "
            "AND idempotency_key=%s",
            (protocol_id, work_id, key),
        ).fetchone()
        if not existing or existing[1] != version or existing[2] != request_sha256:
            raise HTTPException(409, "Protocol instance conflicts with the original request")
        return str(existing[0])

    instance_id = str(inserted[0])
    db.execute(
        "INSERT INTO events(id,subject_id,kind,details) VALUES (%s,%s,'protocol.started',%s::jsonb)",
        (str(uuid4()), work_id, json.dumps({
            "protocol_instance_id": instance_id,
            "protocol_id": protocol_id,
            "protocol_version": version,
            "actor": started_by,
        })),
    )
    return instance_id
