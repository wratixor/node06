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
<script src="/profile-sync/client.js" defer></script>
<script src="/profile-sync/links.js" defer></script></head><body>"""
        + navigation("profile-sync")
        + """<main><h1>Связанные аккаунты</h1>
<p id="links-status" role="status">Проверяем вход…</p>
<p>Подтвердите пару на обоих серверах. Связь действует 30 дней; её можно отозвать.
Выберите данные для автоматического обмена.
Подписки и свои посты с другого сервера — ссылки на оригиналы; местное влияние не переносится.</p>
<form id="links-create"><label>Другой сервер
<input id="links-origin" type="url" placeholder="https://wiki.example" required></label>
<div id="links-scopes"></div>
<button type="submit" disabled>Пригласить</button></form>
<form id="links-import"><label>Приглашение или ответ
<input id="links-input" type="text" maxlength="4096" autocomplete="off" required></label>
<button type="submit" disabled>Проверить</button></form>
<section id="links-preview" hidden><p id="links-pair"></p><p id="links-permissions"></p>
<button id="links-confirm" type="button">Подтвердить пару</button></section>
<section id="links-output" hidden><label>Откройте ссылку на другом сервере в своём аккаунте
<input id="links-url" type="text" readonly></label>
<a id="links-go" referrerpolicy="no-referrer" rel="noreferrer">Перейти</a></section>
<ul id="links-list"></ul><button id="links-reload" type="button" disabled>Обновить список</button>
<section id="sync-preferences"><h2>Данные профиля</h2>
<label>Показать<select id="sync-kind"><option value="favorites">Избранное</option>
<option value="subscriptions">Подписки на точки</option>
<option value="own_points">Свои посты</option></select></label>
<p>На других серверах открывается оригинал. Подписка здесь не создаёт там голос или поддержку.</p>
<ul id="sync-items"></ul><button id="sync-more" type="button" hidden>Ещё</button></section>
<details><summary>Файл профиля: экспорт и сравнение</summary>
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
</details><noscript>Для связывания, экспорта и сравнения нужен JavaScript.</noscript>
</main></body></html>""",
        headers={**HEADERS, "Referrer-Policy": "no-referrer"},
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
        "#packet-result summary{cursor:pointer}#packet-result li{overflow-wrap:anywhere}"
        "#links-list p,#links-pair,#sync-items{overflow-wrap:anywhere}"
        "#links-list button{margin:4px}#links-scopes{display:flex;gap:16px;flex-wrap:wrap}"
        "#links-scopes label,.sync-options label{display:block;margin:6px 0}"
        "#links-scopes input,.sync-options input{display:inline-block;width:auto;margin-right:6px}"
        "#links-scopes fieldset,.sync-options fieldset{min-width:0;flex:1 1 200px}"
        "#links-list>li{border-bottom:1px solid #293644;padding:10px 0}",
        media_type="text/css",
        headers=HEADERS,
    )


@router.get("/profile-sync/links.js")
def links_script():
    return Response(
        files("node06_service").joinpath("ui/profile-links.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )
