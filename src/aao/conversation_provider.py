"""Opt-in OpenAI-compatible streaming adapter for CEO conversations.

AAO owns the conversation contract and persistence; this module is only a replaceable
transport adapter. It makes no provider call unless all explicit environment settings exist.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def stream_reply(messages: list[dict[str, str]]) -> Iterator[str]:
    endpoint = os.getenv("AAO_CONVERSATION_API_URL", "").strip()
    model = os.getenv("AAO_CONVERSATION_MODEL", "").strip()
    token = os.getenv("AAO_CONVERSATION_API_KEY", "")
    provider = os.getenv("AAO_CONVERSATION_PROVIDER", "").strip()
    if provider != "openai-compatible" or not endpoint or not model or not token:
        raise ProviderUnavailable("PROVIDER_NOT_CONFIGURED", "Conversación con modelo no configurada.")
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
        raise ProviderUnavailable("PROVIDER_HTTP_ERROR", f"Proveedor respondió HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable("PROVIDER_UNAVAILABLE", "No se pudo conectar con el proveedor.") from exc
