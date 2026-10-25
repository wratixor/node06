from copy import deepcopy
from uuid import uuid4

import pytest
from node06_service import profile_packet
from node06_service.models import point_hides, social_events, user_geometry
from node06_service.profile_packet import Packet, compare, digest
from pydantic import ValidationError
from sqlalchemy import func, insert, select
from test_authoring import attach, payload, post
from test_authoring import manager as manager_fixture
from test_authoring import static_bundle as bundle_fixture


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database, static_bundle)


def packet():
    value = {
        "format": "node06-profile/1",
        "source": {"origin": "https://a.example", "user_id": "u_" + "1" * 32, "handle": "alice"},
        "coordinates": [128] * 6,
        "subscriptions": [],
        "favorites": [],
        "own_points": [],
    }
    return {**value, "digest": digest(value)}


def signed(value):
    value = deepcopy(value)
    value.pop("digest", None)
    return {**value, "digest": digest(value)}


@pytest.mark.parametrize(
    "field,value",
    [
        ("roles", ["admin"]),
        ("trust", []),
        ("influence", 1),
        ("sessions", []),
        ("coordinates", [True] * 6),
        ("coordinates", [1.0] * 6),
        ("coordinates", [0] * 6),
        ("format", "node06-profile/2"),
    ],
)
def test_forbidden_authority_fields_and_bad_coordinates(field, value):
    with pytest.raises(ValidationError):
        Packet.model_validate(signed({**packet(), field: value}))


@pytest.mark.parametrize(
    "origin",
    [
        "http://a.example",
        "https://alice:secret@a.example",
        "https://a.example/path",
        "https://a.example/#secret",
        "https://a.example?token=x",
        "https://a.example:0",
        "javascript:bad()",
    ],
)
def test_packet_source_is_only_a_bounded_https_origin(origin):
    value = packet()
    value["source"]["origin"] = origin
    with pytest.raises(ValidationError):
        Packet.model_validate(signed(value))


def test_digest_duplicates_limits_and_cross_origin_identity():
    value = packet()
    value["coordinates"][0] = 100
    with pytest.raises(ValidationError):
        Packet.model_validate(value)
    ref = {
        "point_id": "field-ru",
        "revision_id": None,
        "content_digest": "1" * 64,
        "available": True,
    }
    value = packet()
    value["favorites"] = [ref, ref]
    with pytest.raises(ValidationError):
        Packet.model_validate(signed(value))
    value["favorites"] = [{**ref, "point_id": f"p_{i}"} for i in range(129)]
    with pytest.raises(ValidationError):
        Packet.model_validate(signed(value))
    value["favorites"] = [ref]
    local = Packet.model_validate(signed(value))
    value["source"]["origin"] = "https://b.example"
    result = compare(local, Packet.model_validate(signed(value)))
    assert result["applied"] is False and result["verified_identity"] is False
    assert len(result["favorites"]["only_here"]) == len(result["favorites"]["only_in_file"]) == 1
    assert result["favorites"]["different"] == []


def test_private_export_stable_digest_and_compare_have_no_social_effect(
    manager, static_bundle, pg_database
):
    attach(manager, static_bundle)
    client = manager.client
    created = post(client, payload(client, body="Private export must not contain this body")).json()
    pid = created["id"]
    point = client.get("/api/v1/points/" + pid).json()
    headers = {"Idempotency-Key": uuid4().hex}
    assert (
        client.post(
            f"/api/v1/me/favorites/{pid}", json={"active": True}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/points/{pid}/subscription",
            json={
                "revision_id": point["revision_id"],
                "content_digest": point["content_digest"],
                "active": False,
            },
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 200
    )
    result = client.get("/api/v1/me/profile-export")
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    value = result.json()
    assert value == client.get("/api/v1/me/profile-export").json()
    assert value["source"]["user_id"] == manager.user
    assert value["own_points"][0]["point_id"] == pid
    assert value["subscriptions"][0]["active"] is False
    assert "Private export must not contain this body" not in result.text
    for forbidden in ("static_body", "password", "token", "csrf", "roles", "influence", "trust"):
        assert forbidden not in result.text
    with pg_database.connect() as c:
        events = c.scalar(select(func.count()).select_from(social_events))
    response = client.post("/api/v1/me/profile-compare", json=value)
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is False
    assert response.json()["favorites"] == {"only_here": [], "only_in_file": [], "different": []}
    value["coordinates"] = [100, 150, 128, 128, 128, 128]
    assert client.post("/api/v1/me/profile-compare", json=signed(value)).json()["color_changed"]
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(social_events)) == events
        assert (
            c.scalar(
                select(user_geometry.c.coordinates).where(user_geometry.c.user_id == manager.user)
            )
            is None
        )
    assert client.post("/api/v1/me/profile-compare", json=value).status_code == 422


def test_hidden_originals_not_in_public_post_references_and_no_truncation(
    manager, static_bundle, pg_database, monkeypatch
):
    attach(manager, static_bundle)
    pid = post(manager.client, payload(manager.client)).json()["id"]
    with pg_database.begin() as c:
        c.execute(
            insert(point_hides).values(
                scope="server", point_id=pid, active=True, updated_by=manager.user
            )
        )
    assert manager.client.get("/api/v1/me/profile-export").json()["own_points"] == []
    monkeypatch.setattr(profile_packet, "MAX_ITEMS", 0)
    response = manager.client.get("/api/v1/me/profile-export")
    assert response.status_code == 413 and response.json()["code"] == "PROFILE_PACKET_TOO_LARGE"


def test_auth_csrf_origin_embed_and_disabled_profile_guards(manager, static_bundle):
    attach(manager, static_bundle)
    client = manager.client
    value = client.get("/api/v1/me/profile-export").json()
    assert (
        client.post(
            "/api/v1/me/profile-compare", json=value, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/me/profile-export", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/me/profile-export?user_id=other").status_code == 400
    manager.app.state.settings.embed_origin = "https://embed.example"
    assert client.get("https://embed.example/api/v1/me/profile-export").status_code == 404
    assert client.get("https://embed.example/profile-sync/").status_code == 404
    assert client.get("/profile-sync/").status_code == 200
    assert client.get("/profile-sync/client.js").status_code == 200
    assert client.delete("/api/v1/auth/session").status_code == 204
    assert client.get("/api/v1/me/profile-export").status_code == 401
    assert client.post("/api/v1/me/profile-compare", json=value).status_code == 401


def test_full_packet_byte_limit_even_when_each_list_is_bounded():
    ref = {
        "point_id": "p_" + "1" * 93,
        "revision_id": None,
        "content_digest": "1" * 64,
        "available": True,
    }
    refs = [{**ref, "point_id": "p_" + str(i).zfill(93)} for i in range(128)]
    value = packet()
    value["favorites"] = refs
    value["own_points"] = refs
    value["subscriptions"] = [
        {**row, "active": True, "changed_at": "2026-10-25T00:00:00+00:00"} for row in refs
    ]
    with pytest.raises(ValidationError, match="byte budget"):
        Packet.model_validate(signed(value))


def test_other_account_and_disabled_session_cannot_export_original_preferences(
    manager, static_bundle, pg_database
):
    from node06_service.models import users
    from sqlalchemy import update
    from test_site_management import PASSWORD

    attach(manager, static_bundle)
    original = manager.client.get("/api/v1/me/profile-export").json()
    created = manager.auth.register("packet-other", PASSWORD, "packet-fixture")
    login = manager.client.post(
        "/api/v1/auth/login", json={"handle": "packet-other", "password": PASSWORD}
    )
    assert login.status_code == 200
    other = manager.client.get("/api/v1/me/profile-export").json()
    assert other["source"]["user_id"] == created.identity.user_id != original["source"]["user_id"]
    assert other["own_points"] == other["subscriptions"] == other["favorites"] == []
    with pg_database.begin() as c:
        c.execute(
            update(users).where(users.c.id == created.identity.user_id).values(state="disabled")
        )
    assert manager.client.get("/api/v1/me/profile-export").status_code == 401
