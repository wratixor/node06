"""Private creation feed: follows, birth links, date gaps and stable cursor bounds."""

from datetime import UTC, datetime
from uuid import uuid4

from node06_service.models import points
from sqlalchemy import update
from test_authoring import payload, post
from test_people import action
from test_social import manager as manager
from test_social import second, setup, sub
from test_social import static_bundle as static_bundle


def born(database, pid, day, hour=12):
    with database.begin() as c:
        c.execute(
            update(points)
            .where(points.c.id == pid)
            .values(created_at=datetime(2026, 10, day, hour, tzinfo=UTC))
        )


def test_feed_current_subscriptions_historical_days_and_no_duplicate(
    manager, static_bundle, pg_database
):
    topic, public = setup(manager, static_bundle)
    alice, bob, charlie = manager.client, second(manager), second(manager, "charlie")
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    sub(alice, public, topic["id"])
    assert action(alice, bob_id, "trust").status_code == 200
    a = post(bob, payload(bob, body="Bob newest")).json()["id"]
    b = post(charlie, payload(charlie, target=topic["id"], body="Related older")).json()["id"]
    both = post(bob, payload(bob, target=topic["id"], body="Both paths once")).json()["id"]
    unrelated = post(charlie, payload(charlie, body="Unrelated")).json()["id"]
    for pid, day in [(a, 20), (both, 20), (b, 15), (unrelated, 21)]:
        born(pg_database, pid, day)
    first = alice.get("/api/v1/me/feed").json()
    assert first["viewer_id"] == manager.user
    assert first["day"] == "2026-10-20"
    assert {p["id"] for p in first["items"]} == {a, both}
    assert first["next_day"] == "2026-10-15"
    older = alice.get("/api/v1/me/feed", params={"cursor": first["next_cursor"]}).json()
    assert older["day"] == "2026-10-15" and [p["id"] for p in older["items"]] == [b]
    assert older["next_cursor"] is None
    selected = alice.get("/api/v1/me/feed", params={"before_day": "2026-10-18"}).json()
    assert selected["day"] == "2026-10-15"
    # Dates come from creation; updates neither duplicate nor move the post.
    current = bob.get("/api/v1/points/" + a).json()
    assert (
        bob.patch(
            "/api/v1/points/" + a,
            json={
                **payload(bob, body="Changed preview"),
                "expected_revision_id": current["revision_id"],
            },
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 200
    )
    same = alice.get("/api/v1/me/feed").json()
    assert same["day"] == first["day"] and len(same["items"]) == 2
    assert next(p for p in same["items"] if p["id"] == a)["preview"] == "Changed preview"
    # Current subscriptions control historical reads too, without an inbox backfill.
    assert action(alice, bob_id, "trust", False).status_code == 200
    remaining = alice.get("/api/v1/me/feed").json()
    assert remaining["day"] == "2026-10-20" and [p["id"] for p in remaining["items"]] == [both]
    sub(alice, public, topic["id"], False)
    assert alice.get("/api/v1/me/feed").json()["items"] == []


def test_feed_birth_links_block_visibility_and_cursor(manager, static_bundle, pg_database):
    topic, public = setup(manager, static_bundle)
    alice, bob = manager.client, second(manager)
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    sub(alice, public, topic["id"])
    originals = []
    for i in range(3):
        p = post(bob, payload(bob, target=topic["id"], body=f"Post {i}")).json()
        originals.append(p["id"])
        born(pg_database, p["id"], 15)
    # Later links must not manufacture a new creation event in someone's feed.
    late = post(bob, payload(bob, body="Late link")).json()
    assert (
        bob.patch(
            "/api/v1/points/" + late["id"],
            json={
                **payload(bob, target=topic["id"], body="Late link edited"),
                "expected_revision_id": late["revision_id"],
            },
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 200
    )
    page = alice.get("/api/v1/me/feed?limit=2").json()
    assert [row["id"] for row in page["items"]] == sorted(originals, reverse=True)[:2]
    assert page["next_day"] == page["day"]
    cursor = page["next_cursor"]
    next_page = alice.get("/api/v1/me/feed", params={"cursor": cursor}).json()
    assert [p["id"] for p in next_page["items"]] == sorted(originals)[:1]
    assert bob.get("/api/v1/me/feed", params={"cursor": cursor}).status_code == 422
    for invalid in ("!!!", "e30", "x" * 513):
        assert alice.get("/api/v1/me/feed", params={"cursor": invalid}).status_code == 422
    assert (
        alice.get(
            "/api/v1/me/feed", params={"cursor": cursor, "before_day": "2026-10-15"}
        ).status_code
        == 400
    )
    assert alice.get("/api/v1/me/feed?limit=0").status_code == 422
    # Newly created points after the first page do not slip into its history.
    new = post(bob, payload(bob, target=topic["id"], body="New after cursor")).json()["id"]
    assert new not in [
        p["id"] for p in alice.get("/api/v1/me/feed", params={"cursor": cursor}).json()["items"]
    ]
    assert action(alice, bob_id, "block").status_code == 200
    assert alice.get("/api/v1/me/feed").json()["items"] == []
    assert action(alice, bob_id, "block", False).status_code == 200
    with pg_database.begin() as c:
        c.execute(
            update(points).where(points.c.id.in_([*originals, new])).values(lifecycle="retired")
        )
    assert alice.get("/api/v1/me/feed").json()["items"] == []


def test_feed_index_populated_roundtrip(manager, static_bundle, pg_database):
    import os
    import subprocess
    import sys

    from sqlalchemy import inspect, select
    from test_compose_migration import ROOT

    point, _ = setup(manager, static_bundle)
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for target in ("0014_user_blocks", "head", "0014_user_blocks", "head"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade" if target == "head" else "downgrade",
                target,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        names = {index["name"] for index in inspect(pg_database._engine).get_indexes("points")}
        assert ("ix_points_created_feed" in names) == (target == "head")
        with pg_database.connect() as c:
            assert (
                c.scalar(select(points.c.current_revision_id).where(points.c.id == point["id"]))
                == point["revision_id"]
            )


def test_feed_point_block_and_private_access(manager, static_bundle):
    topic, public = setup(manager, static_bundle)
    client = manager.client
    sub(client, public, topic["id"])
    created = post(client, payload(client, target=topic["id"], body="Access check"))
    assert created.status_code == 201
    point = public.get(created.json()["id"])
    assert point["id"] in [p["id"] for p in client.get("/api/v1/me/feed").json()["items"]]
    assert (
        client.post(
            f"/api/v1/points/{point['id']}/block",
            json={"active": True, **{k: point[k] for k in ("revision_id", "content_digest")}},
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/me/feed").json()["items"] == []
    assert (
        client.get("/api/v1/me/feed", headers={"Origin": "https://untrusted.example"}).status_code
        == 403
    )
    client.cookies.clear()
    response = client.get("/api/v1/me/feed")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
