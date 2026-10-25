"""First-party consent endpoints and cookie-independent link-control exchanges."""

from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .auth import SESSION_COOKIE
from .auth_api import configured_origin, service
from .profile_links import Confirmation, Invitation, LinkID, Metadata, Peer, ProfileLinks, Secret
from .profile_packet import Strict
from .profile_peer import exchange
from .public_points import PublicPointError
from .site_api import manager

router = APIRouter()


class Approval(Strict):
    invitation: Invitation
    expected: Metadata


class Empty(Strict):
    pass


def local(request, mutation=True):
    if request.query_params:
        raise PublicPointError("INVALID_PARAMS", 400)
    _, auth, actor = manager(request, mutation=mutation)
    auth._limit("profile-link-owner", actor.user_id, 120, 3600)
    return make(
        request,
        authorize=lambda c, uid: auth.authorize_session(
            c, request.cookies.get(SESSION_COOKIE), uid
        ),
    ), actor.user_id


def make(request, authorize=None):
    db, settings = request.app.state.database, request.app.state.settings
    # Test injection is app-local, never an environment/URL-controlled SSRF bypass.
    transport = getattr(request.app.state, "profile_link_transport", None)
    if transport is None:

        def transport(origin, op, fields):
            return exchange(db, settings, origin, op, fields)

    return ProfileLinks(db, configured_origin(request), transport, authorize)


@router.get("/api/v1/me/profile-links")
def listing(request: Request):
    if request.query_params:
        raise PublicPointError("INVALID_PARAMS", 400)
    links, uid = local(request, False)
    return links.list(uid)


@router.post("/api/v1/me/profile-links/invite")
def invite(payload: Peer, request: Request):
    links, uid = local(request)
    return links.invite(uid, payload.origin)


@router.post("/api/v1/me/profile-links/inspect")
def inspect(payload: Invitation, request: Request):
    links, _ = local(request)
    return links.inspect(payload).model_dump()


@router.post("/api/v1/me/profile-links/approve")
def approve(payload: Approval, request: Request):
    links, uid = local(request)
    return links.approve(uid, payload.invitation, payload.expected)


@router.post("/api/v1/me/profile-links/confirm")
def confirm(payload: Confirmation, request: Request):
    links, uid = local(request)
    return links.confirm(uid, payload)


@router.post("/api/v1/me/profile-links/{link_id}/revoke")
def revoke(link_id: LinkID, payload: Empty, request: Request):
    links, uid = local(request)
    return links.revoke(uid, link_id)


@router.post("/api/v1/me/profile-links/{link_id}/refresh")
def refresh(link_id: LinkID, payload: Empty, request: Request):
    links, uid = local(request)
    return links.refresh(uid, link_id)


class Info(Strict):
    secret: Secret
    client_id: str


class Code(Strict):
    grant_type: str
    code: Secret
    code_verifier: Secret
    client_id: str
    redirect_uri: str


class Control(Strict):
    token: Secret


async def peer_form(request, schema):
    configured_origin(request)
    # Peer endpoints never use/accept browser session cookies as authorization.
    if request.headers.get("origin") is not None or request.cookies:
        raise PublicPointError("PROFILE_PEER_ONLY", 403)
    if (
        request.query_params
        or request.headers.get("content-type", "").split(";", 1)[0]
        != "application/x-www-form-urlencoded"
    ):
        raise PublicPointError("PROFILE_FORM_REQUIRED", 415)
    raw = await request.body()
    if len(raw) > 4096:
        raise PublicPointError("PROFILE_FORM_TOO_LARGE", 413)
    try:
        pairs = parse_qsl(raw.decode("ascii"), strict_parsing=True, max_num_fields=8)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError("Duplicate form fields")
        return schema.model_validate(data)
    except (ValueError, UnicodeError, ValidationError):
        raise PublicPointError("PROFILE_FORM_INVALID", 400) from None


def peer_admit(request):
    service(request)._limit("profile-link-peer-ip", request.client.host, 60, 60)
    return make(request)


@router.post("/api/v1/profile-links/metadata")
async def metadata(request: Request):
    data = await peer_form(request, Info)
    return await run_in_threadpool(
        lambda: peer_admit(request).metadata(data.secret, data.client_id)
    )


@router.post("/api/v1/profile-links/token")
async def token(request: Request):
    data = await peer_form(request, Code)
    if data.grant_type != "authorization_code":
        raise PublicPointError("PROFILE_GRANT_INVALID", 400)
    return await run_in_threadpool(
        lambda: peer_admit(request).redeem(
            data.code, data.code_verifier, data.client_id, data.redirect_uri
        )
    )


@router.post("/api/v1/profile-links/status")
async def status(request: Request):
    data = await peer_form(request, Control)
    return await run_in_threadpool(lambda: peer_admit(request).token_status(data.token))


@router.post("/api/v1/profile-links/revoke")
async def peer_revoke(request: Request):
    data = await peer_form(request, Control)
    return await run_in_threadpool(lambda: peer_admit(request).token_status(data.token, True))
