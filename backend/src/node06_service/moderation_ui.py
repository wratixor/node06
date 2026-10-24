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
<button>Открыть</button><select id="case-state" aria-label="Статус жалоб">
<option value="open">Открытые</option><option value="closed">Закрытые</option></select></form>
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
        CSS + "\n#scope-form{display:flex;gap:8px;flex-wrap:wrap;align-items:end}"
        "h2{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:50vh;overflow:auto}"
        "li{padding:8px 0;border-bottom:1px solid #293442;overflow-wrap:anywhere}"
        "#cases button{max-width:100%;white-space:normal;overflow-wrap:anywhere}"
        "#scope-form label{flex:1;min-width:0}"
        "details{margin-top:12px}#roles form{display:flex;gap:8px;flex-wrap:wrap}",
        media_type="text/css",
        headers=HEADERS,
    )
