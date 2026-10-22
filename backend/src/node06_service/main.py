from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .account_ui import router as account_router
from .auth import AuthError
from .auth_api import router as auth_router
from .bridge import register_bridge
from .config import Settings, get_settings
from .db import Database
from .hosted import management_path, register_hosted, request_origin
from .request_limits import AuthBodyLimit
from .schemas import PublicSiteResponse
from .site_api import router as site_router
from .site_claims import ProofFetchError, SiteClaimError
from .site_registry import (
    SiteAttemptsError,
    SiteClaimExpiredError,
    SiteConflictError,
    SiteNotFoundError,
    SitePermissionError,
    SiteRegistry,
    SiteRegistryError,
)
from .site_ui import router as site_ui_router
from .verifier import VerifierBusyError, VerifierTimeoutError


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
    app.add_middleware(AuthBodyLimit)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(site_router)
    app.include_router(site_ui_router)

    @app.exception_handler(SiteRegistryError)
    @app.exception_handler(SiteClaimError)
    async def site_error(request: Request, exc):
        status = 400
        headers = {}
        if isinstance(exc, SiteNotFoundError):
            status = 404
        elif isinstance(exc, SitePermissionError):
            status = 403
        elif isinstance(exc, (SiteConflictError, SiteClaimExpiredError)):
            status = 409
        elif isinstance(exc, SiteAttemptsError):
            status = 429
        elif isinstance(exc, VerifierBusyError):
            status, headers = 503, {"Retry-After": "2"}
        elif isinstance(exc, VerifierTimeoutError):
            status = 504
        elif isinstance(exc, ProofFetchError):
            status = 502
        return JSONResponse(
            {"code": exc.code, "message": str(exc), "request_id": request.state.request_id},
            status_code=status,
            headers=headers,
        )

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
        return JSONResponse(
            {
                "code": exc.code,
                "message": "Account request could not be completed.",
                "request_id": request.state.request_id,
            },
            status_code=exc.status,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, _exc: RequestValidationError):
        # FastAPI's default error body includes submitted values, including secrets.
        return JSONResponse(
            {
                "code": "INVALID_INPUT",
                "message": "Check the submitted fields.",
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID", uuid4().hex)
        if (
            current_settings.embed_origin
            and management_path(request.url.path, request.method)
            and request_origin(request) != current_settings.management_origin
        ):
            return JSONResponse(
                {"code": "MANAGEMENT_ORIGIN_REQUIRED"},
                status_code=404,
                headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"},
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if (
            request.url.path.startswith(("/api/v1/auth/", "/api/v1/me"))
            or request.url.path.endswith("/manage")
            or request.url.path == "/api/v1/ui-config"
            or (request.url.path.startswith("/api/v1/sites") and request.method != "GET")
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
            response.headers["X-Frame-Options"] = "DENY"
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
            "implemented": [
                "health",
                "ready",
                "meta",
                "public_site_read",
                "account_sessions",
                "site_management",
                "site_management_ui",
            ]
            + (["hosted_wiki"] if current_settings.hosted_dist else [])
            + (
                ["read_only_embed", "public_read_bridge"]
                if current_settings.hosted_dist and current_settings.embed_origin
                else []
            ),
            "not_implemented": [
                "embed_auth",
                "points",
                "imports",
                "billing",
            ],
        }

    @app.get("/api/v1/sites/{site_id}", response_model=PublicSiteResponse)
    def public_site(site_id: str, request: Request):
        if not app.state.database.configured:
            return JSONResponse(
                status_code=503,
                content={
                    "code": "DATABASE_NOT_CONFIGURED",
                    "message": "Service dependencies are not ready.",
                    "request_id": request.state.request_id,
                },
            )
        try:
            site = SiteRegistry(app.state.database).get_public_site(site_id)
        except SiteNotFoundError:
            return JSONResponse(
                status_code=404,
                content={
                    "code": "SITE_NOT_FOUND",
                    "message": "Active site does not exist.",
                    "request_id": request.state.request_id,
                },
            )
        return PublicSiteResponse(**site.__dict__)

    register_hosted(app, current_settings)
    register_bridge(app)
    return app


app = create_app()
