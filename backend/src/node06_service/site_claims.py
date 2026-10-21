from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import secrets
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

PROOF_PATH = "/node06-verification.txt"
PROOF_VERSION = "NODE06-SITE-VERIFICATION-V1"
MAX_PROOF_BYTES = 8 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_CLAIM_LIFETIME = timedelta(minutes=30)


class SiteClaimError(ValueError):
    code = "SITE_CLAIM_INVALID"


class OriginError(SiteClaimError):
    code = "ORIGIN_INVALID"


class ProofFetchError(SiteClaimError):
    code = "PROOF_FETCH_FAILED"


class ProofMismatchError(SiteClaimError):
    code = "PROOF_MISMATCH"


@dataclass(frozen=True)
class ClaimMaterial:
    token: str
    digest: str
    document: str
    expires_at: datetime


@dataclass(frozen=True)
class FetchTarget:
    origin: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def normalize_origin(value: str) -> str:
    raw = value.strip()
    if any(ord(char) <= 32 or ord(char) == 127 for char in raw):
        raise OriginError("Whitespace and control characters are not allowed in an origin.")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise OriginError("Origin URL is invalid.") from exc
    if parts.scheme.lower() != "https":
        raise OriginError("Only HTTPS origins are accepted.")
    if parts.username or parts.password:
        raise OriginError("Credentials are not allowed in an origin.")
    if parts.query or parts.fragment or parts.path not in ("", "/"):
        raise OriginError("Claim an origin, not a URL path/query/fragment.")
    if not parts.hostname:
        raise OriginError("Origin hostname is required.")
    try:
        hostname = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise OriginError("Origin hostname is not valid IDNA.") from exc
    if not hostname or len(hostname) > 253 or "%" in hostname:
        raise OriginError("Origin hostname is invalid.")
    try:
        port = parts.port
    except ValueError as exc:
        raise OriginError("Origin port is invalid.") from exc
    if port not in (None, 443):
        raise OriginError("Only the standard HTTPS port is accepted for site claims.")
    if _looks_like_ip_literal(hostname):
        address = ipaddress.ip_address(hostname)
        if not _is_public_address(address):
            raise OriginError("Private, reserved, loopback and link-local origins are rejected.")
    elif not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in hostname.split(".")
    ):
        raise OriginError("Origin hostname contains invalid DNS labels.")
    netloc = hostname
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    return urlunsplit(("https", netloc, "", "", ""))


def issue_claim(site_id: str, now: datetime | None = None) -> ClaimMaterial:
    issued_at = now or datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    document = f"{PROOF_VERSION}\nsite={site_id}\nnonce={token}\n"
    return ClaimMaterial(
        token=token,
        digest=digest,
        document=document,
        expires_at=issued_at + DEFAULT_CLAIM_LIFETIME,
    )


def validate_proof_document(document: bytes, site_id: str, expected_digest: str) -> None:
    if len(document) > MAX_PROOF_BYTES:
        raise ProofMismatchError("Verification file is too large.")
    try:
        text = document.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProofMismatchError("Verification file must be UTF-8 text.") from exc
    lines = text.splitlines()
    if len(lines) != 3 or lines[0] != PROOF_VERSION:
        raise ProofMismatchError("Verification file version/shape is invalid.")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if "=" not in line:
            raise ProofMismatchError("Verification file field is invalid.")
        key, value = line.split("=", 1)
        fields[key] = value
    if fields.get("site") != site_id:
        raise ProofMismatchError("Verification file belongs to a different site.")
    nonce = fields.get("nonce")
    if not nonce:
        raise ProofMismatchError("Verification nonce is missing.")
    actual = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(actual, expected_digest):
        raise ProofMismatchError("Verification nonce does not match the active claim.")


def resolve_public_target(origin: str) -> FetchTarget:
    normalized = normalize_origin(origin)
    hostname = urlsplit(normalized).hostname
    assert hostname is not None
    try:
        answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProofFetchError("Origin DNS resolution failed.") from exc
    addresses: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in answers:
        address = sockaddr[0]
        parsed = ipaddress.ip_address(address)
        if not _is_public_address(parsed):
            raise ProofFetchError(
                "Origin resolved to a private, reserved, loopback or link-local address."
            )
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ProofFetchError("Origin DNS resolution returned no usable addresses.")
    return FetchTarget(normalized, hostname, 443, tuple(addresses))


def fetch_proof(origin: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    target = resolve_public_target(origin)
    last_error: Exception | None = None
    for address in target.addresses:
        try:
            return _fetch_from_address(target.hostname, address, target.port, timeout)
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
    raise ProofFetchError("Unable to retrieve the verification file.") from last_error


def _fetch_from_address(hostname: str, address: str, port: int, timeout: float) -> bytes:
    raw = socket.create_connection((address, port), timeout=timeout)
    tls = None
    try:
        context = ssl.create_default_context()
        tls = context.wrap_socket(raw, server_hostname=hostname)
        host_header = f"[{hostname}]" if ":" in hostname else hostname
        request = (
            f"GET {PROOF_PATH} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "User-Agent: node06-site-verifier/1\r\n"
            "Accept: text/plain\r\n"
            "Connection: close\r\n\r\n"
        )
        tls.sendall(request.encode("ascii"))
        with http.client.HTTPResponse(tls) as connection:
            connection.begin()
            if 300 <= connection.status < 400:
                raise ProofFetchError("Verification redirects are not accepted.")
            if connection.status != 200:
                raise ProofFetchError(f"Verification endpoint returned HTTP {connection.status}.")
            length = connection.getheader("Content-Length")
            if length is not None:
                try:
                    if not 0 <= int(length) <= MAX_PROOF_BYTES:
                        raise ProofFetchError("Verification file length is out of bounds.")
                except ValueError as exc:
                    raise ProofFetchError("Verification Content-Length is invalid.") from exc
            body = connection.read(MAX_PROOF_BYTES + 1)
            if len(body) > MAX_PROOF_BYTES:
                raise ProofFetchError("Verification file is too large.")
            return body
    finally:
        if tls is not None:
            tls.close()
        raw.close()


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not address.is_multicast and not address.is_reserved


def _looks_like_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True
