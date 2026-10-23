"""Public snapshot geometry with source pins and explicit last-good freshness."""

from sqlalchemy import func, select

from .geometry import MODEL
from .models import influence_runs, social_events, users
from .public_points import PublicPointError


def batch(public, ids):
    if not 1 <= len(ids) <= 64 or len(set(ids)) != len(ids):
        raise PublicPointError("INVALID_PARAMS", 400)
    if not public.database.configured:
        raise PublicPointError("DATABASE_NOT_CONFIGURED", 503)
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
        active = set(c.scalars(select(users.c.id).where(users.c.state == "active").limit(10001)))
        cutoff = c.scalar(select(func.max(social_events.c.seq))) or 0
        data = run["data"] if run else {}
        pending = (
            "geometry" not in data
            or data.get("cutoff_seq") != cutoff
            or active != set(data.get("weights", {}))
        )
        records = []
        for pid in ids:
            try:
                point = public.raw_on(c, pid)
            except PublicPointError:
                continue  # Never reveal hidden/retired point metadata.
            item = {
                "id": pid,
                "revision_id": point["revision_id"],
                "content_digest": point["content_digest"],
                "coordinates": None,
                "color": None,
                "model": MODEL,
                "pending": pending,
            }
            entry = data.get("geometry", {}).get(pid)
            if entry and all(entry[k] == point[k] for k in ("revision_id", "content_digest")):
                item.update(coordinates=entry["coordinates"], color=entry["color"])
            elif entry:
                item["pending"] = True
            records.append(item)
        if (c.scalar(select(func.max(social_events.c.seq))) or 0) != cutoff:
            pending = True
            for item in records:
                item["pending"] = True
        return {
            "schema": "node06-geometry/1",
            "snapshot_id": run["id"] if run else None,
            "pending": pending,
            "items": records,
        }
