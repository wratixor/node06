"""First-party feed read; never available through the anonymous iframe bridge."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from .feed import CreationFeed
from .point_api import service
from .public_points import PublicPointError
from .site_api import manager

router = APIRouter(prefix="/api/v1/me")


@router.get("/feed")
def creation_feed(
    request: Request,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    before_day: date | None = None,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
):
    _, _, actor = manager(request, mutation=False)
    public = service(request, {"cursor", "before_day", "limit"})
    try:
        return CreationFeed(public).page(
            actor.user_id, cursor=cursor, before_day=before_day, limit=limit
        )
    except SQLAlchemyError as exc:
        raise PublicPointError("FEED_UNAVAILABLE", 503) from exc
