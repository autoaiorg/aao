from __future__ import annotations

import hashlib
import socket
import ssl
import subprocess
import threading
import time

import pytest
import uvicorn

from aao.uvicorn_mtls import (
    MTLS_CLIENT_CERT_EXTENSION,
    MtlsH11Protocol,
    verified_peer_fingerprint,
)


def _openssl(*args: str) -> None:
    subprocess.run(
        ["openssl", *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def test_certificates(tmp_path):
    """Create an ephemeral local CA and separate server/client certificates."""
    if not shutil_which("openssl"):
        pytest.skip("openssl is required for the local TLS integration test")

    ca_key = tmp_path / "ca.key"
    ca_cert = tmp_path / "ca.pem"
    server_key = tmp_path / "server.key"
    server_csr = tmp_path / "server.csr"
    server_cert = tmp_path / "server.pem"
    client_key = tmp_path / "client.key"
    client_csr = tmp_path / "client.csr"
    client_cert = tmp_path / "client.pem"
    server_ext = tmp_path / "server.ext"
    client_ext = tmp_path / "client.ext"

    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=AAO test CA",
        "-keyout",
        str(ca_key),
        "-out",
        str(ca_cert),
    )
    for name, key, csr in (
        ("AAO test server", server_key, server_csr),
        ("AAO test workload", client_key, client_csr),
    ):
        _openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            f"/CN={name}",
            "-keyout",
            str(key),
            "-out",
            str(csr),
        )

    server_ext.write_text(
        "subjectAltName=IP:127.0.0.1\n"
        "extendedKeyUsage=serverAuth\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
    )
    client_ext.write_text(
        "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
    )
    for csr, cert, ext in (
        (server_csr, server_cert, server_ext),
        (client_csr, client_cert, client_ext),
    ):
        _openssl(
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            str(ext),
            "-out",
            str(cert),
        )

    return {
        "ca": ca_cert,
        "server_cert": server_cert,
        "server_key": server_key,
        "client_cert": client_cert,
        "client_key": client_key,
    }


def shutil_which(program: str) -> str | None:
    # Keep the test independent of shell invocation and avoid printing paths.
    import shutil

    return shutil.which(program)


def _start_server(app, *, ssl_options=None):
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        http=MtlsH11Protocol,
        lifespan="off",
        log_level="critical",
        **(ssl_options or {}),
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Uvicorn did not start"
    return server, thread, server.servers[0].sockets[0].getsockname()


def _stop_server(server, thread):
    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive(), "Uvicorn test server did not stop"


def test_verified_peer_fingerprint_hashes_der_certificate():
    certificate = b"test-certificate-der"

    class TlsPeer:
        def getpeercert(self, *, binary_form):
            assert binary_form is True
            return certificate

    assert verified_peer_fingerprint(TlsPeer()) == hashlib.sha256(certificate).hexdigest()
    assert verified_peer_fingerprint(None) is None


def test_mtls_listener_attaches_fingerprint_only_from_verified_tls_peer(
    test_certificates,
):
    scopes = []

    async def app(scope, receive, send):
        scopes.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    certs = test_certificates
    server, thread, address = _start_server(
        app,
        ssl_options={
            "ssl_certfile": str(certs["server_cert"]),
            "ssl_keyfile": str(certs["server_key"]),
            "ssl_ca_certs": str(certs["ca"]),
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
        },
    )
    client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(certs["ca"]))
    client_context.load_cert_chain(str(certs["client_cert"]), str(certs["client_key"]))
    try:
        with (
            socket.create_connection(address, timeout=3) as raw,
            client_context.wrap_socket(raw, server_hostname="127.0.0.1") as client,
        ):
            client.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\n"
                b"X-AAO-Peer-Uid: 0\r\nX-AAO-Principal: ceo\r\n"
                b"Connection: close\r\n\r\n"
            )
            response = b""
            while chunk := client.recv(4096):
                response += chunk

        assert b"200 OK" in response
        assert len(scopes) == 1
        fingerprint = scopes[0]["extensions"][MTLS_CLIENT_CERT_EXTENSION]["sha256"]
        client_der = subprocess.run(
            ["openssl", "x509", "-in", str(certs["client_cert"]), "-outform", "DER"],
            check=True,
            capture_output=True,
        ).stdout
        assert fingerprint == hashlib.sha256(client_der).hexdigest()
        assert scopes[0]["headers"]
        assert dict(scopes[0]["headers"])[b"x-aao-peer-uid"] == b"0"
        assert dict(scopes[0]["headers"])[b"x-aao-principal"] == b"ceo"
    finally:
        _stop_server(server, thread)


def test_mtls_listener_rejects_client_without_certificate(test_certificates):
    scopes = []

    async def app(scope, receive, send):
        scopes.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"unexpected"})

    certs = test_certificates
    server, thread, address = _start_server(
        app,
        ssl_options={
            "ssl_certfile": str(certs["server_cert"]),
            "ssl_keyfile": str(certs["server_key"]),
            "ssl_ca_certs": str(certs["ca"]),
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
        },
    )
    client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(certs["ca"]))
    try:
        with socket.create_connection(address, timeout=3) as raw:
            try:
                with client_context.wrap_socket(raw, server_hostname="127.0.0.1") as client:
                    client.sendall(
                        b"GET / HTTP/1.1\r\nHost: localhost\r\n"
                        b"X-AAO-Principal: ceo\r\nConnection: close\r\n\r\n"
                    )
                    response = client.recv(4096)
            except (ssl.SSLError, OSError):
                # TLS stacks may report a missing required certificate either
                # during the handshake or on the first read/write afterwards.
                response = b""
        assert b"200 OK" not in response
        assert scopes == []
    finally:
        _stop_server(server, thread)
