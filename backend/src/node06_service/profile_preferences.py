"""Causal preferences. External subscriptions/posts are references, never social votes."""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import Field, StringConstraints, model_validator
from sqlalchemy import func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from .geometry import DEFAULT
from .models import (
    authored_points,
    favorite_points,
    points,
    subscriptions,
    user_geometry,
)
from .models import (
    profile_preference_state as states,
)
from .models import (
    profile_preferences as prefs,
)
from .profile_packet import Source, Strict
from .public_points import PublicPointError
from .social_common import event

KINDS = ("color", "favorites", "subscriptions", "own_points")
Kind = Literal["color", "favorites", "subscriptions", "own_points"]
Scopes = Annotated[list[Kind], Field(max_length=4)]
PAGE = 16
MAX_ITEMS = 10000
MAX_CLOCK = 9223372036854775807


def now_tick():
    return int(datetime.now(UTC).timestamp() * 1000) * 65536


class Entry(Strict):
    kind: Kind
    origin: Annotated[str, Field(max_length=512)]
    point_id: Annotated[str, Field(max_length=96)]
    value: list[Annotated[int, Field(strict=True, ge=1, le=65535)]] | dict
    deleted: bool
    clock: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,18}$")]
    writer_origin: Annotated[str, Field(max_length=512)]
    writer_user_id: Annotated[str, StringConstraints(pattern=r"^u_[0-9a-f]{32}$")]
    event_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]

    @model_validator(mode="after")
    def shape(self):
        if int(self.clock) > MAX_CLOCK:
            raise ValueError("Clock exceeds database range")
        if Source.https_origin(self.writer_origin) != self.writer_origin:
            raise ValueError("Noncanonical writer origin")
        if self.kind == "color":
            if (
                self.origin
                or self.point_id
                or self.deleted
                or not isinstance(self.value, list)
                or len(self.value) != 6
            ):
                raise ValueError("Expected one six-stat preference")
        else:
            if Source.https_origin(self.origin) != self.origin:
                raise ValueError("Noncanonical point origin")
            from .root_import import POINT

            if not POINT.fullmatch(self.point_id) or not isinstance(self.value, dict):
                raise ValueError("Expected canonical point reference")
            if self.kind == "own_points":
                if set(self.value) != {"author_user_id"} or not isinstance(
                    self.value["author_user_id"], str
                ):
                    raise ValueError("Expected original author ID")
                import re

                if not re.fullmatch(r"u_[0-9a-f]{32}", self.value["author_user_id"]):
                    raise ValueError("Invalid original author")
            elif self.value:
                raise ValueError("Point preferences contain no bodies or authority")
        return self


def key(entry):
    return (entry["kind"], entry["origin"], entry["point_id"])


def version(entry):
    return (int(entry["clock"]), entry["writer_origin"], entry["writer_user_id"], entry["event_id"])


def put(c, uid, kind, origin, pid, value, deleted, writer, baseline=None):
    c.execute(
        text(
            "SELECT node06_profile_put(:uid,:kind,:origin,:pid,"
            "CAST(:value AS JSON),:deleted,:writer,:baseline)"
        ),
        dict(
            uid=uid,
            kind=kind,
            origin=origin,
            pid=pid,
            value=json.dumps(value),
            deleted=deleted,
            writer=writer,
            baseline=baseline,
        ),
    )


def configured_put(c, uid, kind, pid, value, deleted):
    origin = c.scalar(text("SELECT current_setting('node06.profile_origin',true)"))
    if origin:
        put(c, uid, kind, origin, pid, value, deleted, origin)


def rows(c, uid):
    return select(prefs).where(prefs.c.user_id == uid)


def seed(c, uid, origin, public):
    c.execute(insert(states).values(user_id=uid).on_conflict_do_nothing())
    state = (
        c.execute(select(states).where(states.c.user_id == uid).with_for_update()).mappings().one()
    )
    if not state["seeded"]:
        color = (
            c.execute(select(user_geometry).where(user_geometry.c.user_id == uid))
            .mappings()
            .one_or_none()
        )
        stamp = (
            min(now_tick(), max(1, int(color["updated_at"].timestamp() * 1000) * 65536))
            if color
            else 1
        )
        put(
            c,
            uid,
            "color",
            "",
            "",
            color["coordinates"] if color else DEFAULT,
            False,
            origin,
            stamp,
        )
        for table, kind in ((favorite_points, "favorites"), (subscriptions, "subscriptions")):
            entries = (
                c.execute(select(table).where(table.c.user_id == uid).limit(MAX_ITEMS + 1))
                .mappings()
                .all()
            )
            if len(entries) > MAX_ITEMS:
                raise PublicPointError("PROFILE_SYNC_LIMIT", 413)
            for row in entries:
                put(
                    c,
                    uid,
                    kind,
                    origin,
                    row["point_id"],
                    {},
                    not row.get("active", True),
                    origin,
                    1,
                )
        c.execute(update(states).where(states.c.user_id == uid).values(seeded=True))
    # Public source-owned originals: no body/title/cache and no quarantined/hidden originals.
    visible = c.scalars(
        public._query()
        .with_only_columns(points.c.id, maintain_column_froms=True)
        .where(points.c.author_user_id == uid, authored_points.c.point_id.is_not(None))
        .limit(MAX_ITEMS + 1)
    ).all()
    if len(visible) > MAX_ITEMS:
        raise PublicPointError("PROFILE_SYNC_LIMIT", 413)
    existing = (
        c.execute(rows(c, uid).where(prefs.c.kind == "own_points", prefs.c.origin == origin))
        .mappings()
        .all()
    )
    visible = set(visible)
    old = {row["point_id"]: row for row in existing}
    for pid in set(visible) | set(old):
        removed = pid not in visible
        if pid not in old or old[pid]["deleted"] != removed:
            put(c, uid, "own_points", origin, pid, {"author_user_id": uid}, removed, origin)
    if c.scalar(select(func.count()).select_from(prefs).where(prefs.c.user_id == uid)) > MAX_ITEMS:
        raise PublicPointError("PROFILE_SYNC_LIMIT", 413)


def page(c, uid, scopes, after=None):
    query = rows(c, uid).where(prefs.c.kind.in_(scopes))
    if after:
        query = query.where(tuple_(prefs.c.kind, prefs.c.origin, prefs.c.point_id) > tuple(after))
    data = (
        c.execute(query.order_by(prefs.c.kind, prefs.c.origin, prefs.c.point_id).limit(PAGE + 1))
        .mappings()
        .all()
    )
    result = [
        {**{k: v for k, v in row.items() if k != "user_id"}, "clock": str(row["clock"])}
        for row in data[:PAGE]
    ]
    return result, list(key(data[PAGE - 1])) if len(data) > PAGE else None


def apply(c, uid, origin, entries, scopes):
    if len({key(e) for e in entries}) != len(entries):
        raise PublicPointError("PROFILE_SYNC_DUPLICATE", 422)
    if any(e["kind"] not in scopes for e in entries):
        raise PublicPointError("PROFILE_SYNC_SCOPE", 403)
    if any(int(e["clock"]) > now_tick() + 5 * 60 * 1000 * 65536 for e in entries):
        raise PublicPointError("PROFILE_SYNC_CLOCK_AHEAD", 409)
    count = c.scalar(select(func.count()).select_from(prefs).where(prefs.c.user_id == uid))
    changed = 0
    c.execute(text("SELECT set_config('node06.profile_import','on',true)"))
    for entry in entries:
        if entry["kind"] in ("subscriptions", "own_points") and entry["origin"] == origin:
            continue  # Never turn external account state into local support/authorship.
        where = (
            (prefs.c.user_id == uid)
            & (prefs.c.kind == entry["kind"])
            & (prefs.c.origin == entry["origin"])
            & (prefs.c.point_id == entry["point_id"])
        )
        old = c.execute(select(prefs).where(where)).mappings().one_or_none()
        if old and version(entry) == version(old):
            if old["value"] != entry["value"] or old["deleted"] != entry["deleted"]:
                raise PublicPointError("PROFILE_SYNC_VERSION_CONFLICT", 409)
            continue
        if old and version(entry) < version(old):
            continue
        if not old:
            count += 1
            if count > MAX_ITEMS:
                raise PublicPointError("PROFILE_SYNC_LIMIT", 413)
        c.execute(
            insert(prefs)
            .values(user_id=uid, **{**entry, "clock": int(entry["clock"])})
            .on_conflict_do_update(
                index_elements=[prefs.c.user_id, prefs.c.kind, prefs.c.origin, prefs.c.point_id],
                set_={**entry, "clock": int(entry["clock"])},
            )
        )
        c.execute(
            update(states)
            .where(states.c.user_id == uid)
            .values(clock=func.greatest(states.c.clock, int(entry["clock"])))
        )
        if entry["kind"] == "color":
            current = (
                c.scalar(select(user_geometry.c.coordinates).where(user_geometry.c.user_id == uid))
                or DEFAULT
            )
            if current != entry["value"]:
                c.execute(
                    insert(user_geometry)
                    .values(user_id=uid, coordinates=entry["value"])
                    .on_conflict_do_update(
                        index_elements=[user_geometry.c.user_id],
                        set_={"coordinates": entry["value"], "updated_at": datetime.now(UTC)},
                    )
                )
                event(c, "coordinates-changed", actor=uid, payload={"source": "profile-sync"})
        changed += 1
    c.execute(text("SELECT set_config('node06.profile_import','off',true)"))
    return changed


def favorite_ids(c, uid, origin):
    legacy = set(
        c.scalars(select(favorite_points.c.point_id).where(favorite_points.c.user_id == uid))
    )
    for row in c.execute(
        rows(c, uid).where(prefs.c.kind == "favorites", prefs.c.origin == origin)
    ).mappings():
        if row["deleted"]:
            legacy.discard(row["point_id"])
        else:
            legacy.add(row["point_id"])
    return sorted(legacy)


def reference(entry):
    return entry["origin"] + "/?" + urlencode({"p": entry["point_id"], "open": entry["point_id"]})
