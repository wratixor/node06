"""Private creation-only feed, using current follows and immutable birth links."""

import base64
import json
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import cast, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB

from .models import (
    point_blocks,
    point_revisions,
    points,
    site_user_blocks,
    subscriptions,
    user_blocks,
    user_trust,
)
from .public_points import PublicPointError
from .root_import import POINT


def stamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError
    return result.astimezone(UTC)


def encode(actor, after, ceiling):
    value = [1, actor, after[0].isoformat(), after[1], ceiling[0].isoformat(), ceiling[1]]
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def decode(value, actor):
    try:
        raw = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        if not isinstance(raw, list) or len(raw) != 6 or raw[0] != 1 or raw[1] != actor:
            raise ValueError
        if not all(isinstance(raw[i], str) and POINT.fullmatch(raw[i]) for i in (3, 5)):
            raise ValueError
        after, ceiling = (stamp(raw[2]), raw[3]), (stamp(raw[4]), raw[5])
        if after > ceiling:
            raise ValueError
        return after, ceiling
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise PublicPointError("INVALID_FEED_CURSOR", 422) from exc


class CreationFeed:
    def __init__(self, public):
        self.public = public

    def query(self, actor):
        original = point_revisions.alias("feed_original")
        birth_links = (
            select(original.c.declared_links)
            .where(original.c.point_id == points.c.id)
            .order_by(original.c.created_at, original.c.id)
            .limit(1)
            .correlate(points)
            .scalar_subquery()
        )
        followed = (
            select(user_trust.c.target_user_id)
            .where(
                user_trust.c.source_user_id == actor,
                user_trust.c.target_user_id == self.public.author.c.id,
            )
            .exists()
        )
        related = (
            select(subscriptions.c.point_id)
            .where(
                subscriptions.c.user_id == actor,
                subscriptions.c.active.is_(True),
                func.jsonb_exists(cast(birth_links, JSONB), subscriptions.c.point_id),
            )
            .exists()
        )
        blocked_author = (
            select(user_blocks.c.target_user_id)
            .where(
                user_blocks.c.source_user_id == actor,
                user_blocks.c.target_user_id == self.public.author.c.id,
            )
            .exists()
        )
        blocked_point = (
            select(point_blocks.c.point_id)
            .where(
                point_blocks.c.user_id == actor,
                point_blocks.c.point_id == points.c.id,
            )
            .exists()
        )
        blocked_on_site = (
            select(site_user_blocks.c.target_user_id)
            .where(
                site_user_blocks.c.source_user_id == actor,
                site_user_blocks.c.target_user_id == self.public.author.c.id,
                site_user_blocks.c.site_id == (self.public.site_id or ""),
            )
            .exists()
        )
        return self.public._query().where(
            or_(followed, related), ~blocked_author, ~blocked_on_site, ~blocked_point
        )

    @staticmethod
    def seek(c, query):
        return c.execute(
            query.with_only_columns(
                points.c.created_at,
                points.c.id,
                maintain_column_froms=True,
            )
            .order_by(points.c.created_at.desc(), points.c.id.collate("C").desc())
            .limit(1)
        ).first()

    def page(self, actor, *, cursor=None, before_day=None, limit=20):
        if cursor and before_day:
            raise PublicPointError("INVALID_PARAMS", 400)
        key = tuple_(points.c.created_at, points.c.id.collate("C"))
        with self.public.database.connect() as c:
            query = self.query(actor)
            if cursor:
                after, ceiling = decode(cursor, actor)
                query = query.where(key < after, key <= ceiling)
            else:
                if before_day:
                    if before_day.year == 9999 and before_day.month == 12 and before_day.day == 31:
                        raise PublicPointError("INVALID_PARAMS", 422)
                    query = query.where(
                        points.c.created_at
                        < datetime.combine(before_day + timedelta(days=1), time(), UTC)
                    )
                ceiling = self.seek(c, query)
            first = self.seek(c, query)
            if not first:
                return {
                    "viewer_id": actor,
                    "day": None,
                    "items": [],
                    "next_cursor": None,
                    "next_day": None,
                }
            day = first[0].astimezone(UTC).date()
            floor = datetime.combine(day, time(), UTC)
            rows = (
                c.execute(
                    query.where(
                        points.c.created_at >= floor,
                        points.c.created_at < floor + timedelta(days=1),
                    )
                    .order_by(points.c.created_at.desc(), points.c.id.collate("C").desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
            if not rows:
                # The public projection may change during this read. Do not invent an empty day.
                raise PublicPointError("FEED_CHANGED", 409)
            last = rows[-1]
            after = (last["created_at"], last["id"])
            older = self.seek(c, query.where(key < after))
            return {
                "viewer_id": actor,
                "day": day.isoformat(),
                "items": [self.public._convert(row, full=False) for row in rows],
                "next_cursor": encode(actor, after, ceiling) if older else None,
                "next_day": older[0].astimezone(UTC).date().isoformat() if older else None,
            }
