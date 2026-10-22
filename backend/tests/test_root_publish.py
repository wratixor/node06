import json
from dataclasses import replace

import pytest
from node06_service.models import events, point_revisions, points, root_entries, root_sources, sites
from node06_service.root_import import GitBlob, RootImportError, prepare_candidate
from node06_service.root_publish import publish
from node06_service.root_render import render_root
from node06_service.site_registry import SiteRegistry
from sqlalchemy import func, select, update

REPO = "https://github.com/example/wiki.git"
ORIGIN = "https://wiki.example"


@pytest.fixture
def registered(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("root-owner")
    site = registry.create_pending_site(
        owner_user_id=owner, origin=ORIGIN, welcome_body="UI welcome"
    )
    registry.verify_site(
        site.site_id, actor_user_id=owner, proof_fetcher=lambda _: site.proof_document.encode()
    )
    return site, owner


def candidate(site, *, body="# Привет", include=True, sha="a" * 40, home_page=None):
    specs = [{"id": "idea", "file": "idea.md", "lang": "ru"}] if include else []
    manifest = {
        "schema_version": 1,
        "site_id": site.site_id,
        "content_directory": "site-content",
        "welcome": {"file": "welcome.md", "mode": "git"},
        "points": specs,
    }
    if home_page is not None:
        manifest["home_page"] = home_page
    welcome = "# Home\n\n[Идея](md://local/idea)" if include else "# Home"
    blobs = {
        "site-content/welcome.md": GitBlob(welcome.encode()),
        "site-content/idea.md": GitBlob((body + "\n\n[Home](md://local/welcome)").encode()),
    }
    return prepare_candidate(
        json.dumps(manifest).encode(), blobs, site_id=site.site_id, commit_sha=sha
    )


def count(db, table):
    with db.connect() as c:
        return c.scalar(select(func.count()).select_from(table))


def test_publication_noop_changed_revisions_and_safe_retirement(pg_database, registered):
    site, _ = registered
    first = candidate(site)
    before = count(pg_database, point_revisions)
    assert publish(pg_database, first, REPO, ORIGIN, check=True)["writes_performed"] is False
    assert count(pg_database, point_revisions) == before
    assert count(pg_database, root_sources) == 0
    assert publish(pg_database, first, REPO, ORIGIN)["changed"] == 2
    revisions = count(pg_database, point_revisions)
    event_count = count(pg_database, events)
    assert not publish(pg_database, first, REPO, ORIGIN)["writes_performed"]
    assert count(pg_database, point_revisions) == revisions
    assert count(pg_database, events) == event_count
    # Different source SHA / rename, identical meaning: no extra point revisions.
    assert publish(pg_database, candidate(site, sha="b" * 40), REPO, ORIGIN)["changed"] == 0
    assert count(pg_database, point_revisions) == revisions
    assert (
        publish(pg_database, candidate(site, body="Changed", sha="c" * 40), REPO, ORIGIN)["changed"]
        == 1
    )
    assert (
        publish(pg_database, candidate(site, include=False, sha="d" * 40), REPO, ORIGIN)["retired"]
        == 1
    )
    with pg_database.connect() as c:
        assert (
            c.scalar(select(points.c.lifecycle).where(points.c.id.endswith("_idea"))) == "retired"
        )
        assert c.scalar(select(sites.c.welcome_source).where(sites.c.id == site.site_id)) == "git"
    # Reintroduction revives the same ID while preserving old revisions.
    assert publish(pg_database, candidate(site), REPO, ORIGIN)["changed"] == 2
    assert count(pg_database, root_entries) == 2


@pytest.mark.parametrize("case", ["wrong-origin", "pending", "owner", "repo", "revision", "ui"])
def test_binding_and_revision_changes_never_overwrite(pg_database, registered, case):
    site, _ = registered
    first = candidate(site)
    publish(pg_database, first, REPO, ORIGIN)
    repo, origin = REPO, ORIGIN
    with pg_database.begin() as c:
        if case == "wrong-origin":
            origin = "https://other.example"
        elif case == "pending":
            c.execute(update(sites).where(sites.c.id == site.site_id).values(state="pending"))
        elif case == "owner":
            other = SiteRegistry(pg_database).create_placeholder_user("new-owner")
            c.execute(update(sites).where(sites.c.id == site.site_id).values(owner_user_id=other))
        elif case == "repo":
            repo = "https://github.com/other/wiki.git"
        elif case == "ui":
            c.execute(update(sites).where(sites.c.id == site.site_id).values(welcome_source="ui"))
        else:
            c.execute(update(root_entries).values(revision_id="v_00000000000000000000000000000000"))
    before = count(pg_database, point_revisions)
    with pytest.raises(RootImportError):
        publish(pg_database, candidate(site, body="Unsafe"), repo, origin)
    assert count(pg_database, point_revisions) == before


def test_conflict_rolls_back_all_other_points(pg_database, registered):
    site, _ = registered
    first = candidate(site)
    with pg_database.begin() as c:
        c.execute(points.insert().values(id=f"r_{site.site_id[2:]}_idea", origin="user"))
    with pytest.raises(RootImportError, match="ROOT_ID_COLLISION"):
        publish(pg_database, first, REPO, ORIGIN)
    assert count(pg_database, root_sources) == 0
    with pg_database.connect() as c:
        assert c.scalar(select(sites.c.welcome_source).where(sites.c.id == site.site_id)) == "ui"


def test_external_pins_not_silently_dropped(pg_database, registered):
    site, _ = registered
    first = candidate(site)
    point = replace(first.points[0], external_revision_pins=(("field-ru", "v_" + "0" * 32),))
    with pytest.raises(RootImportError, match="EXTERNAL_PINS_NOT_YET_SUPPORTED"):
        publish(pg_database, replace(first, points=(point,)), REPO, ORIGIN)


def test_markdown_boundary_escapes_and_preserves_code():
    site_id = "s_" + "0" * 32
    body = '# Title\n<script>alert(1)</script>\n["<tag>](https://example.org/?x="evil")\n'
    body += "[мысль](md://local/idea)\n`[code](md://local/idea)`\n```\n[raw](md://local/idea)\n```"
    output = render_root(body, site_id)
    assert "<script>" not in output and "<tag>" not in output
    assert "&lt;script&gt;" in output and "&quot;evil&quot;" in output
    assert output.count("data-point-id=") == 1
    assert f'data-point-id="r_{site_id[2:]}_idea"' in output
    assert "<pre><code>" in output


def test_operator_migration_online_round_trip(pg_database):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import inspect

    with pg_database.connect() as connection:
        url = connection.engine.url.render_as_string(hide_password=False)
    env = {**os.environ, "NODE06_DATABASE_URL": url}
    root = Path(__file__).resolve().parents[2]
    for revision in ("0004_verifier_leases", "head"):
        operation = "downgrade" if revision.startswith("0004") else "upgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            env=env,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    with pg_database.connect() as connection:
        tables = inspect(connection).get_table_names()
        assert "root_entries" in tables and "root_sources" in tables


def test_cli_accepts_only_selected_remote_main(pg_database, registered, tmp_path):
    import os
    import subprocess
    import sys

    site, _ = registered
    repo = tmp_path / "content"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Root CLI fixture")
    git("remote", "add", "origin", REPO)
    content = repo / "site-content"
    content.mkdir()
    (content / "welcome.md").write_text("# Home")
    (repo / "node06-roots.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "site_id": site.site_id,
                "content_directory": "site-content",
                "welcome": {"file": "welcome.md", "mode": "git"},
                "points": [],
            }
        )
    )
    git("add", ".")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "Content fixture")
    sha = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", sha)
    with pg_database.connect() as connection:
        url = connection.engine.url.render_as_string(hide_password=False)
    env = {**os.environ, "NODE06_DATABASE_URL": url}
    args = [
        sys.executable,
        "-m",
        "node06_service.root_publish",
        "--repo",
        str(repo),
        "--commit",
        sha,
        "--site-id",
        site.site_id,
        "--origin",
        ORIGIN,
        "--repository-url",
        REPO,
    ]
    preview = subprocess.run(
        [*args, "--check"], env=env, capture_output=True, text=True, timeout=20
    )
    assert preview.returncode == 0, preview.stdout
    assert not json.loads(preview.stdout)["writes_performed"]
    assert count(pg_database, root_sources) == 0
    accepted = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
    assert accepted.returncode == 0, accepted.stdout
    assert json.loads(accepted.stdout)["writes_performed"]
    git("remote", "set-url", "origin", "https://github.com/other/wiki.git")
    refused = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
    assert refused.returncode == 1
    assert json.loads(refused.stdout)["code"] == "REPOSITORY_ORIGIN_MISMATCH"
    git("remote", "set-url", "origin", REPO)
    git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-qm", "New main")
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
    refused = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
    assert refused.returncode == 1
    assert json.loads(refused.stdout)["code"] == "REGISTERED_MAIN_SHA_REQUIRED"


def test_operator_cannot_adopt_unrecognized_git_welcome(pg_database, registered):
    site, _ = registered
    with pg_database.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == site.site_id).values(welcome_source="git")
        )
    with pytest.raises(RootImportError, match="WELCOME_ALREADY_GIT_MANAGED"):
        publish(pg_database, candidate(site), REPO, ORIGIN)
    assert count(pg_database, root_sources) == 0
