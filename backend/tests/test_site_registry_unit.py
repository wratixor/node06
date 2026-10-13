from datetime import UTC, datetime

import pytest
from node06_service.db import Database
from node06_service.models import edge_claims, metadata, point_edges, site_claims, sites
from node06_service.site_claims import ProofMismatchError
from node06_service.site_registry import ALL_SITES_ID, SiteConflictError, SiteRegistry
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool


def make_database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    assert (
        database._engine is not None
    )  # unit fixture only; PostgreSQL is required for migration tests.
    database._engine.dispose()
    database._engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database._engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(database._engine)
    return database


def test_two_sites_activate_into_one_all_sites_directory() -> None:
    database = make_database()
    registry = SiteRegistry(database)
    owner_a = registry.create_placeholder_user("owner-a")
    owner_b = registry.create_placeholder_user("owner-b")
    now = datetime(2026, 9, 15, tzinfo=UTC)
    pending_a = registry.create_pending_site(
        owner_user_id=owner_a,
        origin="https://a.example",
        welcome_body="Site A",
        now=now,
    )
    pending_b = registry.create_pending_site(
        owner_user_id=owner_b,
        origin="https://b.example",
        welcome_body="Site B",
        now=now,
    )

    registry.verify_site(
        pending_a.site_id,
        actor_user_id=owner_a,
        proof_fetcher=lambda _origin: pending_a.proof_document.encode(),
        now=now,
    )
    registry.verify_site(
        pending_b.site_id,
        actor_user_id=owner_b,
        proof_fetcher=lambda _origin: pending_b.proof_document.encode(),
        now=now,
    )

    with database.connect() as connection:
        active = (
            connection.execute(select(sites.c.id).where(sites.c.state == "active")).scalars().all()
        )
        assert set(active) == {pending_a.site_id, pending_b.site_id}
        edges = connection.execute(select(point_edges.c.point_a, point_edges.c.point_b)).all()
        assert set(edges) == {
            tuple(sorted((ALL_SITES_ID, pending_a.site_id))),
            tuple(sorted((ALL_SITES_ID, pending_b.site_id))),
        }
        claims = connection.execute(select(edge_claims.c.claim_ref)).scalars().all()
        assert set(claims) == {pending_a.site_id, pending_b.site_id}


def test_duplicate_origin_is_rejected_before_verification() -> None:
    database = make_database()
    registry = SiteRegistry(database)
    owner = registry.create_placeholder_user("owner")
    registry.create_pending_site(
        owner_user_id=owner, origin="https://same.example", welcome_body="First"
    )
    with pytest.raises(SiteConflictError):
        registry.create_pending_site(
            owner_user_id=owner, origin="https://same.example/", welcome_body="Second"
        )


def test_failed_proof_increments_attempt_even_when_verification_fails() -> None:
    database = make_database()
    registry = SiteRegistry(database)
    owner = registry.create_placeholder_user("owner")
    pending = registry.create_pending_site(
        owner_user_id=owner, origin="https://proof.example", welcome_body="Proof"
    )
    with pytest.raises(ProofMismatchError):
        registry.verify_site(
            pending.site_id,
            actor_user_id=owner,
            proof_fetcher=lambda _origin: b"wrong",
        )
    with database.connect() as connection:
        attempts = connection.execute(
            select(site_claims.c.attempt_count).where(site_claims.c.id == pending.claim_id)
        ).scalar_one()
        assert attempts == 1
