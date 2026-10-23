"""Relative geometry, signed slot conservation, version pins and public transport."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from node06_service.geometry import DEFAULT, calculate, color, normalized
from node06_service.influence import SCALE, InfluenceUnavailable
from node06_service.models import influence_runs, point_blocks, subscriptions, support_history
from node06_service.public_points import PublicPoints
from node06_service.social import Social
from sqlalchemy import select
from test_social import manager as manager_fixture
from test_social import proposal, second, setup, sub, vote
from test_social import static_bundle as bundle_fixture


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database, static_bundle)


def write(client, path, data, key=None):
    result = client.post(
        "/api/v1" + path, json=data, headers={"Idempotency-Key": key or uuid4().hex}
    )
    assert result.status_code == 200, result.text
    return result.json()


def block(client, public, pid, active=True):
    p = public.get(pid)
    return write(client, f"/points/{pid}/block", {**Social.pin(p), "active": active})


def latest(database):
    with database.connect() as c:
        return c.execute(
            select(influence_runs.c.data).order_by(influence_runs.c.created_at.desc()).limit(1)
        ).scalar_one()


def read(client, ids):
    result = client.get("/api/v1/geometry", params={"ids": ",".join(ids)})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


def test_relative_vectors_mirror_normalize_and_neutral():
    v = [90, 10, 40, 60, 20, 80]
    assert normalized(v) == normalized([x * 10 for x in v])
    assert sum(normalized(v)) == SCALE
    support = calculate({"a": v}, {"a": {"p": SCALE}}, {})["p"]
    negative = calculate({"a": v}, {}, {"a": {"p": SCALE}})["p"]
    assert negative["coordinates"] == [support["coordinates"][j ^ 1] for j in range(6)]
    both = calculate({"a": v, "b": v}, {"a": {"p": SCALE}}, {"b": {"p": SCALE}})["p"]
    assert all(both["coordinates"][j] == both["coordinates"][j ^ 1] for j in (0, 2, 4))
    assert both["color"] == "#808080"
    assert calculate({}, {}, {}) == {}
    assert color(v) == "#e66633"
    assert calculate({"a": v}, {"a": {"p": 0}}, {}) == {}
    for invalid in ([0] * 6, [True] * 6, [1] * 5, [65536] * 6):
        with pytest.raises(InfluenceUnavailable):
            normalized(invalid)


def test_shared_budget_switching_profile_receipts_and_no_identity_leak(
    manager, static_bundle, pg_database
):
    first, public = setup(manager, static_bundle)
    pid, client = first["id"], manager.client
    assert client.get("/api/v1/me/geometry").json()["coordinates"] == DEFAULT
    v = [90, 10, 40, 60, 20, 80]
    key = uuid4().hex
    assert write(client, "/me/geometry", {"coordinates": v}, key)["color"] == "#e66633"
    write(client, "/me/geometry", {"coordinates": v}, key)
    assert (
        client.post(
            "/api/v1/me/geometry", json={"coordinates": DEFAULT}, headers={"Idempotency-Key": key}
        ).status_code
        == 409
    )
    for invalid in ([0] * 6, [True] * 6, [1] * 5, [1.5] * 6):
        assert client.post("/api/v1/me/geometry", json={"coordinates": invalid}).status_code == 422
    sub(client, public, pid)
    block(client, public, "skills-ru")
    Social(public).work()
    data = latest(pg_database)
    assert data["allocations"][manager.user][pid] == SCALE // 4
    assert data["block_allocations"][manager.user]["skills-ru"] == SCALE // 4
    assert (
        data["mass_units"] + data["blocked_units"] + data["held_units"] + data["idle_units"]
        == SCALE // 2
    )
    result = read(client, [pid, "skills-ru"])
    assert not result["pending"]
    assert result["items"][0]["color"] == "#e66633"
    assert result["items"][1]["color"] == "#1999cc"
    assert manager.user not in json.dumps(result)
    block(client, public, pid)
    own = client.get(f"/api/v1/me/subscriptions/{pid}").json()
    assert own["block"] and not own["subscription"]["active"]
    sub(client, public, pid)
    assert client.get(f"/api/v1/me/subscriptions/{pid}").json()["block"] is None
    sub(client, public, pid, False)
    Social(public).work()
    assert read(client, [pid])["items"][0]["coordinates"] is None
    write(client, "/me/geometry", {"coordinates": DEFAULT})
    assert read(client, ["skills-ru"])["pending"]
    # Coordinates change layout, not recursive trust weight or total budget.
    Social(public).work()
    assert latest(pg_database)["weights"] == data["weights"]
    assert client.get("/api/v1/me/blocks").json()["items"][0]["point_id"] == "skills-ru"
    guest = second(manager)
    assert guest.get("/api/v1/me/blocks").json()["items"] == []
    assert guest.get("/api/v1/me/geometry").json()["coordinates"] == DEFAULT


def test_block_does_not_vote_and_old_version_is_held(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid, client = first["id"], manager.client
    blocker = second(manager)
    sub(client, public, pid)
    block(blocker, public, pid)
    qid = proposal(client, public, pid)
    # Blocking is neither a subscriber veto nor an old ballot.
    assert vote(client, qid, "new")["state"] == "adopted"
    Social(public).work()
    data = latest(pg_database)
    assert data["point_mass"][pid]["blocked"] == 0
    assert data["point_mass"][pid]["blocked_held"] == SCALE // 2
    assert data["point_mass"][pid]["current"] == SCALE // 2
    block(blocker, public, pid)
    Social(public).work()
    assert latest(pg_database)["point_mass"][pid]["blocked"] == SCALE // 2
    block(blocker, public, pid, False)
    assert blocker.get("/api/v1/me/blocks").json()["items"] == []


def test_static_git_block_transfer_and_source_pin_guard(manager, static_bundle, pg_database):
    _, public = setup(manager, static_bundle)
    block(manager.client, public, "skills-ru")
    Social(public).work()
    roots = [
        {**p, "body": p["body"] + " New law"} if p["id"] == "skills-ru" else p
        for p in manager.app.state.hosted_bundle.roots
    ]
    new_public = PublicPoints(pg_database, roots=roots, build_revision="new-build")
    from node06_service.geometry_read import batch

    assert batch(new_public, ["skills-ru"])["items"][0]["coordinates"] is None
    Social(new_public).work()
    value = batch(new_public, ["skills-ru"])
    assert not value["pending"] and value["items"][0]["coordinates"]
    with pg_database.connect() as c:
        row = c.execute(select(point_blocks)).mappings().one()
        assert row["content_digest"] == new_public.get("skills-ru")["content_digest"]
        assert c.scalar(
            select(support_history.c.reason).where(
                support_history.c.reason == "git-source-update-block"
            )
        )


def test_reaction_race_cannot_double_spend(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    service = Social(public, lambda c, uid: None)
    pin = Social.pin(public.get(first["id"]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(
                service.mutate,
                manager.user,
                uuid4().hex,
                kind,
                first["id"],
                {**pin, "active": True},
            )
            for kind in ("subscription", "block")
        ]
        for future in results:
            future.result()
    with pg_database.connect() as c:
        positive = c.scalar(select(subscriptions.c.active))
        negative = c.scalar(select(point_blocks.c.user_id)) is not None
        assert positive != negative
    Social(public).work()
    data = latest(pg_database)
    assert data["mass_units"] + data["blocked_units"] == SCALE // 2


def test_geometry_bounds_and_private_write_guards(manager, static_bundle):
    first, _public = setup(manager, static_bundle)
    client = manager.client
    for ids in ([], [first["id"]] * 2, ["skills-ru"] * 65, ["../bad"]):
        assert client.get("/api/v1/geometry", params={"ids": ",".join(ids)}).status_code in (
            400,
            422,
        )
    assert read(client, ["missing-point"])["items"] == []
    with client as _:
        csrf = client.headers.pop("X-CSRF-Token")
        assert (
            client.post(
                "/api/v1/me/geometry",
                json={"coordinates": DEFAULT},
                headers={"Idempotency-Key": uuid4().hex},
            ).status_code
            == 403
        )
        client.headers["X-CSRF-Token"] = csrf
    # Public transport never needs account cookies.
    client.cookies.clear()
    assert read(client, [first["id"]])["schema"] == "node06-geometry/1"
    assert client.get("/api/v1/me/geometry").status_code == 401


def test_ballot_replaced_by_block_and_explicit_vote_replaces_block(manager, static_bundle):
    first, public = setup(manager, static_bundle)
    pid, client = first["id"], manager.client
    other = second(manager)
    sub(client, public, pid)
    sub(other, public, pid)
    qid = proposal(client, public, pid)
    vote(client, qid, "old")
    block(client, public, pid)
    own = client.get(f"/api/v1/me/subscriptions/{pid}").json()
    assert own["block"] and own["ballot"] is None
    assert vote(client, qid, "old")["state"] == "open"
    own = client.get(f"/api/v1/me/subscriptions/{pid}").json()
    assert own["block"] is None and own["subscription"]["active"]
    assert own["ballot"] == "old"


def test_populated_geometry_migration_round_trip(manager, static_bundle, pg_database):
    import os
    import subprocess
    import sys
    from pathlib import Path

    first, public = setup(manager, static_bundle)
    sub(manager.client, public, first["id"])
    block(manager.client, public, "skills-ru")
    write(manager.client, "/me/geometry", {"coordinates": [3, 2, 5, 4, 7, 6]})
    with pg_database.connect() as c:
        env = {
            **os.environ,
            "NODE06_DATABASE_URL": c.engine.url.render_as_string(hide_password=False),
        }
    for operation, revision in (("downgrade", "0011_favorite_points"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode()
    assert public.get(first["id"])["revision_id"] == first["revision_id"]
    assert manager.client.get("/api/v1/me/geometry").json()["coordinates"] == DEFAULT
    assert manager.client.get("/api/v1/me/blocks").json()["items"] == []
    assert manager.client.get(f"/api/v1/me/subscriptions/{first['id']}").json()["subscription"][
        "active"
    ]
    Social(public).work()
