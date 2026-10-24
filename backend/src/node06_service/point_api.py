"""Public anonymous reads; private history and all mutations remain out of scope."""

import json
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .hosted import PUBLIC_HEADERS, request_origin
from .public_points import PublicPointError, PublicPoints

router = APIRouter(prefix="/api/v1/points")
Cursor = Annotated[str, Query(pattern=r"^(?:[a-z0-9][a-z0-9_-]{0,95})?$")]


def service(request, allowed):
    origin = request.app.state.settings.management_origin
    if origin and request_origin(request) != origin:
        raise PublicPointError("PUBLIC_ORIGIN_REQUIRED", 404)
    allowed = allowed | {"site"}
    params = request.query_params.multi_items()
    if len(params) != len(dict(params)) or set(request.query_params) - allowed:
        raise PublicPointError("INVALID_PARAMS", 400)
    site = request.query_params.get("site", request.app.state.settings.default_site_id)
    if site:
        from .site_registry import SiteNotFoundError, SiteRegistry
        from .visibility import SCOPE

        if not SCOPE.fullmatch(site) or site == "server":
            raise PublicPointError("INVALID_SCOPE", 422)
        try:
            SiteRegistry(request.app.state.database).get_public_site(site)
        except SiteNotFoundError as exc:
            raise PublicPointError("SCOPE_NOT_FOUND", 404) from exc
    bundle = getattr(request.app.state, "hosted_bundle", None)
    return PublicPoints(
        request.app.state.database,
        roots=bundle.roots if bundle else (),
        build_revision=request.app.state.settings.build_revision,
        site_id=site,
    )


def respond(action):
    try:
        value = action()
        if len(json.dumps(value, ensure_ascii=False).encode()) > 255 * 1024:
            raise PublicPointError("RESPONSE_TOO_LARGE", 413)
        return JSONResponse(value, headers=PUBLIC_HEADERS)
    except PublicPointError as exc:
        return JSONResponse({"code": exc.code}, status_code=exc.status, headers=PUBLIC_HEADERS)
    except SQLAlchemyError:
        return JSONResponse({"code": "POINTS_UNAVAILABLE"}, status_code=503, headers=PUBLIC_HEADERS)


@router.get("/search")
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=128)],
    after: Cursor = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return respond(
        lambda: service(request, {"q", "after", "limit"}).search(q, after=after, limit=limit)
    )


@router.get("/{point_id}/neighbors")
def neighbors(
    point_id: str,
    request: Request,
    after: Cursor = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
):
    from .root_import import POINT

    if not POINT.fullmatch(point_id):
        return JSONResponse({"code": "INVALID_POINT_ID"}, status_code=422, headers=PUBLIC_HEADERS)
    return respond(
        lambda: service(request, {"after", "limit"}).neighbors(point_id, after=after, limit=limit)
    )


@router.get("/{point_id}")
def point(point_id: str, request: Request):
    from .root_import import POINT

    if not POINT.fullmatch(point_id):
        return JSONResponse({"code": "INVALID_POINT_ID"}, status_code=422, headers=PUBLIC_HEADERS)
    return respond(lambda: service(request, set()).get(point_id))
