from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from node06_service.models import (
    ballots,
    proposals,
    social_events,
    subscriptions,
    support_history,
)
from node06_service.public_points import PublicPoints
from node06_service.social import Social
from sqlalchemy import func, select, update
from test_authoring import attach, payload, post
from test_authoring import manager as manager_fixture
from test_authoring import static_bundle as bundle_fixture
from test_site_management import PASSWORD


@pytest.fixture(scope="session")
def static_bundle():
    return bundle_fixture.__wrapped__()


@pytest.fixture
def manager(pg_database, static_bundle):
    yield from manager_fixture.__wrapped__(pg_database, static_bundle)


def setup(manager, static_bundle):
    attach(manager, static_bundle)
    first = post(manager.client, payload(manager.client)).json()
    public = PublicPoints(manager.app.state.database, roots=manager.app.state.hosted_bundle.roots)
    return first, public


def sub(client, public, pid, active=True):
    p = public.get(pid)
    response = client.post(
        f"/api/v1/points/{pid}/subscription",
        json={
            "revision_id": p["revision_id"],
            "content_digest": p["content_digest"],
            "active": active,
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 200, response.text
    return response.json()


def proposal(client, public, pid, body="New meaning"):
    p = public.get(pid)
    data = payload(client, body=body)
    response = client.post(
        f"/api/v1/points/{pid}/proposals",
        json={
            **data,
            "expected_revision_id": p["revision_id"],
            "expected_digest": p["content_digest"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 201, response.text
    return response.json()["proposal_id"]


def vote(client, qid, choice, key=None):
    response = client.post(
        f"/api/v1/proposals/{qid}/vote",
        json={"choice": choice},
        headers={"Idempotency-Key": key or uuid4().hex},
    )
    assert response.status_code == 200, response.text
    return response.json()


def second(manager, handle="bobby"):
    from fastapi.testclient import TestClient
    from test_site_management import ORIGIN

    client = TestClient(manager.app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    client.post("/api/v1/auth/register", json={"handle": handle, "password": PASSWORD})
    login = client.post("/api/v1/auth/login", json={"handle": handle, "password": PASSWORD}).json()
    client.headers["X-CSRF-Token"] = login["csrf_token"]
    return client


def test_subscribe_propose_vote_early_audit_and_no_duplicate(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    sub(client, public, pid)
    qid = proposal(client, public, pid)
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(ballots)) == 0
    key = uuid4().hex
    assert vote(client, qid, "new", key)["state"] == "adopted"
    assert vote(client, qid, "new", key)["state"] == "adopted"
    point = public.get(pid)
    assert point["body"] == "New meaning"
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(ballots)) == 1
        assert c.scalar(select(subscriptions.c.revision_id)) == point["revision_id"]
        q = c.execute(select(proposals)).mappings().one()
        assert q["result"]["early"] and q["result"]["snapshot_id"]
    Social(public).work()
    notices = client.get("/api/v1/me/inbox").json()["items"]
    assert {n["kind"] for n in notices} == {"proposal-opened", "proposal-adopted"}
    Social(public).work()
    assert len(client.get("/api/v1/me/inbox").json()["items"]) == 2
    assert client.get(f"/api/v1/points/{pid}/social").json()["influence"]["pending"] is False


def test_silent_subscriber_blocks_early_not_scheduled_tally(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    other = second(manager)
    sub(client, public, pid)
    sub(other, public, pid)
    qid = proposal(client, public, pid)
    assert vote(client, qid, "new")["state"] == "open"
    with pg_database.begin() as c:
        c.execute(
            update(proposals)
            .where(proposals.c.id == qid)
            .values(closes_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    Social(public).work()
    assert public.get(pid)["body"] == "New meaning"
    with pg_database.connect() as c:
        q = c.execute(select(proposals)).mappings().one()
        assert q["result"]["old_influence"] == "0" and q["result"]["early"] is False
        assert (
            c.scalar(
                select(subscriptions.c.revision_id).where(subscriptions.c.user_id != manager.user)
            )
            == first["revision_id"]
        )


def test_all_silent_and_tie_retain_old(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    other = second(manager)
    sub(client, public, pid)
    sub(other, public, pid)
    qid = proposal(client, public, pid)
    vote(other, qid, "old")
    vote(client, qid, "new")
    with pg_database.begin() as c:
        c.execute(update(proposals).values(closes_at=datetime.now(UTC) - timedelta(seconds=1)))
    Social(public).work()
    assert public.get(pid)["revision_id"] == first["revision_id"]
    with pg_database.connect() as c:
        assert c.scalar(select(proposals.c.state)) == "retained"


def test_direct_edit_protection_daily_limit_and_inbox_privacy(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    sub(client, public, pid)
    edit = {**payload(client, body="Bypass"), "expected_revision_id": first["revision_id"]}
    response = client.patch(
        "/api/v1/points/" + pid, json=edit, headers={"Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 409 and response.json()["code"] == "PROPOSAL_REQUIRED"
    qid = proposal(client, public, pid)
    vote(client, qid, "new")
    otherpoint = post(client, payload(client, body="Another point")).json()["id"]
    data = {
        **payload(client, body="Candidate"),
        "expected_revision_id": public.get(otherpoint)["revision_id"],
        "expected_digest": public.get(otherpoint)["content_digest"],
    }
    assert (
        client.post(
            f"/api/v1/points/{otherpoint}/proposals",
            json=data,
            headers={"Idempotency-Key": uuid4().hex},
        ).json()["code"]
        == "PROPOSAL_DAILY_LIMIT"
    )
    Social(public).work()
    notice = client.get("/api/v1/me/inbox").json()["items"][0]["seq"]
    other = second(manager)
    assert other.get("/api/v1/me/inbox").json()["items"] == []
    assert (
        other.post(
            f"/api/v1/me/inbox/{notice}/read", json={}, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/me/inbox/{notice}/read", json={}, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 200
    )


def test_weighted_majority_is_not_headcount(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    alice = manager.client
    bob = second(manager, "bobby")
    charlie = second(manager, "charlie")
    bob_id = bob.get("/api/v1/me").json()["user_id"]
    for client in (alice, charlie):
        response = client.post(
            f"/api/v1/people/{bob_id}/trust",
            json={"active": True},
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 200, response.text
    for client in (alice, bob, charlie):
        sub(client, public, pid)
    qid = proposal(alice, public, pid)
    vote(alice, qid, "old")
    vote(charlie, qid, "old")
    vote(bob, qid, "new")
    with pg_database.begin() as c:
        c.execute(update(proposals).values(closes_at=datetime.now(UTC) - timedelta(seconds=1)))
    Social(public).work()
    with pg_database.connect() as c:
        q = c.execute(select(proposals)).mappings().one()
        assert q["state"] == "adopted" and not q["result"]["early"]
        assert float(q["result"]["new_influence"]) > float(q["result"]["old_influence"])
        assert (
            c.scalar(select(func.count()).select_from(ballots).where(ballots.c.choice == "old"))
            == 2
        )


def test_git_protection_transfer_changelog_and_noop(manager, static_bundle, pg_database):
    from node06_service.root_publish import publish
    from node06_service.site_registry import SiteRegistry
    from test_root_publish import REPO, candidate

    setup(manager, static_bundle)
    registry = SiteRegistry(pg_database)
    site = registry.create_pending_site(
        owner_user_id=manager.user, origin="https://wiki.example", welcome_body="Welcome"
    )
    registry.verify_site(
        site.site_id,
        actor_user_id=manager.user,
        proof_fetcher=lambda _: site.proof_document.encode(),
    )
    publish(pg_database, candidate(site), REPO, "https://wiki.example")
    public = PublicPoints(pg_database, roots=manager.app.state.hosted_bundle.roots)
    pid = f"r_{site.site_id[2:]}_idea"
    sub(manager.client, public, pid)
    p = public.get(pid)
    bad = manager.client.post(
        f"/api/v1/points/{pid}/proposals",
        json={
            **payload(manager.client, body="No"),
            "expected_revision_id": p["revision_id"],
            "expected_digest": p["content_digest"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert bad.status_code == 403
    for _ in range(2):
        publish(
            pg_database, candidate(site, body="Changed", sha="b" * 40), REPO, "https://wiki.example"
        )
    with pg_database.connect() as c:
        row = (
            c.execute(select(subscriptions).where(subscriptions.c.point_id == pid)).mappings().one()
        )
        assert row["revision_id"] == public.get(pid)["revision_id"]
        assert (
            c.scalar(
                select(func.count())
                .select_from(support_history)
                .where(
                    support_history.c.reason == "git-source-update",
                    support_history.c.point_id == pid,
                )
            )
            == 1
        )
    assert manager.client.get("/api/v1/news").json()["items"][0]["payload"]["commit"] == "b" * 40


def test_static_snapshot_auto_transfer_without_fake_revision(manager, static_bundle, pg_database):
    _, public = setup(manager, static_bundle)
    client = manager.client
    sub(client, public, "skills-ru")
    altered = [
        {**root, "body": root["body"] + "\nA new static source text."}
        if root["id"] == "skills-ru"
        else root
        for root in manager.app.state.hosted_bundle.roots
    ]
    new_public = PublicPoints(pg_database, roots=altered, build_revision="next-build")
    Social(new_public).work()
    with pg_database.connect() as c:
        row = (
            c.execute(select(subscriptions).where(subscriptions.c.point_id == "skills-ru"))
            .mappings()
            .one()
        )
        assert row["revision_id"] is None
        assert row["content_digest"] == new_public.get("skills-ru")["content_digest"]
        assert "new static source" in row["static_body"]
        assert (
            c.scalar(
                select(func.count())
                .select_from(support_history)
                .where(support_history.c.reason == "git-source-update")
            )
            == 1
        )


def test_target_changed_stales_proposal_and_silence_does_not_vote(
    manager, static_bundle, pg_database
):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    sub(client, public, pid)
    proposal(client, public, pid)
    with pg_database.begin() as c:
        c.execute(update(proposals).values(closes_at=datetime.now(UTC) - timedelta(seconds=1)))
    Social(public).work()
    with pg_database.connect() as c:
        q = c.execute(select(proposals)).mappings().one()
        assert (
            q["state"] == "retained"
            and q["result"]["old_influence"] == "0"
            and q["result"]["new_influence"] == "0"
        )


def test_unsubscribe_withdraws_ballot_and_audience_is_event_time(
    manager, static_bundle, pg_database
):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    client = manager.client
    other = second(manager)
    sub(client, public, pid)
    sub(other, public, pid)
    qid = proposal(client, public, pid)
    vote(client, qid, "old")
    sub(client, public, pid, False)
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(ballots)) == 0
    Social(public).work()
    assert any(
        row["kind"] == "proposal-opened" for row in client.get("/api/v1/me/inbox").json()["items"]
    )
    sub(client, public, pid, True)
    assert client.get(f"/api/v1/me/subscriptions/{pid}").json()["ballot"] is None


def test_two_subscribers_race_votes_and_exactly_once_adoption(manager, static_bundle, pg_database):
    from concurrent.futures import ThreadPoolExecutor

    first, public = setup(manager, static_bundle)
    pid = first["id"]
    alice = manager.client
    bob = second(manager)
    sub(alice, public, pid)
    sub(bob, public, pid)
    qid = proposal(alice, public, pid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: vote(client, qid, "new"), [alice, bob]))
    assert {row["state"] for row in results} <= {"open", "adopted"}
    with pg_database.connect() as c:
        assert c.scalar(select(proposals.c.state)) == "adopted"
        assert (
            c.scalar(
                select(func.count())
                .select_from(social_events)
                .where(social_events.c.kind == "proposal-adopted")
            )
            == 1
        )


def test_static_root_retirement_and_reintroduction_are_audited_once(
    manager, static_bundle, pg_database
):
    _, public = setup(manager, static_bundle)
    sub(manager.client, public, "skills-ru")
    roots = manager.app.state.hosted_bundle.roots
    removed = PublicPoints(pg_database, roots=[r for r in roots if r["id"] != "skills-ru"])
    Social(removed).work()
    Social(removed).work()
    with pg_database.connect() as c:
        assert (
            c.scalar(
                select(func.count())
                .select_from(social_events)
                .where(social_events.c.kind == "git-source-retired")
            )
            == 1
        )
    Social(public).work()
    assert manager.client.get("/api/v1/me/subscriptions/skills-ru").json()["subscription"]["active"]
    with pg_database.connect() as c:
        assert (
            c.scalar(
                select(func.count())
                .select_from(social_events)
                .where(social_events.c.kind == "git-source-update")
            )
            == 1
        )


def test_competing_authors_only_one_open_proposal(manager, static_bundle, pg_database):
    from concurrent.futures import ThreadPoolExecutor

    first, public = setup(manager, static_bundle)
    other = second(manager)
    point = public.get(first["id"])
    data = {
        **payload(manager.client, body="Competing revision"),
        "expected_revision_id": point["revision_id"],
        "expected_digest": point["content_digest"],
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda client: client.post(
                    f"/api/v1/points/{first['id']}/proposals",
                    json=data,
                    headers={"Idempotency-Key": uuid4().hex},
                ),
                [manager.client, other],
            )
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(proposals)) == 1


def test_changed_reference_prevents_even_unanimous_adoption(manager, static_bundle, pg_database):
    first, public = setup(manager, static_bundle)
    pid = first["id"]
    sub(manager.client, public, pid)
    qid = proposal(manager.client, public, pid)
    altered = [
        {**r, "body": r["body"] + " Changed definition"} if r["id"] == "skills-ru" else r
        for r in manager.app.state.hosted_bundle.roots
    ]
    from node06_service.hosted import HostedBundle

    original = manager.app.state.hosted_bundle
    replacement = HostedBundle(static_bundle)
    replacement.roots = altered
    manager.app.state.hosted_bundle = replacement
    assert vote(manager.client, qid, "new")["state"] == "stale"
    assert public.get(pid)["revision_id"] == first["revision_id"]
    manager.app.state.hosted_bundle = original


def test_site_welcome_requires_proposal_but_theme_stays_owner_managed(manager, static_bundle):
    from node06_service.site_registry import SiteRegistry
    from test_site_management import create, settings_payload, state

    _, public = setup(manager, static_bundle)
    site = create(manager)
    pid = site["site_id"]
    SiteRegistry(manager.app.state.database).verify_site(
        pid, actor_user_id=manager.user, proof_fetcher=lambda _: site["proof_document"].encode()
    )
    sub(manager.client, public, pid)
    current = state(manager, site)
    response = manager.client.patch(
        f"/api/v1/sites/{pid}",
        json=settings_payload(current, welcome_body="Silent replacement"),
    )
    assert response.status_code == 409
    response = manager.client.patch(
        f"/api/v1/sites/{pid}", json=settings_payload(current, theme={"bg": "#123"})
    )
    assert response.status_code == 200
    qid = proposal(manager.client, public, pid, body="Community welcome")
    assert vote(manager.client, qid, "new")["state"] == "adopted"
    assert public.get(pid)["body"] == "Community welcome"
    assert public.get(pid)["lang"] == "ru"
    assert state(manager, site)["settings_revision"] > current["settings_revision"]


def test_social_upgrade_keeps_existing_publication(manager, static_bundle, pg_database):
    import os
    import subprocess
    import sys
    from pathlib import Path

    first, public = setup(manager, static_bundle)
    with pg_database.connect() as c:
        env = {
            **os.environ,
            "NODE06_DATABASE_URL": c.engine.url.render_as_string(hide_password=False),
        }
    for operation, revision in (("downgrade", "0009_point_authoring"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode()
    assert public.get(first["id"])["revision_id"] == first["revision_id"]
    assert sub(manager.client, public, first["id"])["active"]


def test_static_changelog_exists_without_subscribers(manager, static_bundle, pg_database):
    _, public = setup(manager, static_bundle)
    Social(public).work()
    roots = [
        {**r, "body": r["body"] + " Source correction"} if r["id"] == "skills-ru" else r
        for r in manager.app.state.hosted_bundle.roots
    ]
    changed = PublicPoints(pg_database, roots=roots, build_revision="fresh-build")
    Social(changed).work()
    with pg_database.connect() as c:
        assert (
            c.scalar(
                select(func.count())
                .select_from(social_events)
                .where(social_events.c.kind == "git-source-update")
            )
            == 1
        )
        assert c.scalar(select(func.count()).select_from(subscriptions)) == 0
