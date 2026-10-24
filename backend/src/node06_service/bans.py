"""Scope-local publication restrictions. Anonymous reads never gain quarantine access."""

from sqlalchemy import and_, func, or_, select

from .models import moderation_bans as bans
from .models import points
from .root_import import digest


def live():
    return and_(
        bans.c.active.is_(True),
        or_(bans.c.expires_at.is_(None), bans.c.expires_at > func.clock_timestamp()),
    )


def areas(site=None):
    return ("server", site) if site else ("server",)


def mask(author, changed, site=None):
    return (
        select(bans.c.user_id)
        .where(
            live(),
            bans.c.scope.in_(areas(site)),
            bans.c.user_id == author,
            or_(bans.c.mode == "block", changed >= bans.c.starts_at),
        )
        .exists()
    )


def point_mask(point_id, site=None):
    p = points.alias("ban_point")
    return (
        select(p.c.id)
        .where(
            p.c.id == point_id,
            p.c.origin == "user",
            mask(p.c.author_user_id, p.c.content_updated_at, site),
        )
        .exists()
    )


def publication(c, actor, site=None, *, proposal=False):
    from .public_points import PublicPointError

    rows = c.execute(
        select(bans.c.scope, bans.c.mode).where(
            live(),
            bans.c.scope.in_(areas(site)),
            bans.c.user_id == actor,
        )
    ).all()
    modes = {mode for _, mode in rows}
    if "block" in modes or (proposal and modes):
        raise PublicPointError("PUBLICATION_BANNED", 403)
    quarantine_scopes = {scope for scope, mode in rows if mode == "quarantine"}
    return (
        "server" if "server" in quarantine_scopes else site if site in quarantine_scopes else None
    )


def epoch(c):
    """Server visibility changes affect persisted weights, including automatic expiry."""
    rows = c.execute(
        select(bans.c.user_id, bans.c.mode, bans.c.starts_at, bans.c.expires_at)
        .where(live(), bans.c.scope == "server")
        .order_by(bans.c.user_id)
    ).all()
    return digest(
        [
            [uid, mode, start.isoformat(), end.isoformat() if end else None]
            for uid, mode, start, end in rows
        ]
    )


EMPTY_EPOCH = digest([])


def can_review(c, actor, scope):
    from .moderation import role_on

    return bool(role_on(c, actor, scope)) or bool(
        c.scalar(
            select(bans.c.user_id).where(
                live(),
                bans.c.user_id == actor,
                bans.c.scope.in_(areas(None if scope == "server" else scope)),
            )
        )
    )


def restrictions(c, point_id, site=None):
    p = points.alias("restricted_point")
    return (
        c.execute(
            select(bans)
            .join(p, p.c.author_user_id == bans.c.user_id)
            .where(
                p.c.id == point_id,
                p.c.origin == "user",
                live(),
                bans.c.scope.in_(areas(site)),
                or_(bans.c.mode == "block", p.c.content_updated_at >= bans.c.starts_at),
            )
        )
        .mappings()
        .all()
    )


def require_review(c, actor, scope, point_id=None):
    from .moderation import ModerationError, role_on, scope_on

    scope_on(c, scope)
    if not can_review(c, actor, scope):
        raise ModerationError("QUARANTINE_FORBIDDEN", 403)
    if point_id:
        rows = restrictions(c, point_id, None if scope == "server" else scope)
        if not rows or any(
            row["mode"] != "quarantine" or not can_review(c, actor, row["scope"]) for row in rows
        ):
            raise ModerationError("POINT_NOT_FOUND", 404)
        # Explicit hides are independent: the quarantine cohort cannot bypass them.
        from .models import point_hides

        hidden = c.scalars(
            select(point_hides.c.scope).where(
                point_hides.c.point_id == point_id,
                point_hides.c.active.is_(True),
                point_hides.c.scope.in_(areas(None if scope == "server" else scope)),
            )
        ).all()
        if any(not role_on(c, actor, area) for area in hidden):
            raise ModerationError("POINT_NOT_FOUND", 404)
