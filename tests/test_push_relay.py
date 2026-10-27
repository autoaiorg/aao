import base64
import hashlib
import hmac
import io
import json
import subprocess

import pytest

from aao.github_delivery_corroboration import PushWebhookTrust
from aao.push_receipts import read_push_receipts
from aao.push_relay import drain_one

GITHUB = b'g' * 32
PULL = b'p' * 32
API_TOKEN = 'explicit-api-token-for-test'
ID = '11111111-1111-4111-8111-111111111111'
TRUST = PushWebhookTrust(
    repository='o/r', repository_id=7, hook_id=9,
    actor_map={(55, 'app[bot]'): 'aao-impl-one'},
)


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


def setup(tmp_path, *, signature=None, fail_ack=False, relay_payload=None,
          github_payload=None, delivery_guid=ID):
    key = tmp_path / 'key.pem'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-out', str(key)],
                   check=True, capture_output=True)
    payload = relay_payload or {
        'repository': {'id': 7, 'full_name': 'o/r'},
        'sender': {'id': 55, 'login': 'app[bot]'}, 'ref': 'refs/heads/x',
        'before': '0' * 40, 'after': 'a' * 40,
    }
    verified_payload = github_payload or payload
    body = (json.dumps(payload, indent=2) + '\n ').encode()
    rows = [{'delivery_id': delivery_guid, 'body_base64': base64.b64encode(body).decode(),
             'signature': signature or 'sha256=' + hmac.new(GITHUB, body, hashlib.sha256).hexdigest()}]
    relay_calls = []
    github_calls = []
    directory = tmp_path / 'receipts'

    class RelayOpener:
        def open(self, req, timeout):
            relay_calls.append(req.method)
            path = req.full_url.removeprefix('https://relay')
            timestamp = req.get_header('X-aao-timestamp')
            message = f'{req.method}\n{path}\n{timestamp}\n{hashlib.sha256(b"").hexdigest()}'.encode()
            assert req.get_header('X-aao-signature') == hmac.new(PULL, message, hashlib.sha256).hexdigest()
            if req.method == 'GET':
                return Response(json.dumps(rows).encode())
            assert path == f'/receipts/{delivery_guid.lower()}/ack'
            # ACK is impossible before a corroborated and durable receipt exists.
            assert read_push_receipts(directory, repository='o/r', private_key=str(key))[0]['actor'] == 'app[bot]'
            if fail_ack:
                raise OSError('simulated transport failure')
            return Response(b'', 204)

    class GithubOpener:
        def open(self, req, timeout):
            github_calls.append(req.full_url)
            assert req.get_header('Authorization') == f'Bearer {API_TOKEN}'
            assert req.full_url.startswith('https://api.github.com/repos/o/r/hooks/9/deliveries')
            if '?' in req.full_url:
                return Response(json.dumps([{'id': 123, 'guid': delivery_guid}]).encode())
            detail = {
                'id': 123, 'guid': delivery_guid, 'event': 'push',
                'request': {'headers': {
                    'X-GitHub-Delivery': delivery_guid, 'X-GitHub-Event': 'push',
                    'X-GitHub-Hook-ID': '9',
                }, 'payload': verified_payload},
            }
            return Response(json.dumps(detail).encode())

    kwargs = {
        'endpoint': 'https://relay', 'pull_secret': PULL, 'github_secret': GITHUB,
        'github_api_token': API_TOKEN, 'webhook_trust': TRUST,
        'directory': directory, 'private_key': str(key), 'opener': RelayOpener(),
        'github_opener': GithubOpener(),
    }
    return kwargs, relay_calls, github_calls


def test_corroborated_original_bytes_persist_before_ack(tmp_path):
    kwargs, relay_calls, github_calls = setup(tmp_path)
    assert drain_one(**kwargs)
    assert relay_calls == ['GET', 'POST']
    assert len(github_calls) == 2


def test_invalid_webhook_hmac_never_acknowledged(tmp_path):
    kwargs, relay_calls, _ = setup(tmp_path, signature='sha256=' + '0' * 64)
    with pytest.raises(ValueError, match='signature'):
        drain_one(**kwargs)
    assert relay_calls == ['GET']


def test_valid_hmac_over_forged_transition_still_requires_github_match(tmp_path):
    forged = {
        'repository': {'id': 7, 'full_name': 'o/r'},
        'sender': {'id': 55, 'login': 'app[bot]'}, 'ref': 'refs/heads/x',
        'before': '0' * 40, 'after': 'b' * 40,
    }
    actual = {**forged, 'after': 'a' * 40}
    kwargs, relay_calls, github_calls = setup(tmp_path, relay_payload=forged, github_payload=actual)
    with pytest.raises(ValueError, match='does not match relayed'):
        drain_one(**kwargs)
    assert relay_calls == ['GET']
    assert len(github_calls) == 2
    assert not list(kwargs['directory'].glob('*.json'))


def test_ack_failure_retries_without_losing_or_conflicting_receipt(tmp_path):
    kwargs, relay_calls, _ = setup(tmp_path, fail_ack=True)
    for _ in range(2):
        with pytest.raises(ValueError, match='request failed'):
            drain_one(**kwargs)
    assert relay_calls == ['GET', 'POST', 'GET', 'POST']
    assert len(list(kwargs['directory'].glob('*.json'))) == 1


def test_repo_not_in_verified_configuration_never_acknowledged(tmp_path):
    kwargs, relay_calls, github_calls = setup(tmp_path)
    kwargs['webhook_trust'] = PushWebhookTrust(
        repository='other/repo', repository_id=8, hook_id=10,
        actor_map={(55, 'app[bot]'): 'aao-impl-one'},
    )
    with pytest.raises(ValueError, match='allowlisted'):
        drain_one(**kwargs)
    assert relay_calls == ['GET']
    assert github_calls == []


def test_github_api_credential_must_be_explicit_and_distinct(tmp_path):
    kwargs, relay_calls, github_calls = setup(tmp_path)
    kwargs['github_api_token'] = GITHUB.decode()
    with pytest.raises(ValueError, match='independent GitHub API credential'):
        drain_one(**kwargs)
    assert relay_calls == []
    assert github_calls == []


@pytest.mark.parametrize('endpoint', ['http://relay', 'https://user@relay', 'https://relay/path', 'https://relay?x=1'])
def test_relay_origin_restricted(tmp_path, endpoint):
    kwargs, relay_calls, github_calls = setup(tmp_path)
    kwargs['endpoint'] = endpoint
    with pytest.raises(ValueError, match='HTTPS origin'):
        drain_one(**kwargs)
    assert relay_calls == []
    assert github_calls == []
