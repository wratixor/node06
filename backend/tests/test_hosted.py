import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from node06_service.config import Settings
from node06_service.main import create_app
from node06_service.models import sites
from node06_service.site_registry import SiteRegistry
from sqlalchemy import update

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://wiki.example"
EMBED = "https://embed.example"


@pytest.fixture(scope="session")
def static_bundle():
    subprocess.run([sys.executable, "build.py"], cwd=ROOT, check=True, capture_output=True)
    return ROOT / "dist"


@pytest.fixture
def hosted(pg_database, static_bundle):
    app = create_app(
        Settings(
            management_origin=ORIGIN,
            embed_origin=EMBED,
            hosted_dist=static_bundle,
        )
    )
    app.state.database = pg_database
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("hosted-owner")
    active = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://garden.example",
        display_name='<img src=x onerror="alert(1)">',
        welcome_body="<script>window.stolen=1</script>言葉",
    )
    registry.verify_site(
        active.site_id, actor_user_id=owner, proof_fetcher=lambda _: active.proof_document.encode()
    )
    pending = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://pending.example",
        welcome_body="private pending welcome",
    )
    with TestClient(app, base_url=ORIGIN) as client:
        yield app, client, active, pending


def test_shared_public_projection_escapes_site_text_and_hides_pending(hosted):
    _app, client, active, pending = hosted
    response = client.get("/data/points.json")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    points = {point["id"]: point for point in response.json()}
    assert len(points) == 53
    assert "field-ru" in points and "field-en" in points
    assert pending.site_id not in points and "private pending welcome" not in response.text
    assert "nonce=" not in response.text and "challenge_digest" not in response.text
    assert points[active.site_id]["links"] == ["all-sites"]
    assert points["all-sites"]["links"] == [active.site_id]
    assert "&lt;script&gt;" in points[active.site_id]["html"]
    assert "<script>" not in points[active.site_id]["html"]
    assert points[active.site_id]["coordinates"] is None
    assert points[active.site_id]["coordinate_source"] == "display-only"
    assert {"hosted_wiki", "read_only_embed", "site_management_ui"} <= set(
        client.get("/api/v1/meta").json()["implemented"]
    )


def test_site_shell_default_theme_and_exact_embed_policy(hosted, pg_database):
    app, client, active, pending = hosted
    with pg_database.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == active.site_id).values(theme={"bg": "#123"})
        )
    path = f"/sites/{active.site_id}/"
    response = client.get(path)
    assert response.status_code == 200
    assert f'data-home-point="{active.site_id}"' in response.text
    assert "&quot;bg&quot;: &quot;#123&quot;" in response.text
    assert "<img src=x onerror=" not in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get(f"/sites/{pending.site_id}/").status_code == 404
    embed_path = f"/embed/v1/{active.site_id}/"
    assert client.get(embed_path).status_code == 404
    response = client.get(EMBED + embed_path)
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert f"frame-ancestors https://garden.example {ORIGIN}" in csp
    assert "*" not in csp
    assert "x-frame-options" not in response.headers
    assert "set-cookie" not in response.headers
    assert "READ ONLY / SHARED GRAPH" in response.text
    assert client.get(EMBED + f"/embed/v1/{pending.site_id}/").status_code == 404
    app.state.settings.default_site_id = active.site_id
    assert f'data-home-point="{active.site_id}"' in client.get("/").text


def test_embed_host_denies_all_management_surfaces_even_with_cookie(hosted):
    _app, client, active, _pending = hosted
    for method, path in [
        ("GET", "/account/"),
        ("GET", "/sites/"),
        ("GET", "/api/v1/me"),
        ("GET", "/api/v1/me/sites"),
        ("GET", "/api/v1/me/feed"),
        ("GET", "/api/v1/ui-config"),
        ("GET", f"/api/v1/sites/{active.site_id}/manage"),
        ("POST", "/api/v1/auth/login"),
        ("PATCH", f"/api/v1/sites/{active.site_id}"),
    ]:
        response = client.request(
            method,
            EMBED + path,
            headers={"Origin": ORIGIN, "Cookie": "__Host-node06-session=" + "x" * 43},
            json={},
        )
        assert response.status_code == 404, path
        assert response.headers["cache-control"] == "no-store"
    assert client.get(EMBED + f"/api/v1/sites/{active.site_id}").status_code == 200
    assert client.get(EMBED + "/data/points.json").status_code == 200


def test_graph_limit_is_explicit_and_never_silently_truncates(hosted, pg_database):
    app, client, _active, _pending = hosted
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("second-owner")
    second = registry.create_pending_site(
        owner_user_id=owner, origin="https://second.example", welcome_body="Hi"
    )
    registry.verify_site(
        second.site_id, actor_user_id=owner, proof_fetcher=lambda _: second.proof_document.encode()
    )
    app.state.settings.hosted_site_limit = 1
    response = client.get("/data/points.json")
    assert response.status_code == 503
    assert response.json() == {"code": "GRAPH_CAPACITY_EXCEEDED"}


def test_hosted_assets_canonical_aliases_and_safe_filename_binding(hosted, static_bundle):
    _app, client, _active, _pending = hosted
    response = client.get("/")
    assert response.status_code == 200 and "Geno-Dice Wiki" in response.text
    assert "MY SITES" in response.text
    assert (
        client.get("/ru/?p=field-en", follow_redirects=False).headers["location"] == "/?p=field-en"
    )
    assert (
        client.get("/p/field-ru/", follow_redirects=False).headers["location"]
        == "/?p=field-ru&open=field-ru"
    )
    assert client.get("/assets/site.js").status_code == 200
    icon = client.get("/favicon.svg?filename=/etc/passwd")
    assert icon.content == (static_bundle / "favicon.svg").read_bytes()
    manifest = client.get("/site.webmanifest").json()
    assert all(client.get(item["src"]).status_code == 200 for item in manifest["icons"])
    assert client.get("/assets/../../pyproject.toml").status_code == 404


def test_management_ui_assets_deny_framing_and_do_not_interpolate_content(hosted):
    _app, client, _active, _pending = hosted
    for path in ("/sites/", "/sites/client.js", "/sites/style.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/api/v1/ui-config").status_code == 401
    script = client.get("/sites/client.js").text
    assert "innerHTML" not in script


def test_missing_database_has_explicit_public_failure(static_bundle):
    app = create_app(Settings(management_origin=ORIGIN, hosted_dist=static_bundle))
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/data/points.json").status_code == 503
        app.state.settings.default_site_id = "s_" + "0" * 32
        assert client.get("/").json()["code"] == "DATABASE_NOT_CONFIGURED"
        assert client.get("/").status_code == 503
        assert "hosted_wiki" in client.get("/api/v1/meta").json()["implemented"]
        assert "read_only_embed" not in client.get("/api/v1/meta").json()["implemented"]


@pytest.mark.parametrize(
    "management,embed",
    [
        ("https://same.example:443", "https://same.example:8443"),
        (ORIGIN, "http://embed.example"),
        (None, EMBED),
        (ORIGIN, EMBED + "/path"),
        (ORIGIN, EMBED + ":443"),
        (ORIGIN, "https://EMBED.example"),
    ],
)
def test_invalid_cookie_isolation_or_origin_fails_startup(management, embed):
    with pytest.raises(ValueError):
        create_app(Settings(management_origin=management, embed_origin=embed))


def test_bridge_document_and_anonymous_api_boundary(hosted):
    _app, client, active, pending = hosted
    path = f"/bridge/v1/{active.site_id}/"
    assert client.get(path).status_code == 404
    doc = client.get(EMBED + path)
    assert doc.status_code == 200
    assert (
        f"frame-ancestors https://garden.example {ORIGIN}" in doc.headers["content-security-policy"]
    )
    assert "set-cookie" not in doc.headers
    assert client.get(EMBED + f"/bridge/v1/{pending.site_id}/").status_code == 404
    assert client.get(EMBED + "/bridge/assets/bridge.js").status_code == 200
    api = EMBED + path + "read"
    caps = client.get(api, params={"method": "capabilities.get"})
    assert caps.json()["read_only"] is True
    assert "public_read_bridge" in client.get("/api/v1/meta").json()["implemented"]
    assert client.post(api, json={"method": "point.createIntent"}).status_code == 405
    assert (
        client.get(api, params={"method": "point.createIntent"}).json()["code"]
        == "METHOD_NOT_ALLOWED"
    )
    assert (
        client.get(api, params={"method": "site.get", "url": "https://evil.example"}).status_code
        == 400
    )
    assert client.get(api + "?method=site.get&method=point.get").status_code == 400


def test_bridge_reads_same_graph_and_bounded_search(hosted):
    _app, client, active, pending = hosted
    api = EMBED + f"/bridge/v1/{active.site_id}/read"
    assert (
        client.get(api, params={"method": "site.get"}).json()["welcome_point_id"] == active.site_id
    )
    for point_id in (active.site_id, "field-ru", "field-en", "all-sites"):
        result = client.get(api, params={"method": "point.get", "point_id": point_id})
        assert result.status_code == 200
        assert result.json()["id"] == point_id
    assert (
        client.get(api, params={"method": "point.get", "point_id": pending.site_id}).status_code
        == 404
    )
    result = client.get(api, params={"method": "points.search", "query": "skill"}).json()
    assert 0 < len(result["items"]) <= 20
    assert set(result["items"][0]) == {"id", "preview"}
    assert (
        client.get(api, params={"method": "points.search", "query": "x" * 129}).status_code == 400
    )


def test_bridge_revoked_site_and_oversize_reads_fail_closed(hosted, pg_database, monkeypatch):
    app, client, active, _pending = hosted
    api = EMBED + f"/bridge/v1/{active.site_id}/read"
    monkeypatch.setattr(
        app.state.hosted_bundle,
        "graph",
        lambda _, site_id=None: [{"id": "large", "html": "x" * 270000}],
    )
    assert client.get(api, params={"method": "point.get", "point_id": "large"}).status_code == 413
    with pg_database.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == active.site_id).values(state="inactive")
        )
    assert client.get(api, params={"method": "capabilities.get"}).status_code == 404
    assert client.get(EMBED + f"/bridge/v1/{active.site_id}/").status_code == 404


def test_operator_roots_visible_through_hosted_and_embed_graph(hosted, pg_database):
    from node06_service.root_publish import publish
    from test_root_publish import REPO, candidate

    _app, client, active, _pending = hosted
    publish(pg_database, candidate(active), REPO, "https://garden.example")
    response = client.get("/data/points.json")
    assert response.status_code == 200
    graph = {p["id"]: p for p in response.json()}
    root_id = f"r_{active.site_id[2:]}_idea"
    assert graph[root_id]["lang"] == "ru"
    assert root_id in graph[active.site_id]["links"]
    assert "all-sites" in graph[active.site_id]["links"]
    assert "data-point-id=" in graph[active.site_id]["html"]
    assert graph[root_id]["source"]["commit_sha"] == "a" * 40
    assert client.get(EMBED + "/data/points.json").json() == response.json()
    # Revoking the entry hides its roots as well as its welcome.
    with pg_database.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == active.site_id).values(state="inactive")
        )
    graph = {p["id"]: p for p in client.get("/data/points.json").json()}
    assert active.site_id not in graph and root_id not in graph


def test_custom_home_blocks_and_scoped_links_for_all_entrances(hosted, pg_database):
    from test_home_page import PAGE

    _app, client, active, _pending = hosted
    with pg_database.begin() as connection:
        connection.execute(update(sites).where(sites.c.id == active.site_id).values(home_page=PAGE))
    path = f"/sites/{active.site_id}/"
    response = client.get(path)
    assert response.status_code == 200
    assert 'data-home-page="true"' in response.text
    assert "<h2>Механики</h2>" in response.text and "<h2>World</h2>" in response.text
    assert f'href="{path}?p=skills-ru&amp;open=skills-ru"' in response.text
    assert f'href="{path}"' in response.text
    assert "Точка Geno-Dice" not in response.text
    embedded = client.get(EMBED + f"/embed/v1/{active.site_id}/")
    assert f'href="/embed/v1/{active.site_id}/?p=skills-ru&amp;open=skills-ru"' in embedded.text
    assert client.put(EMBED + f"/api/v1/sites/{active.site_id}/home", json={}).status_code == 404
    assert client.get("/sites/home.js").status_code == 200


def test_setup_and_all_copies_link_to_configured_management(hosted):
    _app, client, active, _pending = hosted
    for path in ("/", "/setup/", "/setup/en/", "/about/", f"/sites/{active.site_id}/"):
        response = client.get(path)
        assert response.status_code == 200
        assert "wiki.geno-dice.com/account/" not in response.text
        assert 'href="/sites/"' in response.text or f'href="{ORIGIN}/sites/"' in response.text
        assert 'href="/account/"' in response.text or f'href="{ORIGIN}/account/"' in response.text
        assert 'href="/setup/"' in response.text or 'href="/setup/en/"' in response.text
    embedded = client.get(f"{EMBED}/embed/v1/{active.site_id}/")
    assert embedded.status_code == 200
    assert f'href="{ORIGIN}/sites/"' in embedded.text
    assert f'href="{ORIGIN}/setup/en/"' in embedded.text
    assert "режим" in client.get("/setup/").text.lower()


def test_social_bridge_is_bounded_public_read_and_pins_match_display(hosted):
    from node06_service.public_points import PublicPoints
    from node06_service.social import Social

    app, client, active, pending = hosted
    public = PublicPoints(app.state.database, roots=app.state.hosted_bundle.roots)
    Social(public).work()
    api = f"{EMBED}/bridge/v1/{active.site_id}/read"
    direct = client.get("/api/v1/points/skills-ru/social-summary").json()
    bridged = client.get(api, params={"method": "point.social", "point_id": "skills-ru"})
    assert bridged.status_code == 200
    assert bridged.json() == direct
    assert (
        "point.social" in client.get(api, params={"method": "capabilities.get"}).json()["methods"]
    )
    for extras in ({"after": ""}, {"limit": 1}, {"user_id": "forged"}):
        assert (
            client.get(
                api, params={"method": "point.social", "point_id": "skills-ru", **extras}
            ).status_code
            == 400
        )
    assert (
        client.get(api, params={"method": "point.social", "point_id": pending.site_id}).status_code
        == 404
    )
    graph = client.get("/data/points.json").json()
    for pid in ("skills-ru", active.site_id, "all-sites"):
        displayed = next(p for p in graph if p["id"] == pid)
        current = client.get(f"/api/v1/points/{pid}/social-summary").json()
        assert displayed["content_digest"] == current["content_digest"]
        assert displayed["revision_id"] == current["revision_id"]


def test_installation_guides_are_separate_documents(hosted):
    _, client, _, _ = hosted
    ru, en = client.get("/setup/").text, client.get("/setup/en/").text
    assert '<html lang="ru">' in ru and '<html lang="en">' in en
    assert "Режим 5" in ru and "Mode 5" not in ru
    assert "Mode 5" in en and "Режим 5" not in en
    assert "УСТАНОВКА" in ru and ">SETUP<" in en
    assert "SETUP /" not in ru + en
    assert "<h1>NODE06: своя вики</h1>" in ru
    assert "<h2>Mode 5" in en


def test_geometry_bridge_matches_anonymous_read_and_rejects_extra_authority(hosted):
    from node06_service.public_points import PublicPoints
    from node06_service.social import Social

    app, client, active, pending = hosted
    public = PublicPoints(app.state.database, roots=app.state.hosted_bundle.roots)
    Social(public).work()
    api = f"{EMBED}/bridge/v1/{active.site_id}/read"
    direct = client.get("/api/v1/geometry", params={"ids": "skills-ru,skills-en"})
    bridged = client.get(
        api, params={"method": "points.geometry", "point_ids": "skills-ru,skills-en"}
    )
    assert bridged.status_code == 200 and bridged.json() == direct.json()
    assert (
        "points.geometry"
        in client.get(api, params={"method": "capabilities.get"}).json()["methods"]
    )
    assert (
        client.get(api, params={"method": "points.geometry", "point_ids": pending.site_id}).json()[
            "items"
        ]
        == []
    )
    for params in (
        {"point_ids": "skills-ru,skills-ru"},
        {"point_ids": "../secret"},
        {"point_ids": "skills-ru", "user_id": "forged"},
        {"point_ids": "skills-ru", "limit": 64},
    ):
        assert client.get(api, params={"method": "points.geometry", **params}).status_code == 400


def test_site_source_author_is_public_owner_and_directory_is_system(hosted):
    _, client, active, _ = hosted
    site = client.get(f"/api/v1/points/{active.site_id}").json()
    assert site["author"]["name"] == "hosted-owner"
    assert site["author"]["kind"] == "user"
    directory = client.get("/api/v1/points/all-sites").json()
    assert directory["author"] == {"kind": "system", "name": "System"}
    root = client.get("/api/v1/points/skills-ru").json()
    assert root["author"] == {"kind": "source", "name": "Git source"}


def test_embedded_draft_is_anonymous_scoped_and_confirmation_unframeable(hosted, pg_database):
    _, client, active, pending = hosted
    draft = f"/compose/v1/{active.site_id}/"
    response = client.get(EMBED + draft)
    assert response.status_code == 200
    assert 'data-external-editor="true"' in response.text
    assert 'data-search-site="' + active.site_id in response.text
    assert "/compose/assets/client.js" in response.text
    assert (
        "frame-ancestors https://garden.example https://embed.example"
        in response.headers["content-security-policy"]
    )
    assert "set-cookie" not in response.headers
    assert client.get(draft).status_code == 404
    assert client.get(EMBED + f"/compose/v1/{pending.site_id}/").status_code == 404
    assert (
        client.get(EMBED + draft, params={"parent_origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get(EMBED + draft, params={"parent_origin": EMBED}).status_code == 200
    for path in ("/compose/assets/client.js", "/compose/assets/style.css"):
        assert client.get(EMBED + path).status_code == 200
    approval = f"/editor/confirm/{active.site_id}/"
    confirmation = client.get(approval)
    assert confirmation.status_code == 200
    assert confirmation.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in confirmation.headers["content-security-policy"]
    assert client.get(EMBED + approval).status_code == 404
    library = f"/editor/library/{active.site_id}/"
    assert client.get(library).status_code == 200
    assert client.get(library).headers["x-frame-options"] == "DENY"
    assert client.get(EMBED + library).status_code == 404
    assert client.get(f"/editor/library/{pending.site_id}/").status_code == 404
    assert client.get(EMBED + "/people/u_" + "1" * 32 + "/").status_code == 404

    assert client.get(EMBED + "/api/v1/me").status_code == 404
    assert client.post(EMBED + "/api/v1/points", json={}).status_code == 404
    with pg_database.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == active.site_id).values(state="inactive")
        )
    assert client.get(EMBED + draft).status_code == 404
    assert client.get(approval).status_code == 404


def test_hosted_corner_uses_instance_git_home_not_current_tenant(hosted, pg_database):
    import re

    app, client, current, _ = hosted
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("wiki-home-owner")
    home = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://lore.example",
        display_name="Lore",
        welcome_body="Wiki welcome",
    )
    registry.verify_site(
        home.site_id, actor_user_id=owner, proof_fetcher=lambda _: home.proof_document.encode()
    )
    app.state.settings.default_site_id = home.site_id
    with pg_database.begin() as c:
        c.execute(
            update(sites)
            .where(sites.c.id == home.site_id)
            .values(
                git_home_page={"title": "Geno-Dice: Wiki <safe>", "blocks": []},
                home_page_source="git",
            )
        )
        c.execute(
            update(sites)
            .where(sites.c.id == current.site_id)
            .values(home_page={"title": "Other tenant", "blocks": []}, home_page_source="ui")
        )
    for path in ("/", f"/sites/{current.site_id}/", f"/sites/{current.site_id}/?p=point-ru"):
        response = client.get(path)
        assert response.status_code == 200
        corner = re.search(r'<a class="site-home-link" href="([^"]*)">(.*?)</a>', response.text)
        assert corner.groups() == ("/", "Geno-Dice: Wiki &lt;safe&gt;")
    tenant = client.get(f"/sites/{current.site_id}/").text
    assert "<h1>Other tenant</h1>" in tenant
    frame = client.get(EMBED + f"/embed/v1/{current.site_id}/").text
    corner = re.search(r'<a class="site-home-link" href="([^"]*)">(.*?)</a>', frame)
    assert corner.group(1) == f"/embed/v1/{current.site_id}/"
    assert "Geno-Dice: Wiki" not in corner.group(2)
    with pg_database.begin() as c:
        c.execute(
            update(sites)
            .where(sites.c.id == home.site_id)
            .values(git_home_page={"title": "Updated Wiki", "blocks": []})
        )
    assert ">Updated Wiki</a>" in client.get(f"/sites/{current.site_id}/").text
    # Without a default home, the operator title remains the local fallback.
    app.state.settings.default_site_id = None
    assert (
        f">{app.state.settings.hosted_title}</a>" in client.get(f"/sites/{current.site_id}/").text
    )
