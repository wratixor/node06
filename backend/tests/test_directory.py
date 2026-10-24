"""Public discovery privacy, persisted influence, visibility and scoped private reads."""

from uuid import uuid4

from node06_service.models import users
from node06_service.moderation_admin import grant
from node06_service.social import Social
from sqlalchemy import insert, update
from test_moderation import action, active
from test_social import manager as manager
from test_social import second, setup, sub
from test_social import static_bundle as static_bundle


def test_public_search_is_paginated_literal_and_private_dates_require_scope(
    manager, static_bundle, pg_database
):
    _, public = setup(manager, static_bundle)
    guest = second(manager)
    site = active(pg_database, manager.user, "https://directory.example")
    with pg_database.begin() as c:
        c.execute(
            insert(users),
            [{"id": "u_" + uuid4().hex, "handle": f"directory_{i:02}"} for i in range(25)],
        )
        c.execute(
            insert(users).values(
                id="u_" + uuid4().hex, handle="directory_disabled", state="disabled"
            )
        )
    params = {"q": "directory_"}
    first = guest.get("/api/v1/directory/users", params=params)
    assert first.status_code == 200
    value = first.json()
    assert len(value["items"]) == 20 and value["next_cursor"]
    assert all(set(item) == {"id", "handle"} for item in value["items"])
    rest = guest.get(
        "/api/v1/directory/users", params={**params, "after": value["next_cursor"]}
    ).json()
    assert len(rest["items"]) == 5 and rest["next_cursor"] is None
    assert not ({p["id"] for p in value["items"]} & {p["id"] for p in rest["items"]})
    assert guest.get("/api/v1/directory/users", params={"q": "%"}).json()["items"] == []
    private = "/api/v1/moderation/users"
    assert guest.get(private, params={"scope": site}).status_code == 403
    assert manager.client.get(private, params={"scope": "server"}).status_code == 403
    result = manager.client.get(private, params={"scope": site, "q": "DIRECTORY_DISABLED"}).json()
    assert result["role"] == "admin" and len(result["items"]) == 1
    assert set(result["items"][0]) == {"id", "handle", "created_at", "state"}
    assert result["items"][0]["state"] == "disabled"
    user_id = guest.get("/api/v1/me").json()["user_id"]
    assert (
        action(manager.client, site, "roles/" + user_id, {"role": "moderator"}).status_code == 200
    )
    assert guest.get(private, params={"scope": site}).status_code == 200
    assert action(manager.client, site, "roles/" + user_id, {"role": None}).status_code == 200
    assert guest.get(private, params={"scope": site}).status_code == 403
    from fastapi.testclient import TestClient
    from test_site_management import ORIGIN

    anonymous = TestClient(manager.app, base_url=ORIGIN)
    response = anonymous.get("/api/v1/directory/users")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in response.headers
    assert anonymous.get(private, params={"scope": site}).status_code == 401
    Social(public).work()
    page = anonymous.get("/api/v1/directory/rankings").json()
    assert page["pending"] is False and len(page["items"]) == 20
    remaining = anonymous.get(
        "/api/v1/directory/rankings", params={"after": page["next_cursor"]}
    ).json()
    assert len(remaining["items"]) == 7 and remaining["next_cursor"] is None
    combined = page["items"] + remaining["items"]
    assert [p["id"] for p in combined] == sorted(p["id"] for p in combined)
    assert all(p["influence"] == "1" for p in combined)


def test_rankings_use_snapshot_and_filter_site_hides(manager, static_bundle, pg_database):
    point, public = setup(manager, static_bundle)
    bob = second(manager)
    endpoint = "/api/v1/directory/rankings"
    assert bob.get(endpoint).json()["pending"] is True
    sub(manager.client, public, point["id"])
    Social(public).work()
    result = bob.get(endpoint, params={"kind": "points"}).json()
    assert result["pending"] is False
    assert result["items"][0]["id"] == point["id"]
    assert result["items"][0]["influence"] == "0.5"
    ranked_users = bob.get(endpoint).json()
    assert len(ranked_users["items"]) == 2
    assert all(set(p) == {"id", "handle", "influence"} for p in ranked_users["items"])
    assert sum(float(p["influence"]) for p in ranked_users["items"]) == 2
    # A social mutation invalidates the stored projection without a GET recomputation.
    sub(bob, public, point["id"])
    assert bob.get(endpoint).json()["pending"] is True
    Social(public).work()
    assert bob.get(endpoint, params={"kind": "points"}).json()["items"][0]["influence"] == "1"
    old_snapshot = result["snapshot_id"]
    assert (
        bob.get(
            endpoint, params={"kind": "points", "after": old_snapshot + ":points:20"}
        ).status_code
        == 409
    )
    assert bob.get(endpoint, params={"after": "garbage"}).status_code == 422
    site = active(pg_database, manager.user, "https://rank.example")
    assert (
        action(
            manager.client, site, "visibility/" + point["id"], {"hidden": True, "reason": "local"}
        ).status_code
        == 200
    )
    Social(public).work()
    assert bob.get(endpoint, params={"kind": "points", "site": site}).json()["items"] == []
    assert bob.get(endpoint, params={"kind": "points"}).json()["items"][0]["id"] == point["id"]
    grant(pg_database, manager.user, "admin")
    assert (
        action(
            manager.client,
            "server",
            "visibility/" + point["id"],
            {"hidden": True, "reason": "global"},
        ).status_code
        == 200
    )
    Social(public).work()
    assert bob.get(endpoint, params={"kind": "points"}).json()["items"] == []
    sub(bob, public, "skills-ru")
    Social(public).work()
    roots = bob.get(endpoint, params={"kind": "points"}).json()
    assert roots["pending"] is False
    assert [p["id"] for p in roots["items"]] == ["skills-ru"]


def test_rankings_do_not_expose_disabled_users_or_stale_point_versions(
    manager, static_bundle, pg_database
):
    point, public = setup(manager, static_bundle)
    bob = second(manager)
    sub(manager.client, public, point["id"])
    Social(public).work()
    # Invalidate a pin without a social event, as a new static build can do.
    with pg_database.begin() as c:
        from node06_service.models import influence_runs
        from sqlalchemy import select

        run = c.execute(select(influence_runs)).mappings().one()
        data = run["data"]
        data["point_mass"][point["id"]]["content_digest"] = "stale"
        c.execute(update(influence_runs).where(influence_runs.c.id == run["id"]).values(data=data))
    assert bob.get("/api/v1/directory/rankings?kind=points").json()["pending"] is True
    with pg_database.begin() as c:
        c.execute(update(users).where(users.c.id == manager.user).values(state="disabled"))
    assert bob.get("/api/v1/directory/rankings").json()["pending"] is True
    assert all(p["id"] != manager.user for p in bob.get("/api/v1/directory/users").json()["items"])
