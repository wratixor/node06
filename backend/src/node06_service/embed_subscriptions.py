"""Only point subscriptions. No cookie authority, general API proxy or parent bearer."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, text, update

from .auth import digest
from .models import embed_subscriptions as grants
from .models import sessions, sites, subscriptions, users
from .profile_links import challenge
from .public_points import PublicPointError
from .social import Social


def now():
    return datetime.now(UTC)


def fail():
    raise PublicPointError("SUBSCRIPTIONS_NOT_CONNECTED", 401)


def site(c, sid, parent):
    row = (
        c.execute(select(sites).where(sites.c.id == sid).with_for_update()).mappings().one_or_none()
    )
    if not row or row["state"] != "active" or row["primary_origin"] != parent:
        raise PublicPointError("SUBSCRIPTION_SITE_CHANGED", 403)


def prepare(db, sid, payload):
    rid = "e_" + uuid4().hex
    with db.begin() as c:
        site(c, sid, payload.parent_origin)
        c.execute(
            delete(grants).where(
                grants.c.pending_until < now() - timedelta(days=1),
                or_(
                    grants.c.approved_until.is_(None),
                    grants.c.approved_until < now() - timedelta(days=1),
                ),
            )
        )
        count = c.scalar(
            select(func.count())
            .select_from(grants)
            .where(grants.c.site_id == sid, grants.c.pending_until > now())
        )
        if count >= 1000:
            raise PublicPointError("SUBSCRIPTION_REQUEST_LIMIT", 429)
        c.execute(
            grants.insert().values(
                id=rid,
                site_id=sid,
                **payload.model_dump(),
                pending_until=now() + timedelta(minutes=5),
            )
        )
    return {"id": rid, "state": payload.state}


def pending(c, rid):
    row = (
        c.execute(select(grants).where(grants.c.id == rid).with_for_update())
        .mappings()
        .one_or_none()
    )
    if not row or row["revoked"] or row["pending_until"] <= now():
        raise PublicPointError("SUBSCRIPTION_REQUEST_EXPIRED", 409)
    return row


def reusable(c, row, uid, session_digest):
    return c.scalar(
        select(grants.c.approved_until)
        .where(
            grants.c.user_id == uid,
            grants.c.session_digest == session_digest,
            grants.c.site_id == row["site_id"],
            grants.c.parent_origin == row["parent_origin"],
            grants.c.consented.is_(True),
            grants.c.revoked.is_(False),
            grants.c.approved_until > now(),
        )
        .order_by(grants.c.approved_until.desc())
        .limit(1)
    )


def approve(db, rid, uid, session_token, authorize, resume=False):
    code = secrets.token_urlsafe(32)
    with db.connect() as c:
        initial = c.execute(select(grants).where(grants.c.id == rid)).mappings().one_or_none()
    if not initial:
        raise PublicPointError("SUBSCRIPTION_REQUEST_EXPIRED", 409)
    with db.begin() as c:
        authorize(c, uid)
        site(c, initial["site_id"], initial["parent_origin"])
        row = pending(c, rid)
        if row["token_digest"] or (row["user_id"] and row["user_id"] != uid):
            raise PublicPointError("SUBSCRIPTION_REQUEST_USED", 409)
        expiry = (
            reusable(c, row, uid, digest(session_token))
            if resume
            else now() + timedelta(minutes=15)
        )
        if not expiry:
            raise PublicPointError("SUBSCRIPTION_CONSENT_REQUIRED", 409)
        c.execute(
            update(grants)
            .where(grants.c.id == rid)
            .values(
                user_id=uid,
                session_digest=digest(session_token),
                approved_until=expiry,
                code_digest=digest(code),
                code_until=now() + timedelta(seconds=60),
                consented=True,
            )
        )
    return {"id": rid, "state": row["state"], "code": code}


def owner_lock(c, row, management):
    if not c.scalar(
        select(users.c.id)
        .where(users.c.id == row["user_id"], users.c.state == "active")
        .with_for_update()
    ):
        fail()
    if not c.scalar(
        select(sessions.c.digest)
        .where(
            sessions.c.digest == row["session_digest"],
            sessions.c.user_id == row["user_id"],
            sessions.c.revoked_at.is_(None),
            sessions.c.expires_at > now(),
        )
        .with_for_update()
    ):
        fail()
    site(c, row["site_id"], row["parent_origin"])
    current = (
        c.execute(select(grants).where(grants.c.id == row["id"]).with_for_update()).mappings().one()
    )
    if (
        current["user_id"] != row["user_id"]
        or current["session_digest"] != row["session_digest"]
        or current["revoked"]
        or not current["approved_until"]
        or current["approved_until"] <= now()
    ):
        fail()
    c.execute(
        text("SELECT set_config('node06.profile_origin',:origin,true)"), {"origin": management}
    )
    return current


def redeem(db, sid, payload, management):
    with db.connect() as c:
        row = c.execute(select(grants).where(grants.c.id == payload.id)).mappings().one_or_none()
    if (
        not row
        or row["site_id"] != sid
        or row["parent_origin"] != payload.parent_origin
        or not row["user_id"]
    ):
        fail()
    token = secrets.token_urlsafe(32)
    with db.begin() as c:
        current = owner_lock(c, row, management)
        if (
            current["state"] != payload.state
            or current["token_digest"]
            or not current["code_digest"]
            or current["code_until"] <= now()
            or not secrets.compare_digest(current["code_digest"], digest(payload.code))
            or not secrets.compare_digest(current["challenge"], challenge(payload.verifier))
        ):
            fail()
        c.execute(
            update(grants)
            .where(grants.c.id == row["id"])
            .values(token_digest=digest(token), code_digest=None)
        )
    return {"token": token, "expires_at": current["approved_until"].isoformat()}


def complete(db, sid, payload, management):
    """PKCE-bound rendezvous also works when a browser removes window.opener."""
    with db.connect() as c:
        row = c.execute(select(grants).where(grants.c.id == payload.id)).mappings().one_or_none()
    if (
        not row
        or row["site_id"] != sid
        or row["parent_origin"] != payload.parent_origin
        or row["state"] != payload.state
        or row["revoked"]
        or row["pending_until"] <= now()
        or not secrets.compare_digest(row["challenge"], challenge(payload.verifier))
    ):
        fail()
    if not row["user_id"]:
        return {"connected": False}
    token = secrets.token_urlsafe(32)
    with db.begin() as c:
        current = owner_lock(c, row, management)
        if (
            current["pending_until"] <= now()
            or not current["consented"]
            or current["token_digest"]
            or not current["code_digest"]
            or current["code_until"] <= now()
        ):
            fail()
        c.execute(
            update(grants)
            .where(grants.c.id == row["id"])
            .values(token_digest=digest(token), code_digest=None)
        )
    return {"connected": True, "token": token, "expires_at": current["approved_until"].isoformat()}


def lookup(db, sid, token, parent):
    with db.connect() as c:
        row = (
            c.execute(
                select(grants).where(
                    grants.c.token_digest == digest(token),
                    grants.c.site_id == sid,
                    grants.c.parent_origin == parent,
                )
            )
            .mappings()
            .one_or_none()
        )
    if not row:
        fail()
    return row


def read(public, row, management, pid):
    # Private read and public visibility are checked within one short transaction.
    with public.database.begin() as c:
        owner_lock(c, row, management)
        public.raw_on(c, pid)
        sub = (
            c.execute(
                select(subscriptions).where(
                    subscriptions.c.user_id == row["user_id"], subscriptions.c.point_id == pid
                )
            )
            .mappings()
            .one_or_none()
        )
    return {
        "connection": digest(
            "node06-subscription-session/1:"
            + row["session_digest"]
            + ":"
            + row["site_id"]
            + ":"
            + row["parent_origin"]
        ),
        "expires_at": row["approved_until"].isoformat(),
        "subscription": {k: sub[k] for k in ("active", "revision_id", "content_digest")}
        if sub
        else None,
    }


def mutate(public, row, management, pid, payload, key):
    return Social(public, lambda c, uid: owner_lock(c, row, management)).mutate(
        row["user_id"], key, "subscription", pid, payload.model_dump()
    )
