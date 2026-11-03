"""Opt-in OpenAI-compatible streaming adapter for CEO conversations.

AAO owns the conversation contract and persistence; this module is only a replaceable
transport adapter. Setting any ``AAO_CONVERSATION_*`` provider configuration activates
a model provider and is reserved to the CEO. Those settings are currently not configured.
It makes no provider call unless all explicit environment settings exist.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class _RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # the 3xx surfaces as HTTPError; the bearer token never follows a redirect


_OPENER = build_opener(_RefuseRedirects())


def urlopen(request, timeout):
    """The only network seam (tests and the activation check replace it); redirects are refused."""
    return _OPENER.open(request, timeout=timeout)


def endpoint_allowed(endpoint: str) -> bool:
    """https only (http just for loopback fakes), no userinfo: the bearer token must not travel in clear."""
    try:
        parsed = urlsplit(endpoint)
        host, _port = parsed.hostname, parsed.port  # .port raises ValueError when malformed
    except ValueError:
        return False
    if not host or parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return False
    return parsed.scheme == "https" or (parsed.scheme == "http" and host in _LOOPBACK_HOSTS)


class ProviderUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def safe_endpoint_metadata(endpoint: str) -> str:
    """Return endpoint provenance without userinfo, query parameters, or fragments."""
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return "configured-endpoint"
    if not parsed.scheme or not host:
        return "configured-endpoint"
    if port is not None:
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def stream_reply(messages: list[dict[str, str]]) -> Iterator[str]:
    endpoint = os.getenv("AAO_CONVERSATION_API_URL", "").strip()
    model = os.getenv("AAO_CONVERSATION_MODEL", "").strip()
    token = os.getenv("AAO_CONVERSATION_API_KEY", "")
    provider = os.getenv("AAO_CONVERSATION_PROVIDER", "").strip()
    if provider != "openai-compatible" or not endpoint or not model or not token:
        raise ProviderUnavailable("PROVIDER_NOT_CONFIGURED", "Conversación con modelo no configurada.")
    if not endpoint_allowed(endpoint):
        # Same code as "not configured": nothing is sent. The message never echoes the URL or the key.
        raise ProviderUnavailable("PROVIDER_NOT_CONFIGURED",
                                  "Endpoint del proveedor rechazado: se requiere https sin credenciales en la URL.")
    body = json.dumps({"model": model, "messages": messages, "stream": True}).encode()
    request = Request(endpoint, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "Accept": "text/event-stream",
    })
    try:
        with urlopen(request, timeout=60) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError, TypeError):
                    continue
                if isinstance(chunk, str) and chunk:
                    yield chunk
    except HTTPError as exc:
        exc.close()  # also a refused redirect: its body is never read
        raise ProviderUnavailable("PROVIDER_HTTP_ERROR", f"Proveedor respondió HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable("PROVIDER_UNAVAILABLE", "No se pudo conectar con el proveedor.") from exc
