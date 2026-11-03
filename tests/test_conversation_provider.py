from __future__ import annotations

from importlib import import_module

import pytest
from fastapi.testclient import TestClient

conversation_provider = import_module("aao.conversation_provider")


def test_provider_fails_closed_without_explicit_configuration(monkeypatch):
    for name in ("AAO_CONVERSATION_PROVIDER", "AAO_CONVERSATION_API_URL", "AAO_CONVERSATION_MODEL", "AAO_CONVERSATION_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hello"}]))
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"


def test_provider_streams_only_content_delta_and_ignores_malformed_frames(monkeypatch):
    monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AAO_CONVERSATION_API_URL", "https://provider.invalid/chat/completions")
    monkeypatch.setenv("AAO_CONVERSATION_MODEL", "test-model")
    monkeypatch.setenv("AAO_CONVERSATION_API_KEY", "not-a-real-secret")

    class Response:
        def __enter__(self):
            return iter([
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
                b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
                b'data: malformed\n',
                b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
                b'data: [DONE]\n',
            ])

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(conversation_provider, "urlopen", lambda *_args, **_kwargs: Response())
    assert list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}])) == ["Hello", " world"]


def test_endpoint_metadata_omits_userinfo_query_and_fragment():
    assert conversation_provider.safe_endpoint_metadata(
        "https://user:password@gateway.example/v1/chat?api_key=secret#fragment",
    ) == "https://gateway.example/v1/chat"


def test_provider_http_errors_do_not_echo_credentials(monkeypatch):
    from urllib.error import HTTPError

    secret = "never-log-this-token"
    monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AAO_CONVERSATION_API_URL", "https://provider.invalid/chat")
    monkeypatch.setenv("AAO_CONVERSATION_MODEL", "test-model")
    monkeypatch.setenv("AAO_CONVERSATION_API_KEY", secret)

    def reject(request, **_kwargs):
        assert request.get_header("Authorization") == f"Bearer {secret}"
        raise HTTPError(request.full_url, 401, secret, {}, None)

    monkeypatch.setattr(conversation_provider, "urlopen", reject)
    with pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hello"}]))
    assert secret not in str(error.value)
    assert error.value.code == "PROVIDER_HTTP_ERROR"


def test_unauthorized_conversation_turn_never_invokes_provider(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setenv("AAO_CEO_TOKEN", "test-only-token")
    called = False

    def provider(_messages):
        nonlocal called
        called = True
        yield "must not happen"

    monkeypatch.setattr(conversation_provider, "stream_reply", provider)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/00000000-0000-4000-8000-000000000001/conversations/"
            "00000000-0000-4000-8000-000000000002/turns",
            json={"body": "please answer", "idempotency_key": "00000000-0000-4000-8000-000000000003"},
        )
    assert response.status_code == 403
    assert called is False


def _configure(monkeypatch, endpoint, secret="never-log-this-token"):
    monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AAO_CONVERSATION_API_URL", endpoint)
    monkeypatch.setenv("AAO_CONVERSATION_MODEL", "test-model")
    monkeypatch.setenv("AAO_CONVERSATION_API_KEY", secret)
    return secret


@pytest.mark.parametrize("endpoint", [
    "http://provider.example/v1/chat",
    "http://10.0.0.1/v1/chat",
    "https://user:pass@provider.example/v1/chat",
    "https://user@provider.example/v1/chat",
    "http://user:pass@127.0.0.1/v1/chat",
    "file:///etc/passwd",
    "ftp://provider.example/chat",
    "provider.example/v1/chat",
    "https:///v1/chat",
    "https://provider.example:bad/v1/chat",
    "ftp://127.0.0.1/chat",
    "ftp://localhost/chat",
    "https://provider.example/v1/chat?key=sk-in-query",
    "https://provider.example/v1/chat?",
    "https://provider.example/v1/ch at",
    "https://provider.example/v1/chat\r\nX-Injected: 1",
    "https://provider.example/v1/\tchat",
    "https://provider.example/v1/\x7fchat",
])
def test_rejected_endpoints_never_reach_the_network(monkeypatch, caplog, endpoint):
    secret = _configure(monkeypatch, endpoint)
    monkeypatch.setattr(conversation_provider, "urlopen", lambda *_a, **_k: pytest.fail("network reached"))
    with caplog.at_level("DEBUG"), pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}]))
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"
    assert secret not in str(error.value) and endpoint not in str(error.value)
    assert secret not in caplog.text


@pytest.mark.parametrize("endpoint", [
    "https://provider.example/v1/chat", "http://127.0.0.1:8080/v1/chat",
    "http://[::1]:8080/v1/chat", "http://localhost/v1/chat",
])
def test_https_and_loopback_http_endpoints_are_allowed(monkeypatch, endpoint):
    secret = _configure(monkeypatch, endpoint)
    sent = []

    class Done:
        def __enter__(self):
            return iter([b"data: [DONE]\n"])

        def __exit__(self, *_):
            return False

    def capture(request, **_kwargs):
        sent.append(request)
        return Done()

    monkeypatch.setattr(conversation_provider, "urlopen", capture)
    assert list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}])) == []
    (request,) = sent
    assert request.full_url == endpoint
    # The key travels only in the Authorization header, never in the URL or the body.
    assert request.get_header("Authorization") == f"Bearer {secret}"
    assert secret not in request.full_url and secret.encode() not in request.data


def test_redirect_is_refused_and_the_token_never_follows(monkeypatch, caplog):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    hits = []

    class Target(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST  # urllib would follow a POST 302 as GET, keeping the Authorization header

        def log_message(self, *_args):
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)

    class Redirector(Target):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{target.server_port}/steal")
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirector = HTTPServer(("127.0.0.1", 0), Redirector)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (target, redirector)]
    for thread in threads:
        thread.start()
    try:
        secret = _configure(monkeypatch, f"http://127.0.0.1:{redirector.server_port}/v1/chat")
        with caplog.at_level("DEBUG"), pytest.raises(conversation_provider.ProviderUnavailable) as error:
            list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}]))
    finally:
        for server in (target, redirector):
            server.shutdown()
            server.server_close()
    assert error.value.code == "PROVIDER_HTTP_ERROR"
    assert hits == []
    assert secret not in str(error.value) and secret not in caplog.text


def test_loopback_http_ignores_environment_proxy(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    target_hits = []
    proxy_hits = []

    class Target(BaseHTTPRequestHandler):
        def do_POST(self):
            target_hits.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", len(b"data: [DONE]\\n"))
            self.end_headers()
            self.wfile.write(b"data: [DONE]\\n")

        def log_message(self, *_args):
            pass

    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):
            proxy_hits.append(self.headers.get("Authorization"))
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)
    proxy = HTTPServer(("127.0.0.1", 0), Proxy)
    servers = [target, proxy]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    try:
        secret = _configure(
            monkeypatch,
            f"http://127.0.0.1:{target.server_port}/v1/chat",
        )
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy.server_port}")
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.server_port}")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        assert list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}])) == []
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    assert target_hits == [f"Bearer {secret}"]
    assert proxy_hits == []


@pytest.mark.parametrize("secret", [
    "sk-live\r\nX-Injected: 1", "sk-live\n", "sk-live\r", "sk live", "sk-live\t", "sk-\x01live",
    "sk-\x7flive", "sk-\x1blive", "sk-liv\u00e9", " sk-live",
])
def test_invalid_api_key_is_refused_before_any_request(monkeypatch, caplog, secret):
    _configure(monkeypatch, "https://provider.example/v1/chat", secret)
    monkeypatch.setattr(conversation_provider, "urlopen", lambda *_a, **_k: pytest.fail("network reached"))
    with caplog.at_level("DEBUG"), pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}]))
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"
    assert "sk-" not in str(error.value) and "sk-" not in caplog.text


def _formatted(exc):
    import traceback
    return "".join(traceback.format_exception(exc))


@pytest.mark.parametrize("raised", ["header", "url", "unicode"])
def test_request_value_errors_never_echo_key_or_url(monkeypatch, caplog, raised):
    from http.client import InvalidURL

    endpoint = "https://provider.example/v1/chat"
    secret = _configure(monkeypatch, endpoint)

    def explode(request, **_kwargs):
        if raised == "header":
            raise ValueError(f"Invalid header value {request.get_header('Authorization').encode()!r}")
        if raised == "url":
            raise InvalidURL(f"URL can't contain control characters. {request.full_url!r} {secret}")
        raise UnicodeEncodeError("latin-1", f"Bearer {secret}", 0, 1, "ordinal not in range(256)")

    monkeypatch.setattr(conversation_provider, "urlopen", explode)
    with caplog.at_level("DEBUG"), pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}]))
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert error.value.__cause__ is None and error.value.__suppress_context__
    text = _formatted(error.value)
    assert secret not in text and endpoint not in text and secret not in caplog.text


def test_real_http_client_header_error_is_contained(monkeypatch, caplog):
    """Defence in depth: even if a CR/LF key slipped past validation, http.client's ValueError (which embeds the
    whole header value) is converted before it can reach a 500 traceback. Fails before any connection."""
    secret = "sk-live\r\nX-Injected: 1"
    _configure(monkeypatch, "http://127.0.0.1:9/v1/chat", secret)
    monkeypatch.setattr(conversation_provider, "_visible_ascii", lambda _value: True)
    with caplog.at_level("DEBUG"), pytest.raises(conversation_provider.ProviderUnavailable) as error:
        list(conversation_provider.stream_reply([{"role": "user", "content": "hi"}]))
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    text = _formatted(error.value)
    assert "sk-live" not in text and "sk-live" not in caplog.text
