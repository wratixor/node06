"""Run against a disposable database named node06_test_*; each test owns one schema."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from node06_service.models import (
    edge_claims,
    events,
    point_edges,
    points,
    site_claims,
    sites,
    users,
)
from node06_service.site_claims import ProofMismatchError
from node06_service.site_registry import (
    ALL_SITES_ID,
    SiteClaimExpiredError,
    SiteConflictError,
    SiteNotFoundError,
    SiteRegistry,
    SiteRegistryError,
)
from sqlalchemy import func, select, update

ROOT = Path(__file__).resolve().parents[2]


def pending_site(registry, owner, origin="https://registry.example", **kwargs):
    return registry.create_pending_site(
        owner_user_id=owner, origin=origin, welcome_body="Welcome", **kwargs
    )


def test_migration_can_downgrade_and_upgrade_again(pg_database):
    with pg_database.connect() as connection:
        url = connection.engine.url.render_as_string(hide_password=False)
    env = {**os.environ, "NODE06_DATABASE_URL": url}
    for operation, revision in (("downgrade", "0001_bootstrap_schema"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    with pg_database.connect() as connection:
        assert (
            connection.execute(select(points.c.id).where(points.c.id == ALL_SITES_ID)).scalar_one()
            == ALL_SITES_ID
        )


def test_migration_bootstraps_directory_and_rejects_duplicate_origin_atomically(pg_database):
    registry = SiteRegistry(pg_database)
    owners = [registry.create_placeholder_user(f"owner-{index}") for index in range(2)]
    barrier = Barrier(2)

    def create(owner):
        barrier.wait(timeout=5)
        try:
            return pending_site(registry, owner)
        except SiteConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, owners))
    assert sum(result is not None for result in results) == 1
    with pg_database.connect() as connection:
        assert connection.execute(select(func.count()).select_from(sites)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(site_claims)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(events)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(points)).scalar_one() == 2
        assert connection.execute(
            select(points.c.current_revision_id).where(points.c.id == ALL_SITES_ID)
        ).scalar_one()


def test_simultaneous_verify_is_idempotent_and_does_not_hold_network_transaction(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("owner")
    pending = pending_site(registry, owner)
    barrier = Barrier(2)

    def fetch(_origin):
        # Both requests reach this point before either can finish. A transaction
        # holding the site lock during I/O would make this barrier time out.
        barrier.wait(timeout=5)
        return pending.proof_document.encode()

    def verify(_index):
        return registry.verify_site(pending.site_id, actor_user_id=owner, proof_fetcher=fetch)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(verify, range(2)))
    assert results[0] == results[1]
    replay = registry.verify_site(
        pending.site_id,
        actor_user_id=owner,
        proof_fetcher=lambda _: pytest.fail("Replay must not fetch the proof again"),
    )
    assert replay == results[0]
    with pg_database.connect() as connection:
        assert connection.execute(select(site_claims.c.attempt_count)).scalar_one() == 2
        for table in (point_edges, edge_claims):
            assert connection.execute(select(func.count()).select_from(table)).scalar_one() == 1
        assert (
            connection.execute(
                select(func.count()).select_from(events).where(events.c.kind == "site_verified")
            ).scalar_one()
            == 1
        )


def test_two_distinct_sites_share_one_directory(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("owner")
    pending = [pending_site(registry, owner, f"https://site-{i}.example") for i in range(2)]
    barrier = Barrier(2)

    def verify(site):
        def fetch(_origin):
            barrier.wait(timeout=5)
            return site.proof_document.encode()

        return registry.verify_site(site.site_id, actor_user_id=owner, proof_fetcher=fetch)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(list(pool.map(verify, pending))) == 2
    with pg_database.connect() as connection:
        assert connection.execute(select(func.count()).select_from(point_edges)).scalar_one() == 2


@pytest.mark.parametrize("mutation", ["owner", "state", "origin", "digest", "account"])
def test_state_changes_during_fetch_cannot_publish_stale_proof(pg_database, mutation):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("owner")
    other = registry.create_placeholder_user("other")
    pending = pending_site(registry, owner)

    def fetch(_origin):
        # A separate committed transaction models a concurrent management change.
        with pg_database.begin() as connection:
            if mutation == "account":
                connection.execute(
                    update(users).where(users.c.id == owner).values(state="disabled")
                )
            elif mutation == "digest":
                connection.execute(update(site_claims).values(challenge_digest="0" * 64))
            else:
                values = {
                    "owner": {"owner_user_id": other},
                    "state": {"state": "inactive"},
                    "origin": {"claimed_origin": "https://changed.example"},
                }[mutation]
                connection.execute(
                    update(sites).where(sites.c.id == pending.site_id).values(**values)
                )
        return pending.proof_document.encode()

    with pytest.raises(SiteRegistryError):
        registry.verify_site(pending.site_id, actor_user_id=owner, proof_fetcher=fetch)
    with pg_database.connect() as connection:
        assert connection.execute(select(site_claims.c.attempt_count)).scalar_one() == 1
        assert connection.execute(select(site_claims.c.verified_at)).scalar_one() is None
        assert connection.execute(select(func.count()).select_from(point_edges)).scalar_one() == 0


def test_proof_expiring_during_fetch_is_not_accepted(pg_database):
    clock = [datetime(2026, 10, 21, tzinfo=UTC)]
    registry = SiteRegistry(pg_database, clock=lambda: clock[0])
    owner = registry.create_placeholder_user("owner")
    pending = pending_site(registry, owner)

    def fetch(_origin):
        clock[0] = pending.expires_at
        return pending.proof_document.encode()

    with pytest.raises(SiteClaimExpiredError):
        registry.verify_site(pending.site_id, actor_user_id=owner, proof_fetcher=fetch)
    with pytest.raises(SiteNotFoundError):
        registry.get_public_site(pending.site_id)


def test_reclaim_and_wrong_actor_do_not_reuse_an_existing_site(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("owner")
    other = registry.create_placeholder_user("other")
    pending = pending_site(registry, owner)
    with pytest.raises(SiteRegistryError):
        registry.verify_site(
            pending.site_id,
            actor_user_id=other,
            proof_fetcher=lambda _: pytest.fail("Unauthorized actor must not trigger network I/O"),
        )
    with pytest.raises(ProofMismatchError):
        registry.verify_site(pending.site_id, actor_user_id=owner, proof_fetcher=lambda _: b"wrong")
    with pytest.raises(SiteClaimExpiredError):
        registry.verify_site(
            pending.site_id,
            actor_user_id=owner,
            now=pending.expires_at + timedelta(seconds=1),
            proof_fetcher=lambda _: pytest.fail("Expired claim must not trigger network I/O"),
        )
    with pytest.raises(SiteConflictError):
        pending_site(registry, other)
    registry.verify_site(
        pending.site_id,
        actor_user_id=owner,
        proof_fetcher=lambda _: pending.proof_document.encode(),
    )
    with pytest.raises(SiteConflictError):
        pending_site(registry, other)
    with pg_database.begin() as connection:
        connection.execute(update(sites).values(state="inactive"))
    with pytest.raises(SiteConflictError):
        registry.verify_site(pending.site_id, actor_user_id=owner)
    with pytest.raises(SiteConflictError):
        pending_site(registry, other)
