"""Trusted first-party editor; session credentials never enter an iframe parent."""

from hashlib import sha256
from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS

router = APIRouter(prefix="/editor")
PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>NODE06 — точка</title>
<link rel="stylesheet" href="/assets/site.css"><link rel="stylesheet" href="/editor/style.css">
<script src="/assets/point-picker.js" defer></script><script src="/editor/client.js" defer></script>
</head><body data-page="editor" data-hosted="true" data-point-picker="true">
<header class="site-header"><nav><a href="/">Вики</a>
· <a href="/account/">Аккаунт</a></nav></header>
<main><h1 id="title">Новая точка</h1><p id="editor-status" role="status">Проверяем вход…</p>
<p>Слова остаются словами, пока вы сами не выберете для них смысловую ссылку.
Связь не означает поддержку. Язык — свойство текста точки.</p>
<section id="my-points"><h2>Мои точки</h2><ul></ul>
<button id="more-mine" hidden>Ещё</button></section>
<form id="editor-form" hidden>
<label>Язык текста (ru, en, und…)<input id="point-lang" value="und" maxlength="35" required></label>
<label>Текст<textarea id="point-body" maxlength="8192" rows="14" required></textarea></label>
<button id="link-word" type="button">Связать выделенные слова / добавить связь</button>
<p>Для публикации выберите 1–16 связанных точек.</p><ul id="point-links"></ul>
<button id="publish" type="submit">Опубликовать</button></form>
<p><a id="open-point" hidden>Открыть точку</a></p>
<section id="history" hidden><h2>История опубликованных версий</h2><ol></ol>
<button id="more-history" type="button" hidden>Ещё версии</button></section>
<noscript>Для редактора нужен JavaScript.</noscript></main></body></html>"""


@router.get("/", response_class=HTMLResponse)
def editor(request: Request):
    page = PAGE
    bundle = getattr(request.app.state, "hosted_bundle", None)
    if bundle:
        for name in ("site.css", "point-picker.js"):
            version = sha256((bundle.directory / "assets" / name).read_bytes()).hexdigest()[:12]
            page = page.replace(f"/assets/{name}", f"/assets/{name}?v={version}")
    return HTMLResponse(page, headers=HEADERS)


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
body[data-page=editor] main{margin:1rem auto}
body[data-page=editor] pre{white-space:pre-wrap;overflow-wrap:anywhere}
body[data-page=editor] li,body[data-page=editor] summary{overflow-wrap:anywhere}
""",
        media_type="text/css",
        headers=HEADERS,
    )
