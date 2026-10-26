"""Cookie-independent least-authority subscription grants, real PostgreSQL transactions."""

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from node06_service.models import embed_subscriptions as grants
from node06_service.models import sessions, sites, social_events, subscriptions, user_trust, users
from node06_service.profile_links import challenge
from node06_service.site_registry import SiteRegistry
from sqlalchemy import func, select, update
from test_authoring import attach
from test_authoring import static_bundle as static_bundle_fixture
from test_site_management import ORIGIN
from test_site_management import manager as manager_fixture

manager = manager_fixture
static_bundle = static_bundle_fixture
EMBED = "https://embed.example"
PARENT = "https://garden.example"


@pytest.fixture
def access(manager, static_bundle):
    attach(manager, static_bundle)
    manager.app.state.settings.embed_origin = EMBED
    registry = SiteRegistry(manager.app.state.database)
    site = registry.create_pending_site(
        owner_user_id=manager.user, origin=PARENT, welcome_body="Garden"
    )
    registry.verify_site(
        site.site_id,
        actor_user_id=manager.user,
        proof_fetcher=lambda _: site.proof_document.encode(),
    )
    with TestClient(manager.app, base_url=EMBED, headers={"Origin": EMBED}) as peer:
        yield SimpleNamespace(
            owner=manager,
            peer=peer,
            db=manager.app.state.database,
            sid=site.site_id,
            prefix=f"/bridge/v1/{site.site_id}/subscriptions/",
        )


def prepare(a):
    verifier = secrets.token_urlsafe(32)
    payload = {"parent_origin": PARENT, "challenge": challenge(verifier), "state": uuid4().hex}
    r = a.peer.post(a.prefix + "prepare", json=payload)
    assert r.status_code == 200, r.text
    return {**r.json(), "verifier": verifier, "parent_origin": PARENT}


def approve(a, request, action="approve"):
    r = a.owner.client.post("/embed-subscriptions/" + request["id"] + "/" + action, json={})
    assert r.status_code == 200, r.text
    return {**request, "code": r.json()["code"]}


def redeem(a, request):
    r = a.peer.post(a.prefix + "redeem", json=request)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def established(a):
    return redeem(a, approve(a, prepare(a)))


def read(a, token, pid="skills-ru"):
    return a.peer.post(
        a.prefix + "read",
        json={"parent_origin": PARENT, "point_id": pid},
        headers={"Authorization": "Bearer " + token},
    )


def change(a, token, active=True, key=None):
    pin = a.owner.client.get("/api/v1/points/skills-ru").json()
    return a.peer.post(
        a.prefix + "set",
        json={
            "parent_origin": PARENT,
            "point_id": "skills-ru",
            "key": key or uuid4().hex,
            "subscription": {
                "active": active,
                "revision_id": pin["revision_id"],
                "content_digest": pin["content_digest"],
            },
        },
        headers={"Authorization": "Bearer " + token},
    )


def test_shared_session_subscription_read_write_and_idempotent_receipt(access):
    a = access
    request = prepare(a)
    before = a.owner.client.get("/api/v1/me/subscriptions/skills-ru").json()["subscription"]
    page = a.owner.client.get("/embed-subscriptions/" + request["id"] + "/")
    assert page.status_code == 200 and "15 минут" not in page.text
    assert "access-allow" not in page.text and "Разрешить" not in page.text
    assert page.headers["x-frame-options"] == "DENY"
    assert a.owner.client.get("/api/v1/me/subscriptions/skills-ru").json()["subscription"] == before
    assert (
        a.owner.client.post(
            "/embed-subscriptions/" + request["id"] + "/resume", json={}
        ).status_code
        == 409
    )
    token = redeem(a, approve(a, request))
    with a.db.connect() as c:
        row = c.execute(select(grants)).mappings().one()
        native_expiry = c.scalar(
            select(sessions.c.expires_at).where(sessions.c.digest == row["session_digest"])
        )
        assert row["approved_until"] == native_expiry
    initial_read = read(a, token)
    assert initial_read.status_code == 200, initial_read.text
    assert initial_read.json()["subscription"] is None
    key = uuid4().hex
    first = change(a, token, key=key)
    assert first.status_code == 200, first.text
    assert change(a, token, key=key).json() == first.json()
    assert read(a, token).json()["subscription"]["active"] is True
    assert change(a, token, False).status_code == 200
    assert read(a, token).json()["subscription"]["active"] is False
    assert token not in read(a, token).text and a.owner.user not in read(a, token).text
    with a.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(user_trust)) == 0
        assert (
            c.scalar(
                select(func.count())
                .select_from(social_events)
                .where(social_events.c.kind == "subscribed")
            )
            <= 1
        )
        assert c.scalar(select(func.count()).select_from(users)) == 1


def test_pkce_code_state_exact_site_origin_and_single_use(access):
    a = access
    request = approve(a, prepare(a))
    for field, value in [
        ("verifier", secrets.token_urlsafe(32)),
        ("state", uuid4().hex),
        ("parent_origin", "https://evil.example"),
    ]:
        assert a.peer.post(a.prefix + "redeem", json={**request, field: value}).status_code == 401
    token = redeem(a, request)
    assert a.peer.post(a.prefix + "redeem", json=request).status_code == 401
    assert (
        a.peer.post(
            a.prefix + "read",
            json={"parent_origin": "https://evil.example", "point_id": "skills-ru"},
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 401
    )
    assert a.peer.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code == 404
    assert (
        a.owner.client.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code
        == 200
    )  # its real cookie only
    with TestClient(a.owner.app, base_url=ORIGIN) as guest:
        assert (
            guest.get("/api/v1/me", headers={"Authorization": "Bearer " + token}).status_code == 401
        )
        assert (
            guest.post("/embed-subscriptions/" + request["id"] + "/approve", json={}).status_code
            == 403
        )


@pytest.mark.parametrize(
    "invalidate", ["logout", "disabled", "site", "origin", "expired", "revoked"]
)
def test_every_private_operation_rechecks_authority(access, invalidate):
    a = access
    token = established(a)
    with a.db.begin() as c:
        if invalidate == "logout":
            c.execute(update(sessions).values(revoked_at=datetime.now(UTC)))
        elif invalidate == "disabled":
            c.execute(update(users).values(state="disabled"))
        elif invalidate == "site":
            c.execute(update(sites).where(sites.c.id == a.sid).values(state="inactive"))
        elif invalidate == "origin":
            c.execute(
                update(sites)
                .where(sites.c.id == a.sid)
                .values(primary_origin="https://other.example")
            )
        elif invalidate == "expired":
            c.execute(
                update(grants).values(approved_until=datetime.now(UTC) - timedelta(seconds=1))
            )
        else:
            c.execute(update(grants).values(revoked=True))
    assert read(a, token).status_code in (401, 403)
    assert change(a, token).status_code in (401, 403)
    with a.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(subscriptions)) == 0


def test_resume_uses_existing_consent_without_extending_deadline_and_revoke(access):
    a = access
    established(a)
    with a.db.connect() as c:
        expiry = c.scalar(select(grants.c.approved_until))
    request = prepare(a)
    assert (
        a.owner.client.get("/embed-subscriptions/" + request["id"] + "/info").json()["can_resume"]
        is True
    )
    token = redeem(a, approve(a, request, "resume"))
    with a.db.connect() as c:
        assert (
            c.scalar(select(grants.c.approved_until).where(grants.c.id == request["id"])) == expiry
        )
    assert read(a, token).status_code == 200
    assert (
        a.owner.client.post(
            "/embed-subscriptions/" + request["id"] + "/revoke", json={}
        ).status_code
        == 200
    )
    assert read(a, token).status_code == 401
    next_request = prepare(a)
    assert (
        a.owner.client.post(
            "/embed-subscriptions/" + next_request["id"] + "/resume", json={}
        ).status_code
        == 409
    )


def test_rejects_unknown_fields_cookies_wrong_origins_and_stale_revision(access):
    a = access
    request = prepare(a)
    assert (
        a.owner.client.post(
            "/embed-subscriptions/" + request["id"] + "/approve",
            json={},
            headers={"X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    token = redeem(a, approve(a, request))
    headers = {"Authorization": "Bearer " + token}
    body = {"parent_origin": PARENT, "point_id": "skills-ru"}
    assert (
        a.peer.post(
            a.prefix + "read", json={**body, "user_id": a.owner.user}, headers=headers
        ).status_code
        == 422
    )
    assert (
        a.peer.post(
            a.prefix + "read", json=body, headers={**headers, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        a.peer.post(
            a.prefix + "read", json=body, headers={**headers, "Cookie": "fake=1"}
        ).status_code
        == 403
    )
    payload = {
        "parent_origin": PARENT,
        "point_id": "skills-ru",
        "key": uuid4().hex,
        "subscription": {"active": True, "revision_id": None, "content_digest": "f" * 64},
    }
    assert a.peer.post(a.prefix + "set", json=payload, headers=headers).status_code == 409
    assert (
        a.peer.post(
            a.prefix + "set", json={**payload, "kind": "trust"}, headers=headers
        ).status_code
        == 422
    )


def test_partitioned_cookie_is_scoped_httponly_and_memory_fallback_needs_no_cookie(access):
    a = access
    request = approve(a, prepare(a))
    r = a.peer.post(a.prefix + "redeem", json=request)
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"]
    for attr in ("HttpOnly", "Secure", "SameSite=none", "Partitioned", "Path=" + a.prefix):
        assert attr in cookie
    # Cookie-only restoration is allowed solely from the embed origin, never a parent request.
    assert (
        a.peer.post(
            a.prefix + "read", json={"parent_origin": PARENT, "point_id": "skills-ru"}
        ).status_code
        == 200
    )
    assert (
        a.peer.post(
            a.prefix + "read",
            json={"parent_origin": PARENT, "point_id": "skills-ru"},
            headers={"Origin": PARENT},
        ).status_code
        == 403
    )
    token = r.json()["token"]
    a.peer.cookies.clear()
    assert read(a, token).status_code == 200
    assert (
        a.peer.post(
            a.prefix + "read", json={"parent_origin": PARENT, "point_id": "skills-ru"}
        ).status_code
        == 401
    )
    assert a.owner.client.post("/api/v1/me/embed-subscriptions/revoke", json={}).status_code == 200
    assert read(a, token).status_code == 401


def test_expired_code_and_concurrent_redeem(access):
    from concurrent.futures import ThreadPoolExecutor

    a = access
    request = approve(a, prepare(a))
    with a.db.begin() as c:
        c.execute(
            update(grants)
            .where(grants.c.id == request["id"])
            .values(code_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert a.peer.post(a.prefix + "redeem", json=request).status_code == 401
    request = approve(a, prepare(a))

    def redeem_once(_):
        with TestClient(a.owner.app, base_url=EMBED, headers={"Origin": EMBED}) as client:
            return client.post(a.prefix + "redeem", json=request).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(redeem_once, range(2))) == [200, 401]


def test_invalid_parent_origin_rejected_before_database_lookup(access):
    a = access
    token = established(a)
    assert (
        a.peer.post(
            a.prefix + "read",
            json={"parent_origin": PARENT + "\x00", "point_id": "skills-ru"},
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 422
    )


def test_populated_online_migration_roundtrip_keeps_real_subscriptions(access):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import inspect

    a = access
    token = established(a)
    assert change(a, token).status_code == 200
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": a.db._engine.url.render_as_string(hide_password=False),
    }
    for command, revision in [("downgrade", "0022_profile_preferences"), ("upgrade", "head")]:
        r = subprocess.run(
            [sys.executable, "-m", "alembic", command, revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
        assert ("embed_subscriptions" in inspect(a.db._engine).get_table_names()) == (
            command == "upgrade"
        )
        with a.db.connect() as c:
            assert c.scalar(
                select(subscriptions.c.active).where(subscriptions.c.user_id == a.owner.user)
            )
            assert c.scalar(select(func.count()).select_from(users)) == 1
    assert read(a, token).status_code == 401


def test_completion_uses_same_server_account_without_opener(access):
    a = access
    request = prepare(a)
    pending = a.peer.post(a.prefix + "complete", json=request)
    assert pending.status_code == 200
    assert pending.json() == {"connected": False}
    assert "set-cookie" not in pending.headers
    approve(a, request)
    result = a.peer.post(a.prefix + "complete", json=request)
    assert result.status_code == 200, result.text
    assert result.json()["connected"]
    assert "Partitioned" in result.headers["set-cookie"]
    token = result.json()["token"]
    assert change(a, token).status_code == 200
    assert a.owner.client.get("/api/v1/me/subscriptions/skills-ru").json()["subscription"]["active"]
    with a.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(users)) == 1
    assert a.peer.post(a.prefix + "complete", json=request).status_code == 401


def test_completion_binding_before_and_after_consent(access):
    a = access
    request = prepare(a)
    for consented in (False, True):
        if consented:
            approve(a, request)
        for change_field in (
            {"verifier": secrets.token_urlsafe(32)},
            {"state": uuid4().hex},
            {"parent_origin": "https://other.example"},
        ):
            assert (
                a.peer.post(a.prefix + "complete", json={**request, **change_field}).status_code
                == 401
            )
    with a.db.begin() as c:
        c.execute(update(grants).where(grants.c.id == request["id"]).values(revoked=True))
    assert a.peer.post(a.prefix + "complete", json=request).status_code == 401


def test_completion_expiry_and_native_session_revocation(access):
    a = access
    request = prepare(a)
    approve(a, request)
    with a.db.begin() as c:
        c.execute(
            update(grants)
            .where(grants.c.id == request["id"])
            .values(code_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert a.peer.post(a.prefix + "complete", json=request).status_code == 401
    request = prepare(a)
    approve(a, request)
    with a.db.begin() as c:
        c.execute(
            update(sessions).where(sessions.c.user_id == a.owner.user).values(revoked_at=func.now())
        )
    assert a.peer.post(a.prefix + "complete", json=request).status_code == 401


def test_concurrent_completion_is_single_use(access):
    from concurrent.futures import ThreadPoolExecutor

    a = access
    request = prepare(a)
    approve(a, request)

    def complete_once(_):
        with TestClient(a.owner.app, base_url=EMBED, headers={"Origin": EMBED}) as client:
            return client.post(a.prefix + "complete", json=request).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(complete_once, range(2))) == [200, 401]


def test_two_registered_sites_use_one_account_and_subscription_store(access):
    a = access
    first_token = established(a)
    assert change(a, first_token).status_code == 200
    other_origin = "https://other.example"
    registry = SiteRegistry(a.db)
    other = registry.create_pending_site(
        owner_user_id=a.owner.user, origin=other_origin, welcome_body="Other site"
    )
    registry.verify_site(
        other.site_id,
        actor_user_id=a.owner.user,
        proof_fetcher=lambda _: other.proof_document.encode(),
    )
    prefix = f"/bridge/v1/{other.site_id}/subscriptions/"
    verifier = secrets.token_urlsafe(32)
    prepared = a.peer.post(
        prefix + "prepare",
        json={
            "parent_origin": other_origin,
            "state": uuid4().hex,
            "challenge": challenge(verifier),
        },
    )
    assert prepared.status_code == 200, prepared.text
    request = {**prepared.json(), "verifier": verifier, "parent_origin": other_origin}
    approve(a, request)
    response = a.peer.post(prefix + "complete", json=request)
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    state = a.peer.post(
        prefix + "read",
        json={"parent_origin": other_origin, "point_id": "skills-ru"},
        headers={"Authorization": "Bearer " + token},
    )
    assert state.status_code == 200 and state.json()["subscription"]["active"]
    with a.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(users)) == 1
        assert set(c.scalars(select(grants.c.user_id))) == {a.owner.user}
        assert c.scalar(select(func.count()).select_from(subscriptions)) == 1
    with a.db.begin() as c:
        c.execute(
            update(sessions).where(sessions.c.user_id == a.owner.user).values(revoked_at=func.now())
        )
    assert read(a, first_token).status_code == 401
    assert (
        a.peer.post(
            prefix + "read",
            json={"parent_origin": other_origin, "point_id": "skills-ru"},
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 401
    )
