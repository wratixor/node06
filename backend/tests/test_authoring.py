"""Publication ACL, current-target checks, replay and graph visibility on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from node06_service.authoring import Authoring, AuthoringError
from node06_service.hosted import HostedBundle
from node06_service.models import authored_revisions, edge_claims, events, point_revisions, points
from node06_service.public_points import PublicPoints
from sqlalchemy import func, select, update
from test_hosted import static_bundle as bundle_fixture
from test_site_management import ORIGIN, PASSWORD
from test_site_management import manager as manager_fixture


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database)


def attach(manager, static_bundle):
    manager.app.state.hosted_bundle = HostedBundle(static_bundle)


def payload(client, target="skills-ru", body="Моя [воля](md://point/skills-ru)"):
    point = client.get("/api/v1/points/" + target).json()
    return {
        "body": body,
        "lang": "ru",
        "links": [{k: point[k] for k in ("id", "revision_id", "content_digest")}],
    }


def post(client, data, key=None):
    return client.post("/api/v1/points", json=data, headers={"Idempotency-Key": key or uuid4().hex})


def test_publish_no_site_replay_history_and_public_projection(manager, static_bundle, pg_database):
    attach(manager, static_bundle)
    client = manager.client
    body = payload(client)
    key = uuid4().hex
    result = post(client, body, key)
    assert result.status_code == 201, result.text
    first = result.json()
    assert post(client, body, key).json() == first
    assert post(client, {**body, "body": "other"}, key).status_code == 409
    pid = first["id"]
    point = client.get("/api/v1/points/" + pid).json()
    assert point["body"] == body["body"] and point["source"]["author_user_id"] == manager.user
    assert 'data-point-id="skills-ru"' in point["html"]
    assert point["lang"] == "ru" and "skills-ru" in point["links"]
    assert pid in client.get("/api/v1/points/skills-ru").json()["links"]
    assert client.get("/api/v1/points/search?q=Моя").json()["items"][0]["id"] == pid
    assert client.get("/api/v1/me/points").json()["items"][0]["id"] == pid
    history = client.get(f"/api/v1/points/{pid}/revisions").json()
    assert history["items"][0]["citations"][0]["revision_id"] is None
    assert "static_body" not in history["items"][0]["citations"][0]
    with pg_database.connect() as c:
        assert c.execute(select(authored_revisions.c.citations)).scalar_one()[0]["static_body"]
        assert (
            c.execute(
                select(func.count()).select_from(events).where(events.c.kind == "point-created")
            ).scalar_one()
            == 1
        )
    assert client.get("/api/v1/points/skills-ru/revisions").status_code == 404


def test_edit_stale_noop_escaping_claims_and_history(manager, static_bundle, pg_database):
    attach(manager, static_bundle)
    client = manager.client
    body = payload(client)
    first = post(client, body).json()
    url = "/api/v1/points/" + first["id"]
    edit = {**body, "expected_revision_id": first["revision_id"]}
    noop = client.patch(url, json=edit, headers={"Idempotency-Key": uuid4().hex})
    assert noop.status_code == 200 and noop.json()["changed"] is False
    changed = client.patch(
        url,
        json={**edit, "body": "<script>alert(1)</script> plain воля"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert changed.status_code == 200, changed.text
    assert "<script>" not in client.get(url).json()["html"]
    assert (
        client.patch(url, json=edit, headers={"Idempotency-Key": uuid4().hex}).json()["code"]
        == "POINT_REVISION_CHANGED"
    )
    page = client.get(url + "/revisions?limit=1").json()
    assert page["items"][0]["revision_id"] == changed.json()["revision_id"]
    second = client.get(
        url + "/revisions", params={"before": page["next_cursor"], "limit": 1}
    ).json()
    assert (
        second["items"][0]["revision_id"] == first["revision_id"] and second["next_cursor"] is None
    )
    with pg_database.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(edge_claims)
                .where(edge_claims.c.claim_ref == first["id"])
            ).scalar_one()
            == 1
        )
        assert (
            c.execute(
                select(func.count())
                .select_from(point_revisions)
                .where(point_revisions.c.point_id == first["id"])
            ).scalar_one()
            == 2
        )


def test_reject_stale_targets_and_undeclared_links(manager, static_bundle):
    attach(manager, static_bundle)
    client = manager.client
    body = payload(client)
    badpin = {**body, "links": [{**body["links"][0], "content_digest": "0" * 64}]}
    assert post(client, badpin).json()["code"] == "TARGET_REVISION_CHANGED"
    assert post(client, {**body, "body": "[x](md://point/unknown)"}).status_code == 422
    assert post(client, {**body, "body": "[x](md://local/welcome)"}).status_code == 422
    assert post(client, {**body, "links": []}).status_code == 422
    assert post(client, {**body, "links": body["links"] * 2}).status_code == 422
    assert post(client, {**body, "body": "   "}).status_code == 422
    assert (
        post(
            client, {**body, "body": "`[x](md://point/unknown)`\n```\n[x](md://point/unknown)\n```"}
        ).status_code
        == 201
    )
    assert client.post("/api/v1/points", json=body).status_code == 422


def test_acl_csrf_session_and_body_bounds(manager, static_bundle):
    attach(manager, static_bundle)
    client = manager.client
    body = payload(client)
    first = post(client, body).json()
    headers = {"Idempotency-Key": uuid4().hex}
    edit = {**body, "expected_revision_id": first["revision_id"]}
    assert client.patch("/api/v1/points/skills-ru", json=edit, headers=headers).status_code == 403
    with TestClient(manager.app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as other:
        assert post(other, body).status_code in (401, 403)
        other.post("/api/v1/auth/register", json={"handle": "bobby", "password": PASSWORD})
        login = other.post(
            "/api/v1/auth/login", json={"handle": "bobby", "password": PASSWORD}
        ).json()
        other.headers["X-CSRF-Token"] = login["csrf_token"]
        assert (
            other.patch("/api/v1/points/" + first["id"], json=edit, headers=headers).status_code
            == 403
        )
        other.headers["Origin"] = "https://evil.example"
        assert post(other, body).status_code == 403
    assert client.post("/api/v1/points", content=b"x" * 65537).status_code == 413
    client.delete("/api/v1/auth/session")
    assert post(client, body).status_code == 401


def test_transactional_race_replay_and_target_change(manager, static_bundle, pg_database):
    attach(manager, static_bundle)
    body = payload(manager.client)
    public = PublicPoints(pg_database, roots=manager.app.state.hosted_bundle.roots)
    service = Authoring(
        public, lambda c, uid: manager.auth.authorize_session(c, manager.token, uid)
    )
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.save(manager.user, key, body), range(2)))
    assert results[0] == results[1]
    first = results[0]
    target = public.get(first["id"])
    referencing = {
        "body": "reference",
        "lang": "en",
        "links": [{k: target[k] for k in ("id", "revision_id", "content_digest")}],
    }
    service.save(
        manager.user,
        uuid4().hex,
        {**body, "body": "new", "expected_revision_id": first["revision_id"]},
        first["id"],
    )
    with pytest.raises(AuthoringError, match="TARGET_REVISION_CHANGED"):
        service.save(manager.user, uuid4().hex, referencing)
    with pg_database.begin() as c:
        c.execute(update(points).where(points.c.id == first["id"]).values(lifecycle="inactive"))
    with pytest.raises(AuthoringError, match="TARGET_NOT_PUBLIC"):
        service.save(manager.user, uuid4().hex, referencing)


def test_competing_edits_and_independent_claim_preservation(manager, static_bundle, pg_database):
    attach(manager, static_bundle)
    body = payload(manager.client)
    public = PublicPoints(pg_database, roots=manager.app.state.hosted_bundle.roots)
    service = Authoring(
        public, lambda c, uid: manager.auth.authorize_session(c, manager.token, uid)
    )
    first = service.save(manager.user, uuid4().hex, body)
    edit = {**body, "expected_revision_id": first["revision_id"]}

    def attempt(text):
        try:
            return service.save(manager.user, uuid4().hex, {**edit, "body": text}, first["id"])
        except AuthoringError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["Version A", "Version B"]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "POINT_REVISION_CHANGED" in results
    current = public.get(first["id"])
    reference = {
        "body": "Independent reference",
        "lang": "en",
        "links": [{k: current[k] for k in ("id", "revision_id", "content_digest")}],
    }
    other = service.save(manager.user, uuid4().hex, reference)
    service.save(
        manager.user,
        uuid4().hex,
        {
            **payload(manager.client, "skills-en", "Changed link"),
            "expected_revision_id": current["revision_id"],
        },
        first["id"],
    )
    assert first["id"] in public.get(other["id"])["links"]
    assert "skills-ru" not in public.get(first["id"])["links"]
    assert "skills-en" in public.get(first["id"])["links"]
    with pg_database.connect() as c:
        assert (
            c.execute(
                select(func.count())
                .select_from(edge_claims)
                .where(edge_claims.c.claim_ref == other["id"])
            ).scalar_one()
            == 1
        )


def test_editor_and_management_boundary(manager, static_bundle):
    attach(manager, static_bundle)
    response = manager.client.get("/editor/")
    assert (
        response.status_code == 200
        and "frame-ancestors 'self'" in response.headers["content-security-policy"]
        and response.headers["x-frame-options"] == "SAMEORIGIN"
    )
    assert manager.client.get("/editor/client.js").status_code == 200
    assert manager.client.get("/editor/style.css").status_code == 200
    manager.app.state.settings.embed_origin = "https://embed.example"
    assert manager.client.get("https://embed.example/editor/").status_code == 404
    assert post(manager.client, payload(manager.client), "boundary-test").status_code == 201


def test_author_attribution_stays_with_original_creator(manager, static_bundle):
    attach(manager, static_bundle)
    client = manager.client
    created = post(client, payload(client)).json()
    current = client.get("/api/v1/points/" + created["id"]).json()
    identity = client.get("/api/v1/me").json()
    assert current["author"] == {
        "kind": "user",
        "id": identity["user_id"],
        "name": identity["handle"],
    }
    edited = client.patch(
        "/api/v1/points/" + created["id"],
        json={
            **payload(client, body="Updated meaning"),
            "expected_revision_id": created["revision_id"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert edited.status_code == 200
    assert client.get("/api/v1/points/" + created["id"]).json()["author"] == current["author"]
    summary = client.get(f"/api/v1/points/{created['id']}/social-summary").json()
    assert summary["author"] == {"kind": "user", "name": identity["handle"]}
    assert "id" not in summary["author"]
