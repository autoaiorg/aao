import hashlib
import hmac
import http.client
import json
import os
import subprocess
import threading
from http.server import ThreadingHTTPServer

import pytest

from aao.push_receipts import make_webhook_handler, read_push_receipts, store_push_receipt
from aao.supervisor_service import attribution


def _key(path):
    subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(path)],
                   check=True, capture_output=True)


def _push():
    return {"repository": {"full_name": "owner/repo"}, "sender": {"login": "aao-impl[bot]"},
            "ref": "refs/heads/feature", "before": "0" * 40, "after": "a" * 40, "deleted": False}


def _store(directory, key, payload=None, *, delivery="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", secret=b"webhook-secret"):
    payload = _push() if payload is None else payload
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return store_push_receipt(directory, payload, repository="owner/repo", delivery_id=delivery,
                              raw_body=body, secret=secret, signature=signature, private_key=str(key))


def test_signed_receipt_is_durable_idempotent_and_verifiable(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    directory = tmp_path / "receipts"
    receipt_path = _store(directory, key)
    mode = os.stat(receipt_path).st_mode & 0o777
    assert mode == 0o640
    assert _store(directory, key) == receipt_path
    receipts = read_push_receipts(directory, repository="owner/repo", private_key=str(key))
    assert receipts == [{"schema": "aao.github-push-receipt.v1", "delivery_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                         "repository": "owner/repo", "actor": "aao-impl[bot]", "ref": "refs/heads/feature",
                         "before": "0" * 40, "after": "a" * 40}]


def test_invalid_signature_and_invalid_payload_are_rejected(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    payload = _push()
    body = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="signature"):
        store_push_receipt(tmp_path / "receipts", payload, repository="owner/repo",
                           delivery_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", raw_body=body,
                           secret=b"secret", signature="sha256=" + "0" * 64, private_key=str(key))
    with pytest.raises(ValueError, match="repository"):
        _store(tmp_path / "receipts", key, payload={**payload, "repository": {"full_name": "other/repo"}})
    assert not (tmp_path / "receipts").exists()


def test_redelivery_id_cannot_replace_a_different_authenticated_receipt(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    directory = tmp_path / "receipts"
    _store(directory, key)
    changed = {**_push(), "sender": {"login": "aao-pm[bot]"}}
    with pytest.raises(ValueError, match="conflicts"):
        _store(directory, key, payload=changed)


def test_tampered_receipt_is_rejected(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    receipt_path = _store(tmp_path / "receipts", key)
    receipt_path.chmod(0o600)
    document = json.loads(receipt_path.read_text())
    document["actor"] = "attacker"
    receipt_path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="signature"):
        read_push_receipts(receipt_path.parent, repository="owner/repo", private_key=str(key))


def test_shared_receipt_directory_filters_other_authenticated_repositories(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    directory = tmp_path / "receipts"
    _store(directory, key)
    fork_payload = {**_push(), "repository": {"full_name": "owner/impl-fork"},
                    "sender": {"login": "aao-impl[bot]"}, "after": "c" * 40}
    body = json.dumps(fork_payload, separators=(",", ":")).encode()
    secret = b"webhook-secret"
    signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    store_push_receipt(directory, fork_payload, repository="owner/impl-fork",
        delivery_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", raw_body=body, secret=secret,
        signature=signature, private_key=str(key))

    canonical = read_push_receipts(directory, repository="owner/repo", private_key=str(key))
    fork = read_push_receipts(directory, repository="owner/impl-fork", private_key=str(key))
    assert [receipt["repository"] for receipt in canonical] == ["owner/repo"]
    assert [receipt["repository"] for receipt in fork] == ["owner/impl-fork"]


def test_attribution_uses_durable_receipts_after_api_event_window_loses_chain(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    directory = tmp_path / "receipts"
    older, head = "b" * 40, "a" * 40
    first = {"repository": {"full_name": "owner/repo"}, "sender": {"login": "aao-pm[bot]"},
             "ref": "refs/heads/feature", "before": "0" * 40, "after": older, "deleted": False}
    second = {**_push(), "before": older, "after": head}
    _store(directory, key, payload=first, delivery="11111111-1111-4111-8111-111111111111")
    _store(directory, key, payload=second, delivery="22222222-2222-4222-8222-222222222222")

    class Client:
        def request(self, _method, path):
            responses = {
                "/repos/owner/repo/pulls?state=open&per_page=100": [{"number": 3, "head": {
                    "sha": head, "ref": "feature", "repo": {"full_name": "owner/repo"}}}],
                "/repos/owner/repo/events?per_page=100": [],
                "/repos/owner/repo/pulls/3/commits?per_page=100": [{"sha": head}],
            }
            return type("Response", (), {"status": 200, "body": responses.get(path, [])})()

    output = tmp_path / "attribution.json"
    result = attribution({"repository": "owner/repo", "attribution_path": str(output),
                          "push_receipts_dir": str(directory), "private_key": str(key)}, Client())
    assert result == {"candidates": 1, "skipped_prs": []}
    saved = json.loads(output.read_text())
    assert saved["candidates"][head] == ["aao-impl[bot]", "aao-pm[bot]"]


def test_webhook_http_receiver_authenticates_and_accepts_only_allowlisted_repositories(tmp_path):
    key = tmp_path / "private.pem"
    _key(key)
    secret = b"x" * 32
    handler = make_webhook_handler(directory=tmp_path / "receipts", repository="owner/repo",
        repositories={"owner/repo", "owner/impl-fork"}, secret=secret, private_key=str(key))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = {**_push(), "repository": {"full_name": "owner/impl-fork"}}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("POST", "/github/push", body=raw, headers={"Content-Length": str(len(raw)),
            "X-GitHub-Event": "push", "X-GitHub-Delivery": "33333333-3333-4333-8333-333333333333",
            "X-Hub-Signature-256": sig})
        assert conn.getresponse().status == 202
        conn.close()

        payload["repository"] = {"full_name": "owner/unlisted"}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        conn.request("POST", "/github/push", body=raw, headers={"Content-Length": str(len(raw)),
            "X-GitHub-Event": "push", "X-GitHub-Delivery": "44444444-4444-4444-8444-444444444444",
            "X-Hub-Signature-256": sig})
        assert conn.getresponse().status == 401
        conn.close()
        receipts = read_push_receipts(tmp_path / "receipts", repository="owner/impl-fork", private_key=str(key))
        assert len(receipts) == 1 and receipts[0]["actor"] == "aao-impl[bot]"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
