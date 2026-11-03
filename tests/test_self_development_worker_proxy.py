import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aao import inert_execution_worker
from scripts import run_self_development_worker as worker


def test_worker_api_clients_ignore_configured_proxy_and_keep_token_on_api(monkeypatch):
    observed = {"api": [], "proxy": []}

    class ApiHandler(BaseHTTPRequestHandler):
        def _respond(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            observed["api"].append((self.path, self.headers.get("X-Agent-Token")))
            self._respond({"principal_id": "aao-selfdev-impl-test", "kind": "AGENT",
                           "enabled": True})

        def do_POST(self):
            observed["api"].append((self.path, self.headers.get("X-Agent-Token")))
            if self.path.endswith("dispatch-next"):
                payload = {"status": "QUEUED", "execution_id": "exec-1", "work_id": "work-1"}
            else:
                payload = {"status": "IDLE"}
            self._respond(payload)

        def log_message(self, *_args):
            pass

    class ProxyHandler(BaseHTTPRequestHandler):
        def _record(self):
            observed["proxy"].append((self.path, self.headers.get("X-Agent-Token")))
            self.send_response(502)
            self.end_headers()

        do_GET = _record
        do_POST = _record

        def log_message(self, *_args):
            pass

    api = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    for server in (api, proxy):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.setenv(name, "")
        for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                     "all_proxy", "ALL_PROXY"):
            monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_port}")
        # Ensure urllib's implicit localhost bypass cannot hide proxy-aware code.
        monkeypatch.setattr("urllib.request.proxy_bypass", lambda _host: False)
        monkeypatch.setenv("AAO_API_BASE_URL", f"http://127.0.0.1:{api.server_port}")
        monkeypatch.setattr(worker, "_read_agent_token", lambda: "worker-secret")

        assert inert_execution_worker._api_request(
            "/v1/agent/executions/claim", "inert-secret", body={}
        ) == {"status": "IDLE"}
        assert worker.dispatch_next("project-1", None, "a" * 40) == {
            "status": "QUEUED", "execution_id": "exec-1", "work_id": "work-1",
        }
    finally:
        for server in (api, proxy):
            server.shutdown()
            server.server_close()

    assert observed == {
        "api": [
            ("/v1/agent/executions/claim", "inert-secret"),
            ("/v1/principals/me", "worker-secret"),
            ("/v1/agent/dispatch-next", "worker-secret"),
        ],
        "proxy": [],
    }
