"""Bounded, anonymous public reads for registered parent sites; never an API proxy."""

import html
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .hosted import CSP, PUBLIC_HEADERS, GraphUnavailable, request_origin
from .site_registry import SiteNotFoundError, SiteRegistry

METHODS = ["capabilities.get", "site.get", "point.get", "points.search"]
# Leave room for channel/request ID and the response envelope within 256 KiB.
MAX_RESPONSE_BYTES = 255 * 1024


def register_bridge(app: FastAPI) -> None:
    settings = app.state.settings
    if not settings.hosted_dist or not settings.embed_origin:
        return

    def error(code, status=400):
        return JSONResponse({"code": code}, status_code=status, headers=PUBLIC_HEADERS)

    def active_site(request, site_id):
        if request_origin(request) != settings.embed_origin:
            raise SiteNotFoundError(site_id)
        if not app.state.database.configured:
            raise GraphUnavailable("DATABASE_NOT_CONFIGURED")
        return SiteRegistry(app.state.database).get_public_site(site_id)

    @app.get("/bridge/assets/bridge.js")
    def script():
        return FileResponse(
            Path(__file__).parent / "ui/bridge.js",
            media_type="text/javascript",
            headers=PUBLIC_HEADERS,
        )

    @app.get("/bridge/assets/client.js")
    def client_script():
        return FileResponse(
            Path(__file__).parent / "ui/bridge-client.js",
            media_type="text/javascript",
            headers=PUBLIC_HEADERS,
        )

    @app.get("/bridge/v1/{site_id}/")
    def document(site_id: str, request: Request):
        try:
            site = active_site(request, site_id)
        except SiteNotFoundError:
            return error("SITE_NOT_FOUND", 404)
        except (GraphUnavailable, SQLAlchemyError):
            return error("GRAPH_UNAVAILABLE", 503)
        # Registry origins are already canonical; escape even trusted DB values in HTML.
        parents = f"{site.origin} {settings.management_origin}"
        source = (
            '<!doctype html><html><head><meta charset="utf-8"><title>NODE06 bridge</title>'
            '</head><body data-parents="'
            + html.escape(parents, quote=True)
            + '" data-site="'
            + html.escape(site.id, quote=True)
            + '">NODE06 public read bridge<script src="/bridge/assets/bridge.js"></script>'
            "</body></html>"
        )
        return HTMLResponse(
            source,
            headers={
                **PUBLIC_HEADERS,
                "Content-Security-Policy": CSP + "frame-ancestors " + parents,
            },
        )

    @app.get("/bridge/v1/{site_id}/read")
    def read(site_id: str, request: Request):
        try:
            site = active_site(request, site_id)
            params = dict(request.query_params)
            if len(request.query_params.multi_items()) != len(params):
                return error("INVALID_PARAMS")
            method = params.pop("method", None)
            if method not in METHODS:
                return error("METHOD_NOT_ALLOWED")
            if method in ("capabilities.get", "site.get"):
                if params:
                    return error("INVALID_PARAMS")
                data = (
                    {"methods": METHODS, "read_only": True, "parent_credentials": False}
                    if method == "capabilities.get"
                    else {"id": site.id, "origin": site.origin, "welcome_point_id": site.id}
                )
            else:
                key = "point_id" if method == "point.get" else "query"
                value = params.get(key, "")
                if set(params) != {key} or not 1 <= len(value) <= 128:
                    return error("INVALID_PARAMS")
                graph = app.state.hosted_bundle.graph(request)
                if method == "point.get":
                    data = next((point for point in graph if point["id"] == value), None)
                    if data is None:
                        return error("POINT_NOT_FOUND", 404)
                else:
                    query = value.casefold()
                    matches = [
                        {"id": point["id"], "preview": point.get("preview", "")[:500]}
                        for point in graph
                        if query in point["id"].casefold()
                        or query in point.get("preview", "").casefold()
                    ]
                    data = {"items": matches[:20], "truncated": len(matches) > 20}
            payload = json.dumps(data, ensure_ascii=False).encode()
            if len(payload) > MAX_RESPONSE_BYTES:
                return error("RESPONSE_TOO_LARGE", 413)
            return JSONResponse(data, headers=PUBLIC_HEADERS)
        except SiteNotFoundError:
            return error("SITE_NOT_FOUND", 404)
        except (GraphUnavailable, SQLAlchemyError):
            return error("GRAPH_UNAVAILABLE", 503)
