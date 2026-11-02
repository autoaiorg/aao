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
    def __init__(self, fetched=None, *, status=None, guids=None, event='push', hook_id='20',
                 error=None, error_headers=None, response_status=200, detail_body=None, **detail):
        self.fetched = fetched or payload()
        self.status = status
        self.guids = guids or [GUID]
        self.event = event
        self.hook_id = hook_id
        self.error = error
        self.error_headers = error_headers
        self.response_status = response_status
        self.detail_body = detail_body
        self.detail = detail  # single-field overrides: header_event, detail_event, header_guid, detail_guid
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request.full_url)
        assert request.get_header('Authorization') == 'Bearer independently-provisioned-token'
        if self.error:
            raise self.error
        if self.status:
            raise urllib.error.HTTPError(request.full_url, self.status, 'simulated',
                                         self.error_headers or {}, io.BytesIO())
        if '?' in request.full_url:
            response = Response(json.dumps([
                {'id': 123 + index, 'guid': guid} for index, guid in enumerate(self.guids)
            ]).encode())
            response.status = self.response_status
            return response
        if self.detail_body is not None:
            return Response(self.detail_body)
        detail = {
            'guid': self.detail.get('detail_guid', self.guids[0]),
            'event': self.detail.get('detail_event', self.event),
            'request': {'headers': {
                'X-GitHub-Delivery': self.detail.get('header_guid', self.guids[0]),
                'X-GitHub-Event': self.detail.get('header_event', self.event),
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
])
def test_revoked_credential_fails_closed_and_is_not_retryable(status, message):
    with pytest.raises(ValueError, match=message) as caught:
        corroborate(GithubOpener(status=status))
    assert not isinstance(caught.value, DeliveryCorroborationInconclusive)


@pytest.mark.parametrize('status, headers, message, retry_after', [
    (429, {'Retry-After': '30'}, 'rate limited', 30),
    (403, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1000120'}, 'rate limited', 120),
    (403, {'Retry-After': '5'}, 'rate limited', 5),
    (429, {}, 'rate limited', 60),
    (500, {}, 'temporarily unavailable', None),
    (503, {}, 'temporarily unavailable', None),
])
def test_rate_limit_and_outage_are_retryable_inconclusive(monkeypatch, status, headers, message, retry_after):
    import aao.github_delivery_corroboration as module
    monkeypatch.setattr(module.time, 'time', lambda: 1000000)
    with pytest.raises(DeliveryCorroborationInconclusive, match=message) as caught:
        corroborate(GithubOpener(status=status, error_headers=headers))
    assert caught.value.retry_after == retry_after


def test_network_failure_is_retryable_inconclusive():
    with pytest.raises(DeliveryCorroborationInconclusive, match='request failed'):
        corroborate(GithubOpener(error=urllib.error.URLError('down')))


def test_other_http_error_fails_closed_not_retryable():
    with pytest.raises(ValueError, match='lookup failed') as caught:
        corroborate(GithubOpener(status=404))
    assert not isinstance(caught.value, DeliveryCorroborationInconclusive)


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


def test_next_link_in_numeric_repository_form_is_accepted_by_cursor_only():
    link = '<https://api.github.com/repositories/10/hooks/20/deliveries?per_page=100&cursor=v1>; rel="next"'
    opener = PagedOpener([filler(0), [GUID]], link=link)
    assert corroborate(opener) == payload()
    # The link URL itself is never requested; only its cursor is reused on the verified path.
    assert opener.calls[:2] == [f'{BASE}?per_page=100', f'{BASE}?per_page=100&cursor=v1']


@pytest.mark.parametrize('path', [
    '/repositories/11/hooks/20/deliveries',   # other repository ID
    '/repositories/10/hooks/21/deliveries',   # other hook
    '/repositories/10/hooks/20/deliveries/5',
])
def test_next_link_numeric_form_must_match_verified_repository_and_hook(path):
    link = f'<https://api.github.com{path}?cursor=v1>; rel="next"'
    with pytest.raises(ValueError, match='pagination link is malformed'):
        corroborate(PagedOpener([filler(0), [GUID]], link=link))


def test_recent_unlisted_delivery_is_inconclusive_within_grace(monkeypatch):
    import aao.github_delivery_corroboration as module
    monkeypatch.setattr(module.time, 'time', lambda: 1000000)
    recent = payload()
    recent['repository']['pushed_at'] = 1000000 - 30
    with pytest.raises(DeliveryCorroborationInconclusive, match='not listed yet'):
        corroborate(PagedOpener([filler(0)]), candidate=recent)
    old = payload()
    old['repository']['pushed_at'] = 1000000 - module.NOT_FOUND_GRACE_SECONDS - 1
    with pytest.raises(ValueError, match='GUID was not found') as caught:
        corroborate(PagedOpener([filler(0)]), candidate=old)
    assert not isinstance(caught.value, DeliveryCorroborationInconclusive)


@pytest.mark.parametrize('override', [
    {'header_event': 'issues'}, {'detail_event': 'issues'},
    {'header_guid': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'},
])
def test_single_detail_header_or_event_mismatch_fails_closed(override):
    with pytest.raises(ValueError, match='not the configured push webhook event'):
        corroborate(GithubOpener(**override))


def test_single_detail_guid_mismatch_fails_closed():
    with pytest.raises(ValueError, match='detail GUID does not match'):
        corroborate(GithubOpener(detail_guid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'))


def test_fetched_full_name_mismatch_alone_fails_closed():
    fetched = payload()
    fetched['repository']['full_name'] = 'owner/other'
    with pytest.raises(ValueError, match='does not match relayed'):
        corroborate(GithubOpener(fetched=fetched))


def test_relay_full_name_mismatch_alone_fails_closed_before_api_call():
    candidate = payload()
    candidate['repository']['full_name'] = 'owner/other'
    opener = GithubOpener()
    with pytest.raises(ValueError, match='does not match verified repository'):
        corroborate(opener, candidate=candidate)
    assert opener.calls == []


def test_non_200_success_status_fails_closed():
    with pytest.raises(ValueError, match='unexpected status'):
        corroborate(GithubOpener(response_status=201))


def test_oversized_response_fails_closed():
    with pytest.raises(ValueError, match='too large'):
        corroborate(GithubOpener(detail_body=b' ' * (25 * 1024 * 1024 + 1)))


@pytest.mark.parametrize('max_pages', [0, -1, True, '3', 1.5])
def test_invalid_page_bound_fails_closed_before_api_call(max_pages):
    opener = GithubOpener()
    with pytest.raises(ValueError, match='page bound is invalid'):
        corroborate_push_delivery(
            token='independently-provisioned-token', trust=TRUST, delivery_guid=GUID,
            relay_payload=payload(), opener=opener, max_pages=max_pages)
    assert opener.calls == []


def test_non_dict_relay_payload_fails_closed():
    with pytest.raises(TypeError, match='not an object'):
        corroborate(GithubOpener(), candidate=[payload()])
