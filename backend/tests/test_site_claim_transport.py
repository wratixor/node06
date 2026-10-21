"""Real local TLS/HTTP; only DNS and the physical dial destination are controlled."""

import socket
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from node06_service import site_claims


@pytest.fixture
def tls_origin(tmp_path, monkeypatch):
    certificate = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=proof.example",
            "-addext",
            "subjectAltName=DNS:proof.example",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    requests = []
    payload = {"status": 200, "body": b"proof", "length": "5"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("Host")))
            self.send_response(payload["status"])
            if payload["length"] is not None:
                self.send_header("Content-Length", payload["length"])
            if payload["status"] == 302:
                self.send_header("Location", "https://127.0.0.1/private")
            self.end_headers()
            self.wfile.write(payload["body"])

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    create_connection = socket.create_connection
    getaddrinfo = socket.getaddrinfo
    dials = []

    def dial(address, *, timeout):
        dials.append(address)
        assert address == ("8.8.8.8", 443)
        return create_connection(server.server_address, timeout=timeout)

    monkeypatch.setattr(site_claims.socket, "create_connection", dial)

    def resolve(host, port, *args, **kwargs):
        if host in ("proof.example", "wrong.example"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        assert host == "127.0.0.1"
        return getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(site_claims.socket, "getaddrinfo", resolve)
    trusted_context = ssl.create_default_context(cafile=str(certificate))
    monkeypatch.setattr(site_claims.ssl, "create_default_context", lambda: trusted_context)
    try:
        yield payload, requests, dials
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_tls_fetch_uses_fixed_path_host_and_pinned_public_address(tls_origin):
    _payload, requests, dials = tls_origin
    assert site_claims.fetch_proof("https://proof.example") == b"proof"
    assert requests == [(site_claims.PROOF_PATH, "proof.example")]
    assert dials == [("8.8.8.8", 443)]


def test_tls_rejects_wrong_hostname_before_sending_http(tls_origin):
    _payload, requests, _dials = tls_origin
    with pytest.raises(site_claims.ProofFetchError):
        site_claims.fetch_proof("https://wrong.example")
    assert requests == []


@pytest.mark.parametrize(
    ("status", "body", "length"),
    [
        (302, b"", "0"),
        (404, b"", "0"),
        (200, b"", "9000"),
        (200, b"x" * 8193, None),
        (200, b"", "-1"),
        (200, b"", "invalid"),
    ],
    ids=["redirect", "not-found", "large-length", "large-stream", "negative-length", "bad-length"],
)
def test_http_redirects_errors_and_oversized_bodies_are_rejected(tls_origin, status, body, length):
    payload, requests, dials = tls_origin
    payload.update(status=status, body=body, length=length)
    with pytest.raises(site_claims.ProofFetchError):
        site_claims.fetch_proof("https://proof.example")
    assert len(requests) == len(dials) == 1


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "ff02::1"])
def test_mixed_public_private_dns_answers_fail_before_any_connection(monkeypatch, address):
    monkeypatch.setattr(
        site_claims.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("8.8.8.8", address)
        ],
    )
    monkeypatch.setattr(
        site_claims.socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("Unsafe DNS results must not open sockets"),
    )
    with pytest.raises(site_claims.ProofFetchError):
        site_claims.fetch_proof("https://proof.example")
