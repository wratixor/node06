import os
import subprocess
import sys
from pathlib import Path

import pytest
from node06_service.db import Database
from node06_service.models import (
    edge_claims,
    point_revisions,
    points,
    root_entries,
    sites,
)
from node06_service.root_publish import publish
from node06_service.site_registry import SiteRegistry
from sqlalchemy import inspect, select, update
from test_hosted import EMBED
from test_hosted import hosted as hosted_fixture
from test_hosted import static_bundle as bundle_fixture
from test_root_publish import REPO, candidate


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def hosted(pg_database, static_bundle):
    yield from hosted_fixture.__wrapped__(pg_database, static_bundle)


def search(client, q, **params):
    response = client.get("/api/v1/points/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_public_core_and_current_db_reads(hosted):
    _app, client, active, pending = hosted
    root = client.get("/api/v1/points/skills-ru")
    assert root.status_code == 200
    point = root.json()
    assert point["body"] and point["revision_id"] is None
    assert point["source"]["kind"] == "static-root"
    assert len(point["content_digest"]) == 64
    row = client.get("/api/v1/points/" + active.site_id)
    assert row.status_code == 200
    assert row.json()["revision_id"].startswith("v_")
    assert "<script>" not in row.json()["html"]
    assert client.get("/api/v1/points/" + pending.site_id).status_code == 404
    assert client.get("/api/v1/points/missing").status_code == 404
    assert client.get("/api/v1/points/" + active.site_id + "/revisions").status_code == 404
    assert client.get(EMBED + "/api/v1/points/" + active.site_id).status_code == 404
    assert "public_point_read" in client.get("/api/v1/meta").json()["implemented"]


def test_paged_bridge_parity_legacy_and_revocation(hosted, pg_database):
    _app, client, active, pending = hosted
    api = EMBED + f"/bridge/v1/{active.site_id}/read"
    body = "Начало " * 80 + " ВоЛшЕбСтВо farawayword"
    publish(pg_database, candidate(active, body=body), REPO, "https://garden.example")
    pid = f"r_{active.site_id[2:]}_idea"
    page = client.get(api, params={"method": "points.searchPage", "query": "ВОЛШЕБ", "limit": 1})
    assert page.status_code == 200
    assert page.json() == search(client, "ВОЛШЕБ", limit=1)
    assert page.json()["items"][0]["id"] == pid
    assert (
        client.get(api, params={"method": "point.read", "point_id": pid}).json()
        == client.get("/api/v1/points/" + pid).json()
    )
    assert (
        client.get(api, params={"method": "point.neighbors", "point_id": pid, "limit": 1}).json()
        == client.get("/api/v1/points/" + pid + "/neighbors", params={"limit": 1}).json()
    )
    legacy = client.get(api, params={"method": "points.search", "query": "farawayword"}).json()
    assert legacy == {"items": [], "truncated": False}
    capabilities = client.get(api, params={"method": "capabilities.get"}).json()
    assert {"point.read", "points.searchPage", "point.neighbors"} <= set(capabilities["methods"])
    assert (
        client.get(api, params={"method": "point.read", "point_id": pending.site_id}).status_code
        == 404
    )
    with pg_database.begin() as c:
        c.execute(update(sites).where(sites.c.id == active.site_id).values(state="inactive"))
    assert (
        client.get(api, params={"method": "points.searchPage", "query": "ВОЛШЕБ"}).status_code
        == 404
    )


def test_paged_bridge_input_bounds_and_cursors(hosted):
    _app, client, active, _pending = hosted
    api = EMBED + f"/bridge/v1/{active.site_id}/read"
    first = client.get(
        api, params={"method": "points.searchPage", "query": "skill", "limit": 1}
    ).json()
    assert first["next_cursor"]
    second = client.get(
        api,
        params={
            "method": "points.searchPage",
            "query": "skill",
            "limit": 1,
            "after": first["next_cursor"],
        },
    ).json()
    assert second["items"][0]["id"] > first["items"][0]["id"]
    for params in [
        {"method": "points.searchPage", "query": "skill", "limit": "1.5"},
        {"method": "points.searchPage", "query": "skill", "limit": "51"},
        {"method": "points.searchPage", "query": "skill", "after": "../bad"},
        {"method": "points.searchPage", "query": "skill", "url": "https://evil.example"},
        {"method": "point.read", "point_id": "skills-ru", "limit": 1},
        {"method": "point.neighbors", "point_id": "../secret"},
    ]:
        assert client.get(api, params=params).status_code == 400
    assert client.get(api + "?method=points.searchPage&query=skill&query=other").status_code == 400
    assert (
        client.get(
            api.replace(EMBED, ""), params={"method": "point.read", "point_id": "skills-ru"}
        ).status_code
        == 404
    )


def test_full_body_prefix_search_and_stale_revision_is_not_searchable(hosted, pg_database):
    _app, client, active, _pending = hosted
    extra = " Начало " * 80 + "уникальнопоздний ВоЛшЕбСтВо Straße"
    publish(pg_database, candidate(active, body=extra), REPO, "https://garden.example")
    pid = f"r_{active.site_id[2:]}_idea"
    with pg_database.connect() as c:
        accepted_digest = c.execute(
            select(root_entries.c.content_digest).where(root_entries.c.point_id == pid)
        ).scalar_one()
    assert client.get("/api/v1/points/" + pid).json()["content_digest"] == accepted_digest
    matches = search(client, "уникальнопоз")
    assert [p["id"] for p in matches["items"]] == [pid]
    assert "body" not in matches["items"][0] and "html" not in matches["items"][0]
    assert (
        matches["items"][0]["revision_id"]
        == client.get("/api/v1/points/" + pid).json()["revision_id"]
    )
    assert search(client, "ВОЛШЕБ")["items"][0]["id"] == pid
    assert search(client, "STRASSE")["items"][0]["id"] == pid
    assert search(client, "private pending")["items"] == []
    # The GIN index can find old revisions; visibility still pins the current one.
    publish(
        pg_database,
        candidate(active, body="Новая формулировка", sha="b" * 40),
        REPO,
        "https://garden.example",
    )
    assert search(client, "уникальнопоз")["items"] == []
    assert search(client, "формулир")["items"][0]["id"] == pid
    with pg_database.begin() as c:
        c.execute(
            update(root_entries)
            .where(root_entries.c.point_id == pid)
            .values(revision_id="v_00000000000000000000000000000000")
        )
    assert search(client, "формулир")["items"] == []
    assert client.get("/api/v1/points/" + pid).status_code == 404
    assert pid not in {p["id"] for p in client.get("/data/points.json").json()}


def test_source_visibility_retired_roots_and_undeclared_rows(hosted, pg_database):
    _app, client, active, _pending = hosted
    publish(
        pg_database, candidate(active, body="Rarevisibilityword"), REPO, "https://garden.example"
    )
    pid = f"r_{active.site_id[2:]}_idea"
    assert search(client, "rarevisibility")["items"][0]["id"] == pid
    with pg_database.begin() as c:
        c.execute(update(sites).where(sites.c.id == active.site_id).values(state="inactive"))
    assert search(client, "rarevisibility")["items"] == []
    assert client.get("/api/v1/points/" + pid).status_code == 404
    with pg_database.begin() as c:
        c.execute(update(sites).where(sites.c.id == active.site_id).values(state="active"))
        c.execute(points.insert().values(id="p_not_published", origin="user"))
        c.execute(
            point_revisions.insert().values(
                id="v_" + "8" * 32, point_id="p_not_published", body="Rarevisibilityunpublished"
            )
        )
        c.execute(
            update(points)
            .where(points.c.id == "p_not_published")
            .values(current_revision_id="v_" + "8" * 32)
        )
    assert search(client, "Rarevisibilityunpublished")["items"] == []
    publish(
        pg_database, candidate(active, include=False, sha="c" * 40), REPO, "https://garden.example"
    )
    assert search(client, "rarevisibility")["items"] == []


def test_directory_neighbors_cursor_and_unclaimed_edges_are_excluded(hosted, pg_database):
    _app, client, active, pending = hosted
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("neighbor-owner")
    for index in range(3):
        site = registry.create_pending_site(
            owner_user_id=owner, origin=f"https://neighbor{index}.example", welcome_body="Neighbor"
        )
        proof_document = site.proof_document.encode()
        registry.verify_site(
            site.site_id,
            actor_user_id=owner,
            proof_fetcher=lambda _, proof=proof_document: proof,
        )
    ids = []
    cursor = ""
    while True:
        response = client.get(
            "/api/v1/points/all-sites/neighbors", params={"after": cursor, "limit": 2}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        ids.extend(p["id"] for p in page["items"])
        if not page["next_cursor"]:
            break
        cursor = page["next_cursor"]
    assert len(ids) == len(set(ids)) == 4 and pending.site_id not in ids
    publish(pg_database, candidate(active), REPO, "https://garden.example")
    pid = f"r_{active.site_id[2:]}_idea"
    assert active.site_id in client.get("/api/v1/points/" + pid).json()["links"]
    with pg_database.begin() as c:
        c.execute(edge_claims.delete().where(edge_claims.c.claim_kind == "operator-git-root"))
    assert client.get("/api/v1/points/" + pid).json()["links"] == []
    core = client.get("/api/v1/points/skills-en/neighbors", params={"limit": 1}).json()
    assert len(core["items"]) == 1 and core["next_cursor"]


def test_search_cursors_input_guards_and_no_html_in_briefs(hosted):
    _app, client, _active, _pending = hosted
    seen = []
    cursor = ""
    while True:
        page = search(client, "skill", after=cursor, limit=1)
        seen.extend(p["id"] for p in page["items"])
        if not page["next_cursor"]:
            break
        cursor = page["next_cursor"]
    assert seen == sorted(set(seen)) and {"skills-en", "skills-ru"} <= set(seen)
    assert client.get("/api/v1/points/search?q=a&q=b").status_code == 400
    assert client.get("/api/v1/points/search?q=skill&secret=x").status_code == 400
    assert client.get("/api/v1/points/search?q=skill&limit=51").status_code == 422
    assert (
        client.get("/api/v1/points/search", params={"q": " ".join(["term"] * 9)}).status_code == 422
    )
    assert client.get("/api/v1/points/search", params={"q": " "}).status_code == 422
    assert search(client, "zznoexist' OR 1=1 --")["items"] == []
    assert search(client, "nonexistent%_")["items"] == []


def test_response_budget_and_unconfigured_database(hosted):
    app, client, _active, _pending = hosted
    root = app.state.hosted_bundle.roots[0]
    original = dict(root)
    try:
        root["body"] = "Большой текст " * 30000
        assert client.get("/api/v1/points/" + root["id"]).status_code == 413
    finally:
        root.clear()
        root.update(original)
    app.state.database = Database(None)
    response = client.get("/api/v1/points/search?q=skill")
    assert response.status_code == 503
    assert response.json() == {"code": "DATABASE_NOT_CONFIGURED"}


def test_migration_index_online_round_trip(hosted, pg_database):
    _app, client, active, _pending = hosted
    body = "До миграции ВоЛшЕбСтВо Straße"
    publish(pg_database, candidate(active, body=body), REPO, "https://garden.example")
    pid = f"r_{active.site_id[2:]}_idea"
    with pg_database.connect() as c:
        stored_body = c.execute(
            select(point_revisions.c.body).where(point_revisions.c.point_id == pid)
        ).scalar_one()
    with pg_database.connect() as c:
        url = c.engine.url.render_as_string(hide_password=False)
    for operation, revision in [("downgrade", "0007_git_home"), ("upgrade", "head")]:
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
        assert (
            c.execute(
                select(point_revisions.c.search_text).where(point_revisions.c.point_id == pid)
            ).scalar_one()
            == stored_body.casefold()
        )
        indexes = inspect(c).get_indexes("point_revisions")
        assert any(
            i["name"] == "ix_point_revisions_search_simple"
            and i["dialect_options"]["postgresql_using"] == "gin"
            for i in indexes
        )
    assert search(client, "ВОЛШЕБ STRASSE")["items"]
