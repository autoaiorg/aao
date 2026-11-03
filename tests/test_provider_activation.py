"""Activation path and read-only check, with a loopback fake OpenAI-compatible server (no external network)."""
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from aao.conversation_provider import ProviderUnavailable, stream_reply

KEY = "sk-test-only-SECRET-123456"
ALL = ("AAO_CONVERSATION_PROVIDER", "AAO_CONVERSATION_API_URL", "AAO_CONVERSATION_MODEL",
       "AAO_CONVERSATION_API_KEY", "AAO_AGENT_PROVIDER", "AAO_AGENT_CODEX_HOME",
       "AAO_AGENT_DAILY_BUDGET_USD", "AAO_AGENT_MAX_ATTEMPTS", "AAO_CONVERSATION_RECOVERY_ENABLED")

_spec = importlib.util.spec_from_file_location(
    "check_provider_activation", Path(__file__).parents[1] / "scripts" / "check_provider_activation.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


@pytest.fixture
def fake_provider():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, self.headers["Authorization"], body))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for part in ("Hola", " mundo"):
                chunk = json.dumps({"choices": [{"delta": {"content": part}}]})
                self.wfile.write(f"data: {chunk}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", seen
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL:
        monkeypatch.delenv(name, raising=False)


def _activate(monkeypatch, url):
    monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AAO_CONVERSATION_API_URL", url)
    monkeypatch.setenv("AAO_CONVERSATION_MODEL", "fake-model")
    monkeypatch.setenv("AAO_CONVERSATION_API_KEY", KEY)


def test_activated_conversation_provider_calls_loopback_server(monkeypatch, fake_provider):
    url, seen = fake_provider
    _activate(monkeypatch, url)
    assert "".join(stream_reply([{"role": "user", "content": "hi"}])) == "Hola mundo"
    path, auth, body = seen[0]
    assert (path, auth, body["model"], body["stream"]) == (
        "/v1/chat/completions", f"Bearer {KEY}", "fake-model", True)


def test_unset_variables_refuse_without_calling_server(fake_provider):
    _url, seen = fake_provider
    with pytest.raises(ProviderUnavailable) as error:
        list(stream_reply([{"role": "user", "content": "hi"}]))
    assert error.value.code == "PROVIDER_NOT_CONFIGURED"
    assert seen == []


@pytest.mark.parametrize("missing", ["AAO_CONVERSATION_API_URL", "AAO_CONVERSATION_MODEL",
                                     "AAO_CONVERSATION_API_KEY"])
def test_any_missing_variable_keeps_provider_off(monkeypatch, fake_provider, missing):
    url, seen = fake_provider
    _activate(monkeypatch, url)
    monkeypatch.delenv(missing)
    with pytest.raises(ProviderUnavailable):
        list(stream_reply([]))
    assert seen == []


def test_check_script_off_then_on_never_prints_secret(monkeypatch, fake_provider, capsys, tmp_path):
    url, seen = fake_provider
    assert check.main(["--expect", "off"]) == 0
    off = json.loads(capsys.readouterr().out)
    assert not off["conversation_provider_active"] and not off["codex_backend_would_run"]

    _activate(monkeypatch, url)
    monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")
    monkeypatch.setenv("AAO_AGENT_CODEX_HOME", str(tmp_path))
    assert check.main(["--expect", "on"]) == 0
    captured = capsys.readouterr()
    on = json.loads(captured.out)
    assert on["conversation_provider_active"] and on["codex_backend_would_run"]
    assert on["variables_set"]["AAO_CONVERSATION_API_KEY"] is True
    for text in (captured.out, captured.err):
        assert KEY not in text and url not in text and str(tmp_path) not in text
    assert seen == []  # the check never sends a request


def test_check_script_expect_mismatch_and_partial_codex(monkeypatch, capsys):
    monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")  # no CODEX_HOME: the runner would refuse
    assert check.main(["--expect", "on"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["codex_backend_activated"] and not out["codex_backend_would_run"]
    assert check.main(["--expect", "off"]) == 0
