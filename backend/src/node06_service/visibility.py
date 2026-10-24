"""Public visibility on this server; caller may choose a site, never skip server hides."""

import re

from sqlalchemy import select

from .bans import point_mask
from .models import point_hides, points

SCOPE = re.compile(r"server|s_[0-9a-f]{32}")


def scopes(site=None):
    return ("server", site) if site else ("server",)


def visible(point_id, site=None):
    return (
        ~point_mask(point_id, site)
        & ~select(point_hides.c.point_id)
        .where(
            point_hides.c.point_id == point_id,
            point_hides.c.scope.in_(scopes(site)),
            point_hides.c.active.is_(True),
        )
        .exists()
    )


def hidden_ids(connection, ids, site=None):
    if not ids:
        return set()
    hidden = set(
        connection.scalars(
            select(point_hides.c.point_id).where(
                point_hides.c.point_id.in_(list(ids)),
                point_hides.c.scope.in_(scopes(site)),
                point_hides.c.active.is_(True),
            )
        )
    )
    hidden.update(
        connection.scalars(
            select(points.c.id).where(points.c.id.in_(list(ids)), point_mask(points.c.id, site))
        )
    )
    return hidden
