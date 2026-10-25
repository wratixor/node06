"""No redirects/proxies/private-address bypass; bounded pinned link transport."""

import io
import multiprocessing
import time
from types import SimpleNamespace

import pytest
from node06_service import profile_peer
from node06_service.config import Settings
from node06_service.models import verifier_leases
from node06_service.public_points import PublicPointError
from node06_service.site_claims import FetchTarget, ProofFetchError
from sqlalchemy import func, select


class Socket:
    def __init__(self, response):
        self.response = response
        self.sent = None
        self.closed = False

    def sendall(self, data):
        self.sent = data

    def makefile(self, *_args):
        return io.BytesIO(self.response)

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "status,headers,body,valid",
    [
        (200, b"Content-Type: application/json\r\n", b'{"active":true}', True),
        (302, b"Location: https://other.example/\r\n", b"", False),
        (200, b"Content-Type: text/html\r\n", b"{}", False),
        (200, b"Content-Type: application/json\r\n", b'{"active":true,"active":false}', False),
        (200, b"Content-Type: application/json\r\nContent-Length: 999999\r\n", b"{}", False),
        (200, b"Content-Type: application/json\r\n", b"{" * 8193, False),
    ],
)
def test_tls_pinning_and_bounded_response(monkeypatch, status, headers, body, valid):
    sock = Socket(f"HTTP/1.1 {status} Test\r\n".encode() + headers + b"\r\n" + body)
    connects = []
    names = []
    monkeypatch.setattr(
        profile_peer,
        "resolve_public_target",
        lambda _: FetchTarget("https://peer.example", "peer.example", 443, ("8.8.8.8",)),
    )

    def connect(address, timeout):
        connects.append((address, timeout))
        return sock

    def wrap(raw, server_hostname):
        assert raw is sock
        names.append(server_hostname)
        return sock

    monkeypatch.setattr(profile_peer.socket, "create_connection", connect)
    monkeypatch.setattr(
        profile_peer.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    if valid:
        assert profile_peer.fetch("https://peer.example", "status", {"token": "test-token"}) == {
            "active": True
        }
    else:
        with pytest.raises(ValueError):
            profile_peer.fetch("https://peer.example", "status", {"token": "test-token"})
    assert connects == [(("8.8.8.8", 443), 4)] and names == ["peer.example"] and sock.closed
    assert b"Host: peer.example\r\n" in sock.sent and b"Cookie:" not in sock.sent
    assert b"/api/v1/profile-links/status HTTP/1.1" in sock.sent


def test_rebinding_private_dns_rejected_before_connection(monkeypatch):
    monkeypatch.setattr(
        profile_peer.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Private destination must never be contacted")

    monkeypatch.setattr(profile_peer.socket, "create_connection", forbidden)
    with pytest.raises(ProofFetchError):
        profile_peer.fetch("https://peer.example", "metadata", {"secret": "secret"})


def stall(*_args):
    time.sleep(5)


def test_hard_deadline_terminates_child_and_releases_slot(pg_database, monkeypatch):
    before = {p.pid for p in multiprocessing.active_children()}
    monkeypatch.setattr(profile_peer, "_worker", stall)
    started = time.monotonic()
    with pytest.raises(PublicPointError, match="PROFILE_PEER_UNAVAILABLE"):
        profile_peer.exchange(
            pg_database,
            Settings(verifier_seconds=0.1),
            "https://peer.example",
            "status",
            {"token": "test"},
        )
    assert time.monotonic() - started < 3
    assert {p.pid for p in multiprocessing.active_children()} == before
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(verifier_leases)) == 0
