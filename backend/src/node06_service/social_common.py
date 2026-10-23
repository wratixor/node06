"""Small shared write guards and audit helpers; imports no web application."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import exists, insert, select

from .models import social_events, subscriptions, users


def active_support(point_id):
    return exists(
        select(subscriptions.c.user_id)
        .join(users, users.c.id == subscriptions.c.user_id)
        .where(
            subscriptions.c.point_id == point_id,
            subscriptions.c.active.is_(True),
            users.c.state == "active",
        )
    )


def event(
    c,
    kind,
    point_id=None,
    *,
    actor=None,
    proposal=None,
    payload=None,
    notify=False,
    public=False,
    now=None,
):
    return c.execute(
        insert(social_events)
        .values(
            kind=kind,
            point_id=point_id,
            actor_user_id=actor,
            proposal_id=proposal,
            payload=payload or {},
            public=public,
            fanout_done=not notify,
            created_at=now or datetime.now(UTC),
        )
        .returning(social_events.c.seq)
    ).scalar_one()


def uid(prefix):
    return prefix + "_" + uuid4().hex
