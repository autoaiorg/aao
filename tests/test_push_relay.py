import base64
import hashlib
import hmac
import io
import json
import subprocess

import pytest

from aao.push_receipts import read_push_receipts
from aao.push_relay import drain_one

GITHUB = b'g' * 32
PULL = b'p' * 32
ID = '11111111-1111-4111-8111-111111111111'


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


def setup(tmp_path, *, signature=None, fail_ack=False):
    key = tmp_path / 'key.pem'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-out', str(key)],
                   check=True, capture_output=True)
    payload = {'repository': {'full_name': 'o/r'}, 'sender': {'login': 'app[bot]'},
               'ref': 'refs/heads/x', 'before': '0' * 40, 'after': 'a' * 40}
    body = (json.dumps(payload, indent=2) + '\n ').encode()
    rows = [{'delivery_id': ID, 'body_base64': base64.b64encode(body).decode(),
             'signature': signature or 'sha256=' + hmac.new(GITHUB, body, hashlib.sha256).hexdigest()}]
    calls = []
    directory = tmp_path / 'receipts'

    class Opener:
        def open(self, req, timeout):
            calls.append(req.method)
            path = req.full_url.removeprefix('https://relay')
            timestamp = req.get_header('X-aao-timestamp')
            message = f'{req.method}\n{path}\n{timestamp}\n{hashlib.sha256(b"").hexdigest()}'.encode()
            assert req.get_header('X-aao-signature') == hmac.new(PULL, message, hashlib.sha256).hexdigest()
            if req.method == 'GET':
                return Response(json.dumps(rows).encode())
            # The ack is impossible before a signed, readable local receipt exists.
            assert read_push_receipts(directory, repository='o/r', private_key=str(key))[0]['actor'] == 'app[bot]'
            if fail_ack:
                raise OSError('simulated transport failure')
            return Response(b'', 204)

    kwargs = {'endpoint': 'https://relay', 'pull_secret': PULL, 'github_secret': GITHUB,
              'directory': directory, 'repositories': {'o/r'}, 'private_key': str(key), 'opener': Opener()}
    return kwargs, calls


def test_original_bytes_verified_and_persisted_before_ack(tmp_path):
    kwargs, calls = setup(tmp_path)
    assert drain_one(**kwargs)
    assert calls == ['GET', 'POST']


def test_invalid_signature_never_acknowledged(tmp_path):
    kwargs, calls = setup(tmp_path, signature='sha256=' + '0' * 64)
    with pytest.raises(ValueError, match='signature'):
        drain_one(**kwargs)
    assert calls == ['GET']


def test_ack_failure_retries_without_losing_or_conflicting_receipt(tmp_path):
    kwargs, calls = setup(tmp_path, fail_ack=True)
    for _ in range(2):
        with pytest.raises(ValueError, match='request failed'):
            drain_one(**kwargs)
    assert calls == ['GET', 'POST', 'GET', 'POST']
    assert len(list(kwargs['directory'].glob('*.json'))) == 1


def test_unallowlisted_repository_never_acknowledged(tmp_path):
    kwargs, calls = setup(tmp_path)
    kwargs['repositories'] = {'other/repo'}
    with pytest.raises(ValueError, match='allowlisted'):
        drain_one(**kwargs)
    assert calls == ['GET']


@pytest.mark.parametrize('endpoint', ['http://relay', 'https://user@relay', 'https://relay/path', 'https://relay?x=1'])
def test_relay_origin_restricted(tmp_path, endpoint):
    kwargs, calls = setup(tmp_path)
    kwargs['endpoint'] = endpoint
    with pytest.raises(ValueError, match='HTTPS origin'):
        drain_one(**kwargs)
    assert calls == []
