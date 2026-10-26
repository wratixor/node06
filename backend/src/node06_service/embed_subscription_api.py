"""Private subscription grants have a separate, bounded transport from public reads."""

from html import escape
from importlib.resources import files
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import AfterValidator, Field, StringConstraints
from sqlalchemy import select, update

from . import embed_subscriptions as service
from .account_ui import HEADERS
from .auth import SESSION_COOKIE, digest
from .auth_api import service as auth_service
from .hosted import request_origin
from .models import embed_subscriptions as grants
from .profile_links import Secret
from .profile_packet import PointID, Source, Strict
from .public_points import PublicPointError, PublicPoints
from .site_api import SiteID, manager
from .social_api import Subscription

router = APIRouter()
COOKIE = "node06_subscriptions"
RequestID = Annotated[str, StringConstraints(pattern=r"^e_[0-9a-f]{32}$")]
Nonce = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
ParentOrigin = Annotated[str, Field(max_length=512), AfterValidator(Source.https_origin)]


class Prepare(Strict):
    parent_origin: ParentOrigin
    challenge: Secret
    state: Nonce


class Completion(Strict):
    id: RequestID
    parent_origin: ParentOrigin
    verifier: Secret
    state: Nonce


class Redeem(Completion):
    code: Secret


class Operation(Strict):
    parent_origin: ParentOrigin
    point_id: PointID


class Mutation(Operation):
    subscription: Subscription
    key: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,80}$")]


class Empty(Strict):
    pass


def peer(request):
    settings = request.app.state.settings
    if request_origin(request) != settings.embed_origin:
        raise PublicPointError("EMBED_ORIGIN_REQUIRED", 404)
    if (
        set(request.cookies) - {COOKIE}
        or request.query_params
        or request.headers.get("origin")
        not in (
            None,
            settings.embed_origin,
        )
    ):
        raise PublicPointError("EMBED_PEER_REQUIRED", 403)
    if request.cookies and request.headers.get("origin") != settings.embed_origin:
        raise PublicPointError("EMBED_PEER_REQUIRED", 403)
    auth_service(request)._limit("subscription-peer-ip", request.client.host, 240, 60)
    return request.app.state.database, settings


@router.post("/bridge/v1/{site_id}/subscriptions/prepare")
def prepare(site_id: SiteID, payload: Prepare, request: Request):
    db, _ = peer(request)
    auth_service(request)._limit("subscription-prepare-ip", request.client.host, 30, 60)
    return service.prepare(db, site_id, payload)


@router.post("/bridge/v1/{site_id}/subscriptions/redeem")
def redeem(site_id: SiteID, payload: Redeem, request: Request, response: Response):
    db, settings = peer(request)
    result = service.redeem(db, site_id, payload, settings.management_origin)
    persist(response, result, site_id)
    return result


def persist(response, result, site_id):
    # Optional partitioned persistence; denied third-party storage still uses the
    # iframe's in-memory token. Never reuse the management session cookie.
    from datetime import datetime

    ttl = max(
        0, int((datetime.fromisoformat(result["expires_at"]) - service.now()).total_seconds())
    )
    response.set_cookie(
        COOKIE,
        result["token"],
        max_age=ttl,
        secure=True,
        httponly=True,
        samesite="none",
        path=f"/bridge/v1/{site_id}/subscriptions/",
    )
    response.headers["set-cookie"] += "; Partitioned"


@router.post("/bridge/v1/{site_id}/subscriptions/complete")
def complete(site_id: SiteID, payload: Completion, request: Request, response: Response):
    db, settings = peer(request)
    result = service.complete(db, site_id, payload, settings.management_origin)
    if result["connected"]:
        persist(response, result, site_id)
    return result


def grant(request, sid, parent):
    db, settings = peer(request)
    authorization = request.headers.get("authorization", "")
    if not authorization and request.cookies.get(COOKIE):
        authorization = "Bearer " + request.cookies[COOKIE]
    try:
        token = authorization.removeprefix("Bearer ")
        if authorization != "Bearer " + token or len(token) != 43:
            service.fail()
        row = service.lookup(db, sid, token, parent)
    except (UnicodeError, ValueError):
        service.fail()
    auth_service(request)._limit("subscription-grant-user", row["user_id"], 240, 60)
    bundle = getattr(request.app.state, "hosted_bundle", None)
    public = PublicPoints(
        db,
        roots=bundle.roots if bundle else (),
        build_revision=settings.build_revision,
        site_id=sid,
    )
    return row, public, settings.management_origin


@router.post("/bridge/v1/{site_id}/subscriptions/read")
def read(site_id: SiteID, payload: Operation, request: Request):
    row, public, origin = grant(request, site_id, payload.parent_origin)
    return service.read(public, row, origin, payload.point_id)


@router.post("/bridge/v1/{site_id}/subscriptions/set")
def mutate(site_id: SiteID, payload: Mutation, request: Request):
    row, public, origin = grant(request, site_id, payload.parent_origin)
    auth = auth_service(request)
    auth._limit("social-owner", row["user_id"], 240, 3600)
    auth._limit("social-ip", request.client.host, 480, 3600)
    return service.mutate(public, row, origin, payload.point_id, payload.subscription, payload.key)


def own(request, rid, mutation=False):
    if request.query_params:
        raise PublicPointError("INVALID_PARAMS", 400)
    _, auth, actor = manager(request, mutation=mutation)
    auth._limit("subscription-owner", actor.user_id, 120, 3600)
    db = request.app.state.database
    with db.connect() as c:
        row = c.execute(select(grants).where(grants.c.id == rid)).mappings().one_or_none()
    if (
        not row
        or row["revoked"]
        or (
            row["pending_until"] <= service.now()
            and (not row["approved_until"] or row["approved_until"] <= service.now())
        )
    ):
        raise PublicPointError("SUBSCRIPTION_REQUEST_EXPIRED", 409)
    return db, auth, actor, row


@router.get("/embed-subscriptions/{rid}/info")
def info(rid: RequestID, request: Request):
    db, _, actor, row = own(request, rid)
    with db.connect() as c:
        reusable = service.reusable(c, row, actor.user_id, digest(request.cookies[SESSION_COOKIE]))
    return {"handle": actor.handle, "can_resume": bool(reusable)}


@router.post("/embed-subscriptions/{rid}/{action}")
def approve(rid: RequestID, action: str, payload: Empty, request: Request):
    if action not in ("approve", "resume", "revoke"):
        raise PublicPointError("INVALID_PARAMS", 400)
    db, auth, actor, row = own(request, rid, True)
    token = request.cookies[SESSION_COOKIE]
    if action == "revoke":
        with db.begin() as c:
            auth.authorize_session(c, token, actor.user_id)
            c.execute(
                update(grants)
                .where(
                    grants.c.user_id == actor.user_id,
                    grants.c.site_id == row["site_id"],
                    grants.c.parent_origin == row["parent_origin"],
                )
                .values(revoked=True)
            )
        return {"revoked": True}
    return service.approve(
        db,
        rid,
        actor.user_id,
        token,
        lambda c, uid: auth.authorize_session(c, token, uid),
        resume=action == "resume",
    )


@router.get("/embed-subscriptions/{rid}/", response_class=HTMLResponse)
def page(rid: RequestID, request: Request):
    with request.app.state.database.connect() as c:
        row = c.execute(select(grants).where(grants.c.id == rid)).mappings().one_or_none()
    if not row or row["pending_until"] <= service.now():
        raise PublicPointError("SUBSCRIPTION_REQUEST_EXPIRED", 409)
    parent = Source.https_origin(row["parent_origin"])
    return HTMLResponse(
        '''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Общий аккаунт сервера</title>
<link rel="stylesheet" href="/account/style.css">
<script src="/subscription-access.js" defer></script></head><body data-request="'''
        + rid
        + '" data-parent="'
        + escape(parent, quote=True)
        + '" data-state="'
        + row["state"]
        + """"><main><h1>Подключить общий аккаунт</h1>
<p>Используется тот же аккаунт сервера, что и на вики.
Повторная регистрация не нужна.</p><p>Сайт <strong>"""
        + escape(parent)
        + """</strong> сможет показывать и переключать ваши подписки на точки
в течение 15 минут. Пароль и доступ к профилю сайту не передаются.</p>
<p id="access-status" role="status">Проверяем вход…</p>
<p><a id="access-login" href="/account/" target="_blank" rel="noopener">Войти в аккаунт</a></p>
<button id="access-check" type="button">Продолжить после входа</button>
<button id="access-allow" type="button" disabled>Разрешить подписки</button>
<button id="access-revoke" type="button" disabled>Отключить доступ этого сайта</button>
</main></body></html>""",
        headers={**HEADERS, "Referrer-Policy": "no-referrer"},
    )


@router.get("/subscription-access.js")
def script():
    return Response(
        files("node06_service").joinpath("ui/subscription-access.js").read_text(),
        media_type="application/javascript",
        headers=HEADERS,
    )


@router.post("/api/v1/me/embed-subscriptions/revoke")
def revoke_all(payload: Empty, request: Request):
    _, auth, actor = manager(request, mutation=True)
    with request.app.state.database.begin() as c:
        auth.authorize_session(c, request.cookies[SESSION_COOKIE], actor.user_id)
        c.execute(update(grants).where(grants.c.user_id == actor.user_id).values(revoked=True))
    return {"revoked": True}
