from copy import deepcopy

import pytest
from node06_service.home_page import render_home, resolve_home
from node06_service.models import point_revisions, sites
from node06_service.root_import import RootImportError
from node06_service.root_publish import publish
from node06_service.site_registry import SiteConflictError, SiteRegistry
from sqlalchemy import func, select
from test_home_page import PAGE
from test_root_import import SITE, fixture_source
from test_root_import import candidate as import_candidate
from test_root_publish import ORIGIN, REPO, candidate
from test_root_publish import registered as root_site_fixture
from test_site_management import create, state
from test_site_management import manager as manager_fixture


@pytest.fixture
def registered(pg_database):
    return root_site_fixture.__wrapped__(pg_database)


@pytest.fixture
def manager(pg_database):
    yield from manager_fixture.__wrapped__(pg_database)


GIT_PAGE = {
    "title": "Repository home",
    "blocks": [{"title": "Ideas", "links": [{"label": "Idea", "point_id": "local/idea"}]}],
}


def test_git_home_is_immutable_candidate_metadata_not_point_meaning():
    manifest, blobs = fixture_source()
    before = import_candidate(manifest, blobs)
    manifest["home_page"] = {
        "title": "Git start",
        "blocks": [
            {
                "title": "Thought",
                "links": [
                    {"label": "Start", "point_id": "local/welcome"},
                    {"label": "Thought", "point_id": "local/thought"},
                ],
            }
        ],
    }
    after = import_candidate(manifest, blobs)
    assert before.digest != after.digest
    assert [p.content_digest for p in before.points] == [p.content_digest for p in after.points]
    assert after.home_page.blocks[0].links[0].point_id == SITE
    assert after.home_page.blocks[0].links[1].point_id == f"r_{SITE[2:]}_thought"
    view = after.home_page
    view.blocks.clear()
    assert len(after.home_page.blocks) == 1
    assert after.summary()["home_block_count"] == 1
    assert "Git start" not in str(after.summary())
    manifest["home_page"]["blocks"][0]["links"][0]["point_id"] = "local/missing"
    with pytest.raises(RootImportError, match="HOME_LOCAL_TARGET_MISSING"):
        import_candidate(manifest, blobs)


@pytest.mark.parametrize(
    "mode,git,ui,expected",
    [
        ("auto", True, True, "git"),
        ("auto", False, True, "ui"),
        ("auto", False, False, "welcome"),
        ("git", False, True, "welcome"),
        ("ui", True, False, "welcome"),
        ("ui", True, True, "ui"),
        ("welcome", True, True, "welcome"),
    ],
)
def test_priority_is_explicit(mode, git, ui, expected):
    value, source = resolve_home(PAGE if ui else None, GIT_PAGE if git else None, mode)
    assert source == expected
    assert (value is None) == (expected == "welcome")


def test_published_git_home_priority_source_switching_and_removal(pg_database, registered):
    site, owner = registered
    registry = SiteRegistry(pg_database)
    first = candidate(site, home_page=GIT_PAGE)
    with pg_database.connect() as c:
        revisions = c.scalar(select(func.count()).select_from(point_revisions))
    assert publish(pg_database, first, REPO, ORIGIN)["home_changed"]
    current = registry.get_public_site(site.site_id)
    assert current.home_page_source == "auto" and current.effective_home_source == "git"
    assert (
        current.git_home_page["blocks"][0]["links"][0]["point_id"] == f"r_{site.site_id[2:]}_idea"
    )
    assert "Repository home" in render_home(current, "Wiki", "/")
    assert not publish(pg_database, first, REPO, ORIGIN)["writes_performed"]
    managed = registry.managed_site(site.site_id, owner)
    registry.update_home_page(
        site.site_id,
        owner,
        expected_settings_revision=managed["settings_revision"],
        home_page=PAGE,
        home_page_source="ui",
    )
    second_page = deepcopy(GIT_PAGE)
    second_page["title"] = "Changed Git home"
    publish(pg_database, candidate(site, home_page=second_page, sha="b" * 40), REPO, ORIGIN)
    current = registry.get_public_site(site.site_id)
    assert current.effective_home_source == "ui" and current.home_page["title"] == PAGE["title"]
    assert current.git_home_page["title"] == "Changed Git home"
    # Layout-only edits create no extra semantic point revisions.
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(point_revisions)) == revisions + 2
    with pytest.raises(SiteConflictError):
        registry.update_home_page(
            site.site_id,
            owner,
            expected_settings_revision=managed["settings_revision"],
            home_page=PAGE,
            home_page_source="git",
        )
    managed = registry.managed_site(site.site_id, owner)
    registry.update_home_page(
        site.site_id,
        owner,
        expected_settings_revision=managed["settings_revision"],
        home_page=PAGE,
        home_page_source="auto",
    )
    assert registry.get_public_site(site.site_id).effective_home_source == "git"
    publish(pg_database, candidate(site, sha="c" * 40), REPO, ORIGIN)
    current = registry.get_public_site(site.site_id)
    assert current.git_home_page is None and current.effective_home_source == "ui"
    assert current.home_page["title"] == PAGE["title"]


def test_owner_api_selects_priority_without_deleting_either_snapshot(manager, pg_database):
    site = create(manager)
    current = state(manager, site)
    path = f"/api/v1/sites/{site['site_id']}/home"
    response = manager.client.put(
        path,
        json={
            "expected_settings_revision": current["settings_revision"],
            "home_page": PAGE,
            "home_page_source": "auto",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["effective_home_source"] == "ui"
    response = manager.client.put(
        path,
        json={
            "expected_settings_revision": response.json()["settings_revision"],
            "home_page": PAGE,
            "home_page_source": "welcome",
        },
    )
    assert response.status_code == 200
    assert response.json()["home_page"]["title"] == PAGE["title"]
    assert response.json()["effective_home_page"] is None
    bad = manager.client.put(
        path,
        json={
            "expected_settings_revision": response.json()["settings_revision"],
            "home_page": None,
            "home_page_source": "remote-script",
        },
    )
    assert bad.status_code == 422


def test_migration_preserves_existing_ui_choice(pg_database, registered):
    import os
    import subprocess
    import sys
    from pathlib import Path

    site, _ = registered
    with pg_database.connect() as c:
        url = c.engine.url.render_as_string(hide_password=False)

    def migrate(operation, revision):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "NODE06_DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    migrate("downgrade", "0006_home_page")
    with pg_database.begin() as c:
        c.execute(sites.update().where(sites.c.id == site.site_id).values(home_page=PAGE))
    migrate("upgrade", "head")
    with pg_database.connect() as c:
        row = c.execute(select(sites).where(sites.c.id == site.site_id)).mappings().one()
        assert row["home_page_source"] == "ui"
        assert row["home_page"] == PAGE
        assert row["git_home_page"] is None
