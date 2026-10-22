from types import SimpleNamespace

import pytest
from node06_service.home_page import HomePage, render_home
from node06_service.models import point_revisions, sites
from node06_service.root_publish import publish
from node06_service.site_registry import SiteRegistry
from pydantic import ValidationError
from sqlalchemy import func, select, update
from test_root_publish import REPO, candidate
from test_site_management import create, state
from test_site_management import manager as manager_fixture


@pytest.fixture
def manager(pg_database):
    yield from manager_fixture.__wrapped__(pg_database)


PAGE = {
    "title": "Игра и мир",
    "introduction": "Любые аспекты, любые языки",
    "blocks": [
        {
            "title": "Механики",
            "description": "Правила игры",
            "links": [{"label": "Навыки", "point_id": "skills-ru"}],
        },
        {
            "title": "World",
            "description": "Public lore",
            "links": [{"label": "Играть", "url": "https://arena.geno-dice.com/"}],
        },
    ],
}


def put(manager, site, page, revision):
    return manager.client.put(
        f"/api/v1/sites/{site['site_id']}/home",
        json={"expected_settings_revision": revision, "home_page": page},
    )


def test_owner_edits_git_managed_home_without_touching_welcome(manager, pg_database):
    site = create(manager)
    SiteRegistry(pg_database).verify_site(
        site["site_id"],
        actor_user_id=manager.user,
        proof_fetcher=lambda _: site["proof_document"].encode(),
    )
    with pg_database.begin() as c:
        c.execute(update(sites).where(sites.c.id == site["site_id"]).values(welcome_source="git"))
    before = state(manager, site)
    with pg_database.connect() as c:
        revisions = c.scalar(select(func.count()).select_from(point_revisions))
    response = put(manager, site, PAGE, before["settings_revision"])
    assert response.status_code == 200, response.text
    current = response.json()
    assert current["home_page"]["blocks"][0]["title"] == "Механики"
    assert current["welcome_body"] == before["welcome_body"]
    assert current["welcome_revision_id"] == before["welcome_revision_id"]
    assert current["settings_revision"] == before["settings_revision"] + 1
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(point_revisions)) == revisions
    # No-op, stale edit, public projection and reset are separate cases.
    assert (
        put(manager, site, PAGE, current["settings_revision"]).json()["settings_revision"]
        == current["settings_revision"]
    )
    assert put(manager, site, PAGE, before["settings_revision"]).status_code == 409
    public = manager.client.get(f"/api/v1/sites/{site['site_id']}").json()
    assert public["home_page"] == current["home_page"]
    reset = put(manager, site, None, current["settings_revision"])
    assert reset.status_code == 200 and reset.json()["home_page"] is None


def test_home_auth_csrf_origin_and_inactive_guards(manager, pg_database):
    site = create(manager)
    before = state(manager, site)
    url = f"/api/v1/sites/{site['site_id']}/home"
    body = {"expected_settings_revision": before["settings_revision"], "home_page": PAGE}
    assert manager.client.put(url, json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert (
        manager.client.put(url, json=body, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    other = SiteRegistry(pg_database).create_placeholder_user("other-home-owner")
    with pg_database.begin() as c:
        c.execute(update(sites).where(sites.c.id == site["site_id"]).values(owner_user_id=other))
    assert manager.client.put(url, json=body).status_code == 403
    with pg_database.begin() as c:
        c.execute(
            update(sites)
            .where(sites.c.id == site["site_id"])
            .values(owner_user_id=manager.user, state="inactive")
        )
    assert manager.client.put(url, json=body).status_code == 409
    manager.client.cookies.clear()
    assert manager.client.put(url, json=body).status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"title": " "},
        {"blocks": [{"title": "x"}] * 13},
        {"blocks": [{"title": "x", "links": [{"label": "x", "url": "javascript:alert(1)"}]}]},
        {"blocks": [{"title": "x", "links": [{"label": "x", "url": "https://u:p@example.com"}]}]},
        {
            "blocks": [
                {
                    "title": "x",
                    "links": [{"label": "x", "point_id": "field-en", "url": "https://example.com"}],
                }
            ]
        },
        {"blocks": [{"title": "x", "links": [{"label": "x", "point_id": "../../account"}]}]},
        {"blocks": [{"title": "x", "links": [{"label": "x", "url": "https://example.com"}] * 9}]},
        {"blocks": [{"title": "x", "description": "я" * 1500}] * 12},
    ],
)
def test_layout_bounds_and_destinations(change):
    with pytest.raises(ValidationError):
        HomePage.model_validate({**PAGE, **change})


def test_safe_html_and_entrance_relative_point_links():
    page = {
        "title": "<script>alert(1)</script>",
        "blocks": [
            {
                "title": "<img src=x>",
                "description": "<iframe>",
                "links": [{"label": '" onmouseover="bad', "point_id": "skills-en"}],
            }
        ],
    }
    site = SimpleNamespace(home_page=page, id="s_" + "0" * 32)
    source = render_home(site, "Wiki", f"/embed/v1/{site.id}/")
    assert "<script>" not in source and "<img" not in source and "<iframe>" not in source
    assert "&lt;script&gt;" in source
    assert f'href="/embed/v1/{site.id}/?p=skills-en&amp;open=skills-en"' in source


def test_publication_preserves_owner_home_page(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("publish-home-owner")
    site = registry.create_pending_site(
        owner_user_id=owner, origin="https://home.example", welcome_body="Home"
    )
    registry.verify_site(
        site.site_id, actor_user_id=owner, proof_fetcher=lambda _: site.proof_document.encode()
    )
    current = registry.managed_site(site.site_id, owner)
    registry.update_home_page(
        site.site_id, owner, expected_settings_revision=current["settings_revision"], home_page=PAGE
    )
    publish(pg_database, candidate(site), REPO, "https://home.example")
    assert (
        registry.get_public_site(site.site_id).home_page
        == HomePage.model_validate(PAGE).model_dump()
    )


def test_home_page_migration_round_trip(pg_database):
    import os
    import subprocess
    import sys
    from pathlib import Path

    with pg_database.connect() as c:
        url = c.engine.url.render_as_string(hide_password=False)
    for operation, revision in (("downgrade", "0005_operator_roots"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "NODE06_DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    with pg_database.connect() as c:
        c.execute(select(sites.c.home_page))
