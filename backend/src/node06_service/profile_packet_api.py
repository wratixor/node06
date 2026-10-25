"""First-party private export/compare; no import, linking or remote requests."""

from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .account_ui import HEADERS
from .personal_ui import navigation
from .point_api import service
from .profile_packet import Packet, compare, snapshot
from .public_points import PublicPointError
from .site_api import manager

router = APIRouter()


def own(request, *, mutation=False):
    if request.query_params:
        raise PublicPointError("INVALID_PARAMS", 400)
    _, auth, actor = manager(request, mutation=mutation)
    auth._limit("profile-packet-owner", actor.user_id, 60, 3600)
    public = service(request, set())
    public.site_id = None
    return snapshot(public, actor.user_id, request.app.state.settings.management_origin)


@router.get("/api/v1/me/profile-export")
def export_profile(request: Request):
    return own(request).model_dump()


@router.post("/api/v1/me/profile-compare")
def compare_profile(payload: Packet, request: Request):
    return compare(own(request, mutation=True), payload)


@router.get("/profile-sync/", response_class=HTMLResponse)
def page():
    return HTMLResponse(
        """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Перенос профиля</title>
<link rel="stylesheet" href="/account/style.css">
<link rel="stylesheet" href="/profile-sync/style.css">
<script src="/profile-sync/client.js" defer></script></head><body>"""
        + navigation("profile-sync")
        + """<main><h1>Перенос профиля</h1>
<p id="packet-status" role="status">Проверяем вход…</p>
<p>Файл содержит личные списки. Сравнение ничего не записывает и не связывает аккаунты.</p>
<button id="packet-download" type="button" disabled>Скачать профиль</button>
<form id="packet-form">
<label>Профиль из файла
<input id="packet-file" type="file" accept="application/json,.json" required></label>
<button id="packet-compare" type="submit" disabled>Сравнить</button></form>
<section id="packet-result" hidden><h2>Сравнение</h2><p id="packet-source"></p>
<p>Источник указан в файле; владение аккаунтом не подтверждено. Изменения не применены.</p>
<p id="packet-color"></p><div id="packet-differences"></div></section>
<p><a href="/account/">Вход и безопасность</a></p>
<noscript>Для экспорта и сравнения нужен JavaScript.</noscript></main></body></html>""",
        headers=HEADERS,
    )


@router.get("/profile-sync/client.js")
def script():
    return Response(
        files("node06_service").joinpath("ui/profile-packet.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.get("/profile-sync/style.css")
def style():
    return Response(
        "#packet-source{overflow-wrap:anywhere}#packet-result details{margin:12px 0}"
        "#packet-result summary{cursor:pointer}#packet-result li{overflow-wrap:anywhere}",
        media_type="text/css",
        headers=HEADERS,
    )
