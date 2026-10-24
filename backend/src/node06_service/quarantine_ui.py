"""First-party private quarantine reader. No framing or public graph capability."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from .account_ui import HEADERS
from .personal_ui import navigation

router = APIRouter(prefix="/quarantine")


@router.get("/")
def page():
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Карантин</title>
<link rel="stylesheet" href="/moderation/style.css">
<script src="/quarantine/client.js" defer></script></head><body>"""
        + navigation("quarantine")
        + """<main><h1>Карантин</h1><p id="q-status" role="status"></p>
<p><a href="/account/">Вход и безопасность</a></p>
<ul id="q-bans"></ul><form id="q-form"><label>Область<select id="q-scope"></select></label>
<button>Открыть</button></form><ul id="q-points"></ul><button id="q-more" hidden>Ещё</button>
<article id="q-article" hidden><h2 id="q-author"></h2><pre id="q-body"></pre></article>
</main></body></html>""",
        headers=HEADERS,
    )


@router.get("/client.js")
def client():
    return Response(
        files("node06_service").joinpath("ui/quarantine.js").read_text(),
        media_type="text/javascript",
        headers=HEADERS,
    )
