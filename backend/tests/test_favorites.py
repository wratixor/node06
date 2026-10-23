"""Account favorites are private bookmarks, never endorsements or ballots."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from node06_service.models import favorite_points, points, subscriptions
from node06_service.social import Social
from sqlalchemy import func, insert, select
from test_site_management import ORIGIN
from test_social import manager as manager_fixture
from test_social import second, setup
from test_social import static_bundle as bundle_fixture


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database, static_bundle)


def favorite(client, pid, active=True, key=None):
    return client.post(
        f"/api/v1/me/favorites/{pid}",
        json={"active": active},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_favorites_private_shared_by_account_and_no_influence(manager, static_bundle, pg_database):
    point, public = setup(manager, static_bundle)
    Social(public).work()
    key = uuid4().hex
    assert favorite(manager.client, point["id"], key=key).status_code == 200
    assert favorite(manager.client, point["id"], key=key).status_code == 200
    response = manager.client.get("/api/v1/me/favorites")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [p["id"] for p in response.json()["items"]] == [point["id"]]
    assert second(manager).get("/api/v1/me/favorites").json()["items"] == []
    with TestClient(manager.app, base_url=ORIGIN) as anonymous:
        assert anonymous.get("/api/v1/me/favorites").status_code == 401
    denied = manager.client.post(
        f"/api/v1/me/favorites/{point['id']}",
        json={"active": False},
        headers={"Origin": "https://other.example", "Idempotency-Key": uuid4().hex},
    )
    assert denied.status_code == 403
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(subscriptions)) == 0
        assert c.scalar(select(func.count()).select_from(favorite_points)) == 1
    assert favorite(manager.client, point["id"], active=False).status_code == 200
    assert manager.client.get("/api/v1/me/favorites").json()["items"] == []


def test_favorite_pins_are_fresh_and_invalid_target_never_saved(
    manager, static_bundle, pg_database
):
    _, _public = setup(manager, static_bundle)
    assert favorite(manager.client, "missing-root").status_code == 404
    assert favorite(manager.client, "skills-ru").status_code == 200
    saved = manager.client.get("/api/v1/me/favorites").json()["items"][0]
    current = manager.client.get("/api/v1/points/skills-ru").json()
    assert saved["content_digest"] == current["content_digest"]
    assert saved["revision_id"] is None


def test_favorites_limit_and_removal_even_when_target_unavailable(
    manager, static_bundle, pg_database
):
    _, _public = setup(manager, static_bundle)
    with pg_database.begin() as c:
        for i in range(64):
            pid = f"missing-{i}"
            c.execute(insert(points).values(id=pid, origin="user"))
            c.execute(insert(favorite_points).values(user_id=manager.user, point_id=pid))
    assert favorite(manager.client, "skills-ru").json()["code"] == "FAVORITES_LIMIT"
    assert favorite(manager.client, "missing-0", active=False).status_code == 200
    assert favorite(manager.client, "skills-ru").status_code == 200
