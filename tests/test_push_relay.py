import base64
import hashlib
import hmac
import io
import json
import subprocess

import pytest

from aao.github_delivery_corroboration import DeliveryCorroborationInconclusive, PushWebhookTrust
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
        self.headers = {}


def setup(tmp_path, *, signature=None, fail_ack=False, relay_payload=None,
          github_payload=None, delivery_guid=ID, listed_guids=None):
    key = tmp_path / 'key.pem'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-out', str(key)],
                   check=True, capture_output=True)
    payload = relay_payload or {
        'repository': {'id': 7, 'full_name': 'o/r'},
        'sender': {'id': 55, 'login': 'app[bot]'}, 'ref': 'refs/heads/x',
        'before': '0' * 40, 'after': 'a' * 40,
    }
    verified_payload = github_payload or payload
    body = payload if isinstance(payload, bytes) else (json.dumps(payload, indent=2) + '\n ').encode()
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
            quarantined = list((directory / 'quarantine').glob('*.json'))
            if not quarantined:
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
                guids = listed_guids if listed_guids is not None else [delivery_guid]
                return Response(json.dumps([{'id': 123 + n, 'guid': g} for n, g in enumerate(guids)]).encode())
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
    kwargs, relay_calls, github_calls = setup(tmp_path, signature='sha256=' + '0' * 64)
    with pytest.raises(ValueError, match='signature'):
        drain_one(**kwargs)
    assert relay_calls == ['GET']
    assert github_calls == []  # HMAC is checked before any GitHub API call


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
    kwargs, relay_calls, github_calls = setup(tmp_path, fail_ack=True)
    for _ in range(2):
        with pytest.raises(ValueError, match='request failed'):
            drain_one(**kwargs)
    assert relay_calls == ['GET', 'POST', 'GET', 'POST']
    assert len(list(kwargs['directory'].glob('*.json'))) == 1
    # The reacquired head matched the stored receipt: re-ack only, no second GitHub lookup.
    assert len(github_calls) == 2


def test_reacquired_head_conflicting_with_stored_receipt_is_not_acked(tmp_path):
    kwargs, relay_calls, _ = setup(tmp_path, fail_ack=True)
    with pytest.raises(ValueError, match='request failed'):
        drain_one(**kwargs)
    stored = next(kwargs['directory'].glob('*.json'))
    stored.write_bytes(stored.read_bytes().replace(b'app[bot]', b'app[xot]'))
    with pytest.raises(ValueError, match='conflicts'):
        drain_one(**kwargs)
    assert relay_calls == ['GET', 'POST', 'GET']


def quarantine_record(kwargs):
    (path,) = (kwargs['directory'] / 'quarantine').glob('*.json')
    return path, json.loads(path.read_bytes())


@pytest.mark.parametrize('relay_payload, reason', [
    # Fork / repository outside verified configuration.
    ({'repository': {'id': 70, 'full_name': 'fork/r'}, 'sender': {'id': 55, 'login': 'app[bot]'},
      'ref': 'refs/heads/x', 'before': '0' * 40, 'after': 'a' * 40}, 'repository-not-configured'),
    # Human, github-actions[bot], dependabot or a renamed login: no persisted AAO mapping.
    ({'repository': {'id': 7, 'full_name': 'o/r'}, 'sender': {'id': 99, 'login': 'some-human'},
      'ref': 'refs/heads/x', 'before': '0' * 40, 'after': 'a' * 40}, 'sender-not-mapped'),
    ({'repository': {'id': 7, 'full_name': 'o/r'}, 'sender': {'id': 55, 'login': 'renamed[bot]'},
      'ref': 'refs/heads/x', 'before': '0' * 40, 'after': 'a' * 40}, 'sender-not-mapped'),
])
def test_non_attributable_head_is_quarantined_provisional_and_does_not_stall(
        tmp_path, relay_payload, reason):
    kwargs, relay_calls, github_calls = setup(tmp_path, relay_payload=relay_payload)
    assert drain_one(**kwargs)
    assert relay_calls == ['GET', 'POST']
    assert github_calls == []
    path, record = quarantine_record(kwargs)
    assert record['status'] == 'PROVISIONAL' and record['reason'] == reason
    assert record['schema'] == 'aao.github-push-quarantine.v1'
    assert record['delivery_id'] == ID and record['signature_256'].startswith('sha256=')
    assert json.loads(base64.b64decode(record['body_base64'])) == relay_payload
    assert oct(path.stat().st_mode & 0o777) == '0o640'
    # Quarantine grants no attribution: not visible as a push receipt.
    assert read_push_receipts(kwargs['directory'], repository='o/r', private_key=kwargs['private_key']) == []
    # Supervisor signature verifies over the canonical record.
    from aao.integration_authorization import canonical
    signature = base64.b64decode(record.pop('signature'))
    (tmp_path / 'msg').write_bytes(canonical(record))
    (tmp_path / 'sig').write_bytes(signature)
    subprocess.run(['openssl', 'pkey', '-in', kwargs['private_key'], '-pubout', '-out', str(tmp_path / 'pub')],
                   check=True, capture_output=True)
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(tmp_path / 'pub'), '-rawin',
                    '-sigfile', str(tmp_path / 'sig'), '-in', str(tmp_path / 'msg')], check=True, capture_output=True)


def test_non_dict_relayed_body_with_valid_hmac_fails_closed(tmp_path):
    kwargs, relay_calls, github_calls = setup(tmp_path, relay_payload=b'[1, 2]')
    with pytest.raises(TypeError, match='not an object'):
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


def test_inconclusive_corroboration_neither_stores_nor_acks_and_recovers_on_retry(tmp_path):
    listed = ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa']
    kwargs, relay_calls, github_calls = setup(tmp_path, listed_guids=listed)
    opener = kwargs['github_opener']
    original_open = opener.open

    def paged_open(req, timeout):
        response = original_open(req, timeout)
        if '?' in req.full_url:  # every list page claims another page exists
            response.headers = {'Link': f'<https://api.github.com/repos/o/r/hooks/9/deliveries'
                                        f'?per_page=100&cursor=c{len(github_calls)}>; rel="next"'}
        return response

    opener.open = paged_open
    with pytest.raises(DeliveryCorroborationInconclusive):
        drain_one(**kwargs)
    assert relay_calls == ['GET']
    assert len(github_calls) == 10
    assert not list(kwargs['directory'].glob('*.json'))
    # Retry once GitHub lists the delivery within the bound: stored, then acked.
    listed[:] = [ID]
    assert drain_one(**kwargs)
    assert relay_calls == ['GET', 'GET', 'POST']
