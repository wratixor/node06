"""PostgreSQL owner/proof/preview/accept, stale races, polling and purge boundaries."""

import hashlib
from datetime import timedelta

import pytest
from node06_service.models import (
    git_sources,
    point_hides,
    point_revisions,
    points,
    root_sources,
    sites,
)
from node06_service.root_import import RootImportError
from node06_service.source_service import SourceError, Sources
from sqlalchemy import func, select, update
from test_moderation import active, install
from test_purge import run as purge
from test_root_publish import candidate
from test_social import manager as manager
from test_social import second, setup
from test_social import static_bundle as static_bundle


def registered(manager, bundle, database, policy="manual"):
    setup(manager, bundle)
    site_id = active(database, manager.user, "https://source.example")
    # The candidate fixture only needs this existing site's immutable ID.
    from types import SimpleNamespace

    site = SimpleNamespace(site_id=site_id)
    service = Sources(database)
    proof = service.configure(manager.user, site_id, "example/wiki", "main", policy, None)
    service.loader = lambda *args: (
        candidate(site),
        (1, 2),
        hashlib.sha256(proof["source_proof"].encode()).hexdigest(),
    )
    return site, service, proof


def allow_refresh(database, site_id):
    with database.begin() as c:
        c.execute(
            update(git_sources)
            .where(git_sources.c.site_id == site_id)
            .values(
                last_attempt_at=None, next_check_at=func.clock_timestamp() - timedelta(seconds=1)
            )
        )


def test_private_api_preview_accept_replay_and_origin(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database)
    manager.app.state.source_loader = service.loader
    client, path = manager.client, "/api/v1/sites/" + site.site_id + "/source"
    install(manager, static_bundle)
    private = client.get(path)
    assert private.json()["verified"] is False
    assert private.headers["cache-control"] == "no-store"
    assert private.headers["x-frame-options"] == "DENY"
    assert second(manager).get(path).status_code == 403
    assert client.get("https://embed.example" + path).status_code == 404
    preview = client.post(path + "/preview", json={"generation": proof["generation"]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["writes_performed"] is False
    status = client.get(path).json()
    assert (
        status["verified"]
        and next(p for p in status["preview"]["comparison"] if p["id"] == site.site_id)["before"]
        == "Welcome"
    )
    assert client.get("/api/v1/points/r_" + site.site_id[2:] + "_idea").status_code == 404
    data = {
        "generation": proof["generation"],
        "preview_id": status["preview"]["id"],
        "accept_git_welcome": True,
    }
    response = client.post(path + "/accept", json=data)
    assert response.status_code == 200, response.text
    assert response.json()["source_authority"] == "owner"
    assert client.post(path + "/accept", json=data).json() == response.json()
    assert client.get("/api/v1/points/r_" + site.site_id[2:] + "_idea").status_code == 200
    assert client.get(path).json()["preview"] is None
    assert (
        client.post(path + "/accept", json={**data, "accept_git_welcome": False}).status_code == 422
    )
    assert (
        client.post(
            path + "/preview",
            json={"generation": proof["generation"]},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )


def test_wrong_proof_expiry_and_repository_transfer(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database)
    good = service.loader
    service.loader = lambda *args: (candidate(site), (1, 2), "0" * 64)
    with pytest.raises(SourceError, match="SOURCE_PROOF_REQUIRED"):
        service.refresh(manager.user, site.site_id, proof["generation"])
    service.loader = good
    allow_refresh(pg_database, site.site_id)
    with pg_database.begin() as c:
        c.execute(
            update(git_sources)
            .where(git_sources.c.site_id == site.site_id)
            .values(proof_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    with pytest.raises(SourceError, match="SOURCE_PROOF_REQUIRED"):
        service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.begin() as c:
        c.execute(
            update(git_sources)
            .where(git_sources.c.site_id == site.site_id)
            .values(proof_expires_at=func.clock_timestamp() + timedelta(hours=1))
        )
    allow_refresh(pg_database, site.site_id)
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    allow_refresh(pg_database, site.site_id)
    service.loader = lambda *args: (candidate(site, body="Stolen", sha="b" * 40), (999, 2), "")
    with pytest.raises(SourceError, match="SOURCE_IDENTITY_CHANGED"):
        service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.connect() as c:
        assert (
            c.scalar(
                select(root_sources.c.commit_sha).where(root_sources.c.site_id == site.site_id)
            )
            == "a" * 40
        )


def test_stale_preview_no_partial_accept_and_reconfiguration(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database)
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.begin() as c:
        c.execute(
            update(sites)
            .where(sites.c.id == site.site_id)
            .values(settings_revision=sites.c.settings_revision + 1)
        )
    with pytest.raises(SourceError, match="SOURCE_PREVIEW_STALE"):
        service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    with pg_database.connect() as c:
        assert c.scalar(select(root_sources.c.site_id)) is None
    service.configure(
        manager.user, site.site_id, "example/wiki", "main", "manual", proof["generation"]
    )
    with pytest.raises(SourceError, match="SOURCE_CHANGED"):
        service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])


def test_opt_in_polling_failure_last_good_and_purge_preview(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database, policy="auto")
    service.work()  # No repository proof/explicit first acceptance yet.
    assert service.status(manager.user, site.site_id)["preview"] is None
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    service.loader = lambda *args: (candidate(site, body="Second", sha="b" * 40), (1, 2), "")
    allow_refresh(pg_database, site.site_id)
    service.work()
    pid = "r_" + site.site_id[2:] + "_idea"
    with pg_database.connect() as c:
        assert "Second" in c.scalar(
            select(point_revisions.c.body)
            .join(points, points.c.current_revision_id == point_revisions.c.id)
            .where(points.c.id == pid)
        )

    def unavailable(*args):
        raise RootImportError("GITHUB_UNAVAILABLE")

    service.loader = unavailable
    allow_refresh(pg_database, site.site_id)
    service.work()
    assert service.status(manager.user, site.site_id)["last_error"] == "GITHUB_UNAVAILABLE"
    service.loader = lambda *args: (candidate(site, body="Third", sha="c" * 40), (1, 2), "")
    allow_refresh(pg_database, site.site_id)
    service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.begin() as c:
        from sqlalchemy import insert

        c.execute(
            insert(point_hides).values(
                scope="server",
                point_id=pid,
                active=True,
                hidden_since=func.clock_timestamp() - timedelta(days=30),
            )
        )
    assert purge(pg_database) == 1
    status = service.status(manager.user, site.site_id)
    assert status["preview"] is None and status["last_error"] == "POINT_PURGED"
    assert "Third" not in str(status)


def test_owner_revocation_during_fetch_rolls_back_preview(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database)
    original = service.loader
    other = second(manager)
    other_id = other.get("/api/v1/me").json()["user_id"]

    def transfer(*args):
        result = original(*args)
        with pg_database.begin() as c:
            c.execute(
                update(sites).where(sites.c.id == site.site_id).values(owner_user_id=other_id)
            )
        return result

    service.loader = transfer
    with pytest.raises(SourceError, match="SITE_FORBIDDEN"):
        service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.connect() as c:
        assert (
            c.scalar(select(git_sources.c.candidate).where(git_sources.c.site_id == site.site_id))
            is None
        )
        assert c.scalar(select(root_sources.c.site_id)) is None
    with pytest.raises(SourceError, match="SOURCE_BINDING_CHANGED"):
        service.status(other_id, site.site_id)


def test_preview_expiry_rate_limit_and_operator_boundary(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database)
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    with pytest.raises(SourceError, match="SOURCE_RATE_LIMITED"):
        service.refresh(manager.user, site.site_id, proof["generation"])
    with pg_database.begin() as c:
        c.execute(
            update(git_sources)
            .where(git_sources.c.site_id == site.site_id)
            .values(preview_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    with pytest.raises(SourceError, match="SOURCE_PREVIEW_EXPIRED"):
        service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    from types import SimpleNamespace

    from node06_service.root_publish import publish

    another = SimpleNamespace(site_id=active(pg_database, manager.user, "https://operator.example"))
    publish(
        pg_database,
        candidate(another),
        "https://github.com/example/wiki.git",
        "https://operator.example",
    )
    assert service.status(manager.user, another.site_id)["operator_managed"]
    with pytest.raises(SourceError, match="SOURCE_OPERATOR_MANAGED"):
        service.configure(manager.user, another.site_id, "example/wiki", "main", "auto", None)


def test_concurrent_accept_and_manual_policy(manager, static_bundle, pg_database):
    from concurrent.futures import ThreadPoolExecutor

    site, service, proof = registered(manager, static_bundle, pg_database)
    preview = service.refresh(manager.user, site.site_id, proof["generation"])

    def accept(_):
        return service.accept(
            manager.user, site.site_id, proof["generation"], preview["preview_id"]
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert results[0] == results[1]
    allow_refresh(pg_database, site.site_id)

    def forbidden(*args):
        raise AssertionError("Manual source must not poll")

    service.loader = forbidden
    service.work()


def test_unchanged_poll_does_not_write_revisions(manager, static_bundle, pg_database):
    site, service, proof = registered(manager, static_bundle, pg_database, policy="auto")
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    with pg_database.connect() as c:
        before = c.scalar(select(func.count()).select_from(point_revisions))

    def same(repository, branch, site_id, known_commit):
        assert known_commit == "a" * 40
        return None, (1, 2), None

    service.loader = same
    allow_refresh(pg_database, site.site_id)
    service.work()
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(point_revisions)) == before
    assert service.status(manager.user, site.site_id)["preview"] is None


def test_populated_migration_preserves_roots_and_reverts_to_operator(
    manager, static_bundle, pg_database
):
    import os
    import subprocess
    import sys

    from test_compose_migration import ROOT

    site, service, proof = registered(manager, static_bundle, pg_database)
    preview = service.refresh(manager.user, site.site_id, proof["generation"])
    service.accept(manager.user, site.site_id, proof["generation"], preview["preview_id"])
    with pg_database.connect() as c:
        revision = c.scalar(select(points.c.current_revision_id).where(points.c.id == site.site_id))
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for command, target in [("downgrade", "0018_content_purge"), ("upgrade", "head")]:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", command, target],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    with pg_database.connect() as c:
        assert (
            c.scalar(select(points.c.current_revision_id).where(points.c.id == site.site_id))
            == revision
        )
    assert service.status(manager.user, site.site_id)["operator_managed"]
