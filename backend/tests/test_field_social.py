"""Bounded social field summaries expose influence, never subscriber identities."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from node06_service.models import influence_runs, proposals, users
from node06_service.social import Social
from sqlalchemy import select, update
from test_social import manager as manager_fixture
from test_social import proposal, second, setup, sub, vote
from test_social import static_bundle as bundle_fixture


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database, static_bundle)


def summary(client, pid):
    response = client.get(f"/api/v1/points/{pid}/social-summary")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_summary_distinguishes_unpublished_zero_and_pending(manager, static_bundle):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    before = summary(manager.client, pid)
    assert not before["influence"]["available"]
    assert before["influence"]["current"] is None
    Social(public).work()
    zero = summary(manager.client, pid)
    assert zero["influence"]["current"] == "0"
    assert not zero["protected"]
    assert summary(manager.client, "skills-ru")["protected"]
    sub(manager.client, public, pid)
    pending = summary(manager.client, pid)["influence"]
    assert pending["pending"] and pending["current"] is None
    Social(public).work()
    assert summary(manager.client, pid)["influence"]["current"] == "0.5"


def test_summary_separates_version_mass_and_explicit_votes(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    other = second(manager)
    sub(manager.client, public, pid)
    sub(other, public, pid)
    qid = proposal(manager.client, public, pid)
    vote(manager.client, qid, "new")
    Social(public).work()
    current = summary(manager.client, pid)
    assert current["proposal"]["id"] == qid
    assert current["proposal"]["tally"] == {"old": "0", "new": "0.5"}
    assert current["influence"]["current"] == current["influence"]["held"] == "0.5"
    assert current["influence"]["subscribed"] == "1"
    with pg_database.connect() as c:
        ids = c.scalars(select(users.c.id)).all()
    assert current["author"]["id"] == manager.user
    # Only public attribution identifies a person, never reaction participants.
    anonymous = {key: value for key, value in current.items() if key != "author"}
    assert not any(uid in json.dumps(anonymous) for uid in ids)
    assert all(uid == manager.user or uid not in json.dumps(current) for uid in ids)
    assert "New meaning" not in json.dumps(current)
    with pg_database.begin() as c:
        c.execute(update(proposals).values(closes_at=datetime.now(UTC) - timedelta(seconds=1)))
    Social(public).work()
    adopted = summary(manager.client, pid)
    assert adopted["proposal"] is None
    assert adopted["influence"]["current"] == adopted["influence"]["held"] == "0.5"


def test_summary_refuses_old_projection_and_changed_eligibility(
    manager, static_bundle, pg_database
):
    first, public = setup(manager, static_bundle)
    Social(public).work()
    with pg_database.begin() as c:
        row = c.execute(select(influence_runs)).mappings().one()
        data = {k: v for k, v in row["data"].items() if k != "point_mass"}
        c.execute(update(influence_runs).values(data=data, input_digest="older-format"))
    assert summary(manager.client, first["id"])["influence"]["pending"]
    Social(public).work()
    assert not summary(manager.client, first["id"])["influence"]["pending"]
    with pg_database.begin() as c:
        c.execute(update(users).where(users.c.id == manager.user).values(state="disabled"))
    # Public summary remains anonymous even when the caller's account is disabled.
    assert summary(manager.client, first["id"])["influence"]["pending"]
