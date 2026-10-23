"""Same-origin authenticated publication; deliberately absent from public bridge."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select, tuple_

from .auth_api import authenticated_mutation
from .authoring import Authoring, AuthoringError
from .models import authored_points, authored_revisions, point_revisions, points
from .point_api import service as public_service
from .public_points import PublicPointError, preview
from .site_api import manager

router = APIRouter(prefix="/api/v1")
PointID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9_-]{0,95}$")]
RevisionID = Annotated[str, StringConstraints(strict=True, pattern=r"^v_[0-9a-f]{32}$")]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PointID
    revision_id: RevisionID | None
    content_digest: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=8192)]
    lang: Annotated[
        str,
        StringConstraints(
            strict=True, pattern=r"^[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*$|^und$", max_length=35
        ),
    ] = "und"
    links: Annotated[list[Citation], Field(min_length=1, max_length=16)]


class EditContent(Content):
    expected_revision_id: RevisionID


def write(request, payload, point_id=None):
    public = public_service(request, set())
    auth, token = authenticated_mutation(request)
    actor = auth.authenticate(token)
    key = request.headers.get("Idempotency-Key", "")
    if not 8 <= len(key) <= 80 or not all(c.isascii() and (c.isalnum() or c in "-_") for c in key):
        raise AuthoringError("IDEMPOTENCY_KEY_REQUIRED")
    auth._limit("point-write-owner", actor.user_id, 120, 3600)
    auth._limit("point-write-ip", request.client.host, 240, 3600)
    return Authoring(public, lambda c, uid: auth.authorize_session(c, token, uid)).save(
        actor.user_id,
        key,
        payload.model_dump(),
        point_id,
    )


@router.post("/points", status_code=201)
def create(payload: Content, request: Request):
    return write(request, payload)


@router.patch("/points/{point_id}")
def edit(point_id: PointID, payload: EditContent, request: Request):
    return write(request, payload, point_id)


@router.get("/points/{point_id}/revisions")
def history(
    point_id: PointID,
    request: Request,
    response: Response,
    before: RevisionID | None = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
):
    from .hosted import PUBLIC_HEADERS

    response.headers.update(PUBLIC_HEADERS)
    public = public_service(request, {"before", "limit"})
    public._raw(point_id)
    # Only the explicit publication registry authorizes public history. Never site drafts.
    with public.database.connect() as c:
        if not c.execute(
            select(authored_points.c.point_id).where(authored_points.c.point_id == point_id)
        ).scalar_one_or_none():
            raise PublicPointError("POINT_NOT_FOUND")
        query = (
            select(
                point_revisions.c.id.label("revision_id"),
                point_revisions.c.body,
                point_revisions.c.declared_links,
                point_revisions.c.editor_user_id,
                point_revisions.c.created_at,
                authored_revisions.c.lang,
                authored_revisions.c.citations,
            )
            .join(authored_revisions, authored_revisions.c.revision_id == point_revisions.c.id)
            .where(point_revisions.c.point_id == point_id)
        )
        # Random UUIDs are not time cursors: use the exact persisted (time,id) pair.
        if before:
            cursor = c.execute(
                select(point_revisions.c.created_at).where(
                    point_revisions.c.point_id == point_id,
                    point_revisions.c.id == before,
                )
            ).scalar_one_or_none()
            if cursor is None:
                raise AuthoringError("INVALID_HISTORY_CURSOR", 400)
            query = query.where(
                tuple_(point_revisions.c.created_at, point_revisions.c.id) < (cursor, before)
            )
        rows = (
            c.execute(
                query.order_by(
                    point_revisions.c.created_at.desc(), point_revisions.c.id.desc()
                ).limit(limit + 1)
            )
            .mappings()
            .all()
        )
    return {
        "items": [
            {
                **dict(row),
                "citations": [
                    {k: v for k, v in pin.items() if k != "static_body"} for pin in row["citations"]
                ],
            }
            for row in rows[:limit]
        ],
        "next_cursor": rows[limit - 1]["revision_id"] if len(rows) > limit else None,
    }


@router.get("/me/points")
def own_points(
    request: Request, after: PointID | None = None, limit: Annotated[int, Query(ge=1, le=30)] = 20
):
    _registry, _auth, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        query = (
            select(points.c.id, points.c.current_revision_id, point_revisions.c.body)
            .join(authored_points, authored_points.c.point_id == points.c.id)
            .join(point_revisions, points.c.current_revision_id == point_revisions.c.id)
            .where(
                points.c.author_user_id == actor.user_id,
                points.c.lifecycle == "active",
            )
        )
        if after:
            query = query.where(points.c.id.collate("C") > after)
        rows = c.execute(query.order_by(points.c.id.collate("C")).limit(limit + 1)).mappings().all()
    return {
        "items": [
            {
                "id": row["id"],
                "revision_id": row["current_revision_id"],
                "preview": preview(row["body"]),
            }
            for row in rows[:limit]
        ],
        "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
    }
