"""Explicit bilateral account pairing. Link-control grants cannot read/apply profiles."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, StringConstraints, ValidationError, field_validator
from sqlalchemy import delete, func, insert, select, update

from .models import profile_links as links
from .models import users
from .profile_packet import Source, Strict
from .public_points import PublicPointError
from .site_claims import normalize_origin

Secret = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$", strict=True)]
LinkID = Annotated[str, StringConstraints(pattern=r"^l_[0-9a-f]{32}$", strict=True)]
UserID = Annotated[str, StringConstraints(pattern=r"^u_[0-9a-f]{32}$", strict=True)]
Handle = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$", strict=True)]
PENDING = timedelta(minutes=10)
LIFETIME = timedelta(days=30)
SCOPE = "node06:link"


def digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def challenge(verifier):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode()
        .rstrip("=")
    )


class Peer(Strict):
    origin: Annotated[str, Field(max_length=512)]

    @field_validator("origin")
    @classmethod
    def canonical(cls, value):
        return normalize_origin(value)


class Invitation(Peer):
    id: LinkID
    secret: Secret


class Metadata(Peer):
    id: LinkID
    user_id: UserID
    handle: Handle
    recipient: str
    state: Secret
    code_challenge: Secret
    code_challenge_method: Literal["S256"] = "S256"
    scope: Literal["node06:link"] = SCOPE
    redirect_uri: str


class Confirmation(Peer):
    id: LinkID
    code: Secret
    state: Secret
    peer_user_id: UserID
    peer_handle: Handle


class Token(Strict):
    access_token: Secret
    token_type: Literal["Bearer"]
    scope: Literal["node06:link"]
    expires_in: Annotated[int, Field(strict=True, ge=1, le=2592000)]
    id: LinkID
    user_id: UserID
    handle: Handle
    client_user_id: UserID


class Status(Strict):
    active: bool
    id: LinkID
    user_id: UserID
    client_user_id: UserID


def validated(model, value):
    try:
        return model.model_validate(value)
    except ValidationError:
        raise PublicPointError("PROFILE_PEER_INVALID", 502) from None


class ProfileLinks:
    def __init__(self, database, origin, transport, authorize=None, clock=None):
        self.db, self.origin, self.transport = database, Source.https_origin(origin), transport
        self.authorize = authorize
        self.clock = clock or (lambda: datetime.now(UTC))

    def actor(self, c, uid):
        if self.authorize:
            return self.authorize(c, uid).handle
        row = (
            c.execute(select(users).where(users.c.id == uid).with_for_update())
            .mappings()
            .one_or_none()
        )
        if row is None or row["state"] != "active":
            raise PublicPointError("AUTH_REQUIRED", 401)
        return row["handle"]

    def own(self, c, uid, lid):
        row = (
            c.execute(
                select(links).where(links.c.id == lid, links.c.user_id == uid).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PublicPointError("PROFILE_LINK_NOT_FOUND", 404)
        return row

    def room(self, c, uid):
        # Keep history bounded without deleting live control credentials.
        c.execute(
            delete(links).where(
                links.c.user_id == uid, links.c.expires_at < self.clock() - LIFETIME
            )
        )
        count = c.scalar(select(func.count()).select_from(links).where(links.c.user_id == uid))
        if count >= 100:
            raise PublicPointError("PROFILE_LINK_LIMIT", 409)

    def invite(self, uid, peer):
        if peer == self.origin:
            raise PublicPointError("PROFILE_SELF_LINK", 400)
        lid, secret, verifier, nonce = (
            "l_" + uuid4().hex,
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
        )
        with self.db.begin() as c:
            self.actor(c, uid)
            self.room(c, uid)
            c.execute(
                insert(links).values(
                    id=lid,
                    user_id=uid,
                    direction="outbound",
                    peer_origin=peer,
                    status="pending",
                    expires_at=self.clock() + PENDING,
                    invite_digest=digest(secret),
                    verifier=verifier,
                    nonce=nonce,
                    challenge=challenge(verifier),
                )
            )
        return {"origin": self.origin, "id": lid, "secret": secret, "recipient": peer}

    def metadata(self, secret, client):
        with self.db.connect() as c:
            row = (
                c.execute(
                    select(links, users.c.handle)
                    .join(users, users.c.id == links.c.user_id)
                    .where(
                        links.c.invite_digest == digest(secret),
                        links.c.direction == "outbound",
                        links.c.status == "pending",
                        links.c.expires_at > self.clock(),
                        links.c.peer_origin == client,
                        users.c.state == "active",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise PublicPointError("PROFILE_INVITATION_INVALID", 400)
        return Metadata(
            origin=self.origin,
            id=row["id"],
            user_id=row["user_id"],
            handle=row["handle"],
            recipient=client,
            state=row["nonce"],
            code_challenge=row["challenge"],
            redirect_uri=self.origin + "/profile-sync/",
        ).model_dump()

    def inspect(self, invitation):
        if invitation.origin == self.origin:
            raise PublicPointError("PROFILE_SELF_LINK", 400)
        data = validated(
            Metadata,
            self.transport(
                invitation.origin,
                "metadata",
                {"secret": invitation.secret, "client_id": self.origin},
            ),
        )
        if (
            data.origin != invitation.origin
            or data.id != invitation.id
            or data.recipient != self.origin
            or data.redirect_uri != data.origin + "/profile-sync/"
        ):
            raise PublicPointError("PROFILE_PEER_INVALID", 502)
        return data

    def approve(self, uid, invitation, expected):
        # Re-fetch before granting, then compare exact identities/scopes displayed at preview.
        meta = self.inspect(invitation)
        if meta != expected:
            raise PublicPointError("PROFILE_INVITATION_CHANGED", 409)
        code, lid = secrets.token_urlsafe(32), "l_" + uuid4().hex
        with self.db.begin() as c:
            handle = self.actor(c, uid)
            self.room(c, uid)
            c.execute(
                insert(links).values(
                    id=lid,
                    user_id=uid,
                    direction="inbound",
                    peer_origin=meta.origin,
                    peer_user_id=meta.user_id,
                    peer_handle=meta.handle,
                    remote_id=meta.id,
                    status="pending",
                    expires_at=self.clock() + PENDING,
                    nonce=meta.state,
                    challenge=meta.code_challenge,
                    code_digest=digest(code),
                )
            )
        return {
            "origin": self.origin,
            "id": meta.id,
            "code": code,
            "state": meta.state,
            "peer_user_id": uid,
            "peer_handle": handle,
            "recipient": meta.origin,
        }

    def redeem(self, code, verifier, client, redirect):
        # OAuth authorization-code / PKCE binding. Only this grant's link status/revocation.
        with self.db.connect() as c:
            uid = c.scalar(select(links.c.user_id).where(links.c.code_digest == digest(code)))
        if not uid:
            raise PublicPointError("PROFILE_CODE_INVALID", 400)
        token = secrets.token_urlsafe(32)
        with self.db.begin() as c:
            handle = self.actor(c, uid)
            row = (
                c.execute(
                    select(links).where(links.c.code_digest == digest(code)).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["status"] != "pending"
                or row["expires_at"] <= self.clock()
                or row["peer_origin"] != client
                or redirect != client + "/profile-sync/"
                or not secrets.compare_digest(row["challenge"], challenge(verifier))
            ):
                raise PublicPointError("PROFILE_CODE_INVALID", 400)
            c.execute(
                update(links)
                .where(links.c.id == row["id"])
                .values(
                    status="active",
                    code_digest=None,
                    token_digest=digest(token),
                    expires_at=self.clock() + LIFETIME,
                )
            )
        return Token(
            access_token=token,
            token_type="Bearer",
            scope=SCOPE,
            expires_in=int(LIFETIME.total_seconds()),
            id=row["id"],
            user_id=uid,
            handle=handle,
            client_user_id=row["peer_user_id"],
        ).model_dump()

    def confirm(self, uid, payload):
        with self.db.begin() as c:
            self.actor(c, uid)
            row = self.own(c, uid, payload.id)
            if (
                row["direction"] != "outbound"
                or row["status"] != "pending"
                or row["expires_at"] <= self.clock()
                or row["peer_origin"] != payload.origin
                or not secrets.compare_digest(row["nonce"], payload.state)
            ):
                raise PublicPointError("PROFILE_CONFIRMATION_INVALID", 409)
            c.execute(update(links).where(links.c.id == row["id"]).values(status="exchanging"))
        data = None
        try:
            data = validated(
                Token,
                self.transport(
                    payload.origin,
                    "token",
                    {
                        "grant_type": "authorization_code",
                        "code": payload.code,
                        "code_verifier": row["verifier"],
                        "client_id": self.origin,
                        "redirect_uri": self.origin + "/profile-sync/",
                    },
                ),
            )
            if (
                data.user_id != payload.peer_user_id
                or data.handle != payload.peer_handle
                or data.client_user_id != uid
            ):
                raise PublicPointError("PROFILE_PEER_INVALID", 502)
            with self.db.begin() as c:
                self.actor(c, uid)
                current = self.own(c, uid, payload.id)
                if current["status"] != "exchanging" or current["expires_at"] <= self.clock():
                    raise PublicPointError("PROFILE_CONFIRMATION_INVALID", 409)
                c.execute(
                    update(links)
                    .where(links.c.id == payload.id)
                    .values(
                        status="active",
                        peer_user_id=data.user_id,
                        peer_handle=data.handle,
                        remote_id=data.id,
                        remote_token=data.access_token,
                        verifier=None,
                        invite_digest=None,
                        expires_at=self.clock() + timedelta(seconds=data.expires_in),
                    )
                )
        except Exception:
            # Compensate a known remote grant, including concurrent local cancellation.
            # If the response itself was lost, no returned credential is available.
            retry_token = None
            if isinstance(data, Token) and data.client_user_id == uid:
                try:
                    self.transport(payload.origin, "revoke", {"token": data.access_token})
                except PublicPointError:
                    retry_token = data.access_token
            with self.db.begin() as c:
                c.execute(
                    update(links)
                    .where(links.c.id == payload.id, links.c.status.in_(("exchanging", "revoked")))
                    .values(
                        status="revoked",
                        verifier=None,
                        invite_digest=None,
                        remote_token=retry_token,
                        revocation_pending=retry_token is not None,
                    )
                )
            raise
        return {"id": payload.id, "status": "active", "profile_sync": False}

    def token_status(self, token, revoke=False):
        with self.db.begin() as c:
            row = (
                c.execute(
                    select(links, users.c.state)
                    .join(users, users.c.id == links.c.user_id)
                    .where(links.c.token_digest == digest(token))
                    .with_for_update(of=links)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                # RFC7009 revocation is idempotent and does not reveal token existence.
                if revoke:
                    return {}
                raise PublicPointError("PROFILE_TOKEN_INVALID", 401)
            if revoke:
                c.execute(update(links).where(links.c.id == row["id"]).values(status="revoked"))
                return {}
            return Status(
                active=row["status"] == "active"
                and row["expires_at"] > self.clock()
                and row["state"] == "active",
                id=row["id"],
                user_id=row["user_id"],
                client_user_id=row["peer_user_id"],
            ).model_dump()

    def list(self, uid):
        with self.db.begin() as c:
            self.actor(c, uid)
            rows = (
                c.execute(
                    select(links)
                    .where(links.c.user_id == uid)
                    .order_by(links.c.created_at.desc(), links.c.id)
                    .limit(100)
                )
                .mappings()
                .all()
            )
        return {
            "items": [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "direction",
                        "peer_origin",
                        "peer_user_id",
                        "peer_handle",
                        "created_at",
                        "expires_at",
                        "revocation_pending",
                    )
                }
                | {
                    "status": "expired"
                    if row["expires_at"] <= self.clock() and row["status"] != "revoked"
                    else row["status"]
                }
                for row in rows
            ],
            "profile_sync": False,
        }

    def revoke(self, uid, lid):
        with self.db.begin() as c:
            self.actor(c, uid)
            row = self.own(c, uid, lid)
            pending = bool(row["remote_token"])
            c.execute(
                update(links)
                .where(links.c.id == lid)
                .values(
                    status="revoked",
                    invite_digest=None,
                    verifier=None,
                    code_digest=None,
                    revocation_pending=pending,
                )
            )
        if pending:
            try:
                self.transport(row["peer_origin"], "revoke", {"token": row["remote_token"]})
            except PublicPointError:
                return {"revoked": True, "peer_notified": False}
            with self.db.begin() as c:
                c.execute(
                    update(links)
                    .where(links.c.id == lid)
                    .values(remote_token=None, revocation_pending=False)
                )
        return {"revoked": True, "peer_notified": True if pending else None}

    def refresh(self, uid, lid):
        with self.db.begin() as c:
            self.actor(c, uid)
            row = self.own(c, uid, lid)
            if (
                row["status"] != "active"
                or row["direction"] != "outbound"
                or row["expires_at"] <= self.clock()
            ):
                raise PublicPointError("PROFILE_LINK_NOT_ACTIVE", 409)
        result = validated(
            Status, self.transport(row["peer_origin"], "status", {"token": row["remote_token"]})
        )
        if (
            result.id != row["remote_id"]
            or result.user_id != row["peer_user_id"]
            or result.client_user_id != uid
        ):
            raise PublicPointError("PROFILE_PEER_INVALID", 502)
        if not result.active:
            with self.db.begin() as c:
                self.actor(c, uid)
                c.execute(
                    update(links)
                    .where(links.c.id == lid, links.c.status == "active")
                    .values(status="revoked", remote_token=None)
                )
        return {"peer_active": result.active, "profile_sync": False}
