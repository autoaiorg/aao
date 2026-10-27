import io
import json
import urllib.error

import pytest

from aao.github_delivery_corroboration import PushWebhookTrust, corroborate_push_delivery

GUID = '11111111-1111-4111-8111-111111111111'
TRUST = PushWebhookTrust(
    repository='owner/repo', repository_id=10, hook_id=20,
    actor_map={(30, 'impl-app[bot]'): 'aao-impl-one'},
)


def payload(*, repository_id=10, sender_id=30, login='impl-app[bot]',
            ref='refs/heads/main', before='0' * 40, after='a' * 40):
    return {
        'repository': {'id': repository_id, 'full_name': 'owner/repo'},
        'sender': {'id': sender_id, 'login': login},
        'ref': ref, 'before': before, 'after': after,
    }


class Response(io.BytesIO):
    status = 200


class GithubOpener:
    def __init__(self, fetched=None, *, status=None, guids=None, event='push', hook_id='20'):
        self.fetched = fetched or payload()
        self.status = status
        self.guids = guids or [GUID]
        self.event = event
        self.hook_id = hook_id
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        assert request.get_header('Authorization') == 'Bearer independently-provisioned-token'
        if self.status:
            raise urllib.error.HTTPError(request.full_url, self.status, 'simulated', None, io.BytesIO())
        if '?' in request.full_url:
            return Response(json.dumps([
                {'id': 123 + index, 'guid': guid} for index, guid in enumerate(self.guids)
            ]).encode())
        detail = {
            'guid': self.guids[0], 'event': self.event,
            'request': {'headers': {
                'X-GitHub-Delivery': self.guids[0], 'X-GitHub-Event': self.event,
                'X-GitHub-Hook-ID': self.hook_id,
            }, 'payload': self.fetched},
        }
        return Response(json.dumps(detail).encode())


def corroborate(opener, *, candidate=None, guid=GUID, trust=TRUST):
    return corroborate_push_delivery(
        token='independently-provisioned-token', trust=trust, delivery_guid=guid,
        relay_payload=candidate or payload(), opener=opener,
    )


def test_returns_independently_fetched_payload_for_exact_guid():
    opener = GithubOpener()
    assert corroborate(opener) == payload()
    assert opener.calls == [
        'https://api.github.com/repos/owner/repo/hooks/20/deliveries?per_page=100',
        'https://api.github.com/repos/owner/repo/hooks/20/deliveries/123',
    ]


def test_missing_or_nonmatching_delivery_guid_fails_closed():
    opener = GithubOpener(guids=['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'])
    with pytest.raises(ValueError, match='GUID was not found'):
        corroborate(opener)
    with pytest.raises(ValueError, match='GUID is missing'):
        corroborate(GithubOpener(), guid='')


def test_fork_or_repository_id_mismatch_fails_closed():
    opener = GithubOpener(fetched=payload(repository_id=11))
    with pytest.raises(ValueError, match='repository ID'):
        corroborate(opener)


@pytest.mark.parametrize('status, message', [
    (401, 'revoked or unauthorized'), (403, 'revoked or unauthorized'),
    (503, 'temporarily unavailable'),
])
def test_revoked_credential_and_api_outage_fail_closed(status, message):
    with pytest.raises(ValueError, match=message):
        corroborate(GithubOpener(status=status))


def test_mismatched_identity_or_ref_transition_fails_closed():
    mismatch = GithubOpener(fetched=payload(after='b' * 40))
    with pytest.raises(ValueError, match='does not match relayed'):
        corroborate(mismatch)


def test_unknown_persisted_identity_mapping_fails_closed_before_api_call():
    opener = GithubOpener()
    with pytest.raises(ValueError, match='no persisted AAO identity mapping'):
        corroborate(opener, candidate=payload(sender_id=31, login='unknown[bot]'))
    assert opener.calls == []


@pytest.mark.parametrize('event, hook_id', [('issues', '20'), ('push', '21')])
def test_wrong_event_or_hook_fails_closed(event, hook_id):
    with pytest.raises(ValueError, match='not the configured push webhook event'):
        corroborate(GithubOpener(event=event, hook_id=hook_id))


def test_no_redirects_are_configured_for_default_https_transport(monkeypatch):
    # Inspect the builder path via patching build_opener; no network call occurs.
    import aao.github_delivery_corroboration as module

    captured = {}

    def build_opener(handler):
        captured['handler'] = handler
        return GithubOpener()

    monkeypatch.setattr(module.urllib.request, 'build_opener', build_opener)
    corroborate_push_delivery(token='independently-provisioned-token', trust=TRUST,
        delivery_guid=GUID, relay_payload=payload())
    assert captured['handler'].__class__.__name__ == '_NoRedirect'
