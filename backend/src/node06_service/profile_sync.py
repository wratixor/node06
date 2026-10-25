"""Durable, bounded at-least-once preference exchange; no remote graph writes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy import select, update

from .graph_writes import lock_graph
from .models import profile_links as links
from .models import users
from .profile_links import LinkID, UserID, digest, validated
from .profile_packet import Strict
from .profile_preferences import Entry, Scopes, apply, page, seed
from .public_points import PublicPointError

Cursor = Annotated[list[str], Field(min_length=3, max_length=3)]


class Message(Strict):
    protocol: Literal["node06-profile-sync/1"] = "node06-profile-sync/1"
    link_id: LinkID
    user_id: UserID
    send: Scopes
    receive: Scopes
    entries: Annotated[list[Entry], Field(max_length=16)]
    after: Cursor | None = None

    @model_validator(mode="after")
    def shape(self):
        if len(self.send) != len(set(self.send)) or len(self.receive) != len(set(self.receive)):
            raise ValueError("Duplicate permission")
        if self.after:
            from .profile_packet import Source
            from .profile_preferences import KINDS
            from .root_import import POINT

            kind, origin, pid = self.after
            if kind not in KINDS or (kind == "color" and (origin or pid)):
                raise ValueError("Invalid cursor")
            if kind != "color" and (
                Source.https_origin(origin) != origin or not POINT.fullmatch(pid)
            ):
                raise ValueError("Invalid cursor")
        return self


class Reply(Strict):
    protocol: Literal["node06-profile-sync/1"] = "node06-profile-sync/1"
    link_id: LinkID
    user_id: UserID
    client_user_id: UserID
    entries: Annotated[list[Entry], Field(max_length=16)]
    next_cursor: Cursor | None


class SyncSettings(Strict):
    enabled: bool
    send: Scopes
    receive: Scopes


class ProfileSync:
    def __init__(self, public, origin, transport, authorize=None, seconds=10):
        self.public, self.db, self.origin = public, public.database, origin
        self.transport, self.authorize, self.seconds = transport, authorize, seconds
        self.public.site_id = None

    def actor(self, c, uid):
        if self.authorize:
            self.authorize(c, uid)
        elif not c.scalar(
            select(users.c.id).where(users.c.id == uid, users.c.state == "active").with_for_update()
        ):
            raise PublicPointError("AUTH_REQUIRED", 401)

    def own(self, c, uid, lid):
        row = (
            c.execute(
                select(links).where(links.c.id == lid, links.c.user_id == uid).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if not row:
            raise PublicPointError("PROFILE_LINK_NOT_FOUND", 404)
        return row

    @staticmethod
    def live(row):
        if row["status"] != "active" or row["expires_at"] <= datetime.now(UTC):
            raise PublicPointError("PROFILE_LINK_NOT_ACTIVE", 409)
        if not row["sync_enabled"]:
            raise PublicPointError("PROFILE_SYNC_PAUSED", 409)

    def settings(self, uid, lid, payload):
        with self.db.begin() as c:
            lock_graph(c)
            self.actor(c, uid)
            row = self.own(c, uid, lid)
            if not (row["remote_data_token"] or row["data_token_digest"]):
                raise PublicPointError("PROFILE_DATA_CONSENT_REQUIRED", 409)
            if not set(payload.send) <= set(row["sync_send_allowed"]) or not set(
                payload.receive
            ) <= set(row["sync_receive_allowed"]):
                raise PublicPointError("PROFILE_DATA_CONSENT_REQUIRED", 409)
            c.execute(
                update(links)
                .where(links.c.id == lid)
                .values(
                    sync_enabled=payload.enabled,
                    sync_send=sorted(set(payload.send)),
                    sync_receive=sorted(set(payload.receive)),
                    sync_generation=row["sync_generation"] + 1,
                    sync_lease=None,
                    sync_lease_until=None,
                    sync_next_check=datetime.now(UTC),
                    sync_local_cursor=None,
                    sync_peer_cursor=None,
                    sync_local_done=False,
                    sync_peer_done=False,
                    sync_error=None,
                )
            )
        return {"saved": True}

    def receive(self, token, message):
        with self.db.connect() as c:
            uid = c.scalar(
                select(links.c.user_id).where(links.c.data_token_digest == digest(token))
            )
        if not uid:
            raise PublicPointError("PROFILE_DATA_TOKEN_INVALID", 401)
        with self.db.begin() as c:
            lock_graph(c)
            self.actor(c, uid)
            row = (
                c.execute(
                    select(links)
                    .where(links.c.data_token_digest == digest(token))
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if not row:
                raise PublicPointError("PROFILE_DATA_TOKEN_INVALID", 401)
            self.live(row)
            if (
                row["direction"] != "inbound"
                or row["id"] != message.link_id
                or row["peer_user_id"] != message.user_id
            ):
                raise PublicPointError("PROFILE_SYNC_IDENTITY", 403)
            if not set(message.send) <= set(row["sync_receive_allowed"]) or not set(
                message.receive
            ) <= set(row["sync_send_allowed"]):
                raise PublicPointError("PROFILE_SYNC_SCOPE", 403)
            if any(e.kind not in message.send for e in message.entries):
                raise PublicPointError("PROFILE_SYNC_SCOPE", 403)
            seed(c, uid, self.origin, self.public)
            incoming = set(message.send) & set(row["sync_receive"])
            outgoing = set(message.receive) & set(row["sync_send"])
            apply(
                c,
                uid,
                self.origin,
                [e.model_dump() for e in message.entries if e.kind in incoming],
                incoming,
            )
            entries, cursor = page(c, uid, outgoing, message.after)
            c.execute(
                update(links)
                .where(links.c.id == row["id"])
                .values(sync_last_success=datetime.now(UTC), sync_error=None)
            )
            return Reply(
                link_id=row["id"],
                user_id=uid,
                client_user_id=message.user_id,
                entries=entries,
                next_cursor=cursor,
            ).model_dump()

    def step(self, uid, lid):
        lease = uuid4().hex
        with self.db.begin() as c:
            lock_graph(c)
            self.actor(c, uid)
            row = self.own(c, uid, lid)
            self.live(row)
            if row["direction"] != "outbound" or not row["remote_data_token"]:
                raise PublicPointError("PROFILE_SYNC_INITIATOR_REQUIRED", 409)
            if row["sync_lease_until"] and row["sync_lease_until"] > datetime.now(UTC):
                raise PublicPointError("PROFILE_SYNC_BUSY", 409)
            seed(c, uid, self.origin, self.public)
            entries, local_cursor = (
                page(c, uid, row["sync_send"], row["sync_local_cursor"])
                if not row["sync_local_done"]
                else ([], None)
            )
            c.execute(
                update(links)
                .where(links.c.id == lid)
                .values(
                    sync_lease=lease,
                    sync_lease_until=datetime.now(UTC) + timedelta(seconds=self.seconds + 30),
                )
            )
            message = Message(
                link_id=row["remote_id"],
                user_id=uid,
                send=row["sync_send"],
                receive=[] if row["sync_peer_done"] else row["sync_receive"],
                entries=entries,
                after=row["sync_peer_cursor"],
            )
        try:
            result = validated(
                Reply,
                self.transport(
                    row["peer_origin"],
                    "sync",
                    {"token": row["remote_data_token"], "packet": message.model_dump_json()},
                ),
            )
            if (
                result.link_id != row["remote_id"]
                or result.user_id != row["peer_user_id"]
                or result.client_user_id != uid
            ):
                raise PublicPointError("PROFILE_SYNC_IDENTITY", 502)
            # A cursor acknowledges exactly the last item, never an arbitrary skip.
            from .profile_preferences import key

            keys = [key(e.model_dump()) for e in result.entries]
            if (
                keys != sorted(set(keys))
                or (keys and message.after and keys[0] <= tuple(message.after))
                or (
                    result.next_cursor is not None
                    and (not keys or tuple(result.next_cursor) != keys[-1])
                )
            ):
                raise PublicPointError("PROFILE_SYNC_CURSOR", 502)
            with self.db.begin() as c:
                lock_graph(c)
                self.actor(c, uid)
                current = self.own(c, uid, lid)
                self.live(current)
                if (
                    current["sync_generation"] != row["sync_generation"]
                    or current["sync_lease"] != lease
                ):
                    raise PublicPointError("PROFILE_SYNC_CHANGED", 409)
                apply(
                    c,
                    uid,
                    self.origin,
                    [e.model_dump() for e in result.entries],
                    message.receive,
                )
                finished = local_cursor is None and result.next_cursor is None
                c.execute(
                    update(links)
                    .where(links.c.id == lid)
                    .values(
                        sync_local_cursor=None if finished else local_cursor,
                        sync_peer_cursor=None if finished else result.next_cursor,
                        sync_local_done=False if finished else local_cursor is None,
                        sync_peer_done=False if finished else result.next_cursor is None,
                        sync_next_check=datetime.now(UTC)
                        + timedelta(seconds=60 if finished else 2),
                        sync_last_success=datetime.now(UTC),
                        sync_lease=None,
                        sync_lease_until=None,
                        sync_error=None,
                        sync_attempts=0,
                    )
                )
            return {"complete": finished, "received": len(result.entries), "sent": len(entries)}
        except Exception as exc:
            # Keep cursors on outage: repeat only idempotent versioned changes, no silent skip.
            code = exc.code if isinstance(exc, PublicPointError) else "PROFILE_SYNC_UNAVAILABLE"
            with self.db.begin() as c:
                c.execute(
                    update(links)
                    .where(links.c.id == lid, links.c.sync_lease == lease)
                    .values(
                        sync_lease=None,
                        sync_lease_until=None,
                        sync_error=code,
                        sync_attempts=row["sync_attempts"] + 1,
                        sync_next_check=datetime.now(UTC)
                        + timedelta(seconds=min(900, 10 * 2 ** min(row["sync_attempts"], 7))),
                    )
                )
            raise
