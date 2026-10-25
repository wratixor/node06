"""Permanent erasure on real PostgreSQL, including old receipts and core copies."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from node06_service.graph_writes import lock_graph
from node06_service.models import (
    authored_revisions,
    core_publications,
    moderation_audit,
    point_hides,
    point_revisions,
    point_tombstones,
    points,
    proposals,
    subscriptions,
)
from node06_service.moderation_admin import grant
from node06_service.public_points import PublicPointError
from node06_service.purge import sweep
from node06_service.social import Social
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from test_authoring import payload, post
from test_moderation import action, active
from test_social import manager as manager
from test_social import proposal, setup, sub
from test_social import static_bundle as static_bundle


def hide(manager, pid, scope="server"):
    if scope == "server":
        grant(manager.app.state.database, manager.user, "admin")
    response = action(
        manager.client,
        scope,
        "visibility/" + pid,
        {"hidden": True, "reason": "Private moderation reason"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def age(database, pid, days=31, scope="server"):
    with database.begin() as c:
        c.execute(
            update(point_hides)
            .where(point_hides.c.point_id == pid, point_hides.c.scope == scope)
            .values(hidden_since=func.clock_timestamp() - timedelta(days=days))
        )


def run(database):
    with database.begin() as c:
        lock_graph(c)
        return sweep(c)


def test_erases_all_revisions_proposals_and_replay(manager, static_bundle, pg_database):
    _, public = setup(manager, static_bundle)
    client = manager.client
    data = payload(client, body="Retention secret original")
    key = uuid4().hex
    first = post(client, data, key).json()
    pid = first["id"]
    sub(client, public, pid)
    qid = proposal(client, public, pid, body="Retention secret proposed")
    hide(manager, pid)
    age(pg_database, pid)
    Social(public).work()
    assert run(pg_database) == 0
    marker = client.get("/api/v1/points/" + pid)
    assert marker.status_code == 200 and marker.json()["deleted"]
    assert marker.json()["body"] == "" and "Private" not in marker.text
    assert post(client, data, key).status_code == 410
    assert (
        action(
            client, "server", "visibility/" + pid, {"hidden": False, "reason": "Restore"}
        ).status_code
        == 410
    )
    assert client.get(f"/api/v1/points/{pid}/revisions").status_code == 410
    assert client.get("/api/v1/points/search?q=Retention").json()["items"] == []
    with pg_database.connect() as c:
        revs = (
            c.execute(select(point_revisions).where(point_revisions.c.point_id == pid))
            .mappings()
            .all()
        )
        assert len(revs) >= 2
        assert all(r["body"] == r["search_text"] == "" and r["declared_links"] == [] for r in revs)
        q = c.execute(select(proposals).where(proposals.c.id == qid)).mappings().one()
        assert q["state"] == "stale" and q["base_body"] == "" and q["content"] == {}
        assert (
            c.scalar(select(subscriptions.c.active).where(subscriptions.c.point_id == pid)) is False
        )
        assert (
            c.scalar(
                select(func.count())
                .select_from(moderation_audit)
                .where(moderation_audit.c.action == "purge")
            )
            == 1
        )
        assert (
            c.scalar(select(points.c.current_revision_id).where(points.c.id == pid))
            == first["revision_id"]
        )
    for change in ({"lifecycle": "active"}, {"current_revision_id": None}):
        with pytest.raises(IntegrityError, match="POINT_PURGED"):
            with pg_database.begin() as c:
                c.execute(update(points).where(points.c.id == pid).values(**change))
    with pytest.raises(IntegrityError, match="POINT_PURGED"):
        with pg_database.begin() as c:
            c.execute(
                update(point_revisions)
                .where(point_revisions.c.point_id == pid)
                .values(body="Resurrection")
            )


def test_core_snapshots_erased_without_changing_other_text(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    sub(manager.client, public, "skills-ru")
    proposal(manager.client, public, first["id"])
    Social(public).work()
    hide(manager, "skills-ru")
    age(pg_database, "skills-ru")
    Social(public).work()
    Social(public).work()
    assert public.get("skills-ru")["deleted"]
    with pg_database.connect() as c:
        with pytest.raises(PublicPointError, match="POINT_PURGED"):
            public.moderation = False
            public.raw_on(c, "skills-ru")
        assert (
            c.scalar(
                select(core_publications.c.body).where(core_publications.c.point_id == "skills-ru")
            )
            == ""
        )
        assert (
            c.scalar(
                select(subscriptions.c.static_body).where(subscriptions.c.point_id == "skills-ru")
            )
            is None
        )
        for table in (authored_revisions, proposals):
            for refs in c.scalars(select(table.c.citations)):
                for ref in refs:
                    if ref["id"] == "skills-ru":
                        assert ref["static_body"] is None
        assert (
            c.scalar(
                select(point_revisions.c.body).where(point_revisions.c.id == first["revision_id"])
            )
            == "Моя [воля](md://point/skills-ru)"
        )


def test_retention_boundary_restore_and_site_only(manager, static_bundle, pg_database):
    first, _ = setup(manager, static_bundle)
    pid = first["id"]
    site = active(pg_database, manager.user, "https://retention.example")
    hide(manager, pid, scope=site)
    age(pg_database, pid, scope=site)
    assert run(pg_database) == 0
    hide(manager, pid)
    age(pg_database, pid, days=29)
    assert run(pg_database) == 0
    restored = action(
        manager.client,
        "server",
        "visibility/" + pid,
        {"hidden": False, "reason": "Restore before cutoff"},
    )
    assert restored.status_code == 200
    assert run(pg_database) == 0
    restarted = hide(manager, pid)
    repeated = hide(manager, pid)
    assert restarted["server_hidden_since"] == repeated["server_hidden_since"]
    assert run(pg_database) == 0
    # At exactly the retention boundary, not a 31-day calendar approximation.
    age(pg_database, pid, days=30)
    assert run(pg_database) == 1


def test_atomic_failure_and_competing_workers(manager, static_bundle, pg_database, monkeypatch):
    first, _ = setup(manager, static_bundle)
    pid = first["id"]
    hide(manager, pid)
    age(pg_database, pid)
    import node06_service.purge as purge

    def fail(*args, **kwargs):
        raise RuntimeError("Injected audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(purge, "event", fail)
        with pytest.raises(RuntimeError, match="Injected"):
            run(pg_database)
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(point_tombstones)) == 0
        assert c.scalar(
            select(point_revisions.c.body).where(point_revisions.c.id == first["revision_id"])
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(pg_database), range(2))) == [0, 1]


def test_git_cannot_resurrect_but_can_drop_purged_root(manager, static_bundle, pg_database):
    from node06_service.root_import import RootImportError
    from node06_service.root_publish import publish
    from test_root_publish import REPO, candidate

    setup(manager, static_bundle)
    from node06_service.site_registry import SiteRegistry

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
    hide(manager, pid)
    age(pg_database, pid)
    assert run(pg_database) == 1
    for check in (True, False):
        with pytest.raises(RootImportError, match="POINT_PURGED"):
            publish(
                pg_database, candidate(site, sha="b" * 40), REPO, "https://git.example", check=check
            )
    publish(pg_database, candidate(site, include=False, sha="c" * 40), REPO, "https://git.example")


def test_site_welcome_is_empty_and_cannot_be_rewritten(manager, static_bundle, pg_database):
    from node06_service.models import sites
    from test_moderation import install

    setup(manager, static_bundle)
    install(manager, static_bundle)
    site = active(pg_database, manager.user, "https://empty.example")
    hide(manager, site)
    age(pg_database, site)
    assert run(pg_database) == 1
    client = manager.client
    assert client.get("/api/v1/points/" + site).json()["deleted"]
    assert client.get("/sites/" + site + "/?p=" + site).status_code == 200
    response = client.patch(
        "/api/v1/sites/" + site,
        json={
            "expected_settings_revision": 1,
            "expected_welcome_revision": "v_" + "a" * 32,
            "display_name": "Revived",
            "welcome_body": "Revived",
            "theme": {},
        },
    )
    assert response.status_code == 410, response.text
    with pg_database.connect() as c:
        row = c.execute(select(sites).where(sites.c.id == site)).mappings().one()
        assert row["display_name"] is None and row["home_page"] is None
        assert row["git_home_page"] is None and row["theme"] == {}
        assert row["primary_origin"] == "https://empty.example"


def test_restore_serializes_before_waiting_worker(manager, static_bundle, pg_database):
    from threading import Event

    from sqlalchemy import text

    first, _ = setup(manager, static_bundle)
    pid = first["id"]
    hide(manager, pid)
    age(pg_database, pid)
    started = Event()

    def worker():
        started.set()
        return run(pg_database)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg_database.begin() as c:
            lock_graph(c)
            future = pool.submit(worker)
            assert started.wait(2)
            # Same lock/order as the moderation restore; commit before worker can inspect.
            c.execute(
                update(point_hides)
                .where(point_hides.c.point_id == pid)
                .values(active=False, hidden_since=None)
            )
        assert future.result(timeout=10) == 0
        # Waiting must not freeze the retention clock at transaction start.
        with pg_database.begin() as c:
            lock_graph(c)
            c.execute(
                update(point_hides)
                .where(point_hides.c.point_id == pid)
                .values(
                    active=True,
                    hidden_since=func.clock_timestamp()
                    - timedelta(days=30)
                    + timedelta(milliseconds=250),
                )
            )
            future = pool.submit(worker)
            c.execute(text("SELECT pg_sleep(0.4)"))
        assert future.result(timeout=10) == 1


def test_populated_ledger_refuses_schema_downgrade(manager, static_bundle, pg_database):
    import os
    import subprocess
    import sys

    from test_compose_migration import ROOT

    first, _ = setup(manager, static_bundle)
    hide(manager, first["id"])
    age(pg_database, first["id"])
    assert run(pg_database) == 1
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0017_scoped_bans"],
        cwd=ROOT,
        env={
            **os.environ,
            "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0 and "retain tombstones" in result.stderr
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(point_tombstones)) == 1
