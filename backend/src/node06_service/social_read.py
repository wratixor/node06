"""Public per-point projection; no subscriber identities or personal session data."""

from sqlalchemy import func, select

from .bans import EMPTY_EPOCH, epoch
from .bans import mask as ban_mask
from .influence import amount
from .models import influence_runs, proposals, root_entries, social_events, users
from .public_points import PublicPointError


def point_summary(public, point_id):
    if not public.database.configured:
        raise PublicPointError("DATABASE_NOT_CONFIGURED", 503)
    with public.database.connect() as c:
        point = public.raw_on(c, point_id)
        protected = (
            point["source"]["kind"] not in ("user", "site")
            or c.scalar(select(root_entries.c.point_id).where(root_entries.c.point_id == point_id))
            is not None
        )
        proposal = (
            c.execute(
                select(proposals)
                .where(
                    proposals.c.point_id == point_id,
                    proposals.c.state == "open",
                    ~ban_mask(proposals.c.author_user_id, proposals.c.created_at, public.site_id),
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        run = (
            c.execute(
                select(influence_runs)
                .order_by(influence_runs.c.created_at.desc(), influence_runs.c.id.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        influence = {
            "available": False,
            "pending": True,
            "current": None,
            "held": None,
            "subscribed": None,
            "blocked": None,
            "blocked_held": None,
            "snapshot_id": None,
            "model": None,
        }
        ballot = None
        if run:
            data = run["data"]
            entry = data.get("point_mass", {}).get(point_id)
            active = set(
                c.scalars(select(users.c.id).where(users.c.state == "active").limit(10001))
            )
            latest = c.scalar(select(func.max(social_events.c.seq))) or 0
            pending = (
                data.get("ban_epoch", EMPTY_EPOCH) != epoch(c)
                or "geometry" not in data
                or "point_mass" not in data
                or data.get("cutoff_seq") != latest
                or active != set(data["weights"])
                or bool(
                    entry and any(entry[k] != point[k] for k in ("revision_id", "content_digest"))
                )
            )
            influence.update(
                available=True, pending=pending, snapshot_id=run["id"], model=data["model"]
            )
            if not pending:
                influence.update(
                    {
                        key: amount(entry.get(key, 0) if entry else 0)
                        for key in ("current", "held", "subscribed", "blocked", "blocked_held")
                    }
                )
            if proposal and not pending:
                # The existing public proposal read owns ballot aggregation. Keep
                # this small transport free of voter IDs and candidate bodies.
                from .models import ballots

                choices = dict(
                    c.execute(
                        select(ballots.c.user_id, ballots.c.choice).where(
                            ballots.c.proposal_id == proposal["id"]
                        )
                    ).all()
                )
                totals = {"old": 0, "new": 0}
                for actor, allocation in data["allocations"].items():
                    choice = choices.get(actor)
                    if choice in totals:
                        totals[choice] += allocation.get(point_id, 0)
                # A concurrent vote after snapshot selection must never get a fresh label.
                if (c.scalar(select(func.max(social_events.c.seq))) or 0) != latest:
                    influence.update(pending=True, current=None, held=None, subscribed=None)
                else:
                    ballot = {key: amount(value) for key, value in totals.items()}
        return {
            "schema": "node06-point-social/1",
            "id": point_id,
            "revision_id": point["revision_id"],
            "content_digest": point["content_digest"],
            "protected": protected,
            "author": {
                k: v
                for k, v in point.get("author", {"kind": "source", "name": "Git source"}).items()
            },
            "influence": influence,
            "proposal": (
                {
                    "id": proposal["id"],
                    "closes_at": proposal["closes_at"].isoformat(),
                    "tally": ballot,
                }
                if proposal
                else None
            ),
        }
