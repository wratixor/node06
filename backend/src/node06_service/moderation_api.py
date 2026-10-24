"""First-party moderation and reports. No management surface on the embed host."""

import html
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from .auth_api import authenticated_mutation
from .author_api import PointID
from .models import (
    moderation_audit,
    moderation_cases,
    moderation_reports,
    moderation_roles,
    point_hides,
    sites,
)
from .moderation import Moderation, ModerationError, require
from .point_api import service
from .public_points import PublicPointError, PublicPoints
from .site_api import manager

router = APIRouter(prefix="/api/v1/moderation")
Scope = Annotated[str, Query(pattern=r"^(server|s_[0-9a-f]{32})$")]


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Reason required")
        return value


class Visibility(Report):
    hidden: bool = Field(strict=True)


class Role(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "moderator"] | None


def mutate(request, scope, action, target, payload):
    public = service(request, {"scope"})
    auth, token = authenticated_mutation(request)
    actor = auth.authenticate(token)
    key = request.headers.get("Idempotency-Key", "")
    if not 8 <= len(key) <= 80 or not all(
        ch.isascii() and (ch.isalnum() or ch in "-_") for ch in key
    ):
        raise ModerationError("IDEMPOTENCY_KEY_REQUIRED", 422)
    auth._limit("moderation-user", actor.user_id, 120, 3600)
    auth._limit("moderation-ip", request.client.host, 240, 3600)
    return Moderation(public, lambda c, uid: auth.authorize_session(c, token, uid)).mutate(
        actor.user_id,
        key,
        scope,
        action,
        target,
        payload,
    )


@router.post("/reports/{point_id}")
def report(point_id: PointID, payload: Report, request: Request, scope: Scope = "server"):
    return mutate(request, scope, "report", point_id, payload.model_dump())


@router.post("/visibility/{point_id}")
def visibility(point_id: PointID, payload: Visibility, request: Request, scope: Scope = "server"):
    return mutate(request, scope, "visibility", point_id, payload.model_dump())


@router.post("/cases/{point_id}/close")
def close(point_id: PointID, request: Request, scope: Scope = "server"):
    return mutate(request, scope, "close", point_id, {})


@router.post("/roles/{user_id}")
def role(user_id: str, payload: Role, request: Request, scope: Scope = "server"):
    if not re.fullmatch(r"u_[0-9a-f]{32}", user_id):
        raise ModerationError("INVALID_USER", 422)
    return mutate(request, scope, "role", user_id, payload.model_dump())


@router.get("/scopes")
def scopes(request: Request):
    _, _, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        own = c.execute(
            select(sites.c.id, sites.c.display_name).where(
                sites.c.owner_user_id == actor.user_id,
                sites.c.state == "active",
            )
        ).all()
        grants = (
            c.execute(select(moderation_roles).where(moderation_roles.c.user_id == actor.user_id))
            .mappings()
            .all()
        )
        result = {}
        for row in grants:
            result[row["scope"]] = {
                "scope": row["scope"],
                "role": row["role"],
                "name": row["scope"],
            }
        for sid, name in own:
            result[sid] = {"scope": sid, "role": "admin", "name": name or sid}
    return {"items": list(result.values())}


@router.get("/cases")
def cases(
    request: Request,
    scope: Scope = "server",
    after: Annotated[str, Query(max_length=96, pattern=r"^(?:[a-z0-9][a-z0-9_-]{0,95})?$")] = "",
    status: Literal["open", "closed"] = "open",
):
    _, _, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        role = require(c, actor.user_id, scope)
        count = (
            select(func.count())
            .select_from(moderation_reports)
            .where(
                moderation_reports.c.scope == moderation_cases.c.scope,
                moderation_reports.c.point_id == moderation_cases.c.point_id,
            )
            .correlate(moderation_cases)
            .scalar_subquery()
        )
        rows = (
            c.execute(
                select(
                    moderation_cases, count.label("reports"), point_hides.c.active.label("hidden")
                )
                .outerjoin(
                    point_hides,
                    (point_hides.c.scope == moderation_cases.c.scope)
                    & (point_hides.c.point_id == moderation_cases.c.point_id),
                )
                .where(
                    moderation_cases.c.scope == scope,
                    moderation_cases.c.status == status,
                    moderation_cases.c.point_id.collate("C") > after,
                )
                .order_by(moderation_cases.c.point_id.collate("C"))
                .limit(31)
            )
            .mappings()
            .all()
        )
    return {
        "role": role,
        "items": [dict(r) for r in rows[:30]],
        "next_cursor": rows[29]["point_id"] if len(rows) > 30 else None,
    }


@router.get("/inspect/{point_id}")
def inspect_point(point_id: PointID, request: Request, scope: Scope = "server"):
    _, _, actor = manager(request, mutation=False)
    public = service(request, {"scope"})
    with public.database.connect() as c:
        role = require(c, actor.user_id, scope)
        store = PublicPoints(public.database, roots=public.core.values(), moderation=False)
        try:
            point = store.raw_on(c, point_id)
        except PublicPointError:
            point = {"id": point_id, "body": None}
        point["display_text"] = point.get("body")
        if point["display_text"] is None and point.get("html"):
            point["display_text"] = html.unescape(re.sub(r"<[^>]*>", " ", point["html"]))
        where = (moderation_reports.c.scope == scope) & (moderation_reports.c.point_id == point_id)
        rows = (
            c.execute(
                select(moderation_reports)
                .where(where)
                .order_by(moderation_reports.c.reporter_id)
                .limit(31)
            )
            .mappings()
            .all()
        )
        hidden = (
            c.execute(
                select(point_hides).where(
                    point_hides.c.scope == scope, point_hides.c.point_id == point_id
                )
            )
            .mappings()
            .one_or_none()
        )
        members = (
            c.execute(select(moderation_roles).where(moderation_roles.c.scope == scope).limit(101))
            .mappings()
            .all()
            if role == "admin"
            else []
        )
        audit_rows = (
            c.execute(
                select(moderation_audit)
                .where(moderation_audit.c.scope == scope, moderation_audit.c.target == point_id)
                .order_by(moderation_audit.c.created_at.desc(), moderation_audit.c.id.desc())
                .limit(20)
            )
            .mappings()
            .all()
        )
    return {
        "point": point,
        "visibility": dict(hidden) if hidden else None,
        "role": role,
        "reports": [dict(r) for r in rows[:30]],
        "reports_more": len(rows) > 30,
        "roles": [dict(r) for r in members[:100]],
        "roles_more": len(members) > 100,
        "audit": [dict(r) for r in audit_rows],
    }
