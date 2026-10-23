"""Anonymous embedded drafts; publication requires explicit trusted top-level consent."""

import html
from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from .account_ui import HEADERS
from .author_api import Content, write
from .editor_ui import PAGE
from .hosted import CSP, PUBLIC_HEADERS, request_origin
from .site_registry import SiteNotFoundError, SiteRegistry

router = APIRouter()


@router.get("/compose/v1/{site_id}/", response_class=HTMLResponse)
def compose(site_id: str, request: Request):
    settings = request.app.state.settings
    if request_origin(request) != settings.embed_origin:
        return JSONResponse({"code": "EMBED_ORIGIN_REQUIRED"}, status_code=404)
    if not request.app.state.database.configured:
        return JSONResponse(
            {"code": "DATABASE_NOT_CONFIGURED"}, status_code=503, headers=PUBLIC_HEADERS
        )
    try:
        site = SiteRegistry(request.app.state.database).get_public_site(site_id)
    except SiteNotFoundError:
        return JSONResponse({"code": "SITE_NOT_FOUND"}, status_code=404, headers=PUBLIC_HEADERS)
    except SQLAlchemyError:
        return JSONResponse({"code": "SITES_UNAVAILABLE"}, status_code=503, headers=PUBLIC_HEADERS)
    parent_origin = request.query_params.get("parent_origin", site.origin)
    if parent_origin not in (site.origin, settings.embed_origin, settings.management_origin):
        return JSONResponse({"code": "PARENT_ORIGIN_FORBIDDEN"}, status_code=403)
    # No credentials, session routes or arbitrary themes in the draft frame.
    attributes = {
        "data-external-editor": "true",
        "data-search-site": site.id,
        "data-parent-origin": parent_origin,
        "data-management-origin": settings.management_origin,
    }
    attrs = " ".join(
        f'{key}="{html.escape(value, quote=True)}"' for key, value in attributes.items()
    )
    page = PAGE.replace('data-page="editor"', 'data-page="editor" ' + attrs)
    page = page.replace("/editor/client.js", "/compose/assets/client.js")
    page = page.replace("/editor/style.css", "/compose/assets/style.css")
    page = page.replace("Проверяем вход…", "Загружаем связи…")
    page = page.replace("Опубликовать</button>", "Проверить и опубликовать</button>")
    return HTMLResponse(
        page,
        headers={
            **PUBLIC_HEADERS,
            "Content-Security-Policy": CSP
            + f"frame-ancestors {site.origin} {settings.embed_origin} {settings.management_origin}",
        },
    )


@router.get("/compose/assets/client.js")
def compose_script():
    return Response(
        files("node06_service").joinpath("ui/editor.js").read_text(),
        media_type="application/javascript",
        headers=PUBLIC_HEADERS,
    )


@router.get("/compose/assets/style.css")
def compose_style():
    from .editor_ui import style

    return style()


@router.get("/editor/confirm/{site_id}/", response_class=HTMLResponse)
def confirm(site_id: str, request: Request):
    if not request.app.state.database.configured:
        return JSONResponse(
            {"code": "DATABASE_NOT_CONFIGURED"}, status_code=503, headers=PUBLIC_HEADERS
        )
    try:
        site = SiteRegistry(request.app.state.database).get_public_site(site_id)
    except SiteNotFoundError:
        return JSONResponse({"code": "SITE_NOT_FOUND"}, status_code=404, headers=PUBLIC_HEADERS)
    except SQLAlchemyError:
        return JSONResponse({"code": "SITES_UNAVAILABLE"}, status_code=503, headers=PUBLIC_HEADERS)
    settings = request.app.state.settings
    attrs = f'data-embed-origin="{html.escape(settings.embed_origin or "", quote=True)}" '
    attrs += f'data-site="{html.escape(site.id, quote=True)}"'
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Публикация точки</title>
<link rel="stylesheet" href="/assets/site.css"><link rel="stylesheet" href="/editor/style.css">
<script src="/editor/confirm.js" defer></script></head><body data-page="editor" """
        + attrs
        + """>
<main><h1>Опубликовать точку</h1><p>Сайт: """
        + html.escape(site.origin)
        + """</p>
<p id="confirmation-status" role="status">Ожидаем текст редактора…</p>
<a href="/account/" target="_blank" rel="noopener">Войти / зарегистрироваться</a>
<button id="confirmation-login" type="button">Продолжить после входа</button>
<section id="confirmation-draft" hidden><h2>Связи</h2><ul id="confirmation-links"></ul>
<h2>Текст</h2><pre id="confirmation-body"></pre>
<button id="confirmation-publish" type="button" disabled>Опубликовать от моего имени</button>
</section><noscript>Для публикации нужен JavaScript.</noscript></main></body></html>""",
        headers=HEADERS,
    )


@router.get("/editor/confirm.js")
def confirm_script():
    return Response(
        files("node06_service").joinpath("ui/editor-confirm.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.post("/editor/confirm/{site_id}/", status_code=201)
def publish(site_id: str, payload: Content, request: Request):
    return write(request, payload, compose_site=site_id)
