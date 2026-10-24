"""Authenticated quarantine text, separate from public graph/bridge/search."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from .author_api import PointID
from .bans import areas, live, require_review
from .models import moderation_bans as bans
from .models import points
from .moderation_api import Scope
from .point_api import service
from .public_points import PublicPointError, PublicPoints
from .site_api import manager

router = APIRouter(prefix="/api/v1/me/quarantine")
Cursor = Annotated[str, Query(pattern=r"^(?:p_[0-9a-f]{32})?$")]


@router.get("")
def listing(request: Request, scope: Scope = "server", after: Cursor = ""):
    public = service(request, {"scope", "after"})
    _, _, actor = manager(request, mutation=False)
    with public.database.connect() as c:
        require_review(c, actor.user_id, scope)
        query = (
            select(points.c.id, points.c.id.collate("C").label("sort_id"))
            .join(bans, bans.c.user_id == points.c.author_user_id)
            .where(
                points.c.origin == "user",
                points.c.lifecycle == "active",
                live(),
                bans.c.scope.in_(areas(None if scope == "server" else scope)),
                bans.c.mode == "quarantine",
                points.c.content_updated_at >= bans.c.starts_at,
                points.c.id.collate("C") > after,
            )
            .distinct()
            .order_by(points.c.id.collate("C"))
            .limit(21)
        )
        # Bounded scan; a local role never grants private server quarantine access.
        ids = list(c.scalars(query))
        items = []
        for pid in ids[:20]:
            try:
                require_review(c, actor.user_id, scope, pid)
                point = PublicPoints(public.database, moderation=False).raw_on(c, pid)
            except PublicPointError as exc:
                if exc.status in (403, 404):
                    continue
                raise
            items.append({"id": pid, "preview": point["preview"], "author": point.get("author")})
    return {"items": items, "next_cursor": ids[19] if len(ids) > 20 else None}


@router.get("/{point_id}")
def read(point_id: PointID, request: Request, scope: Scope = "server"):
    public = service(request, {"scope"})
    _, _, actor = manager(request, mutation=False)
    with public.database.connect() as c:
        require_review(c, actor.user_id, scope, point_id)
        point = PublicPoints(public.database, moderation=False).raw_on(c, point_id)
        return {"id": point["id"], "body": point["body"], "author": point.get("author")}


# Registered on a separate router to avoid /quarantine/{point_id} ambiguity.
account_router = APIRouter(prefix="/api/v1/me")


@account_router.get("/bans")
def own_bans(request: Request):
    _, _, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        rows = (
            c.execute(
                select(bans).where(live(), bans.c.user_id == actor.user_id).order_by(bans.c.scope)
            )
            .mappings()
            .all()
        )
    return {
        "items": [
            {k: r[k] for k in ("scope", "mode", "starts_at", "expires_at", "reason")} for r in rows
        ]
    }
