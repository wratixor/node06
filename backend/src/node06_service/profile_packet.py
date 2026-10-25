"""Private portable profile data and read-only comparison. No peer authority."""

import hashlib
import json
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy import select

from .geometry import DEFAULT
from .models import authored_points, favorite_points, points, subscriptions, user_geometry, users
from .public_points import PublicPointError

MAX_ITEMS = 128
MAX_BYTES = 60000
PointID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,95}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
RevisionID = Annotated[str, StringConstraints(pattern=r"^v_[0-9a-f]{32}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Source(Strict):
    origin: Annotated[str, StringConstraints(max_length=512)]
    user_id: Annotated[str, StringConstraints(pattern=r"^u_[0-9a-f]{32}$")]
    handle: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")]

    @field_validator("origin")
    @classmethod
    def https_origin(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Expected an HTTPS origin without credentials")
        host = parsed.hostname.encode("idna").decode().lower()
        if ":" in host:
            host = "[" + host + "]"
        port = parsed.port
        if port == 0:
            raise ValueError("Invalid port")
        return "https://" + host + (f":{port}" if port and port != 443 else "")


class Reference(Strict):
    point_id: PointID
    revision_id: RevisionID | None
    content_digest: Digest | None
    available: bool


class Subscription(Reference):
    active: bool
    changed_at: Annotated[str, StringConstraints(min_length=1, max_length=64)]


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class Packet(Strict):
    format: Literal["node06-profile/1"]
    source: Source
    coordinates: Annotated[
        list[Annotated[int, Field(ge=1, le=65535)]], Field(min_length=6, max_length=6)
    ]
    subscriptions: list[Subscription] = Field(max_length=MAX_ITEMS)
    favorites: list[Reference] = Field(max_length=MAX_ITEMS)
    own_points: list[Reference] = Field(max_length=MAX_ITEMS)
    digest: Digest

    @model_validator(mode="after")
    def bounded(self):
        for values in (self.subscriptions, self.favorites, self.own_points):
            if len({item.point_id for item in values}) != len(values):
                raise ValueError("Duplicate point reference")
        value = self.model_dump()
        if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_BYTES:
            raise ValueError("Profile packet exceeds its byte budget")
        if self.digest != digest(self.model_dump(exclude={"digest"})):
            raise ValueError("Profile packet digest mismatch")
        return self


def snapshot(public, user_id: str, origin: str) -> Packet:
    """One consistent private read. No bodies, trust, votes, sessions or source grants."""
    with public.database.connect() as c:
        c = c.execution_options(isolation_level="REPEATABLE READ")
        with c.begin():
            user = c.execute(select(users).where(users.c.id == user_id)).mappings().one()
            coordinates = (
                c.scalar(
                    select(user_geometry.c.coordinates).where(user_geometry.c.user_id == user_id)
                )
                or DEFAULT
            )

            def limited(query):
                rows = c.execute(query.limit(MAX_ITEMS + 1)).mappings().all()
                if len(rows) > MAX_ITEMS:
                    raise PublicPointError("PROFILE_PACKET_TOO_LARGE", 413)
                return rows

            def reference(pid):
                try:
                    p = public.raw_on(c, pid)
                    return {
                        "point_id": pid,
                        "revision_id": p["revision_id"],
                        "content_digest": p["content_digest"],
                        "available": True,
                    }
                except PublicPointError as exc:
                    if exc.code not in ("POINT_NOT_FOUND", "POINT_PURGED"):
                        raise
                    return {
                        "point_id": pid,
                        "revision_id": None,
                        "content_digest": None,
                        "available": False,
                    }

            subs = limited(
                select(subscriptions)
                .where(subscriptions.c.user_id == user_id)
                .order_by(subscriptions.c.point_id)
            )
            saved = limited(
                select(favorite_points)
                .where(favorite_points.c.user_id == user_id)
                .order_by(favorite_points.c.point_id)
            )
            # Only public authored originals are eligible for cross-server display.
            own = limited(
                select(points.c.id)
                .join(authored_points)
                .where(points.c.author_user_id == user_id)
                .order_by(points.c.id)
            )
            own_refs = [reference(row["id"]) for row in own]
            source = Source(origin=origin, user_id=user_id, handle=user["handle"])
            value = {
                "format": "node06-profile/1",
                "source": source.model_dump(),
                "coordinates": coordinates,
                "subscriptions": [
                    {
                        **reference(row["point_id"]),
                        "revision_id": row["revision_id"],
                        "content_digest": row["content_digest"],
                        "active": row["active"],
                        "changed_at": row["updated_at"].isoformat(),
                    }
                    for row in subs
                ],
                "favorites": [reference(row["point_id"]) for row in saved],
                "own_points": [row for row in own_refs if row["available"]],
            }
    value["digest"] = digest(value)
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_BYTES:
        raise PublicPointError("PROFILE_PACKET_TOO_LARGE", 413)
    return Packet.model_validate(value)


def compare(local: Packet, incoming: Packet):
    """Incoming identity is a claim, not proof. URLs are compared, never fetched."""

    def uri(origin, item):
        return origin + "/?" + urlencode({"p": item.point_id, "open": item.point_id})

    def difference(field):
        before = {uri(local.source.origin, p): p.model_dump() for p in getattr(local, field)}
        after = {uri(incoming.source.origin, p): p.model_dump() for p in getattr(incoming, field)}
        return {
            "only_here": sorted(before.keys() - after.keys()),
            "only_in_file": sorted(after.keys() - before.keys()),
            "different": sorted(
                key for key in before.keys() & after.keys() if before[key] != after[key]
            ),
        }

    return {
        "verified_identity": False,
        "applied": False,
        "local_digest": local.digest,
        "incoming_digest": incoming.digest,
        "source": incoming.source.model_dump(),
        "color_changed": local.coordinates != incoming.coordinates,
        **{field: difference(field) for field in ("subscriptions", "favorites", "own_points")},
    }
