"""Scoped bans: write-time checks, public isolation and session-only cohort reads."""

import os
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from node06_service.bans import epoch
from node06_service.models import moderation_audit, moderation_bans, point_revisions, points
from node06_service.moderation_admin import grant
from node06_service.public_points import PublicPoints
from node06_service.social import Social
from sqlalchemy import func, select, update
from test_authoring import payload, post
from test_compose_migration import ROOT
from test_moderation import EMBED, action, active, install
from test_site_management import ORIGIN
from test_social import manager as manager
from test_social import second, setup, sub
from test_social import static_bundle as static_bundle


def restrict(client, target, scope="server", mode="block", key=None):
    return action(
        client,
        scope,
        "bans/" + target,
        {"mode": mode, "duration_seconds": 3600, "reason": "Review <script>unsafe()</script>"},
        key,
    )


def write(client, data, site=None, key=None):
    return client.post(
        "/api/v1/points",
        params={"site": site} if site else {},
        json=data,
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_site_block_is_local_and_rechecks_before_replay(manager, static_bundle, pg_database):
    setup(manager, static_bundle)
    bob = second(manager)
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://ban.example")
    other = active(pg_database, manager.user, "https://other-ban.example")
    data, key = payload(bob), uuid4().hex
    point = write(bob, data, site, key).json()
    assert restrict(bob, manager.user, site).status_code == 403
    assert restrict(manager.client, bob_id, site).status_code == 200
    assert bob.get("/api/v1/points/" + point["id"], params={"site": site}).status_code == 404
    assert bob.get("/api/v1/points/" + point["id"], params={"site": other}).status_code == 200
    denied = write(bob, data, site, key)
    assert denied.status_code == 403 and denied.json()["code"] == "PUBLICATION_BANNED"
    assert write(bob, data, other).status_code == 201
    # A local ban must not prevent another website's trusted compose confirmation.
    from node06_service.author_api import Content

    # Exercise the same service method used by compose, with the proper site.
    from node06_service.authoring import Authoring

    store = PublicPoints(pg_database, roots=manager.app.state.hosted_bundle.roots)
    result = Authoring(store, lambda c, uid: None).save(
        bob_id, uuid4().hex, Content(**data).model_dump(), compose_site=other
    )
    assert result["id"]
    assert restrict(manager.client, bob_id, site, None).status_code == 200
    assert write(bob, data, site, key).json() == point


def test_quarantine_cohort_private_reads_and_public_surfaces(manager, static_bundle, pg_database):
    setup(manager, static_bundle)
    install(manager, static_bundle)
    bob, charlie, dave = second(manager), second(manager, "charlie"), second(manager, "dave")
    bob_id, charlie_id, dave_id = [
        c.get("/api/v1/me").json()["user_id"] for c in (bob, charlie, dave)
    ]
    site = active(pg_database, manager.user, "https://quarantine.example")
    grant(pg_database, manager.user, "admin")
    assert restrict(manager.client, bob_id, mode="quarantine").status_code == 200
    assert restrict(manager.client, dave_id).status_code == 200
    q = post(bob, payload(bob, body="Quarantine <script>private()</script>")).json()
    assert q["quarantined"] is True
    assert q["quarantine_scope"] == "server"
    pid = q["id"]
    assert manager.client.get("/api/v1/points/" + pid).status_code == 404
    assert manager.client.get("/api/v1/points/" + pid + "/revisions").status_code == 404
    assert manager.client.get("/api/v1/points/" + pid + "/social").status_code == 404
    assert not any(
        p["id"] == pid
        for p in manager.client.get("/api/v1/points/search?q=Quarantine").json()["items"]
    )
    assert not any(
        p["id"] == pid
        for p in manager.client.get(f"/api/v1/people/{bob_id}/points").json()["items"]
    )
    assert not any(p["id"] == pid for p in manager.client.get("/data/points.json").json())
    assert not any(
        p["id"] == pid
        for p in manager.client.get("/api/v1/points/skills-ru/neighbors").json()["items"]
    )
    assert not any(p["id"] == pid for p in manager.client.get("/api/v1/me/feed").json()["items"])
    path = "/api/v1/me/quarantine/" + pid
    assert charlie.get(path).status_code == 403
    assert TestClient(manager.app, base_url=ORIGIN).get(path).status_code == 401
    for viewer in (bob, dave, manager.client):
        response = viewer.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert "private()" in response.json()["body"]
        assert viewer.get("/api/v1/me/quarantine").json()["items"][0]["id"] == pid
    # A site moderator does not acquire access to server quarantine.
    assert (
        action(manager.client, site, "roles/" + charlie_id, {"role": "moderator"}).status_code
        == 200
    )
    assert charlie.get(path, params={"scope": site}).status_code == 404
    assert (
        charlie.get("/api/v1/moderation/inspect/" + pid, params={"scope": site}).status_code == 403
    )
    assert bob.get(EMBED + path).status_code == 404
    assert bob.get(EMBED + "/quarantine/").status_code == 404
    assert manager.client.get("/quarantine/").headers["x-frame-options"] == "DENY"
    assert (
        action(
            manager.client,
            "server",
            "visibility/" + pid,
            {"hidden": True, "reason": "separate hide"},
        ).status_code
        == 200
    )
    assert bob.get(path).status_code == 404
    assert manager.client.get(path).status_code == 200
    assert restrict(manager.client, bob_id, mode=None).status_code == 200
    assert bob.get(path).status_code == 403


def test_local_quarantine_new_edits_and_other_sites(manager, static_bundle, pg_database):
    setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://local-quarantine.example")
    point = post(bob, payload(bob)).json()
    assert restrict(manager.client, uid, site, "quarantine").status_code == 200
    assert bob.get("/api/v1/points/" + point["id"], params={"site": site}).status_code == 200
    created = write(bob, payload(bob, body="Local quarantine"), site).json()
    assert created["quarantined"] is True
    assert created["quarantine_scope"] == site
    assert bob.get("/api/v1/points/" + created["id"], params={"site": site}).status_code == 404
    assert bob.get("/api/v1/points/" + created["id"]).status_code == 200
    edit = bob.patch(
        "/api/v1/points/" + point["id"],
        params={"site": site},
        json={
            **payload(bob, body="Updated while quarantined"),
            "expected_revision_id": point["revision_id"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert edit.status_code == 200 and edit.json()["quarantined"]
    assert bob.get("/api/v1/points/" + point["id"], params={"site": site}).status_code == 404
    assert bob.get("/api/v1/points/" + point["id"]).status_code == 200
    # Repeated sanctions preserve the beginning of quarantine, not release earlier posts.
    with pg_database.connect() as c:
        start = c.scalar(
            select(moderation_bans.c.starts_at).where(moderation_bans.c.user_id == uid)
        )
    assert restrict(manager.client, uid, site, "quarantine").status_code == 200
    with pg_database.connect() as c:
        assert (
            c.scalar(select(moderation_bans.c.starts_at).where(moderation_bans.c.user_id == uid))
            == start
        )
    assert bob.get("/api/v1/points/" + created["id"], params={"site": site}).status_code == 404
    assert restrict(manager.client, uid, site, None).status_code == 200
    assert bob.get("/api/v1/points/" + created["id"], params={"site": site}).status_code == 200


def test_expiry_freshness_and_global_t1_isolation(manager, static_bundle, pg_database):
    _, public = setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    point = post(bob, payload(bob)).json()
    sub(manager.client, public, point["id"])
    site = active(pg_database, manager.user, "https://mass-ban.example")
    assert restrict(manager.client, uid, site).status_code == 200
    local = PublicPoints(pg_database, roots=public.core.values(), site_id=site)
    Social(local).work()
    # A local scope must not change global mass or global voting projections.
    result = manager.client.get("/api/v1/points/" + point["id"] + "/social-summary").json()
    assert result["influence"]["current"] == "0.5", result
    grant(pg_database, manager.user, "admin")
    assert restrict(manager.client, uid).status_code == 200
    Social(public).work()
    with pg_database.connect() as c:
        old = epoch(c)
    with pg_database.begin() as c:
        now = c.scalar(select(func.now()))
        c.execute(
            update(moderation_bans)
            .where(moderation_bans.c.scope == "server")
            .values(starts_at=now - timedelta(hours=2), expires_at=now - timedelta(seconds=1))
        )
    assert manager.client.get("/api/v1/points/" + point["id"]).status_code == 200
    assert manager.client.get("/api/v1/directory/rankings").json()["pending"] is True
    assert (
        manager.client.get("/api/v1/points/" + point["id"] + "/social-summary").json()["influence"][
            "pending"
        ]
        is True
    )
    with pg_database.connect() as c:
        assert epoch(c) != old
    Social(public).work()
    assert (
        manager.client.get("/api/v1/points/" + point["id"] + "/social-summary").json()["influence"][
            "current"
        ]
        == "0.5"
    )


def test_protected_roles_replay_and_source_management_guard(manager, static_bundle, pg_database):
    setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://roles-ban.example")
    assert restrict(manager.client, manager.user, site).status_code == 409
    assert action(manager.client, site, "roles/" + uid, {"role": "moderator"}).status_code == 200
    assert restrict(manager.client, uid, site).status_code == 403
    assert action(manager.client, site, "roles/" + uid, {"role": None}).status_code == 200
    # Delegate to bob, ban a third account, revoke bob: replay must still authorize.
    charlie = second(manager, "charlie")
    cid = charlie.get("/api/v1/me").json()["user_id"]
    assert action(manager.client, site, "roles/" + uid, {"role": "moderator"}).status_code == 200
    key = uuid4().hex
    first = restrict(bob, cid, site, key=key)
    assert first.status_code == 200
    assert restrict(bob, cid, site, key=key).json() == first.json()
    assert action(manager.client, site, "roles/" + uid, {"role": None}).status_code == 200
    assert restrict(bob, cid, site, key=key).status_code == 403
    grant(pg_database, manager.user, "admin")
    assert restrict(manager.client, cid).status_code == 200
    assert (
        charlie.post(
            "/api/v1/sites", json={"origin": "https://circumvent.example", "welcome_body": "Bypass"}
        ).status_code
        == 403
    )
    assert manager.client.get("/api/v1/points/skills-ru").status_code == 200
    with pg_database.connect() as c:
        assert (
            c.scalar(
                select(func.count())
                .select_from(moderation_audit)
                .where(moderation_audit.c.action == "ban")
            )
            == 2
        )


def test_scoped_bans_populated_migration_roundtrip(manager, static_bundle, pg_database):
    point, _ = setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    grant(pg_database, manager.user, "admin")
    assert restrict(manager.client, uid).status_code == 200
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for target in ("0016_scoped_moderation", "head"):
        command = "downgrade" if target.startswith("0016") else "upgrade"
        r = subprocess.run(
            [sys.executable, "-m", "alembic", command, target],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(moderation_bans)) == 0
        assert (
            c.scalar(select(points.c.current_revision_id).where(points.c.id == point["id"]))
            == point["revision_id"]
        )
        assert c.scalar(
            select(point_revisions.c.body).where(point_revisions.c.id == point["revision_id"])
        )


def test_local_visibility_cannot_close_a_global_proposal(manager, static_bundle, pg_database):
    from node06_service.models import proposals
    from test_social import proposal

    _, public = setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    point = post(bob, payload(bob)).json()
    sub(manager.client, public, point["id"])
    qid = proposal(manager.client, public, point["id"])
    site = active(pg_database, manager.user, "https://proposal-ban.example")
    assert restrict(manager.client, uid, site).status_code == 200
    current = public.get(point["id"])
    result = manager.client.post(
        "/api/v1/points/" + point["id"] + "/subscription",
        params={"site": site},
        json={
            "active": False,
            "revision_id": current["revision_id"],
            "content_digest": current["content_digest"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert result.status_code == 200, result.text
    with pg_database.connect() as c:
        assert c.scalar(select(proposals.c.state).where(proposals.c.id == qid)) == "open"


def test_server_ban_restricts_new_and_pending_proposals(manager, static_bundle, pg_database):
    from node06_service.models import proposals
    from test_social import proposal

    point, public = setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    qid = proposal(bob, public, point["id"])
    grant(pg_database, manager.user, "admin")
    assert restrict(manager.client, uid).status_code == 200
    assert manager.client.get("/api/v1/proposals/" + qid).status_code == 404
    assert manager.client.get("/api/v1/points/" + point["id"] + "/social").json()["proposals"] == []
    p = public.get(point["id"])
    denied = bob.post(
        "/api/v1/points/" + point["id"] + "/proposals",
        json={
            **payload(bob),
            "expected_revision_id": p["revision_id"],
            "expected_digest": p["content_digest"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert denied.status_code == 403 and denied.json()["code"] == "PUBLICATION_BANNED"
    Social(public).work()
    with pg_database.connect() as c:
        assert c.scalar(select(proposals.c.state).where(proposals.c.id == qid)) == "stale"


def test_waiting_transaction_cannot_publish_before_quarantine_start(
    manager, static_bundle, pg_database, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import node06_service.authoring as module
    from node06_service.graph_writes import lock_graph
    from node06_service.moderation import Moderation

    _, public = setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    site = active(pg_database, manager.user, "https://waiting-ban.example")
    data = payload(bob)
    entered = Event()

    def waiting(c):
        # Force a transaction timestamp before the ban is applied under the lock.
        c.scalar(select(func.pg_backend_pid()))
        entered.set()
        lock_graph(c)

    monkeypatch.setattr(module, "lock_graph", waiting)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg_database.begin() as c:
            lock_graph(c)
            future = pool.submit(write, bob, data, site)
            assert entered.wait(10)
            Moderation(public, lambda c, actor: None)._ban(
                c,
                manager.user,
                site,
                uid,
                {"mode": "quarantine", "duration_seconds": 3600, "reason": "Concurrent ban"},
            )
        response = future.result(timeout=15)
    assert response.status_code == 201, response.text
    point = response.json()
    assert point["quarantined"] is True
    assert bob.get("/api/v1/points/" + point["id"], params={"site": site}).status_code == 404


def test_snapshot_rejects_expiry_during_computation(
    manager, static_bundle, pg_database, monkeypatch
):
    import node06_service.bans as module
    import pytest
    from node06_service.influence import InfluenceUnavailable
    from node06_service.models import influence_runs

    _, public = setup(manager, static_bundle)
    before = 0
    with pg_database.connect() as c:
        before = c.scalar(select(func.count()).select_from(influence_runs))
    original = module.epoch
    calls = []

    def changed(c):
        calls.append(True)
        return original(c) if len(calls) == 1 else "changed-during-computation"

    monkeypatch.setattr(module, "epoch", changed)
    with pytest.raises(InfluenceUnavailable, match="INFLUENCE_MODERATION_CHANGED"):
        Social(public).work()
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(influence_runs)) == before
