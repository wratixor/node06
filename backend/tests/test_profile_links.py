"""Two isolated registries: explicit pair approval, PKCE, revocation and no social authority."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import pg_database as database_fixture
from fastapi.testclient import TestClient
from node06_service.config import Settings
from node06_service.main import create_app
from node06_service.models import profile_links, user_geometry, users
from node06_service.profile_links import challenge
from node06_service.public_points import PublicPointError
from sqlalchemy import func, select, update

PASSWORD = "test-profile-links-only"
A, B = "https://alpha.example", "https://beta.example"


@pytest.fixture
def peer_database():
    yield from database_fixture.__wrapped__()


@pytest.fixture
def pair(pg_database, peer_database):
    with ExitStack() as stack:
        nodes = []
        for db, origin, handle in ((pg_database, A, "alice"), (peer_database, B, "bob")):
            app = create_app(
                Settings(
                    management_origin=origin,
                    embed_origin="https://embed.example",
                    registration_per_hour=100,
                )
            )
            app.state.database = db
            client = stack.enter_context(
                TestClient(app, base_url=origin, headers={"Origin": origin})
            )
            created = client.post(
                "/api/v1/auth/register", json={"handle": handle, "password": PASSWORD}
            )
            assert created.status_code == 201, created.text
            login = client.post("/api/v1/auth/login", json={"handle": handle, "password": PASSWORD})
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            machine = stack.enter_context(TestClient(app, base_url=origin))
            nodes.append(
                SimpleNamespace(
                    app=app,
                    db=db,
                    origin=origin,
                    uid=created.json()["user_id"],
                    client=client,
                    machine=machine,
                )
            )

        def transport(origin, op, data):
            node = next(n for n in nodes if n.origin == origin)
            result = node.machine.post("/api/v1/profile-links/" + op, data=data)
            if result.status_code != 200:
                raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)
            return result.json()

        for n in nodes:
            n.app.state.profile_link_transport = transport
        yield nodes


def invitation(pair):
    a, _b = pair
    response = a.client.post("/api/v1/me/profile-links/invite", json={"origin": B})
    assert response.status_code == 200, response.text
    result = response.json()
    return {key: result[key] for key in ("origin", "id", "secret")}


def approval(pair, invite):
    _, b = pair
    preview = b.client.post("/api/v1/me/profile-links/inspect", json=invite)
    assert preview.status_code == 200, preview.text
    result = b.client.post(
        "/api/v1/me/profile-links/approve", json={"invitation": invite, "expected": preview.json()}
    )
    assert result.status_code == 200, result.text
    return {key: value for key, value in result.json().items() if key != "recipient"}


def establish(pair):
    a, _ = pair
    invite = invitation(pair)
    answer = approval(pair, invite)
    assert a.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "pending"
    result = a.client.post("/api/v1/me/profile-links/confirm", json=answer)
    assert result.status_code == 200, result.text
    return invite, answer


def test_complete_pair_with_separate_users_and_no_profile_transfer(pair):
    a, b = pair
    invite, answer = establish(pair)
    for node, peer in ((a, b), (b, a)):
        response = node.client.get("/api/v1/me/profile-links")
        item = response.json()["items"][0]
        assert item["status"] == "active" and item["peer_user_id"] == peer.uid
        assert item["peer_origin"] == peer.origin and response.json()["profile_sync"] is False
        for secret in ("secret", "verifier", "nonce", "digest", "remote_token", "code"):
            assert secret not in response.text
        with node.db.connect() as c:
            assert c.scalar(select(func.count()).select_from(user_geometry)) == 0
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 409
    assert b.client.post("/api/v1/me/profile-links/inspect", json=invite).status_code == 502
    assert (
        a.client.post(f"/api/v1/me/profile-links/{invite['id']}/refresh", json={}).json()[
            "peer_active"
        ]
        is True
    )


@pytest.mark.parametrize("side", [0, 1])
def test_either_account_revokes_without_deleting_settings(pair, side):
    a, b = pair
    invite, _ = establish(pair)
    node = pair[side]
    lid = node.client.get("/api/v1/me/profile-links").json()["items"][0]["id"]
    assert node.client.post(f"/api/v1/me/profile-links/{lid}/revoke", json={}).json()["revoked"]
    if side == 1:
        assert (
            a.client.post(f"/api/v1/me/profile-links/{invite['id']}/refresh", json={}).json()[
                "peer_active"
            ]
            is False
        )
    for n in (a, b):
        assert n.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "revoked"
        assert n.client.get("/api/v1/me").status_code == 200


def test_preview_requires_current_identity_and_explicit_consent(pair):
    a, b = pair
    inv = invitation(pair)
    meta = b.client.post("/api/v1/me/profile-links/inspect", json=inv).json()
    assert b.client.get("/api/v1/me/profile-links").json()["items"] == []
    meta["user_id"] = "u_" + "f" * 32
    assert (
        b.client.post(
            "/api/v1/me/profile-links/approve", json={"invitation": inv, "expected": meta}
        ).status_code
        == 409
    )
    answer = approval(pair, inv)
    for key, value in (("state", secrets.token_urlsafe(32)), ("origin", "https://wrong.example")):
        assert (
            a.client.post(
                "/api/v1/me/profile-links/confirm", json={**answer, key: value}
            ).status_code
            == 409
        )
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 200


def test_pkce_client_redirect_and_replay_are_bound(pair):
    a, b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    with a.db.connect() as c:
        verifier = c.scalar(select(profile_links.c.verifier).where(profile_links.c.id == inv["id"]))
    request = {
        "grant_type": "authorization_code",
        "client_id": A,
        "redirect_uri": A + "/profile-sync/",
        "code": answer["code"],
        "code_verifier": verifier,
    }
    for key, value in (
        ("code_verifier", secrets.token_urlsafe(32)),
        ("client_id", "https://wrong.example"),
        ("redirect_uri", A + "/other/"),
        ("grant_type", "password"),
    ):
        assert (
            b.machine.post("/api/v1/profile-links/token", data={**request, key: value}).status_code
            == 400
        )

    def redeem():
        return b.machine.post("/api/v1/profile-links/token", data=request).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: redeem(), range(2))) == [200, 400]


def test_scope_does_not_authorize_profile_read_login_or_mutation(pair):
    a, b = pair
    establish(pair)
    with a.db.connect() as c:
        token = c.scalar(select(profile_links.c.remote_token))
    assert (
        b.machine.get(
            "/api/v1/me/profile-export", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )
    assert (
        b.machine.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    )
    assert (
        b.machine.post(
            "/api/v1/me/profile-links/invite",
            json={"origin": A},
            headers={"Authorization": "Bearer " + token, "Origin": B},
        ).status_code
        == 401
    )
    assert (
        b.machine.post("/api/v1/profile-links/status", data={"token": token}).json()["active"]
        is True
    )
    with b.db.begin() as c:
        c.execute(update(users).where(users.c.id == b.uid).values(state="disabled"))
    assert (
        b.machine.post("/api/v1/profile-links/status", data={"token": token}).json()["active"]
        is False
    )


def test_expiry_cancel_and_peer_outage(pair):
    a, _b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    with a.db.begin() as c:
        c.execute(
            update(profile_links)
            .where(profile_links.c.id == inv["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 409
    inv, _ = establish(pair)

    def offline(*_):
        raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)

    a.app.state.profile_link_transport = offline
    result = a.client.post(f"/api/v1/me/profile-links/{inv['id']}/revoke", json={})
    assert result.json() == {"revoked": True, "peer_notified": False}
    assert a.client.get("/api/v1/me/profile-links").json()["items"][0]["revocation_pending"]


def test_no_browser_machine_calls_or_embed_private_access(pair):
    a, _ = pair
    inv = invitation(pair)
    assert (
        a.client.post(
            "/api/v1/profile-links/metadata", data={"secret": inv["secret"], "client_id": B}
        ).status_code
        == 403
    )
    for path in (
        "/profile-sync/",
        "/profile-sync/links.js",
        "/api/v1/me/profile-links",
        "/api/v1/profile-links/metadata",
    ):
        response = (
            a.machine.get("https://embed.example" + path)
            if path != "/api/v1/profile-links/metadata"
            else a.machine.post("https://embed.example" + path, data={})
        )
        assert response.status_code == 404
    assert (
        a.client.post(
            "/api/v1/me/profile-links/invite", json={"origin": B}, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        a.machine.post(
            "/api/v1/profile-links/metadata",
            content=b"x" * 4097,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 413
    )
    assert (
        a.machine.post(
            "/api/v1/profile-links/metadata",
            content="secret=a&secret=b",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 400
    )
    assert (
        a.client.post(
            "/api/v1/me/profile-links/invite", json={"origin": "https://127.0.0.1"}
        ).status_code
        == 422
    )
    assert a.client.post("/api/v1/me/profile-links/invite", json={"origin": A}).status_code == 400


def test_lost_response_never_fakes_active_link(pair):
    a, b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    normal = a.app.state.profile_link_transport

    def lost(origin, op, data):
        normal(origin, op, data)
        raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)

    a.app.state.profile_link_transport = lost
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 502
    own = a.client.get("/api/v1/me/profile-links").json()["items"][0]
    assert own["status"] == "revoked"
    # The remote control-only grant may exist; it never reads/applies private profiles.
    assert b.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "active"


def test_wrong_final_subject_cannot_replace_confirmed_pair(pair):
    a, _b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    answer["peer_user_id"] = "u_" + "f" * 32
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 502
    assert a.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "revoked"


def test_pkce_reference_vector():
    assert (
        challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_other_local_account_cannot_steal_invitation(pair):
    a, _ = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    a.client.post("/api/v1/auth/register", json={"handle": "mallory", "password": PASSWORD})
    login = a.client.post("/api/v1/auth/login", json={"handle": "mallory", "password": PASSWORD})
    a.client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 404
    assert a.client.post(f"/api/v1/me/profile-links/{inv['id']}/revoke", json={}).status_code == 404
    assert a.client.get("/api/v1/me/profile-links").json()["items"] == []


def test_profile_link_migrations_roundtrip_preserves_old_users(pair):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import inspect

    a, _ = pair
    invitation(pair)
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": a.db._engine.url.render_as_string(hide_password=False),
    }
    for revision in ("0019_git_sources", "head", "0019_git_sources", "head"):
        direction = "upgrade" if revision == "head" else "downgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        tables = inspect(a.db._engine).get_table_names()
        assert ("profile_links" in tables) == (revision == "head")
        assert ("site_user_blocks" in tables) == (revision == "head")
        with a.db.connect() as c:
            assert c.scalar(select(func.count()).select_from(users).where(users.c.id == a.uid)) == 1


def test_cancel_during_exchange_compensates_known_remote_grant(pair):
    a, b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    normal = a.app.state.profile_link_transport

    def cancel(origin, op, data):
        result = normal(origin, op, data)
        if op == "token":
            response = a.client.post(f"/api/v1/me/profile-links/{inv['id']}/revoke", json={})
            assert response.status_code == 200
        return result

    a.app.state.profile_link_transport = cancel
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 409
    for node in (a, b):
        assert node.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "revoked"


def test_failed_compensation_retains_only_private_retry_credential(pair):
    a, b = pair
    inv = invitation(pair)
    answer = approval(pair, inv)
    answer["peer_user_id"] = "u_" + "f" * 32
    normal = a.app.state.profile_link_transport

    def fail_revoke(origin, op, data):
        if op == "revoke":
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)
        return normal(origin, op, data)

    a.app.state.profile_link_transport = fail_revoke
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 502
    own = a.client.get("/api/v1/me/profile-links")
    assert own.json()["items"][0]["revocation_pending"] is True
    assert "remote_token" not in own.text
    a.app.state.profile_link_transport = normal
    assert a.client.post(f"/api/v1/me/profile-links/{inv['id']}/revoke", json={}).json()[
        "peer_notified"
    ]
    assert b.client.get("/api/v1/me/profile-links").json()["items"][0]["status"] == "revoked"


def test_trusted_local_preview_origin_does_not_relax_outbound_peer_rules(pair):
    from node06_service.profile_links import ProfileLinks

    a, _ = pair
    source = ProfileLinks(a.db, "https://localhost:8846", a.app.state.profile_link_transport)
    issued = source.invite(a.uid, B)
    assert issued["origin"] == "https://localhost:8846"
    assert source.list(a.uid)["items"][0]["status"] == "pending"
    # The network-facing peer schema still rejects private literal/alternate port.
    for peer in ("https://127.0.0.1", "https://beta.example:8846"):
        assert (
            a.client.post("/api/v1/me/profile-links/invite", json={"origin": peer}).status_code
            == 422
        )
