import asyncio

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
    assert "points" in response.json()["not_implemented"]
