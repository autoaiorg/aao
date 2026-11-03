from __future__ import annotations

import json
import os
import socket
import threading
import time

import pytest
import uvicorn

from aao.uvicorn_peercred import (
    PEER_CREDENTIALS_EXTENSION,
    PeerCredH11Protocol,
    read_peer_credentials,
)


def test_read_peer_credentials_uses_kernel_socket_credentials():
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux SO_PEERCRED is unavailable")
    server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = read_peer_credentials(server)
        assert peer == {"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid()}
    finally:
        server.close()
        client.close()


def test_read_peer_credentials_refuses_non_unix_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert read_peer_credentials(sock) is None
    finally:
        sock.close()


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux SO_PEERCRED is unavailable")
def test_uvicorn_unix_listener_adds_unforgeable_scope_extension(tmp_path):
    socket_path = tmp_path / "api.sock"
    observed: list[dict] = []

    async def app(scope, receive, send):
        observed.append(scope.get("extensions", {}).get(PEER_CREDENTIALS_EXTENSION))
        payload = json.dumps(observed[-1]).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    config = uvicorn.Config(
        app,
        uds=str(socket_path),
        http=PeerCredH11Protocol,
        lifespan="off",
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not socket_path.exists() and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert socket_path.exists(), "Uvicorn did not create its Unix socket"

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(3)
            client.connect(str(socket_path))
            client.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\n"
                b"X-AAO-Peer-Uid: 0\r\nConnection: close\r\n\r\n"
            )
            response = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response += chunk
        finally:
            client.close()

        headers, body = response.split(b"\r\n\r\n", 1)
        assert b"200 OK" in headers
        if b"transfer-encoding: chunked" in headers.lower():
            size_end = body.index(b"\r\n")
            size = int(body[:size_end], 16)
            body = body[size_end + 2 : size_end + 2 + size]
        peer = json.loads(body)
        assert peer == {"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid()}
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "Uvicorn test server did not stop"


def test_tcp_listener_never_attests_uid_from_request_headers():
    observed: list[dict | None] = []

    async def app(scope, receive, send):
        observed.append(scope.get("extensions", {}).get(PEER_CREDENTIALS_EXTENSION))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        http=PeerCredH11Protocol,
        lifespan="off",
        log_level="critical",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Uvicorn TCP server did not start"
        sockets = server.servers[0].sockets
        address = sockets[0].getsockname()

        client = socket.create_connection(address, timeout=3)
        try:
            client.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\n"
                b"X-AAO-Peer-Uid: 0\r\nConnection: close\r\n\r\n"
            )
            response = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response += chunk
        finally:
            client.close()

        assert b"200 OK" in response
        assert observed == [None]
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "Uvicorn test server did not stop"
