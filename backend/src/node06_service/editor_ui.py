"""Trusted first-party editor; session credentials never enter an iframe parent."""

from hashlib import sha256
from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS
from .personal_ui import navigation

router = APIRouter(prefix="/editor")
PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>NODE06 — точка</title>
<link rel="stylesheet" href="/assets/site.css"><link rel="stylesheet" href="/editor/style.css">
<script src="/assets/point-picker.js" defer></script><script src="/editor/client.js" defer></script>
</head><body data-page="editor" data-hosted="true" data-point-picker="true">
{personal_navigation}
<main><h1 id="title">Новая точка</h1><p id="editor-status" role="status">Проверяем вход…</p>
<button id="retry-login" type="button" hidden>Продолжить после входа</button>
<div class="editor-meta">
<details><summary>Мои точки</summary><section id="my-points"><ul></ul>
<button id="more-mine" hidden>Ещё</button></section></details>
<details id="history" hidden><summary>История</summary><ol></ol>
<button id="more-history" type="button" hidden>Ещё версии</button></details>
<a id="open-point" hidden>Открыть точку</a></div>
<section id="tag-tools" aria-label="Связи и избранное" hidden>
<button id="open-library" type="button" hidden>Мои точки и избранное</button>
<div id="tag-search"></div><ul id="point-links" aria-label="Выбранные связи"></ul>
<div id="favorite-wrap" hidden><span class="editor-caption">Избранное</span>
<ul id="favorite-tags"></ul></div></section>
<form id="editor-form" hidden>
<div class="editor-toolbar"><button id="link-word" type="button"
title="Вставить ссылку на точку в текст">Вставить ссылку</button></div>
<textarea id="point-body" aria-label="Текст" placeholder="Текст точки…"
maxlength="8192" rows="14" required></textarea>
<button id="publish" type="submit">Опубликовать</button></form>
<noscript>Для редактора нужен JavaScript.</noscript></main></body></html>""".replace(
    "{personal_navigation}", navigation("editor")
)


@router.get("/", response_class=HTMLResponse)
def editor(request: Request):
    page = PAGE
    bundle = getattr(request.app.state, "hosted_bundle", None)
    if bundle:
        for name in ("site.css", "point-picker.js"):
            version = sha256((bundle.directory / "assets" / name).read_bytes()).hexdigest()[:12]
            page = page.replace(f"/assets/{name}", f"/assets/{name}?v={version}")
    headers = {
        **HEADERS,
        "Content-Security-Policy": HEADERS["Content-Security-Policy"].replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"
        ),
        "X-Frame-Options": "SAMEORIGIN",
    }
    return HTMLResponse(page, headers=headers)


@router.get("/client.js")
def client():
    return Response(
        files("node06_service").joinpath("ui/editor.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.get("/style.css")
def style():
    return Response(
        CSS
        + """
body[data-page=editor] .site-header{position:static}
body[data-page=editor] nav{flex-wrap:wrap;gap:.7rem;align-items:center}
body[data-page=editor] main{margin:1rem auto;max-width:960px;padding-top:8px}
body[data-page=editor] h1{font-size:28px;margin:8px 0}
#editor-status{font-size:13px;margin:4px 0;color:var(--muted)}
.editor-meta{display:flex;flex-wrap:wrap;gap:12px;font-size:13px;margin:8px 0}
.editor-meta details[open]{flex-basis:100%}
body[data-page=editor] #tag-tools{border:1px solid var(--line);padding:10px;margin:12px 0}
body[data-page=editor] #tag-search .point-search{max-width:none;width:100%;margin:0}
body[data-page=editor] #point-links,body[data-page=editor] #favorite-tags{
list-style:none;padding:0;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:6px}
body[data-page=editor] #point-links:empty{display:none}
body[data-page=editor] #point-links li,body[data-page=editor] #favorite-tags li{
display:inline-flex;align-items:center;border:1px solid var(--line);max-width:100%}
body[data-page=editor] #point-links a{padding:4px 8px;overflow-wrap:anywhere}
body[data-page=editor] #point-links button,body[data-page=editor] #favorite-tags button{
border:0;padding:4px 7px;margin:0;min-width:28px;font-size:13px}
#favorite-wrap{margin-top:8px}.editor-caption{font-size:12px;color:var(--muted)}
body[data-page=editor] #editor-form{padding:10px;border:1px solid var(--line)}
.editor-toolbar{margin-bottom:6px}.editor-toolbar button{padding:3px 9px}
body[data-page=editor] textarea{width:100%;height:clamp(280px,45vh,460px);
min-height:220px;resize:vertical;font:inherit;line-height:1.6;margin:0}
body[data-page=editor] #publish{display:block;margin:8px 0 0 auto;width:auto}
body[data-page=editor] button{max-width:100%;overflow-wrap:anywhere}
body[data-page=editor] pre{white-space:pre-wrap;overflow-wrap:anywhere}
body[data-page=editor] li,body[data-page=editor] summary{overflow-wrap:anywhere}
""",
        media_type="text/css",
        headers=HEADERS,
    )
