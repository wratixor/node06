"""Atomic retention cleanup, called only by the graph-locked background worker."""

from sqlalchemy import func, insert, select, text, update

from .models import (
    core_publications,
    moderation_audit,
    point_blocks,
    point_hides,
    point_revisions,
    point_tombstones,
    points,
    proposals,
    sites,
    subscriptions,
)
from .social_common import event, uid


def absent(point_id):
    return (
        ~select(point_tombstones.c.point_id).where(point_tombstones.c.point_id == point_id).exists()
    )


def purged_ids(c, ids):
    return (
        set(
            c.scalars(
                select(point_tombstones.c.point_id).where(
                    point_tombstones.c.point_id.in_(list(ids))
                )
            )
        )
        if ids
        else set()
    )


def require_live(c, point_id):
    if purged_ids(c, [point_id]):
        from .public_points import PublicPointError

        raise PublicPointError("POINT_PURGED", 410)


def marker(c, point_id):
    row = (
        c.execute(
            select(points.c.origin, points.c.created_at, point_tombstones.c.purged_at)
            .join(point_tombstones, point_tombstones.c.point_id == points.c.id)
            .where(points.c.id == point_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    from .root_import import digest

    return {
        "id": point_id,
        "origin": row["origin"],
        "lang": "und",
        "body": "",
        "html": "<p>Point deleted.</p>",
        "preview": "Point deleted",
        "deleted": True,
        "purged_at": row["purged_at"].isoformat(),
        "created_at": row["created_at"].isoformat(),
        "last_interaction_at": row["purged_at"].isoformat(),
        "links": [],
        "declared_links": [],
        "links_truncated": False,
        "neighbors_cursor": None,
        "revision_id": None,
        "content_digest": digest({"deleted": point_id}),
        "source": {"kind": "tombstone"},
        "author": {"kind": "system", "name": "System"},
    }


def sweep(c, limit=1):
    """Caller holds lock_graph. Clock is sampled after acquiring that lock."""
    now = c.scalar(select(func.clock_timestamp()))
    from datetime import timedelta

    due = (
        c.execute(
            select(point_hides)
            .join(points, points.c.id == point_hides.c.point_id)
            .where(
                point_hides.c.scope == "server",
                point_hides.c.active.is_(True),
                point_hides.c.hidden_since <= now - timedelta(days=30),
                absent(point_hides.c.point_id),
            )
            .order_by(point_hides.c.hidden_since, point_hides.c.point_id)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    for row in due:
        pid = row["point_id"]
        c.execute(
            insert(point_tombstones).values(
                point_id=pid, hidden_since=row["hidden_since"], purged_at=now
            )
        )
        c.execute(
            update(point_revisions)
            .where(point_revisions.c.point_id == pid)
            .values(body="", search_text="", declared_links=[])
        )
        c.execute(
            update(core_publications).where(core_publications.c.point_id == pid).values(body="")
        )
        c.execute(
            update(subscriptions)
            .where(subscriptions.c.point_id == pid)
            .values(active=False, static_body=None)
        )
        c.execute(
            update(point_blocks).where(point_blocks.c.point_id == pid).values(static_body=None)
        )
        c.execute(
            update(proposals)
            .where(proposals.c.point_id == pid, proposals.c.state == "open")
            .values(state="stale", result={"reason": "point-purged"})
        )
        c.execute(
            update(proposals)
            .where(proposals.c.point_id == pid)
            .values(
                base_body="",
                content={},
                citations=[],
            )
        )
        # Also erase structured root snapshots kept in other points' citations.
        for table in ("authored_revisions", "proposals"):
            c.execute(
                text(f"""UPDATE {table} SET citations = (
                SELECT coalesce(jsonb_agg(CASE WHEN ref->>'id' = :pid
                  THEN ref || jsonb_build_object('static_body', NULL) ELSE ref END), '[]'::jsonb)
                FROM jsonb_array_elements(citations::jsonb) AS ref)::json
                WHERE citations::jsonb @> jsonb_build_array(
                  jsonb_build_object('id', CAST(:pid AS text)))"""),
                {"pid": pid},
            )
        c.execute(
            update(sites)
            .where(sites.c.id == pid)
            .values(display_name=None, home_page=None, git_home_page=None, theme={})
        )
        c.execute(update(points).where(points.c.id == pid).values(lifecycle="retired"))
        event(c, "point-purged", pid, now=now)
        c.execute(
            insert(moderation_audit).values(
                id=uid("m"),
                actor_id=None,
                scope="server",
                action="purge",
                target=pid,
                detail={"hidden_since": row["hidden_since"].isoformat()},
                created_at=now,
            )
        )
    return len(due)
