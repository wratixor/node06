import asyncio
from datetime import UTC, datetime

import httpx
from node06_service.config import Settings
from node06_service.main import create_app


def get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def request() -> httpx.Response:
        app = create_app(Settings(database_url=None, build_revision="test"))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def test_health_is_live_without_database() -> None:
    response = get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "node06", "version": "0.1.0"}
    assert response.headers["x-request-id"]


def test_readiness_is_not_liveness() -> None:
    response = get("/api/v1/ready", headers={"X-Request-ID": "test-request"})
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"
    assert response.headers["x-request-id"] == "test-request"


def test_meta_marks_future_domains_as_unimplemented() -> None:
    response = get("/api/v1/meta")
    assert response.status_code == 200
    assert response.json()["build_revision"] == "test"
    assert "signed_point_reactions" in response.json()["not_implemented"]
    assert "point_authoring" in response.json()["implemented"]
    assert "public_site_read" in response.json()["implemented"]
    assert "site_management" in response.json()["implemented"]
    assert "embed_auth" in response.json()["not_implemented"]


def test_public_site_read_uses_shared_site_registry() -> None:
    from node06_service.db import Database
    from node06_service.models import metadata
    from node06_service.site_registry import SiteRegistry
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    database = Database("sqlite+pysqlite:///:memory:")
    assert database._engine is not None
    database._engine.dispose()
    database._engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(database._engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        # Match the PostgreSQL-only ban query in this lightweight read fixture.
        dbapi_connection.create_function(
            "clock_timestamp",
            0,
            lambda: datetime.now(UTC).replace(tzinfo=None).isoformat(" "),
        )

    metadata.create_all(database._engine)
    registry = SiteRegistry(database)
    owner = registry.create_placeholder_user("site-reader-owner")
    pending = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://read.example",
        welcome_body="Reader welcome",
    )
    registry.verify_site(
        pending.site_id,
        actor_user_id=owner,
        proof_fetcher=lambda _origin: pending.proof_document.encode(),
    )

    async def request() -> httpx.Response:
        app = create_app(Settings(database_url=None, build_revision="test"))
        app.state.database = database
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(f"/api/v1/sites/{pending.site_id}")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json()["id"] == pending.site_id
    assert response.json()["welcome_body"] == "Reader welcome"


def test_public_social_summary_without_database_is_explicitly_unavailable():
    response = get("/api/v1/points/skills-ru/social-summary")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_NOT_CONFIGURED"
    assert response.headers["cache-control"] == "no-store"
