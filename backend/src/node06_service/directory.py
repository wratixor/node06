"""Public discovery from persisted T1 snapshots; no social graph identities."""

import html
import re
from datetime import UTC
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .bans import EMPTY_EPOCH, epoch
from .influence import amount
from .models import influence_runs, social_events, users
from .point_api import respond, service
from .public_points import PublicPointError, preview

router = APIRouter(prefix="/api/v1/directory")
UserCursor = Annotated[str, Query(pattern=r"^(?:u_[0-9a-f]{32})?$")]


def user_rows(c, q, after, *, private=False):
    columns = [users.c.id, users.c.handle]
    if private:
        columns += [users.c.created_at, users.c.state]
    query = select(*columns).where(
        users.c.id.collate("C") > after,
        users.c.handle.contains(q.strip().casefold(), autoescape=True),
    )
    if not private:
        query = query.where(users.c.state == "active")
    rows = c.execute(query.order_by(users.c.id.collate("C")).limit(21)).mappings().all()
    items = [dict(row) for row in rows[:20]]
    for item in items:
        if private:
            item["created_at"] = item["created_at"].astimezone(UTC).isoformat()
    return {"items": items, "next_cursor": rows[19]["id"] if len(rows) > 20 else None}


@router.get("/users")
def search_users(
    request: Request, q: Annotated[str, Query(max_length=64)] = "", after: UserCursor = ""
):
    def read():
        public = service(request, {"q", "after"})
        public._check()
        with public.database.connect() as c:
            return user_rows(c, q, after)

    return respond(read)


def ranking(public, kind, after):
    public._check()
    with public.database.connect() as c:
        run = (
            c.execute(
                select(influence_runs)
                .order_by(influence_runs.c.created_at.desc(), influence_runs.c.id.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        result = {"items": [], "next_cursor": None, "pending": True, "snapshot_id": None}
        if not run:
            return result
        data = run["data"]
        active = dict(
            c.execute(
                select(users.c.id, users.c.handle).where(users.c.state == "active").limit(10001)
            ).all()
        )
        latest = c.scalar(select(func.max(social_events.c.seq))) or 0
        result["snapshot_id"] = run["id"]
        if (
            data.get("ban_epoch", EMPTY_EPOCH) != epoch(c)
            or "geometry" not in data
            or "point_mass" not in data
            or data.get("cutoff_seq") != latest
            or set(active) != set(data.get("weights", {}))
        ):
            return result
        offset = 0
        if after:
            match = re.fullmatch(r"(i_[0-9a-f]{32}):(users|points):(\d{1,6})", after)
            if not match:
                raise PublicPointError("INVALID_CURSOR", 422)
            if match[1] != run["id"] or match[2] != kind:
                raise PublicPointError("RANKING_CHANGED", 409)
            offset = int(match[3])
        values = (
            data["weights"]
            if kind == "users"
            else {
                pid: entry["current"]
                for pid, entry in data["point_mass"].items()
                if entry["current"] > 0
            }
        )
        ordered = sorted(values, key=lambda pid: (-values[pid], pid))
        # Bounded visibility checks, including static roots; sparse pages may be empty.
        end = min(offset + 100, len(ordered))
        index = offset
        while index < end and len(result["items"]) < 20:
            pid = ordered[index]
            index += 1
            if kind == "users":
                item = {"id": pid, "handle": active[pid]}
            else:
                try:
                    point = public.raw_on(c, pid)
                except PublicPointError as exc:
                    if exc.status == 404:
                        continue
                    raise
                pin = data["point_mass"][pid]
                if any(pin[key] != point[key] for key in ("revision_id", "content_digest")):
                    return {**result, "items": [], "pending": True}
                item = {
                    "id": pid,
                    "preview": preview(
                        point.get("body")
                        or html.unescape(re.sub(r"<[^>]*>", " ", point.get("html", "")))
                    ),
                    "author": point.get("author"),
                }
            result["items"].append({**item, "influence": amount(values[pid])})
        # A write during this read must not label an obsolete ranking as current.
        if (c.scalar(select(func.max(social_events.c.seq))) or 0) != latest:
            return {**result, "items": [], "pending": True}
        result.update(pending=False, model=data["model"], created_at=run["created_at"].isoformat())
        if index < len(ordered):
            result["next_cursor"] = f"{run['id']}:{kind}:{index}"
        return result


@router.get("/rankings")
def rankings(
    request: Request,
    kind: Literal["users", "points"] = "users",
    after: Annotated[str, Query(max_length=64)] = "",
):
    return respond(lambda: ranking(service(request, {"kind", "after"}), kind, after))
