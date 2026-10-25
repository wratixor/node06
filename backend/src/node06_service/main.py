import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .account_ui import router as account_router
from .auth import AuthError
from .auth_api import router as auth_router
from .author_api import router as author_router
from .authoring import AuthoringError
from .bridge import register_bridge
from .community_ui import router as community_router
from .compose_ui import router as compose_router
from .config import Settings, get_settings
from .db import Database
from .directory import router as directory_router
from .directory_ui import router as directory_ui_router
from .editor_ui import router as editor_router
from .feed_api import router as feed_router
from .geometry_api import router as geometry_router
from .hosted import management_path, register_hosted, request_origin
from .moderation_api import router as moderation_router
from .moderation_ui import router as moderation_ui_router
from .people_ui import router as people_ui_router
from .point_api import router as point_router
from .profile_link_api import router as profile_link_router
from .profile_packet_api import router as profile_packet_router
from .profile_sync_api import router as profile_sync_router
from .public_points import PublicPointError
from .quarantine_api import account_router as ban_account_router
from .quarantine_api import router as quarantine_router
from .quarantine_ui import router as quarantine_ui_router
from .request_limits import AuthBodyLimit
from .root_import import RootImportError
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
from .social_api import router as social_router
from .source_api import router as source_router
from .verifier import VerifierBusyError, VerifierTimeoutError


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task = None
        source_task = None
        profile_task = None
        if current_settings.database_url:
            from .social_worker import run

            task = asyncio.create_task(run(app, stop))
            from .source_worker import run as run_sources

            source_task = asyncio.create_task(run_sources(app, stop))
            from .profile_sync_worker import run as run_profiles

            profile_task = asyncio.create_task(run_profiles(app, stop))
        try:
            yield
        finally:
            stop.set()
            if task:
                await task
            if source_task:
                await source_task
            if profile_task:
                await profile_task
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
    app.include_router(source_router)
    app.include_router(social_router)
    app.include_router(feed_router)
    app.include_router(moderation_router)
    app.include_router(moderation_ui_router)
    app.include_router(quarantine_router)
    app.include_router(ban_account_router)
    app.include_router(quarantine_ui_router)
    app.include_router(geometry_router)
    app.include_router(community_router)
    app.include_router(author_router)
    app.include_router(editor_router)
    app.include_router(compose_router)
    app.include_router(people_ui_router)
    app.include_router(directory_router)
    app.include_router(directory_ui_router)
    app.include_router(point_router)
    app.include_router(profile_packet_router)
    app.include_router(profile_link_router)
    app.include_router(profile_sync_router)
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

    @app.exception_handler(RootImportError)
    async def source_error(request, exc):
        return JSONResponse(
            {"code": exc.code}, status_code=422, headers={"Cache-Control": "no-store"}
        )

    @app.exception_handler(AuthoringError)
    @app.exception_handler(PublicPointError)
    async def point_error(request: Request, exc):
        return JSONResponse(
            {"code": exc.code}, status_code=exc.status, headers={"Cache-Control": "no-store"}
        )

    from .influence import InfluenceUnavailable

    @app.exception_handler(InfluenceUnavailable)
    async def influence_error(request: Request, exc):
        return JSONResponse(
            {"code": exc.args[0]}, status_code=503, headers={"Cache-Control": "no-store"}
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
            request.url.path.startswith(
                (
                    "/api/v1/auth/",
                    "/api/v1/me",
                    "/api/v1/profile-links",
                    "/editor/confirm/",
                    "/api/v1/moderation",
                    "/api/v1/directory",
                )
            )
            or request.url.path.endswith("/manage")
            or (request.url.path.startswith("/api/v1/sites/") and "/source" in request.url.path)
            or request.url.path == "/api/v1/ui-config"
            or (
                request.url.path.startswith(("/api/v1/proposals", "/api/v1/people"))
                and request.method != "GET"
            )
            or (request.url.path.startswith("/api/v1/points") and request.method != "GET")
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
            "social_worker": getattr(
                app.state,
                "social_worker_status",
                {"state": "disabled" if not current_settings.database_url else "starting"},
            ),
            "source_worker": getattr(
                app.state,
                "source_worker_status",
                {"state": "starting" if current_settings.database_url else "disabled"},
            ),
            "implemented": [
                "health",
                "ready",
                "meta",
                "public_site_read",
                "public_point_read",
                "point_search",
                "point_authoring",
                "revision_subscriptions",
                "revision_proposals",
                "influence_t1",
                "opposite_pair_geometry",
                "point_blocks",
                "user_coordinates",
                "private_inbox",
                "creation_feed",
                "scoped_moderation",
                "scoped_bans_quarantine",
                "content_tombstones",
                "embedded_draft_confirmation",
                "compact_profile",
                "public_author_profiles",
                "public_directory_rankings",
                "author_blocks",
                "site_author_blocks",
                "trusted_tag_library",
                "authored_point_history",
                "bounded_neighbors",
                "account_sessions",
                "site_management",
                "site_management_ui",
                "site_home_blocks",
                "git_home_priority",
                "home_translations",
                "private_profile_packets",
                "bilateral_profile_links",
                "cross_server_profile_sync",
                "operator_root_publication",
                "owner_git_sources",
            ]
            + (["hosted_wiki"] if current_settings.hosted_dist else [])
            + (
                ["read_only_embed", "public_read_bridge"]
                if current_settings.hosted_dist and current_settings.embed_origin
                else []
            ),
            "not_implemented": [
                "embed_auth",
                "signed_point_reactions",
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
            from .visibility import hidden_ids

            with app.state.database.connect() as connection:
                if hidden_ids(
                    connection,
                    [site_id],
                    request.query_params.get("site") or current_settings.default_site_id,
                ):
                    raise SiteNotFoundError(site_id)
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
