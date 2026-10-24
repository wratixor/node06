"""Real PostgreSQL moderation scope boundaries, deduplication and read-surface suppression."""

import os
import subprocess
import sys
from uuid import uuid4

from node06_service.bridge import register_bridge
from node06_service.hosted import register_hosted
from node06_service.models import moderation_audit, moderation_reports, point_hides, points
from node06_service.moderation_admin import grant
from node06_service.site_registry import SiteRegistry
from sqlalchemy import func, inspect, select
from test_authoring import payload, post
from test_compose_migration import ROOT
from test_social import manager as manager
from test_social import second, setup, sub
from test_social import static_bundle as static_bundle

EMBED = "https://embed.example"


def active(database, owner, origin):
    registry = SiteRegistry(database)
    site = registry.create_pending_site(owner_user_id=owner, origin=origin, welcome_body="Welcome")
    registry.verify_site(
        site.site_id, actor_user_id=owner, proof_fetcher=lambda _: site.proof_document.encode()
    )
    return site.site_id


def action(client, scope, path, data=None, key=None):
    return client.post(
        "/api/v1/moderation/" + path,
        params={"scope": scope},
        json=data or {},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def install(manager, bundle):
    manager.app.state.settings.hosted_dist = bundle
    manager.app.state.settings.embed_origin = EMBED
    register_hosted(manager.app, manager.app.state.settings)
    register_bridge(manager.app)


def test_roles_reports_dedup_and_revocation(manager, static_bundle, pg_database):
    point, _ = setup(manager, static_bundle)
    alice, bob, charlie = manager.client, second(manager), second(manager, "charlie")
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://site.example")
    reason = {"reason": "Needs review <script>bad()</script>"}
    for _ in range(2):
        assert action(bob, site, "reports/" + point["id"], reason).status_code == 200
    assert action(alice, site, "reports/" + point["id"], reason).status_code == 200
    queue = alice.get("/api/v1/moderation/cases", params={"scope": site}).json()
    assert queue["role"] == "admin" and queue["items"][0]["reports"] == 2
    assert bob.get("/api/v1/moderation/cases", params={"scope": site}).status_code == 403
    assert action(alice, "server", "roles/" + bob_id, {"role": "admin"}).status_code == 403
    assert action(alice, site, "roles/" + bob_id, {"role": "moderator"}).status_code == 200
    assert (
        bob.get("/api/v1/moderation/inspect/" + point["id"], params={"scope": site}).status_code
        == 200
    )
    assert action(bob, site, "roles/" + manager.user, {"role": "admin"}).status_code == 403
    key = uuid4().hex
    data = {"hidden": True, "reason": "Local decision"}
    first = action(bob, site, "visibility/" + point["id"], data, key)
    assert first.status_code == 200
    assert action(bob, site, "visibility/" + point["id"], data, key).json() == first.json()
    assert (
        action(bob, site, "visibility/" + point["id"], {**data, "hidden": False}, key).status_code
        == 409
    )
    assert action(alice, site, "roles/" + bob_id, {"role": None}).status_code == 200
    assert action(bob, site, "visibility/" + point["id"], data, key).status_code == 403
    assert action(alice, site, "cases/" + point["id"] + "/close").status_code == 200
    # Restore, then an existing reporter does not reopen; a genuinely new reporter does.
    assert (
        action(
            alice, site, "visibility/" + point["id"], {"hidden": False, "reason": "Restore"}
        ).status_code
        == 200
    )
    assert action(bob, site, "reports/" + point["id"], reason).status_code == 200
    assert alice.get("/api/v1/moderation/cases", params={"scope": site}).json()["items"] == []
    assert action(charlie, site, "reports/" + point["id"], reason).status_code == 200
    assert (
        alice.get("/api/v1/moderation/cases", params={"scope": site}).json()["items"][0]["reports"]
        == 3
    )
    denied = alice.post(
        "/api/v1/moderation/visibility/" + point["id"] + "?scope=" + site,
        json=data,
        headers={"X-CSRF-Token": "wrong", "Idempotency-Key": uuid4().hex},
    )
    assert denied.status_code == 403
    assert action(alice, "server", "reports/" + point["id"], reason).status_code == 200
    grant(pg_database, manager.user, "admin")
    assert action(alice, "server", "roles/" + manager.user, {"role": None}).status_code == 409
    assert action(alice, "server", "roles/" + bob_id, {"role": "moderator"}).status_code == 200
    assert action(bob, "server", "visibility/" + point["id"], data).status_code == 200
    assert action(bob, "server", "roles/" + manager.user, {"role": None}).status_code == 403


def test_hide_every_read_surface_core_fallback_and_site_isolation(
    manager, static_bundle, pg_database
):
    topic, public = setup(manager, static_bundle)
    install(manager, static_bundle)
    alice, bob = manager.client, second(manager)
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://site.example")
    other = active(pg_database, bob_id, "https://other.example")
    sub(alice, public, topic["id"])
    created = post(bob, payload(bob, target=topic["id"], body="Moderated unique phrase")).json()
    pid = created["id"]
    for target in (pid, "point-ru"):
        assert (
            action(
                alice, site, "visibility/" + target, {"hidden": True, "reason": "Site hide"}
            ).status_code
            == 200
        )
        assert alice.get("/api/v1/points/" + target, params={"site": site}).status_code == 404
        assert alice.get("/api/v1/points/" + target, params={"site": other}).status_code == 200
        assert alice.get("/api/v1/points/" + target).status_code == 200
        for method in ("point.read", "point.get", "point.social"):
            assert (
                alice.get(
                    EMBED + f"/bridge/v1/{site}/read", params={"method": method, "point_id": target}
                ).status_code
                == 404
            )
        assert target not in [
            p["id"] for p in alice.get("/data/points.json", params={"site": site}).json()
        ]
    assert (
        alice.get("/api/v1/points/" + pid + "/revisions", params={"site": site}).status_code == 404
    )
    assert pid not in [
        p["id"]
        for p in alice.get("/api/v1/people/" + bob_id + "/points", params={"site": site}).json()[
            "items"
        ]
    ]
    assert pid not in [
        p["id"] for p in alice.get("/api/v1/me/feed", params={"site": site}).json()["items"]
    ]
    assert (
        alice.get("/api/v1/points/search", params={"site": site, "q": "Moderated"}).json()["items"]
        == []
    )
    assert alice.get("/api/v1/geometry", params={"site": site, "ids": pid}).json()["items"] == []
    # Server hides apply even when another site context is explicitly selected.
    grant(pg_database, manager.user, "admin")
    for target in (pid, "point-ru"):
        result = action(
            alice, "server", "visibility/" + target, {"hidden": True, "reason": "Server hide"}
        )
        assert result.status_code == 200 and result.json()["server_hidden_since"]
        repeated = action(
            alice, "server", "visibility/" + target, {"hidden": True, "reason": "Again"}
        )
        assert repeated.json()["server_hidden_since"] == result.json()["server_hidden_since"]
        assert alice.get("/api/v1/points/" + target, params={"site": other}).status_code == 404
        assert alice.get("/api/v1/points/" + target).status_code == 404
        assert target not in [p["id"] for p in alice.get("/data/points.json").json()]
        assert target not in [
            p["id"]
            for p in alice.get("/api/v1/points/search", params={"q": target}).json()["items"]
        ]
        for endpoint in (
            "/moderation/",
            "/api/v1/moderation/scopes",
            "/api/v1/moderation/inspect/" + target,
        ):
            response = alice.get(EMBED + endpoint)
            assert response.status_code == 404 and response.headers["cache-control"] == "no-store"
        inspect_response = alice.get("/api/v1/moderation/inspect/" + target).json()
        assert inspect_response["point"]["id"] == target
        assert (
            action(
                alice,
                "server",
                "visibility/" + target,
                {"hidden": False, "reason": "Server restore"},
            ).status_code
            == 200
        )
        assert alice.get("/api/v1/points/" + target, params={"site": other}).status_code == 200
        assert alice.get("/api/v1/points/" + target, params={"site": site}).status_code == 404
    # Even the welcome cannot leak via rendered HTML or public site metadata.
    assert (
        action(
            alice, site, "visibility/" + site, {"hidden": True, "reason": "Welcome hide"}
        ).status_code
        == 200
    )
    assert alice.get("/sites/" + site + "/").status_code == 404
    assert alice.get("/api/v1/sites/" + site, params={"site": site}).status_code == 404


def test_moderation_populated_migration_roundtrip(manager, static_bundle, pg_database):
    point, _ = setup(manager, static_bundle)
    grant(pg_database, manager.user, "admin")
    assert (
        action(manager.client, "server", "reports/" + point["id"], {"reason": "Review"}).status_code
        == 200
    )
    assert (
        action(
            manager.client,
            "server",
            "visibility/" + point["id"],
            {"hidden": True, "reason": "Hide"},
        ).status_code
        == 200
    )
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(moderation_reports)) == 1
        assert c.scalar(select(func.count()).select_from(moderation_audit)) == 3
        assert c.scalar(select(point_hides.c.hidden_since))
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for target in ("0015_creation_feed", "head", "0015_creation_feed", "head"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade" if target == "head" else "downgrade",
                target,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert ("point_hides" in inspect(pg_database._engine).get_table_names()) == (
            target == "head"
        )
        with pg_database.connect() as c:
            assert (
                c.scalar(select(points.c.current_revision_id).where(points.c.id == point["id"]))
                == point["revision_id"]
            )


def test_git_reimport_keeps_hide_and_retired_point_can_restore(manager, static_bundle, pg_database):
    from node06_service.root_publish import publish
    from test_root_publish import REPO, candidate

    setup(manager, static_bundle)
    registry = SiteRegistry(pg_database)
    site = registry.create_pending_site(
        owner_user_id=manager.user, origin="https://git.example", welcome_body="Welcome"
    )
    registry.verify_site(
        site.site_id,
        actor_user_id=manager.user,
        proof_fetcher=lambda _: site.proof_document.encode(),
    )
    publish(pg_database, candidate(site), REPO, "https://git.example")
    pid = "r_" + site.site_id[2:] + "_idea"
    grant(pg_database, manager.user, "admin")
    assert (
        action(
            manager.client,
            "server",
            "visibility/" + pid,
            {"hidden": True, "reason": "Review source"},
        ).status_code
        == 200
    )
    publish(
        pg_database,
        candidate(site, body="Changed behind hide", sha="b" * 40),
        REPO,
        "https://git.example",
    )
    assert manager.client.get("/api/v1/points/" + pid).status_code == 404
    inspected = manager.client.get("/api/v1/moderation/inspect/" + pid).json()
    assert "Changed behind hide" in inspected["point"]["display_text"]
    publish(pg_database, candidate(site, include=False, sha="c" * 40), REPO, "https://git.example")
    assert (
        action(
            manager.client,
            "server",
            "visibility/" + pid,
            {"hidden": False, "reason": "Restore absent"},
        ).status_code
        == 200
    )
    with pg_database.connect() as c:
        assert (
            c.scalar(select(point_hides.c.hidden_since).where(point_hides.c.point_id == pid))
            is None
        )
    publish(
        pg_database, candidate(site, body="Returned", sha="d" * 40), REPO, "https://git.example"
    )
    assert manager.client.get("/api/v1/points/" + pid).status_code == 200
