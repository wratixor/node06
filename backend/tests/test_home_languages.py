import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from node06_service.home_page import HomePage, render_home
from node06_service.models import sites
from pydantic import ValidationError
from sqlalchemy import update
from test_home_page import manager as manager_fixture
from test_home_page import put
from test_hosted import EMBED
from test_hosted import hosted as hosted_fixture
from test_hosted import static_bundle as static_fixture
from test_root_import import SITE, candidate, fixture_source
from test_site_management import create, state


@pytest.fixture
def manager(pg_database):
    yield from manager_fixture.__wrapped__(pg_database)


@pytest.fixture(scope="session")
def static_bundle():
    return static_fixture.__wrapped__()


@pytest.fixture
def hosted(pg_database, static_bundle):
    yield from hosted_fixture.__wrapped__(pg_database, static_bundle)


PAGE = {
    "default_language": "ru",
    "title": "Мир",
    "entrance_label": "Точка входа",
    "all_sites_label": "Все сайты",
    "blocks": [{"title": "Мир", "links": [{"label": "Открыть мир", "point_id": "field-ru"}]}],
    "translations": {
        "en": {
            "title": "World",
            "blocks": [{"title": "World", "links": [{"label": "World", "point_id": "field-en"}]}],
        },
        "ja": {"title": "世界", "entrance_label": "入口", "all_sites_label": "すべてのサイト"},
    },
}


def test_whole_translations_have_distinct_targets_and_safe_markup():
    page = deepcopy(PAGE)
    page["translations"]["ja"]["title"] = "</div><script>bad()</script>"
    source = render_home(SimpleNamespace(home_page=page, id=SITE), "Wiki", "/entrance/")
    assert '<div data-home-language="ru" lang="ru"><h1>Мир</h1>' in source
    assert '<div data-home-language="en" lang="en" hidden><h1>World</h1>' in source
    assert 'href="/entrance/?p=field-en&amp;open=field-en" data-point-id="field-en"' in source
    assert 'href="/entrance/?p=field-ru&amp;open=field-ru" data-point-id="field-ru"' in source
    assert "<script>" not in source and "&lt;script&gt;" in source
    assert 'class="home-language-control" hidden' in source


@pytest.mark.parametrize(
    "change",
    [
        {"default_language": 'ru" onload="bad'},
        {"translations": {"RU": {"title": "duplicate default"}}},
        {"translations": {"en": {"title": "A"}, "EN": {"title": "B"}}},
        {"translations": {"en": {"title": "x", "translations": {}}}},
        {"translations": {"en": {"title": "x", "blocks": [{"title": "x"}] * 12}}},
        {
            "translations": {
                "en": {"title": "x", "blocks": [{"title": "x", "description": "я" * 1500}] * 4}
            }
        },
        {
            "translations": {
                "en": {
                    "title": "x",
                    "blocks": [
                        {"title": "x", "links": [{"label": "x", "url": "javascript:bad()"}]}
                    ],
                }
            }
        },
        {"translations": {"en": {"title": " "}}},
        {"all_sites_label": " "},
        {
            "translations": {
                tag: {"title": tag}
                for tag in ("aa", "ab", "ac", "ad", "ae", "af", "ag", "ah", "ai")
            }
        },
    ],
)
def test_translation_limits_cover_entire_bundle(change):
    with pytest.raises(ValidationError):
        HomePage.model_validate({**PAGE, **change})


def test_git_aliases_in_all_languages_without_changing_point_digests():
    manifest, blobs = fixture_source()
    before = candidate(manifest, blobs)
    page = deepcopy(PAGE)
    page["translations"]["en"]["blocks"][0]["links"][0]["point_id"] = "local/thought"
    manifest["home_page"] = page
    after = candidate(manifest, blobs)
    assert after.home_page.translations["en"].blocks[0].links[0].point_id == f"r_{SITE[2:]}_thought"
    assert after.summary()["home_block_count"] == 2
    assert before.digest != after.digest
    assert before.points == after.points


def test_owner_roundtrip_and_stale_translation_edit(manager):
    site = create(manager)
    revision = state(manager, site)["settings_revision"]
    result = put(manager, site, PAGE, revision)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["home_page"] == HomePage.model_validate(PAGE).model_dump()
    changed = deepcopy(PAGE)
    changed["translations"]["ja"]["title"] = "新しい世界"
    assert put(manager, site, changed, revision).status_code == 409
    current = put(manager, site, changed, value["settings_revision"]).json()
    assert (
        current["home_page"]["translations"]["en"]["blocks"][0]["links"][0]["point_id"]
        == "field-en"
    )
    assert current["settings_revision"] == value["settings_revision"] + 1


def test_hosted_embed_defaults_and_graph_are_unchanged(hosted, pg_database):
    _app, client, active, _pending = hosted
    before = client.get("/data/points.json").json()
    with pg_database.begin() as connection:
        connection.execute(update(sites).where(sites.c.id == active.site_id).values(home_page=PAGE))
    for prefix in (f"/sites/{active.site_id}/", f"{EMBED}/embed/v1/{active.site_id}/"):
        response = client.get(prefix)
        assert response.status_code == 200
        assert '<html lang="ru"' in response.text
        assert 'data-home-language="ja" lang="ja" hidden' in response.text
        assert 'data-point-id="field-ru"' in response.text
        assert 'data-point-id="field-en"' in response.text
        assert "/assets/home-languages.js?v=" in response.text
    assert client.get("/data/points.json").json() == before


def test_long_language_default_does_not_corrupt_hosted_markup(hosted, pg_database):
    _app, client, active, _pending = hosted
    with pg_database.begin() as connection:
        connection.execute(
            update(sites)
            .where(sites.c.id == active.site_id)
            .values(home_page={"title": "Olá", "default_language": "pt-BR"})
        )
    source = client.get(f"/sites/{active.site_id}/").text
    assert '<html lang="pt-BR"' in source
    assert '<section id="root-field"' in source
    assert "<h1>Olá</h1>" in source


def test_entire_legacy_size_range_survives_default_metadata():
    # Former HomePage JSON, including the old nested model defaults, exactly at 12KiB.
    legacy = {
        "title": "x",
        "introduction": "",
        "blocks": [{"title": "x", "description": "", "links": []} for _ in range(8)],
    }
    remaining = 12288 - len(json.dumps(legacy, ensure_ascii=False).encode())
    for block in legacy["blocks"]:
        count = min(1500, remaining)
        block["description"] = "x" * count
        remaining -= count
    assert remaining == 0
    assert len(json.dumps(legacy, ensure_ascii=False).encode()) == 12288
    page = HomePage.model_validate(legacy)
    assert HomePage.model_validate_json(page.model_dump_json()) == page
    # One more authored byte must still be rejected.
    legacy["introduction"] = "x"
    with pytest.raises(ValidationError):
        HomePage.model_validate(legacy)
