"""Public users and influence directory on the management origin."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from .account_ui import CSS, HEADERS
from .personal_ui import navigation

router = APIRouter(prefix="/directory")


@router.get("/")
def page():
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Пользователи и рейтинги</title>
<link rel="stylesheet" href="/directory/style.css">
<script src="/directory/client.js" defer></script></head><body>"""
        + navigation("directory")
        + """<main><h1>Пользователи и рейтинги</h1>
<form id="directory-form"><label>Показать<select id="directory-kind">
<option value="search">Поиск пользователей</option>
<option value="users">Рейтинг пользователей</option>
<option value="points">Рейтинг поддерживаемых точек</option></select></label>
<label id="directory-query-label">Имя пользователя<input id="directory-query" type="search"
maxlength="64" placeholder="Поиск"></label>
<button>Показать</button></form><p id="directory-status" role="status"></p>
<ol id="directory-results"></ol><button id="directory-more" hidden>Ещё</button>
<p>Рейтинг пользователей — влияние T1. Рейтинг точек — подтверждённая поддержка текущей версии.</p>
</main></body></html>""",
        headers=HEADERS,
    )


@router.get("/client.js")
def client():
    return Response(
        files("node06_service").joinpath("ui/directory.js").read_text(),
        media_type="text/javascript",
        headers=HEADERS,
    )


@router.get("/style.css")
def style():
    return Response(
        CSS + "#directory-results{padding-left:24px}"
        "#directory-results li{padding:10px 0;border-bottom:1px solid #293442;"
        "overflow-wrap:anywhere}"
        "#directory-results a{color:inherit}"
        "#directory-results span{color:#8292a2;white-space:nowrap}",
        media_type="text/css",
        headers=HEADERS,
    )
