from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .config import Settings, get_settings
from .db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.database.dispose()

    app = FastAPI(
        title="NODE06 service", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.settings = current_settings
    app.state.database = Database(current_settings.database_url)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID", uuid4().hex)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "node06", "version": app.version}

    @app.get("/api/v1/ready")
    def ready(request: Request):
        is_ready, code = app.state.database.ready()
        if is_ready:
            return {"status": "ready"}
        return JSONResponse(
            status_code=503,
            content={
                "code": code,
                "message": "Service dependencies are not ready.",
                "request_id": request.state.request_id,
            },
        )

    @app.get("/api/v1/meta")
    def meta() -> dict[str, object]:
        return {
            "api_version": "v1",
            "service": "node06",
            "build_revision": current_settings.build_revision,
            "embed_protocol": "node06-embed/1",
            "implemented": ["health", "ready", "meta"],
            "not_implemented": ["auth", "sites", "points", "imports", "billing"],
        }

    return app


app = create_app()
