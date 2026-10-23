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
· <a href="/account/" target="_blank" rel="noopener">Аккаунт</a>
· <a href="/sites/">Мои сайты</a> · <a href="/community/">Подписки</a></nav></header>
<main><h1 id="title">Новая точка</h1><p id="editor-status" role="status">Проверяем вход…</p>
<p id="related-context" hidden></p>
<p>Слова остаются словами, пока вы сами не выберете для них смысловую ссылку.
Связь не означает поддержку. Язык — свойство текста точки.</p>
<button id="retry-login" type="button" hidden>Продолжить после входа</button>

<form id="editor-form" hidden>
<label>Язык текста (ru, en, und…)<input id="point-lang" value="und" maxlength="35" required></label>
<label>Текст<textarea id="point-body" maxlength="8192" rows="14" required></textarea></label>
</form>
<section id="tag-tools" hidden><h2>Связанные точки / теги</h2>
<div id="tag-search"></div>
<button id="link-word" type="button">Связать выделенные слова / добавить связь</button>
<p>Найдите смысл, откройте результат и нажмите «Выбрать». Выделенное слово можно
превратить в ссылку. Для публикации нужны 1–16 связанных точек.</p>
<h3>Выбранные</h3><ul id="point-links"></ul>
<h3>Избранные теги</h3><p>Личный список для следующих публикаций. Это не подписка и не голос.</p>
<ul id="favorite-tags"></ul>
<button id="publish" type="submit" form="editor-form">Опубликовать</button></section>
<p><a id="open-point" hidden>Открыть точку</a></p>
<section id="history" hidden><h2>История опубликованных версий</h2><ol></ol>
<button id="more-history" type="button" hidden>Ещё версии</button></section>
<details><summary>Мои точки</summary><section id="my-points"><ul></ul>
<button id="more-mine" hidden>Ещё</button></section></details>
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
body[data-page=editor] main{margin:1rem auto;max-width:960px}
body[data-page=editor] #point-lang{max-width:160px}
body[data-page=editor] textarea{width:100%;min-height:280px;resize:vertical;font:inherit;
line-height:1.6}
body[data-page=editor] #tag-tools{border:1px solid var(--line);padding:16px;margin:20px 0}
body[data-page=editor] #tag-search .point-search{max-width:none;width:100%;margin:12px 0}
body[data-page=editor] #point-links,body[data-page=editor] #favorite-tags{list-style:none;padding:0}
body[data-page=editor] #point-links li,body[data-page=editor] #favorite-tags li{
display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 0;
border-bottom:1px solid var(--line)}
body[data-page=editor] #point-links a{flex:1 1 200px}
.point-create-related{display:inline-block;border:1px solid var(--line);padding:8px;margin:12px 0}

body[data-page=editor] button{max-width:100%;overflow-wrap:anywhere}
body[data-page=editor] pre{white-space:pre-wrap;overflow-wrap:anywhere}
body[data-page=editor] li,body[data-page=editor] summary{overflow-wrap:anywhere}
""",
        media_type="text/css",
        headers=HEADERS,
    )
