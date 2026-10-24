"""Public profiles, T1 subscriptions, reversible author blocks and populated upgrade."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from node06_service.models import (
    inbox,
    point_blocks,
    points,
    social_events,
    user_blocks,
    user_trust,
)
from sqlalchemy import func, insert, inspect, select, update
from test_authoring import payload, post
from test_social import manager as manager
from test_social import second, setup, sub
from test_social import static_bundle as static_bundle


def action(client, target, kind, active=True, key=None):
    return client.post(
        f"/api/v1/people/{target}/{kind}",
        json={"active": active},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_profile_visibility_t1_block_replay_and_inbox(manager, static_bundle, pg_database):
    _point, public = setup(manager, static_bundle)
    bob = second(manager)
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    p = post(bob, payload(bob, body="Bobby public post")).json()
    client = manager.client
    profile = client.get(f"/api/v1/people/{bob_id}")
    assert profile.status_code == 200
    assert set(profile.json()) == {"id", "handle", "color"}
    assert profile.json()["handle"] == "bobby"
    listing = client.get(f"/api/v1/people/{bob_id}/points").json()
    assert p["id"] in [row["id"] for row in listing["items"]]
    url = f"/api/v1/people/{bob_id}/block"
    assert (
        client.post(
            url,
            json={"active": True},
            headers={"Origin": "https://evil.example", "Idempotency-Key": uuid4().hex},
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json={"active": True}, headers={"X-CSRF-Token": "", "Idempotency-Key": uuid4().hex}
        ).status_code
        == 403
    )
    assert action(client, bob_id, "trust").status_code == 200
    assert client.get(f"/api/v1/me/people/{bob_id}").json()["following"]
    sub(client, public, p["id"])
    with pg_database.begin() as c:
        seq = c.scalar(
            insert(social_events)
            .values(
                kind="point-edited",
                point_id=p["id"],
                actor_user_id=bob_id,
                payload={},
                created_at=datetime.now(UTC),
            )
            .returning(social_events.c.seq)
        )
        c.execute(insert(inbox).values(user_id=manager.user, event_seq=seq))
    assert seq in [row["seq"] for row in client.get("/api/v1/me/inbox").json()["items"]]
    key = uuid4().hex
    assert action(client, bob_id, "block", key=key).status_code == 200
    assert action(client, bob_id, "block", key=key).status_code == 200
    assert action(client, bob_id, "block", False, key).status_code == 409
    assert client.get(f"/api/v1/me/people/{bob_id}").json() == {
        "user_id": bob_id,
        "following": False,
        "blocked": True,
    }
    assert seq not in [row["seq"] for row in client.get("/api/v1/me/inbox").json()["items"]]
    assert action(client, bob_id, "trust").json()["code"] == "AUTHOR_BLOCKED"
    assert client.get("/api/v1/me/people/blocks").json()["items"] == [
        {"id": bob_id, "handle": "bobby"}
    ]
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(user_trust)) == 0
        assert c.scalar(select(func.count()).select_from(point_blocks)) == 0
    assert client.get(f"/api/v1/me/subscriptions/{p['id']}").json()["subscription"]["active"]
    assert action(client, bob_id, "block", False).status_code == 200
    assert client.get(f"/api/v1/me/people/{bob_id}").json() == {
        "user_id": bob_id,
        "following": False,
        "blocked": False,
    }
    assert seq in [row["seq"] for row in client.get("/api/v1/me/inbox").json()["items"]]
    assert action(client, bob_id, "trust").status_code == 200
    assert action(client, manager.user, "block").json()["code"] == "INVALID_TRUST_TARGET"
    with pg_database.begin() as c:
        c.execute(update(points).where(points.c.id == p["id"]).values(lifecycle="retired"))
    assert p["id"] not in [
        row["id"] for row in client.get(f"/api/v1/people/{bob_id}/points").json()["items"]
    ]


def test_user_block_migration_populated_roundtrip(manager, static_bundle, pg_database):
    from test_compose_migration import ROOT

    point, _ = setup(manager, static_bundle)
    bob = second(manager)
    target = bob.get("/api/v1/me").json()["user_id"]
    assert action(manager.client, target, "block").status_code == 200
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for target_revision in ("0013_compose_receipts", "head", "0013_compose_receipts", "head"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade" if target_revision == "head" else "downgrade",
                target_revision,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert ("user_blocks" in inspect(pg_database._engine).get_table_names()) == (
            target_revision == "head"
        )
        with pg_database.connect() as c:
            assert (
                c.scalar(select(points.c.current_revision_id).where(points.c.id == point["id"]))
                == point["revision_id"]
            )
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(user_blocks)) == 0
