"""Public author view and first-party T1 subscription/block controls."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from .account_ui import HEADERS
from .personal_ui import navigation
from .social_api import UserID

router = APIRouter()


@router.get("/people/{user_id}/", response_class=HTMLResponse)
def person_page(user_id: UserID):
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Профиль автора</title>
<link rel="stylesheet" href="/account/style.css">
<script src="/people/client.js" defer></script></head><body>"""
        + navigation("profile")
        + """<main><h1 id="author-name">Профиль автора</h1>
<p id="author-status" role="status">Загрузка…</p>
<div id="author-actions" hidden>
<button id="author-follow" type="button">Подписаться</button>
<button id="author-block" type="button">Заблокировать</button></div>
<p><a href="/account/" id="author-login" target="_blank" rel="noopener">Вход и регистрация</a></p>
<h2>Точки автора</h2><ul id="author-points"></ul>
<button id="author-more" type="button" hidden>Ещё</button>
<noscript>Для профиля нужен JavaScript.</noscript></main></body></html>""",
        headers=HEADERS,
    )


@router.get("/people/client.js")
def script():
    return Response(
        files("node06_service").joinpath("ui/people.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )
