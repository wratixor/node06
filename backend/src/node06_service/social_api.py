"""Trusted first-party social writes and bounded public/private reads."""

from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select

from .auth_api import authenticated_mutation
from .author_api import Content, PointID, RevisionID
from .hosted import PUBLIC_HEADERS
from .models import (
    ballots,
    favorite_points,
    inbox,
    influence_runs,
    proposals,
    root_entries,
    social_events,
    social_user_state,
    subscriptions,
    user_trust,
    users,
)
from .point_api import service as public_service
from .site_api import manager
from .social import Social, SocialError

router = APIRouter(prefix="/api/v1")
ProposalID = Annotated[str, StringConstraints(strict=True, pattern=r"^q_[0-9a-f]{32}$")]
UserID = Annotated[str, StringConstraints(strict=True, pattern=r"^u_[0-9a-f]{32}$")]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: RevisionID | None
    content_digest: Digest
    active: bool = Field(strict=True)


class Proposal(Content):
    expected_revision_id: RevisionID | None
    expected_digest: Digest


class Vote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: Literal["old", "new"]


class Trust(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool = Field(strict=True)


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


def mutate(request, kind, target, payload):
    public = public_service(request, set())
    auth, token = authenticated_mutation(request)
    actor = auth.authenticate(token)
    key = request.headers.get("Idempotency-Key", "")
    if not 8 <= len(key) <= 80 or not all(
        ch.isascii() and (ch.isalnum() or ch in "-_") for ch in key
    ):
        raise SocialError("IDEMPOTENCY_KEY_REQUIRED")
    auth._limit("social-owner", actor.user_id, 240, 3600)
    auth._limit("social-ip", request.client.host, 480, 3600)
    service = Social(public, lambda c, uid: auth.authorize_session(c, token, uid))
    return service.mutate(actor.user_id, key, kind, target, payload.model_dump())


@router.post("/points/{point_id}/subscription")
def subscribe(point_id: PointID, payload: Subscription, request: Request):
    return mutate(request, "subscription", point_id, payload)


@router.post("/points/{point_id}/proposals", status_code=201)
def propose(point_id: PointID, payload: Proposal, request: Request):
    return mutate(request, "propose", point_id, payload)


@router.post("/proposals/{proposal_id}/vote")
def vote(proposal_id: ProposalID, payload: Vote, request: Request):
    return mutate(request, "vote", proposal_id, payload)


@router.post("/people/{user_id}/trust")
def trust(user_id: UserID, payload: Trust, request: Request):
    return mutate(request, "trust", user_id, payload)


@router.post("/me/inbox/{event_seq}/read")
def mark_read(event_seq: Annotated[int, Field(ge=1)], payload: Empty, request: Request):
    return mutate(request, "read_notice", str(event_seq), payload)


def public_proposal(row):
    return {
        key: row[key]
        for key in (
            "id",
            "point_id",
            "author_user_id",
            "base_revision_id",
            "base_digest",
            "base_body",
            "base_lang",
            "candidate_revision_id",
            "candidate_digest",
            "content",
            "state",
            "created_at",
            "closes_at",
            "result",
        )
    }


@router.get("/points/{point_id}/social")
def point_social(point_id: PointID, request: Request, response: Response):
    response.headers.update(PUBLIC_HEADERS)
    public = public_service(request, set())
    point = public._raw(point_id)
    with public.database.connect() as c:
        protected = (
            point["source"]["kind"] not in ("user", "site")
            or c.scalar(select(root_entries.c.point_id).where(root_entries.c.point_id == point_id))
            is not None
        )
        rows = (
            c.execute(
                select(proposals)
                .where(proposals.c.point_id == point_id)
                .order_by(proposals.c.created_at.desc(), proposals.c.id.desc())
                .limit(10)
            )
            .mappings()
            .all()
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
        derived = None
        if run:
            from .influence import amount

            latest = c.scalar(select(func.max(social_events.c.seq))) or 0
            active = set(
                c.execute(
                    select(users.c.id).where(users.c.state == "active").limit(10001)
                ).scalars()
            )
            pending = run["data"].get("cutoff_seq") != latest or active != set(
                run["data"]["weights"]
            )
            tally = {}
            for row in rows:
                choices = dict(
                    c.execute(
                        select(ballots.c.user_id, ballots.c.choice).where(
                            ballots.c.proposal_id == row["id"]
                        )
                    ).all()
                )
                old = new = total = 0
                for user, allocations in run["data"]["allocations"].items():
                    units = allocations.get(point_id, 0)
                    total += units
                    if choices.get(user) == "old":
                        old += units
                    if choices.get(user) == "new":
                        new += units
                tally[row["id"]] = {
                    "old": amount(old),
                    "new": amount(new),
                    "subscribed": amount(total),
                }
            derived = {
                "snapshot_id": run["id"],
                "pending": pending,
                "tallies": None if pending else tally,
            }
    return {
        "point": point,
        "protected": protected,
        "proposals": [public_proposal(q) for q in rows],
        "influence": derived,
    }


@router.get("/proposals/{proposal_id}")
def proposal(proposal_id: ProposalID, request: Request, response: Response):
    response.headers.update(PUBLIC_HEADERS)
    public = public_service(request, set())
    with public.database.connect() as c:
        q = Social(public)._proposal(c, proposal_id)
        public.raw_on(c, q["point_id"])
        return public_proposal(q)


@router.get("/me/social")
def own(
    request: Request, after: PointID | None = None, limit: Annotated[int, Query(ge=1, le=30)] = 20
):
    _, _, actor = manager(request, mutation=False)
    public = public_service(request, {"after", "limit"})
    with public.database.connect() as c:
        query = select(subscriptions).where(
            subscriptions.c.user_id == actor.user_id, subscriptions.c.active.is_(True)
        )
        if after:
            query = query.where(subscriptions.c.point_id > after)
        rows = c.execute(query.order_by(subscriptions.c.point_id).limit(limit + 1)).mappings().all()
        trust = list(
            c.execute(
                select(user_trust.c.target_user_id)
                .where(user_trust.c.source_user_id == actor.user_id)
                .order_by(user_trust.c.target_user_id)
                .limit(100)
            ).scalars()
        )
        choices = [
            dict(row)
            for row in c.execute(
                select(ballots.c.proposal_id, ballots.c.choice)
                .join(proposals, proposals.c.id == ballots.c.proposal_id)
                .where(ballots.c.user_id == actor.user_id, proposals.c.state == "open")
                .limit(100)
            ).mappings()
        ]
    return {
        "items": [dict(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1]["point_id"] if len(rows) > limit else None,
        "trust": trust,
        "ballots": choices,
    }


@router.get("/me/inbox")
def notifications(
    request: Request,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    _, _, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        query = (
            select(social_events, inbox.c.read_at)
            .join(inbox, inbox.c.event_seq == social_events.c.seq)
            .where(inbox.c.user_id == actor.user_id)
        )
        if before:
            query = query.where(social_events.c.seq < before)
        rows = (
            c.execute(query.order_by(social_events.c.seq.desc()).limit(limit + 1)).mappings().all()
        )
    return {
        "items": [dict(r) for r in rows[:limit]],
        "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
    }


@router.get("/news")
def news(request: Request, response: Response, before: Annotated[int | None, Query(ge=1)] = None):
    response.headers.update(PUBLIC_HEADERS)
    public = public_service(request, {"before"})
    with public.database.connect() as c:
        query = select(social_events).where(social_events.c.public.is_(True))
        if before:
            query = query.where(social_events.c.seq < before)
        rows = c.execute(query.order_by(social_events.c.seq.desc()).limit(21)).mappings().all()
    return {
        "items": [dict(r) for r in rows[:20]],
        "next_cursor": rows[19]["seq"] if len(rows) > 20 else None,
    }


@router.get("/people")
def people(
    request: Request, response: Response, q: Annotated[str, Query(min_length=1, max_length=64)]
):
    response.headers.update(PUBLIC_HEADERS)
    public = public_service(request, {"q"})
    with public.database.connect() as c:
        rows = (
            c.execute(
                select(users.c.id, users.c.handle)
                .where(
                    users.c.state == "active",
                    users.c.handle.contains(q.strip().casefold(), autoescape=True),
                )
                .order_by(users.c.handle)
                .limit(10)
            )
            .mappings()
            .all()
        )
    return {"items": [dict(row) for row in rows]}


@router.get("/me/subscriptions/{point_id}")
def own_subscription(point_id: PointID, request: Request):
    _, _, actor = manager(request, mutation=False)
    with request.app.state.database.connect() as c:
        row = (
            c.execute(
                select(subscriptions).where(
                    subscriptions.c.user_id == actor.user_id, subscriptions.c.point_id == point_id
                )
            )
            .mappings()
            .one_or_none()
        )
        choice = c.scalar(
            select(ballots.c.choice)
            .join(proposals, proposals.c.id == ballots.c.proposal_id)
            .where(
                proposals.c.point_id == point_id,
                proposals.c.state == "open",
                ballots.c.user_id == actor.user_id,
            )
        )
        last = c.scalar(
            select(social_user_state.c.last_proposed_at).where(
                social_user_state.c.user_id == actor.user_id
            )
        )
    return {
        "subscription": dict(row) if row else None,
        "ballot": choice,
        "next_proposal_at": last + timedelta(hours=24) if last else None,
    }


@router.get("/me/influence")
def own_influence(request: Request):
    _, _, actor = manager(request, mutation=False)
    from .influence import amount

    with request.app.state.database.connect() as c:
        run = (
            c.execute(
                select(influence_runs)
                .order_by(influence_runs.c.created_at.desc(), influence_runs.c.id.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if not run or actor.user_id not in run["data"]["weights"]:
            return None
        latest = c.scalar(select(func.max(social_events.c.seq))) or 0
        units = run["data"]["weights"][actor.user_id]
        return {
            "snapshot_id": run["id"],
            "weight": amount(units),
            "point_budget": amount(units // 2),
            "pending": run["data"].get("cutoff_seq") != latest,
        }


@router.post("/me/favorites/{point_id}")
def favorite(point_id: PointID, payload: Trust, request: Request):
    return mutate(request, "favorite", point_id, payload)


@router.get("/me/favorites")
def favorites(request: Request):
    _, _, actor = manager(request, mutation=False)
    public = public_service(request, set())
    from .public_points import PublicPointError

    with request.app.state.database.connect() as c:
        ids = c.scalars(
            select(favorite_points.c.point_id)
            .where(favorite_points.c.user_id == actor.user_id)
            .order_by(favorite_points.c.point_id)
        ).all()
        items = []
        for pid in ids:
            try:
                point = public.raw_on(c, pid)
                items.append(
                    {key: point[key] for key in ("id", "preview", "revision_id", "content_digest")}
                )
            except PublicPointError:
                items.append({"id": pid, "preview": "", "unavailable": True})
    return {"items": items}
