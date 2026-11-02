import io
import json
import urllib.error
import urllib.parse

import pytest

from aao.github_delivery_corroboration import (
    DeliveryCorroborationInconclusive,
    PushWebhookTrust,
    corroborate_push_delivery,
)

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

    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


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


OTHER = 'aaaaaaaa-aaaa-4aaa-8aaa-{:012x}'
BASE = 'https://api.github.com/repos/owner/repo/hooks/20/deliveries'


class PagedOpener(GithubOpener):
    """Cursor-paginated delivery list; page N links to cursor vN until the last page."""

    def __init__(self, pages, *, link=None, **kwargs):
        super().__init__(**kwargs)
        self.pages = pages
        self.link = link

    def open(self, request, timeout):
        if '?' not in request.full_url:
            return super().open(request, timeout)
        self.calls.append(request.full_url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        index = int(query.get('cursor', ['v0'])[0][1:])
        page = self.pages[index]
        if not isinstance(page, list):
            return Response(json.dumps(page).encode())
        items = [{'id': 1000 * index + n, 'guid': guid} if isinstance(guid, str) else guid
                 for n, guid in enumerate(page)]
        link = self.link
        if link is None and index + 1 < len(self.pages):
            link = f'<{BASE}?per_page=100&cursor=v{index + 1}>; rel="next"'
        return Response(json.dumps(items).encode(), headers={'Link': link} if link else {})


def filler(page):
    return [OTHER.format(page * 100 + n) for n in range(100)]


def test_delivery_on_first_page_does_not_fetch_further_pages():
    opener = PagedOpener([filler(0)[:50] + [GUID], filler(1)])
    assert corroborate(opener) == payload()
    assert opener.calls == [f'{BASE}?per_page=100', f'{BASE}/50']


def test_delivery_on_third_page_is_found_by_cursor():
    opener = PagedOpener([filler(0), filler(1), [OTHER.format(999), GUID]])
    assert corroborate(opener) == payload()
    assert opener.calls == [
        f'{BASE}?per_page=100', f'{BASE}?per_page=100&cursor=v1',
        f'{BASE}?per_page=100&cursor=v2', f'{BASE}/2001',
    ]


def test_delivery_beyond_page_bound_is_retryable_inconclusive_not_invalid():
    opener = PagedOpener([filler(0), filler(1), filler(2), [GUID]])
    with pytest.raises(DeliveryCorroborationInconclusive, match='bounded delivery scan'):
        corroborate_push_delivery(
            token='independently-provisioned-token', trust=TRUST, delivery_guid=GUID,
            relay_payload=payload(), opener=opener, max_pages=3)
    assert len(opener.calls) == 3
    # The same delivery is accepted once it is listed within the bound.
    assert corroborate(PagedOpener([filler(0), filler(1), filler(2), [GUID]])) == payload()


def test_guid_absent_from_exhausted_list_is_not_found_not_inconclusive():
    with pytest.raises(ValueError, match='GUID was not found') as caught:
        corroborate(PagedOpener([filler(0), filler(1)]))
    assert not isinstance(caught.value, DeliveryCorroborationInconclusive)


@pytest.mark.parametrize('pages, link, error, message', [
    ([filler(0), {'message': 'not a list'}], None, TypeError, 'list is malformed'),
    ([filler(0), [42, GUID]], None, TypeError, 'list is malformed'),
    ([filler(0), [GUID]], '<https://evil.example/repos/owner/repo/hooks/20/deliveries?cursor=v1>; rel="next"',
     ValueError, 'pagination link is malformed'),
    ([filler(0), [GUID]], '<https://api.github.com/repos/other/repo/hooks/20/deliveries?cursor=v1>; rel="next"',
     ValueError, 'pagination link is malformed'),
    ([filler(0), [GUID]], f'<{BASE}?per_page=100>; rel="next"', ValueError, 'pagination link is malformed'),
    ([filler(0), [GUID]], f'<{BASE}?cursor=v1&page=2>; rel="next"', ValueError, 'pagination link is malformed'),
    ([filler(0), filler(1)], f'<{BASE}?cursor=v1>; rel="next"', ValueError, 'pagination link is malformed'),
])
def test_malformed_page_or_pagination_link_fails_closed(pages, link, error, message):
    with pytest.raises(error, match=message) as caught:
        corroborate(PagedOpener(pages, link=link))
    assert not isinstance(caught.value, DeliveryCorroborationInconclusive)
