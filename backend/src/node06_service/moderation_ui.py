"""Compact trusted report/review panel; all authority is checked by the API."""

from hashlib import sha256
from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS
from .personal_ui import navigation

router = APIRouter(prefix="/moderation")
PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>NODE06 — модерация</title>
<link rel="stylesheet" href="/moderation/style.css">
<script src="/moderation/client.js?v={version}" defer></script></head><body>
{navigation}<main><h1>Жалобы и модерация</h1><p id="status" role="status"></p>
<form id="scope-form"><label>Область<input id="scope" list="scopes" required
pattern="server|s_[0-9a-f]{{32}}" value="server"></label><datalist id="scopes"></datalist>
<label>Жалобы<select id="case-state">
<option value="open">Открытые</option><option value="closed">Закрытые</option></select></label>
<button>Открыть</button></form>
<form id="report-form" hidden><h2>Пожаловаться на точку</h2>
<label>Точка<input id="report-point" readonly></label>
<label>Причина<textarea id="report-reason" required maxlength="2000" rows="2"></textarea></label>
<button>Отправить жалобу</button></form>
<section id="review" hidden><h2>Жалобы</h2><ul id="cases"></ul><button id="more" hidden>Ещё</button>
<article id="detail" hidden><h2 id="point-name"></h2><pre id="point-body"></pre>
<ul id="reports"></ul><p id="report-more" hidden>Показаны первые 30 жалоб.</p>
<form id="visibility-form"><label>Причина решения
<input id="decision-reason" required maxlength="2000"></label>
<button id="hide-point" type="button">Скрыть</button>
<button id="restore-point" type="button">Восстановить</button>
<button id="close-case" type="button">Закрыть жалобу</button></form>
<p id="hidden-since"></p><details><summary>Последние 20 решений</summary>
<ul id="audit"></ul></details>
</article></section>
<section id="user-search" hidden><h2>Пользователи</h2>
<form id="user-search-form"><label class="search-field">Имя пользователя
<input id="user-query" type="search" maxlength="64" placeholder="Поиск"></label>
<button>Найти</button></form>
<ul id="user-results"></ul><button id="users-more" hidden>Ещё</button></section>
<details id="roles" hidden><summary>Доступ к области</summary>
<form id="role-form"><label>ID пользователя
<input id="role-user" required pattern="u_[0-9a-f]{{32}}"></label>
<label>Роль<select id="role"><option value="moderator">Модератор</option>
<option value="admin">Администратор</option>
<option value="">Отозвать назначение</option></select></label><button>Применить</button></form>
<p>Владелец активного сайта сохраняет права администратора своего сайта.</p></details>
</main></body></html>"""


@router.get("/")
def page():
    version = sha256(files("node06_service").joinpath("ui/moderation.js").read_bytes()).hexdigest()[
        :12
    ]
    return HTMLResponse(
        PAGE.format(version=version, navigation=navigation("moderation")), headers=HEADERS
    )


@router.get("/client.js")
def client():
    return Response(
        files("node06_service").joinpath("ui/moderation.js").read_text(),
        media_type="text/javascript",
        headers=HEADERS,
    )


@router.get("/style.css")
def style():
    return Response(
        CSS
        + "\n#scope-form{display:grid;grid-template-columns:minmax(0,1fr) minmax(130px,.6fr) auto;"
        "gap:8px;align-items:end}"
        "#scope-form label,#scope-form button,#user-search-form label,"
        "#user-search-form button{margin:0}"
        "#scope-form input,#scope-form select,#scope-form button{min-height:46px}"
        "#user-search-form{display:flex;gap:8px;align-items:end}"
        "#user-search-form label{flex:1;min-width:0}"
        "#user-results small{display:block;color:#8292a2}"
        "#user-results a{color:inherit}#user-results button{margin-left:8px}"
        "@media(max-width:520px){#scope-form{grid-template-columns:minmax(0,1fr) auto}"
        "#scope-form label:first-child{grid-column:1/-1}}"
        "h2{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:50vh;overflow:auto}"
        "li{padding:8px 0;border-bottom:1px solid #293442;overflow-wrap:anywhere}"
        "#cases button{max-width:100%;white-space:normal;overflow-wrap:anywhere}"
        "#scope-form label{flex:1;min-width:0}"
        "details{margin-top:12px}#roles form{display:grid;gap:8px;align-items:end;"
        "grid-template-columns:minmax(0,1fr) minmax(150px,.7fr) auto}"
        "#roles label,#roles button{margin:0}"
        "#roles input,#roles select,#roles button{min-height:46px}"
        "@media(max-width:520px){#roles form{grid-template-columns:minmax(0,1fr)} }",
        media_type="text/css",
        headers=HEADERS,
    )
