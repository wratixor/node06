"""Pinned public HTTPS, bounded response and hard DNS/body deadline for link control."""

import http.client
import json
import multiprocessing
import os
import signal
import socket
import ssl
from urllib.parse import urlencode

from .public_points import PublicPointError
from .site_claims import SiteClaimError, resolve_public_target
from .verifier import ProofVerifier

PATHS = {"metadata", "token", "status", "revoke", "metadata-data", "token-data", "sync"}
MAX_BYTES = 8192


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate peer JSON field")
        result[key] = value
    return result


def fetch(origin, operation, fields):
    if operation not in PATHS:
        raise ValueError("Unknown link operation")
    target = resolve_public_target(origin)
    # A single pinned address: no retry to another destination after sending a secret.
    raw = socket.create_connection((target.addresses[0], 443), timeout=4)
    tls = None
    try:
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=target.hostname)
        body = urlencode(fields).encode("ascii")
        if len(body) > (65536 if operation == "sync" else 4096):
            raise ValueError("Request exceeds bound")
        host = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
        headers = (
            f"POST /api/v1/profile-links/{operation} HTTP/1.1\r\nHost: {host}\r\n"
            "User-Agent: node06-profile-links/1\r\nAccept: application/json\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        )
        tls.sendall(headers.encode("ascii") + body)
        with http.client.HTTPResponse(tls) as response:
            response.begin()
            if response.status != 200:
                raise ValueError("Peer rejected operation")
            if response.getheader("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("Peer response is not JSON")
            length = response.getheader("Content-Length")
            maximum = 60000 if operation == "sync" else MAX_BYTES
            if length is not None and not 0 <= int(length) <= maximum:
                raise ValueError("Peer response exceeds bound")
            result = response.read(maximum + 1)
            if len(result) > maximum:
                raise ValueError("Peer response exceeds bound")
            return json.loads(result, object_pairs_hook=unique_object)
    finally:
        if tls:
            tls.close()
        raw.close()


def _timeout(_signal, _frame):
    os._exit(124)


def _worker(sender, origin, operation, fields, seconds):
    if hasattr(signal, "setitimer"):
        signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        sender.send((True, fetch(origin, operation, fields)))
    except (SiteClaimError, OSError, ValueError, RecursionError, http.client.HTTPException):
        sender.send((False, None))
    finally:
        sender.close()


def exchange(database, settings, origin, operation, fields):
    verifier = ProofVerifier(database, settings)
    lease = verifier.acquire()
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker,
        args=(sender, origin, operation, fields, settings.verifier_seconds),
        daemon=True,
    )
    try:
        try:
            process.start()
        except (OSError, RuntimeError):
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502) from None
        sender.close()
        if not receiver.poll(settings.verifier_seconds):
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)
        try:
            ok, data = receiver.recv()
        except EOFError:
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502) from None
        if not ok:
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)
        return data
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        verifier.release(lease)
