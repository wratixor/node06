"""Private profile preferences and explicit synchronization controls."""

import json
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from .auth import SESSION_COOKIE
from .auth_api import service
from .graph_writes import lock_graph
from .models import profile_preferences as prefs
from .point_api import service as public_service
from .profile_link_api import local, make, peer_form
from .profile_links import LinkID, Secret
from .profile_packet import PointID, Strict
from .profile_peer import unique_object
from .profile_preferences import Kind, put, reference, seed
from .profile_sync import Message, ProfileSync, SyncSettings
from .public_points import PublicPointError

router = APIRouter()


def sync_service(request, authorized=False):
    control, uid = local(request, mutation=authorized)
    public = public_service(request, set())
    return ProfileSync(
        public,
        control.origin,
        control.transport,
        control.authorize if authorized else None,
        request.app.state.settings.verifier_seconds,
    ), uid


@router.post("/api/v1/me/profile-links/{link_id}/sync-settings")
def settings(link_id: LinkID, payload: SyncSettings, request: Request):
    sync, uid = sync_service(request, True)
    return sync.settings(uid, link_id, payload)


@router.post("/api/v1/me/profile-links/{link_id}/sync")
def start_sync(link_id: LinkID, payload: dict, request: Request):
    if payload:
        raise PublicPointError("INVALID_INPUT", 422)
    sync, uid = sync_service(request, True)
    return sync.step(uid, link_id)


class Envelope(Strict):
    token: Secret
    packet: Annotated[str, Field(max_length=60000)]


def receive(request, envelope):
    service(request)._limit("profile-sync-peer-ip", request.client.host, 180, 60)
    control = make(request)
    try:
        parsed = json.loads(envelope.packet, object_pairs_hook=unique_object)
        payload = Message.model_validate(parsed)
    except (ValueError, RecursionError, ValidationError):
        raise PublicPointError("PROFILE_SYNC_INVALID", 422) from None
    sync = ProfileSync(public_service(request, set()), control.origin, control.transport)
    return sync.receive(envelope.token, payload)


@router.post("/api/v1/profile-links/sync")
async def peer_sync(request: Request):
    data = await peer_form(request, Envelope, 65536)
    return await run_in_threadpool(receive, request, data)


class Favorite(Strict):
    origin: Annotated[str, Field(max_length=512)]

    @field_validator("origin")
    @classmethod
    def origin_shape(cls, value):
        from .profile_packet import Source

        return Source.https_origin(value)

    point_id: PointID
    active: bool


@router.post("/api/v1/me/profile-sync/favorite")
def favorite(payload: Favorite, request: Request):
    sync, uid = sync_service(request, True)
    with sync.db.begin() as c:
        lock_graph(c)
        sync.actor(c, uid)
        seed(c, uid, sync.origin, sync.public)
        # A foreign reference is a bookmark, never a local point/import or reaction.
        present = (
            c.execute(
                select(prefs).where(
                    prefs.c.user_id == uid,
                    prefs.c.kind == "favorites",
                    prefs.c.origin == payload.origin,
                    prefs.c.point_id == payload.point_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if payload.active and (not present or present["deleted"]):
            count = c.scalar(
                select(func.count())
                .select_from(prefs)
                .where(
                    prefs.c.user_id == uid,
                    prefs.c.kind == "favorites",
                    prefs.c.origin == payload.origin,
                    prefs.c.deleted.is_(False),
                )
            )
            if count >= 64:
                raise PublicPointError("FAVORITES_LIMIT", 409)
        if (
            not present
            and c.scalar(select(func.count()).select_from(prefs).where(prefs.c.user_id == uid))
            >= 10000
        ):
            raise PublicPointError("PROFILE_SYNC_LIMIT", 413)
        put(
            c,
            uid,
            "favorites",
            payload.origin,
            payload.point_id,
            {},
            not payload.active,
            sync.origin,
        )
    return {"saved": True}


@router.get("/api/v1/me/profile-sync/preferences")
def preferences(
    request: Request,
    kind: Kind = "favorites",
    after_origin: Annotated[str, Query(max_length=512)] = "",
    after_point: Annotated[str, Query(max_length=96)] = "",
):
    # Bounded parameters; local() rejects query parameters on link operations.
    from .site_api import manager

    _registry, auth, actor = manager(request, mutation=False)
    auth._limit("profile-preferences-owner", actor.user_id, 600, 3600)
    if len(request.query_params.multi_items()) != len(request.query_params) or (
        bool(after_origin) != bool(after_point)
    ):
        raise PublicPointError("INVALID_PARAMS", 400)
    if set(request.query_params) - {"kind", "after_origin", "after_point"}:
        raise PublicPointError("INVALID_PARAMS", 400)
    public = public_service(request, {"kind", "after_origin", "after_point"})
    public.site_id = None
    origin = request.app.state.settings.management_origin
    from sqlalchemy import tuple_

    with public.database.begin() as c:
        lock_graph(c)
        auth.authorize_session(c, request.cookies.get(SESSION_COOKIE), actor.user_id)
        seed(c, actor.user_id, origin, public)
        query = select(prefs).where(
            prefs.c.user_id == actor.user_id, prefs.c.kind == kind, prefs.c.deleted.is_(False)
        )
        if after_origin:
            query = query.where(
                tuple_(prefs.c.origin, prefs.c.point_id) > (after_origin, after_point)
            )
        data = (
            c.execute(query.order_by(prefs.c.origin, prefs.c.point_id).limit(31)).mappings().all()
        )
    return {
        "items": [
            {
                "kind": r["kind"],
                "origin": r["origin"],
                "point_id": r["point_id"],
                "value": r["value"],
                "url": reference(r) if r["kind"] != "color" else None,
                "external": r["origin"] != origin,
                "writer_origin": r["writer_origin"],
            }
            for r in data[:30]
        ],
        "next_cursor": {"after_origin": data[29]["origin"], "after_point": data[29]["point_id"]}
        if len(data) > 30
        else None,
    }
