"""Hosted core, accepted operator roots and site projection; no votes or synthetic influence."""

import html
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .home_page import render_home
from .models import point_revisions, points, root_entries, root_sources, sites
from .root_render import render_root
from .site_registry import ALL_SITES_ID, SiteNotFoundError, SiteRegistry

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'; "
)
PUBLIC_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
ICONS = (
    "favicon.svg",
    "favicon.ico",
    "favicon-96x96.png",
    "apple-touch-icon.png",
    "web-app-manifest-192x192.png",
    "web-app-manifest-512x512.png",
    "site.webmanifest",
)


class GraphUnavailable(RuntimeError):
    pass


def request_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def validate_embed_origin(settings: Settings) -> None:
    if settings.embed_origin is None:
        return
    for value in (settings.management_origin, settings.embed_origin):
        if value and any(ord(char) <= 32 or ord(char) == 127 for char in value):
            raise ValueError("Origin cannot contain whitespace/control characters")
        parsed = urlsplit(value or "")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Management and embed require exact HTTPS origins without paths")
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = f":{parsed.port}" if parsed.port not in (None, 443) else ""
        if value != f"https://{host}{port}":
            raise ValueError("Use browser-canonical HTTPS origins (no explicit default port)")
    if urlsplit(settings.management_origin).hostname == urlsplit(settings.embed_origin).hostname:
        raise ValueError("Management and embed must use different hostnames (cookies ignore ports)")


def management_path(path: str, method: str) -> bool:
    return (
        path.startswith(("/account", "/sites", "/api/v1/auth/", "/api/v1/me"))
        or path == "/api/v1/ui-config"
        or (path.startswith("/api/v1/sites") and (method != "GET" or path.endswith("/manage")))
    )


class HostedBundle:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.page = (self.directory / "index.html").read_text()
        self.roots = json.loads((self.directory / "data/points.json").read_text())
        if not isinstance(self.roots, list) or any(p.get("origin") != "root" for p in self.roots):
            raise ValueError("Hosted bundle must contain a built root-point array")
        ids = {p["id"] for p in self.roots}
        if len(ids) != len(self.roots) or ALL_SITES_ID in ids:
            raise ValueError("Root IDs conflict with the provisional site directory")

    def graph(self, request: Request) -> list[dict]:
        database = request.app.state.database
        if not database.configured:
            raise GraphUnavailable("DATABASE_NOT_CONFIGURED")
        # The cap is explicit, never silent truncation.
        with database.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        sites.c.id,
                        points.c.created_at,
                        points.c.last_interaction_at,
                        point_revisions.c.body,
                    )
                    .join(points, sites.c.id == points.c.id)
                    .join(point_revisions, points.c.current_revision_id == point_revisions.c.id)
                    .where(
                        sites.c.state == "active",
                        sites.c.primary_origin.is_not(None),
                        points.c.lifecycle == "active",
                    )
                    .order_by(sites.c.id)
                    .limit(request.app.state.settings.hosted_site_limit + 1)
                )
                .mappings()
                .all()
            )
            directory = (
                connection.execute(
                    select(points.c.created_at, points.c.last_interaction_at).where(
                        points.c.id == ALL_SITES_ID
                    )
                )
                .mappings()
                .one()
            )
        if len(rows) > request.app.state.settings.hosted_site_limit:
            raise GraphUnavailable("GRAPH_CAPACITY_EXCEEDED")
        imported = []
        with database.connect() as connection:
            imported = (
                connection.execute(
                    select(
                        root_entries.c.point_id,
                        root_entries.c.site_id,
                        root_entries.c.lang,
                        root_sources.c.commit_sha,
                        root_sources.c.repository_url,
                        points.c.created_at,
                        points.c.last_interaction_at,
                        point_revisions.c.body,
                        point_revisions.c.declared_links,
                    )
                    .join(root_sources, root_sources.c.site_id == root_entries.c.site_id)
                    .join(sites, sites.c.id == root_sources.c.site_id)
                    .join(points, points.c.id == root_entries.c.point_id)
                    .join(point_revisions, point_revisions.c.id == points.c.current_revision_id)
                    .where(
                        sites.c.state == "active",
                        sites.c.primary_origin == root_sources.c.origin,
                        sites.c.owner_user_id == root_sources.c.owner_user_id,
                        root_entries.c.revision_id == points.c.current_revision_id,
                        points.c.lifecycle == "active",
                    )
                    .order_by(root_entries.c.point_id)
                    .limit(request.app.state.settings.hosted_site_limit * 101 + 1)
                )
                .mappings()
                .all()
            )
        if len(imported) > request.app.state.settings.hosted_site_limit * 101:
            raise GraphUnavailable("GRAPH_CAPACITY_EXCEEDED")
        result = list(self.roots)
        # Active site directory; self-service source claims are still P04.
        result.append(
            {
                "id": ALL_SITES_ID,
                "origin": "root",
                "lang": "und",
                "html": "<p>Все сайты / All sites</p>",
                "preview": "Все сайты / All sites",
                "created_at": directory["created_at"].isoformat(),
                "last_interaction_at": directory["last_interaction_at"].isoformat(),
                "links": [row["id"] for row in rows],
                "degree": len(rows),
                "coordinates": None,
                "coordinate_source": "display-only",
            }
        )
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "origin": "site",
                    "lang": "und",
                    "html": "<p>" + html.escape(row["body"]).replace("\n", "<br>") + "</p>",
                    "preview": row["body"][:180],
                    "links": [ALL_SITES_ID],
                    "degree": 1,
                    "created_at": row["created_at"].isoformat(),
                    "last_interaction_at": row["last_interaction_at"].isoformat(),
                    "coordinates": None,
                    "coordinate_source": "display-only",
                }
            )
        by_id = {point["id"]: point for point in result}
        active_sites = {row["id"] for row in rows}
        for row in imported:
            if row["site_id"] not in active_sites:
                continue
            pid = row["point_id"]
            links = list(row["declared_links"])
            if pid == row["site_id"]:
                links.append(ALL_SITES_ID)
            by_id[pid] = {
                "id": pid,
                "origin": "site" if pid == row["site_id"] else "root",
                "lang": row["lang"],
                "html": render_root(row["body"], row["site_id"]),
                "preview": row["body"][:180],
                "links": sorted(set(links)),
                "degree": len(set(links)),
                "coordinates": None,
                "coordinate_source": "display-only",
                "created_at": row["created_at"].isoformat(),
                "last_interaction_at": row["last_interaction_at"].isoformat(),
                "source": {
                    "kind": "operator-git",
                    "site_id": row["site_id"],
                    "repository_url": row["repository_url"],
                    "commit_sha": row["commit_sha"],
                },
            }
        # Retired/missing local roots do not leave visible dangling links.
        for point in by_id.values():
            point["links"] = [target for target in point["links"] if target in by_id]
            point["degree"] = len(point["links"])
        return list(by_id.values())

    def render(
        self, settings: Settings, *, field_path="/", site=None, theme=None, embedded=False
    ) -> str:
        title = html.escape((site and site.display_name) or settings.hosted_title)
        home = site.id if site else ""
        attributes = {
            "field-path": field_path,
            "home-point": home,
            "home-page": "true",
            "hosted": "true",
            "search-site": home if embedded else "",
            "tenant": "true" if site else "",
            "theme": json.dumps(theme or {}),
        }
        source = self.page.replace(
            '<body data-page="field"',
            '<body data-page="field" '
            + " ".join(
                f'data-{key}="{html.escape(value, quote=True)}"'
                for key, value in attributes.items()
            ),
        )
        source = source.replace("<title>NODE06 · node06</title>", f"<title>{title}</title>")
        source = source.replace(">NODE06</a>", f">{title}</a>")
        start = source.index('<section id="start-page"')
        end = source.index('<section id="root-field"', start)
        welcome = render_home(
            site, (site and site.display_name) or settings.hosted_title, field_path
        )
        source = source[:start] + welcome + source[end:]
        if home:
            source = source.replace('href="/"', f'href="{html.escape(field_path, quote=True)}"')
        feed = field_path + "?" + urlencode({"p": ALL_SITES_ID, "mode": "feed"})
        source = source.replace('href="/recent/"', f'href="{html.escape(feed, quote=True)}"')
        navigation = f'<a href="{field_path}?p=all-sites&amp;open=all-sites">ALL SITES</a>'
        if embedded:
            source = source.replace(
                '<a href="/about/">ABOUT</a>',
                f'<a href="{html.escape(settings.management_origin)}/about/" '
                'target="_blank" rel="noopener">ABOUT ↗</a>',
            )
            navigation += (
                f'<a href="{html.escape(settings.management_origin)}/account/" '
                'target="_blank" rel="noopener">ACCOUNT ↗</a>'
            )
            source = source.replace("ROOT ERA / STATIC FIELD", "READ ONLY / SHARED GRAPH")
        else:
            navigation += '<a href="/sites/">MY SITES</a><a href="/account/">ACCOUNT</a>'
            source = source.replace("ROOT ERA / STATIC FIELD", "ROOTS + SITES / READ ONLY")
        source = source.replace(
            "static root field · social layer planned",
            "shared graph · read-only preview · social layer planned",
        )
        return source.replace("</nav>", navigation + "</nav>", 1)


def register_hosted(app: FastAPI, settings: Settings) -> None:
    validate_embed_origin(settings)
    if settings.hosted_dist is None:
        return
    bundle = HostedBundle(settings.hosted_dist)
    app.state.hosted_bundle = bundle
    app.mount("/assets", StaticFiles(directory=bundle.directory / "assets"), name="assets")

    def page(request: Request, site_id=None, embedded=False):
        if embedded and (
            not settings.embed_origin or request_origin(request) != settings.embed_origin
        ):
            return JSONResponse(
                {"code": "EMBED_ORIGIN_REQUIRED"}, status_code=404, headers=PUBLIC_HEADERS
            )
        if (
            not embedded
            and settings.management_origin
            and request_origin(request) != settings.management_origin
        ):
            return JSONResponse(
                {"code": "HOSTED_ORIGIN_REQUIRED"}, status_code=404, headers=PUBLIC_HEADERS
            )
        selected = site_id or settings.default_site_id
        site = None
        theme = {}
        if selected:
            if not request.app.state.database.configured:
                return JSONResponse(
                    {"code": "DATABASE_NOT_CONFIGURED"}, status_code=503, headers=PUBLIC_HEADERS
                )
            try:
                site = SiteRegistry(request.app.state.database).get_public_site(selected)
                with request.app.state.database.connect() as connection:
                    theme = connection.execute(
                        select(sites.c.theme).where(sites.c.id == selected)
                    ).scalar_one()
            except SiteNotFoundError:
                return JSONResponse(
                    {"code": "SITE_NOT_FOUND"}, status_code=404, headers=PUBLIC_HEADERS
                )
            except SQLAlchemyError:
                return JSONResponse(
                    {"code": "GRAPH_UNAVAILABLE"}, status_code=503, headers=PUBLIC_HEADERS
                )
        field_path = (
            f"/embed/v1/{site.id}/" if embedded else f"/sites/{site.id}/" if site_id else "/"
        )
        source = bundle.render(
            settings, field_path=field_path, site=site, theme=theme, embedded=embedded
        )
        ancestors = f"{site.origin} {settings.management_origin}" if embedded else "'none'"
        headers = {
            **PUBLIC_HEADERS,
            "Content-Security-Policy": CSP + "frame-ancestors " + ancestors,
        }
        if not embedded:
            headers["X-Frame-Options"] = "DENY"
        return HTMLResponse(source, headers=headers)

    @app.get("/data/points.json")
    def graph(request: Request):
        try:
            return JSONResponse(bundle.graph(request), headers=PUBLIC_HEADERS)
        except GraphUnavailable as exc:
            return JSONResponse({"code": str(exc)}, status_code=503, headers=PUBLIC_HEADERS)
        except SQLAlchemyError:
            return JSONResponse(
                {"code": "GRAPH_UNAVAILABLE"}, status_code=503, headers=PUBLIC_HEADERS
            )

    @app.get("/")
    def root(request: Request):
        return page(request)

    @app.get("/sites/{site_id}/")
    def site_page(site_id: str, request: Request):
        return page(request, site_id)

    @app.get("/embed/v1/{site_id}/")
    def embed_page(site_id: str, request: Request):
        return page(request, site_id, embedded=True)

    @app.get("/recent/")
    def recent():
        return RedirectResponse("/?p=all-sites&mode=feed")

    @app.get("/about/")
    def about():
        return FileResponse(
            bundle.directory / "about/index.html",
            headers={
                **PUBLIC_HEADERS,
                "Content-Security-Policy": CSP + "frame-ancestors 'none'",
            },
        )

    @app.get("/p/{point_id}/")
    def point_link(point_id: str):
        return RedirectResponse("/?" + urlencode({"p": point_id, "open": point_id}))

    for old_prefix in ("ru", "en"):
        # These routes only preserve published links; they never select a locale.
        def old_entry(request: Request):
            return RedirectResponse("/" + ("?" + request.url.query if request.url.query else ""))

        app.add_api_route(f"/{old_prefix}/", old_entry, methods=["GET"])

    for filename in ICONS:
        # Do not expose the closure default as an overridable query parameter.
        def icon_endpoint(path=bundle.directory / filename):
            async def serve():
                return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

            return serve

        app.add_api_route("/" + filename, icon_endpoint(), methods=["GET"])
