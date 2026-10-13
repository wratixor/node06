from datetime import UTC, datetime, timedelta

import pytest
from node06_service.site_claims import (
    OriginError,
    ProofMismatchError,
    issue_claim,
    normalize_origin,
    validate_proof_document,
)


def test_normalize_origin_accepts_https_root_and_lowercases_idna_ascii() -> None:
    assert normalize_origin("https://NODE06.neocities.org/") == "https://node06.neocities.org"


@pytest.mark.parametrize(
    "origin",
    [
        "http://node06.neocities.org",
        "https://node06.neocities.org/path",
        "https://user:pass@node06.neocities.org",
        "https://127.0.0.1",
        "https://[::1]",
        "https://node06.neocities.org:8443",
    ],
)
def test_normalize_origin_rejects_non_origin_or_private_targets(origin: str) -> None:
    with pytest.raises(OriginError):
        normalize_origin(origin)


def test_claim_document_roundtrip_and_wrong_site_rejected() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    material = issue_claim("s_" + "a" * 32, now)
    assert material.expires_at == now + timedelta(minutes=30)
    validate_proof_document(material.document.encode("utf-8"), "s_" + "a" * 32, material.digest)
    with pytest.raises(ProofMismatchError):
        validate_proof_document(material.document.encode("utf-8"), "s_" + "b" * 32, material.digest)
